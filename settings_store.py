"""Persists the user's chosen filters/columns in the page's own URL (query
string), so settings survive across sessions and reloads. A cookie was
tried first, but Streamlit Community Cloud's hosting proxy doesn't forward
any cookies (custom or Streamlit's own) through to the app backend, so
st.context.cookies always came back empty there. The URL doesn't have that
problem — it's part of the request Streamlit must route, so it always
reaches the backend."""

import base64
import json

import streamlit as st
import streamlit.components.v1 as components

QUERY_PARAM = "s"


def load_settings():
    raw = st.query_params.get(QUERY_PARAM)
    if not raw:
        return None
    try:
        return json.loads(base64.b64decode(raw).decode())
    except Exception:
        return None


def save_settings(chosen_filters, filter_values, display_columns):
    data = {
        "chosen_filters": chosen_filters,
        "filter_values": filter_values,
        "display_columns": display_columns,
    }
    encoded = base64.b64encode(json.dumps(data).encode()).decode()
    # Update the address bar via the parent page's History API (no
    # navigation/reload triggered) so revisiting the same tab or bookmark
    # restores these settings next time.
    components.html(
        f"""
        <script>
        (function() {{
            const params = new URLSearchParams(window.parent.location.search);
            params.set("{QUERY_PARAM}", "{encoded}");
            const newUrl = window.parent.location.pathname + "?" + params.toString();
            window.parent.history.replaceState(null, "", newUrl);
        }})();
        </script>
        """,
        height=0,
    )
