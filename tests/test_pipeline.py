import json

import pandas as pd


def test_pipeline_succeeds(warehouse):
    s = warehouse["summary"]
    assert s["status"] == "SUCCESS", s.get("error")
    assert [t["task"] for t in s["tasks"]][-1] == "build_report"


def test_raw_defects_are_detected_but_published_layers_are_clean(conn):
    dq = pd.read_sql_query("SELECT suite, status FROM dq_results", conn)
    assert (dq.loc[dq.suite == "raw", "status"] == "WARN").sum() >= 4
    assert (dq.loc[dq.suite != "raw", "status"] == "PASS").all()


def test_quarantine_reasons(conn):
    reasons = dict(conn.execute(
        "SELECT rejection_reason, COUNT(*) FROM quarantine_consumption GROUP BY 1").fetchall())
    assert set(reasons) == {"region_inconnue", "valeur_negative_ou_nulle", "pic_aberrant"}


def test_fahrenheit_temperatures_are_converted(conn):
    n, max_t = conn.execute(
        "SELECT COUNT(*), MAX(temp_mean_c) FROM stg_weather WHERE temp_quality_flag='convertie_fahrenheit'"
    ).fetchone()
    assert n > 0 and max_t < 30


def test_hourly_grid_is_complete_and_gaps_are_flagged(conn):
    total, imputed = conn.execute("SELECT COUNT(*), SUM(is_imputed) FROM fct_consumption_hourly").fetchone()
    assert total == 12 * 17544
    assert 0 < imputed < 0.01 * total


def test_business_orders_of_magnitude(warehouse):
    kpis = json.loads((warehouse["reports"] / "kpis.json").read_text(encoding="utf-8"))
    assert 380 < kpis["consommation_2024_twh"] < 520       # France : ~445 TWh
    assert 1.5 < kpis["thermosensibilite_gw_par_c"] < 3.0  # France : ~2,4 GW/°C
    assert 65 < kpis["pointe_gw"] < 100


def test_forecast_beats_naive_baselines(conn):
    run = json.loads(conn.execute("SELECT payload FROM meta_model_runs ORDER BY trained_at DESC").fetchone()[0])
    m = run["metrics"]
    assert m["modele"]["mape_pct"] < m["naif_veille"]["mape_pct"]
    assert m["modele"]["mape_pct"] < m["naif_semaine"]["mape_pct"]
    assert m["modele"]["mape_pct"] < 4


def test_dashboard_is_generated(warehouse):
    page = (warehouse["reports"] / "dashboard.html").read_text(encoding="utf-8")
    assert page.count("data:image/png;base64") == 5
