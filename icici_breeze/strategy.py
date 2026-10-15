"""SMA mean-reversion strategy, shared by the backtester and the live/paper trader.

Same rule as BacktestingProgram.py:
  - flat and close < SMA  -> buy
  - long and close > SMA  -> sell
"""

import pandas as pd

BUY = "BUY"
SELL = "SELL"
HOLD = "HOLD"


def add_sma(df, period):
    """Return a copy of an OHLC DataFrame with an 'sma' column on the close."""
    out = df.copy()
    out["sma"] = out["close"].rolling(period).mean()
    return out


def signal(close, sma, holding):
    """Decide what to do on a bar, given whether we currently hold shares."""
    if sma is None or pd.isna(sma):
        return HOLD
    if not holding and close < sma:
        return BUY
    if holding and close > sma:
        return SELL
    return HOLD


def shares_for(cash, price):
    """Whole shares affordable with the available cash (NSE has no fractional shares)."""
    if price <= 0:
        return 0
    return int(cash // price)
