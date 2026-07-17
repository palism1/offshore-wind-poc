"""PostgreSQL-backed Repository (Phase 1 schema + migration 002).

Implements the same ``owr.api.store.Repository`` protocol as the in-memory store,
so the API routes are unchanged. Persistence is "hybrid": scenarios, per-day and
per-hour results live in the normalized ``app.*`` tables as designed, while the
small run-level summary (final SoC, peak scalars, detected stress windows) rides
in a ``result_summary`` JSONB column added by migration 002.

psycopg (v3) is an optional dependency: this module is imported only when
``OWR_DATABASE_URL`` is set, so the default in-memory API needs no database driver.
Each method uses its own short-lived connection, which makes the store safe to call
from FastAPI's worker threads without sharing a connection.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

from owr.api.schemas import ScenarioCreate
from owr.api.store import RunRecord, ScenarioRecord
from owr.models import DailyResult, HourlyResult, StressWindow
from owr.simulator import SimulationResult

# Scenario columns that map 1:1 to ScenarioCreate fields, in a fixed order reused
# by both INSERT and SELECT so the two never drift.
_SCENARIO_FIELDS = (
    "name",
    "storage_total_mwh",
    "storage_start_mwh",
    "power_output_mw",
    "efficiency",
    "soc_floor_frac",
    "strategic_reserve_frac",
    "season",
    "date_start",
    "date_end",
    "min_stress_window_days",
    "severity_percentile",
    "transmission_limit_mw",
    "available_capacity_mw",
    "peak_weight",
    "smooth_weight",
)


class PostgresRepository:
    """Repository backed by PostgreSQL. Implements owr.api.store.Repository."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn, row_factory=dict_row)

    # -- scenarios ----------------------------------------------------------

    def add_scenario(self, inputs: ScenarioCreate) -> ScenarioRecord:
        cols = ", ".join(_SCENARIO_FIELDS)
        placeholders = ", ".join(["%s"] * len(_SCENARIO_FIELDS))
        values = [getattr(inputs, f) for f in _SCENARIO_FIELDS]
        with self._connect() as conn:
            row = conn.execute(
                f"INSERT INTO app.scenario ({cols}) VALUES ({placeholders}) "
                f"RETURNING id, created_at",
                values,
            ).fetchone()
        return ScenarioRecord(id=row["id"], inputs=inputs, created_at=row["created_at"])

    def get_scenario(self, scenario_id: int) -> ScenarioRecord | None:
        cols = ", ".join(_SCENARIO_FIELDS)
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT id, created_at, {cols} FROM app.scenario WHERE id = %s",
                (scenario_id,),
            ).fetchone()
        if row is None:
            return None
        inputs = ScenarioCreate(**{f: row[f] for f in _SCENARIO_FIELDS})
        return ScenarioRecord(id=row["id"], inputs=inputs, created_at=row["created_at"])

    # -- runs ---------------------------------------------------------------

    def add_run(self, scenario_id: int, code_version: str) -> RunRecord:
        with self._connect() as conn:
            row = conn.execute(
                "INSERT INTO app.simulation_run (scenario_id, code_version, "
                "dataset_versions, status) VALUES (%s, %s, %s, 'pending') "
                "RETURNING id, created_at",
                (scenario_id, code_version, Json({})),
            ).fetchone()
        return RunRecord(
            id=row["id"],
            scenario_id=scenario_id,
            status="pending",
            code_version=code_version,
            created_at=row["created_at"],
        )

    def save_run(self, run: RunRecord) -> None:
        summary = _summary_json(run) if run.result is not None else None
        with self._connect() as conn, conn.transaction():
            conn.execute(
                "UPDATE app.simulation_run SET status = %s, code_version = %s, "
                "result_summary = %s WHERE id = %s",
                (run.status, run.code_version, Json(summary) if summary else None, run.id),
            )
            # Result rows are rewritten wholesale so save_run stays idempotent.
            conn.execute("DELETE FROM app.run_result_hourly WHERE run_id = %s", (run.id,))
            conn.execute("DELETE FROM app.run_result_daily WHERE run_id = %s", (run.id,))
            if run.result is not None:
                _insert_results(conn, run.id, run.result)
            if run.decision_package is not None:
                conn.execute(
                    "INSERT INTO app.decision_package (run_id, payload, annotation) "
                    "VALUES (%s, %s, %s) ON CONFLICT (run_id) DO UPDATE SET "
                    "payload = EXCLUDED.payload, annotation = EXCLUDED.annotation",
                    (
                        run.id,
                        Json(run.decision_package.get("payload", {})),
                        run.decision_package.get("annotation"),
                    ),
                )

    def get_run(self, run_id: int) -> RunRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, scenario_id, code_version, status, result_summary, created_at "
                "FROM app.simulation_run WHERE id = %s",
                (run_id,),
            ).fetchone()
            if row is None:
                return None
            summary = row["result_summary"]
            result = _load_result(conn, run_id, summary) if summary else None
            windows = _load_windows(summary) if summary else []
            decision = _load_decision_package(conn, run_id)
        return RunRecord(
            id=row["id"],
            scenario_id=row["scenario_id"],
            status=row["status"],
            code_version=row["code_version"],
            created_at=row["created_at"],
            result=result,
            stress_windows=windows,
            decision_package=decision,
        )


