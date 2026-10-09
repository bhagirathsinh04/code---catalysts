import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

st.set_page_config(page_title="CampusPulse", layout="wide")

# Dummy data (replace later with load_data() + M1's backend)
np.random.seed(1)
df = pd.DataFrame({
    "student_id": [f"STU{i:03d}" for i in range(1, 101)],
    "department": np.random.choice(["CSE", "ICT", "IT"], 100),
    "success_score": np.random.randint(30, 95, 100),
    "risk_level": np.random.choice(["Low", "Medium", "High"], 100),
})

st.title("🎓 CampusPulse")
tab1, tab2, tab3 = st.tabs(["Campus Overview", "Student Explorer", "Insights & Interventions"])

with tab1:
    c1, c2, c3 = st.columns(3)
    c1.metric("Total students", len(df))
    c2.metric("Average score", round(df["success_score"].mean(), 1))
    c3.metric("High risk", (df["risk_level"] == "High").sum())
    st.plotly_chart(px.histogram(df, x="success_score"), use_container_width=True)

with tab2:
    dept = st.sidebar.multiselect("Department", df["department"].unique(),
                                  default=list(df["department"].unique()))
    st.dataframe(df[df["department"].isin(dept)], use_container_width=True)

with tab3:
    st.write("Coming soon")