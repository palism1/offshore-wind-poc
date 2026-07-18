"""Phase 2 step 1 — Extract ISO-NE (and, later, EIA) data into ``raw.*``.

docs/PLAN.md Phase 2: *"Extract via ``gridstatus`` (ISO-NE load/LMP, EIA) into
``raw.*`` immutably; idempotent upserts keyed on (source, ts)."*

The module is deliberately layered so that everything except the provider call is
pure and unit-testable offline:

    provider (gridstatus)                <- lazily imported, needs credentials
        -> records (list[dict])          <- offline boundary starts here
        -> observations (dataclasses)    <- pure adapters, tested with fixtures
        -> rows (tuples, provenance-stamped)
        -> upsert into raw.*             <- idempotent ON CONFLICT, tested via a fake conn

Adding LMP or EIA is a matter of: (1) a ``RawDataset`` describing the target table
and its ``to_values`` mapping — the row-building and upsert layers below are already
dataset-generic — and (2) a provider ``Source`` adapter. ``load`` is wired end to
end; ``lmp`` has its dataset + record adapter registered (and tested) with the live
source left as the documented extension point, since it needs the same credentials
that block ``load``.

Nothing here runs against ISO-NE until ISO-NE Web Services credentials exist. Until
then the layers below the provider are exercised entirely with fixtures.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol, runtime_checkable

from owr.etl.provenance import Provenance

# The four provenance columns every raw.* row carries, in a fixed order appended
# after each dataset's value columns (db/migrations/001_init.sql).
PROVENANCE_COLUMNS: tuple[str, ...] = (
    "source",
    "retrieved_at",
    "source_query",
    "dataset_version",
)


# ---------------------------------------------------------------------------
# Observations — the normalized, provider-agnostic intermediate representation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LoadObservation:
    """One hourly system/zone load reading, normalized from a provider payload."""

    ts: datetime
    zone: str
    load_mw: float


@dataclass(frozen=True)
class LmpObservation:
    """One hourly locational marginal price reading ($/MWh)."""

    ts: datetime
    zone: str
    lmp: float


# ---------------------------------------------------------------------------
# Dataset descriptors — one per raw.* table, drive row-building and upserts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RawDataset:
    """Describes a ``raw.*`` target table for the generic extract machinery.

    name
        Short CLI-facing key, e.g. ``'load'``.
    table
        Fully-qualified table, e.g. ``'raw.hourly_load'``.
    value_columns
        The non-provenance columns, in insert order. Provenance columns are
        appended automatically (see :attr:`columns`).
    conflict_key
        The ON CONFLICT target — the table primary key. Re-running an extract over
        the same window collides on this key and overwrites, giving idempotency.
        Matches the schema's "(source, ts[, zone])" idempotency comment.
    to_values
        Maps one observation to a ``{value_column: value}`` dict. The only
        per-dataset code needed to add a new table.
    """

    name: str
    table: str
    value_columns: tuple[str, ...]
    conflict_key: tuple[str, ...]
    to_values: Any  # Callable[[object], dict[str, object]]; Any to keep it frozen-friendly

    @property
    def columns(self) -> tuple[str, ...]:
        """Full insert column order: value columns then provenance columns."""
        return self.value_columns + PROVENANCE_COLUMNS


def _load_values(obs: LoadObservation) -> dict[str, object]:
    return {"ts": obs.ts, "zone": obs.zone, "load_mw": obs.load_mw}


def _lmp_values(obs: LmpObservation) -> dict[str, object]:
    return {"ts": obs.ts, "zone": obs.zone, "lmp": obs.lmp}


HOURLY_LOAD = RawDataset(
    name="load",
    table="raw.hourly_load",
    value_columns=("ts", "zone", "load_mw"),
    conflict_key=("source", "zone", "ts"),
    to_values=_load_values,
)

HOURLY_LMP = RawDataset(
    name="lmp",
    table="raw.hourly_lmp",
    value_columns=("ts", "zone", "lmp"),
    conflict_key=("source", "zone", "ts"),
    to_values=_lmp_values,
)

DATASETS: dict[str, RawDataset] = {ds.name: ds for ds in (HOURLY_LOAD, HOURLY_LMP)}


# ---------------------------------------------------------------------------
# Row building — pure, provenance-stamped, deterministic column order
# ---------------------------------------------------------------------------


def build_rows(
    dataset: RawDataset,
    observations: Iterable[object],
    provenance: Provenance,
) -> list[tuple[object, ...]]:
    """Turn observations + one batch provenance into insert-ready row tuples.

    Every row is stamped with the *same* provenance record (one audit trail per
    pull) and ordered to match ``dataset.columns`` so the tuples line up with the
    upsert's placeholders.
    """
    prov = provenance.as_columns()
    rows: list[tuple[object, ...]] = []
    for obs in observations:
        values = dataset.to_values(obs)
        if set(values) != set(dataset.value_columns):
            raise ValueError(
                f"{dataset.name}.to_values produced {sorted(values)}, "
                f"expected {sorted(dataset.value_columns)}"
            )
        merged = {**values, **prov}
        rows.append(tuple(merged[col] for col in dataset.columns))
    return rows


def build_upsert_sql(dataset: RawDataset) -> str:
    """Idempotent INSERT ... ON CONFLICT (<pk>) DO UPDATE for a dataset.

    Re-extracting the same (source, zone, ts) overwrites the value + provenance
    columns instead of inserting a duplicate — the "idempotent upsert keyed on
    (source, ts)" requirement (docs/PLAN.md Phase 2 step 1).
    """
    cols = ", ".join(dataset.columns)
    placeholders = ", ".join(["%s"] * len(dataset.columns))
    conflict = ", ".join(dataset.conflict_key)
    updatable = [c for c in dataset.columns if c not in dataset.conflict_key]
    set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in updatable)
    return (
        f"INSERT INTO {dataset.table} ({cols}) VALUES ({placeholders}) "
        f"ON CONFLICT ({conflict}) DO UPDATE SET {set_clause}"
    )


def upsert_rows(conn: Any, dataset: RawDataset, rows: Sequence[tuple[object, ...]]) -> int:
    """Batch-upsert rows through ``conn`` (psycopg-style). Returns rows written.

    Uses one ``executemany`` per batch, mirroring owr.api.pg_store. ``conn`` only
    needs a ``cursor()`` context manager whose cursor has ``executemany`` — which
    keeps this testable with a lightweight fake connection.
    """
    if not rows:
        return 0
    sql = build_upsert_sql(dataset)
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    return len(rows)


# ---------------------------------------------------------------------------
# Record adapters — provider payload rows -> normalized observations (pure)
# ---------------------------------------------------------------------------

# gridstatus returns a pandas DataFrame; the live sources below call
# ``df.to_dict("records")`` and hand the plain dicts to these adapters, so the
# normalization is testable without pandas/gridstatus installed.

_TS_KEYS = ("Interval Start", "Time", "ts")
_LOAD_KEYS = ("Load", "load", "load_mw")
_LMP_KEYS = ("LMP", "lmp")


def _first(record: dict[str, object], keys: tuple[str, ...]) -> object:
    for key in keys:
        if key in record and record[key] is not None:
            return record[key]
    raise KeyError(f"record missing any of {keys}: {sorted(record)}")


def load_observations_from_records(
    records: Iterable[dict[str, object]], zone: str
) -> list[LoadObservation]:
    """Normalize gridstatus load records into ``LoadObservation``s."""
    return [
        LoadObservation(
            ts=_as_datetime(_first(r, _TS_KEYS)),
            zone=zone,
            load_mw=float(_first(r, _LOAD_KEYS)),  # type: ignore[arg-type]
        )
        for r in records
    ]


def lmp_observations_from_records(
    records: Iterable[dict[str, object]], zone: str
) -> list[LmpObservation]:
    """Normalize gridstatus LMP records into ``LmpObservation``s."""
    return [
        LmpObservation(
            ts=_as_datetime(_first(r, _TS_KEYS)),
            zone=zone,
            lmp=float(_first(r, _LMP_KEYS)),  # type: ignore[arg-type]
        )
        for r in records
    ]


def _as_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    # pandas Timestamp and similar expose to_pydatetime(); fall back to that.
    to_py = getattr(value, "to_pydatetime", None)
    if callable(to_py):
        result = to_py()
        if isinstance(result, datetime):
            return result
    raise TypeError(f"cannot interpret {value!r} ({type(value).__name__}) as a datetime")


# ---------------------------------------------------------------------------
# Sources — the provider boundary (lazy gridstatus, needs credentials)
# ---------------------------------------------------------------------------


@runtime_checkable
class Source(Protocol):
    """A provider adapter for one dataset over a date window.

    Implementations are the only network/credential-touching code; everything
    downstream (build_rows, upsert_rows) is pure. Fixture tests substitute a fake
    Source, so the extract pipeline runs with no provider installed.
    """

    #: stable producer id; also the ``source`` component of the idempotency key.
    source: str

    def get_observations(self, start: date, end: date) -> list[object]:
        """Fetch and normalize observations for [start, end)."""
        ...

    def describe_query(self, start: date, end: date) -> str:
        """Exact, reproducible query text for the provenance record."""
        ...

    def dataset_version(self) -> str:
        """Provider/library version string for the provenance record."""
        ...


def _import_gridstatus() -> Any:
    try:
        import gridstatus  # noqa: PLC0415  (lazy: only needed for live pulls)
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(
            "gridstatus is not installed. Install the ETL extra "
            "(`uv sync --extra etl`) to run live extracts. Live ISO-NE ingestion "
            "also requires ISO-NE Web Services credentials, which are not yet "
            "provisioned; the extract skeleton is verified against fixtures only."
        ) from exc
    return gridstatus


def gridstatus_version() -> str:
    """``'gridstatus==<version>'`` captured from the live library at pull time.

    Recorded as ``dataset_version`` provenance so no version literal is ever
    hard-coded (mirrors the repo's no-magic-numbers rule).
    """
    gs = _import_gridstatus()
    version = getattr(gs, "__version__", "unknown")
    return f"gridstatus=={version}"


class ISONELoadSource:
    """Live ISO-NE hourly load via ``gridstatus.ISONE().get_load(...)``.

    Blocked on ISO-NE Web Services credentials. Structured so that once the
    credentials land, ``get_observations`` "just works": it pulls, converts the
    DataFrame to records, and normalizes via the tested pure adapter.
    """

    def __init__(self, zone: str = "ISONE") -> None:
        self.zone = zone
        self.source = "gridstatus.isone.load"

    def get_observations(self, start: date, end: date) -> list[object]:  # pragma: no cover
        gs = _import_gridstatus()
        iso = gs.ISONE()
        frame = iso.get_load(start=start.isoformat(), end=end.isoformat())
        records = frame.to_dict("records")
        return list(load_observations_from_records(records, self.zone))

    def describe_query(self, start: date, end: date) -> str:
        return (
            f"gridstatus.ISONE().get_load(start={start.isoformat()}, "
            f"end={end.isoformat()}) [zone={self.zone}]"
        )

    def dataset_version(self) -> str:  # pragma: no cover - needs the library
        return gridstatus_version()


def source_for(dataset_name: str, *, zone: str = "ISONE") -> Source:
    """Factory: the live provider Source for a dataset name.

    ``load`` is wired to ISO-NE. ``lmp`` (and future EIA datasets) raise a clear
    NotImplementedError — the row/upsert layers already support them; only the
    provider adapter remains, and it needs the same blocked credentials.
    """
    if dataset_name == "load":
        return ISONELoadSource(zone=zone)
    if dataset_name in DATASETS:
        raise NotImplementedError(
            f"a live Source for dataset '{dataset_name}' is not wired yet; the "
            f"row-building and upsert layers already support it — add a Source "
            f"adapter once its provider credentials exist"
        )
    raise KeyError(f"unknown dataset '{dataset_name}'; known: {sorted(DATASETS)}")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExtractResult:
    """Summary of one extract call, for the CLI and callers."""

    dataset: str
    rows_built: int
    rows_written: int
    provenance: Provenance
    dry_run: bool


def extract(
    dataset: RawDataset,
    source: Source,
    start: date,
    end: date,
    *,
    conn: Any | None = None,
    retrieved_at: datetime | None = None,
) -> ExtractResult:
    """Pull, stamp provenance, and idempotently upsert one dataset for a window.

    When ``conn`` is ``None`` this is a dry run: observations are pulled and rows
    are built and stamped (so provenance is inspectable), but nothing is written.
    """
    observations = source.get_observations(start, end)
    provenance = Provenance.stamp(
        source=source.source,
        source_query=source.describe_query(start, end),
        dataset_version=source.dataset_version(),
        retrieved_at=retrieved_at,
    )
    rows = build_rows(dataset, observations, provenance)
    written = upsert_rows(conn, dataset, rows) if conn is not None else 0
    return ExtractResult(
        dataset=dataset.name,
        rows_built=len(rows),
        rows_written=written,
        provenance=provenance,
        dry_run=conn is None,
    )
