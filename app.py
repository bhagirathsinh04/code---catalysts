"""CampusPulse dashboard (M2 - Frontend).

This file only DISPLAYS data. Numbers come from:
  src/loader.py   -> load_data()  (M3; src/db.py also works)
  src/backend.py  -> compute_scores(), detect_risks(),
                     assign_segments(), get_recommendations()   (M1)
  (the explainable-score helpers and a built-in scoring fallback live in this file)

Order of preference: real data + M1's backend, then real data + built-in
scoring (labelled in the sidebar), then clearly-labelled DUMMY data.
"""
import html
import importlib

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="CampusPulse", page_icon="🎓", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 1.4rem; max-width: 1400px;}
.hero {background: linear-gradient(120deg, #1d4ed8 0%, #6d28d9 100%);
       border-radius: 16px; padding: 22px 28px; margin-bottom: 18px; color: #ffffff;}
.hero-title {font-size: 2rem; font-weight: 800; line-height: 1.2;}
.hero-sub {opacity: 0.92; margin-top: 4px; font-size: 1rem;}
.pill {display: inline-block; margin-top: 12px; padding: 3px 12px; border-radius: 999px;
       background: rgba(255,255,255,0.18); border: 1px solid rgba(255,255,255,0.4);
       font-size: 0.8rem; font-weight: 600;}
.kpi {background: #ffffff; border: 1px solid #e2e8f0; border-left: 6px solid #2563eb;
      border-radius: 12px; padding: 14px 16px; margin-bottom: 8px;
      box-shadow: 0 1px 3px rgba(15, 23, 42, 0.07);}
.kpi-label {font-size: 0.82rem; color: #64748b; font-weight: 600;}
.kpi-value {font-size: 1.9rem; font-weight: 800; color: #0f172a; line-height: 1.25;}
.kpi-value.small {font-size: 1.05rem; line-height: 1.7; padding-top: 6px;}
.kpi-sub {font-size: 0.78rem; color: #64748b; min-height: 1.1em;}
.stTabs [data-baseweb="tab"] {font-weight: 600;}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------- shared settings
try:  # the team's shared values live in src/config.py
    import src.config as _shared
except Exception:
    _shared = None


def _cfg(name, default):
    return getattr(_shared, name, default)


THRESHOLD_LOW_SUCCESS = _cfg("THRESHOLD_LOW_SUCCESS", 50)
THRESHOLD_ATTENDANCE = _cfg("THRESHOLD_ATTENDANCE", 75)
THRESHOLD_INTERNAL = _cfg("THRESHOLD_INTERNAL", 40)
THRESHOLD_BACKLOGS = _cfg("THRESHOLD_BACKLOGS", 2)
THRESHOLD_PLACEMENT_LOW = _cfg("THRESHOLD_PLACEMENT_LOW", 50)
PLACEMENT_COLUMNS = _cfg("PLACEMENT_COLUMNS", ["aptitude", "coding", "mock_interview"])
WEIGHTS_SUCCESS = _cfg("WEIGHTS_SUCCESS", {
    "academic": 0.35, "attendance": 0.20, "lms": 0.15,
    "engagement": 0.10, "skills": 0.10, "feedback": 0.10,
})

# Academic score loses this many points for every backlog (0 backlogs = 100).
BACKLOG_PENALTY = _cfg("BACKLOG_PENALTY", 20)

RISK_ORDER = ["Low", "Medium", "High"]
RISK_COLORS = {"Low": "#2e9e5b", "Medium": "#f0a530", "High": "#d64545"}

TABLE_COLUMNS = ["student_id", "name", "department", "year",
                 "success_score", "placement_readiness", "risk_level", "segment"]

# label -> (column, multiplier so everything is on a 0-100 scale)
INDICATORS = {
    "CGPA (x10)": ("cgpa", 10),
    "Attendance %": ("attendance_pct", 1),
    "Internal marks": ("internal_avg", 1),
    "Assignments %": ("assignment_completion", 1),
    "Aptitude": ("aptitude", 1),
    "Coding": ("coding", 1),
    "Mock interview": ("mock_interview", 1),
    "Technical skill": ("technical_skill", 1),
    "Soft skill": ("soft_skill", 1),
    "Satisfaction": ("satisfaction", 1),
}

FLAG_LABELS = {
    "risk_low_success": "Low success score",
    "risk_attendance": "Low attendance",
    "risk_internal": "Low internal marks",
    "risk_backlogs": "Too many backlogs",
    "risk_placement": "Low placement readiness",
}

FLAG_ACTIONS = {
    "risk_low_success": "meet a mentor for an academic plan",
    "risk_attendance": "attendance counselling",
    "risk_internal": "extra help for internal exams",
    "risk_backlogs": "backlog clearing plan",
    "risk_placement": "mock interviews and coding practice",
}

REQUIRED_COLUMNS = ["student_id", "name", "department", "success_score", "risk_level"]


# ---------------------------------------------------------------- explainable score
# If M1's compute_scores() adds score_academic, score_attendance, score_lms,
# score_engagement, score_skills, score_feedback (each 0-100), they are used
# directly, so the chart matches the backend exactly. Otherwise each component
# is rebuilt from the raw columns below.
LABELS = {
    "academic": "Academic",
    "attendance": "Attendance",
    "lms": "LMS activity",
    "engagement": "Engagement",
    "skills": "Skills",
    "feedback": "Feedback",
}


# ---------------------------------------------------------------- score parts
def _to_100(series):
    """Bring a rating column onto 0-100 (handles 0-1, 1-5 and 0-10 scales)."""
    top = series.max()
    if pd.isna(top):
        return series
    if top <= 1:
        return series * 100
    if top <= 5:
        return series * 20
    if top <= 10:
        return series * 10
    return series


def _pct_of_max(series):
    """Scale a count column (logins, events...) to 0-100 using the campus maximum."""
    top = series.max()
    if pd.isna(top) or top <= 0:
        return series * np.nan
    return series / top * 100


def _mean_of(parts):
    if not parts:
        return None
    return pd.concat(parts, axis=1).mean(axis=1).clip(0, 100)


def component_table(df):
    """One 0-100 column per score component (NaN when no data exists for it)."""
    comps = pd.DataFrame(index=df.index)
    for name in WEIGHTS_SUCCESS:
        ready = f"score_{name}"
        if ready in df.columns:  # M1 already computed it
            comps[name] = df[ready]
            continue

        parts = []
        if name == "academic":
            if "cgpa" in df.columns:
                parts.append(df["cgpa"] * 10)
            if "internal_avg" in df.columns:
                parts.append(_to_100(df["internal_avg"]))
            if "backlogs" in df.columns:  # 0 backlogs = 100, minus BACKLOG_PENALTY each
                parts.append((100 - df["backlogs"] * BACKLOG_PENALTY).clip(0, 100))
        elif name == "attendance":
            if "attendance_pct" in df.columns:
                parts.append(_to_100(df["attendance_pct"]))
        elif name == "lms":
            if "assignment_completion" in df.columns:
                parts.append(_to_100(df["assignment_completion"]))
            if "login_count" in df.columns:
                parts.append(_pct_of_max(df["login_count"]))
        elif name == "engagement":
            if "events" in df.columns:
                parts.append(_pct_of_max(df["events"]))
            if "certifications" in df.columns:
                parts.append(_pct_of_max(df["certifications"]))
        elif name == "skills":
            if "technical_skill" in df.columns:
                parts.append(_to_100(df["technical_skill"]))
            if "soft_skill" in df.columns:
                parts.append(_to_100(df["soft_skill"]))
        elif name == "feedback":
            if "satisfaction" in df.columns:
                parts.append(_to_100(df["satisfaction"]))

        result = _mean_of(parts)
        comps[name] = result if result is not None else np.nan
    return comps


def contributions(df):
    """Points each component adds to the 0-100 Success Score.

    Weights are re-scaled over the components that have data, so a missing
    component never drags a student down.
    """
    weights = pd.Series(WEIGHTS_SUCCESS, dtype=float)
    weights = weights / weights.sum()
    comps = component_table(df)[list(weights.index)]
    available = comps.notna().mul(weights, axis=1).sum(axis=1).replace(0, np.nan)
    return comps.mul(weights, axis=1).div(available, axis=0)


def overall_score(df):
    """Success Score on a 0-100 scale (used for the dummy data)."""
    return contributions(df).sum(axis=1, min_count=1).round(1)


# ---------------------------------------------------------------- per student
def driver_table(df, student_id):
    """Points per component for one student next to the campus average."""
    contrib = contributions(df)
    mine = contrib[df["student_id"] == student_id]
    columns = ["Component", "This student", "Campus average", "Difference"]
    if mine.empty:
        return pd.DataFrame(columns=columns)
    mine = mine.iloc[0]
    avg = contrib.mean()
    table = pd.DataFrame({
        "Component": [LABELS.get(k, k.title()) for k in contrib.columns],
        "This student": mine.values,
        "Campus average": avg.values,
    })
    table["Difference"] = table["This student"] - table["Campus average"]
    return table.round(1)


def driver_sentence(table):
    """One plain sentence naming the biggest strength and biggest drag."""
    t = table.dropna(subset=["This student", "Campus average"])
    if t.empty:
        return "Not enough data to explain this score."
    worst = t.loc[t["Difference"].idxmin()]
    best = t.loc[t["Difference"].idxmax()]
    parts = []
    if worst["Difference"] < -0.5:
        parts.append(f"Biggest drag: {worst['Component']} "
                     f"({worst['Difference']:+.1f} points vs campus average).")
    if best["Difference"] > 0.5:
        parts.append(f"Biggest strength: {best['Component']} "
                     f"({best['Difference']:+.1f} points vs campus average).")
    return " ".join(parts) or "This student is close to the campus average on every component."


def risk_table(row):
    """Each risk rule: the student's value, the rule, and whether it was raised."""
    rules = [
        ("Success score", "success_score", "risk_low_success", "below", THRESHOLD_LOW_SUCCESS),
        ("Attendance %", "attendance_pct", "risk_attendance", "below", THRESHOLD_ATTENDANCE),
        ("Internal marks", "internal_avg", "risk_internal", "below", THRESHOLD_INTERNAL),
        ("Backlogs", "backlogs", "risk_backlogs", "at least", THRESHOLD_BACKLOGS),
        ("Placement readiness", "placement_readiness", "risk_placement", "below",
         THRESHOLD_PLACEMENT_LOW),
    ]
    rows = []
    for label, col, flag, direction, limit in rules:
        value = row.get(col, np.nan)
        if pd.isna(value):
            shown, result = "N/A", "N/A (no data)"
        else:
            shown = f"{round(float(value), 1):g}"
            if flag in row.index and not pd.isna(row[flag]):
                raised = row[flag] == 1  # trust the backend's own flag
            else:
                raised = value < limit if direction == "below" else value >= limit
            result = "FLAGGED" if raised else "OK"
        rows.append({"Check": label, "Student value": shown,
                     "Rule": f"flag if {direction} {limit}", "Result": result})
    return pd.DataFrame(rows)


def color_result(value):
    """Red cell for a raised risk flag in the 'Why the risk flags...' table."""
    return "background-color: #fee2e2; color: #b91c1c; font-weight: 600" if value == "FLAGGED" else ""


def simulate(df, student_id, changes):
    """Re-score ONE student with edited values (what-if). Nothing is saved.

    The edited row is put back into the full table before scoring, so campus
    maximums (logins, events...) stay the same and the numbers match the app.
    """
    sim = df.drop(columns=[c for c in df.columns if c.startswith("score_")]).copy()
    idx = sim.index[sim["student_id"] == student_id][0]
    for col, value in changes.items():
        sim.loc[idx, col] = value
    sim["success_score"] = overall_score(sim)
    place = [c for c in PLACEMENT_COLUMNS if c in sim.columns]
    sim["placement_readiness"] = sim[place].mean(axis=1).round(1) if place else np.nan
    return add_risk_flags(sim).loc[idx]


# ---------------------------------------------------------------- data
def make_dummy_data(n=120):
    """Fake students with the same column names as the team contract."""
    rng = np.random.default_rng(1)

    def score(mean, sd):
        return rng.normal(mean, sd, n).clip(0, 100).round(1)

    df = pd.DataFrame({
        "student_id": [f"STU{i:03d}" for i in range(1, n + 1)],
        "name": [f"Student {i}" for i in range(1, n + 1)],
        "department": rng.choice(["CSE", "ICT", "IT"], n),
        "year": rng.choice([1, 2, 3, 4], n),
        "cgpa": rng.normal(7.2, 1.0, n).clip(4, 10).round(2),
        "internal_avg": score(65, 14),
        "backlogs": rng.choice([0, 1, 2, 3, 4], n, p=[0.6, 0.2, 0.1, 0.07, 0.03]),
        "attendance_pct": score(78, 12),
        "assignment_completion": score(70, 18),
        "aptitude": score(60, 15),
        "coding": score(58, 18),
        "mock_interview": score(60, 16),
        "technical_skill": score(62, 14),
        "soft_skill": score(64, 14),
        "satisfaction": score(70, 12),
    })
    df.loc[rng.choice(n, 6, replace=False), "coding"] = np.nan  # a few missing values

    # same weights as src/config.py, so the explanation matches the score
    df["success_score"] = overall_score(df)
    df["placement_readiness"] = df[["coding", "aptitude", "mock_interview"]].mean(axis=1).round(1)

    return add_risk_flags(df)


def add_risk_flags(df):
    """Risk flags, risk level and segment from the shared thresholds."""
    def col(name):
        return df[name] if name in df.columns else pd.Series(np.nan, index=df.index)

    df["risk_low_success"] = (col("success_score") < THRESHOLD_LOW_SUCCESS).astype(int)
    df["risk_attendance"] = (col("attendance_pct") < THRESHOLD_ATTENDANCE).astype(int)
    df["risk_internal"] = (col("internal_avg") < THRESHOLD_INTERNAL).astype(int)
    df["risk_backlogs"] = (col("backlogs") >= THRESHOLD_BACKLOGS).astype(int)
    df["risk_placement"] = (col("placement_readiness") < THRESHOLD_PLACEMENT_LOW).astype(int)
    flags = df[list(FLAG_LABELS)].sum(axis=1)
    df["risk_level"] = np.where(flags == 0, "Low", np.where(flags == 1, "Medium", "High"))

    df["segment"] = np.select(
        [
            (col("success_score") >= 60) & (col("placement_readiness") < THRESHOLD_PLACEMENT_LOW),
            col("attendance_pct") < THRESHOLD_ATTENDANCE,
            col("success_score") < THRESHOLD_LOW_SUCCESS,
        ],
        ["High marks, low placement readiness", "Attendance support needed",
         "Academic support needed"],
        default="On track",
    )
    return df


def built_in_backend(df):
    """Scores, flags and segments from src/config.py (used until src/backend.py works)."""
    df = df.copy().reset_index(drop=True)
    df["success_score"] = overall_score(df)
    place = [c for c in PLACEMENT_COLUMNS if c in df.columns]
    df["placement_readiness"] = df[place].mean(axis=1).round(1) if place else np.nan
    return add_risk_flags(df)


def find_loader():
    """Use M3's load_data(), whichever file it lives in."""
    errors = []
    for module_name in ("src.db", "src.loader"):
        try:
            return importlib.import_module(module_name).load_data
        except Exception as e:
            errors.append(f"{module_name}: {e!r}")
    raise ImportError("; ".join(errors))


COLUMN_RENAMES = {
    "branch": "department",
    "avg_internal_marks": "internal_avg",
    "overall_attendance_pct": "attendance_pct",
    "logins_per_week": "login_count",
    "assignment_completion_pct": "assignment_completion",
    "events_attended": "events",
    "aptitude_score": "aptitude",
    "coding_score": "coding",
    "mock_interview_score": "mock_interview",
    "technical_score": "technical_skill",
    "softskill_score": "soft_skill",
    "satisfaction_score": "satisfaction",
}


def standardise_columns(df):
    """Translate M3's column names into the names the dashboard uses."""
    df = df.rename(columns=COLUMN_RENAMES)
    if "year" not in df.columns and "semester" in df.columns:
        df["year"] = ((df["semester"] + 1) // 2).astype(int)  # sem 3,5,7 -> year 2,3,4
    return df


@st.cache_data
def load_dashboard_data():
    """Returns (df, source, note). source is real, partial or dummy."""
    try:
        df = standardise_columns(find_loader()().reset_index(drop=True))
    except Exception as e:  # data not ready -> show dummy data, but say so loudly
        return make_dummy_data(), "dummy", repr(e)
    try:
        from src.backend import compute_scores, detect_risks, assign_segments

        df = assign_segments(detect_risks(compute_scores(df)))
        return df, "real", ""
    except Exception as e:  # M1's backend not ready -> use the built-in scoring
        backend_note = repr(e)
    try:
        return built_in_backend(df), "partial", backend_note
    except Exception as e:
        return make_dummy_data(), "dummy", repr(e)


@st.cache_data
def load_cleaning_log():
    """The loader's list of cleaning steps (empty if there is none)."""
    try:
        return list(find_loader()(return_log=True)[1])
    except Exception:  # e.g. dummy data, or a loader without return_log
        return []


# ---------------------------------------------------------------- helpers
def na(value, digits=1):
    return "N/A" if pd.isna(value) else f"{value:.{digits}f}"


def color_risk(value):
    color = RISK_COLORS.get(value)
    return f"background-color: {color}; color: white" if color else ""


def recommendation_for(row):
    """Use M1's get_recommendations() if it works, else a simple fallback."""
    try:
        from src.backend import get_recommendations
        text = get_recommendations(row)
        if isinstance(text, str) and text.strip():
            return text
    except Exception:
        pass
    steps = [action for flag, action in FLAG_ACTIONS.items() if row.get(flag) == 1]
    if not steps:
        return "No action needed. Keep monitoring."
    return "Suggested: " + "; ".join(steps) + "."


def style_table(frame):
    styler = frame.style.format(precision=1, na_rep="N/A")
    apply_map = getattr(styler, "map", None) or styler.applymap  # pandas old/new
    if "risk_level" in frame.columns:
        styler = apply_map(color_risk, subset=["risk_level"])
    return styler

FALLING_DROP = 10  # points below overall attendance


def falling_attendance(frame, drop=FALLING_DROP):
    """Students whose last-30-day attendance is `drop`+ points below overall.
    Display only: not used in any score. Returns None if the columns are missing."""
    needed = {"attendance_pct", "last_30d_attendance_pct"}
    if not needed.issubset(frame.columns):
        return None
    out = frame.copy()
    out["attendance_drop"] = (out["attendance_pct"] - out["last_30d_attendance_pct"]).round(1)
    out = out[out["attendance_drop"] >= drop]
    return out.sort_values("attendance_drop", ascending=False)

def campus_intervention(frame_all, view, target):
    """What if every high-risk, low-attendance student in `view` reached `target`% attendance?
    Re-scores a COPY of the whole table (same rules as simulate()). Nothing stored changes."""
    if "attendance_pct" not in frame_all.columns or "risk_attendance" not in view.columns:
        return None
    ids = view.loc[(view["risk_level"] == "High") & (view["risk_attendance"] == 1), "student_id"]
    base = frame_all.drop(columns=[c for c in frame_all.columns if c.startswith("score_")]).copy()

    def rescore(table):
        table = table.copy()
        table["success_score"] = overall_score(table)
        place = [c for c in PLACEMENT_COLUMNS if c in table.columns]
        table["placement_readiness"] = table[place].mean(axis=1).round(1) if place else np.nan
        return add_risk_flags(table)

    before = rescore(base)
    changed = base.copy()
    hit = changed["student_id"].isin(ids)
    changed.loc[hit, "attendance_pct"] = changed.loc[hit, "attendance_pct"].clip(lower=target)
    after = rescore(changed)
    in_view = before["student_id"].isin(view["student_id"])
    return {
        "n": int(hit.sum()),
        "high_before": int((before.loc[in_view, "risk_level"] == "High").sum()),
        "high_after": int((after.loc[in_view, "risk_level"] == "High").sum()),
        "score_gain": float((after.loc[hit, "success_score"] - before.loc[hit, "success_score"]).mean())
                      if hit.any() else 0.0,
        "freed": int(((before.loc[hit, "risk_level"] == "High")
                      & (after.loc[hit, "risk_level"] != "High")).sum()),
    }

def student_summary(df, row, recommendation):
    """Plain-English, rule-based summary of one student (no ML). Returns text."""
    sid = row["student_id"]
    head = f"Student summary: {row.get('name', sid)} ({sid})"
    meta = [str(row[c]) for c in ("department",) if c in row.index and not pd.isna(row[c])]
    if "year" in row.index and not pd.isna(row["year"]):
        try:
            meta.append(f"Year {int(row['year'])}")
        except (TypeError, ValueError):
            meta.append(f"Year {row['year']}")
    if "segment" in row.index and not pd.isna(row["segment"]):
        meta.append(f"Segment: {row['segment']}")
    lines = [head, " | ".join(meta), ""]

    n_flags = sum(row.get(c) == 1 for c in FLAG_LABELS)
    score = row.get("success_score", np.nan)
    if pd.isna(score):
        lines.append(f"Success score: not available. Risk level: {row['risk_level']} "
                     f"({n_flags} flag(s) raised).")
    else:
        gap = score - df["success_score"].mean()
        lines.append(f"Success score: {score:.1f} out of 100 ({gap:+.1f} vs campus average). "
                     f"Risk level: {row['risk_level']} ({n_flags} flag(s) raised).")

    drivers = driver_table(df, sid).dropna(subset=["This student", "Campus average"])
    if not drivers.empty:
        drags = drivers[drivers["Difference"] < -0.5].sort_values("Difference").head(2)
        best = drivers[drivers["Difference"] > 0.5].sort_values("Difference", ascending=False).head(1)
        lines += ["", "What drives the score:"]
        for r in drags.itertuples():
            lines.append(f"- Holding the score back: {r.Component} ({r.Difference:+.1f} points vs campus average)")
        for r in best.itertuples():
            lines.append(f"- Helping the score: {r.Component} ({r.Difference:+.1f} points vs campus average)")
        if drags.empty and best.empty:
            lines.append("- Close to the campus average on every component.")

    lines += ["", "Risk flags raised:"]
    flagged = risk_table(row)
    flagged = flagged[flagged["Result"] == "FLAGGED"]
    if flagged.empty:
        lines.append("- None.")
    for _, r in flagged.iterrows():
        lines.append(f"- {r['Check']}: {r['Student value']} ({r['Rule']})")

    if {"attendance_pct", "last_30d_attendance_pct"}.issubset(row.index):
        drop = row["attendance_pct"] - row["last_30d_attendance_pct"]
        if not pd.isna(drop) and drop >= FALLING_DROP:
            lines += ["", f"Watch: attendance in the last 30 days ({row['last_30d_attendance_pct']:.1f}%) "
                          f"is {drop:.1f} points below overall ({row['attendance_pct']:.1f}%)."]

    advice = str(recommendation).strip()
    if advice.startswith("Suggested: "):
        advice = advice[len("Suggested: "):]
    lines += ["", f"Recommended action: {advice}", "",
              "This summary is a decision-support aid built from fixed rules. "
              "It does not replace a teacher's judgement."]
    return "\n".join(lines)

TRACK_STATUSES = ["Not started", "Contacted", "Counselling booked", "In progress", "Resolved"]


def tracker_pool(view, n=15):
    """Flagged students to track: High risk first, then lowest success score."""
    pool = view[view["risk_level"] != "Low"].copy()
    pool["_order"] = pool["risk_level"].map({"High": 0, "Medium": 1})
    return pool.sort_values(["_order", "success_score"]).head(n).drop(columns="_order")


def tracker_counts(tracker):
    """(students with any action, students resolved) from {student_id: status}."""
    acted = sum(1 for s in tracker.values() if s != "Not started")
    return acted, sum(1 for s in tracker.values() if s == "Resolved")


def set_track_status(student_id):
    """Selectbox callback: remember the choice in the session-only tracker."""
    st.session_state.setdefault("tracker", {})[student_id] = st.session_state[f"track_{student_id}"]


def clear_tracker():
    st.session_state["tracker"] = {}
    for key in [k for k in st.session_state if str(k).startswith("track_")]:
        del st.session_state[key]


PRIMARY = "#2563eb"
MUTED = "#94a3b8"
WHO_COLORS = {"This student": PRIMARY, "Campus average": MUTED}


def kpi(column, label, value, accent=PRIMARY, sub="", small=False):
    """A styled KPI card."""
    size = " small" if small else ""
    column.markdown(
        f'<div class="kpi" style="border-left-color:{accent}">'
        f'<div class="kpi-label">{html.escape(str(label))}</div>'
        f'<div class="kpi-value{size}">{html.escape(str(value))}</div>'
        f'<div class="kpi-sub">{html.escape(str(sub))}</div></div>',
        unsafe_allow_html=True,
    )


def show(fig):
    """Draw a chart with the same clean style everywhere."""
    fig.update_layout(template="plotly_white", legend_title_text="",
                      margin=dict(l=10, r=10, t=50, b=10),
                      font=dict(family="Segoe UI, Inter, sans-serif"),
                      title_font_size=16)
    st.plotly_chart(fig)


# ---------------------------------------------------------------- load
df, source, load_error = load_dashboard_data()

missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
if missing:
    st.error(f"The data is missing required columns: {missing}. "
             "Check src/config.py with the team.")
    st.stop()

SOURCE_PILL = {"real": "Live data", "partial": "Real data · built-in scoring",
               "dummy": "Demo data"}
st.markdown(
    '<div class="hero"><div class="hero-title">🎓 CampusPulse</div>'
    '<div class="hero-sub">Student Success Intelligence Platform: see who needs help, '
    'why, and what to do next.</div>'
    f'<span class="pill">{SOURCE_PILL[source]}</span></div>',
    unsafe_allow_html=True,
)

st.caption("**How to use:** set filters in the sidebar. Campus Overview shows who needs help first. "
           "Student Explorer opens one student, explains the score and lets you try what-if changes. "
           "Insights & Interventions groups students and exports lists.")

# ---------------------------------------------------------------- sidebar
st.sidebar.header("Filters")
if source == "dummy":
    st.sidebar.warning("Showing DUMMY data. The real data and backend are not connected yet.")
    with st.sidebar.expander("Why is it dummy?"):
        st.code(load_error)
elif source == "partial":
    st.sidebar.info("Real student data. Scores use the built-in scoring until "
                    "src/backend.py is ready.")
    with st.sidebar.expander("Why built-in scoring?"):
        st.code(load_error)
else:
    st.sidebar.success("Connected to real data")

if source != "dummy":
    with st.sidebar.expander("Data check"):
        st.caption(f"{len(df)} students, {df.shape[1]} columns. "
                   "Check that each min and max looks right.")
        st.dataframe(df.select_dtypes("number").agg(["min", "max"]).T.round(1))

departments = sorted(df["department"].dropna().unique().tolist())
sel_depts = st.sidebar.multiselect("Department", departments, default=departments)

if "year" in df.columns:
    years = sorted(df["year"].dropna().unique().tolist())
    sel_years = st.sidebar.multiselect("Year", years, default=years)
else:
    sel_years = None

sel_risk = st.sidebar.multiselect("Risk level", RISK_ORDER, default=RISK_ORDER)
score_lo, score_hi = st.sidebar.slider("Success score range", 0, 100, (0, 100))

mask = (
    df["department"].isin(sel_depts)
    & df["risk_level"].isin(sel_risk)
    & df["success_score"].between(score_lo, score_hi)
)
if sel_years is not None:
    mask &= df["year"].isin(sel_years)
f = df[mask]

if f.empty:
    st.info("No students match these filters. Try widening the filters in the sidebar.")
    st.stop()

tab_overview, tab_explorer, tab_insights = st.tabs(
    ["Campus Overview", "Student Explorer", "Insights & Interventions"]
)

# ---------------------------------------------------------------- tab 1
with tab_overview:
    c1, c2, c3, c4 = st.columns(4)
    high_n_view = int((f["risk_level"] == "High").sum())
    placement_avg = f["placement_readiness"].mean() if "placement_readiness" in f.columns else np.nan
    kpi(c1, "Total students", len(f), PRIMARY, f"of {len(df)} on campus")
    kpi(c2, "Average success score", na(f["success_score"].mean()), "#7c3aed", "scale 0 to 100")
    kpi(c3, "High-risk students", high_n_view, RISK_COLORS["High"],
        f"{high_n_view / len(f):.0%} of this view")
    kpi(c4, "Avg placement readiness", na(placement_avg), "#0d9488",
        "aptitude, coding, mock interview")

    # ---- who needs help first
    st.subheader("Top 10 students who need help first")
    urgent = f[f["risk_level"] != "Low"].copy()
    if urgent.empty:
        st.success("No Medium or High risk students in this view.")
    else:
        urgent["_order"] = urgent["risk_level"].map({"High": 0, "Medium": 1})
        top = urgent.sort_values(["_order", "success_score"]).head(10).copy()
        top["why_flagged"] = top.apply(
            lambda r: ", ".join(lbl for flag, lbl in FLAG_LABELS.items() if r.get(flag) == 1), axis=1)
        top["recommended_action"] = top.apply(recommendation_for, axis=1)
        top_cols = [c for c in ["name", "student_id", "department", "success_score", "risk_level",
                                "why_flagged", "recommended_action"] if c in top.columns]
        st.caption("High risk first, then lowest success score. Follows the sidebar filters.")
        st.dataframe(style_table(top[top_cols]), hide_index=True)

        # ---- falling-attendance watchlist (display only, not part of any score)
    st.subheader("Falling attendance watchlist")
    watch = falling_attendance(f)
    if watch is None:
        st.caption("Last-30-day attendance is not in the data, so this list is hidden.")
    elif watch.empty:
        st.success(f"No student's last-30-day attendance is {FALLING_DROP}+ points below their overall attendance.")
    else:
        watch = watch.copy()
        watch["recommended_action"] = "Call the student this week and ask what changed."
        watch_cols = [c for c in ["name", "student_id", "department", "attendance_pct",
                                  "last_30d_attendance_pct", "attendance_drop", "risk_level"]
                      if c in watch.columns]
        st.caption(f"{len(watch)} students attended {FALLING_DROP}+ points less in the last 30 days "
                   "than overall. Early warning only. This does not change any score. "
                   "Follows the sidebar filters.")
        st.dataframe(style_table(watch[watch_cols].head(15)), hide_index=True)
        st.download_button("Download watchlist (CSV)",
                           watch[watch_cols].to_csv(index=False).encode("utf-8"),
                           file_name="falling_attendance.csv", mime="text/csv")

    with st.expander("Data quality: how the data was cleaned"):
        steps = load_cleaning_log() if source != "dummy" else []
        if not steps:
            st.caption("No cleaning log available (demo data or loader without a log).")
        else:
            fixes = [s for s in steps if not s.startswith(("Loaded", "Merged"))]
            merged_line = next((s for s in steps if s.startswith("Merged")), "")
            st.markdown(f"**{len(fixes)} cleaning steps** were applied before any score was calculated. "
                        f"{merged_line}")
            for s in fixes:
                st.markdown(f"- {s}")
            st.caption("Every fix is recorded by src/loader.py, so no value was changed silently.")

    with st.expander("How is the Success Score calculated?"):
        weights = pd.DataFrame({
            "Component": [LABELS.get(k, k.title()) for k in WEIGHTS_SUCCESS],
            "Weight": [f"{v:.0%}" for v in WEIGHTS_SUCCESS.values()],
        })
        st.dataframe(weights, hide_index=True)
        st.caption("Each indicator is scaled to 0-100, then combined using these weights. "
                   "The score supports decisions; it does not replace a teacher's judgement.")

    left, right = st.columns(2)
    with left:
                fig = px.histogram(f, x="success_score", nbins=24,
                           color_discrete_sequence=[PRIMARY],
                           title="Success score distribution")
                fig.update_traces(marker_line_color="white", marker_line_width=1.5,
                          hovertemplate="Score %{x}<br>Students: %{y}<extra></extra>")
                fig.update_layout(bargap=0.05, showlegend=False,
                          xaxis_title="Success score", yaxis_title="Students")
                fig.add_vline(x=THRESHOLD_LOW_SUCCESS, line_dash="dash",
                      line_color=RISK_COLORS["High"],
                      annotation_text=f"Risk line ({THRESHOLD_LOW_SUCCESS})",
                      annotation_position="top left")
                fig.add_vline(x=f["success_score"].mean(), line_dash="dot",
                      line_color="#7c3aed",
                      annotation_text=f"Average {f['success_score'].mean():.1f}",
                      annotation_position="top right")
                show(fig)
    with right:
        counts = f.groupby(["department", "risk_level"]).size().reset_index(name="students")
        fig = px.bar(counts, x="department", y="students", color="risk_level",
                     color_discrete_map=RISK_COLORS,
                     category_orders={"risk_level": RISK_ORDER},
                     title="Risk level by department")
        show(fig)

    if "attendance_pct" in f.columns:
        fig = px.scatter(f, x="attendance_pct", y="success_score", color="risk_level",
                         color_discrete_map=RISK_COLORS,
                         category_orders={"risk_level": RISK_ORDER},
                         hover_name="name",
                         title="Attendance vs success score",
                         labels={"attendance_pct": "Attendance %",
                                 "success_score": "Success score"})
        show(fig)

# ---------------------------------------------------------------- tab 2
with tab_explorer:
    st.subheader("Student Explorer")
    query = st.text_input("Search by name or student ID")
    view = f
    if query.strip():
        q = query.strip()
        hit = (view["student_id"].astype(str).str.contains(q, case=False, regex=False, na=False)
               | view["name"].astype(str).str.contains(q, case=False, regex=False, na=False))
        view = view[hit]

    if view.empty:
        st.info("No students match your search.")
    else:
        cols = [c for c in TABLE_COLUMNS if c in view.columns]
        table = view[cols].sort_values("success_score")
        st.caption(f"{len(table)} students (lowest scores first)")
        st.dataframe(style_table(table), hide_index=True)
        st.download_button("Download this list (CSV)",
                           table.to_csv(index=False).encode("utf-8"),
                           file_name="students.csv", mime="text/csv")

        st.divider()
        st.subheader("Student detail")

        labels = {r.student_id: f"{r.student_id} - {r.name}" for r in view.itertuples()}
        ids = list(labels.keys())

        quick = st.radio(
            "Quick pick",
            ["Choose manually", "Good marks, low placement readiness", "Lowest success score"],
            horizontal=True,
        )
        default_idx = 0
        if quick == "Good marks, low placement readiness":
            if "placement_readiness" in view.columns:
                cand = view[(view["success_score"] >= 60)
                            & (view["placement_readiness"] < THRESHOLD_PLACEMENT_LOW)]
                cand = cand.sort_values("success_score", ascending=False)
            else:
                cand = view.iloc[0:0]
            if cand.empty:
                st.caption("No student matches this pattern with the current filters.")
            else:
                default_idx = ids.index(cand.iloc[0]["student_id"])
        elif quick == "Lowest success score":
            default_idx = ids.index(view.sort_values("success_score").iloc[0]["student_id"])

        chosen = st.selectbox("Select a student", ids, index=default_idx,
                              format_func=lambda sid: labels[sid])
        row = view[view["student_id"] == chosen].iloc[0]

        campus_avg = df["success_score"].mean()
        delta = None if pd.isna(row["success_score"]) else f"{row['success_score'] - campus_avg:+.1f} vs campus average"

        year_text = ""
        if "year" in row.index and not pd.isna(row["year"]):
            try:
                year_text = f" · Year {int(row['year'])}"
            except (TypeError, ValueError):
                year_text = f" · {row['year']}"
        st.markdown(f"**{row['name']}** · {row['department']}{year_text}")

        n_flags = sum(row.get(c) == 1 for c in FLAG_LABELS)
        m1, m2, m3, m4 = st.columns(4)
        kpi(m1, "Success score", na(row["success_score"]), "#7c3aed", delta or "")
        kpi(m2, "Placement readiness",
            na(row["placement_readiness"]) if "placement_readiness" in row.index else "N/A",
            "#0d9488", "aptitude, coding, mock interview")
        kpi(m3, "Risk level", str(row["risk_level"]),
            RISK_COLORS.get(str(row["risk_level"]), "#64748b"), f"{n_flags} risk flag(s) raised")
        kpi(m4, "Segment", str(row["segment"]) if "segment" in row.index else "N/A",
            PRIMARY, "group for targeted action", small=True)

        raised = [label for flag, label in FLAG_LABELS.items() if row.get(flag) == 1]
        if raised:
            st.warning("Why flagged: " + ", ".join(raised))
        else:
            st.success("No risk flags for this student.")
        st.info(recommendation_for(row))

        # ---- what-if simulator
        st.divider()
        st.subheader("What-if simulator")
        st.caption("Drag a slider to see how this student's scores and risk would change. "
                   "Nothing is saved.")
        sim_fields = [("attendance_pct", "Attendance %", 0.0, 100.0),
                      ("coding", "Coding score", 0.0, 100.0),
                      ("aptitude", "Aptitude score", 0.0, 100.0),
                      ("mock_interview", "Mock interview score", 0.0, 100.0),
                      ("internal_avg", "Internal marks", 0.0, 100.0),
                      ("backlogs", "Backlogs", 0, 10)]
        sim_fields = [x for x in sim_fields if x[0] in df.columns]
        defaults, changes = {}, {}
        slider_cols = st.columns(3)
        for i, (col, label, lo, hi) in enumerate(sim_fields):
            start = row[col] if not pd.isna(row[col]) else df[col].mean()
            key = f"sim_{chosen}_{col}"
            is_int = col == "backlogs"
            start = int(round(start)) if is_int else float(start)
            defaults[key] = start
            value = slider_cols[i % 3].slider(label, lo, hi, start,
                                              step=1 if is_int else 0.5, key=key)
            if value != start:
                changes[col] = value
        st.button("Reset sliders", on_click=lambda d: st.session_state.update(d), args=(defaults,))

        if not changes:
            st.caption("Move a slider to see the effect.")
        else:
            new = simulate(df, chosen, changes)
            s1, s2, s3 = st.columns(3)
            kpi(s1, "Simulated success score", na(new["success_score"]), "#7c3aed",
                f"{new['success_score'] - row['success_score']:+.1f} vs now")
            kpi(s2, "Simulated placement readiness", na(new["placement_readiness"]), "#0d9488",
                f"{new['placement_readiness'] - row['placement_readiness']:+.1f} vs now")
            kpi(s3, "Simulated risk level", str(new["risk_level"]),
                RISK_COLORS.get(str(new["risk_level"]), "#64748b"), f"now: {row['risk_level']}")
            cleared = [lbl for flag, lbl in FLAG_LABELS.items()
                       if row.get(flag) == 1 and new.get(flag) != 1]
            added = [lbl for flag, lbl in FLAG_LABELS.items()
                     if row.get(flag) != 1 and new.get(flag) == 1]
            if cleared:
                st.success("Flags cleared: " + ", ".join(cleared))
            if added:
                st.warning("New flags raised: " + ", ".join(added))
            if new["segment"] != row["segment"]:
                st.caption(f"Segment would change: {row['segment']} → {new['segment']}")
            st.info("Suggested action then: " + recommendation_for(new))

        # ---- explainable score: what drives this student's score and flags
        st.divider()
        st.subheader("Why this score?")
        drivers = driver_table(df, chosen)
        if drivers.empty:
            st.caption("No explanation available for this student.")
        else:
            st.markdown(f"**{driver_sentence(drivers)}**")
            shown = drivers.dropna(subset=["This student", "Campus average"])
            if not shown.empty:
                chart_data = shown.melt(id_vars="Component",
                                        value_vars=["This student", "Campus average"],
                                        var_name="Who", value_name="Points")
                fig = px.bar(chart_data, x="Points", y="Component", color="Who",
                             barmode="group", orientation="h",
                             color_discrete_map=WHO_COLORS,
                             title="Points each component adds to the success score")
                show(fig)
            no_data = drivers[drivers["This student"].isna()]["Component"].tolist()
            if no_data:
                st.caption("No data for: " + ", ".join(no_data)
                           + ". The other components are re-weighted to cover this.")

            st.markdown("**Why the risk flags were raised or not**")
            risk_view = risk_table(row)
            apply_map = getattr(risk_view.style, "map", None) or risk_view.style.applymap
            st.dataframe(apply_map(color_result, subset=["Result"]), hide_index=True,
                         column_config={"Check": st.column_config.TextColumn(width="medium"),
                                        "Student value": st.column_config.TextColumn(width="small"),
                                        "Rule": st.column_config.TextColumn(width="medium"),
                                        "Result": st.column_config.TextColumn(width="small")})

        bars, missing_labels = [], []
        for label, (col, scale) in INDICATORS.items():
            if col not in df.columns:
                continue
            if pd.isna(row[col]):
                missing_labels.append(label)
                continue
            bars.append({"Indicator": label, "Who": "This student", "Value": row[col] * scale})
            bars.append({"Indicator": label, "Who": "Campus average",
                         "Value": df[col].mean() * scale})
        if bars:
            fig = px.bar(pd.DataFrame(bars), x="Indicator", y="Value", color="Who",
                         barmode="group", color_discrete_map=WHO_COLORS,
                         title="This student vs campus average")
            fig.update_yaxes(range=[0, 100])
            show(fig)
        if missing_labels:
            st.caption("N/A (not available): " + ", ".join(missing_labels))

        # ---- plain-English summary (rule-based, with download)
        st.divider()
        st.subheader("Plain-English summary")
        summary_text = student_summary(df, row, recommendation_for(row))
        with st.container(border=True):
            st.markdown(summary_text.replace("\n", "  \n"))
        st.download_button("Download this summary (.txt)",
                           summary_text.encode("utf-8"),
                           file_name=f"summary_{chosen}.txt", mime="text/plain",
                           key=f"download_summary_{chosen}")
        st.caption("To print it, download the .txt file and print from there, "
                   "or use your browser's print (Ctrl+P).")

# ---------------------------------------------------------------- tab 3
with tab_insights:
    st.subheader("Insights")
    insights = []
    high_n = int((f["risk_level"] == "High").sum())
    insights.append(f"{high_n} of {len(f)} students ({high_n / len(f):.0%}) are high risk.")

    if "attendance_pct" in f.columns:
        low = f[f["attendance_pct"] < THRESHOLD_ATTENDANCE]["success_score"]
        ok = f[f["attendance_pct"] >= THRESHOLD_ATTENDANCE]["success_score"]
        if len(low) and len(ok):
            gap = ok.mean() - low.mean()
            word = "lower" if gap >= 0 else "higher"
            insights.append(
                f"Students with attendance below {THRESHOLD_ATTENDANCE}% score "
                f"{abs(gap):.1f} points {word} on average ({low.mean():.1f} vs {ok.mean():.1f})."
            )

    share = (f.assign(is_high=f["risk_level"] == "High")
             .groupby("department")["is_high"].mean().sort_values(ascending=False))
    insights.append(f"{share.index[0]} has the highest share of high-risk students "
                    f"({share.iloc[0]:.0%}).")

    if "placement_readiness" in f.columns:
        gap_n = int(((f["success_score"] >= 60)
                     & (f["placement_readiness"] < THRESHOLD_PLACEMENT_LOW)).sum())
        insights.append(f"{gap_n} students have good overall scores but low placement "
                        "readiness. Mock interviews and coding practice can help them.")

    for line in insights:
        st.markdown(f"- {line}")

            # ---- campus-level "what if we intervene" (display only, nothing is saved)
    st.divider()
    st.subheader("What if we intervene?")
    st.caption("Takes every high-risk student with low attendance in the current view and "
               "imagines they reach the target below. The scores are recalculated on a copy. "
               "Nothing is saved.")
    target = st.slider("Target attendance %", int(THRESHOLD_ATTENDANCE), 100,
                       int(THRESHOLD_ATTENDANCE), key="campus_target")
    result = campus_intervention(df, f, target)
    if result is None:
        st.caption("Attendance data is not available, so this box is hidden.")
    elif result["n"] == 0:
        st.info("No high-risk students with low attendance in this view.")
    else:
        i1, i2, i3 = st.columns(3)
        kpi(i1, "Students targeted", result["n"], PRIMARY, "high risk + low attendance")
        kpi(i2, "High-risk students", f"{result['high_before']} → {result['high_after']}",
            RISK_COLORS["High"], f"{result['freed']} would leave High")
        kpi(i3, "Avg success score gain", f"{result['score_gain']:+.1f}", "#7c3aed",
            "for the targeted students")
        st.success(f"If the {result['n']} high-risk students with low attendance reach {target}%, "
                   f"high-risk drops from {result['high_before']} to {result['high_after']}.")
        st.caption("Fixing attendance removes one flag, so most of them move from High to Medium. "
                   "They may still have other flags such as backlogs or low placement readiness.")

    if "segment" in f.columns:
        st.divider()
        st.subheader("Student segments")
        seg = (f["segment"].fillna("Unassigned").value_counts()
               .rename_axis("segment").reset_index(name="students"))
        fig = px.bar(seg, x="students", y="segment", orientation="h",
                     color_discrete_sequence=[PRIMARY], title="Students per segment")
        show(fig)

    flag_cols = [c for c in FLAG_LABELS if c in f.columns]
    if flag_cols:
        st.divider()
        st.subheader("Most common risk reasons")
        reasons = pd.DataFrame({
            "reason": [FLAG_LABELS[c] for c in flag_cols],
            "students": [int(f[c].sum()) for c in flag_cols],
        }).sort_values("students")
        fig = px.bar(reasons, x="students", y="reason", orientation="h",
                     color_discrete_sequence=[PRIMARY],
                     title="Students per risk reason (one student can have several)")
        show(fig)

    st.divider()
    st.subheader("Students needing attention")
    need = f[f["risk_level"].isin(["High", "Medium"])]
    if "segment" in f.columns:
        options = ["All segments"] + sorted(need["segment"].dropna().unique().tolist())
        pick = st.selectbox("Segment", options)
        if pick != "All segments":
            need = need[need["segment"] == pick]

    if need.empty:
        st.info("No students need attention with the current filters.")
    else:
        need = need.sort_values("success_score").head(50).copy()
        need["recommended_action"] = need.apply(recommendation_for, axis=1)
        cols = [c for c in TABLE_COLUMNS if c in need.columns] + ["recommended_action"]
        st.caption("Showing up to 50 students, lowest scores first")
        st.dataframe(style_table(need[cols]), hide_index=True)
        st.download_button("Download this list (CSV)",
                           need[cols].to_csv(index=False).encode("utf-8"),
                           file_name="students_needing_attention.csv", mime="text/csv",
                           key="download_attention")

            # ---- intervention tracker (session only: resets on reload)
    st.divider()
    st.subheader("Intervention tracker")
    st.warning("Demo feature: statuses are kept only in this browser session. "
               "They reset when the page is reloaded or the tab is closed, "
               "and they are not saved to any file or database.")
    tracker = st.session_state.setdefault("tracker", {})
    pool = tracker_pool(f)
    if pool.empty:
        st.info("No flagged students in this view.")
    else:
        acted, resolved = tracker_counts(tracker)
        t1, t2, t3 = st.columns(3)
        kpi(t1, "Students listed below", len(pool), PRIMARY, "highest priority first")
        kpi(t2, "Action started", acted, "#f0a530", "any status except Not started")
        kpi(t3, "Resolved", resolved, "#2e9e5b", "marked Resolved")
        st.caption("Counts include every student you have updated in this session.")

        for _, person in pool.iterrows():
            sid = person["student_id"]
            why = ", ".join(lbl for flag, lbl in FLAG_LABELS.items() if person.get(flag) == 1)
            a, b = st.columns([3, 2])
            a.markdown(f"**{person['name']}** ({sid}) · {person['risk_level']} risk  \n{why}")
            current = tracker.get(sid, "Not started")
            b.selectbox("Status", TRACK_STATUSES, index=TRACK_STATUSES.index(current),
                        key=f"track_{sid}", label_visibility="collapsed",
                        on_change=set_track_status, args=(sid,))

        if acted:
            names = df.set_index("student_id")["name"]
            export = pd.DataFrame({"student_id": list(tracker.keys()),
                                   "status": list(tracker.values())})
            export["name"] = export["student_id"].map(names)
            export = export[export["status"] != "Not started"][["student_id", "name", "status"]]
            st.download_button("Download tracker (CSV)", export.to_csv(index=False).encode("utf-8"),
                               file_name="intervention_tracker.csv", mime="text/csv",
                               key="download_tracker")
        st.button("Clear tracker", on_click=clear_tracker)

st.divider()
st.caption("Scores and risk flags are decision-support indicators based on synthetic demo "
           "data. They should guide supportive conversations, not label or penalize students.")