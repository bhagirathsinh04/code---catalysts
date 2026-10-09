"""
Synthetic data generator for Smart Campus Analytics.

Run from the project root:   python data/generate_data.py
Writes 8 CSVs into the same folder as this script (data/).

Design:
- Each student has hidden "ability", "engagement" and "placement" levels that drive
  the visible columns, so correlations look real (high CGPA -> good attendance, etc).
- ~12% of strong students are given weak placement readiness, which creates the
  "high academics, low placement readiness" segment.
- The raw files are deliberately messy (duplicates, missing values, mixed formats,
  inconsistent IDs and branch names) so the cleaning in load_data() has real work to do.
"""
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).parent
SEED = 42
N = 500
rng = np.random.default_rng(SEED)

# ---------------------------------------------------------------- students
BRANCHES = {"CSE": "CS", "IT": "IT", "ECE": "EC", "MECH": "ME"}
BATCHES = {2023: 7, 2024: 5, 2025: 3}   # batch year -> current semester (Oct 2026)

FIRST = ["Aarav", "Vivaan", "Aditya", "Krish", "Rohan", "Karan", "Dev", "Jay", "Harsh", "Meet",
         "Ananya", "Diya", "Isha", "Kavya", "Riya", "Priya", "Neha", "Pooja", "Sneha", "Tanvi",
         "Yash", "Nikhil", "Raj", "Om", "Parth", "Hetvi", "Khushi", "Mansi", "Dhruv", "Jainam"]
LAST = ["Patel", "Shah", "Mehta", "Joshi", "Desai", "Trivedi", "Parmar", "Solanki", "Vyas", "Bhatt",
        "Gohil", "Chauhan", "Jadeja", "Raval", "Pandya", "Thakkar", "Dave", "Modi", "Kapadia", "Sharma"]

branch_names = list(BRANCHES)
rows = []
counters = {}
for i in range(N):
    branch = branch_names[i % 4]
    batch = list(BATCHES)[rng.integers(0, 3)]
    key = (branch, batch)
    counters[key] = counters.get(key, 0) + 1
    sid = f"MU{str(batch)[2:]}{BRANCHES[branch]}{counters[key]:03d}"
    name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
    rows.append((sid, name, branch, BATCHES[batch], batch))
students = pd.DataFrame(rows, columns=["student_id", "name", "branch", "semester", "batch_year"])

# ---------------------------------------------------------------- hidden levels
ability = rng.normal(0, 1, N)
engage = 0.45 * ability + rng.normal(0, 0.9, N)
place = 0.5 * ability + 0.4 * engage + rng.normal(0, 0.6, N)

# "strong academics, weak placement readiness" group
mask = (ability > 0.3) & (rng.random(N) < 0.35)
place[mask] -= 1.7
engage[mask] -= 0.9


def clip(x, lo, hi):
    return np.clip(x, lo, hi)


# ---------------------------------------------------------------- academic
cgpa = clip(6.8 + 1.0 * ability + rng.normal(0, 0.45, N), 4.0, 9.9).round(2)
internal = clip(62 + 9 * ability + rng.normal(0, 6, N), 20, 100).round(1)
backlogs = np.minimum(rng.poisson(clip(0.5 - 0.7 * ability, 0.02, 4)), 6)
academic = pd.DataFrame({"student_id": students.student_id, "cgpa": cgpa,
                         "avg_internal_marks": internal, "backlogs": backlogs})

# ---------------------------------------------------------------- attendance
att_lat = 0.6 * ability + 0.8 * rng.normal(0, 1, N)
overall = clip(76 + 9 * att_lat + rng.normal(0, 3, N), 35, 100).round(1)
last30 = clip(overall + rng.normal(-1.5, 6, N), 20, 100).round(1)
attendance = pd.DataFrame({"student_id": students.student_id, "overall_attendance_pct": overall,
                           "last_30d_attendance_pct": last30})

