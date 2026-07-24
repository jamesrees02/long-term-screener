"""Long-Term Stock Screener — Streamlit app.

Screens stocks by Finviz fundamentals, then charts a selected ticker with
Yahoo Finance daily/weekly candlesticks (TradingView's own charting library).
Also includes a separate Fundamentals Trend Screener tab that checks
multi-year revenue/net income/total assets trends via Yahoo Finance.
"""

import json
import re
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import chart
import fundamentals
import portfolio
import screener
import settings_store


def render_chart_panel(
    ticker, interval_key="chart_interval", range_key="chart_range", show_save_button=True
):
    st.header(f"Chart: {ticker}")
    c1, c2, c3 = st.columns([2, 2, 1])

    interval_options = list(chart.INTERVALS.keys())
    saved_interval = st.session_state.get(interval_key)
    interval_index = (
        interval_options.index(saved_interval)
        if saved_interval in interval_options
        else 0
    )
    interval_label = c1.radio(
        "Interval",
        interval_options,
        index=interval_index,
        horizontal=True,
        key=interval_key,
    )

    range_options = list(chart.RANGES.keys())
    saved_range = st.session_state.get(range_key)
    range_index = (
        range_options.index(saved_range) if saved_range in range_options else 1
    )
    range_label = c2.selectbox(
        "Range", range_options, index=range_index, key=range_key
    )
    if show_save_button:
        c3.write("")  # vertical spacer so the button lines up with the widgets
        c3.write("")
        if c3.button("💾 Save Settings", key="save_settings_button_chart"):
            if settings_store.save_settings():
                st.success("Saved.")
            else:
                st.error("Couldn't save settings.")

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


