# Student Success Score

## Purpose
The Student Success Score is a single 0-100 number that summarises how well a student is doing across academics, attendance, online learning, engagement, skills and feedback. Faculty use it to see who needs help first.

Placement readiness is **not** part of this score. It is a separate 0-100 number, used for placement risk and segments (see below).

All numbers in this note come from `src/config.py`. Change a value there once and the whole project uses it.

## Indicators and weights

| Group | Indicators used | Weight |
|---|---|---|
| Academic | CGPA, internal marks, backlogs | 35% |
| Attendance | overall attendance, last-30-day attendance | 20% |
| LMS | assignment completion, logins per week | 15% |
| Engagement | events, clubs joined, hackathons, certifications | 10% |
| Skills | technical skill, soft skill | 10% |
| Feedback | student satisfaction, faculty rating | 10% |

The weights add up to 100% (`WEIGHTS_SUCCESS` in `src/config.py`). Column names are the dashboard names; the raw CSV names are mapped to them (for example `avg_internal_marks` becomes `internal_avg`).

## How the score is calculated

**Step 1. Clean the data.** Missing values are filled with the student's branch median (fallback: the overall median). Every fix is shown in the cleaning log (`src/loader.py`).

**Step 2. Scale every indicator to 0-100.**
- Percentages and test scores are already on 0-100.
- CGPA is multiplied by 10.
- Backlogs become a score: 0 backlogs = 100, and each backlog lowers it by 20 points (minimum 0).
- Attendance = 70% overall attendance + 30% last-30-day attendance, so a recent drop shows up quickly.
- Count indicators (logins, events, clubs, hackathons, certifications) are scaled against the 95th-percentile student, who gets 100. Anyone above that is capped at 100, so one extreme student cannot squash everyone else.

**Step 3. Average inside each group.** Each group score is the simple average of its scaled indicators. Example: Academic = average of (CGPA x 10, internal marks, backlog score).

**Step 4. Combine the groups with the weights.**

```
Success Score = 0.35 x Academic + 0.20 x Attendance + 0.15 x LMS
              + 0.10 x Engagement + 0.10 x Skills + 0.10 x Feedback
```

If a group has no data for a student, the remaining weights are scaled up so they still add to 100%. A missing group never lowers the score.

**Worked example** (student MU24EC002): CGPA 4.77, internal marks 41.9, 4 backlogs give Academic = (47.7 + 41.9 + 20) / 3 = 36.5. Attendance = 0.7 x 60.5 + 0.3 x 54.8 = 58.8. With LMS 42.0, Engagement 28.6, Skills 46.2 and Feedback 73.2, the Success Score is 45.6.

## Why these weights
- Academic outcomes carry the most weight because they are the core measure of student success.
- Attendance is the strongest early warning sign, so it comes second.
- LMS activity shows day-to-day effort between exams.
- Engagement, skills and feedback give a wider picture, at 10% each.

The ranking of students barely changes if the weights change. When we shifted every weight by up to 30% in 300 random tries, the student ranking stayed above 0.99 correlation with the original, and equal weights give a 0.97 correlation. So the exact weights are not fragile.

## Placement readiness
Placement readiness is the average of aptitude, coding, mock interview (each 0-100). It is shown next to the Success Score and drives placement risk.

## Two risks, not one
The brief asks about two different problems, so each student gets two separate risk levels: **academic risk** and **placement risk**, each Low, Medium or High. A student collects risk points for each warning sign; stronger signs are worth more.

### Academic risk
| Warning sign | Points |
|---|---|
| Success Score below 55 | 2 |
| Internal marks below 45 | 2 |
| 2 or more backlogs | 2 |
| Attendance below 70% | 1 |
| CGPA below 5.5 | 1 |

1-3 points = **Medium**, 4 or more = **High**, 0 = Low.

### Placement risk
| Warning sign | Points |
|---|---|
| Placement readiness below 35 | 3 |
| Placement readiness 35 to 44.9 | 2 |
| 2 or more backlogs (many firms reject them) | 1 |
| CGPA below 6.0 (many firms need 6.0) | 1 |
| Technical skill below 45 | 1 |

2-3 points = **Medium**, 4 or more = **High**, 0-1 = Low.

### Warning-sign flags and the overall level
Five single flags are also stored for the dashboard: low success score, low attendance, low internal marks, too many backlogs, and low placement readiness (below 40). The overall **risk level** is the worse of academic risk and placement risk.