# ---------------------------------------------------------------- LMS
lms_lat = 0.5 * ability + 0.5 * engage + rng.normal(0, 0.5, N)
logins = clip(4.5 + 2.3 * lms_lat + rng.normal(0, 1.3, N), 0, 20).round(1)
assign = clip(74 + 14 * lms_lat + rng.normal(0, 7, N), 0, 100).round(1)
lms = pd.DataFrame({"student_id": students.student_id, "logins_per_week": logins,
                    "assignment_completion_pct": assign})

# ---------------------------------------------------------------- engagement
engagement = pd.DataFrame({
    "student_id": students.student_id,
    "events_attended": rng.poisson(clip(3 + 1.6 * engage, 0.2, 12)),
    "clubs_joined": np.minimum(rng.poisson(clip(1.1 + 0.6 * engage, 0.1, 4)), 5),
    "hackathons": np.minimum(rng.poisson(clip(0.7 + 0.5 * engage, 0.05, 4)), 6),
    "certifications": np.minimum(rng.poisson(clip(1.2 + 0.7 * (0.5 * ability + 0.5 * engage), 0.1, 6)), 8),
})

# ---------------------------------------------------------------- placement
placement = pd.DataFrame({
    "student_id": students.student_id,
    "aptitude_score": clip(56 + 12 * place + rng.normal(0, 6, N), 5, 100).round(1),
    "coding_score": clip(50 + 14 * place + rng.normal(0, 7, N), 0, 100).round(1),
    "mock_interview_score": clip(53 + 12 * place + rng.normal(0, 7, N), 5, 100).round(1),
})

# ---------------------------------------------------------------- skills
skills = pd.DataFrame({
    "student_id": students.student_id,
    "technical_score": clip(56 + 11 * (0.5 * ability + 0.5 * place) + rng.normal(0, 6, N), 5, 100).round(1),
    "softskill_score": clip(62 + 10 * (0.4 * engage + 0.4 * place) + rng.normal(0, 7, N), 10, 100).round(1),
})

# ---------------------------------------------------------------- feedback (0-100)
feedback = pd.DataFrame({
    "student_id": students.student_id,
    "satisfaction_score": clip(66 + 6 * engage + 3 * ability + rng.normal(0, 11, N), 10, 100).round(1),
    "faculty_rating": clip(70 + 4 * ability + rng.normal(0, 9, N), 20, 100).round(1),
})

# ---------------------------------------------------------------- planted demo students
# Overwrite 5 known students so the live demo has clear stories.
demo = {}
ids = students.student_id.tolist()


def plant(idx, label, **cols):
    sid = ids[idx]
    demo[label] = sid
    for col, val in cols.items():
        for df in (academic, attendance, lms, engagement, placement, skills, feedback):
            if col in df.columns:
                df.loc[df.student_id == sid, col] = val


plant(10, "Strong academics, weak placement readiness",
      cgpa=9.1, avg_internal_marks=88, backlogs=0, overall_attendance_pct=91, last_30d_attendance_pct=89,
      logins_per_week=7, assignment_completion_pct=92, events_attended=1, clubs_joined=0, hackathons=0,
      certifications=0, aptitude_score=38, coding_score=29, mock_interview_score=33,
      technical_score=52, softskill_score=41)
plant(21, "Attendance falling fast",
      cgpa=7.2, avg_internal_marks=68, backlogs=0, overall_attendance_pct=74, last_30d_attendance_pct=46,
      logins_per_week=2.5, assignment_completion_pct=58)
plant(32, "High academic risk",
      cgpa=5.1, avg_internal_marks=41, backlogs=4, overall_attendance_pct=52, last_30d_attendance_pct=47,
      logins_per_week=1.0, assignment_completion_pct=31, aptitude_score=34, coding_score=22,
      mock_interview_score=30)
