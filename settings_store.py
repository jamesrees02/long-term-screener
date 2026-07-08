"""Persists the user's chosen filters/columns/chart preferences to a local
JSON file next to the app, saved explicitly via a "Save Settings" button
and loaded automatically each time the app starts.

Cookies and Streamlit's own st.query_params were tried first for automatic,
invisible persistence, but Streamlit Community Cloud's hosting strips
cookies before they reach the app backend (confirmed empty via
st.context.cookies, even for Streamlit's own cookies), and query-param
persistence was confusing in practice. A plain server-side file, written
on an explicit button click, sidesteps both problems — it only resets if
the Streamlit Cloud container itself restarts (weekly sleep or a new
deploy), which is rare compared to every page load."""

import json
from pathlib import Path

import streamlit as st

SETTINGS_FILE = Path(__file__).parent / "user_settings.json"


def load_settings():
    if not SETTINGS_FILE.exists():
        return None
    try:
        return json.loads(SETTINGS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def save_settings():
    """Reads the current filter/column/chart widget values straight out of
    st.session_state and writes them to disk. Call this from a "Save
    Settings" button, not automatically on every rerun. Returns True on
    success."""
    chosen_filters = st.session_state.get("chosen_filters", [])
    filter_values = {}
    for label in chosen_filters:
        key = f"filt_{label}"
        if key in st.session_state:
            value = st.session_state[key]
            filter_values[label] = list(value) if isinstance(value, tuple) else value

    data = {
        "chosen_filters": chosen_filters,
        "filter_values": filter_values,
        "display_columns": st.session_state.get("display_columns", []),
        "chart_interval": st.session_state.get("chart_interval"),
        "chart_range": st.session_state.get("chart_range"),
    }
    try:
        SETTINGS_FILE.write_text(json.dumps(data, indent=2))
        return True
    except OSError:
        return False
