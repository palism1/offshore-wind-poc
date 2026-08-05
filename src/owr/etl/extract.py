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

import math
import os
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol, runtime_checkable

from owr.etl.credentials import EIA_API_KEY_ENV, require_eia_api_key
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
    """One interval system/zone load reading, normalized from a provider payload.

    ``interval_minutes`` is required, not defaulted: energy is
    ``load_mw * interval_minutes / 60``, and a wrong or assumed interval length is a
    silent multiplicative error (e.g. treating 5-minute ISO-NE readings as hourly
    overstates energy 12x). See ``load_observations_from_records`` for how it is
    derived from a provider payload.
    """

    ts: datetime
    zone: str
    load_mw: float
    interval_minutes: float

    def __post_init__(self) -> None:
        if self.interval_minutes <= 0:
            raise ValueError("interval_minutes must be positive")


@dataclass(frozen=True)
class LmpObservation:
    """One hourly locational marginal price reading ($/MWh)."""

    ts: datetime
    zone: str
    lmp: float


@dataclass(frozen=True)
class WindObservation:
    """One hourly realized wind-generation reading (EIA-930, ISO-NE respondent)."""

    ts: datetime
    gen_mw: float
    forecast_mw: float | None = None
    horizon_days: int = 0  # 0 = realized; >0 reserved for forecast rows (see Q6)


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
    return {
        "ts": obs.ts,
        "zone": obs.zone,
        "load_mw": obs.load_mw,
        "interval_minutes": obs.interval_minutes,
    }


def _lmp_values(obs: LmpObservation) -> dict[str, object]:
    return {"ts": obs.ts, "zone": obs.zone, "lmp": obs.lmp}


def _wind_values(obs: WindObservation) -> dict[str, object]:
    return {
        "ts": obs.ts,
        "gen_mw": obs.gen_mw,
        "forecast_mw": obs.forecast_mw,
        "horizon_days": obs.horizon_days,
    }


