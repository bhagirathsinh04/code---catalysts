# Student Success Score

## Purpose
The Student Success Score is a single 0-100 number that summarises how well a student is doing across academics, attendance, online learning, engagement, skills and feedback. Faculty use it to see who needs help first.

Placement readiness is **not** part of this score. It is a separate 0-100 number that is used for risk flags and segments (see below).

## Indicators used

| Group | Columns | Weight |
|---|---|---|
| Academic | cgpa, internal_avg, backlogs | 35% |
| Attendance | attendance_pct | 20% |
| LMS | assignment_completion, login_count | 15% |
| Engagement | events, certifications | 10% |
| Skills | technical_skill, soft_skill | 10% |
| Feedback | satisfaction | 10% |

The weights add up to 100% and live in `src/config.py` (`WEIGHTS_SUCCESS`). Column names are the dashboard names; the raw CSV names are mapped to them in `app.py` (for example `avg_internal_marks` becomes `internal_avg`).

Collected but not used in the score: `last_30d_attendance_pct`, `clubs_joined`, `hackathons` and `faculty_rating`.

## How the score is calculated

**Step 1. Clean the data.** Missing values are filled with the student's branch median (fallback: the overall median). Details are in `src/loader.py`, and every fix is shown in the cleaning log.

**Step 2. Scale every indicator to 0-100.**
- Percentages and test scores are already on 0-100.
- CGPA is multiplied by 10.
- Backlogs are converted so that 0 backlogs = 100 and each backlog lowers the value by 20 points, with a minimum of 0 (5 or more backlogs = 0). The penalty is `BACKLOG_PENALTY` in `src/config.py`.
- Count indicators (logins per week, events, certifications) are scaled against the highest value on campus: the student with the most gets 100, and everyone else gets their count divided by that maximum, times 100.

**Step 3. Average inside each group.** Each group score is the simple average of its scaled indicators. For example, Academic = average of (CGPA x 10, internal marks, backlog score).

**Step 4. Combine the groups with the weights.**

```
Success Score = 0.35 x Academic
              + 0.20 x Attendance
              + 0.15 x LMS
              + 0.10 x Engagement
              + 0.10 x Skills
              + 0.10 x Feedback
```

If a group has no data for a student, the remaining weights are scaled up so they still add to 100%. A missing group never lowers the score.

## Why these weights
- Academic outcomes carry the most weight because they are the core measure of student success.
- Attendance is the strongest early warning sign, so it comes second.
- LMS activity shows day-to-day effort between exams.
- Engagement, skills and feedback add a wider picture of how the student is doing, at 10% each.

## Placement readiness
Placement readiness is the average of three scores, each on 0-100: aptitude, coding and mock interview. It is shown next to the Success Score and is used by the risk flags and segments below.

## Risk flags
Five flags are checked for each student. The thresholds are in `src/config.py`.

| Flag | Raised when |
|---|---|
| Low success score | Success Score is below 50 |
| Low attendance | Attendance is below 75% |
| Low internal marks | Internal marks are below 40 |
| Too many backlogs | 2 or more backlogs |
| Low placement readiness | Placement readiness is below 50 |

The **risk level** depends on how many flags are raised:

| Flags raised | Risk level |
|---|---|
| 0 | Low |
| 1 | Medium |
| 2 or more | High |

The "Why this score?" section of the Student Explorer shows each of these checks with the student's value and whether it was raised.

## Segments
Students are grouped into segments so that interventions can be targeted. Rules are checked in this order and the first match wins:

1. **High marks, low placement readiness:** Success Score is 60 or more and placement readiness is below 50. Suggested action: mock interviews and coding practice.
2. **Attendance support needed:** attendance is below 75%. Suggested action: attendance counselling.
3. **Academic support needed:** Success Score is below 50. Suggested action: meet a mentor for an academic plan.
4. **On track:** everyone else.

## Explaining a student's score
For every student, the dashboard shows how many points each group contributes (group score x weight) next to the campus average, and names the biggest strength and biggest drag. This tells faculty why a student is flagged, so they know what to act on.

## Limitations
- The data is synthetic, so the results illustrate the method and do not describe real students.
- The weights are a starting point. A college can adjust them in `src/config.py` to match its own priorities.
- Count indicators are scaled against the campus maximum, so one unusually high value lowers everyone else's scaled score for that indicator.
- The score shows who needs attention, but a person must decide on any intervention.