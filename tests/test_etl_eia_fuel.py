"""Tests for the EIA-930 oil and gas hourly generation extractor
(docs/PLAN_EIA_OIL_GAS.md).

No gridstatus import except where a test explicitly needs the installed
library's fuel-column constant (test 17): the provider boundary is a fake EIA
client (``FakeEIAClient``, imported from ``tests.test_etl_eia``) and a fake
frame (``FakeFrame``), so everything else here runs offline. Fixtures import
rather than duplicate ``tests/test_etl_eia.py``'s and
``tests/test_etl_extract.py``'s fakes, per the plan's import instruction.
"""

from __future__ import annotations

import argparse
import pathlib
from datetime import UTC, date, datetime

import numpy as np
import pandas as pd
import pytest

from owr.etl import cli
from owr.etl.credentials import MissingCredentialError, require_eia_api_key
from owr.etl.extract import (
    DATASETS,
    EIA_FUEL_TYPE_DATASET,
    EIA_GAS,
    EIA_OIL,
    HOURLY_GAS,
    HOURLY_OIL,
    EIAFuelSource,
    FuelGenObservation,
    build_rows,
    build_upsert_sql,
    extract,
    fuel_observations_from_records,
    hourly_gaps,
    records_from_frame,
    source_for,
    upsert_rows,
)
from owr.etl.provenance import Provenance
from owr.etl.rows_csv import read_rows_csv, write_rows_csv
from tests.test_etl_eia import SENTINEL, FakeEIAClient, FakeFrame, FakeTimestamp
from tests.test_etl_extract import FakeConn

# --------------------------------------------------------------------------- #
# Fixture frames — every number below is synthetic, chosen to be readable,   #
# and none of it is measured ISO-NE data.                                    #
# --------------------------------------------------------------------------- #

GRIDSTATUS_FUEL_MIX_COLUMNS = (
    "Interval Start", "Interval End", "Respondent", "Respondent Name",
    "Battery Storage", "Coal", "Geothermal", "Hydro", "Natural Gas", "Nuclear",
    "Other", "Other Energy Storage", "Petroleum", "Pumped Storage", "Solar",
    "Solar With Integrated Battery Storage", "Unknown Energy Storage", "Wind",
    "Wind With Integrated Battery Storage",
)

_OTHER_FUEL_COLUMNS = tuple(
    c for c in GRIDSTATUS_FUEL_MIX_COLUMNS
    if c not in ("Interval Start", "Interval End", "Respondent", "Respondent Name")
)


def both_fuels_frame() -> pd.DataFrame:
    """Superset shape: several fuels populated. Proves column selection."""
    ts0 = datetime(2026, 1, 10, 0, tzinfo=UTC)
    ts1 = datetime(2026, 1, 10, 1, tzinfo=UTC)
    data: dict[str, list[object]] = {
        "Interval Start": [ts0, ts1],
        "Interval End": [ts1, datetime(2026, 1, 10, 2, tzinfo=UTC)],
        "Respondent": ["ISNE", "ISNE"],
        "Respondent Name": ["ISO New England", "ISO New England"],
    }
    for col in _OTHER_FUEL_COLUMNS:
        if col == "Petroleum":
            data[col] = [0.0, 12.5]
        elif col == "Natural Gas":
            data[col] = [4210.0, 4155.0]
        else:
            data[col] = [np.nan, np.nan]
    return pd.DataFrame(data)


def single_fuel_frame(column: str, values: list[float]) -> pd.DataFrame:
    """Real production shape: one fuel populated, the other 14 fuel columns NaN."""
    n = len(values)
    ts_start = [datetime(2026, 1, 10, i, tzinfo=UTC) for i in range(n)]
    ts_end = [datetime(2026, 1, 10, i + 1, tzinfo=UTC) for i in range(n)]
    data: dict[str, list[object]] = {
        "Interval Start": ts_start,
        "Interval End": ts_end,
        "Respondent": ["ISNE"] * n,
        "Respondent Name": ["ISO New England"] * n,
    }
    for col in _OTHER_FUEL_COLUMNS:
        data[col] = list(values) if col == column else [np.nan] * n
    return pd.DataFrame(data)


