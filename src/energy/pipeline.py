"""Définition du pipeline de bout en bout et point d'entrée en ligne de commande.

Usage :
    python -m energy.pipeline             # pipeline complet
    python -m energy.pipeline --skip-ml   # sans réentraîner le modèle
"""
import argparse
import logging
import sqlite3
import sys

from . import config, transform
from .ingestion import loader, sources
from .ml import forecast
from .orchestration.dag import DAG
from .quality import checks


def build_dag(skip_ml: bool = False) -> DAG:
    dag = DAG("energy_daily")

    @dag.task("extract_sources", retries=2)
    def extract(ctx):
        return [p.name for p in sources.write_sources(sources.generate_sources())]

    @dag.task("load_raw", upstream=["extract_sources"])
    def load(ctx):
        transform.load_reference_tables(ctx["conn"])
        return loader.load_raw(ctx["conn"], loader.read_sources())

    @dag.task("dq_raw", upstream=["load_raw"])
    def dq_raw(ctx):
        return checks.run_suite(ctx["conn"], "raw", ctx["run_id"])

    @dag.task("build_staging", upstream=["dq_raw"])
    def staging(ctx):
        return transform.run_layer(ctx["conn"], "staging")

    @dag.task("dq_staging", upstream=["build_staging"])
    def dq_staging(ctx):
        return checks.run_suite(ctx["conn"], "staging", ctx["run_id"])

    @dag.task("build_marts", upstream=["dq_staging"])
    def marts(ctx):
        return transform.run_layer(ctx["conn"], "marts")

    @dag.task("dq_marts", upstream=["build_marts"])
    def dq_marts(ctx):
        return checks.run_suite(ctx["conn"], "marts", ctx["run_id"])

    last = "dq_marts"
    if not skip_ml:
        @dag.task("train_forecast", upstream=["dq_marts"])
        def train(ctx):
            return forecast.train_and_evaluate(ctx["conn"])
        last = "train_forecast"

    @dag.task("build_report", upstream=[last])
    def report(ctx):
        from .reporting import dashboard  # import tardif : matplotlib n'est utile qu'ici
        return dashboard.build(ctx["conn"])

    return dag


def run(skip_ml: bool = False) -> dict:
    config.ensure_dirs()
    with sqlite3.connect(config.DB_FILE) as conn:
        summary = build_dag(skip_ml).run(conn, {"conn": conn})
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Pipeline de la plateforme de données énergie")
    parser.add_argument("--skip-ml", action="store_true", help="ne pas réentraîner le modèle de prévision")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S")

    summary = run(skip_ml=args.skip_ml)
    print(f"\nRun {summary['run_id']} : {summary['status']}")
    for t in summary["tasks"]:
        print(f"  {t['status']:<8} {t['task']:<16} {t['duration_s']:>6.1f}s")
    if summary["status"] != "SUCCESS":
        print(f"\nErreur : {summary.get('error')}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
