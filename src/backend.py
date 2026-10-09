"""Backend for CampusPulse: scores, risk flags, segments, recommendations.

app.py uses it like:  assign_segments(detect_risks(compute_scores(df)))
Input df uses the dashboard column names (department, internal_avg,
attendance_pct, login_count, ...), not the raw CSV names.
"""
import numpy as np
import pandas as pd

from src import config

def _scale_count(s):
    """0-100 using the 95th-percentile student as 100 (outliers are capped)."""
    top = s.quantile(config.COUNT_CAP_PERCENTILE)
    if pd.isna(top) or top <= 0:
        top = s.max()
    if pd.isna(top) or top <= 0:
        return s * np.nan
    return (s / top * 100).clip(0, 100)


def _mean(parts):
    return pd.concat(parts, axis=1).mean(axis=1).clip(0, 100) if parts else None


def _group_scores(df):
    """One 0-100 Series per indicator group (skipped if its columns are missing)."""
    cols = df.columns
    groups = {}

    parts = []
    if "cgpa" in cols:
        parts.append(df["cgpa"] * 10)
    if "internal_avg" in cols:
        parts.append(df["internal_avg"])
    if "backlogs" in cols:
        parts.append((100 - df["backlogs"] * config.BACKLOG_PENALTY).clip(0, 100))
    groups["academic"] = _mean(parts)

    if "attendance_pct" in cols:
        att = df["attendance_pct"]
        if "last_30d_attendance_pct" in cols:
            share = config.ATTENDANCE_RECENT_SHARE
            att = (1 - share) * att + share * df["last_30d_attendance_pct"]
        groups["attendance"] = att.clip(0, 100)

    parts = []
    if "assignment_completion" in cols:
        parts.append(df["assignment_completion"])
    if "login_count" in cols:
        parts.append(_scale_count(df["login_count"]))
    groups["lms"] = _mean(parts)

    parts = [_scale_count(df[c]) for c in
             ("events", "clubs_joined", "hackathons", "certifications") if c in cols]
    groups["engagement"] = _mean(parts)

    parts = [df[c] for c in ("technical_skill", "soft_skill") if c in cols]
    groups["skills"] = _mean(parts)

    parts = [df[c] for c in ("satisfaction", "faculty_rating") if c in cols]
    groups["feedback"] = _mean(parts)

    return {k: v for k, v in groups.items() if v is not None}


def compute_scores(df):
    """Add score_<group>, success_score and placement_readiness columns."""
    out = df.copy()
    groups = _group_scores(out)
    weights = pd.Series(config.WEIGHTS_SUCCESS, dtype=float)
    for name in weights.index:
        out[f"score_{name}"] = groups[name].round(1) if name in groups else np.nan
    comps = out[[f"score_{n}" for n in weights.index]]
    comps.columns = weights.index
    # a group with no data is skipped and the other weights are scaled up
    available = comps.notna().mul(weights, axis=1).sum(axis=1).replace(0, np.nan)
    out["success_score"] = (comps.mul(weights, axis=1).sum(axis=1, min_count=1)
                            / available).round(1)
    place = [c for c in config.PLACEMENT_COLUMNS if c in out.columns]
    out["placement_readiness"] = out[place].mean(axis=1).round(1) if place else np.nan
    return out

def detect_risks(df):
    """Add the risk_* flag columns and risk_level."""
    raise NotImplementedError


def assign_segments(df):
    """Add the segment column."""
    raise NotImplementedError


def get_recommendations(row):
    """Return a short action text for one student (one row of the table)."""
    raise NotImplementedError