# --------------------------------------------------------------------------- #
# Adapter — tests 1 to 17                                                     #
# --------------------------------------------------------------------------- #


def test_oil_record_normalizes_from_the_petroleum_column():
    ts = datetime(2026, 1, 10, 5, tzinfo=UTC)
    end = datetime(2026, 1, 10, 6, tzinfo=UTC)
    obs = fuel_observations_from_records(
        [{"Interval Start": ts, "Interval End": end, "Petroleum": 512.3}], EIA_OIL
    )
    assert obs == [FuelGenObservation(ts=ts, fuel_code="OIL", gen_mw=512.3, interval_minutes=60.0)]


def test_gas_record_normalizes_from_the_natural_gas_column():
    ts = datetime(2026, 1, 10, 5, tzinfo=UTC)
    end = datetime(2026, 1, 10, 6, tzinfo=UTC)
    obs = fuel_observations_from_records(
        [{"Interval Start": ts, "Interval End": end, "Natural Gas": 4123.0}], EIA_GAS
    )
    assert obs[0].fuel_code == "NG"
    assert obs[0].gen_mw == 4123.0


def test_fuel_record_rejects_the_wrong_column_name():
    ts = datetime(2026, 1, 10, 5, tzinfo=UTC)
    with pytest.raises(KeyError):
        fuel_observations_from_records([{"Interval Start": ts, "Oil": 1.0}], EIA_OIL)


def test_fuel_record_accepts_the_fuel_specific_alias_and_coerces_int():
    ts = datetime(2026, 1, 10, 5, tzinfo=UTC)
    obs = fuel_observations_from_records(
        [{"Interval Start": ts, "Interval End": datetime(2026, 1, 10, 6, tzinfo=UTC),
          "oil_mw": 400}],
        EIA_OIL,
    )
    assert obs[0].gen_mw == 400.0
    obs2 = fuel_observations_from_records(
        [{"Interval Start": ts, "Interval End": datetime(2026, 1, 10, 6, tzinfo=UTC),
          "gas_mw": 400}],
        EIA_GAS,
    )
    assert obs2[0].gen_mw == 400.0


def test_gen_mw_alias_is_not_accepted_for_a_fuel_series():
    ts = datetime(2026, 1, 10, 5, tzinfo=UTC)
    with pytest.raises(KeyError):
        fuel_observations_from_records([{"Interval Start": ts, "gen_mw": 1.0}], EIA_OIL)
    with pytest.raises(KeyError):
        fuel_observations_from_records([{"Interval Start": ts, "gen_mw": 1.0}], EIA_GAS)


def test_fuel_record_accepts_a_pandas_like_timestamp():
    ts = datetime(2026, 1, 10, 7, tzinfo=UTC)
    end = datetime(2026, 1, 10, 8, tzinfo=UTC)
    obs = fuel_observations_from_records(
        [{"Interval Start": FakeTimestamp(ts), "Interval End": FakeTimestamp(end),
          "Petroleum": 1.0}],
        EIA_OIL,
    )
    assert obs[0].ts == ts
    assert obs[0].interval_minutes == 60.0


def test_zero_generation_is_kept_and_is_not_a_reported_zero():
    ts = datetime(2026, 1, 10, 5, tzinfo=UTC)
    end = datetime(2026, 1, 10, 6, tzinfo=UTC)
    obs = fuel_observations_from_records(
        [{"Interval Start": ts, "Interval End": end, "Petroleum": 0.0}], EIA_OIL
    )
    assert obs[0].gen_mw == 0.0


