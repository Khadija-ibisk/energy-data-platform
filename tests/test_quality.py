import sqlite3

import pytest

from energy.quality import checks


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        "CREATE TABLE t (id INTEGER, v REAL, cat TEXT);"
        "INSERT INTO t VALUES (1, 5, 'a'), (2, -1, 'b'), (2, NULL, 'z');"
        "CREATE TABLE ref (cat TEXT); INSERT INTO ref VALUES ('a'), ('b');"
    )
    return conn


@pytest.mark.parametrize("check, expected", [
    ({"table": "t", "type": "not_null", "column": "v"}, 1),
    ({"table": "t", "type": "unique", "columns": ["id"]}, 1),
    ({"table": "t", "type": "range", "column": "v", "min": 0, "max": 10}, 1),
    ({"table": "t", "type": "accepted_values", "column": "cat", "values": ["a", "b"]}, 1),
    ({"table": "t", "type": "relationship", "column": "cat", "to_table": "ref", "to_column": "cat"}, 1),
    ({"table": "t", "type": "completeness", "expected": 5}, 2),
])
def test_each_check_type_counts_failures(db, check, expected):
    assert db.execute(checks._sql(check)).fetchone()[0] == expected


def test_error_severity_blocks_the_pipeline(db, monkeypatch):
    monkeypatch.setitem(checks.SUITES, "demo", [
        {"name": "warn_only", "table": "t", "type": "not_null", "column": "v", "severity": "warn"},
        {"name": "blocking", "table": "t", "type": "range", "column": "v", "min": 0, "severity": "error"},
    ])
    with pytest.raises(checks.DataQualityError, match="blocking"):
        checks.run_suite(db, "demo", "run1")
    statuses = dict(db.execute("SELECT check_name, status FROM dq_results").fetchall())
    assert statuses == {"warn_only": "WARN", "blocking": "FAIL"}