def render_growth_chart_panel(ticker, key_prefix, returns):
    st.subheader(f"{ticker} — 15-Year Growth (Monthly)")
    candles, _markers, levels = portfolio.get_growth_chart_data(ticker, returns)
    if not candles:
        st.warning(f"No price history available for {ticker}.")
        return

    lib_js = Path(__file__).parent.joinpath("lightweight_charts.min.js").read_text()
    candles_json = json.dumps(candles)
    # Round floats so the iframe script stays compact/stable on Streamlit Cloud.
    levels_for_js = []
    for level in levels:
        levels_for_js.append(
            {
                **level,
                "price": round(float(level["price"]), 4),
                "latest_price": round(float(level["latest_price"]), 4),
                "dollar_delta": (
                    None
                    if level["dollar_delta"] is None
                    else round(float(level["dollar_delta"]), 2)
                ),
                "pct": round(float(level["pct"]), 2),
            }
        )
    levels_json = json.dumps(levels_for_js)
    container_id = f"growth_chart_{key_prefix}_{ticker}"
    html = f"""
    <div id="{container_id}" style="position:relative; width:100%; height:420px;"></div>
    <script>{lib_js}</script>
    <script>
        const container = document.getElementById('{container_id}');
        const chart = LightweightCharts.createChart(container, {{
            width: container.clientWidth || container.parentElement.clientWidth || 800,
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

        const levels = {levels_json};
        const candleData = {candles_json};
        let dataLow = Infinity;
        let dataHigh = -Infinity;
        candleData.forEach(function(c) {{
            if (c.low < dataLow) dataLow = c.low;
            if (c.high > dataHigh) dataHigh = c.high;
        }});
        const overlay = document.createElement('canvas');
        overlay.style.position = 'absolute';
        overlay.style.top = '0';
        overlay.style.left = '0';
        overlay.style.zIndex = '10';
        overlay.style.pointerEvents = 'none';
        container.appendChild(overlay);

        function hexToRgba(hex, alpha) {{
            const h = String(hex).replace('#', '');
            const r = parseInt(h.substring(0, 2), 16);
            const g = parseInt(h.substring(2, 4), 16);
            const b = parseInt(h.substring(4, 6), 16);
            return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
        }}

        function formatDelta(value) {{
            if (value === null || value === undefined || isNaN(value)) return 'n/a';
            const abs = Math.abs(value);
            const body = abs >= 100
                ? abs.toLocaleString(undefined, {{ maximumFractionDigits: 0 }})
                : abs.toLocaleString(undefined, {{ maximumFractionDigits: 2 }});
            return (value >= 0 ? '+' : '-') + body;
        }}

        function drawArrow(ctx, x, yBottom, yTop, color) {{
            const tip = 8;
            const head = 6;
            ctx.strokeStyle = color;
            ctx.fillStyle = color;
            ctx.lineWidth = 2;
            ctx.setLineDash([]);
            ctx.beginPath();
            ctx.moveTo(x, yBottom);
            ctx.lineTo(x, yTop + tip);
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(x, yTop);
            ctx.lineTo(x - head, yTop + tip);
            ctx.lineTo(x + head, yTop + tip);
            ctx.closePath();
            ctx.fill();
        }}

        function finite(v) {{
            return typeof v === 'number' && isFinite(v);
        }}

        function priceToYFallback(price, height) {{
            const top = 8;
            const bottom = Math.max(top + 10, height - 28);
            if (!(dataHigh > dataLow)) return (top + bottom) / 2;
            return top + (dataHigh - price) / (dataHigh - dataLow) * (bottom - top);
        }}

        function priceToY(price, height) {{
            const y = series.priceToCoordinate(price);
            if (finite(y)) return y;
            // Fallback if LWC scale isn't ready yet (common in Streamlit iframes).
            return priceToYFallback(price, height);
        }}

        function drawOverlay() {{
            const width = container.clientWidth || chart.options().width || 0;
            const height = container.clientHeight || 420;
            if (width < 10) return;

            overlay.style.width = width + 'px';
            overlay.style.height = height + 'px';
            overlay.width = width;
            overlay.height = height;
            const ctx = overlay.getContext('2d');
            ctx.clearRect(0, 0, width, height);
            if (!levels.length) return;

            const timeScale = chart.timeScale();
            // Longest → shortest so each bucket ends where the next shorter one starts
            // (15→10, 10→5, 5→today) — non-overlapping exclusive spans.
            const points = levels.slice().sort(function(a, b) {{
                return b.years - a.years;
            }}).map(function(level, i, arr) {{
                const xLeft = timeScale.timeToCoordinate(level.anchor_time);
                const endTime = (i + 1 < arr.length)
                    ? arr[i + 1].anchor_time
                    : level.latest_time;
                const xRight = timeScale.timeToCoordinate(endTime);
                let yAnchor = priceToY(level.price, height);
                let yLatest = priceToY(level.latest_price, height);
                // If LWC returns a collapsed/wrong scale, map prices ourselves.
                if (!finite(yAnchor) || !finite(yLatest) || Math.abs(yAnchor - yLatest) < 8) {{
                    yAnchor = priceToYFallback(level.price, height);
                    yLatest = priceToYFallback(level.latest_price, height);
                }}
                return {{
                    level: level,
                    xLeft: xLeft,
                    xRight: xRight,
                    yAnchor: yAnchor,
                    yLatest: yLatest,
                }};
            }}).filter(function(p) {{
                return finite(p.xLeft) && finite(p.xRight)
                    && finite(p.yAnchor) && finite(p.yLatest);
            }});
            if (!points.length) return;

            points.forEach(function(p) {{
                const x0 = Math.min(p.xLeft, p.xRight);
                const x1 = Math.max(p.xLeft, p.xRight);
                const yTop = Math.min(p.yAnchor, p.yLatest);
                const yBottom = Math.max(p.yAnchor, p.yLatest);
                const boxH = Math.max(yBottom - yTop, 2);
                const boxW = Math.max(x1 - x0, 2);

                // Stronger fill so bands stay visible on Streamlit's light theme.
                ctx.fillStyle = hexToRgba(p.level.color, 0.22);
                ctx.fillRect(x0, yTop, boxW, boxH);

                ctx.strokeStyle = hexToRgba(p.level.color, 0.85);
                ctx.lineWidth = 1.5;
                ctx.setLineDash([]);
                ctx.strokeRect(x0 + 0.5, yTop + 0.5, boxW - 1, boxH - 1);

                ctx.setLineDash([4, 3]);
                ctx.beginPath();
                ctx.moveTo(x0, p.yAnchor);
                ctx.lineTo(x1, p.yAnchor);
                ctx.stroke();
                ctx.beginPath();
                ctx.moveTo(x0, p.yLatest);
                ctx.lineTo(x1, p.yLatest);
                ctx.stroke();
            }});

            // Arrows + labels centered in each exclusive bucket.
            points.forEach(function(p) {{
                const midX = (p.xLeft + p.xRight) / 2;
                const up = p.yLatest <= p.yAnchor;
                const yFrom = up ? p.yAnchor : p.yLatest;
                const yTo = up ? p.yLatest : p.yAnchor;
                drawArrow(ctx, midX, yFrom, yTo, p.level.color);

                const pct = p.level.pct;
                const pctText = (pct >= 0 ? '+' : '') + pct.toFixed(0) + '%';
                const label = p.level.years + 'yr  '
                    + formatDelta(p.level.dollar_delta)
                    + '  (' + pctText + ')';
                ctx.font = 'bold 12px sans-serif';
                const textWidth = ctx.measureText(label).width;
                const labelX = Math.max(4, Math.min(midX - textWidth / 2, width - textWidth - 8));
                const labelY = Math.max(16, Math.min(p.yAnchor, p.yLatest) - 12);

                ctx.fillStyle = 'rgba(255, 255, 255, 0.92)';
                ctx.strokeStyle = p.level.color;
                ctx.lineWidth = 1;
                ctx.setLineDash([]);
                ctx.fillRect(labelX - 5, labelY - 12, textWidth + 10, 18);
                ctx.strokeRect(labelX - 5.5, labelY - 12.5, textWidth + 11, 19);
                ctx.fillStyle = '#111';
                ctx.fillText(label, labelX, labelY + 1);
            }});
        }}

        function scheduleDraw() {{
            drawOverlay();
            requestAnimationFrame(function() {{
                drawOverlay();
                requestAnimationFrame(drawOverlay);
            }});
            [50, 150, 400, 1000].forEach(function(ms) {{
                setTimeout(drawOverlay, ms);
            }});
        }}

        scheduleDraw();
        chart.timeScale().subscribeVisibleTimeRangeChange(drawOverlay);
        if (chart.timeScale().subscribeVisibleLogicalRangeChange) {{
            chart.timeScale().subscribeVisibleLogicalRangeChange(drawOverlay);
        }}
        new ResizeObserver(entries => {{
            const w = entries[0].contentRect.width;
            if (w > 0) chart.applyOptions({{ width: w }});
            scheduleDraw();
        }}).observe(container);
    </script>
    """
    components.html(html, height=440)
    st.caption(
        "Adjacent shaded buckets from monthly Yahoo bars: 15→10yr, 10→5yr, "
        "and 5yr→today (60/120/180 months back). Labels show the trailing "
        "return from that start bar to the latest month -- same as the table."
    )


