"""Tableau de bord HTML autonome + graphiques PNG (pour le README)."""
import base64
import html
import json
import sqlite3

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .. import config

C1, C2, C3, GREY = "#0F766E", "#F59E0B", "#6366F1", "#94A3B8"
plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                     "grid.alpha": 0.25, "font.size": 10})


def _save(fig, name):
    fig.tight_layout()
    fig.savefig(config.FIGURES_DIR / name, dpi=110)
    plt.close(fig)
    return name


def fig_daily_vs_temperature(conn):
    df = pd.read_sql_query(
        "SELECT date, SUM(consumption_mw)/24/1000 AS gw, AVG(temp_weighted_c) AS t "
        "FROM mart_national_hourly GROUP BY date ORDER BY date", conn, parse_dates=["date"])
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(df["date"], df["gw"], color=C1, lw=1.2, label="Consommation moyenne (GW)")
    ax.set_ylabel("GW")
    ax2 = ax.twinx()
    ax2.plot(df["date"], df["t"], color=C2, lw=1, alpha=0.8, label="Température pondérée (°C)")
    ax2.set_ylabel("°C")
    ax2.grid(False)
    ax2.invert_yaxis()
    ax.set_title("Consommation nationale journalière et température (axe inversé) – 2023-2024")
    fig.legend(loc="upper center", ncol=2, bbox_to_anchor=(0.5, 0.92), frameon=False)
    return _save(fig, "01_consommation_temperature.png")


def fig_thermosensitivity(conn):
    df = pd.read_sql_query(
        "SELECT date, AVG(temp_weighted_c) AS t, SUM(consumption_mw)/24/1000 AS gw, MAX(is_weekend) AS we "
        "FROM mart_national_hourly GROUP BY date", conn)
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    for we, color, label in [(0, C1, "Jours ouvrés"), (1, GREY, "Week-ends")]:
        d = df[df["we"] == we]
        ax.scatter(d["t"], d["gw"], s=10, alpha=0.6, color=color, label=label)
    cold = df[(df["t"] < 15) & (df["we"] == 0)]
    slope, intercept = np.polyfit(cold["t"], cold["gw"], 1)
    xs = np.linspace(cold["t"].min(), 15, 50)
    ax.plot(xs, slope * xs + intercept, color=C2, lw=2.5, label=f"{-slope:.1f} GW par °C en moins")
    ax.set_xlabel("Température moyenne pondérée (°C)")
    ax.set_ylabel("Consommation moyenne (GW)")
    ax.set_title("Thermosensibilité : l'effet du chauffage électrique")
    ax.legend()
    return _save(fig, "02_thermosensibilite.png")


def fig_load_profile(conn):
    df = pd.read_sql_query("SELECT weekday, hour, avg_consumption_gw FROM mart_load_profile WHERE season='Hiver'", conn)
    grid = df.pivot(index="weekday", columns="hour", values="avg_consumption_gw")
    fig, ax = plt.subplots(figsize=(11, 3.6))
    im = ax.imshow(grid.values, aspect="auto", cmap="YlOrRd")
    ax.set_yticks(range(7))
    ax.set_yticklabels(["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"])
    ax.set_xticks(range(0, 24, 2))
    ax.set_xticklabels([f"{h}h" for h in range(0, 24, 2)])
    ax.grid(False)
    fig.colorbar(im, ax=ax, label="GW")
    ax.set_title("Profil de charge moyen en hiver : la pointe de 19 h en semaine")
    return _save(fig, "03_profil_hiver.png")


def fig_forecast(conn):
    df = pd.read_sql_query("SELECT * FROM mart_forecast", conn, parse_dates=["datetime_utc"])
    zoom = df[(df["datetime_utc"] >= "2024-12-02") & (df["datetime_utc"] < "2024-12-16")]
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(zoom["datetime_utc"], zoom["actual_mw"] / 1000, color="#111827", lw=1.6, label="Réalisé")
    ax.plot(zoom["datetime_utc"], zoom["forecast_mw"] / 1000, color=C1, lw=1.6, ls="--", label="Prévision J+1 (modèle)")
    ax.plot(zoom["datetime_utc"], zoom["naive_lag24_mw"] / 1000, color=GREY, lw=1, alpha=0.8, label="Référence naïve (veille)")
    ax.set_ylabel("GW")
    ax.set_title("Prévision J+1 sur le jeu de test – zoom sur deux semaines de décembre 2024")
    ax.legend(ncol=3, loc="upper left")
    return _save(fig, "04_prevision.png")


def fig_regions(conn):
    df = pd.read_sql_query(
        "SELECT region_name, energy_twh, thermosensitivity_mw_per_c FROM mart_region_kpis WHERE year=2024 "
        "ORDER BY energy_twh", conn)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(df["region_name"], df["energy_twh"], color=C3)
    for i, (v, s) in enumerate(zip(df["energy_twh"], df["thermosensitivity_mw_per_c"])):
        ax.text(v + 0.5, i, f"{v:.0f} TWh · {s:.0f} MW/°C", va="center", fontsize=8.5)
    ax.set_xlim(0, df["energy_twh"].max() * 1.35)
    ax.set_xlabel("TWh")
    ax.set_title("Consommation annuelle 2024 et thermosensibilité par région")
    return _save(fig, "05_regions.png")


def _img(name):
    data = base64.b64encode((config.FIGURES_DIR / name).read_bytes()).decode()
    return f'<img src="data:image/png;base64,{data}" alt="{html.escape(name)}">'


