"""CampusPulse dashboard (frontend).

This file only DISPLAYS data. Numbers come from:
  src/loader.py   -> load_data()   (cleans and joins the 8 CSV files)
  src/backend.py  -> compute_scores(), detect_risks(), assign_segments(),
                     get_recommendations(), risk_breakdown()

If the real data or the backend cannot be loaded, the app shows clearly labelled
DUMMY data (see "Data Status" in the sidebar).
"""

import html
import importlib

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from src.backend import risk_breakdown

st.set_page_config(page_title="CampusPulse", page_icon="🎓", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 1rem; max-width: 1200px;}
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
.kpi-value {font-size: 1.5rem; font-weight: 800; color: #0f172a; line-height: 1.25;}
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

TABLE_COLUMNS = ["student_id", "name", "department", "year", "success_score",
                 "placement_readiness", "academic_risk", "placement_risk", "segment"]

# name of the segment "good marks but low placement readiness" (from src/config.py)
SEG_HIGH_LOW = _cfg("SEGMENTS", ["", "High marks, low placement readiness"])[1]

# all segment names in rule order, what each means, and one colour per segment
SEGMENTS = _cfg("SEGMENTS", [SEG_HIGH_LOW])
SEGMENT_INFO = _cfg("SEGMENT_INFO", {})
SEG_COLORS = dict(zip(SEGMENTS, ["#d64545", "#f0a530", "#2e9e5b", "#7c3aed", "#94a3b8"]))

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

REQUIRED_COLUMNS = ["student_id", "name", "department", "success_score", "risk_level", "academic_risk", "placement_risk"]


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
    """One 0-100 column per score component, read from the backend's score_<name> columns."""
    comps = pd.DataFrame(index=df.index)
    for name in WEIGHTS_SUCCESS:
        comps[name] = df.get(f"score_{name}", np.nan)
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


def run_backend(df):
    """The ONE place the scoring pipeline runs: scores -> risks -> segments.

    The dashboard, the what-if simulator and the campus box all call this,
    so they can never disagree with src/backend.py.
    """
    from src.backend import compute_scores, detect_risks, assign_segments
    return assign_segments(detect_risks(compute_scores(df)))


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


def risk_hits(row, kind=None):
    """The factors that added risk points for this student (from the backend)."""
    table = risk_breakdown(row)
    hits = table[table["Points"] > 0]
    return hits if kind is None else hits[hits["Risk"] == kind]


def why_text(row):
    """One short line: which factors raised the academic and placement risk."""
    hits = risk_hits(row)
    parts = []
    for kind in ("Academic", "Placement"):
        names = hits.loc[hits["Risk"] == kind, "Factor"].tolist()
        if names:
            parts.append(f"{kind}: " + ", ".join(names))
    return "; ".join(parts) or "No warning signs"


def points_note(kind):
    """How points turn into a level, e.g. 'Medium at 1+ points, High at 4+ points'."""
    medium = _cfg("RISK_MEDIUM_POINTS", {"academic": 1, "placement": 2})[kind.lower()]
    high = _cfg("RISK_HIGH_POINTS", {"academic": 4, "placement": 4})[kind.lower()]
    return f"Medium at {medium}+ points, High at {high}+ points"


def color_points(value):
    """Red cell for a factor that added risk points."""
    if isinstance(value, (int, float, np.integer, np.floating)) and value > 0:
        return "background-color: #fee2e2; color: #b91c1c; font-weight: 600"
    return ""


def simulate(df, student_id, changes):
    """Re-score ONE student with edited values (what-if). Nothing is saved.

    The edited row is put back into the full table and the real backend runs
    on the whole table, so campus-wide scaling (logins, events...) stays the
    same and the numbers match the rest of the app.
    """
    sim = df.copy()
    idx = sim.index[sim["student_id"] == student_id][0]
    for col, value in changes.items():
        sim.loc[idx, col] = value
    return run_backend(sim).loc[idx]


# ---------------------------------------------------------------- data
def make_dummy_data(n=120):
    """Fake students with the same column names as the team contract."""
    rng = np.random.default_rng(1)

    def score(mean, sd):
        return rng.normal(mean, sd, n).clip(0, 100).round(1)

    df = pd.DataFrame({
        "student_id": [f"STU{i:03d}" for i in range(1, n + 1)],
        "name": [f"Student {i}" for i in range(1, n + 1)],
        "department": rng.choice(["CSE", "IT", "ECE", "MECH"], n),
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

    return run_backend(df)  # same scoring, risks and segments as the real data

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
    """Returns (df, source, note). source is real or dummy."""
    try:
        df = standardise_columns(find_loader()().reset_index(drop=True))
    except Exception as e:  # data not ready -> show dummy data, but say so loudly
        return make_dummy_data(), "dummy", repr(e)

    try:
        return run_backend(df), "real", ""
    except Exception as e:  # the backend failed -> dummy data, but say so loudly
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
    risk_cols = [c for c in ("risk_level", "academic_risk", "placement_risk") if c in frame.columns]
    if risk_cols:
        styler = apply_map(color_risk, subset=risk_cols)
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

    base = frame_all.copy()
    before = run_backend(base)
    changed = base.copy()
    hit = changed["student_id"].isin(ids)
    changed.loc[hit, "attendance_pct"] = changed.loc[hit, "attendance_pct"].clip(lower=target)
    after = run_backend(changed)
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

    score = row.get("success_score", np.nan)
    levels = f"Academic risk: {row['academic_risk']}. Placement risk: {row['placement_risk']}."
    if pd.isna(score):
        lines.append(f"Success score: not available. {levels}")
    else:
        gap = score - df["success_score"].mean()
        lines.append(f"Success score: {score:.1f} out of 100 ({gap:+.1f} vs campus average). "
                       f"{levels}")

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

    lines += ["", "Why the risk levels are what they are:"]
    for kind in ("Academic", "Placement"):
          hits = risk_hits(row, kind)
          level = row[f"{kind.lower()}_risk"]
          if hits.empty:
              lines.append(f"- {kind} risk {level}: no warning signs.")
              continue
          lines.append(f"- {kind} risk {level} ({int(hits['Points'].sum())} points):")
          for _, r in hits.iterrows():
              lines.append(f"    {r['Factor']}: {r['Student value']} ({r['Rule']}), {r['Points']} point(s)")

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
                      height=340,
                      margin=dict(l=10, r=10, t=50, b=10),
                      font=dict(family="Segoe UI, Inter, sans-serif"),
                      title_font_size=16)
    st.plotly_chart(fig)

def segment_summary(frame):
    """One row per segment (config order, 0 students allowed) with simple averages."""
    order = list(SEGMENTS) + [s for s in frame["segment"].dropna().unique()
                              if s not in SEGMENTS]
    grouped = frame.groupby("segment")
    out = pd.DataFrame({"students": grouped.size()})
    for col in ("success_score", "placement_readiness"):
        out[col] = grouped[col].mean() if col in frame.columns else np.nan
    out = out.reindex(order).rename_axis("segment")
    out["students"] = out["students"].fillna(0).astype(int)
    out["share"] = out["students"] / max(len(frame), 1)
    return out.reset_index()


# ---------------------------------------------------------------- load
df, source, load_error = load_dashboard_data()

missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
if missing:
    st.error(f"The data is missing required columns: {missing}. "
             "Check src/config.py with the team.")
    st.stop()

SOURCE_PILL = {"real": "Live data", "dummy": "Demo data"}
st.markdown(
    '<div class="hero"><div class="hero-title">🎓 CampusPulse</div>'
    '<div class="hero-sub">Student Success Intelligence Platform: see who needs help, '
    'why, and what to do next.</div>'
    f'<span class="pill">{SOURCE_PILL[source]}</span></div>',
    unsafe_allow_html=True,
)

st.caption("**How to use:** set filters in the filter bar at the top. Campus Overview shows who needs help first. "
           "Student Explorer opens one student, explains the score and the two risks, and lets you try "
           "what-if changes. Insights & Interventions groups students into segments and exports lists. "
           "**Overall risk** means the higher of a student's academic risk and placement risk.")

# ---------------------------------------------------------------- sidebar
st.sidebar.header("Data Status")
if source == "dummy":
    st.sidebar.warning("Showing DUMMY data. The real data and backend are not connected yet.")
    with st.sidebar.expander("Why is it dummy?"):
        st.code(load_error)

else:
    st.sidebar.success("Connected to real data")

if source != "dummy":
    with st.sidebar.expander("Data check"):
        st.caption(f"{len(df)} students, {df.shape[1]} columns. "
                   "Check that each min and max looks right.")
        st.dataframe(df.select_dtypes("number").agg(["min", "max"]).T.round(1))

# ---------------------------------------------------------------- filter bar
FILTER_KEYS = ["flt_dept", "flt_year", "flt_acad", "flt_place", "flt_score"]


def reset_filters():
    for k in FILTER_KEYS:
        st.session_state.pop(k, None)


departments = sorted(df["department"].dropna().unique().tolist())
years = sorted(df["year"].dropna().unique().tolist()) if "year" in df.columns else []

with st.container(border=True):
    head_l, head_r = st.columns([6, 1])
    head_l.markdown("**🔎 Filter students** · pick nothing to include everyone")
    head_r.button("Reset", on_click=reset_filters)

c1, c2 = st.columns(2)
sel_depts = c1.pills("Department", departments, selection_mode="multi",
                    key="flt_dept") or departments
if years:
    sel_years = c2.pills("Year", years, selection_mode="multi", key="flt_year",
                        format_func=lambda y: f"Year {int(y)}") or years
else:
    sel_years = None

c3, c4, c5 = st.columns(3)
sel_acad = c3.pills("Academic risk", RISK_ORDER, selection_mode="multi",
                    key="flt_acad") or RISK_ORDER
sel_place = c4.pills("Placement risk", RISK_ORDER, selection_mode="multi",
                    key="flt_place") or RISK_ORDER
score_lo, score_hi = c5.slider("Success score range", 0, 100, (0, 100),
                                key="flt_score")
    
mask = (
    df["department"].isin(sel_depts)
    & df["academic_risk"].isin(sel_acad)
    & df["placement_risk"].isin(sel_place)
    & df["success_score"].between(score_lo, score_hi)
)
if sel_years is not None:
    mask &= df["year"].isin(sel_years)
f = df[mask]
st.caption(f"Showing **{len(f)}** of {len(df)} students")

if f.empty:
    st.info("No students match these filters. Try widening the filters in the filter bar.")
    st.stop()

tab_overview, tab_explorer, tab_insights, tab_trends = st.tabs(
    ["Campus Overview", "Student Explorer", "Insights & Interventions", "Trends"]
)

# ---------------------------------------------------------------- tab 1
with tab_overview: 
    c1, c2, c3, c4, c5 = st.columns(5)
    n_view = len(f)
    acad_high = int((f["academic_risk"] == "High").sum())
    acad_med = int((f["academic_risk"] == "Medium").sum())
    place_high = int((f["placement_risk"] == "High").sum())
    place_med = int((f["placement_risk"] == "Medium").sum())
    both_high = int(((f["academic_risk"] == "High") & (f["placement_risk"] == "High")).sum())
    placement_avg = f["placement_readiness"].mean() if "placement_readiness" in f.columns else np.nan
    kpi(c1, "Total students", n_view, PRIMARY, f"of {len(df)} on campus")
    kpi(c2, "Average success score", na(f["success_score"].mean()), "#7c3aed", "scale 0 to 100")
    kpi(c3, "High academic risk", acad_high, RISK_COLORS["High"],
        f"{acad_high / n_view:.0%} of view · {acad_med} Medium")
    kpi(c4, "High placement risk", place_high, "#c2410c",
        f"{place_high / n_view:.0%} of view · {place_med} Medium")
    kpi(c5, "Avg placement readiness", na(placement_avg), "#0d9488",
        "aptitude, coding, mock interview")
    st.caption(f"{both_high} students are High in both risks, {acad_high - both_high} only in "
               f"academic risk, {place_high - both_high} only in placement risk.")

    # ---- who needs help first
    st.subheader("Top 10 students who need help first")
    urgent = f[f["risk_level"] != "Low"].copy()
    if urgent.empty:
        st.success("No Medium or High risk students in this view.")
    else:
        urgent["_order"] = urgent["risk_level"].map({"High": 0, "Medium": 1})
        urgent["_points"] = urgent[["academic_risk_points", "placement_risk_points"]].sum(axis=1)
        top = urgent.sort_values(["_order", "_points", "success_score"],
                                   ascending=[True, False, True]).head(10).copy()
        top["why_flagged"] = top.apply(why_text, axis=1)
        top["recommended_action"] = top.apply(recommendation_for, axis=1)
        top_cols = [c for c in ["name", "student_id", "department", "success_score",
                                  "academic_risk", "placement_risk",
                                  "why_flagged", "recommended_action"] if c in top.columns]
        st.caption("High in either risk first, then the most warning signs, then the lowest "
                     "success score. Follows the filter bar.")
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
                                    "last_30d_attendance_pct", "attendance_drop",
                                    "academic_risk", "placement_risk"]
                      if c in watch.columns]
        st.caption(f"{len(watch)} students attended {FALLING_DROP}+ points less in the last 30 days "
                   "than overall. Early warning only. This does not change any score. "
                   "Follows the filter bar.")
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
        both = f.melt(id_vars="department", value_vars=["academic_risk", "placement_risk"],
                        var_name="risk_type", value_name="level")
        both["risk_type"] = both["risk_type"].map({"academic_risk": "Academic risk",
                                                     "placement_risk": "Placement risk"})
        counts = both.groupby(["department", "risk_type", "level"]).size().reset_index(name="students")
        fig = px.bar(counts, x="department", y="students", color="level", facet_col="risk_type",
                       color_discrete_map=RISK_COLORS,
                       category_orders={"level": RISK_ORDER},
                       title="Academic and placement risk by department")
        fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
        fig.update_xaxes(title_text="")
        show(fig)

    if "attendance_pct" in f.columns:
        fig = px.scatter(f, x="attendance_pct", y="success_score", color="risk_level",
                         color_discrete_map=RISK_COLORS,
                         category_orders={"risk_level": RISK_ORDER},
                         hover_name="name",
                         title="Attendance vs success score (colour = worse of the two risks)",
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
                        index=2, horizontal=True,
        )
        default_idx = 0
        if quick == "Good marks, low placement readiness":
            if "placement_readiness" in view.columns:
                cand = view[view["segment"] == SEG_HIGH_LOW]
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

        breakdown = risk_breakdown(row)
        points = breakdown.groupby("Risk")["Points"].sum()
        m1, m2, m3, m4, m5 = st.columns(5)
        kpi(m1, "Success score", na(row["success_score"]), "#7c3aed", delta or "")
        kpi(m2, "Placement readiness",
            na(row["placement_readiness"]) if "placement_readiness" in row.index else "N/A",
            "#0d9488", "aptitude, coding, mock interview")
        kpi(m3, "Academic risk", str(row["academic_risk"]),
            RISK_COLORS.get(str(row["academic_risk"]), "#64748b"),
            f"{int(points.get('Academic', 0))} risk points")
        kpi(m4, "Placement risk", str(row["placement_risk"]),
            RISK_COLORS.get(str(row["placement_risk"]), "#64748b"),
            f"{int(points.get('Placement', 0))} risk points")
        kpi(m5, "Segment", str(row["segment"]) if "segment" in row.index else "N/A",
            PRIMARY, "group for targeted action", small=True)

        for kind in ("Academic", "Placement"):
            level = str(row[f"{kind.lower()}_risk"])
            names = breakdown.loc[(breakdown["Risk"] == kind) & (breakdown["Points"] > 0),
                                  "Factor"].tolist()
            text = f"{kind} risk is {level}. " + (
                "Warning signs: " + ", ".join(names) + "." if names else "No warning signs.")
            (st.success if level == "Low" else st.warning)(text)

        st.info(recommendation_for(row))

        filled = int(np.nan_to_num(row.get("missing_fields", 0)))
        no_record = [s for s in ("academic", "attendance", "lms", "engagement",
                                 "placement", "skills", "feedback")
                     if not row.get(f"has_{s}", True)]
        if filled or no_record:
            msg = f"Data confidence: {filled} value(s) were missing and filled with the branch median."
            if no_record:
                msg += " No record in: " + ", ".join(no_record) + "."
            st.caption(msg + " Read this score with care.")

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
            s1, s2, s3, s4 = st.columns(4)
            kpi(s1, "Simulated success score", na(new["success_score"]), "#7c3aed",
                f"{new['success_score'] - row['success_score']:+.1f} vs now")
            kpi(s2, "Simulated placement readiness", na(new["placement_readiness"]), "#0d9488",
                f"{new['placement_readiness'] - row['placement_readiness']:+.1f} vs now")
            kpi(s3, "Simulated academic risk", str(new["academic_risk"]),
                RISK_COLORS.get(str(new["academic_risk"]), "#64748b"),
                f"now: {row['academic_risk']}")
            kpi(s4, "Simulated placement risk", str(new["placement_risk"]),
                RISK_COLORS.get(str(new["placement_risk"]), "#64748b"),
                f"now: {row['placement_risk']}")
            
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

            st.markdown("**Why the risk levels are what they are**")
            st.caption("Each risk adds up points from its warning signs. The total decides the level.")
            for kind in ("Academic", "Placement"):
                part = breakdown[breakdown["Risk"] == kind].drop(columns="Risk")
                st.caption(f"**{kind} risk: {int(part['Points'].sum())} points, so "
                           f"{row[kind.lower() + '_risk']}** ({points_note(kind)})")
                styler = part.style
                apply_map = getattr(styler, "map", None) or styler.applymap
                st.dataframe(apply_map(color_points, subset=["Points"]), hide_index=True)

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
    acad_n = int((f["academic_risk"] == "High").sum())
    place_n = int((f["placement_risk"] == "High").sum())
    either_n = int((f["risk_level"] == "High").sum())
    insights.append(f"{acad_n} students ({acad_n / len(f):.0%}) have High academic risk and "
                    f"{place_n} ({place_n / len(f):.0%}) have High placement risk; "
                    f"{either_n} are High in at least one of the two.")

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
    insights.append(f"{share.index[0]} has the highest share of students at High overall risk "
                    f"({share.iloc[0]:.0%}).")

    if "segment" in f.columns:
        gap_n = int((f["segment"] == SEG_HIGH_LOW).sum())
        insights.append(f"{gap_n} students are in the segment \"{SEG_HIGH_LOW}\": good "
                        "overall scores but low placement readiness. Mock interviews and "
                        "coding practice can help them.")

    thin = 0
    if "data_confidence" in f.columns:
        thin = int((f["data_confidence"] == "Low").sum())
    elif "missing_fields" in f.columns:
        thin = int((f["missing_fields"] >= 3).sum())
    if thin:
        insights.append(f"{thin} students have low data confidence (3 or more values filled "
                        "with estimates, or a whole source missing), so their scores are less certain.")

    for line in insights:
        st.markdown(f"- {line}")

            # ---- campus-level "what if we intervene" (display only, nothing is saved)
    st.divider()
    st.caption("Takes every student with High overall risk and low attendance in the current view "
               "and imagines they reach the target below. The scores are recalculated on a copy. "
               "Nothing is saved.")
    target = st.slider("Target attendance %", int(THRESHOLD_ATTENDANCE), 100,
                       int(THRESHOLD_ATTENDANCE), key="campus_target")
    result = campus_intervention(df, f, target)
    if result is None:
        st.caption("Attendance data is not available, so this box is hidden.")
    elif result["n"] == 0:
        st.info("No students with High overall risk and low attendance in this view.")
    else:
        i1, i2, i3 = st.columns(3)
        kpi(i1, "Students targeted", result["n"], PRIMARY, "High overall risk + low attendance")
        kpi(i2, "High overall risk", f"{result['high_before']} → {result['high_after']}",
            RISK_COLORS["High"], f"{result['freed']} would leave High")
        kpi(i3, "Avg success score gain", f"{result['score_gain']:+.1f}", "#7c3aed",
            "for the targeted students")
        st.success(f"If the {result['n']} students with High overall risk and low attendance reach "
                   f"{target}%, students at High overall risk drop from {result['high_before']} "
                   f"to {result['high_after']}.")
        st.caption(f"Only {result['freed']} of the {result['n']} leave High. Low attendance is just "
                   "one warning sign: most of these students also have backlogs, low internal marks "
                   "or low placement readiness, so attendance alone will not be enough.")
        
    if "segment" in f.columns:
        st.divider()
        st.subheader("Student segments")
        st.caption("Every student is in exactly one segment: the first rule they match decides it. "
                   "Each segment has its own kind of help.")
        seg = segment_summary(f)
        for start in range(0, len(seg), 3):
            cards = st.columns(3)
            for col, (_, s) in zip(cards, seg.iloc[start:start + 3].iterrows()):
                info = SEGMENT_INFO.get(s["segment"], {})
                kpi(col, s["segment"], f"{s['students']} ({s['share']:.0%})",
                    SEG_COLORS.get(s["segment"], PRIMARY), info.get("means", ""))
        fig = px.bar(seg, x="students", y="segment", orientation="h", color="segment",
                     color_discrete_map=SEG_COLORS, title="Students per segment")
        fig.update_layout(showlegend=False, yaxis=dict(autorange="reversed"))
        show(fig)
        
        seg_table = pd.DataFrame({
            "Segment": seg["segment"],
            "Students": seg["students"],
            "Avg success score": seg["success_score"],
            "Avg placement readiness": seg["placement_readiness"],
            "Recommended action": seg["segment"].map(
                lambda name: SEGMENT_INFO.get(name, {}).get("action", "")),
        })
        st.dataframe(seg_table.style.format(precision=1, na_rep="N/A"), hide_index=True,
                     column_config={"Recommended action": st.column_config.TextColumn(width="large")})
        st.caption("Averages are for the students in the current filters. Under \"Students "
                   "needing attention\" you can pick a segment to list its Medium and High risk students.")

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
        st.caption("Students with Medium or High overall risk (the higher of academic and placement risk). "
                   "Showing up to 50, lowest scores first.")
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
            why = why_text(person)
            a, b = st.columns([3, 2])
            a.markdown(f"**{person['name']}** ({sid}) · Academic risk: {person['academic_risk']}, "
                       f"Placement risk: {person['placement_risk']}  \n{why}")
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

        # ---------------------------------------------------------------- tab 4
