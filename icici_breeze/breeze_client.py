"""Thin wrapper around ICICI Direct's Breeze API (pip install breeze-connect).

Credentials are read from environment variables so they never end up in git:
  BREEZE_API_KEY, BREEZE_API_SECRET   - from https://api.icicidirect.com/apiuser/home
  BREEZE_SESSION_TOKEN                - generated daily, see README.md
"""

import datetime as dt
import os
import urllib.parse

import pandas as pd

LOGIN_URL = "https://api.icicidirect.com/apiuser/login?api_key="

# get_historical_data_v2 returns at most ~1000 candles per call, so long ranges
# are fetched in windows of this many calendar days.
WINDOW_DAYS = {
    "1minute": 2,
    "5minute": 10,
    "30minute": 60,
    "1day": 900,
}


class BreezeError(RuntimeError):
    pass


def login_url(api_key=None):
    key = api_key or os.environ.get("BREEZE_API_KEY", "")
    return LOGIN_URL + urllib.parse.quote_plus(key)


def connect(api_key=None, api_secret=None, session_token=None):
    """Create an authenticated BreezeConnect session.

    Arguments that are not given are read from the environment variables.
    """
    from breeze_connect import BreezeConnect

    creds = {
        "BREEZE_API_KEY": api_key or os.environ.get("BREEZE_API_KEY"),
        "BREEZE_API_SECRET": api_secret or os.environ.get("BREEZE_API_SECRET"),
        "BREEZE_SESSION_TOKEN": session_token or os.environ.get("BREEZE_SESSION_TOKEN"),
    }
    missing = [k for k, v in creds.items() if not v]
    if missing:
        raise BreezeError(
            "Missing credentials: %s\n"
            "Get today's session token by logging in at:\n  %s"
            % (", ".join(missing), login_url(creds["BREEZE_API_KEY"])))

    breeze = BreezeConnect(api_key=creds["BREEZE_API_KEY"])
    breeze.generate_session(api_secret=creds["BREEZE_API_SECRET"],
                            session_token=creds["BREEZE_SESSION_TOKEN"])
    return breeze


def _check(resp, what):
    if not isinstance(resp, dict):
        raise BreezeError("%s: unexpected response %r" % (what, resp))
    if resp.get("Status") != 200 or resp.get("Error"):
        raise BreezeError("%s failed: %s" % (what, resp.get("Error") or resp))
    return resp.get("Success")


def isec_code(breeze, nse_symbol, exchange="NSE"):
    """ICICI uses its own stock codes (e.g. RELIANCE -> RELIND). Map an NSE symbol to it."""
    res = breeze.get_names(exchange_code=exchange, stock_code=nse_symbol)
    if isinstance(res, dict) and res.get("isec_stock_code"):
        return res["isec_stock_code"]
    raise BreezeError("Could not find ICICI code for %s: %s" % (nse_symbol, res))


def _iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def fetch_history(breeze, stock_code, start, end, interval="1day", exchange="NSE"):
    """Download OHLCV candles for [start, end] as a DataFrame indexed by datetime."""
    if interval not in WINDOW_DAYS:
        raise ValueError("interval must be one of %s" % ", ".join(WINDOW_DAYS))

    frames = []
    step = dt.timedelta(days=WINDOW_DAYS[interval])
    cur = start
    while cur <= end:
        win_end = min(cur + step, end)
        resp = breeze.get_historical_data_v2(
            interval=interval,
            from_date=_iso(cur),
            to_date=_iso(win_end),
            stock_code=stock_code,
            exchange_code=exchange,
            product_type="cash",
        )
        rows = _check(resp, "get_historical_data_v2") or []
        if rows:
            frames.append(pd.DataFrame(rows))
        cur = win_end + dt.timedelta(days=1)

    if not frames:
        raise BreezeError("No candles returned for %s between %s and %s" % (stock_code, start, end))

    df = pd.concat(frames, ignore_index=True)
    df["datetime"] = pd.to_datetime(df["datetime"])
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col])
    df = df.drop_duplicates("datetime").set_index("datetime").sort_index()
    return df[["open", "high", "low", "close", "volume"]]


def last_price(breeze, stock_code, exchange="NSE"):
    resp = breeze.get_quotes(stock_code=stock_code, exchange_code=exchange,
                             expiry_date="", product_type="cash", right="", strike_price="")
    rows = _check(resp, "get_quotes")
    for row in rows or []:
        if str(row.get("exchange_code", "")).upper() == exchange.upper():
            return float(row["ltp"])
    raise BreezeError("No quote for %s on %s: %s" % (stock_code, exchange, rows))


def place_delivery_order(breeze, stock_code, action, quantity, exchange="NSE"):
    """Place a CNC (delivery) market order. Returns the order id.

    The SDK converts 'market' into an aggressive limit order, as SEBI's algo rules require.
    """
    resp = breeze.place_order(
        stock_code=stock_code,
        exchange_code=exchange,
        product="cash",
        action=action.lower(),
        order_type="market",
        quantity=str(int(quantity)),
        price="",
        validity="day",
        user_remark="sma-bot",
    )
    success = _check(resp, "place_order")
    return success.get("order_id") if isinstance(success, dict) else success
