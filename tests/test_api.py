import pytest
from fastapi.testclient import TestClient

from energy.api.main import app


@pytest.fixture
def client(warehouse, monkeypatch):
    monkeypatch.setenv("ENERGY_DB", str(warehouse["db"]))
    return TestClient(app)


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["last_pipeline_run"]["failed_tasks"] == 0


def test_regions(client):
    regions = client.get("/regions").json()
    assert len(regions) == 12
    assert {"region_code": "11", "region_name": "Île-de-France"} in regions


def test_region_daily_and_errors(client):
    r = client.get("/regions/11/daily", params={"start": "2024-01-01", "end": "2024-01-07"})
    assert r.status_code == 200 and len(r.json()) == 7
    assert client.get("/regions/99/daily").status_code == 404
    assert client.get("/regions/11/daily", params={"start": "2024-02-01", "end": "2024-01-01"}).status_code == 422


def test_kpis_and_forecast(client):
    kpis = client.get("/kpis/regions", params={"year": 2024}).json()
    assert kpis[0]["region_name"] == "Île-de-France"
    day = client.get("/forecast", params={"day": "2024-12-12"}).json()
    assert len(day) == 24
    assert client.get("/forecast", params={"day": "2024-06-01"}).status_code == 404
    assert client.get("/forecast/metrics").json()["metrics"]["modele"]["mape_pct"] > 0


def test_quality_endpoint(client):
    assert len(client.get("/quality/latest").json()) == 18


def test_missing_warehouse_returns_503(monkeypatch, tmp_path):
    monkeypatch.setenv("ENERGY_DB", str(tmp_path / "absent.db"))
    assert TestClient(app).get("/regions").status_code == 503
