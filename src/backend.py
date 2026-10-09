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

def _col(df, name):
    """The column, or an all-NaN Series if the data does not have it."""
    return df[name] if name in df.columns else pd.Series(np.nan, index=df.index)


def _level(points, kind):
    """Turn risk points into Low / Medium / High."""
    return pd.Series(
        np.select([points >= config.RISK_HIGH_POINTS[kind],
                   points >= config.RISK_MEDIUM_POINTS[kind]],
                  ["High", "Medium"], default="Low"),
        index=points.index)


def detect_risks(df):
    """Add the risk_* flags, academic_risk, placement_risk and risk_level.

    A missing value never raises a flag (NaN < x is False), so a student with
    missing data is not accused of being at risk; Step 4 marks such students
    as low-confidence instead.
    """
    out = df.copy()
    success, internal = _col(out, "success_score"), _col(out, "internal_avg")
    attendance, backlogs = _col(out, "attendance_pct"), _col(out, "backlogs")
    cgpa, tech = _col(out, "cgpa"), _col(out, "technical_skill")
    ready = _col(out, "placement_readiness")

    # --- single warning-sign flags (0/1), kept for the dashboard
    out["risk_low_success"] = (success < config.THRESHOLD_LOW_SUCCESS).astype(int)
    out["risk_attendance"] = (attendance < config.THRESHOLD_ATTENDANCE).astype(int)
    out["risk_internal"] = (internal < config.THRESHOLD_INTERNAL).astype(int)
    out["risk_backlogs"] = (backlogs >= config.THRESHOLD_BACKLOGS).astype(int)
    out["risk_placement"] = (ready < config.THRESHOLD_PLACEMENT_LOW).astype(int)

    # --- academic risk: points for each warning sign
    p = config.ACADEMIC_RISK_POINTS
    out["academic_risk_points"] = (
        p["low_success"] * out["risk_low_success"]
        + p["low_internal"] * out["risk_internal"]
        + p["backlogs"] * out["risk_backlogs"]
        + p["low_attendance"] * out["risk_attendance"]
        + p["low_cgpa"] * (cgpa < config.CGPA_WEAK).astype(int))
    out["academic_risk"] = _level(out["academic_risk_points"], "academic")

    # --- placement risk: readiness first, then eligibility problems
    q = config.PLACEMENT_RISK_POINTS
    very_low = ready < config.PLACEMENT_VERY_LOW
    low = (ready >= config.PLACEMENT_VERY_LOW) & (ready < config.PLACEMENT_LOW)
    out["placement_risk_points"] = (
        q["readiness_very_low"] * very_low.astype(int)
        + q["readiness_low"] * low.astype(int)
        + q["backlogs"] * out["risk_backlogs"]
        + q["low_cgpa"] * (cgpa < config.CGPA_ELIGIBLE).astype(int)
        + q["weak_technical"] * (tech < config.TECHNICAL_WEAK).astype(int))
    out["placement_risk"] = _level(out["placement_risk_points"], "placement")

    # --- old single column = the worse of the two
    rank = {name: i for i, name in enumerate(config.RISK_LEVELS)}
    worst = np.maximum(out["academic_risk"].map(rank), out["placement_risk"].map(rank))
    out["risk_level"] = worst.map(dict(enumerate(config.RISK_LEVELS)))
    return out


def assign_segments(df):
    """Add the segment column. The first matching rule wins (order = config.SEGMENTS).

    We tried KMeans first, but this data has no natural clusters (silhouette
    about 0.18) and the groups only said "high / medium / low overall", so
    we use plain rules that each lead to a clear action.
    """
    out = df.copy()
    success, ready = _col(out, "success_score"), _col(out, "placement_readiness")
    attendance = _col(out, "attendance_pct")
    lms, engagement = _col(out, "score_lms"), _col(out, "score_engagement")
    academic_high = _col(out, "academic_risk") == "High"
    names = config.SEGMENTS
    rules = [
        academic_high,
        (success >= config.SEG_GOOD_MARKS) & (ready < config.SEG_LOW_PLACEMENT),
        (success >= config.SEG_HIGH_SUCCESS) & (ready >= config.SEG_HIGH_PLACEMENT),
        (attendance < config.THRESHOLD_ATTENDANCE)
        | ((lms < config.SEG_LOW_LMS) & (engagement < config.SEG_LOW_ENGAGEMENT)),
    ]
    out["segment"] = np.select(rules, names[:-1], default=names[-1])
    return out


