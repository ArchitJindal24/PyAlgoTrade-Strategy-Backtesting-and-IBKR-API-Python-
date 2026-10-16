"""UI tests for app.py with a fake Breeze client.  Run: python -m unittest test_app"""

import datetime as dt
import os
import tempfile
import unittest
from unittest import mock

try:
    from streamlit.testing.v1 import AppTest
except ImportError:  # streamlit not installed
    AppTest = None

from test_strategy import FakeBreeze

HERE = os.path.dirname(os.path.abspath(__file__))


@unittest.skipIf(AppTest is None, "streamlit not installed")
class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"SMA_STATE_DIR": self.tmp.name})
        self.env.start()
        # Treat today as a weekday so the trade flow is the same on any day.
        self.today = mock.patch("trade.dt.date", wraps=dt.date)
        self.today.start().today.return_value = dt.date(2026, 10, 14)

    def tearDown(self):
        self.today.stop()
        self.env.stop()
        self.tmp.cleanup()

    def app(self, fake=None):
        at = AppTest.from_file(os.path.join(HERE, "app.py"), default_timeout=30)
        if fake:
            at.session_state["breeze"] = fake
        return at.run()

    def button(self, at, label):
        return next(b for b in at.button if b.label == label)

    def test_sample_backtest(self):
        at = self.app()
        self.button(at, "Run backtest").click().run()
        self.assertFalse(at.exception)
        self.assertEqual([m.label for m in at.metric][:2], ["Best SMA period", "Best strategy return"])

    def test_paper_trade_flow(self):
        fake = FakeBreeze([100] * 40, ltp=90)
        at = self.app(fake)
        self.button(at, "Check today's signal").click().run()
        self.assertFalse(at.exception)
        signal = next(m for m in at.metric if m.label == "Signal")
        self.assertEqual(signal.value, "BUY")

        self.button(at, "Record paper buy").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(fake.orders, [])
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, "state_TCS_paper.json")))
        held = next(m for m in at.metric if m.label == "Shares held")
        self.assertEqual(held.value, "555")

    def test_live_order_needs_confirmation(self):
        fake = FakeBreeze([100] * 40, ltp=90)
        at = self.app(fake)
        at.toggle[0].set_value(True).run()
        self.button(at, "Check today's signal").click().run()
        place = self.button(at, "Place real buy order")
        self.assertTrue(place.disabled)

        at.checkbox[0].check().run()
        self.button(at, "Place real buy order").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(len(fake.orders), 1)
        self.assertEqual(fake.orders[0]["action"], "buy")


if __name__ == "__main__":
    unittest.main()
