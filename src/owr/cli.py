"""``simulate`` command-line entry point.

Runs one scenario end to end over the engine loop::

    stress_finder -> initial_soc -> [ per day: budget -> dispatch -> soc_engine ] -> metrics

and prints the results. This sequences the engine exactly as
``owr.api.app::create_run`` does, with one documented addition: the API never calls
``initial_soc``, and this CLI reaches it through ``--lead-days`` (default 0, which
reproduces the API's behavior exactly).

Errors and warnings go to **stderr**; results go to **stdout**. This diverges from
``owr.etl.cli``, which prints its DSN error to stdout: the ETL CLI has no
machine-readable output mode, while ``--format json`` here would be corrupted by
diagnostics sharing stdout.

Open team question #3 (is charged wind priced at opportunity cost) has no flag here:
the engine models no prices, so there is nothing to parameterize.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from typing import TextIO

from owr import scenario_input
from owr.config import DEFAULT_CONFIG, Config
from owr.initial_soc import charge_from_wind
from owr.metrics import average_recharge_mismatch_mwh as _average_recharge_mismatch_mwh
from owr.metrics import cycle_recharge_mismatch_mwh as _cycle_recharge_mismatch_mwh
from owr.metrics import equivalent_full_cycles as _equivalent_full_cycles
from owr.metrics import recharge_capacity_mismatch_fraction as _recharge_capacity_mismatch_fraction
from owr.metrics import recharge_opportunity_mw as _recharge_opportunity_mw
from owr.models import HOURS_PER_DAY, DayProfile, StorageAsset, StressWindow
from owr.simulator import simulate
from owr.stress_finder import find_stress_windows, with_peak_hourly_load
from owr.version import code_version

# Reporting-only assumption: no engine function takes it, so it is not a Config
# field (see docs/PLAN_SIMULATOR_CLI.md section 4, "Where each default lives").
# OPEN team question (cycles_per_year): identified 2026-07-28 as the variable the
# storage siting trade-off turns on and left unspecified. At ~10 cycles/yr capex
# dominates; at ~200 the efficiency case returns.
DEFAULT_CYCLES_PER_YEAR: float | None = None

_OPEN_QUESTIONS_STATIC = {
    "round_trip_efficiency": {
        "flags": ["--efficiency"],
        "note": (
            "config.py ships 1.0; Report B computed everything at 0.85. At 1.0 the "
            "engine understates required charging energy by 17.6%. The storage "
            "pivot makes efficiency the axis candidate technologies differ on "
            "(StEnSea 0.80, LAES 0.50-0.70, thermal ~0.35). Undecided."
        ),
        "handoff_ref": "docs/HANDOFF.md open question 1",
    },
    "stress_event_definition": {
        "flags": ["--severity-percentile", "--min-stress-window-days"],
        "note": (
            "Rule and percentile are doc-sourced as of the 2026-08-05 "
            "Architecture export, Component 3: 'Determine: 90th historical "
            "daily load percentile. A stress event begins when: daily_load >= "
            "90th percentile for minimum_window consecutive days.' Report B's "
            "12-hour rule is retired. Still open: the threshold value in MWh on "
            "real data. Both published numbers (3,504 and 16,750 MWh) are "
            "hourly-basis and do not carry over to a daily-basis rule, so a "
            "fresh p90 must be computed on daily sums. The source gives "
            "minimum_window no value, so 2 stays a team choice."
        ),
        "handoff_ref": "docs/HANDOFF.md open question 2",
    },
    "stress_window_output_fields": {
        "flags": [],
        "note": (
            "Component 3 names four output fields whose description cell is @: "
            "first_hour_index, last_hour_index, peak_hourly_load (unit 'MW?') "
            "and load_percentile_threshold. Implemented readings: the two hour "
            "indices are event-local and run 0 to 24*days-1, so under the daily "
            "rule they are a pure function of the duration; peak_hourly_load is "
            "the highest single-hour gross load in MW across the window; "
            "load_percentile_threshold travels as both the percentile and the "
            "MWh cut value, because the unit cell and the field name disagree."
        ),
        "handoff_ref": "docs/PLAN_ARCH_0805_SYNC.md decisions D4 to D7",
    },
    "reserve_usage_rules": {
        "flags": ["--soc-floor-frac", "--strategic-reserve-frac"],
        "note": (
            "The 20% floor and 10% strategic reserve are modeled as two fractions "
            "summed into one protected floor. When each may be drawn is open since "
            "2026-07-18."
        ),
        "handoff_ref": "docs/HANDOFF.md open question 4",
    },
    "cycles_per_year": {
        "flags": ["--cycles-per-year"],
        "note": (
            "Identified 2026-07-28 as the variable the storage siting trade-off "
            "turns on and left unspecified. At ~10 cycles/yr capex dominates; at "
            "~200 the efficiency case returns. The engine does not consume it, so "
            "its default is a labeled constant in cli.py rather than a Config field."
        ),
        "handoff_ref": "docs/HANDOFF.md open question 5",
    },
    "recharge_opportunity_definition": {
        "flags": [],
        "note": (
            "Component 5 lists recharge_opportunity | MWh | @. Implemented as "
            "surplus wind in the hour, before the state-of-charge and power "
            "clamps. A forward-looking forecast reading is possible and would "
            "measure forecast error instead."
        ),
        "handoff_ref": "docs/PLAN_METRICS_COMPONENT7.md open questions",
    },
    "recharge_capacity_denominator": {
        "flags": [],
        "note": (
            "The source description cell for maximum_available_capacity is @. "
            "Implemented as total_mwh - min_soc_mwh, the Overview's 70% "
            "Available Charge band. The alternative, full total_mwh, differs by "
            "about 1.43x."
        ),
        "handoff_ref": "docs/PLAN_METRICS_COMPONENT7.md open questions",
    },
}


def _finite_float(value: str) -> float:
    """Argparse type: parse a float and reject non-finite values.

    ``float()`` accepts "nan"/"inf"/"-inf"/"+inf"/"Infinity" without raising, and
    those slip past StorageAsset/Config validation because every comparison against
    NaN is False (verified against source). Reject at the flag boundary.
    """
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not a number: {value!r}") from exc
    if not math.isfinite(parsed):
        raise argparse.ArgumentTypeError(f"must be a finite number, got {value!r}")
    return parsed


def _window_spec(value: str) -> str | int:
    """Argparse type for ``--window``: 'all' or a positive 1-based integer."""
    if value == "all":
        return "all"
    try:
        n = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"--window must be 'all' or a positive integer, got {value!r}"
        ) from exc
    if n < 1:
        raise argparse.ArgumentTypeError(
            f"--window must be 'all' or a positive integer, got {value!r}"
        )
    return n


def build_parser() -> argparse.ArgumentParser:
    cfg = DEFAULT_CONFIG
    parser = argparse.ArgumentParser(
        prog="simulate",
        description=(
            "Run a day-profile scenario end to end over the offshore-wind reserve "
            "engine and print the results."
        ),
    )

    parser.add_argument(
        "--input", required=True, help="day-profile CSV path, or '-' to read stdin"
    )
    parser.add_argument("--name", default=None, help="label echoed in the output")

    parser.add_argument(
        "--storage-mwh",
        type=_finite_float,
        default=None,
        help="storage total energy capacity, MWh (required unless --list-windows)",
    )
    parser.add_argument(
        "--power-mw",
        type=_finite_float,
        default=None,
        help="storage max charge/discharge power, MW (required unless --list-windows)",
    )
    parser.add_argument(
        "--start-soc-mwh",
        type=_finite_float,
        default=None,
        help="starting state of charge, MWh (default: --storage-mwh, i.e. fully charged)",
    )
    parser.add_argument(
        "--efficiency",
        type=_finite_float,
        default=cfg.default_efficiency,
        help=(
            f"round-trip efficiency (default {cfg.default_efficiency}) "
            "[OPEN: round_trip_efficiency]"
        ),
    )
    parser.add_argument(
        "--soc-floor-frac",
        type=_finite_float,
        default=cfg.default_soc_floor_frac,
        help=(
            f"protected floor fraction of total capacity (default {cfg.default_soc_floor_frac}) "
            "[OPEN: reserve_usage_rules]"
        ),
    )
    parser.add_argument(
        "--strategic-reserve-frac",
        type=_finite_float,
        default=cfg.default_strategic_reserve_frac,
        help=(
            f"strategic reserve fraction of total capacity "
            f"(default {cfg.default_strategic_reserve_frac}) [OPEN: reserve_usage_rules]"
        ),
    )

    parser.add_argument(
        "--severity-percentile",
        type=_finite_float,
        default=cfg.default_severity_percentile,
        help=(
            f"stress-day percentile threshold (default {cfg.default_severity_percentile}, "
            "sourced: Architecture 2026-08-05 Component 3) [OPEN: stress_event_definition]"
        ),
    )
    parser.add_argument(
        "--min-stress-window-days",
        type=int,
        default=cfg.default_min_stress_window_days,
        help=(
            f"minimum consecutive stressed days forming an event "
            f"(default {cfg.default_min_stress_window_days}, team choice; the source names "
            "minimum_window and gives no value) [OPEN: stress_event_definition]"
        ),
    )
    parser.add_argument(
        "--window",
        type=_window_spec,
        default="all",
        help="which detected stress window to simulate: 'all' or a 1-based index (default: all)",
    )
    parser.add_argument(
        "--lead-days",
        type=int,
        default=0,
        help="days fed to pre-event wind charging via initial_soc (default: 0)",
    )
    parser.add_argument(
        "--list-windows",
        action="store_true",
        help="detect and print stress windows, then exit without simulating",
    )

    parser.add_argument(
        "--peak-weight",
        type=_finite_float,
        default=cfg.default_peak_weight,
        help=f"peak-shaving dispatch weight (default {cfg.default_peak_weight})",
    )
    parser.add_argument(
        "--smooth-weight",
        type=_finite_float,
        default=cfg.default_smooth_weight,
        help=f"ramp-smoothing dispatch weight (default {cfg.default_smooth_weight})",
    )
    parser.add_argument(
        "--energy-budget-fraction",
        type=_finite_float,
        default=cfg.energy_budget_fraction,
        help=(
            f"max fraction of usable energy committed per day "
            f"(default {cfg.energy_budget_fraction})"
        ),
    )
    parser.add_argument(
        "--priority-demand-weight",
        type=_finite_float,
        default=cfg.priority_demand_weight,
        help=f"demand weight in Priority(d) (default {cfg.priority_demand_weight})",
    )
    parser.add_argument(
        "--priority-wind-weight",
        type=_finite_float,
        default=cfg.priority_wind_weight,
        help=f"wind weight in Priority(d) (default {cfg.priority_wind_weight})",
    )

    parser.add_argument(
        "--available-capacity-mw",
        type=_finite_float,
        default=None,
        help="firm available capacity, MW; unset leaves capacity margin unset",
    )
    parser.add_argument(
        "--cycles-per-year",
        type=_finite_float,
        default=DEFAULT_CYCLES_PER_YEAR,
        help=(
            "assumed annual cycle count, reported only, never fed to the engine "
            "[OPEN: cycles_per_year]"
        ),
    )
    parser.add_argument(
        "--format",
        choices=("table", "json"),
        default="table",
        help="output rendering (default: table)",
    )

    parser.set_defaults(func=cmd_run)
    return parser


def cmd_run(args: argparse.Namespace) -> int:
    try:
        return _run(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _run(args: argparse.Namespace) -> int:
    if args.input == "-":
        day_set = scenario_input.read_day_profiles(sys.stdin, origin="<stdin>")
    else:
        try:
            stream = open(args.input, encoding="utf-8", newline="")
        except OSError as exc:
            raise ValueError(f"cannot open input file: {exc}") from exc
        try:
            day_set = scenario_input.read_day_profiles(stream, origin=args.input)
        finally:
            stream.close()

    for warning in day_set.warnings:
        print(f"warning: {warning}", file=sys.stderr)

    days = day_set.days

    if args.cycles_per_year is not None and args.cycles_per_year <= 0:
        raise ValueError("--cycles-per-year must be positive")

    cfg = Config(
        priority_demand_weight=args.priority_demand_weight,
        priority_wind_weight=args.priority_wind_weight,
        energy_budget_fraction=args.energy_budget_fraction,
        default_efficiency=args.efficiency,
        default_soc_floor_frac=args.soc_floor_frac,
        default_strategic_reserve_frac=args.strategic_reserve_frac,
        default_severity_percentile=args.severity_percentile,
        default_min_stress_window_days=args.min_stress_window_days,
        default_peak_weight=args.peak_weight,
        default_smooth_weight=args.smooth_weight,
    )

    windows = find_stress_windows(days, args.severity_percentile, args.min_stress_window_days)
    windows = with_peak_hourly_load(windows, days)

    if args.list_windows:
        _render_list_windows(day_set, windows, args, sys.stdout)
        return 0

    if args.storage_mwh is None or args.power_mw is None:
        raise ValueError("--storage-mwh and --power-mw are required (or use --list-windows).")

    asset = StorageAsset(
        total_mwh=args.storage_mwh,
        power_mw=args.power_mw,
        efficiency=args.efficiency,
        soc_floor_frac=args.soc_floor_frac,
        strategic_reserve_frac=args.strategic_reserve_frac,
    )

    if args.lead_days < 0:
        raise ValueError("--lead-days must be >= 0")

    shortfall_note: str | None = None
    if args.window == "all":
        if args.lead_days >= len(days):
            raise ValueError(
                f"--lead-days ({args.lead_days}) must be less than the number of "
                f"days in the file ({len(days)})"
            )
        lead = days[: args.lead_days]
        span = days[args.lead_days :]
        window_label: str | int = "all"
    else:
        if not windows:
            raise ValueError(
                "--window requires at least one detected stress window, but none were found"
            )
        n = args.window
        if n > len(windows):
            raise ValueError(f"--window {n} out of range: {len(windows)} window(s) detected")
        selected = windows[n - 1]
        dates = [d.date for d in days]
        w0 = dates.index(selected.start)
        w1 = dates.index(selected.end)
        span = days[w0 : w1 + 1]
        lead_start = max(0, w0 - args.lead_days)
        lead = days[lead_start:w0]
        if len(lead) < args.lead_days:
            shortfall_note = (
                f"only {len(lead)} lead day(s) available before window {n}; "
                f"requested {args.lead_days}"
            )
        window_label = n

    s0 = args.start_soc_mwh if args.start_soc_mwh is not None else asset.total_mwh
    if not 0 <= s0 <= asset.total_mwh:
        raise ValueError(f"--start-soc-mwh must be within [0, {asset.total_mwh}], got {s0}")

    if shortfall_note:
        print(f"warning: {shortfall_note}", file=sys.stderr)

    soc_at_start = charge_from_wind(s0, lead, asset) if lead else s0

    result = simulate(
        asset,
        span,
        starting_soc=soc_at_start,
        available_capacity_mw=args.available_capacity_mw,
        config=cfg,
        peak_weight=args.peak_weight,
        smooth_weight=args.smooth_weight,
    )

    report = _build_report(
        args=args,
        day_set=day_set,
        days=days,
        windows=windows,
        span=span,
        window_label=window_label,
        lead_days_used=len(lead),
        s0=s0,
        soc_at_start=soc_at_start,
        asset=asset,
        cfg=cfg,
        result=result,
    )

    if args.format == "json":
        _render_json(report, sys.stdout)
    else:
        _render_table(report, args, sys.stdout)
    return 0


def _severity_reduction(baseline_peak_mw: float, reserve_peak_mw: float) -> float:
    # Duplicated locally rather than imported from owr.metrics/api.app: same guard
    # as api/app.py::_severity_reduction, kept local so the engine's runtime path
    # stays free of anything from the API layer.
    if baseline_peak_mw <= 0:
        return 0.0
    return (baseline_peak_mw - reserve_peak_mw) / baseline_peak_mw


def _build_report(
    *,
    args: argparse.Namespace,
    day_set: scenario_input.DayProfileSet,
    days: list[DayProfile],
    windows: list,
    span: list[DayProfile],
    window_label: str | int,
    lead_days_used: int,
    s0: float,
    soc_at_start: float,
    asset: StorageAsset,
    cfg: Config,
    result,
) -> dict:
    energy_discharged = sum(h.discharge for d in result.daily for h in d.hourly)
    energy_charged = sum(h.charge for d in result.daily for h in d.hourly)

    # One simulate() call is one span. Under --window N the span is one detected
    # stress window; under --window all it is every file day after the lead days,
    # so this total covers non-stress days too. The key name says "span" for that
    # reason; see docs/PLAN_METRICS_COMPONENT7.md section 5.2.
    opportunity: list[float] = []
    actual: list[float] = []
    for day_profile, day_result in zip(span, result.daily, strict=True):
        wind = list(day_profile.hourly_wind_mw) or [0.0] * HOURS_PER_DAY
        opportunity.extend(
            _recharge_opportunity_mw(
                hourly_wind_mw=wind,
                hourly_load_mw=[h.gross_load for h in day_result.hourly],
                hourly_discharge_mw=[h.discharge for h in day_result.hourly],
            )
        )
        actual.extend(h.charge for h in day_result.hourly)
    span_mismatch = _cycle_recharge_mismatch_mwh(
        recharge_opportunity_mw=opportunity, actual_recharged_mw=actual
    )
    average_mismatch = _average_recharge_mismatch_mwh([span_mismatch])
    if average_mismatch is None:  # unreachable: the list always holds one element
        raise ValueError("average recharge mismatch is undefined for an empty span list")
    max_available = asset.total_mwh - asset.min_soc_mwh
    # Defensive: Config rejects a floor sum of 1.0, so max_available > 0 on every CLI path.
    recharge_capacity_mismatch = (
        _recharge_capacity_mismatch_fraction(
            average_mismatch, maximum_available_capacity_mwh=max_available
        )
        if max_available > 0
        else None
    )

    equivalent_full_cycles = _equivalent_full_cycles(
        energy_discharged, rated_energy_mwh=asset.total_mwh
    )
    window_share = (
        equivalent_full_cycles / args.cycles_per_year if args.cycles_per_year else None
    )

    min_margin = None
    min_margin_at = None
    if args.available_capacity_mw is not None:
        for d in result.daily:
            for h in d.hourly:
                if h.capacity_margin is not None and (
                    min_margin is None or h.capacity_margin < min_margin
                ):
                    min_margin = h.capacity_margin
                    min_margin_at = {"date": d.date.isoformat(), "hour": h.ts_hour}

    daily_out = []
    for d in result.daily:
        discharged = sum(h.discharge for h in d.hourly)
        charged = sum(h.charge for h in d.hourly)
        daily_out.append(
            {
                "date": d.date.isoformat(),
                "priority": d.priority,
                "budget": d.budget,
                "usable_energy": d.usable_energy,
                "recharge_sufficiency_ratio": d.recharge_sufficiency_ratio,
                "discharged_mwh": discharged,
                "charged_mwh": charged,
                "gross_peak_mw": max(h.gross_load for h in d.hourly),
                "net_peak_mw": max(h.net_load for h in d.hourly),
                "hourly": [
                    {
                        "ts_hour": h.ts_hour,
                        "soc": h.soc,
                        "charge": h.charge,
                        "discharge": h.discharge,
                        "discharge_peak": h.discharge_peak,
                        "discharge_smooth": h.discharge_smooth,
                        "gross_load": h.gross_load,
                        "net_load": h.net_load,
                        "capacity_margin": h.capacity_margin,
                    }
                    for h in d.hourly
                ],
            }
        )

    open_questions = [
        {
            "id": "round_trip_efficiency",
            "flags": _OPEN_QUESTIONS_STATIC["round_trip_efficiency"]["flags"],
            "value_used": args.efficiency,
            "note": _OPEN_QUESTIONS_STATIC["round_trip_efficiency"]["note"],
            "handoff_ref": _OPEN_QUESTIONS_STATIC["round_trip_efficiency"]["handoff_ref"],
        },
        {
            "id": "stress_event_definition",
            "flags": _OPEN_QUESTIONS_STATIC["stress_event_definition"]["flags"],
            "value_used": f"{args.severity_percentile} / {args.min_stress_window_days} days",
            "note": _OPEN_QUESTIONS_STATIC["stress_event_definition"]["note"],
            "handoff_ref": _OPEN_QUESTIONS_STATIC["stress_event_definition"]["handoff_ref"],
        },
        {
            "id": "stress_window_output_fields",
            "flags": _OPEN_QUESTIONS_STATIC["stress_window_output_fields"]["flags"],
            "value_used": "hours 0..24*days-1; peak in MW; threshold as percentile and MWh",
            "note": _OPEN_QUESTIONS_STATIC["stress_window_output_fields"]["note"],
            "handoff_ref": _OPEN_QUESTIONS_STATIC["stress_window_output_fields"][
                "handoff_ref"
            ],
        },
        {
            "id": "reserve_usage_rules",
            "flags": _OPEN_QUESTIONS_STATIC["reserve_usage_rules"]["flags"],
            "value_used": f"{args.soc_floor_frac} + {args.strategic_reserve_frac}",
            "note": _OPEN_QUESTIONS_STATIC["reserve_usage_rules"]["note"],
            "handoff_ref": _OPEN_QUESTIONS_STATIC["reserve_usage_rules"]["handoff_ref"],
        },
        {
            "id": "cycles_per_year",
            "flags": _OPEN_QUESTIONS_STATIC["cycles_per_year"]["flags"],
            "value_used": args.cycles_per_year if args.cycles_per_year is not None else "unset",
            "note": _OPEN_QUESTIONS_STATIC["cycles_per_year"]["note"],
            "handoff_ref": _OPEN_QUESTIONS_STATIC["cycles_per_year"]["handoff_ref"],
        },
        {
            "id": "recharge_opportunity_definition",
            "flags": _OPEN_QUESTIONS_STATIC["recharge_opportunity_definition"]["flags"],
            "value_used": "surplus wind after serving net load, before the SoC and power clamps",
            "note": _OPEN_QUESTIONS_STATIC["recharge_opportunity_definition"]["note"],
            "handoff_ref": _OPEN_QUESTIONS_STATIC["recharge_opportunity_definition"][
                "handoff_ref"
            ],
        },
        {
            "id": "recharge_capacity_denominator",
            "flags": _OPEN_QUESTIONS_STATIC["recharge_capacity_denominator"]["flags"],
            "value_used": "total_mwh - min_soc_mwh",
            "note": _OPEN_QUESTIONS_STATIC["recharge_capacity_denominator"]["note"],
            "handoff_ref": _OPEN_QUESTIONS_STATIC["recharge_capacity_denominator"][
                "handoff_ref"
            ],
        },
    ]

    return {
        "code_version": code_version(),
        "generated_at": datetime.now(UTC).isoformat(),
        "input": {
            "path": args.input,
            "days_read": len(days),
            "date_start": days[0].date.isoformat(),
            "date_end": days[-1].date.isoformat(),
            "demand_percentile_source": day_set.demand_percentile_source,
            "wind_forecast_frac_source": day_set.wind_forecast_frac_source,
            "has_wind": day_set.has_wind,
        },
        "asset": {
            "total_mwh": asset.total_mwh,
            "power_mw": asset.power_mw,
            "efficiency": asset.efficiency,
            "soc_floor_frac": asset.soc_floor_frac,
            "strategic_reserve_frac": asset.strategic_reserve_frac,
            "min_soc_mwh": asset.min_soc_mwh,
        },
        "config": asdict(cfg),
        "dispatch": {"peak_weight": args.peak_weight, "smooth_weight": args.smooth_weight},
        "reporting": {"cycles_per_year": args.cycles_per_year},
        "stress_windows": [_window_json(w) for w in windows],
        "simulated": {
            "window": window_label,
            "lead_days_used": lead_days_used,
            "date_start": span[0].date.isoformat(),
            "date_end": span[-1].date.isoformat(),
            "starting_soc_mwh": s0,
            "soc_at_window_start_mwh": soc_at_start,
        },
        "daily": daily_out,
        "summary": {
            "baseline_peak_mw": result.baseline_peak_mw,
            "reserve_peak_mw": result.reserve_peak_mw,
            "severity_reduction": _severity_reduction(
                result.baseline_peak_mw, result.reserve_peak_mw
            ),
            "final_soc": result.final_soc,
            "min_soc_mwh": asset.min_soc_mwh,
            "energy_discharged_mwh": energy_discharged,
            "energy_charged_mwh": energy_charged,
            "equivalent_full_cycles": equivalent_full_cycles,
            "window_share_of_annual_cycles": window_share,
            "min_capacity_margin_mw": min_margin,
            "min_capacity_margin_at": min_margin_at,
            "recharge_opportunity_mwh": sum(opportunity),
            "span_recharge_mismatch_mwh": span_mismatch,
            "recharge_capacity_mismatch_fraction": recharge_capacity_mismatch,
            "maximum_available_capacity_mwh": max_available,
        },
        "open_questions": open_questions,
    }


def _render_json(report: dict, out: TextIO) -> None:
    out.write(json.dumps(report, indent=2))
    out.write("\n")


def _window_json(w: StressWindow) -> dict:
    """One JSON shape for a stress window, shared by the report and by
    ``--list-windows``. Carries the Component 3 output fields; the two hour indices
    are read from ``StressWindow`` properties and are never stored on the object.
    """
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


def _render_list_windows(
    day_set: scenario_input.DayProfileSet, windows: list, args: argparse.Namespace, out: TextIO
) -> None:
    if args.format == "json":
        payload = {
            "code_version": code_version(),
            "generated_at": datetime.now(UTC).isoformat(),
            "input": {
                "path": args.input,
                "days_read": len(day_set.days),
                "date_start": day_set.days[0].date.isoformat(),
                "date_end": day_set.days[-1].date.isoformat(),
            },
            "stress_windows": [_window_json(w) for w in windows],
        }
        out.write(json.dumps(payload, indent=2))
        out.write("\n")
        return

    out.write(
        f"stress windows (severity >= {args.severity_percentile:.3f} percentile, "
        f">= {args.min_stress_window_days} consecutive day(s))   [OPEN: stress_event_definition]\n"
    )
    out.write(
        "  source: Architecture 2026-08-05 Component 3. The percentile is sourced; "
        "the minimum_window value is a team choice.\n"
    )
    out.write(
        "  fields: hour indices are event-local; peak is the highest single hour, MW"
        "   [OPEN: stress_window_output_fields]\n"
    )
    if not windows:
        out.write("  none\n")
    for i, w in enumerate(windows, 1):
        peak = w.peak_hourly_load_mw
        peak_str = f"{peak:,.0f} MW" if peak is not None else "-"
        out.write(
            f"  {i}   {w.start.isoformat()} .. {w.end.isoformat()}   {w.days} days   "
            f"hours {w.first_hour_index}..{w.last_hour_index}   peak {peak_str}\n"
        )


def _render_table(report: dict, args: argparse.Namespace, out: TextIO) -> None:
    inp = report["input"]
    asset = report["asset"]
    cfg = report["config"]
    dispatch = report["dispatch"]
    reporting = report["reporting"]
    simulated = report["simulated"]
    summary = report["summary"]

    name = args.name or "unnamed scenario"
    out.write(f"simulate - {name} (engine {report['code_version']})\n\n")

    out.write("Inputs\n")
    out.write(f"  input                {inp['path']}\n")
    out.write(
        f"  days read            {inp['days_read']}  ({inp['date_start']} .. {inp['date_end']})\n"
    )
    if inp["demand_percentile_source"] == "derived-rank":
        out.write("  demand percentile    derived from series rank (column absent)\n")
    else:
        out.write("  demand percentile    read from file\n")
    if inp["has_wind"]:
        out.write("  wind_mw              present (hourly series, from file)\n")
    else:
        out.write("  wind_mw              absent (column not in file)\n")
    if inp["wind_forecast_frac_source"] == "default-zero":
        out.write("  wind forecast frac   defaulted to 0.000 (column absent)\n")
    else:
        out.write("  wind forecast frac   read from file\n")
    out.write(
        f"  storage              {asset['total_mwh']:,.0f} MWh / {asset['power_mw']:,.0f} MW\n"
    )
    out.write(
        f"  efficiency           {asset['efficiency']:.3f}"
        f"                      [OPEN: round_trip_efficiency]\n"
    )
    floor_frac = asset["soc_floor_frac"] + asset["strategic_reserve_frac"]
    out.write(
        f"  protected floor      {asset['soc_floor_frac']:.3f} + "
        f"{asset['strategic_reserve_frac']:.3f} = {floor_frac:.3f} -> "
        f"{asset['min_soc_mwh']:,.0f} MWh   [OPEN: reserve_usage_rules]\n"
    )
    out.write(f"  energy budget        {cfg['energy_budget_fraction']:.3f} of usable energy\n")
    out.write(
        f"  priority weights     {cfg['priority_demand_weight']:.3f} demand / "
        f"{cfg['priority_wind_weight']:.3f} wind\n"
    )
    out.write(
        f"  dispatch weights     {dispatch['peak_weight']:.3f} peak / "
        f"{dispatch['smooth_weight']:.3f} smooth\n"
    )
    cpy = reporting["cycles_per_year"]
    cpy_str = f"{cpy:.1f}" if cpy is not None else "unset"
    out.write(f"  cycles per year      {cpy_str}                      [OPEN: cycles_per_year]\n")
    out.write("\n")

    out.write("Stress windows                                    [OPEN: stress_event_definition]\n")
    out.write(
        f"  rule: daily energy >= {cfg['default_severity_percentile']:.3f} percentile of the "
        f"series; >= {cfg['default_min_stress_window_days']} consecutive days\n"
    )
    out.write(
        "  source: Architecture 2026-08-05 Component 3. The percentile is sourced; "
        "the minimum_window value is a team choice.\n"
    )
    out.write(
        "  fields: hour indices are event-local; peak is the highest single hour, MW"
        "   [OPEN: stress_window_output_fields]\n"
    )
    for i, w in enumerate(report["stress_windows"], 1):
        peak = w["peak_hourly_load_mw"]
        peak_str = f"{peak:,.0f} MW" if peak is not None else "-"
        out.write(
            f"  {i}   {w['start']} .. {w['end']}   {w['days']} days   "
            f"hours {w['first_hour_index']}..{w['last_hour_index']}   peak {peak_str}\n"
        )
    out.write(
        f"  simulated: window {simulated['window']} "
        f"({simulated['date_start']} .. {simulated['date_end']})   "
        f"lead days: {simulated['lead_days_used']}\n"
    )
    out.write("\n")

    if simulated["lead_days_used"] > 0:
        out.write("Pre-event charging (initial_soc)\n")
        out.write(
            f"  {simulated['starting_soc_mwh']:,.0f} MWh -> "
            f"{simulated['soc_at_window_start_mwh']:,.0f} MWh over "
            f"{simulated['lead_days_used']} lead day(s)\n\n"
        )

    out.write("Daily results\n")
    # Column definitions drive both the header and every data row, so the two
    # can never drift apart regardless of how many digits a value has.
    daily_columns = [
        ("date", 10),
        ("priority", 8),
        ("budget MWh", 12),
        ("usable MWh (eod)", 17),
        ("discharged MWh", 15),
        ("recharge ratio", 15),
        ("gross peak MW", 14),
        ("net peak MW", 12),
    ]
    # The date column is left-aligned and the numeric columns right-aligned, so each
    # header sits over the edge its values align to.
    header_cells = [
        header.ljust(width) if i == 0 else header.rjust(width)
        for i, (header, width) in enumerate(daily_columns)
    ]
    out.write("  " + "   ".join(header_cells).rstrip() + "\n")
    for d in report["daily"]:
        ratio = d["recharge_sufficiency_ratio"]
        ratio_str = f"{ratio:.3f}" if ratio is not None else "-"
        row_values = [
            str(d["date"]).ljust(daily_columns[0][1]),
            f"{d['priority']:.3f}".rjust(daily_columns[1][1]),
            f"{d['budget']:,.0f}".rjust(daily_columns[2][1]),
            f"{d['usable_energy']:,.0f}".rjust(daily_columns[3][1]),
            f"{d['discharged_mwh']:,.0f}".rjust(daily_columns[4][1]),
            ratio_str.rjust(daily_columns[5][1]),
            f"{d['gross_peak_mw']:,.0f}".rjust(daily_columns[6][1]),
            f"{d['net_peak_mw']:,.0f}".rjust(daily_columns[7][1]),
        ]
        out.write("  " + "   ".join(row_values).rstrip() + "\n")
    out.write("\n")

    out.write("Summary\n")
    label_width = max(
        len("baseline peak"),
        len("reserve peak"),
        len("severity reduction"),
        len("final state of charge"),
        len("energy discharged"),
        len("energy charged"),
        len("equivalent full cycles"),
        len("share of assumed annual cycles"),
        len("min capacity margin"),
        len("recharge opportunity"),
        len("span recharge mismatch"),
        len("recharge capacity mismatch"),
    ) + 4
    out.write(f"  {'baseline peak'.ljust(label_width)}{summary['baseline_peak_mw']:,.0f} MW\n")
    out.write(f"  {'reserve peak'.ljust(label_width)}{summary['reserve_peak_mw']:,.0f} MW\n")
    out.write(
        f"  {'severity reduction'.ljust(label_width)}"
        f"{summary['severity_reduction'] * 100:.1f}%\n"
    )
    out.write(
        f"  {'final state of charge'.ljust(label_width)}{summary['final_soc']:,.0f} MWh   "
        f"(protected floor {summary['min_soc_mwh']:,.0f} MWh)\n"
    )
    out.write(
        f"  {'energy discharged'.ljust(label_width)}{summary['energy_discharged_mwh']:,.0f} MWh\n"
    )
    out.write(
        f"  {'energy charged'.ljust(label_width)}{summary['energy_charged_mwh']:,.0f} MWh\n"
    )
    out.write(
        f"  {'equivalent full cycles'.ljust(label_width)}"
        f"{summary['equivalent_full_cycles']:.3f}   (energy discharged / rated capacity)\n"
    )
    if summary["window_share_of_annual_cycles"] is not None:
        out.write(
            f"  {'share of assumed annual cycles'.ljust(label_width)}"
            f"{summary['window_share_of_annual_cycles']:.3f}\n"
        )
    if summary["min_capacity_margin_mw"] is not None:
        at = summary["min_capacity_margin_at"]
        out.write(
            f"  {'min capacity margin'.ljust(label_width)}"
            f"{summary['min_capacity_margin_mw']:,.0f} MW    "
            f"({at['date']} hour {at['hour']})\n"
        )
    out.write(
        f"  {'recharge opportunity'.ljust(label_width)}"
        f"{summary['recharge_opportunity_mwh']:,.0f} MWh   "
        "[OPEN: recharge_opportunity_definition]\n"
    )
    out.write(
        f"  {'span recharge mismatch'.ljust(label_width)}"
        f"{summary['span_recharge_mismatch_mwh']:,.0f} MWh   "
        f"(opportunity - recharged, window {simulated['window']})\n"
    )
    rcm = summary["recharge_capacity_mismatch_fraction"]
    rcm_str = f"{rcm * 100:.1f}%" if rcm is not None else "-"
    out.write(
        f"  {'recharge capacity mismatch'.ljust(label_width)}"
        f"{rcm_str}    (of {summary['maximum_available_capacity_mwh']:,.0f} MWh available) "
        "[OPEN: recharge_capacity_denominator]\n"
    )
    out.write("\n")

    out.write("Open team questions carried by this run\n")
    for oq in report["open_questions"]:
        out.write(f"  {oq['id']}    used {oq['value_used']}  -- {oq['note']}\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
