"""Mini-orchestrateur (inspiré d'Airflow) : DAG de tâches, tri topologique, reprises
automatiques, journalisation et historisation des exécutions dans `meta_pipeline_runs`."""
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List

log = logging.getLogger("energy.pipeline")


@dataclass
class Task:
    name: str
    fn: Callable[[dict], object]
    upstream: List[str] = field(default_factory=list)
    retries: int = 0


class DAG:
    def __init__(self, name: str):
        self.name = name
        self.tasks: Dict[str, Task] = {}

    def task(self, name: str, upstream=None, retries: int = 0):
        def decorator(fn):
            self.tasks[name] = Task(name, fn, list(upstream or []), retries)
            return fn
        return decorator

    def topological_order(self) -> List[str]:
        order, state = [], {}

        def visit(n: str):
            if state.get(n) == "done":
                return
            if state.get(n) == "visiting":
                raise ValueError(f"Cycle détecté autour de la tâche « {n} »")
            if n not in self.tasks:
                raise KeyError(f"Tâche inconnue : {n}")
            state[n] = "visiting"
            for up in self.tasks[n].upstream:
                visit(up)
            state[n] = "done"
            order.append(n)

        for name in self.tasks:
            visit(name)
        return order

    def run(self, conn: sqlite3.Connection, context: dict = None) -> dict:
        ctx = dict(context or {})
        run_id = uuid.uuid4().hex[:12]
        ctx["run_id"] = run_id
        conn.execute(
            """CREATE TABLE IF NOT EXISTS meta_pipeline_runs (
                   run_id TEXT, dag TEXT, task TEXT, status TEXT, attempts INTEGER,
                   started_at TEXT, duration_s REAL, error TEXT)"""
        )
        summary = {"run_id": run_id, "tasks": [], "status": "SUCCESS"}
        for name in self.topological_order():
            task = self.tasks[name]
            started = datetime.now(timezone.utc).isoformat(timespec="seconds")
            t0, attempts, error, status = time.perf_counter(), 0, None, "SUCCESS"
            while True:
                attempts += 1
                try:
                    log.info("▶ %s (tentative %d)", name, attempts)
                    ctx[name] = task.fn(ctx)
                    break
                except Exception as exc:  # noqa: BLE001 - on trace toute erreur de tâche
                    error = f"{type(exc).__name__}: {exc}"
                    if attempts > task.retries:
                        status = "FAILED"
                        break
                    log.warning("⟳ %s a échoué (%s), nouvelle tentative", name, error)
            duration = round(time.perf_counter() - t0, 2)
            conn.execute("INSERT INTO meta_pipeline_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         (run_id, self.name, name, status, attempts, started, duration, error))
            conn.commit()
            summary["tasks"].append({"task": name, "status": status, "attempts": attempts, "duration_s": duration})
            log.info("%s %s en %.1fs", "✔" if status == "SUCCESS" else "✘", name, duration)
            if status == "FAILED":
                summary["status"] = "FAILED"
                summary["error"] = error
                break
        summary["context"] = ctx
        return summary
