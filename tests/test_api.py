"""End-to-end API tests (Phase 4) via FastAPI TestClient — no DB, no credentials."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from owr.api import create_app
from owr.api.store import InMemoryRepository


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(InMemoryRepository()))


def _scenario_body() -> dict:
    return {
        "name": "winter cold snap",
        "storage_total_mwh": 20000,
        "storage_start_mwh": 20000,
        "power_output_mw": 2000,
        "soc_floor_frac": 0.33,
        "strategic_reserve_frac": 0.0,
        "season": "winter",
        "date_start": "2026-01-10",
        "date_end": "2026-01-12",
        "min_stress_window_days": 2,
        "severity_percentile": 0.5,
        "available_capacity_mw": 13000,
    }


def _days(n: int = 3) -> list[dict]:
    out = []
    for i in range(n):
        load = [8000.0] * 24
        load[17], load[18], load[19] = 10000.0, 12000.0, 10000.0
        out.append(
            {
                "date": (date(2026, 1, 10) + timedelta(days=i)).isoformat(),
                "hourly_load_mw": load,
                "hourly_wind_mw": [500.0] * 24,
                "demand_percentile": 0.95,
                "wind_forecast_frac": 0.1,
            }
        )
    return out


def test_health(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_scenario_create_and_fetch(client: TestClient):
    r = client.post("/scenarios", json=_scenario_body())
    assert r.status_code == 201
    sid = r.json()["id"]
    got = client.get(f"/scenarios/{sid}")
    assert got.status_code == 200
    assert got.json()["storage_total_mwh"] == 20000


def test_missing_scenario_404(client: TestClient):
    assert client.get("/scenarios/999").status_code == 404


def test_full_run_flow(client: TestClient):
    sid = client.post("/scenarios", json=_scenario_body()).json()["id"]
    run = client.post(f"/scenarios/{sid}/runs", json={"days": _days()})
    assert run.status_code == 201
    assert run.json()["status"] == "succeeded"
    rid = run.json()["id"]

    results = client.get(f"/runs/{rid}/results").json()
    assert len(results["daily"]) == 3
    # reserve trims the peak below the direct-to-grid baseline
    assert results["reserve_peak_mw"] < results["baseline_peak_mw"]
    assert results["severity_reduction"] > 0
    # reserve floor (33% of 20000 = 6600) never breached
    for day in results["daily"]:
        for hour in day["hourly"]:
            assert hour["soc"] >= 6600 - 1e-6

    windows = client.get(f"/runs/{rid}/stress-windows").json()
    assert len(windows) == 1
    assert windows[0]["days"] == 3

    pkg = client.post(f"/runs/{rid}/decision-package").json()
    assert "reduction in peak severity" in pkg["annotation"]
    assert pkg["payload"]["summary"]["severity_reduction"] > 0
    assert pkg["payload"]["code_version"]  # provenance tag present


def test_stress_windows_endpoint_carries_component3_fields(client: TestClient):
    sid = client.post("/scenarios", json=_scenario_body()).json()["id"]
    run = client.post(f"/scenarios/{sid}/runs", json={"days": _days()})
    rid = run.json()["id"]

    windows = client.get(f"/runs/{rid}/stress-windows").json()
    w = windows[0]
    expected_keys = {
        "start",
        "end",
        "days",
        "first_hour_index",
        "last_hour_index",
        "peak_hourly_load_mw",
        "threshold_mwh",
        "severity_percentile",
    }
    assert expected_keys <= w.keys()
    assert w["first_hour_index"] == 0
    assert w["last_hour_index"] == 71
    assert w["severity_percentile"] == 0.5
    # Phase 7: the API path now detects on the integer-percentile comparison,
    # which derives no MWh cut value, so threshold_mwh stays None (see the
    # models.StressWindow docstring).
    assert w["threshold_mwh"] is None
    assert w["peak_hourly_load_mw"] == max(
        h for day in _days() for h in day["hourly_load_mw"]
    )


def test_run_against_missing_scenario_404(client: TestClient):
    assert client.post("/scenarios/999/runs", json={"days": _days()}).status_code == 404


def test_bad_day_length_rejected_422(client: TestClient):
    sid = client.post("/scenarios", json=_scenario_body()).json()["id"]
    bad = [{"date": "2026-01-10", "hourly_load_mw": [1.0] * 12}]  # not 24 hours
    assert client.post(f"/scenarios/{sid}/runs", json={"days": bad}).status_code == 422


def test_starting_soc_out_of_bounds_returns_422(client: TestClient):
    sid = client.post("/scenarios", json=_scenario_body()).json()["id"]
    r = client.post(f"/scenarios/{sid}/runs", json={"days": _days(), "starting_soc": 999999})
    assert r.status_code == 422


def test_run_with_an_impossible_floor_is_rejected_not_silently_zero(client: TestClient):
    # F4's own repro, inverted: a scenario whose fractions sum above 1.0 built a
    # StorageAsset with no validation and returned status "succeeded" with
    # severity_reduction 0.0. Now the scenario POST still succeeds (out of scope,
    # see plan section 1), but the run fails loud. `client` builds a fresh
    # InMemoryRepository per test, so this is the run created and its id is 1.
    body = _scenario_body()
    body["soc_floor_frac"] = 0.9
    body["strategic_reserve_frac"] = 0.9
    sid = client.post("/scenarios", json=body).json()["id"]
    run = client.post(f"/scenarios/{sid}/runs", json={"days": _days()})
    assert run.status_code == 422
    assert client.get("/runs/1").json()["status"] == "failed"


def test_annotation_states_the_floor_position_from_the_result(client: TestClient):
    sid = client.post("/scenarios", json=_scenario_body()).json()["id"]
    run = client.post(f"/scenarios/{sid}/runs", json={"days": _days()})
    rid = run.json()["id"]
    pkg = client.post(f"/runs/{rid}/decision-package").json()
    assert "above its protected floor of" in pkg["annotation"]
    assert "min_soc_mwh" in pkg["payload"]["summary"]


def test_annotation_says_below_when_the_run_ends_under_the_floor(client: TestClient):
    # F6: reachable without F1. storage_start_mwh (100) sits under the default
    # fractions' floor (0.20 + 0.10 = 0.30 of 1000 = 300 MWh), so the reserve can
    # never discharge and ends under the floor.
    body = _scenario_body()
    del body["soc_floor_frac"]
    del body["strategic_reserve_frac"]
    body["storage_total_mwh"] = 1000
    body["storage_start_mwh"] = 100
    sid = client.post("/scenarios", json=body).json()["id"]
    run = client.post(f"/scenarios/{sid}/runs", json={"days": _days()})
    rid = run.json()["id"]
    pkg = client.post(f"/runs/{rid}/decision-package").json()
    assert "below its protected floor" in pkg["annotation"]


def test_scenario_wind_multiplier_scales_the_run(client: TestClient):
    body = _scenario_body()
    # Leave room below capacity to charge, so surplus wind has somewhere to go.
    body["storage_start_mwh"] = 10000
    body["wind_generation_multiplier"] = 1.0
    sid_default = client.post("/scenarios", json=body).json()["id"]
    run_default = client.post(f"/scenarios/{sid_default}/runs", json={"days": _days()})
    assert run_default.status_code == 201
    rid_default = run_default.json()["id"]
    default_results = client.get(f"/runs/{rid_default}/results").json()

    body["wind_generation_multiplier"] = 50.0
    sid_scaled = client.post("/scenarios", json=body).json()["id"]
    run_scaled = client.post(f"/scenarios/{sid_scaled}/runs", json={"days": _days()})
    assert run_scaled.status_code == 201
    rid_scaled = run_scaled.json()["id"]
    scaled_results = client.get(f"/runs/{rid_scaled}/results").json()

    # Higher wind lets the reserve recharge more, so at least one hour's SoC
    # differs between the default and the scaled run.
    default_soc = [h["soc"] for d in default_results["daily"] for h in d["hourly"]]
    scaled_soc = [h["soc"] for d in scaled_results["daily"] for h in d["hourly"]]
    assert default_soc != scaled_soc


def test_wind_multiplier_rejects_inf_on_the_wire(client: TestClient):
    import json as json_lib

    body = _scenario_body()
    body["wind_generation_multiplier"] = "__INF__"
    raw = json_lib.dumps(body).replace('"__INF__"', "Infinity")
    r = client.post("/scenarios", content=raw, headers={"content-type": "application/json"})
    assert r.status_code == 422
