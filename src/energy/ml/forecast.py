"""Prévision J+1 de la consommation nationale horaire.

Cadre réaliste « day-ahead » : pour prévoir l'heure h du jour J, on ne dispose que de
l'historique jusqu'à J-1 (décalages >= 24 h) et de la prévision météo du jour J.

Le modèle (gradient boosting) est comparé à deux références naïves :
- même heure la veille (lag 24 h) ;
- même heure la semaine précédente (lag 168 h).
"""
import json
import sqlite3
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance

from .. import config

FEATURES = [
    "hour", "weekday", "month", "is_weekend", "is_holiday",
    "temp_weighted_c", "hdd", "temp_delta_24h",
    "lag_24h", "lag_48h", "lag_168h", "mean_same_hour_7d",
]


def load_series(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query(
        "SELECT datetime_utc, hour, weekday, month, is_weekend, is_holiday, consumption_mw, temp_weighted_c "
        "FROM mart_national_hourly ORDER BY datetime_utc",
        conn,
        parse_dates=["datetime_utc"],
    )
    return df.set_index("datetime_utc")


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    y = out["consumption_mw"]
    out["hdd"] = (15 - out["temp_weighted_c"]).clip(lower=0)
    out["temp_delta_24h"] = out["temp_weighted_c"] - out["temp_weighted_c"].shift(24)
    out["lag_24h"] = y.shift(24)
    out["lag_48h"] = y.shift(48)
    out["lag_168h"] = y.shift(168)
    out["mean_same_hour_7d"] = sum(y.shift(24 * k) for k in range(1, 8)) / 7
    return out.dropna()


def _metrics(y_true, y_pred) -> dict:
    err = np.asarray(y_pred) - np.asarray(y_true)
    return {
        "mape_pct": round(float(np.mean(np.abs(err) / y_true) * 100), 2),
        "mae_mw": round(float(np.mean(np.abs(err))), 0),
        "rmse_mw": round(float(np.sqrt(np.mean(err ** 2))), 0),
    }


def train_and_evaluate(conn: sqlite3.Connection, model_dir=None) -> dict:
    model_dir = model_dir or config.WAREHOUSE_DIR
    data = build_features(load_series(conn))
    train = data[data.index < config.FORECAST_TEST_START]
    test = data[data.index >= config.FORECAST_TEST_START]

    model = HistGradientBoostingRegressor(
        max_iter=400, learning_rate=0.06, max_leaf_nodes=31, l2_regularization=1.0, random_state=config.SEED
    )
    model.fit(train[FEATURES], train["consumption_mw"])
    pred = model.predict(test[FEATURES])

    results = {
        "modele": _metrics(test["consumption_mw"], pred),
        "naif_veille": _metrics(test["consumption_mw"], test["lag_24h"]),
        "naif_semaine": _metrics(test["consumption_mw"], test["lag_168h"]),
    }
    gain = 100 * (1 - results["modele"]["mape_pct"] / results["naif_veille"]["mape_pct"])

    sample = test.sample(n=min(2000, len(test)), random_state=config.SEED)
    imp = permutation_importance(model, sample[FEATURES], sample["consumption_mw"],
                                 n_repeats=5, random_state=config.SEED, scoring="neg_mean_absolute_error")
    importance = (pd.DataFrame({"feature": FEATURES, "importance_mw": imp.importances_mean})
                  .sort_values("importance_mw", ascending=False).round(0))

    forecast = pd.DataFrame({
        "datetime_utc": test.index.strftime("%Y-%m-%d %H:%M:%S"),
        "actual_mw": test["consumption_mw"].values,
        "forecast_mw": pred.round(0),
        "naive_lag24_mw": test["lag_24h"].values,
    })
    forecast.to_sql("mart_forecast", conn, if_exists="replace", index=False)

    run = {
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": "HistGradientBoostingRegressor",
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "test_period": f"{test.index.min():%Y-%m-%d} -> {test.index.max():%Y-%m-%d}",
        "metrics": results,
        "gain_vs_naive_pct": round(float(gain), 1),
    }
    conn.execute("CREATE TABLE IF NOT EXISTS meta_model_runs (trained_at TEXT, payload TEXT)")
    conn.execute("INSERT INTO meta_model_runs VALUES (?, ?)", (run["trained_at"], json.dumps(run)))
    conn.commit()

    joblib.dump({"model": model, "features": FEATURES}, model_dir / "forecast_model.joblib")
    run["importance"] = importance
    return run