def render_etf_holdings_panel(ticker):
    st.subheader(f"Top 10 Holdings: {ticker}")
    holdings_df = portfolio.get_etf_holdings(ticker)
    if holdings_df.empty:
        st.info(f"No holdings data available for {ticker}.")
        return
    st.dataframe(holdings_df, hide_index=True, width="stretch")
    st.caption(
        "Top 10 only -- Yahoo Finance's free data doesn't expose a fund's "
        "full holdings list."
    )


def _render_growth_price_legend(returns):
    """Show the monthly closes behind the selected row's growth figures."""
    st.caption("Prices used for 5/10/15yr growth (Yahoo monthly closes)")
    cols = st.columns(4)
    for col, (label, price, when) in zip(cols, portfolio.growth_price_rows(returns)):
        col.metric(label, price, help=when or "N/A")


def _style_stock_table(display_df):
    styler = display_df.style
    if "P/E" in display_df.columns:
        styler = styler.map(portfolio.pe_style, subset=["P/E"])
    if "EPS" in display_df.columns:
        styler = styler.map(portfolio.eps_style, subset=["EPS"])
    if "Employees" in display_df.columns:
        styler = styler.map(portfolio.employees_style, subset=["Employees"])
    if "Growth Flag" in display_df.columns:
        styler = styler.map(portfolio.growth_flag_style, subset=["Growth Flag"])

    format_map = {}
    if "P/E" in display_df.columns:
        format_map["P/E"] = "{:.1f}"
    if "EPS" in display_df.columns:
        format_map["EPS"] = "{:.2f}"
    if "Employees" in display_df.columns:
        format_map["Employees"] = "{:,.0f}"
    if "Dividend Yield" in display_df.columns:
        format_map["Dividend Yield"] = "{:.2f}%"
    if "Growth Flag" in display_df.columns:
        format_map["Growth Flag"] = lambda v: portfolio.GROWTH_FLAG_LABEL.get(v, str(v))
    return styler.format(format_map, na_rep="N/A")


