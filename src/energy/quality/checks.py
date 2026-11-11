"""Framework de contrôle qualité déclaratif (inspiré de dbt tests / Great Expectations).

Chaque contrôle est décrit par un dictionnaire, compilé en requête SQL qui compte les lignes
en échec. Les résultats sont historisés dans la table `dq_results`.

Sévérités :
- "warn"  : l'anomalie est tracée mais le pipeline continue (ex. profilage de la couche raw) ;
- "error" : le pipeline s'arrête (porte de qualité avant de publier les marts).
"""
import sqlite3
from datetime import datetime, timezone

from .. import config


class DataQualityError(Exception):
    """Levée quand un contrôle bloquant échoue."""


def _sql(check: dict) -> str:
    t, c, kind = check["table"], check.get("column"), check["type"]
    if kind == "not_null":
        return f"SELECT COUNT(*) FROM {t} WHERE {c} IS NULL"
    if kind == "unique":
        cols = ", ".join(check["columns"])
        return f"SELECT COALESCE(SUM(n - 1), 0) FROM (SELECT COUNT(*) AS n FROM {t} GROUP BY {cols} HAVING n > 1)"
    if kind == "range":
        lo, hi = check.get("min"), check.get("max")
        conds = ([f"{c} < {lo}"] if lo is not None else []) + ([f"{c} > {hi}"] if hi is not None else [])
        return f"SELECT COUNT(*) FROM {t} WHERE {' OR '.join(conds)}"
    if kind == "accepted_values":
        values = ", ".join(f"'{v}'" for v in check["values"])
        return f"SELECT COUNT(*) FROM {t} WHERE {c} IS NULL OR {c} NOT IN ({values})"
    if kind == "relationship":
        return (f"SELECT COUNT(*) FROM {t} WHERE {c} NOT IN "
                f"(SELECT {check['to_column']} FROM {check['to_table']})")
    if kind == "completeness":
        # nombre de lignes manquantes par rapport au volume attendu
        return f"SELECT MAX(0, {check['expected']} - COUNT(*)) FROM {t}"
    if kind == "custom":
        return check["sql"]
    raise ValueError(f"Type de contrôle inconnu : {kind}")


N_HOURS = 2 * 365 * 24 + 24  # 2023 + 2024 (année bissextile)
REGION_VALUES = config.REGION_CODES

SUITES = {
    # Profilage de la couche brute : on s'attend à trouver des défauts -> "warn"
    "raw": [
        {"name": "raw_conso_region_non_nulle", "table": "raw_consumption", "type": "not_null", "column": "region_code", "severity": "warn"},
        {"name": "raw_conso_unicite", "table": "raw_consumption", "type": "unique", "columns": ["region_code", "datetime"], "severity": "warn"},
        {"name": "raw_conso_valeurs_positives", "table": "raw_consumption", "type": "range", "column": "consumption_mw", "min": 0, "severity": "warn"},
        {"name": "raw_conso_completude", "table": "raw_consumption", "type": "custom", "severity": "warn",
         "sql": f"SELECT MAX(0, {N_HOURS * len(REGION_VALUES)} - COUNT(DISTINCT region_code || datetime)) FROM raw_consumption WHERE region_code IS NOT NULL"},
        {"name": "raw_meteo_temperature_non_nulle", "table": "raw_weather", "type": "not_null", "column": "temp_mean_c", "severity": "warn"},
        {"name": "raw_meteo_temperature_plausible", "table": "raw_weather", "type": "range", "column": "CAST(temp_mean_c AS REAL)", "min": -30, "max": 45, "severity": "warn"},
    ],
    # Porte de qualité après nettoyage -> "error"
    "staging": [
        {"name": "stg_conso_unicite", "table": "stg_consumption", "type": "unique", "columns": ["region_code", "datetime_utc"], "severity": "error"},
        {"name": "stg_conso_region_valide", "table": "stg_consumption", "type": "accepted_values", "column": "region_code", "values": REGION_VALUES, "severity": "error"},
        {"name": "stg_conso_valeurs_plausibles", "table": "stg_consumption", "type": "range", "column": "consumption_mw", "min": 0, "max": 40000, "severity": "error"},
        {"name": "stg_meteo_temperature_plausible", "table": "stg_weather", "type": "range", "column": "temp_mean_c", "min": -30, "max": 45, "severity": "error"},
        {"name": "stg_meteo_temperature_non_nulle", "table": "stg_weather", "type": "not_null", "column": "temp_mean_c", "severity": "error"},
        {"name": "stg_quarantaine_sous_1pct", "table": "quarantine_consumption", "type": "custom", "severity": "error",
         "sql": "SELECT CASE WHEN COUNT(*) > 0.01 * (SELECT COUNT(*) FROM stg_consumption) THEN COUNT(*) ELSE 0 END FROM quarantine_consumption"},
    ],
    # Contrats de données sur les marts publiés
    "marts": [
        {"name": "fct_horaire_grille_complete", "table": "fct_consumption_hourly", "type": "completeness", "expected": N_HOURS * len(REGION_VALUES), "severity": "error"},
        {"name": "fct_horaire_sans_trou", "table": "fct_consumption_hourly", "type": "not_null", "column": "consumption_mw", "severity": "error"},
        {"name": "fct_horaire_temperature", "table": "fct_consumption_hourly", "type": "not_null", "column": "temp_mean_c", "severity": "error"},
        {"name": "fct_region_reference", "table": "fct_consumption_daily", "type": "relationship", "column": "region_code", "to_table": "dim_region", "to_column": "region_code", "severity": "error"},
        {"name": "national_plage_realiste_gw", "table": "mart_national_hourly", "type": "range", "column": "consumption_mw", "min": 25000, "max": 100000, "severity": "error"},
        {"name": "imputation_sous_1pct", "table": "fct_consumption_hourly", "type": "custom", "severity": "error",
         "sql": "SELECT CASE WHEN AVG(is_imputed) > 0.01 THEN SUM(is_imputed) ELSE 0 END FROM fct_consumption_hourly"},
    ],
}


def run_suite(conn: sqlite3.Connection, suite: str, run_id: str = "manual") -> list:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS dq_results (
               run_id TEXT, suite TEXT, check_name TEXT, table_name TEXT, check_type TEXT,
               severity TEXT, failing_rows INTEGER, status TEXT, checked_at TEXT)"""
    )
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    results = []
    for check in SUITES[suite]:
        failing = int(conn.execute(_sql(check)).fetchone()[0] or 0)
        status = "PASS" if failing == 0 else ("WARN" if check["severity"] == "warn" else "FAIL")
        results.append({"check": check["name"], "table": check["table"], "type": check["type"],
                        "severity": check["severity"], "failing_rows": failing, "status": status})
    conn.executemany(
        "INSERT INTO dq_results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(run_id, suite, r["check"], r["table"], r["type"], r["severity"], r["failing_rows"], r["status"], now)
         for r in results],
    )
    conn.commit()

    failed = [r for r in results if r["status"] == "FAIL"]
    if failed:
        names = ", ".join(f"{r['check']} ({r['failing_rows']} lignes)" for r in failed)
        raise DataQualityError(f"Porte de qualité « {suite} » non franchie : {names}")
    return results
