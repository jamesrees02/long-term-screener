"""Portfolio Builder: yfinance-based fetchers for a personal 4-section
target-allocation tracker (Growing Stocks, ETFs, High Dividend Stocks,
Speculative Stocks), modeled on the user's own spreadsheet.

Single data source (yfinance) for every field in every section -- see
fundamentals.py's docstring for why Finviz doesn't serve this kind of
per-ticker multi-year/historical pull well; no reason to mix two
providers' quirks in one table.
"""

import pandas as pd
import yfinance as yf

RETURN_HORIZONS_YEARS = [5, 10, 15]
EMPLOYEE_THRESHOLD = 10_000
PE_MAX = 100

LIABILITIES_ROW_CANDIDATES = ["Total Liabilities Net Minority Interest", "Total Liab"]

COLOR_GREEN = "background-color: #c8e6c9; color: black"
COLOR_ORANGE = "background-color: #ffe0b2; color: black"
COLOR_RED = "background-color: #ffcdd2; color: black"
COLOR_GRAY = "background-color: #eeeeee; color: black"

GROWTH_FLAG_LABEL = {"green": "Yes", "orange": "Yes", "red": "No", "n/a": "N/A"}
GROWTH_FLAG_STYLE = {
    "green": COLOR_GREEN,
    "orange": COLOR_ORANGE,
    "red": COLOR_RED,
    "n/a": COLOR_GRAY,
}


def _row_value(df, row_names):
    """First non-null value (most recent column) for the first matching
    row name in a yfinance income/balance-sheet DataFrame, or None."""
    for name in row_names:
        if name in df.index:
            series = df.loc[name].dropna()
            if not series.empty:
                return float(series.iloc[0])
    return None


def _nearest_price(closes, target_date, tolerance_days=10):
    if closes.empty:
        return None
    idx = closes.index.searchsorted(target_date)
    candidates = [i for i in (idx - 1, idx) if 0 <= i < len(closes)]
    if not candidates:
        return None
    best = min(candidates, key=lambda i: abs(closes.index[i] - target_date))
    if abs(closes.index[best] - target_date).days > tolerance_days:
        return None
    return float(closes.iloc[best]), closes.index[best]


def _returns_5_10_15(closes):
    """closes: a Close-price Series with a DatetimeIndex, oldest first.
    Returns {years: {"pct": float|None, "anchor_date": Timestamp|None,
    "anchor_price": float|None}}. None (not 0) when that horizon predates
    the available history -- e.g. a recent IPO/ETF -- rather than a
    fabricated number."""
    if closes.empty:
        return {
            y: {"pct": None, "anchor_date": None, "anchor_price": None}
            for y in RETURN_HORIZONS_YEARS
        }

    latest_date = closes.index[-1]
    latest_close = float(closes.iloc[-1])
    result = {}
    for years in RETURN_HORIZONS_YEARS:
        target = latest_date - pd.DateOffset(years=years)
        found = _nearest_price(closes, target)
        if found is None:
            result[years] = {"pct": None, "anchor_date": None, "anchor_price": None}
        else:
            price, anchor_date = found
            pct = (latest_close / price - 1) * 100 if price else None
            result[years] = {"pct": pct, "anchor_date": anchor_date, "anchor_price": price}
    return result


def format_returns_cell(returns):
    """e.g. '+150% | +250% | +1500%', 'N/A' per missing horizon."""
    parts = []
    for years in RETURN_HORIZONS_YEARS:
        pct = returns[years]["pct"]
        parts.append("N/A" if pct is None else f"{pct:+.0f}%")
    return " | ".join(parts)


def _growth_flag(returns):
    """green: 5/10/15yr all positive. orange: 15yr positive but 5 or 10
    isn't (or is missing). red: 15yr itself isn't positive. n/a: not
    enough history to say anything about the 15yr horizon at all."""
    r15 = returns[15]["pct"]
    if r15 is None:
        return "n/a"
    if r15 <= 0:
        return "red"
    r5 = returns[5]["pct"]
    r10 = returns[10]["pct"]
    if r5 is not None and r5 > 0 and r10 is not None and r10 > 0:
        return "green"
    return "orange"


def _pe_ratio(info, net_income):
    """trailingPE if usable; else Market Cap / Net Income, only when
    net_income is positive (matches the spreadsheet's own fallback
    rule). Returns (value_or_None, is_fallback)."""
    pe = info.get("trailingPE")
    if pe is not None and pe > 0:
        return pe, False
    market_cap = info.get("marketCap")
    if market_cap and net_income and net_income > 0:
        return market_cap / net_income, True
    return None, False


def pe_style(value):
    # No usable P/E (loss-making, no fallback available either) fails
    # the same "positive earnings" spirit as the EPS>0 rule, so it's
    # treated as a rule failure (red), not neutral missing data (gray).
    if pd.isna(value):
        return COLOR_RED
    return COLOR_GREEN if 0 < value < PE_MAX else COLOR_RED


def eps_style(value):
    if pd.isna(value):
        return COLOR_GRAY
    return COLOR_GREEN if value > 0 else COLOR_RED


def employees_style(value):
    if pd.isna(value):
        return COLOR_GRAY
    return COLOR_GREEN if value >= EMPLOYEE_THRESHOLD else COLOR_RED


def growth_flag_style(flag):
    return GROWTH_FLAG_STYLE.get(flag, "")


