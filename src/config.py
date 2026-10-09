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

# ------------------------------------------------------------- risk thresholds
THRESHOLD_LOW_SUCCESS = 50       # success_score below this -> risk_low_success
THRESHOLD_ATTENDANCE = 75        # attendance_pct below this -> risk_attendance
THRESHOLD_INTERNAL = 40          # internal_avg below this -> risk_internal
THRESHOLD_BACKLOGS = 2           # backlogs at or above this -> risk_backlogs
THRESHOLD_PLACEMENT_LOW = 50     # placement_readiness below this -> risk_placement

# Number of raised flags -> risk_level
#   0 flags = "Low", 1 flag = "Medium", 2 or more = "High"
RISK_LEVELS = ["Low", "Medium", "High"]

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

SEGMENTS = [
    "High marks, low placement readiness",
    "Attendance support needed",
    "Academic support needed",
    "On track",
]