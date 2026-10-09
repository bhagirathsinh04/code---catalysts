"""Smoke test for the backend, run on the real data.

Run from the project folder:
    python tests/smoke_test.py          (or:  python -m pytest tests -q)
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

import numpy as np
import pandas as pd

from src import config
from src.loader import load_data
from src.backend import (compute_scores, detect_risks, assign_segments,
                         get_recommendations)

SCORE_COLUMNS = ["success_score", "placement_readiness", "score_academic",
                 "score_attendance", "score_lms", "score_engagement",
                 "score_skills", "score_feedback"]
FLAG_COLUMNS = config.RISK_FLAG_COLUMNS
LEVEL_COLUMNS = ["risk_level", "academic_risk", "placement_risk"]


def load_input():
    df = load_data().reset_index(drop=True).rename(columns=config.COLUMN_RENAMES)
    if "year" not in df.columns and "semester" in df.columns:
        df["year"] = ((df["semester"] + 1) // 2).astype(int)
    return df


def run_backend(df):
    return assign_segments(detect_risks(compute_scores(df)))


# ------------------------------------------------------------------ tests
def test_config_weights_add_up():
    assert abs(sum(config.WEIGHTS_SUCCESS.values()) - 1.0) < 1e-9


def test_required_columns_present():
    out = run_backend(load_input())
    needed = (config.REQUIRED_OUTPUT_COLUMNS + SCORE_COLUMNS + FLAG_COLUMNS
              + LEVEL_COLUMNS + ["data_confidence"])
    missing = [c for c in needed if c not in out.columns]
    assert not missing, f"missing columns: {missing}"


def test_one_row_per_student_and_input_untouched():
    df = load_input()
    before = df.copy()
    out = run_backend(df)
    assert len(out) == len(df) and out["student_id"].is_unique
    pd.testing.assert_frame_equal(df, before)  # the backend must not change its input


def test_no_missing_values_in_outputs():
    out = run_backend(load_input())
    cols = SCORE_COLUMNS + FLAG_COLUMNS + LEVEL_COLUMNS + ["segment", "data_confidence"]
    nans = out[cols].isna().sum()
    assert nans.sum() == 0, f"NaN found:\n{nans[nans > 0]}"


def test_scores_between_0_and_100():
    out = run_backend(load_input())
    for c in SCORE_COLUMNS:
        assert out[c].between(0, 100).all(), f"{c} outside 0-100"


def test_flags_are_zero_or_one():
    out = run_backend(load_input())
    for c in FLAG_COLUMNS:
        assert set(out[c].unique()) <= {0, 1}, c


def test_levels_and_segments_are_valid():
    out = run_backend(load_input())
    for c in LEVEL_COLUMNS:
        assert set(out[c]) <= set(config.RISK_LEVELS), c
    assert set(out["segment"]) <= set(config.SEGMENTS)
    assert set(out["data_confidence"]) <= set(config.CONFIDENCE_LEVELS)


def test_risk_counts_are_sane():
    out = run_backend(load_input())
    n = len(out)
    for c in ("academic_risk", "placement_risk", "risk_level"):
        high = (out[c] == "High").mean()
        low = (out[c] == "Low").mean()
        assert 0.03 <= high <= 0.30, f"{c}: {high:.0%} High is not sensible"
        assert low >= 0.30, f"{c}: only {low:.0%} Low, nearly everyone is flagged"
    for c in FLAG_COLUMNS:
        assert out[c].mean() <= 0.40, f"{c} flags {out[c].mean():.0%} of students"
    shares = out["segment"].value_counts(normalize=True)
    assert shares.max() <= 0.45 and shares.min() >= 0.05, shares.to_dict()
    assert (out["data_confidence"] == "Low").mean() <= 0.15


def test_risk_levels_agree_with_each_other():
    out = run_backend(load_input())
    rank = {k: i for i, k in enumerate(config.RISK_LEVELS)}
    worst = np.maximum(out["academic_risk"].map(rank), out["placement_risk"].map(rank))
    assert (out["risk_level"].map(rank) == worst).all()
    # every "intensive support" student has High academic risk
    seg = out[out["segment"] == config.SEGMENTS[0]]
    assert (seg["academic_risk"] == "High").all()


def test_better_students_score_higher():
    out = run_backend(load_input())
    assert out["success_score"].corr(out["cgpa"]) > 0.5
    assert out["success_score"].corr(out["attendance_pct"]) > 0.3
    high = out[out["academic_risk"] == "High"]["success_score"].mean()
    low = out[out["academic_risk"] == "Low"]["success_score"].mean()
    assert low - high > 10


def test_recommendations_are_text():
    out = run_backend(load_input())
    recs = out.apply(get_recommendations, axis=1)
    assert recs.map(lambda t: isinstance(t, str) and t.strip() != "").all()
    assert not recs.str.contains("nan", case=False).any()
    assert recs.str.len().max() < 400


def test_backend_survives_missing_columns():
    df = load_input().drop(columns=["login_count", "assignment_completion",
                                    "satisfaction", "faculty_rating"])
    out = run_backend(df)
    assert out["success_score"].notna().all()
    assert out["score_lms"].isna().all() and out["score_feedback"].isna().all()
    get_recommendations(out.iloc[0])


def test_one_changed_student_changes_score_the_right_way():
    df = load_input()
    base = compute_scores(df)["success_score"]
    worse = df.copy()
    worse.loc[0, "cgpa"] = max(worse.loc[0, "cgpa"] - 2, 0)
    worse.loc[0, "backlogs"] = worse.loc[0, "backlogs"] + 2
    new = compute_scores(worse)["success_score"]
    assert new[0] < base[0]


if __name__ == "__main__":
    failed = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception as e:  # show every failure, not just the first
            failed += 1
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} tests passed")
    sys.exit(1 if failed else 0)