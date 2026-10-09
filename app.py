"""CampusPulse dashboard (M2 - Frontend).

This file only DISPLAYS data. Numbers come from:
  src/db.py       -> load_data()                       (M3)
  src/backend.py  -> compute_scores(), detect_risks(),
                     assign_segments(), get_recommendations()   (M1)

If those are not ready yet, the app shows clearly-labelled DUMMY data,
and switches to the real data automatically once they work.
"""
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="CampusPulse", page_icon="🎓", layout="wide")

# ---------------------------------------------------------------- constants
THRESHOLD_ATTENDANCE = 75
THRESHOLD_PLACEMENT_LOW = 50
WEIGHTS_SUCCESS = {"academic": 0.35, "attendance": 0.20, "lms": 0.15,
                   "engagement": 0.10, "skills": 0.10, "feedback": 0.10}
try:  # use the team's shared values from src/config.py when they exist
    import src.config as cfg
    THRESHOLD_ATTENDANCE = getattr(cfg, "THRESHOLD_ATTENDANCE", THRESHOLD_ATTENDANCE)
    THRESHOLD_PLACEMENT_LOW = getattr(cfg, "THRESHOLD_PLACEMENT_LOW", THRESHOLD_PLACEMENT_LOW)
    WEIGHTS_SUCCESS = getattr(cfg, "WEIGHTS_SUCCESS", WEIGHTS_SUCCESS)
except Exception:
    pass

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

    df["success_score"] = (
        0.35 * df["cgpa"] * 10 + 0.20 * df["attendance_pct"]
        + 0.15 * df["assignment_completion"] + 0.15 * df["internal_avg"]
        + 0.15 * df["satisfaction"]
    ).round(1)
    df["placement_readiness"] = df[["coding", "aptitude", "mock_interview"]].mean(axis=1).round(1)

    df["risk_low_success"] = (df["success_score"] < 50).astype(int)
    df["risk_attendance"] = (df["attendance_pct"] < THRESHOLD_ATTENDANCE).astype(int)
    df["risk_internal"] = (df["internal_avg"] < 40).astype(int)
    df["risk_backlogs"] = (df["backlogs"] >= 2).astype(int)
    df["risk_placement"] = (df["placement_readiness"] < THRESHOLD_PLACEMENT_LOW).astype(int)
    flags = df[[c for c in df.columns if c.startswith("risk_")]].sum(axis=1)
    df["risk_level"] = np.where(flags == 0, "Low", np.where(flags == 1, "Medium", "High"))

    df["segment"] = np.select(
        [
            (df["success_score"] >= 60) & (df["placement_readiness"] < THRESHOLD_PLACEMENT_LOW),
            df["attendance_pct"] < THRESHOLD_ATTENDANCE,
            df["success_score"] < 50,
        ],
        ["High marks, low placement readiness", "Attendance support needed",
         "Academic support needed"],
        default="On track",
    )
    return df


@st.cache_data
def load_dashboard_data():
    """Real pipeline if ready, otherwise dummy data. Returns (df, source, error)."""
    try:
        from src.db import load_data
        from src.backend import compute_scores, detect_risks, assign_segments

        df = load_data()
        df = compute_scores(df)
        df = detect_risks(df)
        df = assign_segments(df)
        return df, "real", ""
    except Exception as e:  # not ready yet -> show dummy data, but say so loudly
        return make_dummy_data(), "dummy", repr(e)


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


def kpi(column, label, value):
    """A bordered KPI card."""
    with column.container(border=True):
        st.metric(label, value)


# ---------------------------------------------------------------- load
df, source, load_error = load_dashboard_data()

missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
if missing:
    st.error(f"The data is missing required columns: {missing}. "
             "Check src/config.py with the team.")
    st.stop()

st.title("🎓 CampusPulse")
st.caption("Student Success Intelligence Platform: see who needs help, why, and what to do next.")

# ---------------------------------------------------------------- sidebar
st.sidebar.header("Filters")
if source == "dummy":
    st.sidebar.warning("Showing DUMMY data. The real data and backend are not connected yet.")
    with st.sidebar.expander("Why is it dummy?"):
        st.code(load_error)
else:
    st.sidebar.success("Connected to real data")

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
    kpi(c1, "Total students", len(f))
    kpi(c2, "Average success score", na(f["success_score"].mean()))
    kpi(c3, "High-risk students", int((f["risk_level"] == "High").sum()))
    placement_avg = f["placement_readiness"].mean() if "placement_readiness" in f.columns else np.nan
    kpi(c4, "Avg placement readiness", na(placement_avg))

    with st.expander("How is the Success Score calculated?"):
        weights = pd.DataFrame({
            "Component": [k.replace("_", " ").title() for k in WEIGHTS_SUCCESS],
            "Weight": [f"{v:.0%}" for v in WEIGHTS_SUCCESS.values()],
        })
        st.dataframe(weights, hide_index=True)
        st.caption("Each indicator is scaled to 0-100, then combined using these weights. "
                   "The score supports decisions; it does not replace a teacher's judgement.")

    left, right = st.columns(2)
    with left:
        fig = px.histogram(f, x="success_score", nbins=20,
                           title="Success score distribution",
                           labels={"success_score": "Success score"})
        st.plotly_chart(fig)
    with right:
        counts = f.groupby(["department", "risk_level"]).size().reset_index(name="students")
        fig = px.bar(counts, x="department", y="students", color="risk_level",
                     color_discrete_map=RISK_COLORS,
                     category_orders={"risk_level": RISK_ORDER},
                     title="Risk level by department")
        st.plotly_chart(fig)

    if "attendance_pct" in f.columns:
        fig = px.scatter(f, x="attendance_pct", y="success_score", color="risk_level",
                         color_discrete_map=RISK_COLORS,
                         category_orders={"risk_level": RISK_ORDER},
                         hover_name="name",
                         title="Attendance vs success score",
                         labels={"attendance_pct": "Attendance %",
                                 "success_score": "Success score"})
        st.plotly_chart(fig)

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

        m1, m2, m3, m4 = st.columns(4)
        with m1.container(border=True):
            st.metric("Success score", na(row["success_score"]), delta=delta)
        with m2.container(border=True):
            st.metric("Placement readiness",
                      na(row["placement_readiness"]) if "placement_readiness" in row.index else "N/A")
        with m3.container(border=True):
            st.metric("Risk level", str(row["risk_level"]))
        with m4.container(border=True):
            st.metric("Segment", str(row["segment"]) if "segment" in row.index else "N/A")

        raised = [label for flag, label in FLAG_LABELS.items() if row.get(flag) == 1]
        if raised:
            st.warning("Why flagged: " + ", ".join(raised))
        else:
            st.success("No risk flags for this student.")
        st.info(recommendation_for(row))

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
                         barmode="group", title="This student vs campus average")
            st.plotly_chart(fig)
        if missing_labels:
            st.caption("N/A (not available): " + ", ".join(missing_labels))

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

    if "segment" in f.columns:
        st.divider()
        st.subheader("Student segments")
        seg = (f["segment"].fillna("Unassigned").value_counts()
               .rename_axis("segment").reset_index(name="students"))
        fig = px.bar(seg, x="students", y="segment", orientation="h",
                     title="Students per segment")
        st.plotly_chart(fig)

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

st.divider()
st.caption("Scores and risk flags are decision-support indicators based on synthetic demo "
           "data. They should guide supportive conversations, not label or penalize students.")