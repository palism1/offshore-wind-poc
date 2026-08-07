"""FastAPI application factory and routes (Phase 4).

Endpoints map 1:1 to docs/PLAN.md Phase 4:
    POST /scenarios                     create a scenario (Step 1 inputs)
    GET  /scenarios/{id}                fetch it
    POST /scenarios/{id}/runs           run the simulation (synchronous for the POC)
    GET  /runs/{id}                     run status
    GET  /runs/{id}/stress-windows      detected stress windows (Step 2)
    GET  /runs/{id}/results             hourly + daily results and summary
    POST /runs/{id}/decision-package    assemble an annotated explanation payload

Runs are executed synchronously here; the async run/poll pattern in the plan is a
later change once a task queue exists. OpenAPI docs (/docs) are the integration
contract for the frontend.
"""

from __future__ import annotations

import math
import os

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from owr import metrics
from owr.api import schemas
from owr.api.store import InMemoryRepository, Repository, RunRecord
from owr.config import DEFAULT_CONFIG
from owr.models import DayProfile, StorageAsset, StressWindow
from owr.simulator import simulate
from owr.stress_finder import find_stress_windows, with_peak_hourly_load
from owr.version import code_version


def _asset(inp: schemas.ScenarioCreate) -> StorageAsset:
    return StorageAsset(
        total_mwh=inp.storage_total_mwh,
        power_mw=inp.power_output_mw,
        efficiency=inp.efficiency,
        soc_floor_frac=inp.soc_floor_frac,
        strategic_reserve_frac=inp.strategic_reserve_frac,
    )


def _day_profiles(
    days: list[schemas.DayProfileIn], *, wind_multiplier: float = 1.0
) -> list[DayProfile]:
    """Build engine ``DayProfile`` objects from the wire payload.

    ``wind_multiplier`` scales ``hourly_wind_mw`` here (D11, D12: the multiplier
    applies once, at the simulator input boundary; site 2 of the wind-consumer
    trace). ``wind_forecast_frac`` is never scaled: it is a fraction of nameplate
    capacity, not an energy. A multiplier that overflows a wind value to a
    non-finite number raises ``ValueError``, which the caller turns into a 422.
    """
    result = []
    for d in days:
        scaled_wind = (
            tuple(w * wind_multiplier for w in d.hourly_wind_mw) if d.hourly_wind_mw else ()
        )
        if any(not math.isfinite(w) for w in scaled_wind):
            raise ValueError(
                f"hourly_wind_mw on {d.date.isoformat()} overflows to non-finite after "
                f"applying wind_multiplier={wind_multiplier!r}"
            )
        result.append(
            DayProfile(
                date=d.date,
                hourly_load_mw=tuple(d.hourly_load_mw),
                hourly_wind_mw=scaled_wind,
                demand_percentile=d.demand_percentile,
                wind_forecast_frac=d.wind_forecast_frac,
            )
        )
    return result


