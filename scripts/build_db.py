"""Build data/campus.db (SQLite) from the 8 raw CSVs in data/.

Run from the project root:   python scripts/build_db.py

Tables mirror the CSVs exactly (same table names, same columns). The raw
values are stored as-is, including the messy ones (e.g. "78%"), because the
cleaning is done by src/loader.py when the data is loaded.
"""
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "campus.db"
TABLES = ["students", "academic", "attendance", "lms", "engagement", "placement", "skills", "feedback"]


def build_db(db_path: Path = DB_PATH) -> Path:
    db_path.parent.mkdir(exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    with sqlite3.connect(db_path) as conn:
        for name in TABLES:
            df = pd.read_csv(DATA_DIR / f"{name}.csv")
            df.to_sql(name, conn, index=False)
    return db_path


if __name__ == "__main__":
    path = build_db()
    with sqlite3.connect(path) as conn:
        for name in TABLES:
            n = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            print(f"{name}: {n} rows")
    print("Built", path)
