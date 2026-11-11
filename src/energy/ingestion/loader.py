"""Couche RAW : chargement des fichiers sources tels quels, avec métadonnées d'ingestion."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone

import pandas as pd

from .. import config


def read_sources(raw_dir=None) -> dict:
    raw_dir = raw_dir or config.RAW_DIR
    weather = json.loads((raw_dir / "weather_daily.json").read_text(encoding="utf-8"))["records"]
    return {
        "consumption": pd.read_csv(raw_dir / "consumption_hourly.csv", dtype={"region_code": str}),
        "weather": pd.DataFrame(weather).astype({"region_code": str}),
        "regions": pd.read_csv(raw_dir / "regions.csv", dtype={"region_code": str}),
    }


def load_raw(conn: sqlite3.Connection, sources: dict) -> dict:
    """Écrit chaque source dans une table raw_* et trace le lot dans meta_ingestion."""
    batch_id = uuid.uuid4().hex[:12]
    loaded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    counts = {}
    for name, df in sources.items():
        out = df.copy()
        out["_batch_id"] = batch_id
        out["_ingested_at"] = loaded_at
        out.to_sql(f"raw_{name}", conn, if_exists="replace", index=False)
        counts[name] = len(out)

    conn.execute(
        """CREATE TABLE IF NOT EXISTS meta_ingestion (
               batch_id TEXT, source TEXT, row_count INTEGER, ingested_at TEXT)"""
    )
    conn.executemany(
        "INSERT INTO meta_ingestion VALUES (?, ?, ?, ?)",
        [(batch_id, name, n, loaded_at) for name, n in counts.items()],
    )
    conn.commit()
    return {"batch_id": batch_id, "rows": counts}
