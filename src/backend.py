"""Backend for CampusPulse: scores, risk flags, segments, recommendations.

app.py uses it like:  assign_segments(detect_risks(compute_scores(df)))
Input df uses the dashboard column names (department, internal_avg,
attendance_pct, login_count, ...), not the raw CSV names.
"""
import numpy as np
import pandas as pd

from src import config


def compute_scores(df):
    """Add success_score, placement_readiness and score_<group> columns."""
    raise NotImplementedError


def detect_risks(df):
    """Add the risk_* flag columns and risk_level."""
    raise NotImplementedError


def assign_segments(df):
    """Add the segment column."""
    raise NotImplementedError


def get_recommendations(row):
    """Return a short action text for one student (one row of the table)."""
    raise NotImplementedError