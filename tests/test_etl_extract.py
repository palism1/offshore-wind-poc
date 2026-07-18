"""Tests for the Phase 2 ETL extract skeleton (docs/PLAN.md Phase 2 step 1).

Everything here runs offline with fixtures/mocks: no gridstatus, no pandas, no
network, no credentials, no live database. The provider boundary is a fake
``Source``; the database is a fake connection that records ``executemany`` calls.
What is under test is exactly the plan's three requirements — transform-to-rows,
idempotent upsert keying, and provenance stamping — plus the CLI wiring.
"""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime

import pytest

from owr.etl import cli
from owr.etl.extract import (
    DATASETS,
    HOURLY_LMP,
    HOURLY_LOAD,
    ISONELoadSource,
    LmpObservation,
    LoadObservation,
    build_rows,
    build_upsert_sql,
    extract,
    lmp_observations_from_records,
    load_observations_from_records,
    source_for,
    upsert_rows,
)
from owr.etl.provenance import Provenance

# --------------------------------------------------------------------------- #
# Fakes                                                                        #
# --------------------------------------------------------------------------- #


class FakeCursor:
    def __init__(self) -> None:
        self.executemany_calls: list[tuple[str, list]] = []

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def executemany(self, sql: str, rows: list) -> None:
        self.executemany_calls.append((sql, list(rows)))


class FakeConn:
    def __init__(self) -> None:
        self.cursors: list[FakeCursor] = []
        self.committed = False
        self.closed = False

    def cursor(self) -> FakeCursor:
        cur = FakeCursor()
        self.cursors.append(cur)
        return cur

    def commit(self) -> None:
        self.committed = True

    def close(self) -> None:
        self.closed = True


class FakeLoadSource:
    """A stand-in for ISONELoadSource with deterministic, offline observations."""

    source = "fake.isone.load"

    def __init__(self, observations: list[LoadObservation]) -> None:
        self._observations = observations
        self.calls: list[tuple[date, date]] = []

    def get_observations(self, start: date, end: date) -> list[object]:
        self.calls.append((start, end))
        return list(self._observations)

    def describe_query(self, start: date, end: date) -> str:
        return f"fake.get_load({start.isoformat()}..{end.isoformat()})"

    def dataset_version(self) -> str:
        return "gridstatus==0.30.0-fake"


def _obs() -> list[LoadObservation]:
    return [
        LoadObservation(ts=datetime(2026, 1, 10, 0, tzinfo=UTC), zone="ISONE", load_mw=8000.0),
        LoadObservation(ts=datetime(2026, 1, 10, 1, tzinfo=UTC), zone="ISONE", load_mw=7900.0),
    ]


def _prov() -> Provenance:
    return Provenance.stamp(
        source="fake.isone.load",
        source_query="fake.get_load(2026-01-10..2026-01-11)",
        dataset_version="gridstatus==0.30.0-fake",
        retrieved_at=datetime(2026, 1, 11, 12, 0, tzinfo=UTC),
    )


# --------------------------------------------------------------------------- #
# Provenance                                                                   #
# --------------------------------------------------------------------------- #


def test_provenance_stamp_defaults_retrieved_at_to_now_utc():
    before = datetime.now(UTC)
    prov = Provenance.stamp("s", "q", "v")
    assert prov.retrieved_at.tzinfo is not None
    assert prov.retrieved_at >= before


def test_provenance_requires_all_fields_and_tzaware_time():
    with pytest.raises(ValueError):
        Provenance("", "q", "v", datetime.now(UTC))
    with pytest.raises(ValueError):
        Provenance("s", "q", "v", datetime(2026, 1, 1))  # naive


def test_provenance_as_columns_has_the_four_schema_columns():
    cols = _prov().as_columns()
    assert set(cols) == {"source", "retrieved_at", "source_query", "dataset_version"}


# --------------------------------------------------------------------------- #
# Row building — provenance stamped on every row, correct column order         #
# --------------------------------------------------------------------------- #


def test_build_rows_stamps_provenance_on_every_row():
    prov = _prov()
    rows = build_rows(HOURLY_LOAD, _obs(), prov)
    assert len(rows) == 2
    # columns: ts, zone, load_mw, source, retrieved_at, source_query, dataset_version
    for row, obs in zip(rows, _obs(), strict=True):
        assert row == (
            obs.ts,
            "ISONE",
            obs.load_mw,
            prov.source,
            prov.retrieved_at,
            prov.source_query,
            prov.dataset_version,
        )


def test_build_rows_uses_dataset_column_order():
    rows = build_rows(HOURLY_LOAD, _obs()[:1], _prov())
    # tuple positions must line up with HOURLY_LOAD.columns for the upsert placeholders
    assert dict(zip(HOURLY_LOAD.columns, rows[0], strict=True))["load_mw"] == 8000.0


