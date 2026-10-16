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


def state_path(state_dir, symbol, live):
    return os.path.join(state_dir, "state_%s_%s.json" % (symbol.upper(), "live" if live else "paper"))


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


def evaluate(breeze, symbol, sma_period, state, max_qty=1000):
    """Compute today's signal from live data. Returns a dict describing the decision."""
    code = bc.isec_code(breeze, symbol)
    end = dt.datetime.now()
    start = end - dt.timedelta(days=sma_period * 3 + 30)  # enough trading days for the SMA
    df = bc.fetch_history(breeze, code, start, end, interval="1day")
    price = bc.last_price(breeze, code)

    # Replace/append today's candle with the live price so the SMA includes it.
    today = dt.datetime.combine(dt.date.today(), dt.time())
    df = df[df.index.normalize() < today]
    df.loc[today, ["open", "high", "low", "close", "volume"]] = [price, price, price, price, 0]
    data = add_sma(df, sma_period)
    sma = data["sma"].iloc[-1]

    action = signal(price, sma, state["qty"] > 0)
    if action == BUY:
        qty = min(shares_for(state["cash"], price), max_qty)
    elif action == SELL:
        qty = state["qty"]
    else:
        qty = 0
    return {"symbol": symbol.upper(), "code": code, "price": price, "sma": sma,
            "action": action, "qty": qty, "history": data}


def record(state, action, qty, price, order_id=None):
    """Update cash/position for a fill. Paper fills are assumed at the given price."""
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
    return state


def execute(breeze, decision, state, path, live):
    """Act on a decision from evaluate(): place the order if live, then save the state."""
    order_id = None
    if live:
        order_id = bc.place_delivery_order(breeze, decision["code"], decision["action"], decision["qty"])
    record(state, decision["action"], decision["qty"], decision["price"], order_id)
    save_state(path, state)
    return order_id


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
    path = state_path(args.state_dir, args.symbol, args.live)
    state = load_state(path, args.capital)

    breeze = bc.connect()
    d = evaluate(breeze, args.symbol, args.sma, state, args.max_qty)
    print("[%s] %s (%s) price=%.2f SMA%d=%.2f qty=%d cash=%.2f -> %s"
          % (mode.upper(), args.symbol, d["code"], d["price"], args.sma, d["sma"],
             state["qty"], state["cash"], d["action"]))

    if d["action"] not in (BUY, SELL):
        return
    if d["qty"] <= 0:
        print("Not enough cash for one share.")
        return

    if args.live and not args.yes:
        ok = input("Place REAL %s order for %d %s at ~Rs %.2f? [y/N] "
                   % (d["action"], d["qty"], args.symbol, d["price"]))
        if ok.strip().lower() != "y":
            print("Cancelled.")
            return

    order_id = execute(breeze, d, state, path, args.live)
    if order_id:
        print("Order placed: %s (check fill status in ICICI Direct before the next run)" % order_id)
    print("Equity: Rs %.2f (state saved to %s)" % (state["cash"] + state["qty"] * d["price"], path))


if __name__ == "__main__":
    main()
