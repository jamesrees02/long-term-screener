"""Persists the user's chosen filters/columns in the page's own URL (query
string) using Streamlit's native st.query_params, so settings survive
across sessions and reloads.

A cookie was tried first, but Streamlit Community Cloud's hosting proxy
doesn't forward any cookies (custom or Streamlit's own) through to the app
backend, so st.context.cookies always came back empty there. A hand-rolled
components.html + window.parent.history.replaceState was tried next, but
had no visible effect either — most likely blocked by the same cross-frame
boundary Streamlit Cloud's hosting introduces. st.query_params, by
contrast, is Streamlit's own first-class mechanism: writing to it goes
through Streamlit's normal frontend/backend protocol rather than a nested
iframe, so it isn't subject to either failure mode."""

import base64
import json

import streamlit as st

QUERY_PARAM = "s"


def load_settings():
    raw = st.query_params.get(QUERY_PARAM)
    if not raw:
        return None
    try:
        return json.loads(base64.b64decode(raw).decode())
    except Exception:
        return None


def save_settings():
    """Reads the current filter/column/chart widget values straight out of
    st.session_state (all keyed consistently: chosen_filters, filt_<label>,
    display_columns, chart_interval, chart_range) and persists them. Safe to
    call from anywhere, including the chart's own st.fragment, since it
    doesn't need any values passed in."""
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
    encoded = base64.b64encode(json.dumps(data).encode()).decode()
    st.query_params[QUERY_PARAM] = encoded


def current_shareable_url():
    """Best-effort full URL (including the current query param) for the
    user to bookmark, shown on the Settings page as a visible fallback."""
    try:
        base = st.context.url.split("?")[0]
    except Exception:
        base = None
    raw = st.query_params.get(QUERY_PARAM)
    if not base or not raw:
        return None
    return f"{base}?{QUERY_PARAM}={raw}"