def _run_portfolio_batch(key_prefix, fetch_fn):
    """Shared ticker-input + Analyze-button + progress-bar wiring for a
    Portfolio Builder section. fetch_fn(tickers, progress_callback) ->
    DataFrame. Returns the stored results DataFrame (or None)."""
    ticker_key = f"portfolio_{key_prefix}_tickers"
    if ticker_key not in st.session_state:
        st.session_state[ticker_key] = ""
    ticker_text = st.text_area(
        "Tickers (comma or newline separated)", key=ticker_key, height=80
    )
    analyze = st.button("Analyze", key=f"analyze_{key_prefix}_button")

    df_key = f"portfolio_{key_prefix}_df"
    if df_key not in st.session_state:
        st.session_state[df_key] = None

    if analyze:
        tickers = [t for t in re.split(r"[,\s]+", ticker_text) if t]
        if not tickers:
            st.warning("Enter at least one ticker first.")
        else:
            progress_bar = st.progress(0.0, text="Starting...")

            def _update_progress(done, total):
                progress_bar.progress(done / total, text=f"Analyzing {done}/{total}...")

            st.session_state[df_key] = fetch_fn(tickers, _update_progress)
            progress_bar.empty()

    return st.session_state[df_key]


def render_stock_section(title, key_prefix, include_financials):
    st.subheader(title)
    df = _run_portfolio_batch(
        key_prefix,
        lambda tickers, cb: portfolio.run_batch(tickers, include_financials, progress_callback=cb),
    )

    if df is None:
        st.write("Enter tickers and click Analyze to see results here.")
        return
    if df.empty:
        st.warning("No results.")
        return

    error_rows = df[df["Error"].notna()]
    ok_df = df[df["Error"].isna()].reset_index(drop=True)

    if ok_df.empty:
        st.warning("No results.")
    else:
        display_cols = ["Ticker", "Sector"]
        if include_financials:
            display_cols += ["Revenue", "Net Income", "Total Assets", "Total Liabilities"]
        display_cols += ["P/E", "EPS", "Employees", "Dividend Yield", "Growth Flag", "Return Display"]

        display_df = ok_df[display_cols].copy()
        for col in ["Revenue", "Net Income", "Total Assets", "Total Liabilities"]:
            if col in display_df.columns:
                display_df[col] = display_df[col].map(fundamentals.format_dollars)
        display_df = display_df.rename(columns={"Return Display": "5/10/15 Yr Growth"})

        event = st.dataframe(
            _style_stock_table(display_df),
            hide_index=True,
            width="stretch",
            on_select="rerun",
            selection_mode="single-row",
            key=f"portfolio_{key_prefix}_table",
        )

        selected_rows = event.selection.rows if event and event.selection else []
        if selected_rows:
            selected_row = ok_df.iloc[selected_rows[0]]
            _render_growth_price_legend(selected_row["Returns"])
            render_growth_chart_panel(str(selected_row["Ticker"]), key_prefix, selected_row["Returns"])

    if not error_rows.empty:
        st.caption(
            "Couldn't fetch: "
            + ", ".join(f"{r['Ticker']} ({r['Error']})" for _, r in error_rows.iterrows())
        )