with tab_trends:
    st.subheader("Key trends")
    if "semester" not in f.columns:
        st.info("Semester is not in the data, so trends are hidden.")
    else:
        st.caption("Each semester is a different batch of students, so these charts "
                   "compare groups. They do not follow one group over time.")
        sem = (f.groupby(["semester", "department"])
                 .agg(avg_score=("success_score", "mean"),
                      high_risk=("risk_level", lambda s: (s == "High").mean() * 100))
                 .reset_index())
        t1, t2 = st.columns(2)
        with t1:
            fig = px.line(sem, x="semester", y="avg_score", color="department",
                          markers=True, title="Average success score by semester")
            fig.update_xaxes(type="category", title="Semester")
            fig.update_yaxes(title="Avg success score")
            show(fig)
        with t2:
            fig = px.bar(sem, x="semester", y="high_risk", color="department",
                         barmode="group", title="Students at High overall risk, by semester (%)")
            fig.update_xaxes(type="category", title="Semester")
            fig.update_yaxes(title="% of students")
            show(fig)

        if {"attendance_pct", "last_30d_attendance_pct"}.issubset(f.columns):
            fall = (f.assign(falling=(f["attendance_pct"] - f["last_30d_attendance_pct"]) >= FALLING_DROP)
                      .groupby("semester")["falling"].mean().mul(100).reset_index())
            fig = px.bar(fall, x="semester", y="falling", color_discrete_sequence=[PRIMARY],
                         title=f"Students whose last-30-day attendance fell {FALLING_DROP}+ points (%)")
            fig.update_xaxes(type="category", title="Semester")
            fig.update_yaxes(title="% of students")
            show(fig)

st.divider()
st.caption("Scores and risk flags are decision-support indicators based on synthetic demo "
           "data. They should guide supportive conversations, not label or penalize students.")