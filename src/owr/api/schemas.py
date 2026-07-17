"""Pydantic request/response models — the integration contract.

These mirror the engine's value objects but stay decoupled from them, so the wire
format (and the OpenAPI docs generated from it) can evolve independently of the
internal dataclasses. Field names track the app.scenario / app.run_result_* tables
in db/migrations/001_init.sql.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

HOURS_PER_DAY = 24


class ScenarioCreate(BaseModel):
    name: str | None = None
    # generic storage asset (pumped-hydro vs battery is a copy decision, not a fork)
    storage_total_mwh: float = Field(gt=0)
    storage_start_mwh: float = Field(ge=0)
    power_output_mw: float = Field(gt=0)
    efficiency: float = Field(default=1.0, gt=0, le=1.0)
    soc_floor_frac: float = Field(default=0.33, ge=0, lt=1.0)
    strategic_reserve_frac: float = Field(default=0.0, ge=0, lt=1.0)
    # event definition
    season: str = "summer"
    date_start: date
    date_end: date
    min_stress_window_days: int = Field(default=2, ge=1)
    severity_percentile: float = Field(default=0.95, ge=0, le=1.0)
    transmission_limit_mw: float | None = None
    available_capacity_mw: float | None = None
    # dispatch emphasis (team design choices, surfaced not hard-coded)
    peak_weight: float = Field(default=0.5, ge=0)
    smooth_weight: float = Field(default=0.5, ge=0)


class ScenarioOut(ScenarioCreate):
    id: int
    created_at: datetime


class DayProfileIn(BaseModel):
    """One day of the input series that ETL (Phase 2) will eventually supply."""

    date: date
    hourly_load_mw: list[float] = Field(min_length=HOURS_PER_DAY, max_length=HOURS_PER_DAY)
    hourly_wind_mw: list[float] | None = None
    demand_percentile: float = 0.0
    wind_forecast_frac: float = 0.0


class RunCreate(BaseModel):
    days: list[DayProfileIn] = Field(min_length=1)
    # defaults to the scenario's storage_start_mwh when omitted
    starting_soc: float | None = None


class RunOut(BaseModel):
    id: int
    scenario_id: int
    status: str
    code_version: str
    created_at: datetime


class StressWindowOut(BaseModel):
    start: date
    end: date
    days: int


class HourlyResultOut(BaseModel):
    ts_hour: int
    soc: float
    charge: float
    discharge: float
    discharge_peak: float
    discharge_smooth: float
    gross_load: float
    net_load: float
    capacity_margin: float | None


class DailyResultOut(BaseModel):
    date: date
    budget: float
    priority: float
    usable_energy: float
    recharge_sufficiency_ratio: float | None
    hourly: list[HourlyResultOut]


class RunResultsOut(BaseModel):
    run_id: int
    daily: list[DailyResultOut]
    final_soc: float
    baseline_peak_mw: float
    reserve_peak_mw: float
    severity_reduction: float


class DecisionPackageOut(BaseModel):
    run_id: int
    payload: dict
    annotation: str