def test_fuel_record_rejects_nan_and_inf_and_names_the_column():
    ts = datetime(2026, 1, 10, 5, tzinfo=UTC)
    end = datetime(2026, 1, 10, 6, tzinfo=UTC)
    with pytest.raises(ValueError, match="Petroleum") as exc1:
        fuel_observations_from_records(
            [{"Interval Start": ts, "Interval End": end, "Petroleum": float("nan")}], EIA_OIL
        )
    assert "OIL" in str(exc1.value)
    with pytest.raises(ValueError, match="Petroleum") as exc2:
        fuel_observations_from_records(
            [{"Interval Start": ts, "Interval End": end, "Petroleum": float("inf")}], EIA_OIL
        )
    assert "OIL" in str(exc2.value)


def test_fuel_record_missing_timestamp_raises_keyerror():
    with pytest.raises(KeyError):
        fuel_observations_from_records([{"Petroleum": 1.0}], EIA_OIL)


def test_fuel_record_without_interval_end_and_without_default_raises():
    ts = datetime(2026, 1, 10, 5, tzinfo=UTC)
    with pytest.raises(ValueError, match="interval_minutes"):
        fuel_observations_from_records([{"Interval Start": ts, "Petroleum": 1.0}], EIA_OIL)


def test_fuel_record_interval_minutes_from_default():
    ts = datetime(2026, 1, 10, 5, tzinfo=UTC)
    obs = fuel_observations_from_records(
        [{"Interval Start": ts, "Petroleum": 1.0}], EIA_OIL, default_interval_minutes=60.0
    )
    assert obs[0].interval_minutes == 60.0


def test_fuel_record_empty_list_is_empty():
    assert fuel_observations_from_records([], EIA_OIL) == []


def test_fuel_observation_rejects_blank_code_and_non_positive_interval():
    with pytest.raises(ValueError, match="fuel_code"):
        FuelGenObservation(ts=datetime(2026, 1, 1, tzinfo=UTC), fuel_code="", gen_mw=1.0,
                            interval_minutes=60.0)
    with pytest.raises(ValueError, match="interval_minutes"):
        FuelGenObservation(ts=datetime(2026, 1, 1, tzinfo=UTC), fuel_code="OIL", gen_mw=1.0,
                            interval_minutes=0.0)


def test_both_fuels_frame_yields_only_the_requested_fuel():
    frame = both_fuels_frame()
    records = records_from_frame(frame)
    oil = fuel_observations_from_records(records, EIA_OIL)
    gas = fuel_observations_from_records(records, EIA_GAS)
    assert [o.gen_mw for o in oil] == [0.0, 12.5]
    assert {o.fuel_code for o in oil} == {"OIL"}
    assert [o.gen_mw for o in gas] == [4210.0, 4155.0]
    assert {o.fuel_code for o in gas} == {"NG"}


def test_single_fuel_frame_is_the_production_shape():
    frame = single_fuel_frame("Petroleum", [0.0, 12.5])
    records = records_from_frame(frame)
    obs = fuel_observations_from_records(records, EIA_OIL)
    assert len(obs) == 2
    assert [o.gen_mw for o in obs] == [0.0, 12.5]


def test_single_fuel_frame_of_the_other_fuel_raises_non_finite():
    frame = single_fuel_frame("Natural Gas", [4210.0, 4155.0])
    records = records_from_frame(frame)
    with pytest.raises(ValueError, match="Petroleum"):
        fuel_observations_from_records(records, EIA_OIL)


def test_fixture_columns_match_the_installed_gridstatus_constant():
    pytest.importorskip("gridstatus")
    from gridstatus.eia_constants import EIA_FUEL_MIX_COLUMNS

    assert list(GRIDSTATUS_FUEL_MIX_COLUMNS) == EIA_FUEL_MIX_COLUMNS


# --------------------------------------------------------------------------- #
# Dataset / rows / SQL — tests 18 to 23                                       #
# --------------------------------------------------------------------------- #


