"""Shared settings for CampusPulse. Everyone (M1, M2, M3) imports from here.

Change a value here ONCE and the whole project uses it.
"""

# ------------------------------------------------------------- data files
# Every CSV has student_id, which is how they are joined into one table.
DATA_DIR = "data"

FILE_COLUMNS = {
    "students.csv":   ["student_id", "name", "department", "year"],
    "academic.csv":   ["student_id", "cgpa", "internal_avg", "backlogs"],
    "attendance.csv": ["student_id", "attendance_pct"],
    "lms.csv":        ["student_id", "login_count", "assignment_completion"],
    "engagement.csv": ["student_id", "events", "certifications"],
    "placement.csv":  ["student_id", "aptitude", "coding", "mock_interview"],
    "skills.csv":     ["student_id", "technical_skill", "soft_skill"],
    "feedback.csv":   ["student_id", "satisfaction"],
}

# ------------------------------------------------------------- score weights
# Success Score = weighted sum of these components, each scaled to 0-100.
# The weights must add up to 1.0.
WEIGHTS_SUCCESS = {
    "academic": 0.35,     # cgpa (x10), internal_avg, backlogs
    "attendance": 0.20,   # attendance_pct
    "lms": 0.15,          # login_count, assignment_completion
    "engagement": 0.10,   # events, certifications
    "skills": 0.10,       # technical_skill, soft_skill
    "feedback": 0.10,     # satisfaction
}

# Placement readiness = average of these three columns (0-100).
PLACEMENT_COLUMNS = ["aptitude", "coding", "mock_interview"]

# ------------------------------------------------------------- risk rules
# Flags (0/1). Each one marks a single warning sign.
THRESHOLD_LOW_SUCCESS = 55       # success_score below this -> risk_low_success
THRESHOLD_ATTENDANCE = 70        # attendance_pct below this -> risk_attendance
THRESHOLD_INTERNAL = 45          # internal_avg below this -> risk_internal
THRESHOLD_BACKLOGS = 2           # backlogs at or above this -> risk_backlogs
THRESHOLD_PLACEMENT_LOW = 40     # placement_readiness below this -> risk_placement

# Risk points. A student collects points for each warning sign; stronger signs
# are worth more. The total decides Low / Medium / High (separately for
# academic risk and placement risk).
ACADEMIC_RISK_POINTS = {
    "low_success": 2,      # success_score < THRESHOLD_LOW_SUCCESS
    "low_internal": 2,     # internal_avg < THRESHOLD_INTERNAL
    "backlogs": 2,         # backlogs >= THRESHOLD_BACKLOGS
    "low_attendance": 1,   # attendance_pct < THRESHOLD_ATTENDANCE
    "low_cgpa": 1,         # cgpa < CGPA_WEAK
}
CGPA_WEAK = 5.5

PLACEMENT_RISK_POINTS = {
    "readiness_very_low": 3,  # placement_readiness < PLACEMENT_VERY_LOW
    "readiness_low": 2,       # PLACEMENT_VERY_LOW <= readiness < PLACEMENT_LOW
    "backlogs": 1,            # backlogs >= THRESHOLD_BACKLOGS (many firms reject these)
    "low_cgpa": 1,            # cgpa < CGPA_ELIGIBLE (many firms need 6.0)
    "weak_technical": 1,      # technical_skill < TECHNICAL_WEAK
}
PLACEMENT_VERY_LOW = 35
PLACEMENT_LOW = 45
CGPA_ELIGIBLE = 6.0
TECHNICAL_WEAK = 45

# Points -> level
RISK_MEDIUM_POINTS = {"academic": 1, "placement": 2}   # at or above -> Medium
RISK_HIGH_POINTS = {"academic": 4, "placement": 4}     # at or above -> High
RISK_LEVELS = ["Low", "Medium", "High"]
# risk_level (the old single column) = the worse of academic_risk and placement_risk.

# ------------------------------------------------------------- final columns
# Columns the dashboard (app.py) expects after load_data() and the backend run.
REQUIRED_OUTPUT_COLUMNS = [
    "student_id", "name", "department", "year",
    "success_score", "placement_readiness", "risk_level", "segment",
]
RISK_FLAG_COLUMNS = [
    "risk_low_success", "risk_attendance", "risk_internal",
    "risk_backlogs", "risk_placement",
]

# Segments are assigned in this order: the first rule a student matches wins.
SEGMENTS = [
    "Needs intensive academic support",     # academic_risk is High
    "High marks, low placement readiness",  # SEG_GOOD_MARKS <= success_score and readiness < SEG_LOW_PLACEMENT
    "Placement-ready high achievers",       # success_score >= SEG_HIGH_SUCCESS and readiness >= SEG_HIGH_PLACEMENT
    "Attendance & engagement concern",      # low attendance, or low LMS use and low engagement
    "Steady / on track",                    # everyone else
]
SEG_GOOD_MARKS = 60          # "high marks" for the low-placement segment
SEG_HIGH_SUCCESS = 65        # success score of a high achiever
SEG_LOW_PLACEMENT = 45       # placement readiness below this = low
SEG_HIGH_PLACEMENT = 55      # placement readiness at or above this = ready
SEG_LOW_LMS = 45             # score_lms below this (together with low engagement)
SEG_LOW_ENGAGEMENT = 15      # score_engagement below this (together with low LMS)

# ------------------------------------------------------------- scoring details
BACKLOG_PENALTY = 20            # academic score loses this many points per backlog
ATTENDANCE_RECENT_SHARE = 0.30  # share of the attendance score from the last 30 days
COUNT_CAP_PERCENTILE = 0.95     # count indicators: this percentile student = 100

# ------------------------------------------------------------- recommendations
MAX_ACTIONS = 3                 # most actions shown per student


# ------------------------------------------------------------- data confidence
# The loader fills missing values with the branch median and counts them in
# missing_fields. Students with many filled values (or a whole source missing)
# get a lower data confidence, because their scores are partly estimated.
CONFIDENCE_LOW_MISSING = 3      # this many filled values (or more) -> Low
CONFIDENCE_MEDIUM_MISSING = 2   # this many filled values -> Medium
CONFIDENCE_LEVELS = ["High", "Medium", "Low"]

# Column names in the loader's output -> names used by the dashboard and backend.
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