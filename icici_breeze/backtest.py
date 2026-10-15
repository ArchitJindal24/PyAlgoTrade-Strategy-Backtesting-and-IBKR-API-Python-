"""Backtest the SMA strategy on NSE data from ICICI Breeze (or a saved CSV).

Examples:
  # download 5 years of TCS daily candles, save them, and sweep SMA 8..29
  python backtest.py --symbol TCS --years 5 --save tcs.csv

  # re-run offline on the saved file
  python backtest.py --csv tcs.csv --sma 20
"""

import argparse
import datetime as dt

import pandas as pd

from strategy import BUY, SELL, add_sma, shares_for, signal


def run(df, period, cash=100000.0, cost_pct=0.12):
    """Simulate the strategy. Signals use a bar's close and fill at the next bar's open.

    cost_pct is charged on each buy and sell (brokerage + STT + exchange fees + stamp duty + GST).
    Returns (final_equity, trades DataFrame).
    """
    data = add_sma(df, period)
    qty = 0
    trades = []
    pending = None

    for ts, row in data.iterrows():
        if pending == BUY:
            price = row["open"]
            n = shares_for(cash / (1 + cost_pct / 100), price)
            if n > 0:
                cost = n * price * (1 + cost_pct / 100)
                cash -= cost
                qty = n
                trades.append((ts, BUY, n, price, cash))
        elif pending == SELL and qty > 0:
            price = row["open"]
            cash += qty * price * (1 - cost_pct / 100)
            trades.append((ts, SELL, qty, price, cash))
            qty = 0
        pending = None

        s = signal(row["close"], row["sma"], qty > 0)
        if s in (BUY, SELL):
            pending = s

    equity = cash + qty * data["close"].iloc[-1]
    return equity, pd.DataFrame(trades, columns=["datetime", "action", "qty", "price", "cash_after"])


def load(args):
    if args.csv and not args.symbol:
        df = pd.read_csv(args.csv, parse_dates=["datetime"], index_col="datetime")
        return df.sort_index()

    import breeze_client as bc

    breeze = bc.connect()
    code = bc.isec_code(breeze, args.symbol)
    end = dt.datetime.now()
    start = end - dt.timedelta(days=int(365 * args.years))
    df = bc.fetch_history(breeze, code, start, end, interval=args.interval)
    if args.save:
        df.to_csv(args.save)
        print("Saved %d candles to %s" % (len(df), args.save))
    return df


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbol", help="NSE symbol to download, e.g. TCS, INFY, RELIANCE")
    p.add_argument("--csv", help="CSV with datetime,open,high,low,close,volume columns")
    p.add_argument("--save", help="save downloaded candles to this CSV")
    p.add_argument("--years", type=float, default=5)
    p.add_argument("--interval", default="1day", choices=["1minute", "5minute", "30minute", "1day"])
    p.add_argument("--cash", type=float, default=100000.0, help="starting capital in INR")
    p.add_argument("--cost", type=float, default=0.12, help="round-trip cost per side, in percent")
    p.add_argument("--sma", type=int, help="single SMA period (default: sweep 8..29)")
    p.add_argument("--show-trades", action="store_true")
    args = p.parse_args()
    if not args.symbol and not args.csv:
        p.error("give --symbol or --csv")

    df = load(args)
    print("%d candles from %s to %s" % (len(df), df.index[0], df.index[-1]))
    buy_hold = args.cash / df["open"].iloc[0] * df["close"].iloc[-1]
    print("Buy & hold: Rs %.2f\n" % buy_hold)

    periods = [args.sma] if args.sma else range(8, 30)
    print("SMA\tFinal equity (Rs)\tReturn\tTrades")
    for period in periods:
        equity, trades = run(df, period, args.cash, args.cost)
        ret = (equity / args.cash - 1) * 100
        print("%d\t%.2f\t\t%+.1f%%\t%d" % (period, equity, ret, len(trades)))
        if args.show_trades and args.sma:
            print(trades.to_string(index=False))


if __name__ == "__main__":
    main()