def test_build_rows_rejects_bad_to_values_mapping():
    bad = HOURLY_LOAD.__class__(
        name="bad",
        table="raw.bad",
        value_columns=("ts", "zone", "load_mw"),
        conflict_key=("source", "zone", "ts"),
        to_values=lambda _o: {"ts": 1},  # missing zone/load_mw
    )
    with pytest.raises(ValueError):
        build_rows(bad, _obs(), _prov())


def test_build_rows_empty_observations_is_empty():
    assert build_rows(HOURLY_LOAD, [], _prov()) == []


# --------------------------------------------------------------------------- #
# Upsert SQL — idempotent, keyed on the primary key                           #
# --------------------------------------------------------------------------- #


def test_upsert_sql_is_idempotent_on_conflict_key():
    sql = build_upsert_sql(HOURLY_LOAD)
    assert "INSERT INTO raw.hourly_load" in sql
    assert "ON CONFLICT (source, zone, ts)" in sql
    assert "DO UPDATE SET" in sql
    # key columns are never in the SET clause; value + provenance columns are updated
    assert "source = EXCLUDED.source" not in sql
    assert "ts = EXCLUDED.ts" not in sql
    assert "load_mw = EXCLUDED.load_mw" in sql
    assert "retrieved_at = EXCLUDED.retrieved_at" in sql


def test_upsert_sql_placeholder_count_matches_columns():
    sql = build_upsert_sql(HOURLY_LOAD)
    assert sql.count("%s") == len(HOURLY_LOAD.columns)


def test_upsert_sql_generic_across_datasets():
    sql = build_upsert_sql(HOURLY_LMP)
    assert "INSERT INTO raw.hourly_lmp" in sql
    assert "ON CONFLICT (source, zone, ts)" in sql
    assert "lmp = EXCLUDED.lmp" in sql


# --------------------------------------------------------------------------- #
# Upsert execution — via a fake connection                                     #
# --------------------------------------------------------------------------- #


def test_upsert_rows_executes_one_batch_and_returns_count():
    conn = FakeConn()
    rows = build_rows(HOURLY_LOAD, _obs(), _prov())
    written = upsert_rows(conn, HOURLY_LOAD, rows)
    assert written == 2
    assert len(conn.cursors) == 1
    sql, sent = conn.cursors[0].executemany_calls[0]
    assert sent == rows
    assert "ON CONFLICT (source, zone, ts)" in sql


def test_upsert_rows_empty_is_noop():
    conn = FakeConn()
    assert upsert_rows(conn, HOURLY_LOAD, []) == 0
    assert conn.cursors == []


# --------------------------------------------------------------------------- #
# Record adapters — provider payload -> observations                          #
# --------------------------------------------------------------------------- #


class FakeTimestamp:
    """Mimics a pandas Timestamp: convertible via to_pydatetime()."""

    def __init__(self, dt: datetime) -> None:
        self._dt = dt

    def to_pydatetime(self) -> datetime:
        return self._dt


def test_load_records_normalize_with_column_aliases():
    ts = datetime(2026, 1, 10, 5, tzinfo=UTC)
    records = [
        {"Interval Start": ts, "Load": 8123.4},
        {"Time": ts, "load_mw": 7000},  # alternate aliases + int coerced to float
    ]
    obs = load_observations_from_records(records, zone="ISONE")
    assert obs[0] == LoadObservation(ts=ts, zone="ISONE", load_mw=8123.4)
    assert obs[1].load_mw == 7000.0


def test_load_records_accept_pandas_like_timestamp():
    ts = datetime(2026, 1, 10, 6, tzinfo=UTC)
    obs = load_observations_from_records([{"Time": FakeTimestamp(ts), "Load": 5.0}], "ISONE")
    assert obs[0].ts == ts


def test_records_missing_required_column_raise():
    with pytest.raises(KeyError):
        load_observations_from_records([{"Load": 1.0}], "ISONE")  # no timestamp


def test_lmp_records_normalize():
    ts = datetime(2026, 1, 10, 7, tzinfo=UTC)
    obs = lmp_observations_from_records([{"Time": ts, "LMP": 42.5}], zone="ISONE")
    assert obs == [LmpObservation(ts=ts, zone="ISONE", lmp=42.5)]


# --------------------------------------------------------------------------- #
# Orchestration                                                                #
# --------------------------------------------------------------------------- #


def test_extract_dry_run_builds_rows_and_stamps_provenance_but_writes_nothing():
    source = FakeLoadSource(_obs())
    result = extract(HOURLY_LOAD, source, date(2026, 1, 10), date(2026, 1, 11), conn=None)
    assert result.dry_run is True
    assert result.rows_built == 2
    assert result.rows_written == 0
    # provenance derived from the source, per plan step 3
    assert result.provenance.source == "fake.isone.load"
    assert "fake.get_load" in result.provenance.source_query
    assert result.provenance.dataset_version == "gridstatus==0.30.0-fake"


