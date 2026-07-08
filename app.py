"""Long-Term Stock Screener — Streamlit app.

Screens stocks by Finviz fundamentals, then charts a selected ticker with
Yahoo Finance daily/weekly candlesticks (TradingView's own charting library).
"""

import json
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import chart
import screener
import settings_store


@st.fragment
def render_chart_panel(ticker):
    st.header(f"4. Chart: {ticker}")
    c1, c2 = st.columns(2)
    interval_label = c1.radio(
        "Interval", list(chart.INTERVALS.keys()), horizontal=True, key="chart_interval"
    )
    range_label = c2.selectbox(
        "Range", list(chart.RANGES.keys()), index=1, key="chart_range"
    )

    candles = chart.get_candles(ticker, interval_label, range_label)
    if not candles:
        st.warning(f"No price data available for {ticker}.")
        return

    lib_js = Path(__file__).parent.joinpath("lightweight_charts.min.js").read_text()
    candles_json = json.dumps(candles)
    html = f"""
    <div id="chart_container" style="width:100%; height:420px;"></div>
    <script>{lib_js}</script>
    <script>
        const container = document.getElementById('chart_container');
        const chart = LightweightCharts.createChart(container, {{
            width: container.clientWidth,
            height: 420,
            layout: {{ background: {{ color: 'transparent' }}, textColor: '#888' }},
            grid: {{
                vertLines: {{ color: 'rgba(128,128,128,0.15)' }},
                horzLines: {{ color: 'rgba(128,128,128,0.15)' }}
            }},
            timeScale: {{ borderColor: 'rgba(128,128,128,0.3)' }},
            rightPriceScale: {{ borderColor: 'rgba(128,128,128,0.3)' }}
        }});
        const series = chart.addCandlestickSeries({{
            upColor: '#26a69a', downColor: '#ef5350',
            borderVisible: false,
            wickUpColor: '#26a69a', wickDownColor: '#ef5350'
        }});
        series.setData({candles_json});
        chart.timeScale().fitContent();
        new ResizeObserver(entries => {{
            chart.applyOptions({{ width: entries[0].contentRect.width }});
        }}).observe(container);
    </script>
    """
    components.html(html, height=440)


st.set_page_config(page_title="Long-Term Stock Screener", layout="wide")
st.title("Long-Term Stock Screener")
st.caption(
    "Screen stocks by fundamentals (Finviz data) and chart a pick with "
    "daily/weekly candlesticks (Yahoo Finance data). Built for long-term "
    "investing research — not day trading."
)

ALL_FILTER_LABELS = sorted(
    list(screener.CATEGORICAL_FILTERS.keys()) + list(screener.NUMERIC_FILTERS.keys())
)

# Seed widget state from last session's saved settings, once per session,
# before any widgets below are created (a key already present in
# session_state takes priority over a widget's own `default=`/`value=`).
if "settings_seeded" not in st.session_state:
    saved = settings_store.load_settings()
    if saved:
        st.session_state["chosen_filters"] = saved.get(
            "chosen_filters", ["Sector", "Dividend Yield (%)", "P/E"]
        )
        st.session_state["display_columns"] = saved.get(
            "display_columns", screener.DEFAULT_DISPLAY_COLUMNS
        )
        for label, value in saved.get("filter_values", {}).items():
            if label in screener.NUMERIC_FILTERS and isinstance(value, list):
                st.session_state[f"filt_{label}"] = tuple(value)
            else:
                st.session_state[f"filt_{label}"] = value
    st.session_state["settings_seeded"] = True

# ---------------------------------------------------------------- Step 1 ---
st.header("1. Choose your filters")
chosen_filters = st.multiselect(
    "Which filters do you want to use? Pick only the ones you care about — "
    "you don't need to touch the rest.",
    options=ALL_FILTER_LABELS,
    default=["Sector", "Dividend Yield (%)", "P/E"],
    key="chosen_filters",
)

categorical_choices = {}
numeric_choices = {}

if chosen_filters:
    cols = st.columns(2)
    for i, label in enumerate(chosen_filters):
        target = cols[i % 2]
        if label in screener.CATEGORICAL_FILTERS:
            options = screener.categorical_options(label)
            categorical_choices[label] = target.selectbox(
                label, options, key=f"filt_{label}"
            )
        else:
            _, lo, hi, step, scale, suffix = screener.NUMERIC_FILTERS[label]
            from_val, to_val = target.slider(
                label,
                min_value=lo,
                max_value=hi,
                value=(lo, hi),
                step=step,
                key=f"filt_{label}",
            )
            numeric_choices[label] = (from_val, to_val)
else:
    st.info("Pick at least one filter above to get started.")

# ---------------------------------------------------------------- Step 2 ---
st.header("2. Choose which columns to show")
st.caption(
    "The order you pick columns here is the order they'll appear in the "
    "table below. To reorder, remove a column and add it back in the order "
    "you want."
)
display_columns = st.multiselect(
    "Columns to display",
    options=screener.ALL_DISPLAY_COLUMNS,
    default=screener.DEFAULT_DISPLAY_COLUMNS,
    key="display_columns",
)

settings_store.save_settings(
    chosen_filters,
    {**categorical_choices, **{k: list(v) for k, v in numeric_choices.items()}},
    display_columns,
)

run = st.button("Run Screen", type="primary", disabled=not chosen_filters, key="run_screen_button")

if "results_df" not in st.session_state:
    st.session_state.results_df = None

if run:
    cols_to_fetch = display_columns or screener.DEFAULT_DISPLAY_COLUMNS
    if "Ticker" not in cols_to_fetch:
        cols_to_fetch = ["Ticker"] + cols_to_fetch
    with st.spinner("Screening Finviz..."):
        try:
            st.session_state.results_df = screener.run_screen(
                categorical_choices, numeric_choices, cols_to_fetch
            )
        except Exception as exc:
            st.error(f"Something went wrong running the screen: {exc}")
            st.session_state.results_df = None

# ---------------------------------------------------------------- Step 3 ---
st.header("3. Results")
df = st.session_state.results_df

if df is None:
    st.write("Run a screen to see results here.")
elif df.empty:
    st.warning("No stocks matched your filters. Try widening a range.")
else:
    st.write(f"**{len(df)}** matching stocks — click a row to chart it.")
    if len(df) >= screener.RESULT_LIMIT:
        st.caption(
            f"Showing the {screener.RESULT_LIMIT} largest companies matching your "
            "filters (by market cap). Add another filter to narrow this down further."
        )

    fmt_map = screener.column_format_map()
    display_df = df.copy()
    for col, (scale, suffix) in fmt_map.items():
        if col in display_df.columns and pd.api.types.is_numeric_dtype(display_df[col]):
            display_df[col] = (display_df[col] * scale).round(2)
            if suffix:
                display_df[col] = display_df[col].map(
                    lambda v: "" if pd.isna(v) else f"{v}{suffix}"
                )

    event = st.dataframe(
        display_df,
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        key="results_table",
    )

    selected_rows = event.selection.rows if event and event.selection else []
    if selected_rows:
        ticker = str(df.iloc[selected_rows[0]]["Ticker"])
        render_chart_panel(ticker)
