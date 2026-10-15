"""Offline tests - no ICICI account needed.  Run: python -m unittest test_strategy"""

import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

import pandas as pd

import backtest
import breeze_client as bc
from strategy import BUY, HOLD, SELL, shares_for, signal


def candles(closes, start="2024-01-01"):
    idx = pd.date_range(start, periods=len(closes), freq="D")
    return pd.DataFrame({"open": closes, "high": closes, "low": closes,
                         "close": closes, "volume": 0}, index=idx)


class StrategyTest(unittest.TestCase):
    def test_signal(self):
        self.assertEqual(signal(90, 100, False), BUY)
        self.assertEqual(signal(110, 100, False), HOLD)
        self.assertEqual(signal(110, 100, True), SELL)
        self.assertEqual(signal(90, 100, True), HOLD)
        self.assertEqual(signal(90, float("nan"), False), HOLD)

    def test_whole_shares(self):
        self.assertEqual(shares_for(1000, 333), 3)
        self.assertEqual(shares_for(100, 333), 0)

    def test_backtest_buys_dip_and_sells_recovery(self):
        df = candles([100, 100, 100, 80, 80, 120, 120])
        equity, trades = backtest.run(df, period=3, cash=1000, cost_pct=0)
        self.assertEqual(list(trades["action"]), [BUY, SELL])
        # buys 12 shares at 80 (next open after the dip), sells at 120
        self.assertEqual(list(trades["qty"]), [12, 12])
        self.assertAlmostEqual(equity, 1000 - 12 * 80 + 12 * 120)

    def test_costs_reduce_equity(self):
        df = candles([100, 100, 100, 80, 80, 120, 120])
        free, _ = backtest.run(df, 3, 1000, 0)
        paid, _ = backtest.run(df, 3, 1000, 0.5)
        self.assertLess(paid, free)


class FakeBreeze:
    def __init__(self, closes, ltp):
        self.closes, self.ltp, self.orders = closes, ltp, []

    def get_names(self, exchange_code, stock_code):
        return {"isec_stock_code": "TCS"}

    def get_historical_data_v2(self, **kw):
        start = dt.datetime.strptime(kw["from_date"][:10], "%Y-%m-%d")
        rows = [{"datetime": (start + dt.timedelta(days=i)).strftime("%Y-%m-%d 00:00:00"),
                 "open": c, "high": c, "low": c, "close": c, "volume": 1}
                for i, c in enumerate(self.closes)]
        return {"Status": 200, "Error": None, "Success": rows}

    def get_quotes(self, **kw):
        return {"Status": 200, "Error": None,
                "Success": [{"exchange_code": "NSE", "ltp": self.ltp}]}

    def place_order(self, **kw):
        self.orders.append(kw)
        return {"Status": 200, "Error": None, "Success": {"order_id": "X1"}}


class TradeTest(unittest.TestCase):
    def run_trade(self, fake, *extra):
        import trade
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(bc, "connect", return_value=fake), \
                mock.patch.object(trade.dt, "date", wraps=dt.date) as fake_date, \
                mock.patch.object(sys, "argv", ["trade.py", "--symbol", "TCS", "--sma", "5",
                                                "--capital", "10000", "--state-dir", d, *extra]):
            fake_date.today.return_value = dt.date(2026, 10, 14)  # a Wednesday
            trade.main()
            files = os.listdir(d)
            if not files:
                return None
            with open(os.path.join(d, files[0])) as f:
                return json.load(f)

    def test_paper_buy_places_no_order(self):
        fake = FakeBreeze([100] * 20, ltp=90)
        state = self.run_trade(fake)
        self.assertEqual(fake.orders, [])
        self.assertEqual(state["qty"], 111)
        self.assertEqual(state["trades"][0]["action"], BUY)

    def test_live_buy_places_delivery_order(self):
        fake = FakeBreeze([100] * 20, ltp=90)
        state = self.run_trade(fake, "--live", "--yes")
        self.assertEqual(len(fake.orders), 1)
        o = fake.orders[0]
        self.assertEqual((o["action"], o["product"], o["quantity"], o["exchange_code"]),
                         ("buy", "cash", "111", "NSE"))
        self.assertEqual(state["trades"][0]["order_id"], "X1")

    def test_no_signal_no_state(self):
        fake = FakeBreeze([100] * 20, ltp=105)
        self.assertIsNone(self.run_trade(fake))


if __name__ == "__main__":
    unittest.main()
