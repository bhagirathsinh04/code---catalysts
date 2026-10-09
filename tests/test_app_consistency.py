"""Checks that the dashboard's what-if code (app.py) agrees with src/backend.py.

app.py cannot be imported here (it starts Streamlit), so we copy out only the
functions we want to test. Run from the project folder:
    python tests/test_app_consistency.py
"""
import ast
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(HERE)
sys.path.insert(0, HERE)

import numpy as np
import pandas as pd

from src import config
from src.loader import load_data

COLUMNS = ["success_score", "placement_readiness", "risk_level",
           "academic_risk", "placement_risk", "segment"]


def load_app_functions(names):
    tree = ast.parse(open(os.path.join(HERE, "app.py"), encoding="utf-8").read())
    scope = {"np": np, "pd": pd, "PLACEMENT_COLUMNS": config.PLACEMENT_COLUMNS}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            exec(compile(ast.Module([node], []), "app.py", "exec"), scope)
    missing = [n for n in names if n not in scope]
    assert not missing, f"not found in app.py: {missing}"
    return scope


def test_simulate_without_changes_matches_the_table():
    app = load_app_functions({"run_backend", "simulate"})
    df = app["run_backend"](load_data().rename(columns=config.COLUMN_RENAMES))
    for sid in df["student_id"].sample(60, random_state=1):
        simulated = app["simulate"](df, sid, {})
        shown = df[df["student_id"] == sid].iloc[0]
        for col in COLUMNS:
            assert simulated[col] == shown[col], f"{sid}: {col} differs"


def test_what_if_does_not_change_the_table():
    app = load_app_functions({"run_backend", "simulate"})
    df = app["run_backend"](load_data().rename(columns=config.COLUMN_RENAMES))
    before = df.copy()
    app["simulate"](df, df["student_id"].iloc[0], {"backlogs": 0, "attendance_pct": 95})
    pd.testing.assert_frame_equal(df, before)


def test_better_attendance_never_lowers_the_score():
    app = load_app_functions({"run_backend", "simulate"})
    df = app["run_backend"](load_data().rename(columns=config.COLUMN_RENAMES))
    low = df[df["attendance_pct"] < 70]["student_id"].head(20)
    for sid in low:
        new = app["simulate"](df, sid, {"attendance_pct": 90})
        assert new["success_score"] >= df[df["student_id"] == sid]["success_score"].iloc[0]


def test_old_duplicate_logic_is_gone():
    text = open(os.path.join(HERE, "app.py"), encoding="utf-8").read()
    for old_name in ("def add_risk_flags", "def built_in_backend", "def overall_score"):
        assert old_name not in text, f"{old_name} should have been removed"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("PASS ", t.__name__)
    print(f"\n{len(tests)}/{len(tests)} tests passed")