def _sanitize_non_finite(value: object) -> object:
    """Replace any inf/nan float in a validation-error payload with its string
    form, recursively.

    A rejected ``allow_inf_nan=False`` field (e.g. ``wind_generation_multiplier``)
    echoes the raw offending value back in FastAPI's 422 error detail. Starlette's
    default ``JSONResponse`` serializes with ``allow_nan=False``, so an
    unsanitized inf/nan in that payload turns the intended 422 into an
    unhandled 500. This walks the error structure and stringifies any such
    float before the response is built.
    """
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {k: _sanitize_non_finite(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_non_finite(v) for v in value]
    return value


def _severity_reduction(baseline_peak: float, reserve_peak: float) -> float:
    if baseline_peak <= 0:
        return 0.0
    return metrics.severity_reduction(baseline_peak, reserve_peak)


def _window_json(w: StressWindow) -> dict:
    """The wire shape for one stress window across the API layer. Mirrors
    ``schemas.StressWindowOut`` and matches ``cli._window_json`` key for key. The
    persisted shape in ``pg_store`` is different and is named apart."""
    return {
        "start": w.start.isoformat(),
        "end": w.end.isoformat(),
        "days": w.days,
        "first_hour_index": w.first_hour_index,
        "last_hour_index": w.last_hour_index,
        "peak_hourly_load_mw": w.peak_hourly_load_mw,
        "threshold_mwh": w.threshold_mwh,
        "severity_percentile": w.severity_percentile,
    }


def _annotation(scenario: schemas.ScenarioCreate, run: RunRecord) -> tuple[dict, str]:
    """Build the decision-package payload and a deterministic, provenance-tagged
    plain-language explanation. No external AI call: the POC ships an auditable
    template so results are reproducible; a real assistant slots in behind this."""
    assert run.result is not None
    res = run.result
    reduction = _severity_reduction(res.baseline_peak_mw, res.reserve_peak_mw)
    # The run succeeded, so the asset is valid by construction (StorageAsset.__post_init__
    # already ran once when the run built it).
    asset = _asset(scenario)
    payload = {
        "code_version": run.code_version,
        "scenario": scenario.model_dump(mode="json"),
        "stress_windows": [_window_json(w) for w in run.stress_windows],
        "summary": {
            "baseline_peak_mw": res.baseline_peak_mw,
            "reserve_peak_mw": res.reserve_peak_mw,
            "severity_reduction": reduction,
            "final_soc_mwh": res.final_soc,
            "min_soc_mwh": asset.min_soc_mwh,
        },
    }
    n_windows = len(run.stress_windows)
    # F6: state the floor position the run actually measured, rather than assuming
    # "above". Reachable without F1: a scenario whose storage_start_mwh sits under
    # the floor can never discharge and ends under the floor, so this branch is
    # live even on an otherwise-correct run. Do not delete it as dead.
    above = res.final_soc >= asset.min_soc_mwh - 1e-6
    position = "above" if above else "below"
    annotation = (
        f"Across {len(res.daily)} simulated day(s) the reserve cut the worst hour of "
        f"net load from {res.baseline_peak_mw:,.0f} MW to {res.reserve_peak_mw:,.0f} MW, "
        f"a {reduction * 100:.1f}% reduction in peak severity. "
        f"{n_windows} stress window(s) met the {scenario.severity_percentile:.0%} "
        f"severity threshold over at least {scenario.min_stress_window_days} day(s). "
        f"The reserve ended at {res.final_soc:,.0f} MWh, {position} its protected "
        f"floor of {asset.min_soc_mwh:,.0f} MWh. "
        f"(engine {run.code_version})"
    )
    return payload, annotation


def create_app(repo: Repository | None = None) -> FastAPI:
    repository: Repository = repo or InMemoryRepository()
    app = FastAPI(
        title="Offshore Wind Reserve — Scenario API",
        version="0.1.0",
        summary="Simulate long-duration seafloor reserve dispatch over ISO-NE stress events.",
    )

    def get_repo() -> Repository:
        return repository

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422, content={"detail": _sanitize_non_finite(exc.errors())}
        )

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "code_version": code_version()}

    @app.post("/scenarios", response_model=schemas.ScenarioOut, status_code=201)
    def create_scenario(
        body: schemas.ScenarioCreate, r: Repository = Depends(get_repo)
    ) -> schemas.ScenarioOut:
        rec = r.add_scenario(body)
        return schemas.ScenarioOut(id=rec.id, created_at=rec.created_at, **body.model_dump())

    @app.get("/scenarios/{scenario_id}", response_model=schemas.ScenarioOut)
    def get_scenario(scenario_id: int, r: Repository = Depends(get_repo)) -> schemas.ScenarioOut:
        rec = r.get_scenario(scenario_id)
        if rec is None:
            raise HTTPException(404, "scenario not found")
        return schemas.ScenarioOut(id=rec.id, created_at=rec.created_at, **rec.inputs.model_dump())

    @app.post("/scenarios/{scenario_id}/runs", response_model=schemas.RunOut, status_code=201)
    def create_run(
        scenario_id: int, body: schemas.RunCreate, r: Repository = Depends(get_repo)
    ) -> schemas.RunOut:
        scenario = r.get_scenario(scenario_id)
        if scenario is None:
            raise HTTPException(404, "scenario not found")
        inp = scenario.inputs
        run = r.add_run(scenario_id, code_version())
        try:
            run.status = "running"
            days = _day_profiles(body.days, wind_multiplier=inp.wind_generation_multiplier)
            asset = _asset(inp)
            run.stress_windows = with_peak_hourly_load(
                find_stress_windows(days, inp.severity_percentile, inp.min_stress_window_days),
                days,
            )
            starting_soc = (
                body.starting_soc if body.starting_soc is not None else inp.storage_start_mwh
            )
            run.result = simulate(
                asset,
                days,
                starting_soc=starting_soc,
                available_capacity_mw=inp.available_capacity_mw,
                config=DEFAULT_CONFIG,
                peak_weight=inp.peak_weight,
                smooth_weight=inp.smooth_weight,
            )
            run.status = "succeeded"
            r.save_run(run)
        except ValueError as exc:
            run.status = "failed"
            r.save_run(run)
            raise HTTPException(422, f"simulation rejected inputs: {exc}") from exc
        return schemas.RunOut(
            id=run.id,
            scenario_id=run.scenario_id,
            status=run.status,
            code_version=run.code_version,
            created_at=run.created_at,
        )

    @app.get("/runs/{run_id}", response_model=schemas.RunOut)
    def get_run(run_id: int, r: Repository = Depends(get_repo)) -> schemas.RunOut:
        run = r.get_run(run_id)
        if run is None:
            raise HTTPException(404, "run not found")
        return schemas.RunOut(
            id=run.id,
            scenario_id=run.scenario_id,
            status=run.status,
            code_version=run.code_version,
            created_at=run.created_at,
        )

    @app.get("/runs/{run_id}/stress-windows", response_model=list[schemas.StressWindowOut])
    def get_stress_windows(
        run_id: int, r: Repository = Depends(get_repo)
    ) -> list[schemas.StressWindowOut]:
        run = _require_completed_run(r, run_id)
        return [schemas.StressWindowOut(**_window_json(w)) for w in run.stress_windows]

    @app.get("/runs/{run_id}/results", response_model=schemas.RunResultsOut)
    def get_results(run_id: int, r: Repository = Depends(get_repo)) -> schemas.RunResultsOut:
        run = _require_completed_run(r, run_id)
        res = run.result
        assert res is not None
        return schemas.RunResultsOut(
            run_id=run.id,
            daily=[
                schemas.DailyResultOut(
                    date=d.date,
                    budget=d.budget,
                    priority=d.priority,
                    usable_energy=d.usable_energy,
                    recharge_sufficiency_ratio=d.recharge_sufficiency_ratio,
                    hourly=[schemas.HourlyResultOut(**vars(h)) for h in d.hourly],
                )
                for d in res.daily
            ],
            final_soc=res.final_soc,
            baseline_peak_mw=res.baseline_peak_mw,
            reserve_peak_mw=res.reserve_peak_mw,
            severity_reduction=_severity_reduction(res.baseline_peak_mw, res.reserve_peak_mw),
        )

    @app.post("/runs/{run_id}/decision-package", response_model=schemas.DecisionPackageOut)
    def make_decision_package(
        run_id: int, r: Repository = Depends(get_repo)
    ) -> schemas.DecisionPackageOut:
        run = _require_completed_run(r, run_id)
        scenario = r.get_scenario(run.scenario_id)
        assert scenario is not None
        payload, annotation = _annotation(scenario.inputs, run)
        run.decision_package = {"payload": payload, "annotation": annotation}
        r.save_run(run)
        return schemas.DecisionPackageOut(run_id=run.id, payload=payload, annotation=annotation)

    def _require_completed_run(r: Repository, run_id: int) -> RunRecord:
        run = r.get_run(run_id)
        if run is None:
            raise HTTPException(404, "run not found")
        if run.status != "succeeded" or run.result is None:
            raise HTTPException(409, f"run is {run.status}, results not available")
        return run

    return app


def _default_repo() -> Repository:
    """Pick the store from the environment. psycopg is imported lazily, only when a
    DSN is present, so the default in-memory API needs no database driver."""
    dsn = os.getenv("OWR_DATABASE_URL")
    if dsn:
        from owr.api.pg_store import PostgresRepository

        return PostgresRepository(dsn)
    return InMemoryRepository()


app = create_app(_default_repo())