### Why points and not "count the flags"
Our first version counted every flag equally and flagged 31% of students as High. Half of the class sat below the old placement and attendance cut-offs, because the class average is close to them. Points make strong signs (a very low score, many backlogs) count more than mild ones, and the new cut-offs put about 13-15% of students in High on each risk, so faculty can start with the students who need help most.

## Segments
Students are grouped so that interventions can be targeted. Rules are checked in this order and the first match wins.

| Segment | Rule | Suggested action |
|---|---|---|
| Needs intensive academic support | academic risk is High | mentor meetings, backlog plan |
| High marks, low placement readiness | Success Score 60+ and readiness below 45 | mock interviews, coding practice |
| Placement-ready high achievers | Success Score 65+ and readiness 55+ | company drives, leadership roles |
| Attendance & engagement concern | attendance below 70%, or low LMS use (below 45) and low engagement (below 15) | attendance counselling, activities |
| Steady / on track | everyone else | keep monitoring |

We tried KMeans clustering first. This data has no natural clusters (silhouette score about 0.18; above 0.5 would mean real groups), and the clusters only said "high, medium or low overall". Rules are easier to explain and each one leads to a clear action.

## Data confidence
The loader fills missing values with the branch median. Such a student looks average, so their result is partly an estimate. Each student gets a data confidence of **Low** (3+ filled values, or a whole source such as placement has no record), **Medium** (2 filled values) or **High** (0 or 1). Scores are not adjusted for this. Low-confidence students are marked, and their advice tells faculty to check the records first.

## Recommendations
Each student gets a short action text built from their biggest problems (backlogs, mentoring, internal marks, attendance, placement preparation, low LMS use), most urgent first, at most 3 actions, quoting the student's own numbers. The weakest of aptitude, coding and mock interview is named for placement practice.

## Explaining a student's score
For every student, the dashboard shows how many points each group contributes (group score x weight) next to the campus average, names the biggest strength and the biggest drag, and lists each warning sign with the student's value. This tells faculty why a student is flagged.

## How we checked it
- **By hand:** we worked out five different students (high-risk, placement-ready, high marks but low placement, attendance concern, low data confidence) with a separate calculation and matched every group score, the Success Score, placement readiness and risk points. This check is repeated by `tests/smoke_test.py`.
- **Smoke test:** `python tests/smoke_test.py` runs the backend on the real data and checks required columns, no empty values, scores between 0 and 100, sensible risk and segment counts, and valid text for every student.
- **Stability:** moving one risk cut-off by 2 points changes the level of between 4 and 31 of the 500 students.

## Settings
Every value below can be changed in `src/config.py`.

| Setting | Value |
|---|---|
| `WEIGHTS_SUCCESS` | academic 0.35, attendance 0.2, lms 0.15, engagement 0.1, skills 0.1, feedback 0.1 |
| `BACKLOG_PENALTY` | 20 |
| `ATTENDANCE_RECENT_SHARE` | 0.3 |
| `COUNT_CAP_PERCENTILE` | 0.95 |
| `THRESHOLD_LOW_SUCCESS` | 55 |
| `THRESHOLD_ATTENDANCE` | 70 |
| `THRESHOLD_INTERNAL` | 45 |
| `THRESHOLD_BACKLOGS` | 2 |
| `THRESHOLD_PLACEMENT_LOW` | 40 |
| `CGPA_WEAK` | 5.5 |
| `CGPA_ELIGIBLE` | 6.0 |
| `PLACEMENT_VERY_LOW` | 35 |
| `PLACEMENT_LOW` | 45 |
| `TECHNICAL_WEAK` | 45 |
| `RISK_MEDIUM_POINTS` | academic 1, placement 2 |
| `RISK_HIGH_POINTS` | academic 4, placement 4 |
| `CONFIDENCE_LOW_MISSING` | 3 |
| `CONFIDENCE_MEDIUM_MISSING` | 2 |

## Limitations
- The data is synthetic, so the results illustrate the method and do not describe real students.
- The weights and cut-offs are our choices, tuned so that about 13-15% of this synthetic class is High risk. A real college should set its own.
- Risk levels have hard edges: a student at 54.9 and one at 55.1 are not really different. Use the points and reasons, not only the label.
- Missing values are replaced by medians, not predicted. Data confidence marks these students but does not correct their scores.
- The score shows who needs attention. A person must decide on any intervention.