# Student Success Score

## Purpose
The Student Success Score is a single 0-100 number that summarises how well a student is doing across academics, attendance, online learning, engagement, placement readiness and skills. Faculty use it to see who needs help first.

## Indicators used

| Group | Columns | Weight |
|---|---|---|
| Academic | cgpa, avg_internal_marks, backlogs | 30% |
| Attendance | overall_attendance_pct, last_30d_attendance_pct | 20% |
| LMS | logins_per_week, assignment_completion_pct | 15% |
| Placement readiness | aptitude_score, coding_score, mock_interview_score | 15% |
| Engagement | events_attended, clubs_joined, hackathons, certifications | 10% |
| Skills | technical_score, softskill_score | 10% |

Student feedback (satisfaction_score, faculty_rating) is shown on the dashboard as context. It is not part of the score, because it describes the institution's service and not the student's performance.

## How the score is calculated

**Step 1. Clean the data.** Missing values are filled with the student's branch median. Details are in `src/loader.py`.

**Step 2. Scale every indicator to 0-100.**
- Percentages and test scores are already on 0-100.
- CGPA is multiplied by 10.
- Backlogs are converted so that 0 backlogs = 100 and each backlog lowers the value [by __ points, minimum 0].
- Count indicators (events, clubs, hackathons, certifications, logins) are scaled against a target, with values capped at 100 [describe the targets used].

**Step 3. Average inside each group.** Each group score is the simple average of its scaled indicators [or the weights inside the group, if M1 used any].

**Step 4. Combine the groups with the weights.**

```
Success Score = 0.30 x Academic
              + 0.20 x Attendance
              + 0.15 x LMS
              + 0.15 x Placement readiness
              + 0.10 x Engagement
              + 0.10 x Skills
```
(Update the numbers to match the table above.)

## Why these weights
- Academic outcomes carry the most weight because they are the core measure of student success.
- Attendance is the strongest early warning sign, so it comes second.
- LMS activity shows day-to-day effort between exams.
- Placement readiness, engagement and skills describe outcomes beyond the classroom.

## Risk flags

| Flag | Rule |
|---|---|
| High risk | Success Score below 50 |
| Medium risk | Success Score from 50 to 65 |
| Low risk | Success Score above 65 |

Two specific risks are also flagged:
- **Academic risk:** [rule, for example CGPA below 6, or 2 or more backlogs, or attendance below 65%]
- **Placement risk:** [rule, for example placement readiness below 50, or coding score below 40]

## Segments
Students are grouped into segments so that interventions can be targeted:
- [Segment 1, for example "High academics, low placement readiness": rule]
- [Segment 2]
- [Segment 3]

## Explaining a student's score
For every student, the dashboard shows how many points each group contributes (group score x weight) and which indicators pull the score down the most. This tells faculty why a student is flagged, so they know what to act on.

## Limitations
- The data is synthetic, so the results illustrate the method and do not describe real students.
- The weights are a starting point. A college can adjust them in `src/config.py` to match its own priorities.
- The score shows who needs attention, but a person must decide on any intervention.