def fetch_stock_row(ticker, include_financials):
    """include_financials=True adds Revenue/Net Income/Total Assets/
    Total Liabilities (Growing & Speculative sections); False skips them
    (High Dividend section). Net Income is still fetched either way --
    it's needed internally for the P/E fallback regardless of whether
    it's shown as its own column."""
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        income = t.income_stmt
        net_income = _row_value(income, ["Net Income"])

        result = {"Ticker": ticker, "Error": None}
        result["Sector"] = info.get("sector") or "N/A"

        if include_financials:
            revenue = _row_value(income, ["Total Revenue"])
            balance = t.balance_sheet
            result["Revenue"] = revenue
            result["Net Income"] = net_income
            result["Total Assets"] = _row_value(balance, ["Total Assets"])
            result["Total Liabilities"] = _row_value(balance, LIABILITIES_ROW_CANDIDATES)

        pe, _pe_is_fallback = _pe_ratio(info, net_income)
        result["P/E"] = pe
        result["EPS"] = info.get("trailingEps")
        result["Employees"] = info.get("fullTimeEmployees")
        result["Dividend Yield"] = info.get("dividendYield")  # already a percent, e.g. 6.46 == 6.46%

        history = t.history(period="16y")
        closes = history["Close"] if not history.empty else pd.Series(dtype=float)
        returns = _returns_5_10_15(closes)
        result["Returns"] = returns
        result["Return Display"] = format_returns_cell(returns)
        result["Growth Flag"] = _growth_flag(returns)
        return result
    except Exception as exc:
        return {"Ticker": ticker, "Error": str(exc)}


def fetch_etf_row(ticker):
    try:
        t = yf.Ticker(ticker)
        history = t.history(period="16y")
        closes = history["Close"] if not history.empty else pd.Series(dtype=float)
        returns = _returns_5_10_15(closes)
        return {
            "Ticker": ticker,
            "Error": None,
            "Returns": returns,
            "Return Display": format_returns_cell(returns),
            "Growth Flag": _growth_flag(returns),
        }
    except Exception as exc:
        return {"Ticker": ticker, "Error": str(exc)}


def _clean_tickers(tickers):
    cleaned = []
    seen = set()
    for tk in tickers:
        tk = tk.strip().upper()
        if tk and tk not in seen:
            cleaned.append(tk)
            seen.add(tk)
    return cleaned


def run_batch(tickers, include_financials, progress_callback=None):
    cleaned = _clean_tickers(tickers)
    rows = []
    for i, tk in enumerate(cleaned):
        rows.append(fetch_stock_row(tk, include_financials))
        if progress_callback:
            progress_callback(i + 1, len(cleaned))
    return pd.DataFrame(rows)


def run_etf_batch(tickers, progress_callback=None):
    cleaned = _clean_tickers(tickers)
    rows = []
    for i, tk in enumerate(cleaned):
        rows.append(fetch_etf_row(tk))
        if progress_callback:
            progress_callback(i + 1, len(cleaned))
    return pd.DataFrame(rows)


HORIZON_COLORS = {5: "#2196f3", 10: "#ffa726", 15: "#00bcd4"}


def get_growth_chart_data(ticker, returns):
    """Monthly candles + up to 3 markers + up to 3 horizontal "level"
    lines for the growth-chart drill-down, styled after a
    TradingView-style annotated growth chart: a dashed horizontal line at
    each anchor's price level running forward to today, labeled with the
    trailing return from that point.

    `returns` is the SAME dict already computed (from daily data) for the
    main table's Growth Flag / Return column -- reused here rather than
    recomputed against the monthly series, so the chart's numbers always
    match the table exactly. The daily anchor date is only snapped to the
    nearest monthly bar for where to draw it; the price/pct shown is the
    original daily figure."""
    t = yf.Ticker(ticker)
    hist = t.history(period="16y", interval="1mo")
    if hist.empty:
        return [], [], []

    candles = [
        {
            "time": ts.strftime("%Y-%m-%d"),
            "open": round(float(row["Open"]), 4),
            "high": round(float(row["High"]), 4),
            "low": round(float(row["Low"]), 4),
            "close": round(float(row["Close"]), 4),
        }
        for ts, row in hist.iterrows()
    ]
    latest_time = candles[-1]["time"]
    monthly_index = hist.index

    markers = []
    levels = []
    for years in RETURN_HORIZONS_YEARS:
        info_r = returns[years]
        if info_r["pct"] is None or info_r["anchor_date"] is None:
            continue
        color = HORIZON_COLORS[years]
        # Snap to the nearest monthly bar so the marker/line lands on an
        # actual candle -- the daily anchor date itself won't usually be
        # a bar in this monthly series.
        idx = monthly_index.searchsorted(info_r["anchor_date"])
        idx = min(max(idx, 0), len(monthly_index) - 1)
        anchor_time = monthly_index[idx].strftime("%Y-%m-%d")
        markers.append(
            {
                "time": anchor_time,
                "position": "belowBar",
                "color": color,
                "shape": "arrowUp",
                "text": f"{years}yr: {info_r['pct']:+.0f}%",
            }
        )
        levels.append(
            {
                "years": years,
                "color": color,
                "anchor_time": anchor_time,
                "latest_time": latest_time,
                "price": info_r["anchor_price"],
                "pct": info_r["pct"],
            }
        )
    markers.sort(key=lambda m: m["time"])
    return candles, markers, levels


def get_etf_holdings(ticker):
    """Top-10 holdings sorted largest-to-smallest by weight -- Yahoo's
    free-data ceiling, not a full constituent list (see plan notes)."""
    try:
        top = yf.Ticker(ticker).funds_data.top_holdings
    except Exception:
        top = None
    if top is None or top.empty:
        return pd.DataFrame(columns=["Symbol", "Name", "Weight %"])
    df = top.reset_index().rename(columns={"Holding Percent": "Weight %"})
    df["Weight %"] = (df["Weight %"] * 100).round(2)
    return df.sort_values("Weight %", ascending=False).reset_index(drop=True)
