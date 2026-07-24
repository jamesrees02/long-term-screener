"""Portfolio Builder fetchers for a personal 4-section target-allocation
tracker (Growing Stocks, ETFs, High Dividend Stocks, Speculative Stocks).

Quote snapshot fields (P/E, EPS, Employees, Dividend Yield) come from
Finviz. Multi-year financials and price history still come from yfinance
-- Finviz's free quote page is a current snapshot only.
"""

import re

import pandas as pd
import yfinance as yf
from finvizfinance.util import web_scrap

RETURN_HORIZONS_YEARS = [5, 10, 15]
EMPLOYEE_THRESHOLD = 10_000
PE_MAX = 100

LIABILITIES_ROW_CANDIDATES = ["Total Liabilities Net Minority Interest", "Total Liab"]
FINVIZ_QUOTE_URL = "https://finviz.com/quote.ashx?t={ticker}"

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


def _returns_5_10_15(closes):
    """closes: monthly Close series (DatetimeIndex, oldest first).

    For each horizon, walk back ``years * 12`` monthly bars from the latest
    bar -- e.g. Jul 2026 current → Aug 2021 for 5yr (60 months inclusive).
    Returns {years: {"pct", "anchor_date", "anchor_price"}} plus
    latest_price / latest_date for tooltips. Horizon values are None when
    that many bars aren't available (recent IPO/ETF), not a fabricated 0."""
    empty_horizons = {
        y: {"pct": None, "anchor_date": None, "anchor_price": None}
        for y in RETURN_HORIZONS_YEARS
    }
    if closes.empty:
        return {**empty_horizons, "latest_price": None, "latest_date": None}

    latest_close = float(closes.iloc[-1])
    result = {"latest_price": latest_close, "latest_date": closes.index[-1]}
    for years in RETURN_HORIZONS_YEARS:
        months = years * 12
        # Last `months` bars: iloc[-months] .. iloc[-1]. Start bar is Aug
        # when latest is Jul and months=60.
        if len(closes) < months:
            result[years] = {"pct": None, "anchor_date": None, "anchor_price": None}
            continue
        anchor_date = closes.index[-months]
        price = float(closes.iloc[-months])
        pct = (latest_close / price - 1) * 100 if price else None
        result[years] = {"pct": pct, "anchor_date": anchor_date, "anchor_price": price}
    return result


def _fmt_month_year(ts):
    if ts is None or (isinstance(ts, float) and pd.isna(ts)):
        return None
    ts = pd.Timestamp(ts)
    return ts.strftime("%b %Y")


