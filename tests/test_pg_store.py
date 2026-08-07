"""Integration tests for the PostgreSQL-backed store (Phase 1/4 persistence).

The three tests that take the ``dsn`` fixture are Docker-gated: they run only when
``OWR_TEST_DATABASE_URL`` points at a live Postgres with migrations 001 + 002
applied, and are marked with ``@requires_db``. See docs/HANDOFF_POSTGRES_REPO.md
for the Docker recipe. The two serializer tests below run without a database; the
module-level ``importorskip`` is what gates them, since ``owr.api.pg_store``
imports ``psycopg`` at module level.
"""

import os
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

psycopg = pytest.importorskip("psycopg")

from owr.api import create_app  # noqa: E402
from owr.api.pg_store import (  # noqa: E402
    PostgresRepository,
    _persisted_window_json,
    _window_from_persisted,
)
from owr.models import StressWindow  # noqa: E402

_DSN = os.getenv("OWR_TEST_DATABASE_URL")
requires_db = pytest.mark.skipif(
    not _DSN, reason="set OWR_TEST_DATABASE_URL to a live Postgres to run PG store tests"
)


@pytest.fixture
def dsn() -> str:
    assert _DSN is not None  # guarded by @requires_db
    with psycopg.connect(_DSN) as conn:
        conn.execute(
            "TRUNCATE app.decision_package, app.run_result_hourly, app.run_result_daily, "
            "app.simulation_run, app.scenario RESTART IDENTITY CASCADE"
        )
        conn.commit()
    return _DSN


def _scenario_body() -> dict:
    return {
        "name": "winter cold snap",
        "storage_total_mwh": 20000,
        "storage_start_mwh": 20000,
        "power_output_mw": 2000,
        "efficiency": 1.0,
        "soc_floor_frac": 0.33,
        "strategic_reserve_frac": 0.0,
        "season": "winter",
        "date_start": "2026-01-10",
        "date_end": "2026-01-12",
        "min_stress_window_days": 2,
        "severity_percentile": 0.5,
        "transmission_limit_mw": None,
        "available_capacity_mw": 13000,
        "peak_weight": 0.7,
        "smooth_weight": 0.3,
        "wind_generation_multiplier": 2.5,
    }


def _days(n: int = 3) -> list[dict]:
    out = []
    for i in range(n):
        load = [8000.0] * 24
        load[17], load[18], load[19] = 10000.0, 12000.0, 10000.0
        out.append(
            {
                "date": (date(2026, 1, 10) + timedelta(days=i)).isoformat(),
                "hourly_load_mw": load,
                "hourly_wind_mw": [500.0] * 24,
                "demand_percentile": 0.95,
                "wind_forecast_frac": 0.1,
            }
        )
    return out


@requires_db
def test_scenario_roundtrips_all_fields(dsn: str):
    """add_scenario -> get_scenario preserves every field, including the migration-002
    columns (available_capacity_mw, peak_weight, smooth_weight)."""
    from owr.api.schemas import ScenarioCreate

    repo = PostgresRepository(dsn)
    inputs = ScenarioCreate(**_scenario_body())
    rec = repo.add_scenario(inputs)
    got = repo.get_scenario(rec.id)
    assert got is not None
    assert got.inputs == inputs
    assert got.inputs.available_capacity_mw == 13000
    assert got.inputs.peak_weight == 0.7
    assert got.inputs.smooth_weight == 0.3
    assert got.inputs.wind_generation_multiplier == 2.5


@requires_db
def test_run_persists_across_fresh_repository(dsn: str):
    """The point of the task: a run's results, peaks, stress windows, and decision
    package survive into a brand-new repository/app (i.e. a later process)."""
    client = TestClient(create_app(PostgresRepository(dsn)))

    sid = client.post("/scenarios", json=_scenario_body()).json()["id"]
    run = client.post(f"/scenarios/{sid}/runs", json={"days": _days()})
    assert run.status_code == 201
    assert run.json()["status"] == "succeeded"
    rid = run.json()["id"]

    first = client.get(f"/runs/{rid}/results").json()
    assert len(first["daily"]) == 3
    assert first["reserve_peak_mw"] < first["baseline_peak_mw"]
    client.post(f"/runs/{rid}/decision-package")

    # A completely fresh repository + app: nothing shared but the database.
    fresh = TestClient(create_app(PostgresRepository(dsn)))

    got_run = fresh.get(f"/runs/{rid}")
    assert got_run.status_code == 200
    assert got_run.json()["status"] == "succeeded"

    second = fresh.get(f"/runs/{rid}/results").json()
    assert second["baseline_peak_mw"] == first["baseline_peak_mw"]
    assert second["reserve_peak_mw"] == first["reserve_peak_mw"]
    assert second["final_soc"] == first["final_soc"]
    assert len(second["daily"]) == 3
    # hourly rows round-trip through the (run_id, ts) primary key
    assert len(second["daily"][0]["hourly"]) == 24

    windows = fresh.get(f"/runs/{rid}/stress-windows").json()
    assert len(windows) == 1
    assert windows[0]["days"] == 3

    pkg = fresh.post(f"/runs/{rid}/decision-package").json()
    assert "reduction in peak severity" in pkg["annotation"]


@requires_db
def test_failed_run_persists_failed_status(dsn: str):
    """A run whose inputs the engine rejects persists status='failed' (the route
    saves the run before raising), visible from a fresh repository."""
    client = TestClient(create_app(PostgresRepository(dsn)))
    sid = client.post("/scenarios", json=_scenario_body()).json()["id"]

    # starting_soc above capacity passes Pydantic validation but the engine rejects it.
    r = client.post(
        f"/scenarios/{sid}/runs", json={"days": _days(), "starting_soc": 999999}
    )
    assert r.status_code == 422

    # The run was created before the failure; find it and confirm it persisted 'failed'.
    fresh = PostgresRepository(dsn)
    with psycopg.connect(dsn) as conn:
        row = conn.execute("SELECT id FROM app.simulation_run ORDER BY id DESC LIMIT 1").fetchone()
    assert row is not None
    rec = fresh.get_run(row[0])
    assert rec is not None
    assert rec.status == "failed"


def test_persisted_window_json_round_trips_every_field():
    w = StressWindow(
        start=date(2026, 1, 9),
        end=date(2026, 1, 11),
        days=3,
        threshold_mwh=400_000.0,
        severity_percentile=0.9,
        peak_hourly_load_mw=12_000.0,
    )
    persisted = _persisted_window_json(w)
    assert "first_hour_index" not in persisted
    assert _window_from_persisted(persisted) == w


def test_window_from_persisted_accepts_a_pre_0805_row():
    row = {"start": "2026-01-09", "end": "2026-01-11", "days": 3}
    w = _window_from_persisted(row)
    assert w.threshold_mwh is None
    assert w.severity_percentile is None
    assert w.peak_hourly_load_mw is None
    assert w.last_hour_index == 71
