"""``etl`` command-line entry point (docs/PLAN.md Phase 2 step 3).

Shape: ``etl extract | transform | validate`` so each pipeline step is runnable and
testable independently. ``extract`` and ``transform`` are implemented; ``validate``
is still scaffolded as a subcommand that reports "not implemented yet" so it slots
in later without reshaping the CLI or its argument surface.

The command functions accept injected callables (``source_factory``/``connect`` for
``extract``, ``open_input`` for ``transform``, defaulting to the real ones) so the
wiring is unit-testable with fakes — no provider, no credentials, no database, and
no real filesystem access required for the CLI logic itself.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta
from typing import Any, TextIO

import pandas as pd

from owr.config import DEFAULT_CONFIG
from owr.etl.credentials import MissingCredentialError, redact_secrets
from owr.etl.daily import IntervalReading, daily_frame, daily_loads_from_readings
from owr.etl.demo_profile import (
    hourly_loads_from_readings,
    percentile_ranks,
    render_day_profile_csv,
)
from owr.etl.extract import DATASETS, ExtractResult, Source, extract, source_for
from owr.etl.rows_csv import read_rows_csv, write_rows_csv
from owr.etl.seasons import Season
from owr.etl.transform import (
    DAILY_FRAME_COLUMNS,
    ThresholdResult,
    add_season_columns,
    compute_threshold,
    find_windows_per_winter,
    winter_labels,
)


def _default_connect(dsn: str) -> Any:
    # Lazy psycopg import so `etl --help`, `transform`, `validate` and dry-run
    # extracts never require the DB driver.
    import psycopg  # noqa: PLC0415

    return psycopg.connect(dsn)


def cmd_extract(
    args: argparse.Namespace,
    *,
    source_factory: Callable[..., Source] = source_for,
    connect: Callable[[str], Any] = _default_connect,
) -> int:
    """Run ``etl extract`` for one dataset over a date window.

    Thin wrapper around ``_run_extract`` whose only job is to keep the EIA API
    key out of any exception that escapes the pull: a missing credential gets our
    own actionable message (exit 2, mirroring the missing-DSN case below); any
    other exception is printed as its type plus a redacted message (exit 1) so a
    genuine bug is still diagnosable without risking a leaked key in the
    traceback. This broad catch is an accepted trade for that guarantee — see
    docs/PLAN_EIA_EXTRACTOR.md Phase A3.
    """
    try:
        return _run_extract(args, source_factory=source_factory, connect=connect)
    except MissingCredentialError as exc:
        print(f"error: {exc}")
        return 2
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {redact_secrets(str(exc))}")
        return 1


def _run_extract(
    args: argparse.Namespace,
    *,
    source_factory: Callable[..., Source],
    connect: Callable[[str], Any],
) -> int:
    dataset = DATASETS[args.dataset]
    source = source_factory(args.dataset, zone=args.zone)
    start, end = args.start, args.end
    out = getattr(args, "out", None)

    if args.dry_run:
        result = extract(dataset, source, start, end, conn=None)
        if out:
            write_rows_csv(out, dataset, result.rows, result.provenance)
        _print_result(result, dry_run=True)
        return 0

    dsn = args.dsn or os.getenv("OWR_DATABASE_URL")
    if not dsn:
        print(
            "error: no database DSN. Pass --dsn or set OWR_DATABASE_URL "
            "(or use --dry-run to skip writing).",
        )
        return 2

    conn = connect(dsn)
    try:
        result = extract(dataset, source, start, end, conn=conn)
        commit = getattr(conn, "commit", None)
        if callable(commit):
            commit()
    finally:
        close = getattr(conn, "close", None)
        if callable(close):
            close()
    if out:
        write_rows_csv(out, dataset, result.rows, result.provenance)
    _print_result(result, dry_run=False)
    return 0


def _print_result(result: ExtractResult, *, dry_run: bool) -> None:
    verb = "would write" if dry_run else "wrote"
    prov = result.provenance
    print(f"etl extract [{result.dataset}]: {verb} {result.rows_built} rows")
    print(f"  source          = {prov.source}")
    print(f"  retrieved_at    = {prov.retrieved_at.isoformat()}")
    print(f"  source_query    = {redact_secrets(prov.source_query)}")
    print(f"  dataset_version = {prov.dataset_version}")


def cmd_transform(
    args: argparse.Namespace,
    *,
    open_input: Callable[[str], TextIO] = open,
) -> int:
    """Run ``etl transform``: rows CSV(s) -> daily rollup -> percentile -> stress windows.

    Mirrors ``cmd_extract``'s injectable-callable shape (``open_input`` plays the role
    ``source_factory``/``connect`` play there): the input-parsing and computation logic
    is unit-testable with an in-memory fake, no real filesystem access required.

    A missing file, a header that doesn't match the ``load`` dataset, a naive
    timestamp, or a season with no complete days are all usage errors (exit 2), not
    tracebacks — the last of those is ``compute_threshold`` raising ``ValueError``,
    caught here alongside the others.
    """
    try:
        return _run_transform(args, open_input=open_input)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}")
        return 2


def _run_transform(
    args: argparse.Namespace,
    *,
    open_input: Callable[[str], TextIO],
) -> int:
    dataset = DATASETS["load"]
    readings: list[IntervalReading] = []
    for path in args.inputs:
        with open_input(path) as stream:
            frame = read_rows_csv(stream, dataset, origin=path)
        if frame.empty:
            print(f"etl transform: {path}: 0 data rows, skipping", file=sys.stderr)
            continue
        for record in frame.to_dict("records"):
            readings.append(_reading_from_row(record, path))

    daily = daily_loads_from_readings(readings)
    frame = add_season_columns(daily_frame(daily))
    season = Season(args.season)
    threshold = compute_threshold(frame, percentile=args.percentile, season=season)
    events: pd.DataFrame | None
    labels: tuple[str, ...]
    if season == Season.WINTER:
        events = find_windows_per_winter(
            frame, threshold_mwh=threshold.threshold_mwh, min_window_days=args.min_window_days
        )
        labels = winter_labels(frame)
    else:
        # Window detection groups by winter_label and is winter-only by
        # construction (owr.etl.transform.find_windows_per_winter). Calling it
        # here would silently report winter date ranges cut against a
        # non-winter threshold, so we skip it and say so explicitly instead.
        events = None
        labels = ()

    if args.out:
        _write_daily_csv(args.out, frame)

    if args.format == "json":
        print(json.dumps(_transform_result_json(threshold, events, labels), indent=2))
    else:
        _print_transform_text(threshold, events)
    return 0


def cmd_demo_profile(
    args: argparse.Namespace,
    *,
    open_input: Callable[[str], TextIO] = open,
) -> int:
    """Run ``etl demo-profile``: rows CSV(s) -> real day-profile CSV bridge.

    Disposable bridge (docs/PLAN_REAL_DEMO_BRIDGE.md): reads real interval
    readings and writes the ``date,hour,load_mw,demand_percentile`` format
    ``owr.scenario_input`` reads for the ``simulate`` CLI. Superseded by
    ``docs/PLAN_SCENARIO_PROFILE_FORMAT.md`` when that format lands.

    Mirrors ``cmd_transform``'s injectable-callable shape and error handling: a
    missing file, a header mismatch, a naive timestamp, an empty season
    population, a selected date outside the population, or ``--start`` after
    ``--end`` are all usage errors (exit 2, ``error: ...`` on stdout), not
    tracebacks.
    """
    try:
        return _run_demo_profile(args, open_input=open_input)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}")
        return 2


def _run_demo_profile(
    args: argparse.Namespace,
    *,
    open_input: Callable[[str], TextIO],
) -> int:
    if args.start > args.end:
        raise ValueError(f"--start {args.start.isoformat()} is after --end {args.end.isoformat()}")

    dataset = DATASETS["load"]
    readings: list[IntervalReading] = []
    provenance_tuples: set[tuple[str, str, str, str]] = set()
    for path in args.inputs:
        with open_input(path) as stream:
            text = stream.read()
        frame = read_rows_csv(io.StringIO(text), dataset, origin=path)
        if frame.empty:
            print(f"etl demo-profile: {path}: 0 data rows, skipping", file=sys.stderr)
            continue
        for record in frame.to_dict("records"):
            readings.append(_reading_from_row(record, path))
        provenance = _read_provenance_banner(text.splitlines())
        provenance_tuples.add(
            (
                provenance.get("source", ""),
                provenance.get("dataset_version", ""),
                provenance.get("source_query", ""),
                provenance.get("retrieved_at", ""),
            )
        )

    if not readings:
        raise ValueError("no data rows in any --input file")

    daily = daily_loads_from_readings(readings)
    season = Season(args.season)
    frame = add_season_columns(daily_frame(daily))
    population = frame[(frame["season"] == season.value) & frame["complete"]]
    if population.empty:
        raise ValueError(f"no complete {season.value} days in the input population")

    population_by_date: dict[date, float] = dict(
        zip(population["date"], population["load_mwh"], strict=True)
    )

    selected_dates = _date_range(args.start, args.end)
    for d in selected_dates:
        if d not in population_by_date:
            raise ValueError(
                f"{d.isoformat()}: not a complete {season.value} day in the input "
                f"population (the population is the pooled complete {season.value} "
                f"days across every --input, before --start/--end are applied)"
            )

    day_totals = {d: population_by_date[d] for d in selected_dates}
    demand_percentile = percentile_ranks(list(population["load_mwh"]), day_totals)

    hourly_all = hourly_loads_from_readings(readings)
    hourly = [h for h in hourly_all if args.start <= h.date <= args.end]

    banner = _demo_profile_banner(
        args,
        season=season,
        population_days=int(len(population.index)),
        provenance_tuples=sorted(provenance_tuples),
    )
    text = render_day_profile_csv(hourly, demand_percentile=demand_percentile, banner=banner)

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        f.write(text)

    print(f"etl demo-profile: wrote {args.out}")
    print(
        f"  days            = {len(selected_dates)} "
        f"({args.start.isoformat()} -> {args.end.isoformat()})"
    )
    print(f"  season          = {season.value}")
    print(f"  population_days = {int(len(population.index))}")
    print(f"  provenance      = {len(provenance_tuples)} source pair(s)")
    return 0


_PROVENANCE_BANNER_KEYS = ("source", "retrieved_at", "source_query", "dataset_version")


def _read_provenance_banner(lines: list[str]) -> dict[str, str]:
    """Parse the ``# key = value`` provenance lines ``write_rows_csv`` writes.

    Provenance is stamped once per input file, in its comment banner, not
    repeated on every data row (``owr.etl.rows_csv.write_rows_csv``). Splits on
    ``" = "`` rather than bare ``"="`` so a ``dataset_version`` value like
    ``"gridstatus==0.36.0"`` is not mistaken for a second separator.
    """
    values: dict[str, str] = {}
    for line in lines:
        if not line.startswith("#"):
            continue
        key, sep, value = line[1:].strip().partition(" = ")
        if sep and key in _PROVENANCE_BANNER_KEYS:
            values[key] = value.strip()
    return values


def _date_range(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def _demo_profile_banner(
    args: argparse.Namespace,
    *,
    season: Season,
    population_days: int,
    provenance_tuples: list[tuple[str, str, str, str]],
) -> list[str]:
    inputs_str = " ".join(f"--input {path}" for path in args.inputs)
    lines = [
        "Real ISO-NE day-profile input for the simulator CLI. Generated, do not hand-edit.",
        "Superseded by docs/PLAN_SCENARIO_PROFILE_FORMAT.md when that format lands.",
        f"Generated by: etl demo-profile {inputs_str} --start {args.start.isoformat()} "
        f"--end {args.end.isoformat()} --out {args.out}",
        "REAL  load_mw: ISO-NE system load, five-minute feed, integrated to hourly energy",
        "      over America/New_York wall-clock hours. No interpolation, no scaling.",
        "REAL  demand_percentile: empirical rank of the day total against the pooled",
        f"      complete {season.value} days in the inputs, N = {population_days}: "
        "count(load_mwh <= x) / N.",
        "      The per-season population choice is an open question (docs/HANDOFF.md).",
        "ABSENT wind_mw: no real ISO-NE or EIA wind series exists in this repository. The",
        "      EIA extractor has never run. No wind column is emitted and none is shaped.",
        "      The engine therefore models zero recharge across this window.",
        "NOTE  simulate recomputes its own percentile from this file alone. At the default",
        "      --severity-percentile 0.90 it reports no window inside a short file. Pass",
        "      --severity-percentile 0 to see the whole file as the one event.",
    ]
    for source, dataset_version, source_query, retrieved_at in provenance_tuples:
        lines.append(
            f"source = {source}  dataset_version = {dataset_version}  "
            f"retrieved_at = {retrieved_at}"
        )
        lines.append(f"source_query = {source_query}")
    return lines


def _reading_from_row(row: dict[str, str], origin: str) -> IntervalReading:
    ts_str = row["ts"]
    ts = datetime.fromisoformat(ts_str)
    if ts.tzinfo is None:
        raise ValueError(
            f"{origin}: naive timestamp {ts_str!r} (row 'ts' must carry a UTC offset)"
        )
    return IntervalReading(
        ts=ts,
        load_mw=float(row["load_mw"]),
        interval_hours=float(row["interval_minutes"]) / 60.0,
    )


def _write_daily_csv(path: str, frame: pd.DataFrame) -> None:
    ordered = frame.sort_values("date")[list(DAILY_FRAME_COLUMNS)]
    ordered.to_csv(path, index=False, lineterminator="\r\n")


def _print_transform_text(
    threshold: ThresholdResult, events: pd.DataFrame | None
) -> None:
    print(f"etl transform: percentile={threshold.percentile}")
    print(f"  threshold_mwh   = {threshold.threshold_mwh:.3f}")
    print(f"  season          = {threshold.season.value}")
    print(f"  population_days = {threshold.population_days}")
    print(
        f"  min/median/max  = {threshold.min_mwh:.3f} / {threshold.median_mwh:.3f} "
        f"/ {threshold.max_mwh:.3f}"
    )

    excluded = threshold.excluded_incomplete
    if not excluded:
        print("  excluded_incomplete = 0")
    elif len(excluded) <= 10:
        listed = ", ".join(d.isoformat() for d in excluded)
        print(f"  excluded_incomplete = {len(excluded)} [{listed}]")
    else:
        print(
            f"  excluded_incomplete = {len(excluded)} "
            f"(first={excluded[0].isoformat()}, last={excluded[-1].isoformat()})"
        )

    if events is None:
        print("  stress windows: not computed (window detection is winter-only)")
        return

    print("  stress windows:")
    for row in events.itertuples():
        print(
            f"    {row.winter_label}: {row.event_start_date.isoformat()} -> "
            f"{row.event_end_date.isoformat()} ({row.event_duration_days} days)"
        )
    if len(events.index) == 0:
        print("    (none)")


def _transform_result_json(
    threshold: ThresholdResult, events: pd.DataFrame | None, labels: tuple[str, ...]
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "percentile": threshold.percentile,
        "threshold_mwh": threshold.threshold_mwh,
        "season": threshold.season.value,
        "population_days": threshold.population_days,
        "min_mwh": threshold.min_mwh,
        "median_mwh": threshold.median_mwh,
        "max_mwh": threshold.max_mwh,
        "excluded_incomplete": [d.isoformat() for d in threshold.excluded_incomplete],
    }
    if events is None:
        result["windows"] = None
        result["stress_windows_note"] = "window detection is winter-only; not computed"
    else:
        result["windows"] = {
            label: [
                {"start": row.event_start_date.isoformat(),
                 "end": row.event_end_date.isoformat(),
                 "days": int(row.event_duration_days)}
                for row in events[events["winter_label"] == label].itertuples()
            ]
            for label in labels
        }
    return result


def _not_implemented(step: str, plan_ref: str) -> Callable[[argparse.Namespace], int]:
    def run(_args: argparse.Namespace) -> int:
        print(f"etl {step}: not implemented yet ({plan_ref}).")
        return 1

    return run


def _date(value: str) -> date:
    return date.fromisoformat(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="etl", description="Offshore Wind Reserve ETL pipeline.")
    sub = parser.add_subparsers(dest="command", required=True)

    extract_p = sub.add_parser("extract", help="pull provider data into raw.* (Phase 2 step 1)")
    extract_p.add_argument(
        "--dataset",
        choices=sorted(DATASETS),
        default="load",
        help="which raw.* dataset to extract (default: load)",
    )
    extract_p.add_argument("--start", type=_date, required=True, help="window start (YYYY-MM-DD)")
    extract_p.add_argument("--end", type=_date, required=True, help="window end (YYYY-MM-DD)")
    extract_p.add_argument("--zone", default="ISONE", help="load/price zone (default: ISONE)")
    extract_p.add_argument(
        "--dsn", default=None, help="Postgres DSN (default: $OWR_DATABASE_URL)"
    )
    extract_p.add_argument(
        "--dry-run",
        action="store_true",
        help="pull and stamp provenance but do not write to the database",
    )
    extract_p.add_argument(
        "--out",
        default=None,
        metavar="PATH",
        help="also write the stamped rows to this CSV (same column order as the "
        "database insert). Independent of --dry-run; you still need either "
        "--dry-run or a DSN.",
    )
    extract_p.set_defaults(func=cmd_extract)

    transform_p = sub.add_parser(
        "transform", help="hourly->daily, season tagging, percentiles (Phase 2 step 2)"
    )
    transform_p.add_argument(
        "--input",
        action="append",
        required=True,
        dest="inputs",
        metavar="PATH",
        help="a rows CSV written by `etl extract --out` (repeatable; all inputs are "
        "pooled before the daily rollup)",
    )
    transform_p.add_argument(
        "--percentile",
        type=float,
        default=DEFAULT_CONFIG.default_severity_percentile,
        help="severity percentile in [0, 1] "
        f"(default: {DEFAULT_CONFIG.default_severity_percentile})",
    )
    transform_p.add_argument(
        "--season",
        choices=[s.value for s in Season],
        default=Season.WINTER.value,
        help="season to threshold on (default: winter). Stress-window detection "
        "is winter-only: a non-winter season reports the threshold but not "
        "windows.",
    )
    transform_p.add_argument(
        "--min-window-days",
        type=int,
        default=DEFAULT_CONFIG.default_min_stress_window_days,
        dest="min_window_days",
        help="minimum consecutive stressed days to count as a window "
        f"(default: {DEFAULT_CONFIG.default_min_stress_window_days})",
    )
    transform_p.add_argument(
        "--out",
        default=None,
        metavar="PATH",
        help="also write the per-day rollup (date, load_mwh, hours_covered, "
        "expected_hours, intervals, complete, season, winter_label) to this CSV",
    )
    transform_p.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="stdout format (default: text)",
    )
    transform_p.set_defaults(func=cmd_transform)

    validate_p = sub.add_parser(
        "validate", help="gap/unit/DST validation gates + report (Phase 2 step 2)"
    )
    validate_p.set_defaults(func=_not_implemented("validate", "docs/PLAN.md Phase 2 step 2"))

    demo_profile_p = sub.add_parser(
        "demo-profile",
        help="bridge: real interval readings -> day-profile CSV for `simulate` "
        "(docs/PLAN_REAL_DEMO_BRIDGE.md). Superseded by "
        "docs/PLAN_SCENARIO_PROFILE_FORMAT.md when that format lands.",
    )
    demo_profile_p.add_argument(
        "--input",
        action="append",
        required=True,
        dest="inputs",
        metavar="PATH",
        help="a rows CSV written by `etl extract --out` (repeatable; all inputs are "
        "pooled before the rollup)",
    )
    demo_profile_p.add_argument(
        "--start",
        type=_date,
        required=True,
        help="first local calendar date, inclusive (YYYY-MM-DD). Run `etl transform` "
        "first; it reports the event's dates.",
    )
    demo_profile_p.add_argument(
        "--end",
        type=_date,
        required=True,
        help="last local calendar date, inclusive (YYYY-MM-DD)",
    )
    demo_profile_p.add_argument(
        "--out",
        required=True,
        metavar="PATH",
        help="where to write the day-profile CSV",
    )
    demo_profile_p.add_argument(
        "--season",
        choices=[s.value for s in Season],
        default=Season.WINTER.value,
        help="season population for demand_percentile (default: winter)",
    )
    demo_profile_p.set_defaults(func=cmd_demo_profile)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
