# Smart Campus Analytics

A Student Success Platform that brings attendance, academics, LMS activity, engagement, placement readiness, skills and feedback into one student view. It gives every student a Success Score, flags those at risk, groups students into segments, and explains what drives each score, so faculty can step in early.

**Live demo:** [fill later, after Streamlit deployment]

## Team
- Somesh_Pandya - Backend: scoring, risk flags, segments
- Bhagirathsinh_Jadeja - Frontend: Streamlit dashboard
- Manan_Mehta - Data and deployment

## What it does
- Merges 8 data sources into one student table, with cleaning and a visible cleaning log
- Computes a 0-100 Student Success Score from six indicator groups
- Flags students at risk of poor academic performance or poor placement outcomes
- Groups students into segments for targeted action (for example, strong academics but low placement readiness)
- Explains which indicators drive each student's score and risk flag
- Marks students whose data was partly missing, so their results are read with care
- Lets faculty and administrators filter by branch and semester and open individual student profiles

## Data
The data is synthetic, generated for this project (500 students across 4 branches: CSE, IT, ECE, MECH). It lives in `data/` and is joined on `student_id`.

| File | Contents |
|---|---|
| students.csv | ID, name, branch, semester, batch year |
| academic.csv | CGPA, internal marks, backlogs |
| attendance.csv | Overall and last-30-day attendance |
| lms.csv | Logins per week, assignment completion |
| engagement.csv | Events, clubs, hackathons, certifications |
| placement.csv | Aptitude, coding and mock interview scores |
| skills.csv | Technical and soft-skill scores |
| feedback.csv | Student satisfaction, faculty rating |

The raw files are deliberately messy, as real campus data is. `load_data()` in `src/loader.py` cleans them:
- standardises student IDs and branch names
- removes duplicate rows
- converts text values like `78%` to numbers
- corrects CGPA values entered as percentages
- flags impossible values
- fills missing values with the branch median

It records every fix in a cleaning log, which the dashboard displays.

## Student Success Score
The score is a weighted average of six indicator groups, each scaled to 0-100. Placement readiness is **not** part of it; it is a separate number used for placement risk.

| Group | Weight |
|---|---|
| Academic (CGPA, internal marks, backlogs) | 35% |
| Attendance (overall and last 30 days) | 20% |
| LMS (assignment completion, logins) | 15% |
| Engagement (events, clubs, hackathons, certifications) | 10% |
| Skills (technical, soft) | 10% |
| Feedback (satisfaction, faculty rating) | 10% |

The weights live in `src/config.py`. Full method, worked example and checks: [docs/scoring.md](docs/scoring.md).

## Risk and segments
Every student gets two separate risk levels, each Low, Medium or High:
- **Academic risk**: points for a low Success Score, low internal marks, 2+ backlogs, low attendance and a weak CGPA.
- **Placement risk**: points for low placement readiness, 2+ backlogs, CGPA below 6.0 and weak technical skill.

Stronger warning signs are worth more points, so "High" means the students who need help first (about 13-15% of the class for each risk). Students are also placed in one of five segments, for example "High marks, low placement readiness" or "Attendance & engagement concern", each tied to a suggested action, and each gets a short recommendation. Students whose data was partly filled in are marked with a lower data confidence. The exact rules and cut-offs are in [docs/scoring.md](docs/scoring.md).


## Risk flags
Fill later, once the backend is final: the score thresholds for High and Medium risk, and how academic risk and placement risk are decided.

## Run it locally
Requires Python 3.12.

```bash
git clone https://github.com/bhagirathsinh04/code---catalysts.git
cd code---catalysts
py -3.12 -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

To regenerate the data: `python data/generate_data.py`

## Project structure
```
app.py                Streamlit dashboard
src/config.py         File paths, columns, weights, thresholds
src/loader.py         Loads, cleans and merges the 8 CSVs
src/backend.py        Success Score, risk levels, segments, recommendations
tests/smoke_test.py   Checks the backend on the real data (python tests/smoke_test.py)
data/                 CSV files and the data generator
docs/scoring.md       Score methodology
```

## Tech
Python, pandas, scikit-learn, Streamlit, Plotly