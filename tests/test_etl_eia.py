"""Tests for the EIA-930 wind extractor (docs/PLAN_EIA_EXTRACTOR.md Phase A2).

No gridstatus import: the provider boundary is a fake EIA client
(``FakeEIAClient``) and a fake frame (``FakeFrame``), so everything here runs
offline. The key-leak assertions are the load-bearing group — they prove the
EIA_API_KEY value never reaches a row, a repr, stdout, or an unredacted error
message.
"""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime

import pandas as pd
import pytest

from owr.etl import cli
from owr.etl.credentials import MissingCredentialError
from owr.etl.extract import (
    DATASETS,
    EIA_FUEL_TYPE_DATASET,
    HOURLY_WIND,
    EIAWindSource,
    WindObservation,
    build_rows,
    build_upsert_sql,
    extract,
    records_from_frame,
    source_for,
    wind_observations_from_records,
)
from owr.etl.provenance import Provenance

SENTINEL = "SENTINELKEY0123456789abcdefghijklmnopqrst"  # 40 chars


# --------------------------------------------------------------------------- #
# Fakes                                                                        #
# --------------------------------------------------------------------------- #


class FakeTimestamp:
    """Mimics a pandas Timestamp: convertible via to_pydatetime()."""

    def __init__(self, dt: datetime) -> None:
        self._dt = dt

    def to_pydatetime(self) -> datetime:
        return self._dt


class FakeFrame:
    def __init__(self, records: list[dict[str, object]]) -> None:
        self._records = records

    def to_dict(self, orient: str) -> list[dict[str, object]]:
        assert orient == "records"
        return list(self._records)


class FakeEIAClient:
    """Records get_dataset calls; list_routes/list_facets raise (query-param canary)."""

    def __init__(self, records: list[dict[str, object]] | None = None) -> None:
        self.records = records if records is not None else []
        self.get_dataset_calls: list[dict[str, object]] = []

    def get_dataset(self, dataset: str, **kwargs: object) -> FakeFrame:
        self.get_dataset_calls.append({"dataset": dataset, **kwargs})
        return FakeFrame(self.records)

    def list_routes(self, *args: object, **kwargs: object) -> None:
        raise AssertionError(
            "list_routes/list_facets send the API key as a URL query parameter; "
            "owr must never call them"
        )

    def list_facets(self, *args: object, **kwargs: object) -> None:
        raise AssertionError(
            "list_routes/list_facets send the API key as a URL query parameter; "
            "owr must never call them"
        )


class FakeWindSource:
    """A stand-in Source for CLI-level tests, mirroring FakeLoadSource."""

    source = "fake.eia930.wind"

    def __init__(self, observations: list[WindObservation]) -> None:
        self._observations = observations

    def get_observations(self, start: date, end: date) -> list[object]:
        return list(self._observations)

    def describe_query(self, start: date, end: date) -> str:
        return f"fake.get_dataset({start.isoformat()}..{end.isoformat()})"

    def dataset_version(self) -> str:
        return "gridstatus==0.36.0-fake"


def _wind_obs() -> list[WindObservation]:
    return [
        WindObservation(ts=datetime(2026, 1, 10, 0, tzinfo=UTC), gen_mw=500.0),
        WindObservation(ts=datetime(2026, 1, 10, 1, tzinfo=UTC), gen_mw=520.0),
    ]


def _prov() -> Provenance:
    return Provenance.stamp(
        source="fake.eia930.wind",
        source_query="fake.get_dataset(2026-01-10..2026-01-11)",
        dataset_version="gridstatus==0.36.0-fake",
        retrieved_at=datetime(2026, 1, 11, 12, 0, tzinfo=UTC),
    )


# --------------------------------------------------------------------------- #
# Adapter                                                                      #
# --------------------------------------------------------------------------- #


def test_wind_record_normalizes_from_gridstatus_shape():
    ts = datetime(2026, 1, 10, 5, tzinfo=UTC)
    obs = wind_observations_from_records([{"Interval Start": ts, "Wind": 512.3}])
    assert obs == [WindObservation(ts=ts, gen_mw=512.3, forecast_mw=None, horizon_days=0)]


