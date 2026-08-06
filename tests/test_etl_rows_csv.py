"""Tests for the extract-rows CSV round trip (docs/archive/plans/PLAN_EIA_EXTRACTOR.md Phase A3)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from owr.etl.extract import HOURLY_LOAD, HOURLY_WIND, LoadObservation, WindObservation, build_rows
from owr.etl.provenance import Provenance
from owr.etl.rows_csv import RowsCsvError, read_rows_csv, write_rows_csv

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
        frame = read_rows_csv(f, HOURLY_LOAD, origin=str(path))
    assert len(frame.index) == len(rows)
    read_rows = frame.to_dict("records")
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


def test_read_rows_csv_returns_string_dtype(tmp_path):
    rows, prov = _rows()
    path = tmp_path / "load.csv"
    write_rows_csv(str(path), HOURLY_LOAD, rows, prov)
    with open(path) as f:
        frame = read_rows_csv(f, HOURLY_LOAD, origin=str(path))
    for col in frame.columns:
        assert frame[col].dtype == object
    for record in frame.to_dict("records"):
        for value in record.values():
            assert isinstance(value, str)


def test_blank_cell_reads_back_as_empty_string(tmp_path):
    obs = [
        WindObservation(
            ts=datetime(2026, 1, 10, 0, tzinfo=UTC),
            gen_mw=500.0,
            forecast_mw=None,
            horizon_days=0,
        )
    ]
    prov = Provenance.stamp(
        source="fake.eia930.wind",
        source_query="fake query",
        dataset_version="gridstatus==0.36.0",
        retrieved_at=datetime(2026, 1, 11, tzinfo=UTC),
    )
    rows = build_rows(HOURLY_WIND, obs, prov)
    path = tmp_path / "wind.csv"
    write_rows_csv(str(path), HOURLY_WIND, rows, prov)
    with open(path) as f:
        frame = read_rows_csv(f, HOURLY_WIND, origin=str(path))
    record = frame.to_dict("records")[0]
    assert record["forecast_mw"] == ""


def test_multi_line_source_query_stays_on_one_banner_line(tmp_path):
    obs = [
        WindObservation(
            ts=datetime(2026, 1, 10, 0, tzinfo=UTC),
            gen_mw=500.0,
            forecast_mw=None,
            horizon_days=0,
        )
    ]
    # Built directly, not through Provenance.stamp, which already collapses newlines.
    prov = Provenance(
        source="fake.eia930.wind",
        source_query="line one\nline two",
        dataset_version="gridstatus==0.36.0",
        retrieved_at=datetime(2026, 1, 11, tzinfo=UTC),
    )
    rows = build_rows(HOURLY_WIND, obs, prov)
    path = tmp_path / "wind.csv"
    write_rows_csv(str(path), HOURLY_WIND, rows, prov)
    with open(path) as f:
        frame = read_rows_csv(f, HOURLY_WIND, origin=str(path))
    assert len(frame.index) == len(rows)
    lines = path.read_text().splitlines()
    header_index = next(i for i, line in enumerate(lines) if line.startswith("ts,"))
    for line in lines[:header_index]:
        assert line.startswith("#") or not line.strip()


def test_over_long_data_row_is_rejected_at_any_position(tmp_path):
    header = "ts,zone,load_mw,interval_minutes,source,retrieved_at,source_query,dataset_version"
    ok_row = "2026-01-10T00:00:00+00:00,ISONE,8000.0,5.0,src,2026-01-11T00:00:00+00:00,q,v"
    long_row = ok_row + ",extra"

    first_bad = tmp_path / "first_bad.csv"
    first_bad.write_text(f"{header}\n{long_row}\n{ok_row}\n")
    with open(first_bad) as f:
        with pytest.raises(RowsCsvError):
            read_rows_csv(f, HOURLY_LOAD, origin=str(first_bad))

    second_bad = tmp_path / "second_bad.csv"
    second_bad.write_text(f"{header}\n{ok_row}\n{long_row}\n")
    with open(second_bad) as f:
        with pytest.raises(RowsCsvError):
            read_rows_csv(f, HOURLY_LOAD, origin=str(second_bad))


def test_unclosed_quote_is_rejected(tmp_path):
    header = "ts,zone,load_mw,interval_minutes,source,retrieved_at,source_query,dataset_version"
    bad_row = '2026-01-10T00:00:00+00:00,ISONE,8000.0,5.0,src,2026-01-11T00:00:00+00:00,"unclosed,v'
    path = tmp_path / "unclosed.csv"
    path.write_text(f"{header}\n{bad_row}\n")
    with open(path) as f:
        with pytest.raises(RowsCsvError):
            read_rows_csv(f, HOURLY_LOAD, origin=str(path))


def test_empty_file_keeps_the_module_message(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("")
    expected = "no data rows \\(file is empty or all comments/blank\\)"
    with open(path) as f:
        with pytest.raises(RowsCsvError, match=expected):
            read_rows_csv(f, HOURLY_LOAD, origin=str(path))
