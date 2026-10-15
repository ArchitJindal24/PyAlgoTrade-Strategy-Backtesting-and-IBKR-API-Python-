"""Run the SMA strategy once against live ICICI prices. Paper trading by default.

Meant to be scheduled once a day shortly before market close (e.g. 15:15 IST,
Mon-Fri) with cron or Windows Task Scheduler. Each run:
  1. downloads recent daily candles and the current price,
  2. treats the current price as today's close and computes the SMA signal,
  3. buys or sells - simulated (default) or for real with --live.

Position and cash are tracked in a JSON state file, one per symbol and mode.

Examples:
  python trade.py --symbol TCS --sma 20 --capital 50000            # paper
  python trade.py --symbol TCS --sma 20 --capital 50000 --live     # real orders
"""

import argparse
import datetime as dt
import json
import os

import breeze_client as bc
from strategy import BUY, SELL, add_sma, shares_for, signal


def load_state(path, capital):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"cash": capital, "qty": 0, "trades": []}


def save_state(path, state):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, path)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbol", required=True, help="NSE symbol, e.g. TCS")
    p.add_argument("--sma", type=int, default=20)
    p.add_argument("--capital", type=float, default=50000.0, help="INR the strategy may use")
    p.add_argument("--max-qty", type=int, default=1000, help="safety cap on shares per order")
    p.add_argument("--live", action="store_true", help="place REAL orders (default: paper)")
    p.add_argument("--yes", action="store_true", help="skip the live-order confirmation prompt")
    p.add_argument("--state-dir", default=".")
    args = p.parse_args()

    if dt.date.today().weekday() >= 5:
        print("Weekend - NSE is closed, nothing to do.")
        return

    mode = "live" if args.live else "paper"
    state_path = os.path.join(args.state_dir, "state_%s_%s.json" % (args.symbol.upper(), mode))
    state = load_state(state_path, args.capital)

    breeze = bc.connect()
    code = bc.isec_code(breeze, args.symbol)

    end = dt.datetime.now()
    start = end - dt.timedelta(days=args.sma * 3 + 30)  # enough trading days for the SMA
    df = bc.fetch_history(breeze, code, start, end, interval="1day")
    price = bc.last_price(breeze, code)

    # Replace/append today's candle with the live price so the SMA includes it.
    today = dt.datetime.combine(dt.date.today(), dt.time())
    df = df[df.index.normalize() < today]
    df.loc[today, ["open", "high", "low", "close", "volume"]] = [price, price, price, price, 0]
    data = add_sma(df, args.sma)
    sma = data["sma"].iloc[-1]

    holding = state["qty"] > 0
    action = signal(price, sma, holding)
    print("[%s] %s (%s) price=%.2f SMA%d=%.2f qty=%d cash=%.2f -> %s"
          % (mode.upper(), args.symbol, code, price, args.sma, sma, state["qty"], state["cash"], action))

    if action == BUY:
        qty = min(shares_for(state["cash"], price), args.max_qty)
    elif action == SELL:
        qty = state["qty"]
    else:
        return
    if qty <= 0:
        print("Not enough cash for one share.")
        return

    order_id = None
    if args.live:
        if not args.yes:
            ok = input("Place REAL %s order for %d %s at ~Rs %.2f? [y/N] " % (action, qty, args.symbol, price))
            if ok.strip().lower() != "y":
                print("Cancelled.")
                return
        order_id = bc.place_delivery_order(breeze, code, action, qty)
        print("Order placed: %s (check fill status in ICICI Direct before the next run)" % order_id)

    # Paper fills are assumed at the current price. In live mode the actual fill
    # may differ slightly; the state file records the price seen when ordering.
    if action == BUY:
        state["cash"] -= qty * price
        state["qty"] += qty
    else:
        state["cash"] += qty * price
        state["qty"] = 0
    state["trades"].append({
        "time": dt.datetime.now().isoformat(timespec="seconds"),
        "action": action, "qty": qty, "price": price, "order_id": order_id,
    })
    save_state(state_path, state)
    print("Equity: Rs %.2f (state saved to %s)" % (state["cash"] + state["qty"] * price, state_path))


if __name__ == "__main__":
    main()
