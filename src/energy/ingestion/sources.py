"""Simulation des sources de données externes.

Trois sources aux formats différents, comme en entreprise :
- consommation électrique horaire par région (CSV, façon RTE éCO2mix) ;
- météo journalière par région (JSON, façon API météo) ;
- référentiel des régions (CSV).

Des défauts réalistes sont injectés : trous de mesure, doublons, valeurs négatives,
pics aberrants, codes région manquants, températures en Fahrenheit…
"""
import json

import numpy as np
import pandas as pd

from .. import config


def _hourly_index() -> pd.DatetimeIndex:
    return pd.date_range(config.START, config.END, freq=pd.Timedelta(hours=1))


def simulate_weather(rng: np.random.Generator) -> pd.DataFrame:
    days = pd.date_range(config.START[:10], config.END[:10], freq="D")
    doy = days.dayofyear.values
    rows = []
    for code, _, _, t_mean in config.REGIONS:
        seasonal = t_mean - 8.5 * np.cos(2 * np.pi * (doy - 15) / 365.25)
        noise = np.zeros(len(days))
        for i in range(1, len(days)):  # bruit autocorrélé : vagues de froid / de chaleur
            noise[i] = 0.8 * noise[i - 1] + rng.normal(0, 1.6)
        temp = seasonal + noise
        rows.append(
            pd.DataFrame(
                {
                    "region_code": code,
                    "date": days.strftime("%Y-%m-%d"),
                    "temp_mean_c": temp.round(1),
                    "temp_min_c": (temp - rng.uniform(3, 7, len(days))).round(1),
                    "temp_max_c": (temp + rng.uniform(3, 8, len(days))).round(1),
                    "cloud_cover_pct": rng.integers(0, 101, len(days)),
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


def simulate_consumption(rng: np.random.Generator, weather: pd.DataFrame) -> pd.DataFrame:
    idx = _hourly_index()
    hour = idx.hour.values
    dow = idx.dayofweek.values
    years = (idx - idx[0]).days.values / 365.25
    holidays = np.isin(idx.strftime("%Y-%m-%d"), config.HOLIDAYS)

    # Profil journalier à deux pointes (matin et soir)
    daily_shape = 0.82 + 0.12 * np.exp(-((hour - 9) ** 2) / 8) + 0.18 * np.exp(-((hour - 19) ** 2) / 6) \
        - 0.10 * np.exp(-((hour - 4) ** 2) / 6)
    calendar = np.where(dow >= 5, 0.88, 1.0) * np.where(holidays, 0.86, 1.0)
    trend = 1 - 0.012 * years  # sobriété énergétique

    frames = []
    w = weather.set_index(["region_code", "date"])["temp_mean_c"]
    day_str = idx.strftime("%Y-%m-%d")
    for code, _, base, _ in config.REGIONS:
        temp = w.loc[code].reindex(day_str).values
        temp_hourly = temp + 3.5 * np.sin(2 * np.pi * (hour - 9) / 24)
        heating = 0.028 * np.clip(15 - temp_hourly, 0, None)   # chauffage électrique
        cooling = 0.012 * np.clip(temp_hourly - 24, 0, None)   # climatisation
        load = base * daily_shape * calendar * trend * (1 + heating + cooling)
        load *= rng.normal(1, 0.015, len(idx))
        frames.append(pd.DataFrame({"region_code": code, "datetime": idx, "consumption_mw": load.round(1)}))
    return pd.concat(frames, ignore_index=True)


def inject_defects(rng: np.random.Generator, conso: pd.DataFrame, weather: pd.DataFrame):
    conso = conso.copy()
    weather = weather.copy()
    n = len(conso)

    # 1. Trous de mesure : quelques heures manquantes
    conso = conso.drop(index=rng.choice(n, size=300, replace=False))
    # 2. Valeurs négatives et pics x10 (erreurs de capteur)
    i = rng.choice(conso.index, size=40, replace=False)
    conso.loc[i, "consumption_mw"] *= -1
    i = rng.choice(conso.index, size=25, replace=False)
    conso.loc[i, "consumption_mw"] *= 10
    # 3. Codes région manquants
    conso["region_code"] = conso["region_code"].astype(object)
    i = rng.choice(conso.index, size=30, replace=False)
    conso.loc[i, "region_code"] = None
    # 4. Doublons (double envoi de fichiers)
    conso = pd.concat([conso, conso.sample(n=500, random_state=1)])
    # 5. Format d'horodatage hétérogène
    conso["datetime"] = pd.to_datetime(conso["datetime"]).dt.strftime("%Y-%m-%dT%H:%M:%S")

    # Météo : températures manquantes et une station qui renvoie des °F en mars 2024
    weather["temp_mean_c"] = weather["temp_mean_c"].astype(object)
    i = rng.choice(len(weather), size=20, replace=False)
    weather.loc[i, "temp_mean_c"] = None
    mask = (weather["region_code"] == "53") & weather["date"].str.startswith("2024-03")
    weather.loc[mask, "temp_mean_c"] = (weather.loc[mask, "temp_mean_c"].astype(float) * 9 / 5 + 32).round(1)
    return conso.sample(frac=1, random_state=2).reset_index(drop=True), weather


def generate_sources(seed: int = config.SEED) -> dict:
    rng = np.random.default_rng(seed)
    weather = simulate_weather(rng)
    conso = simulate_consumption(rng, weather)
    conso, weather = inject_defects(rng, conso, weather)
    regions = pd.DataFrame(config.REGIONS, columns=["region_code", "region_name", "base_load_mw", "avg_temp_c"])
    return {"consumption": conso, "weather": weather, "regions": regions[["region_code", "region_name"]]}


def write_sources(sources: dict, raw_dir=None) -> list:
    raw_dir = raw_dir or config.RAW_DIR
    raw_dir.mkdir(parents=True, exist_ok=True)
    paths = [raw_dir / "consumption_hourly.csv", raw_dir / "weather_daily.json", raw_dir / "regions.csv"]
    sources["consumption"].to_csv(paths[0], index=False)
    records = sources["weather"].to_dict(orient="records")
    paths[1].write_text(json.dumps({"source": "meteo-api-simulee", "records": records}, ensure_ascii=False),
                        encoding="utf-8")
    sources["regions"].to_csv(paths[2], index=False)
    return paths
