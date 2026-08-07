"""``sweep`` command-line entry point.

Runs the engine once per storage size on a ladder and prints the resulting curve:
severity reduction and energy discharged against storage size. Implements
docs/archive/plans/PLAN_SCENARIO_SWEEP.md section 4.5.

A second console script rather than a subcommand on ``simulate`` (plan decision
D1): it touches zero lines of ``cli.py`` and keeps the demo path there untouched.

The sweep always simulates every day in the input file; it does no window
selection and no lead-day trimming (plan section 2, out of scope). Every point
starts full: there is no pre-event charging (``owr.sweep`` rule 5).

Error policy, copied from ``owr.cli``: results to stdout, errors and warnings to
stderr, ``cmd_sweep`` catches ``ValueError`` and returns 2.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TextIO

from owr import scenario_input

# _finite_float: one shared parser-boundary rule for non-finite numbers. Both
# owr.cli and owr.sweep_cli are the CLI layer, and a copy would drift (plan
# section 4.5).
from owr.cli import _finite_float
from owr.config import DEFAULT_CONFIG, Config
from owr.models import PowerRule
from owr.sweep import SweepSpec, run_sweep
from owr.sweep_chart import render_sweep_chart
from owr.version import code_version

_OPEN_QUESTIONS_STATIC = {
    "sweep_power_scaling": {
        "flags": ["--power-rule", "--duration-hours"],
        "note": (
            "Fixed power against fixed duration. Both are implemented and "
            "labeled. Fixed is the default because it reproduces the recorded "
            "reference points and adds no physical assumption. The two curves "
            "differ in shape and not only in scale."
        ),
        "handoff_ref": "docs/archive/plans/PLAN_SCENARIO_SWEEP.md section 9",
    },
    "sweep_size_ladder": {
        "flags": ["--sizes-mwh"],
        "note": (
            "The default seven sizes bracket Report A's 40,000 to 60,000 MWh "
            "system reserve target. docs/archive/reviews/FACT_CHECK_REPORT.md records that this "
            "target does not reproduce from Report A's own inputs, so the ladder "
            "moves when that number moves."
        ),
        "handoff_ref": "docs/archive/plans/PLAN_SCENARIO_SWEEP.md section 9",
    },
}


def _size_list(value: str) -> tuple[float, ...]:
    """Argparse type for ``--sizes-mwh``: a comma-separated, strictly-positive,
    duplicate-free MWh ladder. Sorted ascending on return, because the chart x
    axis must rise; documented in the flag help."""
    if not value.strip():
        raise argparse.ArgumentTypeError("--sizes-mwh must not be empty")
    tokens = [t.strip() for t in value.split(",")]
    sizes: list[float] = []
    for token in tokens:
        if not token:
            raise argparse.ArgumentTypeError(f"--sizes-mwh: empty size in {value!r}")
        try:
            parsed = float(token)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"--sizes-mwh: not a number: {token!r}"
            ) from exc
        if not math.isfinite(parsed):
            raise argparse.ArgumentTypeError(
                f"--sizes-mwh: must be a finite number, got {token!r}"
            )
        if parsed <= 0:
            raise argparse.ArgumentTypeError(
                f"--sizes-mwh: must be positive, got {token!r}"
            )
        sizes.append(parsed)
    if len(set(sizes)) != len(sizes):
        raise argparse.ArgumentTypeError(f"--sizes-mwh: duplicate size(s) in {value!r}")
    return tuple(sorted(sizes))


def build_parser() -> argparse.ArgumentParser:
    cfg = DEFAULT_CONFIG
    parser = argparse.ArgumentParser(
        prog="sweep",
        description=(
            "Run the offshore-wind reserve engine once per storage size and "
            "print severity reduction against storage size."
        ),
    )

    parser.add_argument(
        "--input", required=True, help="day-profile CSV path, or '-' to read stdin"
    )
    parser.add_argument(
        "--sizes-mwh",
        dest="sizes_mwh",
        type=_size_list,
        default=cfg.default_sweep_sizes_mwh,
        help=(
            f"comma-separated MWh size ladder, sorted ascending "
            f"(default {', '.join(f'{s:,.0f}' for s in cfg.default_sweep_sizes_mwh)}) "
            "[OPEN: sweep_size_ladder]"
        ),
    )
    parser.add_argument(
        "--power-rule",
        dest="power_rule",
        type=PowerRule,
        choices=list(PowerRule),
        default=cfg.default_sweep_power_rule,
        help=(
            f"how power scales with size (default {cfg.default_sweep_power_rule.value}) "
            "[OPEN: sweep_power_scaling]"
        ),
    )
    parser.add_argument(
        "--power-mw",
        type=_finite_float,
        default=None,
        help="storage power, MW, held constant at every size (required under --power-rule fixed)",
    )
    parser.add_argument(
        "--duration-hours",
        type=_finite_float,
        default=None,
        help=(
            "storage duration, hours, held constant at every size "
            "(required under --power-rule fixed_duration)"
        ),
    )
    parser.add_argument(
        "--efficiency",
        type=_finite_float,
        default=cfg.default_efficiency,
        help=(
            f"round-trip efficiency, applied as sqrt(eff) on each leg "
            f"(default {cfg.default_efficiency}) [OPEN: round_trip_efficiency]"
        ),
    )
    parser.add_argument(
        "--wind-multiplier",
        type=_finite_float,
        default=cfg.default_wind_generation_multiplier,
        help=(
            f"scale historical wind by this factor before the engine sees it "
            f"(default {cfg.default_wind_generation_multiplier}, sourced: Architecture "
            "2026-08-05 Component 1) [OPEN: wind_multiplier_range]. At 1.0 the shipped "
            "profiles still charge 0.0 MWh: ISO-NE system-wide wind almost never "
            "exceeds system load. A multiplier near 5 is what makes surplus wind appear."
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
        "--chart",
        default=None,
        help="write the chart here; the file extension picks PNG or SVG",
    )
    parser.add_argument(
        "--data-out",
        dest="data_out",
        default=None,
        help="write the bannered sweep-result CSV here",
    )
    parser.add_argument(
        "--title", default=None, help="chart title and table heading"
    )
    parser.add_argument(
        "--format",
        choices=("table", "json"),
        default="table",
        help="output rendering (default: table)",
    )

    parser.set_defaults(func=cmd_sweep)
    return parser


def cmd_sweep(args: argparse.Namespace) -> int:
    try:
        return _run(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _run(args: argparse.Namespace) -> int:
    if args.input == "-":
        day_set = scenario_input.load_day_profiles(
            sys.stdin, origin="<stdin>", wind_multiplier=args.wind_multiplier
        )
    else:
        try:
            stream = open(args.input, encoding="utf-8", newline="")
        except OSError as exc:
            raise ValueError(f"cannot open input file: {exc}") from exc
        try:
            day_set = scenario_input.load_day_profiles(
                stream, origin=args.input, wind_multiplier=args.wind_multiplier
            )
        finally:
            stream.close()

    for warning in day_set.warnings:
        print(f"warning: {warning}", file=sys.stderr)

    days = day_set.days

    cfg = Config(
        default_efficiency=args.efficiency,
        default_soc_floor_frac=args.soc_floor_frac,
        default_strategic_reserve_frac=args.strategic_reserve_frac,
        default_peak_weight=args.peak_weight,
        default_smooth_weight=args.smooth_weight,
    )

    spec = SweepSpec(
        sizes_mwh=args.sizes_mwh,
        power_rule=args.power_rule,
        efficiency=args.efficiency,
        soc_floor_frac=args.soc_floor_frac,
        strategic_reserve_frac=args.strategic_reserve_frac,
        power_mw=args.power_mw,
        duration_hours=args.duration_hours,
    )

    result = run_sweep(spec, span_days=days, config=cfg)

    report = _build_report(
        args=args,
        days=days,
        spec=spec,
        cfg=cfg,
        result=result,
        hour_convention=day_set.hour_convention,
        wind_multiplier=day_set.wind_multiplier,
    )

    if args.chart:
        title, subtitle, footer = _chart_text(args=args, days=days, spec=spec, report=report)
        render_sweep_chart(
            result.frame(), path=args.chart, title=title, subtitle=subtitle, footer=footer
        )
        report["chart"] = args.chart

    if args.data_out:
        _write_data_csv(args.data_out, result.frame(), days=days, spec=spec, args=args)

    if args.format == "json":
        _render_json(report, sys.stdout)
    else:
        _render_table(report, args, sys.stdout)
    return 0


def _chart_text(
    *, args: argparse.Namespace, days: list, spec: SweepSpec, report: dict
) -> tuple[str, str, str]:
    title = args.title or "severity reduction vs storage size"
    rule = spec.power_rule.value
    subtitle = (
        f"{args.input}, {len(days)} days {days[0].date.isoformat()} to "
        f"{days[-1].date.isoformat()}, power rule {rule}, "
        f"efficiency {spec.efficiency:.3f}, "
        f"protected floor {spec.soc_floor_frac + spec.strategic_reserve_frac:.3f}"
    )
    first = spec.sizes_mwh[0]
    last = spec.sizes_mwh[-1]
    footer = (
        f"engine {report['code_version']}, generated {report['generated_at']}, "
        f"sizes {first:,.0f} to {last:,.0f} MWh, {len(spec.sizes_mwh)} points. "
        "Team design constants, not verified facts."
    )
    return title, subtitle, footer


def _build_report(
    *,
    args: argparse.Namespace,
    days: list,
    spec: SweepSpec,
    cfg: Config,
    result,
    hour_convention: str,
    wind_multiplier: float,
) -> dict:
    input_block = {
        "path": args.input,
        "days_read": len(days),
        "date_start": days[0].date.isoformat(),
        "date_end": days[-1].date.isoformat(),
        "hour_convention": hour_convention,
        "wind_multiplier": wind_multiplier,
    }
    spec_block = {
        "sizes_mwh": list(spec.sizes_mwh),
        "power_rule": spec.power_rule.value,
        "power_mw": spec.power_mw,
        "duration_hours": spec.duration_hours,
        "efficiency": spec.efficiency,
        "soc_floor_frac": spec.soc_floor_frac,
        "strategic_reserve_frac": spec.strategic_reserve_frac,
    }
    dispatch_block = {
        "peak_weight": cfg.default_peak_weight,
        "smooth_weight": cfg.default_smooth_weight,
    }
    points_block = [
        {
            "storage_mwh": p.storage_mwh,
            "power_mw": p.power_mw,
            "duration_hours": p.duration_hours,
            "severity_reduction": p.severity_reduction,
            "baseline_peak_mw": p.baseline_peak_mw,
            "reserve_peak_mw": p.reserve_peak_mw,
            "energy_discharged_mwh": p.energy_discharged_mwh,
            "energy_charged_mwh": p.energy_charged_mwh,
            "final_soc_mwh": p.final_soc_mwh,
            "equivalent_full_cycles": p.equivalent_full_cycles,
        }
        for p in result.points
    ]
    open_questions = [
        {
            "id": "sweep_power_scaling",
            "flags": _OPEN_QUESTIONS_STATIC["sweep_power_scaling"]["flags"],
            "value_used": spec.power_rule.value,
            "note": _OPEN_QUESTIONS_STATIC["sweep_power_scaling"]["note"],
            "handoff_ref": _OPEN_QUESTIONS_STATIC["sweep_power_scaling"]["handoff_ref"],
        },
        {
            "id": "sweep_size_ladder",
            "flags": _OPEN_QUESTIONS_STATIC["sweep_size_ladder"]["flags"],
            "value_used": f"{spec.sizes_mwh[0]:,.0f} .. {spec.sizes_mwh[-1]:,.0f} MWh",
            "note": _OPEN_QUESTIONS_STATIC["sweep_size_ladder"]["note"],
            "handoff_ref": _OPEN_QUESTIONS_STATIC["sweep_size_ladder"]["handoff_ref"],
        },
    ]

    return {
        "code_version": code_version(),
        "generated_at": datetime.now(UTC).isoformat(),
        "input": input_block,
        "spec": spec_block,
        "dispatch": dispatch_block,
        "points": points_block,
        "chart": None,
        "open_questions": open_questions,
    }


def _write_data_csv(
    path: str, frame, *, days: list, spec: SweepSpec, args: argparse.Namespace
) -> None:
    with open(path, "w", newline="") as f:
        f.write("# generated_by = owr.sweep_cli\n")
        f.write(f"# code_version = {code_version()}\n")
        f.write(f"# generated_at = {datetime.now(UTC).isoformat()}\n")
        f.write(f"# input = {args.input}\n")
        f.write(f"# days = {len(days)}\n")
        f.write(f"# date_start = {days[0].date.isoformat()}\n")
        f.write(f"# date_end = {days[-1].date.isoformat()}\n")
        f.write(f"# power_rule = {spec.power_rule.value}\n")
        if spec.power_rule is PowerRule.FIXED:
            f.write(f"# power_mw = {spec.power_mw}\n")
        else:
            f.write(f"# duration_hours = {spec.duration_hours}\n")
        f.write(f"# efficiency = {spec.efficiency}\n")
        f.write(f"# soc_floor_frac = {spec.soc_floor_frac}\n")
        f.write(f"# strategic_reserve_frac = {spec.strategic_reserve_frac}\n")
        frame.to_csv(f, index=False, lineterminator="\r\n")


def _render_json(report: dict, out: TextIO) -> None:
    out.write(json.dumps(report, indent=2))
    out.write("\n")


def _render_table(report: dict, args: argparse.Namespace, out: TextIO) -> None:
    inp = report["input"]
    spec = report["spec"]

    title = args.title or "severity reduction vs storage size"
    out.write(f"sweep - {title} (engine {report['code_version']})\n\n")

    out.write("Inputs\n")
    out.write(f"  input                {inp['path']}\n")
    out.write(
        f"  days read            {inp['days_read']}  ({inp['date_start']} .. {inp['date_end']})\n"
    )
    out.write(f"  simulated            {inp['days_read']} days, every day in the file\n")
    out.write(f"  hour convention      {inp['hour_convention']}\n")
    if spec["power_rule"] == "fixed":
        rule_str = f"fixed, {spec['power_mw']:,.0f} MW at every size"
    else:
        rule_str = f"fixed_duration, {spec['duration_hours']:.1f} h at every size"
    out.write(f"  power rule           {rule_str}      [OPEN: sweep_power_scaling]\n")
    out.write(
        f"  efficiency           {spec['efficiency']:.3f}"
        "                              [OPEN: round_trip_efficiency]\n"
    )
    floor = spec["soc_floor_frac"] + spec["strategic_reserve_frac"]
    out.write(
        f"  protected floor      {spec['soc_floor_frac']:.3f} + "
        f"{spec['strategic_reserve_frac']:.3f} = {floor:.3f}     [OPEN: reserve_usage_rules]\n"
    )
    sizes = spec["sizes_mwh"]
    out.write(
        f"  sizes                {len(sizes)} points, {sizes[0]:,.0f} .. {sizes[-1]:,.0f} MWh"
        "     [OPEN: sweep_size_ladder]\n"
    )
    out.write("\n")

    out.write("Sweep\n")
    columns = [
        ("storage MWh", 11),
        ("power MW", 9),
        ("duration h", 10),
        ("severity %", 10),
        ("discharged MWh", 15),
        ("charged MWh", 11),
        ("EFC", 6),
    ]
    header_cells = [header.rjust(width) for header, width in columns]
    out.write("  " + "   ".join(header_cells) + "\n")
    for p in report["points"]:
        row_values = [
            f"{p['storage_mwh']:,.0f}".rjust(columns[0][1]),
            f"{p['power_mw']:,.0f}".rjust(columns[1][1]),
            f"{p['duration_hours']:.1f}".rjust(columns[2][1]),
            f"{p['severity_reduction'] * 100:.2f}".rjust(columns[3][1]),
            f"{p['energy_discharged_mwh']:,.0f}".rjust(columns[4][1]),
            f"{p['energy_charged_mwh']:,.0f}".rjust(columns[5][1]),
            f"{p['equivalent_full_cycles']:.3f}".rjust(columns[6][1]),
        ]
        out.write("  " + "   ".join(row_values) + "\n")
    out.write("\n")

    if report["chart"] is not None:
        out.write("Chart\n")
        out.write(f"  wrote {report['chart']}\n\n")

    out.write("Open team questions carried by this run\n")
    for oq in report["open_questions"]:
        out.write(f"  {oq['id']}    used {oq['value_used']}  -- {oq['note']}\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