def test_extract_writes_through_connection_and_reports_count():
    source = FakeLoadSource(_obs())
    conn = FakeConn()
    result = extract(
        HOURLY_LOAD,
        source,
        date(2026, 1, 10),
        date(2026, 1, 11),
        conn=conn,
        retrieved_at=datetime(2026, 1, 11, 12, tzinfo=UTC),
    )
    assert result.rows_written == 2
    assert result.dry_run is False
    assert result.provenance.retrieved_at == datetime(2026, 1, 11, 12, tzinfo=UTC)
    # the fake source was asked for exactly the requested window
    assert source.calls == [(date(2026, 1, 10), date(2026, 1, 11))]
    # rows reached the DB layer
    assert conn.cursors[0].executemany_calls[0][1] == build_rows(
        HOURLY_LOAD, _obs(), result.provenance
    )


def test_reextract_same_window_is_idempotent_by_construction():
    """Two extracts over the same window emit identical rows against an ON CONFLICT
    upsert, so re-running overwrites rather than duplicates (plan step 1)."""
    source = FakeLoadSource(_obs())
    prov_time = datetime(2026, 1, 11, 12, tzinfo=UTC)
    a = extract(HOURLY_LOAD, source, date(2026, 1, 10), date(2026, 1, 11),
                conn=FakeConn(), retrieved_at=prov_time)
    b = extract(HOURLY_LOAD, source, date(2026, 1, 10), date(2026, 1, 11),
                conn=FakeConn(), retrieved_at=prov_time)
    rows_a = build_rows(HOURLY_LOAD, _obs(), a.provenance)
    rows_b = build_rows(HOURLY_LOAD, _obs(), b.provenance)
    assert rows_a == rows_b  # same (source, zone, ts) keys -> upsert collides and overwrites


# --------------------------------------------------------------------------- #
# Source factory                                                               #
# --------------------------------------------------------------------------- #


def test_source_for_load_is_isone_load_source():
    src = source_for("load", zone="ISONE")
    assert isinstance(src, ISONELoadSource)
    assert src.source == "gridstatus.isone.load"
    assert "get_load" in src.describe_query(date(2026, 1, 10), date(2026, 1, 11))


def test_source_for_lmp_is_the_documented_extension_point():
    # lmp dataset exists (row/upsert layers support it) but the live source is not wired
    assert "lmp" in DATASETS
    with pytest.raises(NotImplementedError):
        source_for("lmp")


def test_source_for_unknown_dataset_raises_keyerror():
    with pytest.raises(KeyError):
        source_for("nope")


# --------------------------------------------------------------------------- #
# CLI wiring                                                                    #
# --------------------------------------------------------------------------- #


def _extract_args(**overrides) -> argparse.Namespace:
    base = dict(
        dataset="load",
        start=date(2026, 1, 10),
        end=date(2026, 1, 11),
        zone="ISONE",
        dsn=None,
        dry_run=False,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def test_cli_extract_dry_run(capsys):
    source = FakeLoadSource(_obs())
    code = cli.cmd_extract(
        _extract_args(dry_run=True),
        source_factory=lambda name, zone: source,
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "would write 2 rows" in out
    assert "dataset_version = gridstatus==0.30.0-fake" in out


def test_cli_extract_writes_and_commits(capsys):
    source = FakeLoadSource(_obs())
    conn = FakeConn()
    code = cli.cmd_extract(
        _extract_args(dsn="postg://fake"),
        source_factory=lambda name, zone: source,
        connect=lambda dsn: conn,
    )
    assert code == 0
    assert conn.committed is True
    assert conn.closed is True
    assert "wrote 2 rows" in capsys.readouterr().out


def test_cli_extract_without_dsn_errors(capsys, monkeypatch):
    monkeypatch.delenv("OWR_DATABASE_URL", raising=False)
    code = cli.cmd_extract(
        _extract_args(),
        source_factory=lambda name, zone: FakeLoadSource(_obs()),
    )
    assert code == 2
    assert "no database DSN" in capsys.readouterr().out


def test_cli_parser_dispatches_extract():
    args = cli.build_parser().parse_args(
        ["extract", "--start", "2026-01-10", "--end", "2026-01-11", "--dry-run"]
    )
    assert args.func is cli.cmd_extract
    assert args.dataset == "load"
    assert args.start == date(2026, 1, 10)
    assert args.dry_run is True


def test_cli_transform_and_validate_are_scaffolded(capsys):
    for step in ("transform", "validate"):
        code = cli.main([step])
        assert code == 1
        assert f"etl {step}: not implemented yet" in capsys.readouterr().out


def test_cli_requires_a_subcommand():
    with pytest.raises(SystemExit):
        cli.main([])