def test_oil_and_gas_datasets_registered():
    assert DATASETS["oil"] is HOURLY_OIL
    assert DATASETS["gas"] is HOURLY_GAS
    assert HOURLY_OIL.table == "raw.hourly_fuel_gen"
    assert HOURLY_GAS.table == "raw.hourly_fuel_gen"


def _oil_obs() -> list[FuelGenObservation]:
    return [
        FuelGenObservation(ts=datetime(2026, 1, 10, 0, tzinfo=UTC), fuel_code="OIL",
                            gen_mw=0.0, interval_minutes=60.0),
        FuelGenObservation(ts=datetime(2026, 1, 10, 1, tzinfo=UTC), fuel_code="OIL",
                            gen_mw=12.5, interval_minutes=60.0),
    ]


def _gas_obs() -> list[FuelGenObservation]:
    return [
        FuelGenObservation(ts=datetime(2026, 1, 10, 0, tzinfo=UTC), fuel_code="NG",
                            gen_mw=4210.0, interval_minutes=60.0),
        FuelGenObservation(ts=datetime(2026, 1, 10, 1, tzinfo=UTC), fuel_code="NG",
                            gen_mw=4155.0, interval_minutes=60.0),
    ]


def _prov(source: str = "eia930.isne.oil") -> Provenance:
    return Provenance.stamp(
        source=source,
        source_query="fake.get_dataset(2026-01-10..2026-01-11)",
        dataset_version="gridstatus==0.36.0-fake",
        retrieved_at=datetime(2026, 1, 11, 12, 0, tzinfo=UTC),
    )


def test_fuel_build_rows_column_order_matches_dataset_columns():
    rows = build_rows(HOURLY_OIL, _oil_obs(), _prov())
    for row in rows:
        assert len(row) == len(HOURLY_OIL.columns)
    mapped = dict(zip(HOURLY_OIL.columns, rows[0], strict=True))
    assert mapped["fuel_code"] == "OIL"


def test_fuel_upsert_sql_shape():
    sql = build_upsert_sql(HOURLY_OIL)
    assert "INSERT INTO raw.hourly_fuel_gen" in sql
    assert "ON CONFLICT (source, ts, fuel_code)" in sql
    assert "gen_mw = EXCLUDED.gen_mw" in sql
    assert "interval_minutes = EXCLUDED.interval_minutes" in sql
    assert "fuel_code = EXCLUDED." not in sql
    assert "ts = EXCLUDED." not in sql
    assert "source = EXCLUDED." not in sql


def test_fuel_upsert_sql_placeholder_count():
    sql = build_upsert_sql(HOURLY_OIL)
    assert sql.count("%s") == len(HOURLY_OIL.columns)


def test_oil_and_gas_rows_do_not_collide_on_the_conflict_key():
    oil_rows = build_rows(HOURLY_OIL, _oil_obs()[:1], _prov("eia930.isne.oil"))
    gas_rows = build_rows(HOURLY_GAS, _gas_obs()[:1], _prov("eia930.isne.gas"))
    oil_cols = HOURLY_OIL.columns
    gas_cols = HOURLY_GAS.columns

    def key(cols, row):
        mapped = dict(zip(cols, row, strict=True))
        return (mapped["source"], mapped["ts"], mapped["fuel_code"])

    assert key(oil_cols, oil_rows[0]) != key(gas_cols, gas_rows[0])


def test_fuel_upsert_rows_through_fake_conn():
    conn = FakeConn()
    rows = build_rows(HOURLY_OIL, _oil_obs(), _prov())
    written = upsert_rows(conn, HOURLY_OIL, rows)
    assert written == 2
    assert conn.cursors[0].executemany_calls[0][1] == rows


# --------------------------------------------------------------------------- #
# hourly_gaps — tests 24 and 25                                               #
# --------------------------------------------------------------------------- #