def test_wind_record_accepts_mw_and_gen_mw_aliases_and_int_coercion():
    ts = datetime(2026, 1, 10, 6, tzinfo=UTC)
    obs = wind_observations_from_records([{"Interval Start": ts, "MW": 400}])
    assert obs[0].gen_mw == 400.0
    obs2 = wind_observations_from_records([{"Interval Start": ts, "gen_mw": 300}])
    assert obs2[0].gen_mw == 300.0


def test_wind_record_accepts_pandas_like_timestamp():
    ts = datetime(2026, 1, 10, 7, tzinfo=UTC)
    obs = wind_observations_from_records([{"Interval Start": FakeTimestamp(ts), "Wind": 1.0}])
    assert obs[0].ts == ts


def test_wind_record_missing_timestamp_raises_keyerror():
    with pytest.raises(KeyError):
        wind_observations_from_records([{"Wind": 1.0}])


def test_wind_record_missing_wind_value_raises_keyerror():
    ts = datetime(2026, 1, 10, 8, tzinfo=UTC)
    with pytest.raises(KeyError):
        wind_observations_from_records([{"Interval Start": ts}])


def test_wind_record_rejects_non_finite_values():
    ts = datetime(2026, 1, 10, 9, tzinfo=UTC)
    with pytest.raises(ValueError, match="ts=2026-01-10T09:00:00"):
        wind_observations_from_records([{"Interval Start": ts, "Wind": float("nan")}])
    with pytest.raises(ValueError, match="ts=2026-01-10T09:00:00"):
        wind_observations_from_records([{"Interval Start": ts, "Wind": float("inf")}])


def test_wind_record_empty_list_is_empty():
    assert wind_observations_from_records([]) == []


def test_real_nan_wind_cell_raises_non_finite():
    ts = pd.Timestamp("2026-01-10T09:00:00Z")
    frame = pd.DataFrame({"Interval Start": [ts], "Wind": [float("nan")]})
    records = records_from_frame(frame)
    with pytest.raises(ValueError, match="non-finite wind value"):
        wind_observations_from_records(records)


# --------------------------------------------------------------------------- #
# Dataset / rows / SQL                                                         #
# --------------------------------------------------------------------------- #


def test_wind_dataset_registered():
    assert "wind" in DATASETS
    assert DATASETS["wind"] is HOURLY_WIND


def test_build_rows_column_order_matches_dataset_columns():
    rows = build_rows(HOURLY_WIND, _wind_obs(), _prov())
    for row in rows:
        assert len(row) == len(HOURLY_WIND.columns)
    mapped = dict(zip(HOURLY_WIND.columns, rows[0], strict=True))
    assert mapped["gen_mw"] == 500.0
    assert mapped["horizon_days"] == 0


def test_wind_upsert_sql_shape():
    sql = build_upsert_sql(HOURLY_WIND)
    assert "INSERT INTO raw.hourly_wind" in sql
    assert "ON CONFLICT (source, ts, horizon_days)" in sql
    assert "gen_mw = EXCLUDED.gen_mw" in sql
    assert "forecast_mw = EXCLUDED.forecast_mw" in sql
    assert "horizon_days = EXCLUDED." not in sql
    assert "ts = EXCLUDED." not in sql
    assert "source = EXCLUDED." not in sql


def test_wind_upsert_sql_placeholder_count():
    sql = build_upsert_sql(HOURLY_WIND)
    assert sql.count("%s") == len(HOURLY_WIND.columns)


def test_wind_upsert_rows_through_fake_conn(monkeypatch):
    from tests.test_etl_extract import FakeConn

    conn = FakeConn()
    rows = build_rows(HOURLY_WIND, _wind_obs(), _prov())
    from owr.etl.extract import upsert_rows

    written = upsert_rows(conn, HOURLY_WIND, rows)
    assert written == 2
    assert conn.cursors[0].executemany_calls[0][1] == rows