def render_etf_section(title, key_prefix):
    st.subheader(title)
    df = _run_portfolio_batch(
        key_prefix, lambda tickers, cb: portfolio.run_etf_batch(tickers, progress_callback=cb)
    )

    if df is None:
        st.write("Enter tickers and click Analyze to see results here.")
        return
    if df.empty:
        st.warning("No results.")
        return

    error_rows = df[df["Error"].notna()]
    ok_df = df[df["Error"].isna()].reset_index(drop=True)

    if ok_df.empty:
        st.warning("No results.")
    else:
        display_df = ok_df[["Ticker", "Growth Flag", "Return Display"]].copy()
        display_df = display_df.rename(columns={"Return Display": "5/10/15 Yr Growth"})

        event = st.dataframe(
            _style_stock_table(display_df),
            hide_index=True,
            width="stretch",
            on_select="rerun",
            selection_mode="single-row",
            key=f"portfolio_{key_prefix}_table",
        )

        selected_rows = event.selection.rows if event and event.selection else []
        if selected_rows:
            selected_row = ok_df.iloc[selected_rows[0]]
            ticker = str(selected_row["Ticker"])
            _render_growth_price_legend(selected_row["Returns"])
            render_growth_chart_panel(ticker, key_prefix, selected_row["Returns"])
            render_etf_holdings_panel(ticker)

    if not error_rows.empty:
        st.caption(
            "Couldn't fetch: "
            + ", ".join(f"{r['Ticker']} ({r['Error']})" for _, r in error_rows.iterrows())
        )


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
        if saved.get("chart_interval") in chart.INTERVALS:
            st.session_state["chart_interval"] = saved["chart_interval"]
        if saved.get("chart_range") in chart.RANGES:
            st.session_state["chart_range"] = saved["chart_range"]
        for key in [
            "portfolio_growing_tickers",
            "portfolio_etf_tickers",
            "portfolio_dividend_tickers",
            "portfolio_speculative_tickers",
        ]:
            if saved.get(key):
                st.session_state[key] = saved[key]
    st.session_state["settings_seeded"] = True

tab1, tab2, tab3 = st.tabs(
    ["Finviz Screener", "Fundamentals Trend Screener", "Portfolio Builder"]
)