# name "load" stays the CLI key; the table is raw.system_load (migration 005) —
# the provider's credential-free ISO-NE feed is 5-minute, not hourly, so the
# table is granularity-agnostic and carries interval_minutes on every row.
HOURLY_LOAD = RawDataset(
    name="load",
    table="raw.system_load",
    value_columns=("ts", "zone", "load_mw", "interval_minutes"),
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

HOURLY_WIND = RawDataset(
    name="wind",
    table="raw.hourly_wind",
    value_columns=("ts", "gen_mw", "forecast_mw", "horizon_days"),
    conflict_key=("source", "ts", "horizon_days"),
    to_values=_wind_values,
)

DATASETS: dict[str, RawDataset] = {ds.name: ds for ds in (HOURLY_LOAD, HOURLY_LMP, HOURLY_WIND)}


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
# ``records_from_frame`` and hand the plain dicts to these adapters, so the
# normalization is testable without pandas/gridstatus installed.


def records_from_frame(frame: Any) -> list[dict[str, object]]:
    """Convert a provider ``pandas.DataFrame`` into plain records.

    ``gridstatus`` returns a ``DataFrame``; every adapter below takes plain dicts, so
    the normalization stays testable without a provider installed. This function is
    the single named place that crosses that boundary.

    **No missing-value conversion happens here, on purpose.** ``gridstatus``
    ``_handle_fuel_type_data`` fills an absent fuel column with ``numpy.nan``.
    Mapping ``NaN`` to ``None`` would make ``_first`` treat the column as absent and
    raise ``KeyError`` instead of the ``non-finite wind value at ts=...`` error that
    ``wind_observations_from_records`` raises today. That guard stays live.
    """
    if not hasattr(frame, "to_dict"):
        raise TypeError(f"expected a pandas.DataFrame, got {type(frame).__name__}")
    return frame.to_dict("records")

_TS_KEYS = ("Interval Start", "Time", "ts")
_TS_END_KEYS = ("Interval End",)
_INTERVAL_MINUTES_KEYS = ("interval_minutes",)
_LOAD_KEYS = ("Load", "load", "load_mw", "Native Load")
_LMP_KEYS = ("LMP", "lmp")
_WIND_KEYS = ("Wind", "gen_mw", "MW", "wind_mw")


def _first(record: dict[str, object], keys: tuple[str, ...]) -> object:
    for key in keys:
        if key in record and record[key] is not None:
            return record[key]
    raise KeyError(f"record missing any of {keys}: {sorted(record)}")


def _interval_minutes_for(
    record: dict[str, object], ts: datetime, *, default_interval_minutes: float | None
) -> float:
    """Derive interval_minutes, in order of authority (see LoadObservation docstring).

    1. Interval End - Interval Start, when both are present on the record. Authoritative.
    2. an explicit interval_minutes key on the record.
    3. default_interval_minutes, if the caller supplied one.
    4. otherwise raise -- no silent default. A wrong interval is a multiplicative
       energy error.
    """
    end = record.get("Interval End")
    if end is not None:
        end_dt = _as_datetime(end)
        return (end_dt - ts).total_seconds() / 60.0
    if any(k in record and record[k] is not None for k in _INTERVAL_MINUTES_KEYS):
        return float(_first(record, _INTERVAL_MINUTES_KEYS))  # type: ignore[arg-type]
    if default_interval_minutes is not None:
        return default_interval_minutes
    raise ValueError(
        f"cannot determine interval_minutes for record at ts={ts.isoformat()}: no "
        f"'Interval End', no 'interval_minutes' key, and no default_interval_minutes "
        f"supplied"
    )


def load_observations_from_records(
    records: Iterable[dict[str, object]],
    zone: str,
    *,
    default_interval_minutes: float | None = None,
) -> list[LoadObservation]:
    """Normalize gridstatus load records into ``LoadObservation``s.

    ``interval_minutes`` is derived per record (see ``_interval_minutes_for``), never
    assumed to be hourly.
    """
    observations = []
    for r in records:
        ts = _as_datetime(_first(r, _TS_KEYS))
        observations.append(
            LoadObservation(
                ts=ts,
                zone=zone,
                load_mw=float(_first(r, _LOAD_KEYS)),  # type: ignore[arg-type]
                interval_minutes=_interval_minutes_for(
                    r, ts, default_interval_minutes=default_interval_minutes
                ),
            )
        )
    return observations


def wind_observations_from_records(
    records: Iterable[dict[str, object]], *, horizon_days: int = 0
) -> list[WindObservation]:
    """Normalize gridstatus EIA-930 fuel-type records into ``WindObservation``s.

    Fail-loud on non-finite values: ``_handle_fuel_type_data`` fills absent fuel
    columns with ``np.nan``, and ``float(nan)`` succeeds, so without this guard a
    NaN would land in the database and silently poison any seasonal ratio.
    """
    observations = []
    for r in records:
        ts = _as_datetime(_first(r, _TS_KEYS))
        gen_mw = float(_first(r, _WIND_KEYS))  # type: ignore[arg-type]
        if not math.isfinite(gen_mw):
            raise ValueError(f"non-finite wind value at ts={ts.isoformat()}")
        observations.append(WindObservation(ts=ts, gen_mw=gen_mw, horizon_days=horizon_days))
    return observations


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
    """Live ISO-NE system load via ``gridstatus.ISONE().get_load(...)``.

    Credential-free: this hits the public ``fiveminutesystemload`` CSV feed, at
    5-minute granularity (``Native Load``). The hourly ISO-NE Web Services feed
    (``get_load_hourly``) is still blocked on credentials; when it lands, it can
    write into the same ``raw.system_load`` table with ``interval_minutes = 60``
    (docs/PLAN_EIA_EXTRACTOR.md Phase A4).
    """

    def __init__(self, zone: str = "ISONE") -> None:
        self.zone = zone
        self.source = "gridstatus.isone.load"

    def get_observations(self, start: date, end: date) -> list[object]:  # pragma: no cover
        gs = _import_gridstatus()
        iso = gs.ISONE()
        frame = iso.get_load(start=start.isoformat(), end=end.isoformat())
        records = records_from_frame(frame)
        return list(load_observations_from_records(records, self.zone))

    def describe_query(self, start: date, end: date) -> str:
        return (
            f"gridstatus.ISONE().get_load(start={start.isoformat()}, "
            f"end={end.isoformat()}) [zone={self.zone}]"
        )

    def dataset_version(self) -> str:  # pragma: no cover - needs the library
        return gridstatus_version()


EIA_FUEL_TYPE_DATASET = "electricity/rto/fuel-type-data"
EIA_ISONE_RESPONDENT = "ISNE"  # note: ISNE, not the ISO-NE zone label "ISONE"
EIA_WIND_FUEL_TYPE = "WND"


def _default_eia_client() -> Any:
    """``gridstatus.EIA()`` — reads ``EIA_API_KEY`` from the environment itself, so
    this process never binds the key to a name.

    NEVER call ``.list_routes()``/``.list_facets()`` on the returned client: those
    pass the key as a URL query parameter (``gridstatus/eia.py:84``), so any HTTP
    error from them puts the key in the exception message. Enforced by a test
    canary (``tests/test_etl_eia.py``), not just this comment.
    """
    return _import_gridstatus().EIA()


class EIAWindSource:
    """Live EIA-930 realized wind generation (ISO-NE respondent) via
    ``gridstatus.EIA().get_dataset('electricity/rto/fuel-type-data', ...)``.

    **No key is ever stored on the instance.** ``self._getenv`` is a callable, not
    a mapping; ``vars()`` on this object therefore shows a function object, not a
    credential. This is a plain class, not a ``@dataclass`` — a dataclass would
    auto-generate a ``__repr__`` that prints every field, including any that later
    held a credential.

    **Residual risk, acknowledged rather than designed away.** Two paths could
    still surface the key in a developer's terminal, neither reachable through the
    shipped CLI: (1) enabling urllib3/``http.client`` DEBUG wire logging, which
    prints request headers including ``X-Api-Key`` — nothing in ``owr`` configures
    logging, so this requires a deliberate opt-in; (2) ``pytest -l``, ``--pdb``, or
    IPython ``%debug`` printing frame locals — this method holds no key local by
    design. Operator-side risks, not defects here.
    """

    source = "eia930.isne.wind"

    def __init__(
        self,
        *,
        respondent: str = EIA_ISONE_RESPONDENT,
        fuel_type: str = EIA_WIND_FUEL_TYPE,
        client_factory: Callable[[], Any] = _default_eia_client,
        getenv: Callable[[str], str | None] = os.environ.get,
    ) -> None:
        self.respondent = respondent
        self.fuel_type = fuel_type
        self._client_factory = client_factory
        self._getenv = getenv

    def get_observations(self, start: date, end: date) -> list[object]:
        require_eia_api_key(self._getenv)  # before the client is built (our message first)
        client = self._client_factory()
        frame = client.get_dataset(
            EIA_FUEL_TYPE_DATASET,
            start=start.isoformat(),
            end=end.isoformat(),
            frequency="hourly",
            facets={"respondent": self.respondent, "fueltype": self.fuel_type},
        )
        records = records_from_frame(frame)
        return list(wind_observations_from_records(records))

    def describe_query(self, start: date, end: date) -> str:
        return (
            f"gridstatus.EIA().get_dataset('{EIA_FUEL_TYPE_DATASET}', "
            f"start={start.isoformat()}, end={end.isoformat()}, frequency=hourly, "
            f"facets={{respondent={self.respondent}, fueltype={self.fuel_type}}})\n"
            f"[api key read from ${EIA_API_KEY_ENV}; value not recorded]"
        )

    def dataset_version(self) -> str:  # pragma: no cover - needs the library
        return gridstatus_version()


def source_for(dataset_name: str, *, zone: str = "ISONE") -> Source:
    """Factory: the live provider Source for a dataset name.

    ``load`` is wired to ISO-NE, ``wind`` to EIA-930. ``lmp`` raises a clear
    NotImplementedError — the row/upsert layers already support it; only the
    provider adapter remains, and it needs credentials not yet provisioned.
    """
    if dataset_name == "load":
        return ISONELoadSource(zone=zone)
    if dataset_name == "wind":
        if zone not in ("ISONE", "ISNE"):
            raise ValueError(
                f"the wind dataset is EIA-930 balancing-authority data (respondent "
                f"{EIA_ISONE_RESPONDENT}) and has no load zone; got --zone {zone!r}. "
                f"Omit --zone or pass ISNE."
            )
        return EIAWindSource()
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
    """Summary of one extract call, for the CLI and callers.

    ``rows`` holds every built row (same column order as ``dataset.columns``), so
    callers can serialize the batch (e.g. to CSV, Phase A3) without re-pulling.
    ``rows_built`` stays for compatibility and is always ``len(rows)``.
    """

    dataset: str
    rows_built: int
    rows_written: int
    provenance: Provenance
    dry_run: bool
    rows: tuple[tuple[object, ...], ...] = ()


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
        rows=tuple(rows),
    )
