"""Multi-year financial-statement trend analysis via yfinance.

Finviz's own multi-year "Financials" tab doesn't serve historical data to
anonymous (non-logged-in) requests -- confirmed by fetching it directly,
it just repeats the same current-snapshot table the Finviz screener
already provides. yfinance's annual statements give 4-5 years for free,
no login required, so that's the data source here instead.
"""

import pandas as pd
import yfinance as yf

# label -> (statement to pull from, exact yfinance row name)
TREND_SOURCES = {
    "Revenue": ("income", "Total Revenue"),
    "Net Income": ("income", "Net Income"),
    "Total Assets": ("balance", "Total Assets"),
}

BADGE_BY_SCORE = {0: "❌", 1: "✅", 2: "✅⭐"}
NA_BADGE = "N/A"


def format_dollars(value):
    """Formats a raw financial-statement number as e.g. '$451.4B'."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    abs_v = abs(value)
    if abs_v >= 1e9:
        return f"${value / 1e9:,.1f}B"
    if abs_v >= 1e6:
        return f"${value / 1e6:,.1f}M"
    return f"${value:,.0f}"


def _series_oldest_to_newest(df, row_name):
    if df.empty or row_name not in df.index:
        return {}
    row = df.loc[row_name].dropna()
    return {ts.year: value for ts, value in row.items()}


def _trend_score(values):
    """values: oldest->newest list of numbers. Returns (score, badge)."""
    if len(values) < 2:
        return None, NA_BADGE
    base_positive = values[-1] > values[0]
    if not base_positive:
        return 0, BADGE_BY_SCORE[0]
    yoy_all_positive = all(values[i + 1] > values[i] for i in range(len(values) - 1))
    score = 2 if yoy_all_positive else 1
    return score, BADGE_BY_SCORE[score]


def analyze_ticker(ticker):
    """Returns a dict describing the ticker's multi-year trends, or a dict
    with an "error" key if the fetch/parse failed for this ticker."""
    try:
        t = yf.Ticker(ticker)
        income = t.income_stmt
        balance = t.balance_sheet
        cashflow = t.cashflow

        by_year = {
            "Revenue": _series_oldest_to_newest(income, "Total Revenue"),
            "Net Income": _series_oldest_to_newest(income, "Net Income"),
            "Total Assets": _series_oldest_to_newest(balance, "Total Assets"),
            "Current Liabilities": _series_oldest_to_newest(balance, "Current Liabilities"),
            "Cash": _series_oldest_to_newest(cashflow, "End Cash Position"),
        }

        all_years = sorted(set().union(*by_year.values()))
        history = [
            {"Year": year, **{label: by_year[label].get(year) for label in by_year}}
            for year in all_years
        ]

        result = {"ticker": ticker, "error": None, "history": history}

        scores = []
        for label, (_, _) in TREND_SOURCES.items():
            years = sorted(by_year[label])
            values = [by_year[label][y] for y in years]
            score, badge = _trend_score(values)
            result[f"{label} Trend"] = badge
            result[f"Latest {label}"] = values[-1] if values else None
            if score is not None:
                scores.append(score)
        result["Total Score"] = sum(scores) if scores else None

        common_years = sorted(set(by_year["Net Income"]) & set(by_year["Current Liabilities"]))
        coverage = [
            (year, by_year["Net Income"][year] >= by_year["Current Liabilities"][year])
            for year in common_years
        ]
        result["Liabilities Coverage"] = (
            "".join("✅" if covered else "❌" for _, covered in coverage)
            if coverage
            else NA_BADGE
        )
        result["_all_liabilities_covered"] = (
            all(covered for _, covered in coverage) if coverage else None
        )
        result["Latest Current Liabilities"] = (
            by_year["Current Liabilities"][common_years[-1]] if common_years else None
        )

        cash_years = sorted(by_year["Cash"])
        cash_values = [by_year["Cash"][y] for y in cash_years]
        result["Cash Trend"] = cash_values if cash_values else None
        result["_cash_declining"] = (
            cash_values[-1] < cash_values[-2] if len(cash_values) >= 2 else None
        )
        result["Latest Cash"] = cash_values[-1] if cash_values else None

        return result
    except Exception as exc:
        return {"ticker": ticker, "error": str(exc)}


def run_batch(tickers, progress_callback=None):
    """tickers: list of ticker strings. progress_callback(done, total), if
    given, is called after each ticker completes. Returns a DataFrame, one
    row per ticker (rows with fetch errors still appear, with an
    "Error" column populated instead of trend data). The "History" column
    holds each ticker's full year-by-year breakdown (list of dicts) for
    drill-down, and isn't meant to be displayed directly."""
    cleaned = []
    seen = set()
    for tk in tickers:
        tk = tk.strip().upper()
        if tk and tk not in seen:
            cleaned.append(tk)
            seen.add(tk)

    rows = []
    for i, tk in enumerate(cleaned):
        result = analyze_ticker(tk)
        if result.get("error"):
            rows.append({"Ticker": tk, "Error": result["error"]})
        else:
            rows.append(
                {
                    "Ticker": result["ticker"],
                    "Revenue Trend": result["Revenue Trend"],
                    "Net Income Trend": result["Net Income Trend"],
                    "Total Assets Trend": result["Total Assets Trend"],
                    "Total Score": result["Total Score"],
                    "Latest Revenue": result["Latest Revenue"],
                    "Latest Net Income": result["Latest Net Income"],
                    "Latest Total Assets": result["Latest Total Assets"],
                    "Latest Current Liabilities": result["Latest Current Liabilities"],
                    "Liabilities Coverage": result["Liabilities Coverage"],
                    "All Liabilities Covered": result["_all_liabilities_covered"],
                    "Cash Trend": result["Cash Trend"],
                    "Cash Declining": result["_cash_declining"],
                    "Latest Cash": result["Latest Cash"],
                    "History": result["history"],
                    "Error": None,
                }
            )
        if progress_callback:
            progress_callback(i + 1, len(cleaned))

    return pd.DataFrame(rows)
