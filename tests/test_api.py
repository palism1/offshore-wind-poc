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