def _num(row, name):
    """A number from the row, or None if it is missing."""
    value = row.get(name) if hasattr(row, "get") else None
    return None if value is None or pd.isna(value) else float(value)


# plain-English advice for the weakest placement test
_PLACEMENT_TIPS = {
    "aptitude": "aptitude and reasoning practice",
    "coding": "coding practice",
    "mock_interview": "mock interviews",
}


def get_recommendations(row):
    """Return a short action text for one student (one row of the table).

    Picks the student's biggest problems, most urgent first, and quotes their
    own numbers. At most MAX_ACTIONS actions are shown.
    """
    key_fields = ("success_score", "attendance_pct", "internal_avg",
                  "backlogs", "placement_readiness")
    if all(_num(row, c) is None for c in key_fields):
        return "Not enough data to make a recommendation. Check this student's records."

    actions = []  # (urgency, text); a smaller urgency number is more urgent

    backlogs = _num(row, "backlogs")
    if backlogs is not None and backlogs >= config.THRESHOLD_BACKLOGS:
        actions.append((1, f"Make a plan to clear {int(backlogs)} backlogs "
                           "(they also block many campus placements)."))

    success = _num(row, "success_score")
    if row.get("academic_risk") == "High" and success is not None:
        actions.append((2, f"Weekly mentor meetings (success score {success:.0f})."))

    internal = _num(row, "internal_avg")
    if internal is not None and internal < config.THRESHOLD_INTERNAL:
        actions.append((3, f"Extra help for internal exams (average {internal:.0f}%)."))

    attendance = _num(row, "attendance_pct")
    recent = _num(row, "last_30d_attendance_pct")
    if attendance is not None and attendance < config.THRESHOLD_ATTENDANCE:
        text = f"Attendance counselling (attendance {attendance:.0f}%"
        if recent is not None and recent < attendance - 10:
            text += f", only {recent:.0f}% in the last 30 days"
        actions.append((4, text + ")."))

    ready = _num(row, "placement_readiness")
    if ready is not None and (row.get("placement_risk") in ("High", "Medium")
                              or ready < config.SEG_LOW_PLACEMENT):
        tests = {c: _num(row, c) for c in config.PLACEMENT_COLUMNS}
        tests = {c: v for c, v in tests.items() if v is not None}
        weakest = min(tests, key=tests.get) if tests else None
        text = f"Placement preparation (readiness {ready:.0f})"
        if weakest:
            text += f", start with {_PLACEMENT_TIPS.get(weakest, weakest)}"
        urgency = 2 if row.get("placement_risk") == "High" else 5
        actions.append((urgency, text + "."))

    lms, engagement = _num(row, "score_lms"), _num(row, "score_engagement")
    if lms is not None and engagement is not None \
            and lms < config.SEG_LOW_LMS and engagement < config.SEG_LOW_ENGAGEMENT:
        actions.append((6, "Encourage LMS use and joining a club or event."))

    if not actions:
        if row.get("segment") == config.SEGMENTS[2]:
            return "On track and placement-ready. Encourage company drives or a leadership role."
        return "On track. No action needed; keep monitoring."

    actions.sort(key=lambda a: a[0])
    texts = [t for _, t in actions[:config.MAX_ACTIONS]]
    level = row.get("risk_level")
    prefix = "High priority. " if level == "High" else ""
    return prefix + " ".join(texts)