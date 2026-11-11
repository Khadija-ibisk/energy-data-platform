import sqlite3

import pytest

from energy.orchestration.dag import DAG


def test_topological_order_respects_dependencies():
    dag = DAG("t")
    for name, up in [("c", ["b"]), ("a", []), ("b", ["a"])]:
        dag.task(name, upstream=up)(lambda ctx: None)
    assert dag.topological_order() == ["a", "b", "c"]


def test_cycle_is_detected():
    dag = DAG("t")
    dag.task("a", upstream=["b"])(lambda ctx: None)
    dag.task("b", upstream=["a"])(lambda ctx: None)
    with pytest.raises(ValueError, match="Cycle"):
        dag.topological_order()


def test_retries_then_success_and_history():
    calls = {"n": 0}
    dag = DAG("t")

    @dag.task("flaky", retries=2)
    def flaky(ctx):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("source indisponible")
        return "ok"

    conn = sqlite3.connect(":memory:")
    summary = dag.run(conn)
    assert summary["status"] == "SUCCESS"
    assert summary["tasks"][0]["attempts"] == 3
    assert conn.execute("SELECT status FROM meta_pipeline_runs").fetchone()[0] == "SUCCESS"


def test_failure_stops_downstream_tasks():
    dag = DAG("t")
    dag.task("boom")(lambda ctx: 1 / 0)
    dag.task("after", upstream=["boom"])(lambda ctx: "jamais")
    summary = dag.run(sqlite3.connect(":memory:"))
    assert summary["status"] == "FAILED"
    assert [t["task"] for t in summary["tasks"]] == ["boom"]
    assert "ZeroDivisionError" in summary["error"]
