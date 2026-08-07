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
    # Scales historical wind before the engine sees it (D11, D12; Component 1 User
    # Inputs, sourced default 1.0). Field(ge=0) alone accepts inf, so
    # allow_inf_nan=False is required.
    # OPEN team question (wind_multiplier_range): the source's validation range is
    # "@" and the field is described as whole-number.
    wind_generation_multiplier: float = Field(default=1.0, ge=0, allow_inf_nan=False)
    name: str | None = None
    # generic storage asset (pumped-hydro vs battery is a copy decision, not a fork)
    storage_total_mwh: float = Field(gt=0)
    storage_start_mwh: float = Field(ge=0)
    power_output_mw: float = Field(gt=0)
    # Round trip at the terminals; the engine applies sqrt(efficiency) on each leg.
    # Stays 1.0 on purpose: Week 4B moved Config.default_efficiency to 0.7225, but
    # that change is scoped to config.py. A caller of this API that omits the
    # field still gets the identity value.
    efficiency: float = Field(default=1.0, gt=0, le=1.0)
    # Team decision 2026-07-17: 20% floor + 10% reserve = 30% protected, 70% usable.
    soc_floor_frac: float = Field(default=0.20, ge=0, lt=1.0)
    strategic_reserve_frac: float = Field(default=0.10, ge=0, lt=1.0)
    # event definition
    season: str = "summer"
    date_start: date
    date_end: date
    min_stress_window_days: int = Field(default=2, ge=1)
    # 0.90 is sourced: Architecture 2026-08-05 Component 3, "90th historical daily
    # load percentile". min_stress_window_days is the source's minimum_window, which
    # the source leaves without a value; 2 is a team choice.
    severity_percentile: float = Field(default=0.90, ge=0, le=1.0)
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
    """Component 3 event row. ``first_hour_index`` and ``last_hour_index`` are
    derived from ``days`` on the engine side and are echoed here, never stored.
    The three optional fields are ``None`` when the detection path could not supply
    them. See docs/archive/plans/PLAN_ARCH_0805_SYNC.md decisions D4 to D7.
    """

    start: date
    end: date
    days: int
    first_hour_index: int
    last_hour_index: int
    peak_hourly_load_mw: float | None = None
    threshold_mwh: float | None = None
    severity_percentile: float | None = None


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