def test_hourly_gaps_finds_an_interior_hole():
    base = datetime(2026, 1, 10, 0, tzinfo=UTC)
    series = [base, base.replace(hour=1), base.replace(hour=3), base.replace(hour=4)]
    gaps = hourly_gaps(series)
    assert gaps == [base.replace(hour=2)]
    # unsorted + duplicate input changes nothing
    unsorted_with_dupe = [series[3], series[0], series[0], series[2], series[1]]
    assert hourly_gaps(unsorted_with_dupe) == [base.replace(hour=2)]


def test_hourly_gaps_is_empty_for_a_contiguous_short_or_empty_series():
    base = datetime(2026, 1, 10, 0, tzinfo=UTC)
    contiguous = [base, base.replace(hour=1), base.replace(hour=2)]
    assert hourly_gaps(contiguous) == []
    assert hourly_gaps([base]) == []
    assert hourly_gaps([]) == []


# --------------------------------------------------------------------------- #
# Migration 004 — test 26                                                     #
# --------------------------------------------------------------------------- #


def test_migration_004_matches_the_dataset_descriptor():
    path = (
        pathlib.Path(__file__).resolve().parents[1]
        / "db" / "migrations" / "004_hourly_fuel_gen.sql"
    )
    text = path.read_text()
    for col in HOURLY_OIL.columns:
        assert col in text
    assert "PRIMARY KEY (source, ts, fuel_code)" in text
    assert HOURLY_OIL.table in text


# --------------------------------------------------------------------------- #
# Source — tests 27 to 38                                                     #
# --------------------------------------------------------------------------- #


def test_source_for_oil_and_gas_return_fuel_sources():
    oil_src = source_for("oil", zone="ISNE")
    gas_src = source_for("gas", zone="ISNE")
    assert isinstance(oil_src, EIAFuelSource)
    assert isinstance(gas_src, EIAFuelSource)
    assert oil_src.source == "eia930.isne.oil"
    assert gas_src.source == "eia930.isne.gas"


def test_source_for_fuel_rejects_a_load_zone():
    assert isinstance(source_for("oil", zone="ISNE"), EIAFuelSource)
    assert isinstance(source_for("oil", zone="ISONE"), EIAFuelSource)
    with pytest.raises(ValueError) as exc:
        source_for("oil", zone="NEMA")
    assert "oil" in str(exc.value)
    assert "ISNE" in str(exc.value)


def test_wind_zone_error_message_is_unchanged():
    with pytest.raises(ValueError) as exc:
        source_for("wind", zone="NEMA")
    assert str(exc.value) == (
        "the wind dataset is EIA-930 balancing-authority data (respondent "
        "ISNE) and has no load zone; got --zone 'NEMA'. "
        "Omit --zone or pass ISNE."
    )


def test_fuel_describe_query_contents():
    src = EIAFuelSource(EIA_OIL)
    text = src.describe_query(date(2026, 1, 1), date(2026, 1, 8))
    assert EIA_FUEL_TYPE_DATASET in text
    assert "respondent=ISNE" in text
    assert "fueltype=OIL" in text
    assert "frequency=hourly" in text
    assert "2026-01-01" in text
    assert "2026-01-08" in text
    assert "column=Petroleum" in text
    assert "fuel_code=OIL" in text
    assert "$EIA_API_KEY" in text


def test_fuel_describe_query_is_single_line_and_deterministic():
    src = EIAFuelSource(EIA_OIL)
    a = src.describe_query(date(2026, 1, 1), date(2026, 1, 8))
    b = src.describe_query(date(2026, 1, 1), date(2026, 1, 8))
    assert "\n" not in a
    assert a == b


