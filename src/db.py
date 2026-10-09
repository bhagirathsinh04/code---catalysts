"""Database entry point used by app.py:  from src.db import load_data

Reads the 8 tables from data/campus.db (SQLite) and sends them through the
SAME cleaning and merging code as the CSV version (src/loader.py), so the
output is identical: 500 rows, 31 columns.

If data/campus.db does not exist yet (for example on a fresh deployment),
it is built from the CSVs automatically.
"""
import sqlite3

import pandas as pd

from src import loader
from scripts.build_db import DB_PATH, build_db


def _read_table(name: str) -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(f"SELECT * FROM {name}", conn)


def load_data(return_log: bool = False):
    if not DB_PATH.exists():
        build_db()
    return loader.load_data(return_log=return_log, read_table=_read_table)


if __name__ == "__main__":
    df, log = load_data(return_log=True)
    print("\n".join(log))
    print(df.shape)
