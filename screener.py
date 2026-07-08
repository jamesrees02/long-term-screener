"""Finviz screening logic: dropdown filters applied server-side, numeric
range filters applied locally on the real fetched values (so the user gets
true from/to sliders instead of Finviz's preset buckets)."""

from finvizfinance.screener.custom import Custom
from finvizfinance.screener.base import filter_dict
from finvizfinance.constants import CUSTOM_SCREENER_COLUMNS

# Column index -> long display name, for every index we might request.
COLUMN_NAME_BY_INDEX = CUSTOM_SCREENER_COLUMNS

# Max rows fetched from Finviz per screen. Finviz paginates 20 rows/request
# with a polite delay between pages, so an uncapped broad filter (e.g. just
# "Sector = Technology") can take a minute or more to fetch in full.
RESULT_LIMIT = 200

# Dropdown filters: applied via Finviz's own set_filter. label -> filter_dict key.
CATEGORICAL_FILTERS = {
    "Exchange": "Exchange",
    "Index": "Index",
    "Sector": "Sector",
    "Industry": "Industry",
    "Country": "Country",
    "Analyst Recom.": "Analyst Recom.",
    "Option/Short": "Option/Short",
    "Earnings Date": "Earnings Date",
    "IPO Date": "IPO Date",
    "Candlestick Pattern": "Candlestick",
    "Chart Pattern": "Pattern",
}

# Numeric filters: applied locally as a from/to slider on the real fetched
# value. Each entry: label -> (column_index, min, max, step, scale, suffix)
# `scale` converts the raw fetched value into slider units
# (e.g. Finviz returns Dividend Yield as a fraction like 0.035; scale=100
# turns that into 3.5 for a "%"-labeled slider).
NUMERIC_FILTERS = {
    "Market Cap ($B)": (6, 0.0, 3500.0, 10.0, 1e-9, "B"),
    "P/E": (7, 0.0, 200.0, 1.0, 1, ""),
    "Forward P/E": (8, 0.0, 200.0, 1.0, 1, ""),
    "PEG": (9, 0.0, 10.0, 0.1, 1, ""),
    "P/S": (10, 0.0, 50.0, 0.5, 1, ""),
    "P/B": (11, 0.0, 50.0, 0.5, 1, ""),
    "Price/Cash": (12, 0.0, 50.0, 0.5, 1, ""),
    "Price/Free Cash Flow": (13, 0.0, 100.0, 1.0, 1, ""),
    "Dividend Yield (%)": (14, 0.0, 15.0, 0.1, 100, "%"),
    "Payout Ratio (%)": (15, 0.0, 200.0, 5.0, 100, "%"),
    "EPS Growth This Year (%)": (17, -100.0, 300.0, 5.0, 100, "%"),
    "EPS Growth Next Year (%)": (18, -100.0, 300.0, 5.0, 100, "%"),
    "EPS Growth Past 5Y (%)": (19, -100.0, 300.0, 5.0, 100, "%"),
    "EPS Growth Next 5Y (%)": (20, -100.0, 300.0, 5.0, 100, "%"),
    "Sales Growth Past 5Y (%)": (21, -100.0, 300.0, 5.0, 100, "%"),
    "Shares Outstanding (M)": (24, 0.0, 20000.0, 50.0, 1e-6, "M"),
    "Float (M)": (25, 0.0, 20000.0, 50.0, 1e-6, "M"),
    "Insider Ownership (%)": (26, 0.0, 100.0, 1.0, 100, "%"),
    "Institutional Ownership (%)": (28, 0.0, 100.0, 1.0, 100, "%"),
    "Float Short (%)": (30, 0.0, 50.0, 1.0, 100, "%"),
    "Return on Assets (%)": (32, -100.0, 200.0, 5.0, 100, "%"),
    "Return on Equity (%)": (33, -200.0, 500.0, 5.0, 100, "%"),
    "Return on Investment (%)": (34, -200.0, 500.0, 5.0, 100, "%"),
    "Current Ratio": (35, 0.0, 20.0, 0.5, 1, ""),
    "Quick Ratio": (36, 0.0, 20.0, 0.5, 1, ""),
    "LT Debt/Equity": (37, 0.0, 10.0, 0.1, 1, ""),
    "Debt/Equity": (38, 0.0, 10.0, 0.1, 1, ""),
    "Gross Margin (%)": (39, -50.0, 100.0, 1.0, 100, "%"),
    "Operating Margin (%)": (40, -200.0, 100.0, 1.0, 100, "%"),
    "Net Profit Margin (%)": (41, -200.0, 100.0, 1.0, 100, "%"),
    "Performance 1Y (%)": (46, -95.0, 1000.0, 5.0, 100, "%"),
    "Performance YTD (%)": (47, -95.0, 500.0, 5.0, 100, "%"),
    "Beta": (48, -2.0, 4.0, 0.1, 1, ""),
    "20-Day SMA Distance (%)": (52, -80.0, 200.0, 1.0, 100, "%"),
    "50-Day SMA Distance (%)": (53, -80.0, 200.0, 1.0, 100, "%"),
    "200-Day SMA Distance (%)": (54, -80.0, 200.0, 1.0, 100, "%"),
    "RSI (14)": (59, 0.0, 100.0, 1.0, 1, ""),
    "Analyst Recom. (1=Buy..5=Sell)": (62, 1.0, 5.0, 0.1, 1, ""),
    "Average Volume (M shares)": (63, 0.0, 200.0, 1.0, 1e-6, "M"),
    "Relative Volume": (64, 0.0, 20.0, 0.1, 1, ""),
    "Price ($)": (65, 0.0, 2000.0, 5.0, 1, ""),
    "Target Price ($)": (69, 0.0, 2000.0, 5.0, 1, ""),
}