def test_fuel_get_observations_calls_get_dataset_with_expected_kwargs():
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 1, 1, tzinfo=UTC)
    client = FakeEIAClient(
        records=[{"Interval Start": ts, "Interval End": end, "Petroleum": 100.0}]
    )
    src = EIAFuelSource(EIA_OIL, client_factory=lambda: client, getenv=lambda _n: "a-real-key")
    obs = src.get_observations(date(2026, 1, 1), date(2026, 1, 8))
    assert len(obs) == 1
    call = client.get_dataset_calls[0]
    assert call["dataset"] == EIA_FUEL_TYPE_DATASET
    assert call["frequency"] == "hourly"
    assert call["facets"] == {"respondent": "ISNE", "fueltype": "OIL"}


class _SnapshottingClient:
    """Snapshots facets, then list-wraps them in place, mimicking _facet_handler."""

    def __init__(self, records: list[dict[str, object]]) -> None:
        self.records = records
        self.snapshots: list[dict[str, object]] = []

    def get_dataset(self, dataset: str, **kwargs: object) -> FakeFrame:
        facets = kwargs["facets"]
        self.snapshots.append(dict(facets))
        for k, v in list(facets.items()):
            facets[k] = [v]
        return FakeFrame(self.records)


def test_fuel_source_sends_a_fresh_facets_mapping_on_every_call():
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 1, 1, tzinfo=UTC)
    client = _SnapshottingClient(
        records=[{"Interval Start": ts, "Interval End": end, "Petroleum": 1.0}]
    )
    src = EIAFuelSource(EIA_OIL, client_factory=lambda: client, getenv=lambda _n: "a-real-key")
    src.get_observations(date(2026, 1, 1), date(2026, 1, 8))
    src.get_observations(date(2026, 1, 1), date(2026, 1, 8))
    assert client.snapshots == [
        {"respondent": "ISNE", "fueltype": "OIL"},
        {"respondent": "ISNE", "fueltype": "OIL"},
    ]


def test_fuel_get_observations_missing_key_never_builds_the_client():
    calls = []

    def client_factory():
        calls.append(1)
        return FakeEIAClient()

    src = EIAFuelSource(EIA_OIL, client_factory=client_factory, getenv=lambda _n: None)
    with pytest.raises(MissingCredentialError):
        src.get_observations(date(2026, 1, 1), date(2026, 1, 8))
    assert len(calls) == 0


def test_fuel_describe_query_never_contains_the_key_value():
    getenv = lambda name: SENTINEL if name == "EIA_API_KEY" else None  # noqa: E731
    src = EIAFuelSource(EIA_OIL, getenv=getenv)
    text = src.describe_query(date(2026, 1, 1), date(2026, 1, 8))
    assert SENTINEL not in text


def test_fuel_repr_and_vars_never_contain_the_key_value():
    getenv = lambda name: SENTINEL if name == "EIA_API_KEY" else None  # noqa: E731
    src = EIAFuelSource(EIA_OIL, getenv=getenv)
    assert SENTINEL not in repr(src)
    assert SENTINEL not in str(vars(src))


def test_fuel_extract_rows_and_provenance_never_contain_the_key(monkeypatch):
    monkeypatch.setenv("EIA_API_KEY", SENTINEL)
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 1, 1, tzinfo=UTC)
    client = FakeEIAClient(
        records=[{"Interval Start": ts, "Interval End": end, "Petroleum": 100.0}]
    )
    src = EIAFuelSource(
        EIA_OIL,
        client_factory=lambda: client,
        version_provider=lambda: "gridstatus==0.36.0-fake",
    )
    result = extract(HOURLY_OIL, src, date(2026, 1, 1), date(2026, 1, 8), conn=None)
    assert not any(SENTINEL in str(cell) for row in result.rows for cell in row)
    prov = result.provenance
    assert SENTINEL not in prov.source
    assert SENTINEL not in prov.source_query
    assert SENTINEL not in prov.dataset_version


def test_missing_key_message_names_the_eia_datasets():
    with pytest.raises(MissingCredentialError) as exc:
        require_eia_api_key(getenv=lambda _n: None)
    text = str(exc.value)
    assert "wind" in text
    assert "oil" in text
    assert "gas" in text