plant(43, "Hidden gem (low CGPA, strong skills)",
      cgpa=6.2, avg_internal_marks=58, backlogs=1, overall_attendance_pct=82, last_30d_attendance_pct=84,
      events_attended=9, clubs_joined=3, hackathons=4, certifications=5,
      aptitude_score=78, coding_score=84, mock_interview_score=75, technical_score=86, softskill_score=79)
plant(54, "All-round star",
      cgpa=9.4, avg_internal_marks=92, backlogs=0, overall_attendance_pct=96, last_30d_attendance_pct=95,
      logins_per_week=12, assignment_completion_pct=98, events_attended=8, clubs_joined=3, hackathons=3,
      certifications=5, aptitude_score=90, coding_score=92, mock_interview_score=88,
      technical_score=91, softskill_score=87)

# ---------------------------------------------------------------- make the raw files messy
def blank(df, cols, frac):
    for c in cols:
        m = (rng.random(len(df)) < frac) & (~df.student_id.isin(demo.values()))
        df[c] = df[c].astype("float64").mask(m)
    return df


academic = blank(academic, ["cgpa", "avg_internal_marks"], 0.03)
attendance = blank(attendance, ["overall_attendance_pct", "last_30d_attendance_pct"], 0.03)
lms = blank(lms, ["logins_per_week", "assignment_completion_pct"], 0.035)
engagement = blank(engagement, ["events_attended", "certifications"], 0.03)
placement = blank(placement, ["aptitude_score", "coding_score", "mock_interview_score"], 0.04)
skills = blank(skills, ["technical_score", "softskill_score"], 0.03)
feedback = blank(feedback, ["satisfaction_score", "faculty_rating"], 0.06)

# some students missing entirely from a source (left-join realism)
def drop_students(df, k):
    pool = df[~df.student_id.isin(demo.values())].student_id.sample(k, random_state=SEED).tolist()
    return df[~df.student_id.isin(pool)].copy()


lms = drop_students(lms, 8)
feedback = drop_students(feedback, 15)
placement = drop_students(placement, 6)

# CGPA typed as a percentage for 3 students (e.g. 78.4 instead of 7.84)
for sid in academic[~academic.student_id.isin(demo.values())].student_id.sample(3, random_state=1):
    academic.loc[academic.student_id == sid, "cgpa"] = (academic.loc[academic.student_id == sid, "cgpa"] * 10).round(1)

# attendance stored as text like "78%" for ~7% of rows
attendance["overall_attendance_pct"] = attendance["overall_attendance_pct"].astype(object)
m = rng.random(len(attendance)) < 0.07
attendance.loc[m, "overall_attendance_pct"] = attendance.loc[m, "overall_attendance_pct"].map(
    lambda v: f"{v:.0f}%" if pd.notna(v) else v)

# duplicate rows
academic = pd.concat([academic, academic.sample(6, random_state=3)], ignore_index=True)
attendance = pd.concat([attendance, attendance.sample(4, random_state=4)], ignore_index=True)
engagement = pd.concat([engagement, engagement.sample(3, random_state=5)], ignore_index=True)

# inconsistent ids in the LMS file (lowercase / trailing space)
m = rng.random(len(lms)) < 0.04
lms.loc[m, "student_id"] = lms.loc[m, "student_id"].str.lower() + " "

# inconsistent branch names
m = rng.random(len(students)) < 0.10
students.loc[m, "branch"] = students.loc[m, "branch"].str.lower()
m = rng.random(len(students)) < 0.05
students.loc[m, "branch"] = students.loc[m, "branch"] + " "

# ---------------------------------------------------------------- write
files = {"students": students, "academic": academic, "attendance": attendance, "lms": lms,
         "engagement": engagement, "placement": placement, "skills": skills, "feedback": feedback}
for name, df in files.items():
    df.to_csv(OUT / f"{name}.csv", index=False)
    print(f"{name}.csv  {len(df)} rows")

print("\nDemo students:")
for label, sid in demo.items():
    print(f"  {sid}  {label}")
