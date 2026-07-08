"""Persists the user's chosen filters/columns as a browser cookie, so
settings survive across sessions and even Streamlit Cloud sleep/redeploy
cycles (a server-side file would not survive those)."""

import base64
import json

import streamlit as st
import streamlit.components.v1 as components

COOKIE_NAME = "ltscreener_settings"
COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 365  # 1 year


def load_settings():
    raw = st.context.cookies.get(COOKIE_NAME)
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
    components.html(
        f'<script>document.cookie = "{COOKIE_NAME}={encoded}; path=/; '
        f'max-age={COOKIE_MAX_AGE_SECONDS}; SameSite=Lax";</script>',
        height=0,
    )
