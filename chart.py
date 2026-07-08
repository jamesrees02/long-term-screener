"""Fetches OHLC history via yfinance and shapes it for TradingView's
lightweight-charts JS library."""

import yfinance as yf

INTERVALS = {"Daily": "1d", "Weekly": "1wk", "Monthly": "1mo"}
RANGES = {"6M": "6mo", "1Y": "1y", "3Y": "3y", "5Y": "5y", "Max": "max"}


def get_candles(ticker, interval_label, range_label):
    """Returns a list of {time, open, high, low, close} dicts, oldest first,
    ready to hand to lightweight-charts' candlestick series."""
    interval = INTERVALS[interval_label]
    period = RANGES[range_label]
    hist = yf.Ticker(ticker).history(period=period, interval=interval)
    if hist.empty:
        return []
    candles = []
    for ts, row in hist.iterrows():
        candles.append(
            {
                "time": ts.strftime("%Y-%m-%d"),
                "open": round(float(row["Open"]), 4),
                "high": round(float(row["High"]), 4),
                "low": round(float(row["Low"]), 4),
                "close": round(float(row["Close"]), 4),
            }
        )
    return candles