# --------------------------------------------------------------------------- #
# Source                                                                       #
# --------------------------------------------------------------------------- #


def test_source_for_wind_is_eia_wind_source():
    src = source_for("wind")
    assert isinstance(src, EIAWindSource)
    assert src.source == "eia930.isne.wind"


def test_source_for_wind_zone_validation():
    assert isinstance(source_for("wind", zone="ISNE"), EIAWindSource)
    with pytest.raises(ValueError, match="ISNE"):
        source_for("wind", zone="NEMA")


def test_wind_describe_query_contents():
    src = EIAWindSource()
    text = src.describe_query(date(2026, 1, 1), date(2026, 1, 8))
    assert EIA_FUEL_TYPE_DATASET in text
    assert "respondent=ISNE" in text
    assert "fueltype=WND" in text
    assert "frequency=hourly" in text
    assert "2026-01-01" in text
    assert "2026-01-08" in text
    assert "$EIA_API_KEY" in text


def test_wind_describe_query_is_deterministic():
    src = EIAWindSource()
    a = src.describe_query(date(2026, 1, 1), date(2026, 1, 8))
    b = src.describe_query(date(2026, 1, 1), date(2026, 1, 8))
    assert a == b


def test_wind_get_observations_calls_get_dataset_with_expected_kwargs():
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    client = FakeEIAClient(records=[{"Interval Start": ts, "Wind": 100.0}])
    src = EIAWindSource(client_factory=lambda: client, getenv=lambda _n: "a-real-key")
    obs = src.get_observations(date(2026, 1, 1), date(2026, 1, 8))
    assert len(obs) == 1
    call = client.get_dataset_calls[0]
    assert call["dataset"] == EIA_FUEL_TYPE_DATASET
    assert call["frequency"] == "hourly"
    assert call["facets"] == {"respondent": "ISNE", "fueltype": "WND"}


def test_wind_get_observations_missing_key_never_builds_client():
    calls = []

    def client_factory():
        calls.append(1)
        return FakeEIAClient()

    src = EIAWindSource(client_factory=client_factory, getenv=lambda _n: None)
    with pytest.raises(MissingCredentialError):
        src.get_observations(date(2026, 1, 1), date(2026, 1, 8))
    assert len(calls) == 0


def test_fake_eia_client_list_routes_and_list_facets_raise():
    """Query-param canary: turns the never-call-these rule into an enforced check."""
    client = FakeEIAClient()
    with pytest.raises(AssertionError, match="query parameter"):
        client.list_routes()
    with pytest.raises(AssertionError, match="query parameter"):
        client.list_facets()


# --------------------------------------------------------------------------- #
# Key-leak assertions — the load-bearing group                                #
# --------------------------------------------------------------------------- #


def test_describe_query_never_contains_the_key_value():
    getenv = lambda name: SENTINEL if name == "EIA_API_KEY" else None  # noqa: E731
    src = EIAWindSource(getenv=getenv)
    text = src.describe_query(date(2026, 1, 1), date(2026, 1, 8))
    assert SENTINEL not in text


def test_repr_and_vars_never_contain_the_key_value():
    getenv = lambda name: SENTINEL if name == "EIA_API_KEY" else None  # noqa: E731
    src = EIAWindSource(getenv=getenv)
    assert SENTINEL not in repr(src)
    assert SENTINEL not in str(vars(src))


def test_extract_rows_and_provenance_never_contain_the_key(monkeypatch):
    monkeypatch.setenv("EIA_API_KEY", SENTINEL)
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    client = FakeEIAClient(records=[{"Interval Start": ts, "Wind": 100.0}])
    src = EIAWindSource(client_factory=lambda: client)
    result = extract(HOURLY_WIND, src, date(2026, 1, 1), date(2026, 1, 8), conn=None)
    assert not any(SENTINEL in str(cell) for row in result.rows for cell in row)
    prov = result.provenance
    assert SENTINEL not in prov.source
    assert SENTINEL not in prov.source_query
    assert SENTINEL not in prov.dataset_version


