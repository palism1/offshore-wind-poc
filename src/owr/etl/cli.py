"""``etl`` command-line entry point (docs/PLAN.md Phase 2 step 3).

Shape: ``etl extract | transform | validate`` so each pipeline step is runnable and
testable independently. Only ``extract`` is implemented in this phase; ``transform``
and ``validate`` are scaffolded as subcommands that report "not implemented yet" so
they slot in later without reshaping the CLI or its argument surface.

The command functions accept injected ``source_factory`` / ``connect`` callables
(defaulting to the real ones) so the wiring is unit-testable with fakes — no
provider, no credentials, no database.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable, Sequence
from datetime import date
from typing import Any

from owr.etl.credentials import MissingCredentialError, redact_secrets
from owr.etl.extract import DATASETS, ExtractResult, Source, extract, source_for
from owr.etl.rows_csv import write_rows_csv


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
    transform_p.set_defaults(func=_not_implemented("transform", "docs/PLAN.md Phase 2 step 2"))

    validate_p = sub.add_parser(
        "validate", help="gap/unit/DST validation gates + report (Phase 2 step 2)"
    )
    validate_p.set_defaults(func=_not_implemented("validate", "docs/PLAN.md Phase 2 step 2"))

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
