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


def _series_oldest_to_newest(df, row_name):
    if df.empty or row_name not in df.index:
        return []
    row = df.loc[row_name].dropna()
    row = row.sort_index()  # columns are dates; ascending = oldest first
    return list(row.items())  # [(Timestamp, value), ...]


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

        statements = {"income": income, "balance": balance}
        result = {"ticker": ticker, "error": None}
        scores = []
        for label, (stmt_key, row_name) in TREND_SOURCES.items():
            series = _series_oldest_to_newest(statements[stmt_key], row_name)
            values = [v for _, v in series]
            score, badge = _trend_score(values)
            result[f"{label} Trend"] = badge
            result[f"_{label}_score"] = score
            if score is not None:
                scores.append(score)

        result["Total Score"] = sum(scores) if scores else None

        net_income_series = dict(_series_oldest_to_newest(income, "Net Income"))
        current_liab_series = dict(_series_oldest_to_newest(balance, "Current Liabilities"))
        common_years = sorted(set(net_income_series) & set(current_liab_series))
        coverage = [
            (year, net_income_series[year] >= current_liab_series[year])
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

        cash_series = _series_oldest_to_newest(cashflow, "End Cash Position")
        cash_values = [v for _, v in cash_series]
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
    "Error" column populated instead of trend data)."""
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
                    "Liabilities Coverage": result["Liabilities Coverage"],
                    "All Liabilities Covered": result["_all_liabilities_covered"],
                    "Cash Trend": result["Cash Trend"],
                    "Cash Declining": result["_cash_declining"],
                    "Latest Cash": result["Latest Cash"],
                    "Error": None,
                }
            )
        if progress_callback:
            progress_callback(i + 1, len(cleaned))

    return pd.DataFrame(rows)
