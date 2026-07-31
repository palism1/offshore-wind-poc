"""Tests for the extract-rows CSV round trip (docs/PLAN_EIA_EXTRACTOR.md Phase A3)."""

from __future__ import annotations

from datetime import UTC, datetime

from owr.etl.extract import HOURLY_LOAD, LoadObservation, build_rows
from owr.etl.provenance import Provenance
from owr.etl.rows_csv import read_rows_csv, write_rows_csv

SENTINEL = "SENTINELKEY0123456789abcdefghijklmnopqrst"  # 40 chars


def _rows():
    obs = [
        LoadObservation(
            ts=datetime(2026, 1, 10, 0, tzinfo=UTC),
            zone="ISONE",
            load_mw=8000.0,
            interval_minutes=5.0,
        ),
        LoadObservation(
            ts=datetime(2026, 1, 10, 1, tzinfo=UTC),
            zone="ISONE",
            load_mw=7900.5,
            interval_minutes=5.0,
        ),
    ]
    prov = Provenance.stamp(
        source="fake.isone.load",
        source_query="fake query",
        dataset_version="gridstatus==0.36.0",
        retrieved_at=datetime(2026, 1, 11, tzinfo=UTC),
    )
    return build_rows(HOURLY_LOAD, obs, prov), prov


def test_round_trip_preserves_row_count_ts_and_floats(tmp_path):
    rows, prov = _rows()
    path = tmp_path / "load.csv"
    write_rows_csv(str(path), HOURLY_LOAD, rows, prov)
    with open(path) as f:
        read_rows = read_rows_csv(f, HOURLY_LOAD, origin=str(path))
    assert len(read_rows) == len(rows)
    for row, read_row in zip(rows, read_rows, strict=True):
        mapped = dict(zip(HOURLY_LOAD.columns, row, strict=True))
        assert datetime.fromisoformat(read_row["ts"]) == mapped["ts"]
        assert float(read_row["load_mw"]) == mapped["load_mw"]


def test_writing_twice_is_byte_identical(tmp_path):
    rows, prov = _rows()
    path_a = tmp_path / "a.csv"
    path_b = tmp_path / "b.csv"
    write_rows_csv(str(path_a), HOURLY_LOAD, rows, prov)
    write_rows_csv(str(path_b), HOURLY_LOAD, rows, prov)
    assert path_a.read_bytes() == path_b.read_bytes()


def test_banner_redacts_sentinel_in_source_query(tmp_path, monkeypatch):
    monkeypatch.setenv("EIA_API_KEY", SENTINEL)
    rows, _ = _rows()
    prov = Provenance.stamp(
        source="eia930.isne.wind",
        source_query=f"query with key {SENTINEL} embedded",
        dataset_version="gridstatus==0.36.0",
        retrieved_at=datetime(2026, 1, 11, tzinfo=UTC),
    )
    path = tmp_path / "wind.csv"
    write_rows_csv(str(path), HOURLY_LOAD, rows, prov)
    content = path.read_text()
    assert "***REDACTED***" in content
    assert SENTINEL not in content


def test_read_rows_csv_rejects_mismatched_header(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("# banner\nwrong,header\n1,2\n")
    with open(path) as f:
        try:
            read_rows_csv(f, HOURLY_LOAD, origin=str(path))
        except ValueError as exc:
            assert "does not match" in str(exc)
        else:
            raise AssertionError("expected ValueError for mismatched header")
