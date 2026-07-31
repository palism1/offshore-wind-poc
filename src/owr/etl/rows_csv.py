"""CSV read/write for extracted ``raw.*`` rows (docs/PLAN_EIA_EXTRACTOR.md Phase A3).

Keeps file I/O out of ``extract.py``, which is deliberately I/O-free below the
provider. The banner convention mirrors ``scenario_input.read_day_profiles``:
``#``-prefixed comment lines before the header, carrying enough provenance to
audit the file without a database.
"""

from __future__ import annotations

import csv
import os
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import TextIO

from owr.etl.credentials import redact_secrets
from owr.etl.extract import RawDataset
from owr.etl.provenance import Provenance


class RowsCsvError(ValueError):
    """Raised for a malformed rows CSV on read."""


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
        f.write(f"# dataset_version = {provenance.dataset_version}\n")
        f.write(f"# source_query = {redact_secrets(provenance.source_query, getenv=getenv)}\n")
        writer = csv.writer(f)
        writer.writerow(dataset.columns)
        for row in rows:
            writer.writerow(["" if v is None else _cell(v) for v in row])
    return len(rows)


def _cell(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def read_rows_csv(stream: TextIO, dataset: RawDataset, *, origin: str) -> list[dict[str, str]]:
    """Read a rows CSV written by :func:`write_rows_csv` back into plain dicts.

    Filters ``#`` and blank lines before handing the rest to ``csv.DictReader``,
    mirroring ``scenario_input.read_day_profiles``. Raises :class:`RowsCsvError` if
    the header does not match ``dataset.columns``.
    """
    filtered = [line for line in stream if line.strip() and not line.lstrip().startswith("#")]
    if not filtered:
        raise RowsCsvError(f"{origin}: no data rows (file is empty or all comments/blank)")
    reader = csv.DictReader(filtered)
    if reader.fieldnames is None or tuple(reader.fieldnames) != dataset.columns:
        raise RowsCsvError(
            f"{origin}: header {reader.fieldnames!r} does not match expected columns "
            f"{dataset.columns!r}"
        )
    return list(reader)
