# SMA strategy on NSE via ICICI Direct (Breeze API)

A port of `BacktestingProgram.py` to Indian markets using ICICI Direct's free
[Breeze API](https://api.icicidirect.com/breezeapi/documents/index.html).
No PyAlgoTrade needed.

## Web app (easiest)

**Windows:** double-click `start_app.bat`. **Mac/Linux:** run `./start_app.sh`.
The first start creates a virtual environment and installs everything (needs
Python 3.9+), then your browser opens the app at <http://localhost:8501>.

- **Sidebar** - paste your API key and secret, click the link to get today's
  session token, paste it, and press **Connect**. Credentials stay in memory
  and are never written to disk.
- **Backtest tab** - pick ICICI data (any NSE symbol), a CSV, or random sample
  data; choose the SMA range, capital and costs. You get the return for every
  SMA period against buy & hold, the price chart with each buy/sell, the
  portfolio value over time, and CSV downloads.
- **Trade tab** - check today's signal for a symbol and record a paper trade,
  or switch on **Live trading** and tick the confirmation to send a real
  delivery order. Cash, shares and trade history are kept per symbol and mode.

The app only listens on your own computer (`localhost`), because it can place orders.

## Files

| File | What it does |
|---|---|
| `app.py` | The web app (Streamlit) |
| `strategy.py` | The SMA rule: buy when close < SMA, sell when close > SMA |
| `backtest.py` | Downloads NSE history from Breeze (or reads a CSV) and sweeps SMA periods 8-29 |
| `trade.py` | Runs the strategy once on live prices - **paper trading by default**, real CNC orders with `--live` |
| `breeze_client.py` | Login, historical data, quotes and order placement |
| `test_strategy.py`, `test_app.py` | Offline tests with a fake Breeze client |

Fixes compared with the original backtester: whole-share quantities, position
size from *current* cash (not the starting amount), and trading costs.

## Command-line setup

1. Have an ICICI Direct trading + demat account.
2. Register an app at <https://api.icicidirect.com/apiuser/home> to get an
   **API key** and **secret**. Under SEBI's retail algo rules you must also
   register the **static IP** you will trade from with ICICI.
3. Install into a virtual environment (Python 3.9+):
   ```
   python -m venv .venv
   .venv\Scripts\activate        # Windows  (Mac/Linux: source .venv/bin/activate)
   pip install -r requirements.txt
   ```
   Installing `breeze-connect` into the system Python of some Linux distributions
   fails with `AttributeError: install_layout`; a virtual environment avoids it.
4. Every trading day, get a session token: open
   `https://api.icicidirect.com/apiuser/login?api_key=<your URL-encoded API key>`,
   log in, and copy the `apisession` value from the URL you are redirected to.
5. Set the credentials as environment variables (never commit them):
   ```
   # Windows (PowerShell)
   $env:BREEZE_API_KEY="..."; $env:BREEZE_API_SECRET="..."; $env:BREEZE_SESSION_TOKEN="..."
   # Linux / macOS
   export BREEZE_API_KEY=... BREEZE_API_SECRET=... BREEZE_SESSION_TOKEN=...
   ```

## Backtest

```
python backtest.py --symbol TCS --years 5 --save tcs.csv   # download + sweep SMA 8..29
python backtest.py --csv tcs.csv --sma 20 --show-trades     # offline, one period
```

Use NSE symbols (`TCS`, `INFY`, `RELIANCE`); they are mapped to ICICI's own
codes (e.g. `RELIANCE` -> `RELIND`) automatically. `--cost` sets the cost per
buy/sell in percent (default 0.12%: STT, exchange fees, stamp duty, GST and
brokerage - adjust to your ICICI plan).

## Paper / live trading

```
python trade.py --symbol TCS --sma 20 --capital 50000          # paper
python trade.py --symbol TCS --sma 20 --capital 50000 --live   # real delivery orders, asks to confirm
```

Schedule it once per trading day around 15:15 IST (cron or Windows Task
Scheduler). It uses the current price as today's close, and keeps cash and
position in `state_<SYMBOL>_<paper|live>.json`.

Things to know before using `--live`:
- Paper-trade for a few weeks first and compare with the backtest.
- The script does not know about market holidays - don't schedule it on them.
- The state file is the strategy's view of its position. If you trade the same
  stock by hand, or an order is rejected or partly filled, fix the state file
  to match your ICICI holdings.
- `--max-qty` caps shares per order; `--yes` skips the confirmation (needed when scheduled).
- Market orders are sent by the SDK as aggressive limit orders.

## Tests

```
python -m unittest test_strategy test_app
```
