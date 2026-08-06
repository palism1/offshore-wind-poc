"""CSV read/write for extracted ``raw.*`` rows (docs/archive/plans/PLAN_EIA_EXTRACTOR.md Phase A3).

Keeps file I/O out of ``extract.py``, which is deliberately I/O-free below the
provider. The banner convention mirrors ``scenario_input.read_day_profiles``:
``#``-prefixed comment lines before the header, carrying enough provenance to
audit the file without a database.
"""

from __future__ import annotations

import csv
import io
import os
import warnings
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import TextIO

import pandas as pd

from owr.etl.credentials import redact_secrets
from owr.etl.extract import RawDataset
from owr.etl.provenance import Provenance


class RowsCsvError(ValueError):
    """Raised for a malformed rows CSV on read."""


def _one_line(value: str) -> str:
    """Collapse a multi-line banner value onto one ``#`` comment line.

    ``read_rows_csv`` keeps a line only when it does not start with ``#``. A value
    that carries a newline puts its tail on an uncommented line, and pandas then
    reads that line as the header. The file becomes unreadable by its own reader.
    Measured 2026-08-05 on ``data/wind_winter_2025_26.csv``, written by
    ``EIAWindSource`` before its ``describe_query`` became single-line.

    ``Provenance.stamp`` already collapses ``source_query``, so a stamped batch
    cannot reach here with a newline. This guard covers a ``Provenance`` built
    directly, which is what the tests do.

    One limit stays, and it predates this change: ``read_rows_csv`` filters
    **physical** lines, so a quoted data cell must not contain a line that is blank
    or starts with ``#``. Collapsing the provenance values removes the only source
    of a newline inside a cell that this repository produces.
    """
    return " ".join(value.splitlines())


def write_rows_csv(
    path: str,
    dataset: RawDataset,
    rows: Sequence[tuple[object, ...]],
    provenance: Provenance,
    *,
    getenv: Callable[[str], str | None] = os.environ.get,
) -> int:
    """Write a provenance-bannered CSV of ``rows``. Returns the row count written."""
    with open(path, "w", newline="") as f:
        f.write(f"# dataset = {dataset.name}\n")
        f.write(f"# table = {dataset.table}\n")
        f.write(f"# source = {provenance.source}\n")
        f.write(f"# retrieved_at = {provenance.retrieved_at.isoformat()}\n")
        f.write(f"# dataset_version = {_one_line(provenance.dataset_version)}\n")
        f.write(
            f"# source_query = "
            f"{_one_line(redact_secrets(provenance.source_query, getenv=getenv))}\n"
        )
        writer = csv.writer(f)
        writer.writerow(dataset.columns)
        for row in rows:
            writer.writerow(["" if v is None else _cell(v) for v in row])
    return len(rows)


def _cell(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def read_rows_csv(stream: TextIO, dataset: RawDataset, *, origin: str) -> pd.DataFrame:
    """Read a rows CSV written by :func:`write_rows_csv` into a string-typed frame.

    Every column is ``object`` dtype holding ``str``; a blank cell reads back as
    ``""``, which is what ``write_rows_csv`` writes for ``None``. No column is
    converted to a number here: the caller owns the unit conversion, and an early
    conversion would turn an empty ``forecast_mw`` cell into ``NaN`` instead of ``""``.

    Two inputs that ``csv.DictReader`` accepted are now rejected, both malformed:
    a data row with more fields than the header, and an unclosed quoted field. See
    docs/archive/plans/PLAN_PANDAS_ADOPTION.md admitted changes A1 and A2.
    """
    filtered = [line for line in stream if line.strip() and not line.lstrip().startswith("#")]
    if not filtered:
        raise RowsCsvError(f"{origin}: no data rows (file is empty or all comments/blank)")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", pd.errors.ParserWarning)
            frame = pd.read_csv(
                io.StringIO("".join(filtered)),
                dtype=str,
                na_filter=False,
                index_col=False,
            )
    except (pd.errors.ParserError, pd.errors.EmptyDataError, pd.errors.ParserWarning) as exc:
        raise RowsCsvError(f"{origin}: cannot parse as CSV: {exc}") from exc
    if tuple(frame.columns) != dataset.columns:
        raise RowsCsvError(
            f"{origin}: header {list(frame.columns)!r} does not match expected columns "
            f"{dataset.columns!r}"
        )
    return frame
