"""API REST (FastAPI) qui expose les marts de l'entrepôt.

Lancement :  uvicorn energy.api.main:app --reload
Documentation interactive : http://localhost:8000/docs
"""
import json
import os
import sqlite3
from datetime import date
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from .. import config

app = FastAPI(
    title="Energy Data Platform API",
    description="Consommation électrique régionale en France : KPI, séries, prévisions et qualité des données.",
    version="1.0.0",
)


def db_path() -> Path:
    return Path(os.environ.get("ENERGY_DB", config.DB_FILE))


def query(sql: str, params: tuple = ()) -> List[dict]:
    path = db_path()
    if not path.exists():
        raise HTTPException(503, "Entrepôt introuvable : lancez d'abord le pipeline (python -m energy.pipeline)")
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


class Region(BaseModel):
    region_code: str
    region_name: str


class DailyPoint(BaseModel):
    date: str
    energy_mwh: float
    peak_mw: float
    temp_mean_c: Optional[float]
    heating_degree_days: float


class RegionKpi(BaseModel):
    region_name: str
    region_code: str
    year: int
    energy_twh: float
    peak_mw: float
    avg_temp_c: float
    thermosensitivity_mw_per_c: float
    evolution_pct: Optional[float]


class ForecastPoint(BaseModel):
    datetime_utc: str
    actual_mw: float
    forecast_mw: float


class QualityCheck(BaseModel):
    suite: str
    check_name: str
    table_name: str
    severity: str
    failing_rows: int
    status: str


@app.get("/health", tags=["Supervision"])
def health():
    exists = db_path().exists()
    last_run = None
    if exists:
        rows = query("SELECT run_id, MIN(started_at) AS started_at, "
                     "SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END) AS failed_tasks "
                     "FROM meta_pipeline_runs GROUP BY run_id ORDER BY started_at DESC LIMIT 1")
        last_run = rows[0] if rows else None
    return {"status": "ok" if exists else "degraded", "warehouse": exists, "last_pipeline_run": last_run}


@app.get("/regions", response_model=List[Region], tags=["Référentiel"])
def regions():
    return query("SELECT region_code, region_name FROM dim_region ORDER BY region_name")


@app.get("/regions/{region_code}/daily", response_model=List[DailyPoint], tags=["Consommation"])
def region_daily(region_code: str, start: date = Query(date(2024, 1, 1)), end: date = Query(date(2024, 12, 31))):
    if start > end:
        raise HTTPException(422, "La date de début doit précéder la date de fin")
    if not query("SELECT 1 FROM dim_region WHERE region_code = ?", (region_code,)):
        raise HTTPException(404, f"Région inconnue : {region_code}")
    return query(
        "SELECT date, energy_mwh, peak_mw, temp_mean_c, heating_degree_days FROM fct_consumption_daily "
        "WHERE region_code = ? AND date BETWEEN ? AND ? ORDER BY date",
        (region_code, start.isoformat(), end.isoformat()),
    )


@app.get("/kpis/regions", response_model=List[RegionKpi], tags=["KPI"])
def region_kpis(year: int = Query(2024, ge=2023, le=2024)):
    return query("SELECT * FROM mart_region_kpis WHERE year = ? ORDER BY energy_twh DESC", (year,))


@app.get("/kpis/peaks", tags=["KPI"])
def peaks():
    return query("SELECT * FROM mart_peak_hours ORDER BY rang")


@app.get("/forecast", response_model=List[ForecastPoint], tags=["Prévision"])
def forecast(day: date = Query(date(2024, 12, 12), description="Jour de la période de test (nov.-déc. 2024)")):
    rows = query("SELECT datetime_utc, actual_mw, forecast_mw FROM mart_forecast "
                 "WHERE substr(datetime_utc, 1, 10) = ? ORDER BY datetime_utc", (day.isoformat(),))
    if not rows:
        raise HTTPException(404, "Aucune prévision pour ce jour (période de test : 2024-11-01 au 2024-12-31)")
    return rows


@app.get("/forecast/metrics", tags=["Prévision"])
def forecast_metrics():
    rows = query("SELECT payload FROM meta_model_runs ORDER BY trained_at DESC LIMIT 1")
    if not rows:
        raise HTTPException(404, "Aucun modèle entraîné")
    return json.loads(rows[0]["payload"])


@app.get("/quality/latest", response_model=List[QualityCheck], tags=["Qualité des données"])
def quality_latest():
    return query(
        "SELECT suite, check_name, table_name, severity, failing_rows, status FROM dq_results "
        "WHERE run_id = (SELECT run_id FROM dq_results ORDER BY checked_at DESC, rowid DESC LIMIT 1)"
    )