def test_cli_dry_run_stdout_never_contains_the_key(monkeypatch, capsys):
    monkeypatch.setenv("EIA_API_KEY", SENTINEL)
    args = argparse.Namespace(
        dataset="wind", start=date(2026, 1, 1), end=date(2026, 1, 8),
        zone="ISONE", dsn=None, dry_run=True, out=None,
    )
    code = cli.cmd_extract(args, source_factory=lambda name, zone: FakeWindSource(_wind_obs()))
    assert code == 0
    assert SENTINEL not in capsys.readouterr().out


def test_cli_exception_redacts_the_key_when_var_is_set(monkeypatch, capsys):
    monkeypatch.setenv("EIA_API_KEY", SENTINEL)

    class BoomSource:
        source = "boom"

        def get_observations(self, start, end):
            raise RuntimeError(f"boom {SENTINEL}")

        def describe_query(self, start, end):
            return "boom query"

        def dataset_version(self):
            return "boom==1"

    args = argparse.Namespace(
        dataset="wind", start=date(2026, 1, 1), end=date(2026, 1, 8),
        zone="ISONE", dsn=None, dry_run=True, out=None,
    )
    code = cli.cmd_extract(args, source_factory=lambda name, zone: BoomSource())
    assert code != 0
    out = capsys.readouterr().out
    assert "***REDACTED***" in out
    assert SENTINEL not in out


def test_cli_exception_unredacted_when_var_unset_mirror_case(monkeypatch, capsys):
    monkeypatch.delenv("EIA_API_KEY", raising=False)

    class BoomSource:
        source = "boom"

        def get_observations(self, start, end):
            raise RuntimeError(f"boom {SENTINEL}")

        def describe_query(self, start, end):
            return "boom query"

        def dataset_version(self):
            return "boom==1"

    args = argparse.Namespace(
        dataset="wind", start=date(2026, 1, 1), end=date(2026, 1, 8),
        zone="ISONE", dsn=None, dry_run=True, out=None,
    )
    code = cli.cmd_extract(args, source_factory=lambda name, zone: BoomSource())
    assert code != 0
    out = capsys.readouterr().out
    assert SENTINEL in out  # proves redaction is env-driven, not an unconditional replace


def test_cli_missing_key_returns_2_with_actionable_message_no_traceback(monkeypatch, capsys):
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    args = argparse.Namespace(
        dataset="wind", start=date(2026, 1, 1), end=date(2026, 1, 8),
        zone="ISONE", dsn=None, dry_run=True, out=None,
    )
    code = cli.cmd_extract(args, source_factory=lambda name, zone: source_for(name, zone=zone))
    assert code == 2
    out = capsys.readouterr().out
    assert "EIA_API_KEY" in out
    assert "https://www.eia.gov/opendata/register.php" in out
    assert "Traceback" not in out


# --------------------------------------------------------------------------- #
# End-to-end                                                                   #
# --------------------------------------------------------------------------- #


def test_wind_dry_run_builds_rows_and_writes_nothing():
    source = FakeWindSource(_wind_obs())
    result = extract(HOURLY_WIND, source, date(2026, 1, 10), date(2026, 1, 11), conn=None)
    assert result.rows_built == 2
    assert result.rows_written == 0
    assert result.dry_run is True


def test_wind_reextract_same_window_is_idempotent_by_construction():
    source = FakeWindSource(_wind_obs())
    prov_time = datetime(2026, 1, 11, 12, tzinfo=UTC)
    a = extract(
        HOURLY_WIND, source, date(2026, 1, 10), date(2026, 1, 11), retrieved_at=prov_time
    )
    b = extract(
        HOURLY_WIND, source, date(2026, 1, 10), date(2026, 1, 11), retrieved_at=prov_time
    )
    rows_a = build_rows(HOURLY_WIND, _wind_obs(), a.provenance)
    rows_b = build_rows(HOURLY_WIND, _wind_obs(), b.provenance)
    assert rows_a == rows_b