# --------------------------------------------------------------------------- #
# CLI and CSV — tests 39 to 45                                                #
# --------------------------------------------------------------------------- #


def test_cli_dataset_choices_include_oil_and_gas():
    args = cli.build_parser().parse_args(
        ["extract", "--dataset", "oil", "--start", "2026-01-10", "--end", "2026-01-11",
         "--dry-run"]
    )
    assert args.dataset == "oil"
    args2 = cli.build_parser().parse_args(
        ["extract", "--dataset", "gas", "--start", "2026-01-10", "--end", "2026-01-11",
         "--dry-run"]
    )
    assert args2.dataset == "gas"


class _FakeFuelSource:
    source = "fake.eia930.oil"

    def __init__(self, observations: list[FuelGenObservation]) -> None:
        self._observations = observations

    def get_observations(self, start: date, end: date) -> list[object]:
        return list(self._observations)

    def describe_query(self, start: date, end: date) -> str:
        return f"fake.get_dataset({start.isoformat()}..{end.isoformat()})"

    def dataset_version(self) -> str:
        return "gridstatus==0.36.0-fake"


def test_cli_dry_run_stdout_never_contains_the_key_for_oil(monkeypatch, capsys):
    monkeypatch.setenv("EIA_API_KEY", SENTINEL)
    args = argparse.Namespace(
        dataset="oil", start=date(2026, 1, 1), end=date(2026, 1, 8),
        zone="ISNE", dsn=None, dry_run=True, out=None,
    )
    code = cli.cmd_extract(
        args, source_factory=lambda name, zone: _FakeFuelSource(_oil_obs())
    )
    assert code == 0
    assert SENTINEL not in capsys.readouterr().out


@pytest.mark.parametrize("dataset", ["oil", "gas"])
def test_cli_missing_key_returns_2_for_oil_and_gas(dataset, monkeypatch, capsys):
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    args = argparse.Namespace(
        dataset=dataset, start=date(2026, 1, 1), end=date(2026, 1, 8),
        zone="ISNE", dsn=None, dry_run=True, out=None,
    )
    code = cli.cmd_extract(args, source_factory=lambda name, zone: source_for(name, zone=zone))
    assert code == 2
    out = capsys.readouterr().out
    assert "EIA_API_KEY" in out
    assert "https://www.eia.gov/opendata/register.php" in out
    assert "Traceback" not in out


def test_cli_dry_run_out_csv_carries_the_fuel_columns(tmp_path, capsys):
    out = tmp_path / "oil.csv"
    args = argparse.Namespace(
        dataset="oil", start=date(2026, 1, 1), end=date(2026, 1, 8),
        zone="ISNE", dsn=None, dry_run=True, out=str(out),
    )
    code = cli.cmd_extract(
        args, source_factory=lambda name, zone: _FakeFuelSource(_oil_obs())
    )
    assert code == 0
    text = out.read_text()
    assert "# dataset = oil" in text
    assert "# table = raw.hourly_fuel_gen" in text
    lines = [line for line in text.splitlines() if not line.startswith("#")]
    assert lines[0] == ",".join(HOURLY_OIL.columns)
    for line in lines[1:]:
        assert line.split(",")[1] == "OIL"


def test_oil_rows_csv_round_trips_through_read_rows_csv(tmp_path):
    src = EIAFuelSource(EIA_OIL, version_provider=lambda: "gridstatus==0.36.0-fake")
    query = src.describe_query(date(2026, 1, 1), date(2026, 1, 8))
    prov = Provenance.stamp(
        source="eia930.isne.oil",
        source_query=query,
        dataset_version="gridstatus==0.36.0-fake",
        retrieved_at=datetime(2026, 1, 11, 12, 0, tzinfo=UTC),
    )
    rows = build_rows(HOURLY_OIL, _oil_obs(), prov)
    out = tmp_path / "oil.csv"
    write_rows_csv(str(out), HOURLY_OIL, rows, prov)
    with open(out) as f:
        frame = read_rows_csv(f, HOURLY_OIL, origin=str(out))
    assert tuple(frame.columns) == HOURLY_OIL.columns
    assert set(frame["fuel_code"]) == {"OIL"}