DEFAULT_DISPLAY_COLUMNS = [
    "Ticker",
    "Company",
    "Sector",
    "Market Cap.",
    "P/E",
    "Dividend Yield",
    "Price",
    "Performance (YearToDate)",
]

# Any display column index >= 71 is skipped in Finviz's own table (72 has no
# defined name); everything else in CUSTOM_SCREENER_COLUMNS is fair game.
ALL_DISPLAY_COLUMNS = [name for name in CUSTOM_SCREENER_COLUMNS.values()]


def _index_for_column_name(name):
    for idx, col_name in CUSTOM_SCREENER_COLUMNS.items():
        if col_name == name:
            return idx
    raise KeyError(f"Unknown column name: {name}")


def run_screen(categorical_choices, numeric_choices, display_columns):
    """categorical_choices: {label: chosen_option_label or None}
    numeric_choices: {label: (from_value, to_value)}
    display_columns: ordered list of long column names the user wants shown.

    Returns a pandas DataFrame with exactly `display_columns` as headers, in
    that order, filtered by both the categorical and numeric selections.
    """
    custom = Custom()

    finviz_filters = {}
    for label, chosen in categorical_choices.items():
        if chosen and chosen != "Any":
            finviz_filters[CATEGORICAL_FILTERS[label]] = chosen
    if finviz_filters:
        custom.set_filter(filters_dict=finviz_filters)

    # Always fetch Ticker/Company plus every column needed for display or
    # for a numeric filter, then rename positionally to avoid finvizfinance's
    # internal short-name collisions (e.g. "Dividend Yield" vs "Dividend").
    needed_indices = [1, 2]  # Ticker, Company
    for name in display_columns:
        idx = _index_for_column_name(name)
        if idx not in needed_indices:
            needed_indices.append(idx)
    for label in numeric_choices:
        idx = NUMERIC_FILTERS[label][0]
        if idx not in needed_indices:
            needed_indices.append(idx)
    needed_indices.sort()

    # finvizfinance mutates the `columns` list it's given (inserting a hidden
    # row-index column), so pass a copy to keep needed_indices trustworthy.
    # Its default limit=-1 only fetches the first 20-row page (alphabetical
    # by ticker) rather than every matching page, so it must be overridden.
    # Sorting by Market Cap (largest first) and capping at RESULT_LIMIT keeps
    # broad, unnarrowed filters fast and surfaces the most established
    # companies first, rather than an arbitrary alphabetical slice.
    df = custom.screener_view(
        columns=needed_indices.copy(),
        order="Market Cap.",
        ascend=False,
        limit=RESULT_LIMIT,
        verbose=0,
    )
    df.columns = [COLUMN_NAME_BY_INDEX[i] for i in needed_indices]

    for label, (from_val, to_val) in numeric_choices.items():
        idx, default_lo, default_hi, _, scale, _ = NUMERIC_FILTERS[label]
        if from_val <= default_lo and to_val >= default_hi:
            # Slider left at its full range: treat as "no filter" rather than
            # excluding every stock with a missing (NaN) value for this field.
            continue
        col_name = COLUMN_NAME_BY_INDEX[idx]
        scaled = df[col_name] * scale
        df = df[(scaled >= from_val) & (scaled <= to_val)]

    ordered_cols = [c for c in display_columns if c in df.columns]
    return df[ordered_cols].reset_index(drop=True)


def categorical_options(label):
    key = CATEGORICAL_FILTERS[label]
    return list(filter_dict[key]["option"].keys())


def column_format_map():
    """long column name -> (scale, suffix) for presentation, derived from
    NUMERIC_FILTERS. Lets the UI show '3.50%' instead of a raw 0.035."""
    result = {}
    for idx, lo, hi, step, scale, suffix in NUMERIC_FILTERS.values():
        col_name = COLUMN_NAME_BY_INDEX[idx]
        if scale != 1 or suffix:
            result[col_name] = (scale, suffix)
    return result
