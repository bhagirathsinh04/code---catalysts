"""
Loads the 8 raw CSVs, cleans them, and merges them into ONE student table.

Usage:
    from src.loader import load_data
    df = load_data()                          # one row per student
    df, log = load_data(return_log=True)      # log = list of cleaning steps (show it on the dashboard)

The cleaning log is also stored in df.attrs["cleaning_log"].
"""
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
KEY = "student_id"
SOURCES = ["students", "academic", "attendance", "lms", "engagement", "placement", "skills", "feedback"]

# columns by source (excluding student_id)
NUMERIC = {
    "academic":   ["cgpa", "avg_internal_marks", "backlogs"],
    "attendance": ["overall_attendance_pct", "last_30d_attendance_pct"],
    "lms":        ["logins_per_week", "assignment_completion_pct"],
    "engagement": ["events_attended", "clubs_joined", "hackathons", "certifications"],
    "placement":  ["aptitude_score", "coding_score", "mock_interview_score"],
    "skills":     ["technical_score", "softskill_score"],
    "feedback":   ["satisfaction_score", "faculty_rating"],
}
# valid ranges used to catch impossible values
RANGES = {
    "cgpa": (0, 10), "backlogs": (0, 20), "logins_per_week": (0, 50),
    "events_attended": (0, 100), "clubs_joined": (0, 20), "hackathons": (0, 50), "certifications": (0, 50),
}
PCT_LIKE = ["avg_internal_marks", "overall_attendance_pct", "last_30d_attendance_pct",
            "assignment_completion_pct", "aptitude_score", "coding_score", "mock_interview_score",
            "technical_score", "softskill_score", "satisfaction_score", "faculty_rating"]


def _clean_ids(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.upper()


def load_data(return_log: bool = False, read_table=None):
    log = []

    def note(msg):
        log.append(msg)

    raw = {}
    for name in SOURCES:
        if read_table is None:
            df = pd.read_csv(DATA_DIR / f"{name}.csv")
            note(f"Loaded {name}.csv: {len(df)} rows")
        else:  # e.g. src/db.py passes a function that reads a database table
            df = read_table(name)
            note(f"Loaded table {name} from database: {len(df)} rows")
        raw[name] = df

    # ---- 1. standardise student IDs, drop duplicates
    for name, df in raw.items():
        before = df[KEY].copy()
        df[KEY] = _clean_ids(df[KEY])
        fixed_ids = int((before != df[KEY]).sum())
        if fixed_ids:
            note(f"{name}: standardised {fixed_ids} student IDs (case / extra spaces)")
        dups = int(df.duplicated(subset=[KEY]).sum())
        if dups:
            df.drop_duplicates(subset=[KEY], keep="first", inplace=True)
            note(f"{name}: removed {dups} duplicate rows")

    # ---- 2. students: normalise branch
    st = raw["students"]
    before = st["branch"].copy()
    st["branch"] = st["branch"].astype(str).str.strip().str.upper()
    n = int((before != st["branch"]).sum())
    note(f"students: standardised {n} branch names (case / spaces)")
    st["name"] = st["name"].astype(str).str.strip()

    # ---- 3. attendance: "78%" strings -> numbers
    att = raw["attendance"]
    as_text = att["overall_attendance_pct"].astype(str).str.contains("%", na=False)
    if as_text.any():
        att["overall_attendance_pct"] = (att["overall_attendance_pct"].astype(str)
                                         .str.replace("%", "", regex=False).str.strip())
        note(f"attendance: converted {int(as_text.sum())} values stored as text like '78%'")

    # ---- 4. numeric conversion
    for src, cols in NUMERIC.items():
        df = raw[src]
        for c in cols:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # ---- 5. CGPA typed as a percentage (e.g. 78.4 instead of 7.84)
    ac = raw["academic"]
    pct_cgpa = ac["cgpa"] > 10
    if pct_cgpa.any():
        ac.loc[pct_cgpa, "cgpa"] = (ac.loc[pct_cgpa, "cgpa"] / 10).round(2)
        note(f"academic: corrected {int(pct_cgpa.sum())} CGPA values entered as a percentage (divided by 10)")

    # ---- 6. out-of-range values -> missing
    for src, cols in NUMERIC.items():
        df = raw[src]
        for c in cols:
            lo, hi = RANGES.get(c, (0, 100) if c in PCT_LIKE else (0, np.inf))
            bad = (df[c] < lo) | (df[c] > hi)
            if bad.any():
                df.loc[bad, c] = np.nan
                note(f"{src}.{c}: set {int(bad.sum())} impossible values to missing")

    # ---- 7. merge everything onto the students table
    merged = raw["students"].copy()
    for src in SOURCES[1:]:
        flag = f"has_{src}"
        right = raw[src].copy()
        right[flag] = True
        merged = merged.merge(right, on=KEY, how="left")
        merged[flag] = merged[flag].fillna(False).astype(bool)
        absent = int((~merged[flag]).sum())
        if absent:
            note(f"merge: {absent} students have no record in {src}.csv")
    note(f"Merged 8 sources into one table: {len(merged)} students, {merged.shape[1]} columns")

    # ---- 8. fill missing values (branch median, then overall median)
    num_cols = [c for cols in NUMERIC.values() for c in cols]
    total_missing = int(merged[num_cols].isna().sum().sum())
    merged["missing_fields"] = merged[num_cols].isna().sum(axis=1)
    for c in num_cols:
        branch_med = merged.groupby("branch")[c].transform("median")
        merged[c] = merged[c].fillna(branch_med).fillna(merged[c].median())
    note(f"Filled {total_missing} missing values with the branch median (fallback: overall median)")

    # integer-like columns
    for c in ["backlogs", "events_attended", "clubs_joined", "hackathons", "certifications"]:
        merged[c] = merged[c].round().astype(int)
    merged = merged.sort_values(KEY).reset_index(drop=True)

    merged.attrs["cleaning_log"] = log
    assert merged[KEY].is_unique, "student_id must be unique after merge"
    assert merged[num_cols].notna().all().all(), "numeric columns still have missing values"

    return (merged, log) if return_log else merged


if __name__ == "__main__":
    df, log = load_data(return_log=True)
    print("\n".join(log))
    print(df.shape)
    print(df.head(3).T)
