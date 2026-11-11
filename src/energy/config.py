"""Configuration centrale : chemins, période couverte, référentiel des régions."""
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
WAREHOUSE_DIR = DATA_DIR / "warehouse"
SQL_DIR = ROOT_DIR / "sql"
REPORTS_DIR = ROOT_DIR / "reports"
FIGURES_DIR = REPORTS_DIR / "figures"

DB_FILE = WAREHOUSE_DIR / "energy.db"

SEED = 7
START = "2023-01-01 00:00"
END = "2024-12-31 23:00"
FORECAST_TEST_START = "2024-11-01"

# code INSEE, nom, consommation de base (MW), température moyenne annuelle (°C)
REGIONS = [
    ("11", "Île-de-France", 7800, 12.6),
    ("84", "Auvergne-Rhône-Alpes", 7300, 11.8),
    ("75", "Nouvelle-Aquitaine", 4600, 13.4),
    ("76", "Occitanie", 4300, 14.2),
    ("32", "Hauts-de-France", 5200, 11.0),
    ("44", "Grand Est", 5100, 10.6),
    ("93", "Provence-Alpes-Côte d'Azur", 4400, 15.6),
    ("52", "Pays de la Loire", 3100, 12.6),
    ("28", "Normandie", 2900, 11.4),
    ("53", "Bretagne", 2600, 12.2),
    ("27", "Bourgogne-Franche-Comté", 2400, 11.0),
    ("24", "Centre-Val de Loire", 2000, 11.9),
]
REGION_CODES = [r[0] for r in REGIONS]

HOLIDAYS = [
    "2023-01-01", "2023-04-10", "2023-05-01", "2023-05-08", "2023-05-18", "2023-05-29", "2023-07-14",
    "2023-08-15", "2023-11-01", "2023-11-11", "2023-12-25",
    "2024-01-01", "2024-04-01", "2024-05-01", "2024-05-08", "2024-05-09", "2024-05-20", "2024-07-14",
    "2024-08-15", "2024-11-01", "2024-11-11", "2024-12-25",
]


def ensure_dirs() -> None:
    for d in (RAW_DIR, WAREHOUSE_DIR, FIGURES_DIR):
        d.mkdir(parents=True, exist_ok=True)
