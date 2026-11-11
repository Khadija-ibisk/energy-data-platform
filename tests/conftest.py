import sqlite3

import pytest

from energy import config, pipeline


@pytest.fixture(scope="session")
def warehouse(tmp_path_factory):
    """Exécute le pipeline complet une fois, dans un dossier temporaire isolé."""
    tmp = tmp_path_factory.mktemp("platform")
    saved = {k: getattr(config, k) for k in ("RAW_DIR", "WAREHOUSE_DIR", "REPORTS_DIR", "FIGURES_DIR", "DB_FILE")}
    config.RAW_DIR = tmp / "raw"
    config.WAREHOUSE_DIR = tmp / "warehouse"
    config.REPORTS_DIR = tmp / "reports"
    config.FIGURES_DIR = tmp / "reports" / "figures"
    config.DB_FILE = tmp / "warehouse" / "energy.db"
    try:
        summary = pipeline.run()
        yield {"summary": summary, "db": config.DB_FILE, "reports": config.REPORTS_DIR}
    finally:
        for k, v in saved.items():
            setattr(config, k, v)


@pytest.fixture
def conn(warehouse):
    c = sqlite3.connect(warehouse["db"])
    yield c
    c.close()