# -- serialization helpers --------------------------------------------------


def _summary_json(run: RunRecord) -> dict:
    res = run.result
    assert res is not None
    return {
        "final_soc": res.final_soc,
        "baseline_peak_mw": res.baseline_peak_mw,
        "reserve_peak_mw": res.reserve_peak_mw,
        "stress_windows": [
            {"start": w.start.isoformat(), "end": w.end.isoformat(), "days": w.days}
            for w in run.stress_windows
        ],
    }


def _hour_ts(day: date, ts_hour: int) -> datetime:
    """Concrete UTC timestamp for an (date, hour-of-day) result cell. Stored so the
    run_result_hourly primary key (run_id, ts) is meaningful and round-trips exactly."""
    return datetime(day.year, day.month, day.day, ts_hour, tzinfo=UTC)


def _insert_results(conn: psycopg.Connection, run_id: int, result: SimulationResult) -> None:
    for d in result.daily:
        conn.execute(
            "INSERT INTO app.run_result_daily (run_id, date, budget, priority, "
            "usable_energy, recharge_sufficiency_ratio) VALUES (%s, %s, %s, %s, %s, %s)",
            (run_id, d.date, d.budget, d.priority, d.usable_energy, d.recharge_sufficiency_ratio),
        )
        for h in d.hourly:
            conn.execute(
                "INSERT INTO app.run_result_hourly (run_id, ts, soc, charge, discharge, "
                "discharge_peak, discharge_smooth, gross_load, net_load, capacity_margin) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    run_id,
                    _hour_ts(d.date, h.ts_hour),
                    h.soc,
                    h.charge,
                    h.discharge,
                    h.discharge_peak,
                    h.discharge_smooth,
                    h.gross_load,
                    h.net_load,
                    h.capacity_margin,
                ),
            )


def _load_result(conn: psycopg.Connection, run_id: int, summary: dict) -> SimulationResult:
    hourly_rows = conn.execute(
        "SELECT ts, soc, charge, discharge, discharge_peak, discharge_smooth, "
        "gross_load, net_load, capacity_margin FROM app.run_result_hourly "
        "WHERE run_id = %s ORDER BY ts",
        (run_id,),
    ).fetchall()
    by_date: dict[date, list[HourlyResult]] = {}
    for r in hourly_rows:
        ts = r["ts"].astimezone(UTC)
        by_date.setdefault(ts.date(), []).append(
            HourlyResult(
                ts_hour=ts.hour,
                soc=r["soc"],
                charge=r["charge"],
                discharge=r["discharge"],
                discharge_peak=r["discharge_peak"],
                discharge_smooth=r["discharge_smooth"],
                gross_load=r["gross_load"],
                net_load=r["net_load"],
                capacity_margin=r["capacity_margin"],
            )
        )
    daily_rows = conn.execute(
        "SELECT date, budget, priority, usable_energy, recharge_sufficiency_ratio "
        "FROM app.run_result_daily WHERE run_id = %s ORDER BY date",
        (run_id,),
    ).fetchall()
    daily = [
        DailyResult(
            date=r["date"],
            budget=r["budget"],
            priority=r["priority"],
            usable_energy=r["usable_energy"],
            recharge_sufficiency_ratio=r["recharge_sufficiency_ratio"],
            hourly=by_date.get(r["date"], []),
        )
        for r in daily_rows
    ]
    return SimulationResult(
        daily=daily,
        final_soc=summary["final_soc"],
        baseline_peak_mw=summary["baseline_peak_mw"],
        reserve_peak_mw=summary["reserve_peak_mw"],
    )


def _load_windows(summary: dict) -> list[StressWindow]:
    return [
        StressWindow(
            start=date.fromisoformat(w["start"]),
            end=date.fromisoformat(w["end"]),
            days=w["days"],
        )
        for w in summary.get("stress_windows", [])
    ]


def _load_decision_package(conn: psycopg.Connection, run_id: int) -> dict | None:
    row = conn.execute(
        "SELECT payload, annotation FROM app.decision_package WHERE run_id = %s",
        (run_id,),
    ).fetchone()
    if row is None:
        return None
    return {"payload": row["payload"], "annotation": row["annotation"]}