def _table(df: pd.DataFrame) -> str:
    return df.to_html(index=False, classes="tbl", border=0, na_rep="–")


def build(conn: sqlite3.Connection) -> dict:
    config.ensure_dirs()
    figures = [fig_daily_vs_temperature(conn), fig_thermosensitivity(conn), fig_load_profile(conn)]
    has_forecast = conn.execute("SELECT name FROM sqlite_master WHERE name='mart_forecast'").fetchone()
    if has_forecast:
        figures.append(fig_forecast(conn))
    figures.append(fig_regions(conn))

    k = pd.read_sql_query(
        "SELECT SUM(energy_twh) AS twh, SUM(thermosensitivity_mw_per_c) AS thermo FROM mart_region_kpis WHERE year=2024",
        conn).iloc[0]
    peak = pd.read_sql_query("SELECT * FROM mart_peak_hours ORDER BY rang LIMIT 1", conn).iloc[0]
    dq = pd.read_sql_query(
        "SELECT suite, check_name AS controle, table_name AS table_cible, severity AS severite, failing_rows AS lignes_en_echec, status "
        "FROM dq_results WHERE run_id = (SELECT run_id FROM dq_results ORDER BY checked_at DESC, rowid DESC LIMIT 1)",
        conn)
    quarantine = pd.read_sql_query(
        "SELECT rejection_reason AS motif, COUNT(*) AS lignes FROM quarantine_consumption GROUP BY 1 ORDER BY 2 DESC", conn)
    model = None
    if has_forecast:
        model = json.loads(conn.execute("SELECT payload FROM meta_model_runs ORDER BY trained_at DESC LIMIT 1").fetchone()[0])

    kpis = {
        "consommation_2024_twh": round(float(k["twh"]), 1),
        "pointe_gw": float(peak["consumption_gw"]),
        "pointe_date": str(peak["datetime_utc"]),
        "thermosensibilite_gw_par_c": round(float(k["thermo"]) / 1000, 2),
        "controles_qualite": int(len(dq)),
        "lignes_en_quarantaine": int(quarantine["lignes"].sum()),
    }
    if model:
        kpis["mape_prevision_pct"] = model["metrics"]["modele"]["mape_pct"]
        kpis["gain_vs_naif_pct"] = model["gain_vs_naive_pct"]

    cards = [
        ("Consommation 2024", f"{kpis['consommation_2024_twh']:.0f} TWh", "France métropolitaine (12 régions)"),
        ("Pointe maximale", f"{kpis['pointe_gw']:.1f} GW", kpis["pointe_date"]),
        ("Thermosensibilité", f"{kpis['thermosensibilite_gw_par_c']:.1f} GW/°C", "en hiver, jours ouvrés"),
        ("Qualité des données", f"{kpis['controles_qualite']} contrôles", f"{kpis['lignes_en_quarantaine']} lignes en quarantaine"),
    ]
    if model:
        cards.append(("Prévision J+1", f"{kpis['mape_prevision_pct']:.1f} % d'erreur",
                      f"{kpis['gain_vs_naif_pct']:.0f} % de mieux que la référence naïve"))
    cards_html = "".join(f'<div class="card"><span>{a}</span><b>{b}</b><small>{c}</small></div>' for a, b, c in cards)

    model_html = ""
    if model:
        m = pd.DataFrame(model["metrics"]).T.reset_index().rename(columns={"index": "approche"})
        model_html = f"<section><h2>Modèle de prévision</h2><p>Période de test : {model['test_period']} · " \
                     f"{model['train_rows']} heures d'entraînement.</p>{_table(m)}</section>"

    page = f"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Energy Data Platform – Tableau de bord</title>
<style>
body{{margin:0;font-family:Segoe UI,Inter,Arial,sans-serif;background:#f1f5f9;color:#0f172a}}
header{{background:linear-gradient(120deg,#0f766e,#6366f1);color:#fff;padding:28px 36px}}
header p{{margin:6px 0 0;opacity:.85}} main{{max-width:1200px;margin:auto;padding:24px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px}}
.card{{background:#fff;border-radius:12px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
.card span{{font-size:13px;color:#64748b}} .card b{{display:block;font-size:24px;margin:6px 0}} .card small{{color:#94a3b8}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(520px,1fr));gap:14px;margin-top:20px}}
.grid div{{background:#fff;border-radius:12px;padding:8px}} img{{width:100%}}
section{{background:#fff;border-radius:12px;padding:16px 22px;margin-top:20px}}
.tbl{{border-collapse:collapse;width:100%;font-size:14px}} .tbl th,.tbl td{{padding:6px 10px;border-bottom:1px solid #e2e8f0;text-align:left}}
</style></head><body>
<header><h1>Energy Data Platform</h1><p>Consommation électrique régionale en France · 2023-2024</p></header>
<main><div class="cards">{cards_html}</div>
<div class="grid">{''.join(f'<div>{_img(f)}</div>' for f in figures)}</div>
{model_html}
<section><h2>Contrôles qualité du dernier run</h2>{_table(dq)}</section>
<section><h2>Quarantaine</h2>{_table(quarantine)}</section>
</main></body></html>"""
    (config.REPORTS_DIR / "dashboard.html").write_text(page, encoding="utf-8")
    (config.REPORTS_DIR / "kpis.json").write_text(json.dumps(kpis, indent=2, ensure_ascii=False), encoding="utf-8")
    return kpis
