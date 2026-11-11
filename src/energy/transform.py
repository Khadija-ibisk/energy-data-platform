"""Exécution des transformations SQL par couche (staging puis marts), à la manière de dbt."""
import sqlite3
import time

from . import config


def load_reference_tables(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS ref_holidays")
    conn.execute("CREATE TABLE ref_holidays (date TEXT PRIMARY KEY)")
    conn.executemany("INSERT INTO ref_holidays VALUES (?)", [(d,) for d in config.HOLIDAYS])
    conn.commit()


def run_layer(conn: sqlite3.Connection, layer: str) -> list:
    """Exécute les fichiers .sql d'une couche dans l'ordre alphabétique et renvoie les durées."""
    timings = []
    for path in sorted((config.SQL_DIR / layer).glob("*.sql")):
        t0 = time.perf_counter()
        conn.executescript(path.read_text(encoding="utf-8"))
        timings.append({"model": f"{layer}/{path.name}", "seconds": round(time.perf_counter() - t0, 2)})
    conn.commit()
    return timings


def table_counts(conn: sqlite3.Connection, prefixes=("raw_", "stg_", "quarantine_", "dim_", "fct_", "mart_")) -> dict:
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    return {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables if t.startswith(prefixes)}