with tab1:
    # ------------------------------------------------------------ Step 1 ---
    st.header("1. Choose your filters")
    chosen_filters = st.multiselect(
        "Which filters do you want to use? Pick only the ones you care about "
        "— you don't need to touch the rest.",
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

    # ------------------------------------------------------------ Step 2 ---
    st.header("2. Choose which columns to show")
    st.caption(
        "The order you pick columns here is the order they'll appear in the "
        "table below. To reorder, remove a column and add it back in the "
        "order you want."
    )
    display_columns = st.multiselect(
        "Columns to display",
        options=screener.ALL_DISPLAY_COLUMNS,
        default=screener.DEFAULT_DISPLAY_COLUMNS,
        key="display_columns",
    )

    with st.sidebar:
        st.header("Settings")
        st.caption(
            "Set your filters, columns, and chart preferences, then click "
            "Save — next time you open the app, they'll be loaded "
            "automatically."
        )
        if st.button("💾 Save Settings", key="save_settings_button"):
            if settings_store.save_settings():
                st.success("Saved.")
            else:
                st.error("Couldn't save settings.")
        with st.expander("What's currently saved?"):
            st.json(settings_store.load_settings() or {})

    run = st.button(
        "Run Screen", type="primary", disabled=not chosen_filters, key="run_screen_button"
    )

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

    # ------------------------------------------------------------ Step 3 ---
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
                f"Showing the {screener.RESULT_LIMIT} largest companies "
                "matching your filters (by market cap). Add another filter "
                "to narrow this down further."
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

with tab2:
    st.header("Fundamentals Trend Screener")
    st.caption(
        "Checks multi-year revenue, net income, and total assets trends "
        "(Yahoo Finance data, up to ~5 years), whether each year's net "
        "income covered that year's current liabilities, and the cash "
        "trend. This is a separate tool from the Finviz screener above — "
        "paste in whichever tickers you want to check. A longer list can "
        "take a couple of minutes, since each ticker needs its own fetch."
    )

    if "fundamentals_ticker_input" not in st.session_state:
        st.session_state["fundamentals_ticker_input"] = ""

    finviz_results = st.session_state.get("results_df")
    if finviz_results is not None and not finviz_results.empty:
        if st.button("Use tickers from current Finviz results", key="use_finviz_tickers"):
            st.session_state["fundamentals_ticker_input"] = ", ".join(
                finviz_results["Ticker"].tolist()
            )

    ticker_text = st.text_area(
        "Tickers to analyze (comma or newline separated)",
        key="fundamentals_ticker_input",
        height=100,
    )

    analyze = st.button("Analyze", type="primary", key="analyze_fundamentals_button")

    if "fundamentals_df" not in st.session_state:
        st.session_state.fundamentals_df = None

    if analyze:
        tickers = [t for t in re.split(r"[,\s]+", ticker_text) if t]
        if not tickers:
            st.warning("Enter at least one ticker first.")
        else:
            progress_bar = st.progress(0.0, text="Starting...")

            def _update_progress(done, total):
                progress_bar.progress(done / total, text=f"Analyzing {done}/{total}...")

            st.session_state.fundamentals_df = fundamentals.run_batch(
                tickers, progress_callback=_update_progress
            )
            progress_bar.empty()

    fdf = st.session_state.fundamentals_df
    if fdf is None:
        st.write("Enter tickers and click Analyze to see results here.")
    elif fdf.empty:
        st.warning("No results.")
    else:
        st.write(f"**{len(fdf)}** tickers analyzed.")

        display_fdf = fdf.copy()

        def _flags(row):
            flags = []
            if row.get("All Liabilities Covered") is False:
                flags.append("⚠️ Liabilities")
            if row.get("Cash Declining"):
                flags.append("⚠️ Cash declining")
            return ", ".join(flags)

        display_fdf["Flags"] = display_fdf.apply(_flags, axis=1)
        for col in [
            "Latest Revenue",
            "Latest Net Income",
            "Latest Total Assets",
            "Latest Current Liabilities",
        ]:
            if col in display_fdf.columns:
                display_fdf[col] = display_fdf[col].map(fundamentals.format_dollars)

        cols_order = [
            "Ticker",
            "Flags",
            "Total Score",
            "Revenue Trend",
            "Latest Revenue",
            "Net Income Trend",
            "Latest Net Income",
            "Total Assets Trend",
            "Latest Total Assets",
            "Liabilities Coverage",
            "Latest Current Liabilities",
            "Cash Trend",
            "Latest Cash",
            "Error",
        ]
        cols_order = [c for c in cols_order if c in display_fdf.columns]
        display_fdf = display_fdf[cols_order]

        event = st.dataframe(
            display_fdf,
            hide_index=True,
            width="stretch",
            on_select="rerun",
            selection_mode="single-row",
            key="fundamentals_table",
            column_config={
                "Cash Trend": st.column_config.LineChartColumn(
                    "Cash Trend", help="Cash balance, oldest to newest"
                ),
                "Latest Cash": st.column_config.NumberColumn(
                    "Latest Cash", format="compact"
                ),
            },
        )
        st.caption(
            "Trend badges: ✅⭐ = grew every year (best), ✅ = grew overall "
            "but not every year, ❌ = declined overall, N/A = not enough "
            "data. Liabilities Coverage shows ✅/❌ per year (oldest → "
            "newest) for whether that year's net income covered current "
            "liabilities. Total Score sums the three trend badges (0-6) — "
            "click the column header to sort by it. Click a row for the "
            "full year-by-year breakdown."
        )

        selected_rows = event.selection.rows if event and event.selection else []
        if selected_rows:
            selected_ticker_row = fdf.iloc[selected_rows[0]]
            ticker_name = selected_ticker_row["Ticker"]
            history = selected_ticker_row.get("History")
            st.subheader(f"{ticker_name} — year by year")
            if not history:
                st.write("No detailed history available for this ticker.")
            else:
                history_df = pd.DataFrame(history)
                for col in ["Revenue", "Net Income", "Total Assets", "Current Liabilities", "Cash"]:
                    if col in history_df.columns:
                        history_df[col] = history_df[col].map(fundamentals.format_dollars)
                st.dataframe(history_df, hide_index=True, width="stretch")

            render_chart_panel(
                ticker_name,
                interval_key="fundamentals_chart_interval",
                range_key="fundamentals_chart_range",
                show_save_button=False,
            )

with tab3:
    st.header("Portfolio Builder")
    st.caption(
        "Four target-allocation buckets, each with its own ticker list "
        "(Yahoo Finance data throughout). Click a row for its price chart, "
        "a 15-year monthly growth chart, and (for ETFs) top holdings."
    )

    render_stock_section("Growing Stocks (~40%)", "growing", include_financials=True)
    st.divider()
    render_etf_section("ETFs (~30-35%)", "etf")
    st.divider()
    render_stock_section("High Dividend Stocks (~5-10%)", "dividend", include_financials=False)
    st.divider()
    render_stock_section("Speculative Stocks (~5-10%)", "speculative", include_financials=True)