def test_fuel_dry_run_builds_rows_and_writes_nothing():
    source = _FakeFuelSource(_oil_obs())
    result = extract(HOURLY_OIL, source, date(2026, 1, 10), date(2026, 1, 11), conn=None)
    assert result.rows_built == 2
    assert result.rows_written == 0
    assert result.dry_run is True


def test_fuel_reextract_same_window_is_idempotent():
    source = _FakeFuelSource(_oil_obs())
    prov_time = datetime(2026, 1, 11, 12, tzinfo=UTC)
    a = extract(
        HOURLY_OIL, source, date(2026, 1, 10), date(2026, 1, 11), retrieved_at=prov_time
    )
    b = extract(
        HOURLY_OIL, source, date(2026, 1, 10), date(2026, 1, 11), retrieved_at=prov_time
    )
    rows_a = build_rows(HOURLY_OIL, _oil_obs(), a.provenance)
    rows_b = build_rows(HOURLY_OIL, _oil_obs(), b.provenance)
    assert rows_a == rows_b


# --------------------------------------------------------------------------- #
# Docker-gated Postgres round trip — test 46                                  #
# --------------------------------------------------------------------------- #


def test_oil_and_gas_upsert_round_trips_through_postgres():
    """Follows tests/test_pg_store.py:9-24's skip pattern exactly."""
    import os

    psycopg = pytest.importorskip("psycopg")
    dsn = os.environ.get("OWR_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("OWR_TEST_DATABASE_URL not set; skipping live Postgres round trip")

    conn = psycopg.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE raw.hourly_fuel_gen")
        conn.commit()

        prov1 = Provenance.stamp(
            source="eia930.isne.oil",
            source_query="test query",
            dataset_version="gridstatus==0.36.0-fake",
            retrieved_at=datetime(2026, 1, 11, 12, 0, tzinfo=UTC),
        )
        gas_prov1 = Provenance.stamp(
            source="eia930.isne.gas",
            source_query="test query",
            dataset_version="gridstatus==0.36.0-fake",
            retrieved_at=datetime(2026, 1, 11, 12, 0, tzinfo=UTC),
        )
        oil_rows = build_rows(HOURLY_OIL, _oil_obs(), prov1)
        gas_rows = build_rows(HOURLY_GAS, _gas_obs(), gas_prov1)
        upsert_rows(conn, HOURLY_OIL, oil_rows)
        upsert_rows(conn, HOURLY_GAS, gas_rows)
        conn.commit()

        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM raw.hourly_fuel_gen")
            assert cur.fetchone()[0] == 4

        prov2_time = datetime(2026, 1, 12, 12, 0, tzinfo=UTC)
        prov2 = Provenance.stamp(
            source="eia930.isne.oil",
            source_query="test query",
            dataset_version="gridstatus==0.36.0-fake",
            retrieved_at=prov2_time,
        )
        gas_prov2 = Provenance.stamp(
            source="eia930.isne.gas",
            source_query="test query",
            dataset_version="gridstatus==0.36.0-fake",
            retrieved_at=prov2_time,
        )
        upsert_rows(conn, HOURLY_OIL, build_rows(HOURLY_OIL, _oil_obs(), prov2))
        upsert_rows(conn, HOURLY_GAS, build_rows(HOURLY_GAS, _gas_obs(), gas_prov2))
        conn.commit()

        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM raw.hourly_fuel_gen")
            assert cur.fetchone()[0] == 4
            cur.execute("SELECT DISTINCT retrieved_at FROM raw.hourly_fuel_gen")
            retrieved_ats = {row[0] for row in cur.fetchall()}
            assert retrieved_ats == {prov2_time}
    finally:
        conn.close()