def _fmt_price(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "N/A"
    return f"${value:,.2f}"


def growth_price_rows(returns):
    """[(label, price_str, month_year_or_None), ...] for Current/5yr/10yr/15yr."""
    rows = [
        (
            "Current",
            _fmt_price(returns.get("latest_price")),
            _fmt_month_year(returns.get("latest_date")),
        )
    ]
    for years in RETURN_HORIZONS_YEARS:
        info = returns[years]
        rows.append(
            (
                f"{years}yr",
                _fmt_price(info["anchor_price"]),
                _fmt_month_year(info["anchor_date"]),
            )
        )
    return rows


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


def _finviz_number(value):
    """Parse a Finviz snapshot cell to float. Returns None for blanks,
    dashes, or non-numeric placeholders."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"-", "—", "- -"}:
        return None
    text = text.replace(",", "").replace("%", "")
    # Values like "5.24 (1.99%)" — caller should use the dedicated
    # dividend helper; here take the leading number.
    text = text.split("(")[0].strip()
    try:
        return float(text)
    except ValueError:
        return None


def _finviz_dividend_yield_pct(dividend_ttm):
    """Finviz 'Dividend TTM' looks like '5.24 (1.99%)' or '-'. Return the
    yield percent (1.99), matching the table's '{:.2f}%' formatter."""
    if dividend_ttm is None:
        return None
    text = str(dividend_ttm).strip()
    if not text or text in {"-", "—"}:
        return None
    match = re.search(r"\(([\d.]+)\s*%\)", text)
    if match:
        return float(match.group(1))
    # Bare percent cell (rare) — treat as already in percent units only
    # when the string itself ends with %.
    if text.endswith("%"):
        return _finviz_number(text)
    return None


def _fetch_finviz_quote_fields(ticker):
    """Current Finviz quote snapshot for P/E, EPS (ttm), Employees, and
    Dividend Yield. Parses all snapshot-table2 blocks — Finviz split the
    old multi-column table into several 2-column tables, which breaks
    finvizfinance.ticker_fundament()."""
    soup = web_scrap(FINVIZ_QUOTE_URL.format(ticker=ticker))
    fund = {}
    for table in soup.find_all("table", class_="snapshot-table2"):
        for row in table.find_all("tr"):
            cols = [c.get_text(strip=True) for c in row.find_all("td")]
            for i in range(0, len(cols) - 1, 2):
                fund[cols[i]] = cols[i + 1]

    employees = _finviz_number(fund.get("Employees"))
    return {
        "P/E": _finviz_number(fund.get("P/E")),
        "EPS": _finviz_number(fund.get("EPS (ttm)")),
        "Employees": int(employees) if employees is not None else None,
        "Dividend Yield": _finviz_dividend_yield_pct(fund.get("Dividend TTM")),
    }


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
    (High Dividend section). P/E, EPS, Employees, and Dividend Yield are
    always from Finviz; growth history stays on yfinance."""
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}

        result = {"Ticker": ticker, "Error": None}
        result["Sector"] = info.get("sector") or "N/A"

        if include_financials:
            income = t.income_stmt
            ttm_income = t.ttm_income_stmt
            balance = t.balance_sheet
            # Prefer TTM revenue (matches Finviz "Sales"); fall back to the
            # latest annual figure when TTM isn't available.
            result["Revenue"] = _row_value(ttm_income, ["Total Revenue"]) or _row_value(
                income, ["Total Revenue"]
            )
            result["Net Income"] = _row_value(income, ["Net Income"])
            result["Total Assets"] = _row_value(balance, ["Total Assets"])
            result["Total Liabilities"] = _row_value(balance, LIABILITIES_ROW_CANDIDATES)

        try:
            fv = _fetch_finviz_quote_fields(ticker)
        except Exception:
            fv = {
                "P/E": None,
                "EPS": None,
                "Employees": None,
                "Dividend Yield": None,
            }
        result["P/E"] = fv["P/E"]
        result["EPS"] = fv["EPS"]
        result["Employees"] = fv["Employees"]
        result["Dividend Yield"] = fv["Dividend Yield"]

        history = t.history(period="16y", interval="1mo")
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
        history = t.history(period="16y", interval="1mo")
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
    """Monthly candles + up to 3 markers + up to 3 growth-block "levels"
    for the Portfolio Builder drill-down chart.

    Each level spans its exclusive bucket start → today and includes the
    anchor price, latest close, dollar delta, and trailing %.

    `returns` is the SAME monthly-bar dict already computed for the table's
    Growth Flag / Return column -- reused here so chart labels always match
    the table. Anchor dates are already monthly bar timestamps."""
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
    latest_price = float(hist["Close"].iloc[-1])

    markers = []
    levels = []
    for years in RETURN_HORIZONS_YEARS:
        info_r = returns[years]
        if info_r["pct"] is None or info_r["anchor_date"] is None:
            continue
        color = HORIZON_COLORS[years]
        anchor_time = pd.Timestamp(info_r["anchor_date"]).strftime("%Y-%m-%d")
        anchor_price = info_r["anchor_price"]
        dollar_delta = (
            None if anchor_price is None else latest_price - float(anchor_price)
        )
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
                "price": anchor_price,
                "latest_price": latest_price,
                "dollar_delta": dollar_delta,
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
