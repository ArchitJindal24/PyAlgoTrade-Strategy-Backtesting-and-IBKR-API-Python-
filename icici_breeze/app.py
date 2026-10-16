"""Web UI for the SMA strategy on ICICI Direct.  Run:  streamlit run app.py"""

import datetime as dt
import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import backtest
import breeze_client as bc
import trade
from strategy import BUY, SELL

st.set_page_config(page_title="SMA Trader", page_icon="📈", layout="wide")

# Chart colors (validated categorical palette; light / dark steps).
DARK = getattr(getattr(st, "context", None), "theme", None) is not None and st.context.theme.type == "dark"
C = {
    "price": "#3987e5" if DARK else "#2a78d6",
    "sma": "#d95926" if DARK else "#eb6834",
    "buy": "#008300",
    "sell": "#e66767" if DARK else "#e34948",
}
STATE_DIR = os.environ.get("SMA_STATE_DIR", os.path.dirname(os.path.abspath(__file__)))


def rupees(x):
    return "₹{:,.0f}".format(x)


def sample_data(days=750, seed=4):
    rng = np.random.default_rng(seed)
    close = 3500 * np.exp(np.cumsum(rng.normal(0.0003, 0.015, days)))
    idx = pd.bdate_range(end=dt.date.today(), periods=days)
    open_ = close * (1 + rng.normal(0, 0.004, days))
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close) * 1.006,
                         "low": np.minimum(open_, close) * 0.994, "close": close,
                         "volume": rng.integers(1e5, 1e6, days)}, index=idx.rename("datetime"))


def read_csv(upload):
    df = pd.read_csv(upload)
    df.columns = [c.strip().lower() for c in df.columns]
    date_col = next((c for c in ("datetime", "date", "timestamp") if c in df.columns), None)
    missing = {"open", "close"} - set(df.columns)
    if date_col is None or missing:
        raise ValueError("CSV needs a datetime/date column plus open and close columns.")
    df[date_col] = pd.to_datetime(df[date_col])
    return df.set_index(date_col).rename_axis("datetime").sort_index()


def style(fig, height=380):
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=72, b=8), hovermode="x unified",
                      title=dict(y=0.97, yanchor="top", x=0, xanchor="left"),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
    return fig


def price_chart(data, trades, title):
    # Trade details ride on the Close tooltip so the unified hover never shows
    # a marker's price on a day without a trade.
    note = pd.Series("", index=data.index)
    if trades is not None:
        for t in trades.itertuples():
            note[t.datetime] = "<br><b>%s %d @ %s</b>" % (t.action.title(), t.qty, "{:,.2f}".format(t.price))
    fig = go.Figure()
    fig.add_scatter(x=data.index, y=data["close"], name="Close", line=dict(color=C["price"], width=2),
                    text=note, hovertemplate="%{y:,.2f}%{text}")
    fig.add_scatter(x=data.index, y=data["sma"], name="SMA", line=dict(color=C["sma"], width=2),
                    hovertemplate="%{y:,.2f}")
    if trades is not None and len(trades):
        for action, symbol, color in ((BUY, "triangle-up", C["buy"]), (SELL, "triangle-down", C["sell"])):
            t = trades[trades["action"] == action]
            fig.add_scatter(x=t["datetime"], y=t["price"], mode="markers", name=action.title(), hoverinfo="skip",
                            marker=dict(symbol=symbol, size=11, color=color,
                                        line=dict(width=1, color="white")))
    fig.update_layout(title=title, yaxis_title="₹")
    return style(fig, 420)


# ---------------------------------------------------------------- sidebar: login
with st.sidebar:
    st.header("ICICI Direct login")
    api_key = st.text_input("API key", value=os.environ.get("BREEZE_API_KEY", ""))
    api_secret = st.text_input("API secret", value=os.environ.get("BREEZE_API_SECRET", ""), type="password")
    if api_key:
        st.markdown("[Get today's session token ↗](%s)" % bc.login_url(api_key))
        st.caption("Log in, then copy the `apisession` value from the address you land on.")
    token = st.text_input("Session token", value=os.environ.get("BREEZE_SESSION_TOKEN", ""), type="password")
    if st.button("Connect", type="primary", width="stretch"):
        try:
            with st.spinner("Connecting…"):
                st.session_state.breeze = bc.connect(api_key, api_secret, token)
            st.session_state.pop("connect_error", None)
        except Exception as e:  # SDK raises many exception types
            st.session_state.breeze = None
            st.session_state.connect_error = str(e)
    breeze = st.session_state.get("breeze")
    if breeze:
        st.success("Connected")
    elif st.session_state.get("connect_error"):
        st.error(st.session_state.connect_error)
    else:
        st.info("Not connected. You can still backtest a CSV or the sample data.")
    st.caption("Credentials stay in this app's memory on your computer and are never saved.")

st.title("📈 SMA Trader")
st.caption("Buys when the price closes below its moving average, sells when it closes above. "
           "NSE stocks via ICICI Direct's Breeze API.")

tab_bt, tab_tr = st.tabs(["Backtest", "Trade"])

# ---------------------------------------------------------------- backtest tab
with tab_bt:
    sources = ["ICICI Direct (NSE)", "Upload CSV", "Sample data (random walk, for trying the app)"]
    source = st.radio("Data", sources, index=0 if breeze else 2, horizontal=True)

    c1, c2, c3, c4 = st.columns(4)
    if source == sources[0]:
        symbol = c1.text_input("NSE symbol", "TCS").strip().upper()
        years = c2.number_input("Years of history", 0.5, 20.0, 5.0, 0.5)
        interval = c3.selectbox("Candle size", ["1day", "30minute", "5minute", "1minute"])
    elif source == sources[1]:
        upload = c1.file_uploader("CSV (datetime, open, high, low, close, volume)", type="csv")
    capital = c4.number_input("Starting capital (₹)", 1000.0, 1e9, 100000.0, 5000.0)

    c1, c2 = st.columns([3, 1])
    lo, hi = c1.slider("SMA periods to test", 2, 200, (8, 29))
    cost = c2.number_input("Costs per buy/sell (%)", 0.0, 2.0, 0.12, 0.01,
                           help="Brokerage + STT + exchange fees + stamp duty + GST. Check your ICICI plan.")

    if st.button("Run backtest", type="primary"):
        try:
            if source == sources[0]:
                if not breeze:
                    raise RuntimeError("Connect to ICICI Direct first (sidebar).")
                with st.spinner("Downloading %s candles…" % symbol):
                    code = bc.isec_code(breeze, symbol)
                    end = dt.datetime.now()
                    df = bc.fetch_history(breeze, code, end - dt.timedelta(days=int(365 * years)), end, interval)
                label = symbol
            elif source == sources[1]:
                if upload is None:
                    raise RuntimeError("Choose a CSV file first.")
                df, label = read_csv(upload), upload.name
            else:
                df, label = sample_data(), "Sample data"
            if len(df) <= hi:
                raise RuntimeError("Only %d candles - fewer than the longest SMA period (%d)." % (len(df), hi))
            st.session_state.bt = {"df": df, "label": label, "capital": capital, "cost": cost,
                                   "results": backtest.sweep(df, range(lo, hi + 1), capital, cost)}
        except Exception as e:
            st.error(str(e))

    bt = st.session_state.get("bt")
    if bt:
        df, res, cap = bt["df"], bt["results"], bt["capital"]
        best = res.loc[res["final_equity"].idxmax()]
        bh_return = (df["close"].iloc[-1] / df["open"].iloc[0] - 1) * 100

        st.subheader("%s · %d candles · %s → %s" % (bt["label"], len(df), df.index[0].date(), df.index[-1].date()))
        m = st.columns(4)
        m[0].metric("Best SMA period", int(best["sma"]))
        m[1].metric("Best strategy return", "%+.1f%%" % best["return_pct"],
                    "%+.1f pts vs buy & hold" % (best["return_pct"] - bh_return))
        m[2].metric("Buy & hold return", "%+.1f%%" % bh_return)
        m[3].metric("Trades (best period)", int(best["trades"]))

        fig = go.Figure(go.Bar(x=res["sma"], y=res["return_pct"], marker_color=C["price"],
                               customdata=res[["final_equity", "trades"]],
                               hovertemplate="SMA %{x}<br>Return %{y:+.1f}%<br>"
                                             "Final ₹%{customdata[0]:,.0f}<br>%{customdata[1]} trades<extra></extra>"))
        fig.add_hline(y=bh_return, line=dict(color=C["sma"], width=2, dash="dash"),
                      annotation_text="Buy & hold %+.1f%%" % bh_return, annotation_position="bottom right")
        fig.update_layout(title="Return by SMA period", xaxis_title="SMA period", yaxis_title="Return (%)",
                          hovermode="closest", bargap=0.15)
        st.plotly_chart(style(fig, 340), width="stretch")

        period = st.selectbox("Inspect SMA period", list(res["sma"]), index=int(res["final_equity"].idxmax()))
        equity, trades, data = backtest.simulate(df, period, cap, bt["cost"])
        st.plotly_chart(price_chart(data, trades, "Price, SMA %d and trades" % period), width="stretch")

        hold = cap / df["open"].iloc[0] * df["close"]
        fig = go.Figure()
        fig.add_scatter(x=equity.index, y=equity, name="SMA %d strategy" % period,
                        line=dict(color=C["price"], width=2), hovertemplate="₹%{y:,.0f}")
        fig.add_scatter(x=hold.index, y=hold, name="Buy & hold", line=dict(color=C["sma"], width=2),
                        hovertemplate="₹%{y:,.0f}")
        fig.update_layout(title="Portfolio value", yaxis_title="₹")
        st.plotly_chart(style(fig), width="stretch")

        with st.expander("Trades (%d)" % len(trades)):
            st.dataframe(trades, width="stretch", hide_index=True)
        with st.expander("All SMA periods"):
            st.dataframe(res.round(2), width="stretch", hide_index=True)
        d1, d2 = st.columns(2)
        d1.download_button("Download candles CSV", df.to_csv().encode(), "%s.csv" % bt["label"].split(".")[0])
        d2.download_button("Download trades CSV", trades.to_csv(index=False).encode(), "trades_sma%d.csv" % period)

# ---------------------------------------------------------------- trade tab
with tab_tr:
    c1, c2, c3, c4 = st.columns(4)
    t_symbol = c1.text_input("NSE symbol ", "TCS", key="t_symbol").strip().upper()
    t_sma = c2.number_input("SMA period", 2, 200, 20)
    t_capital = c3.number_input("Capital for this strategy (₹)", 1000.0, 1e9, 50000.0, 5000.0)
    t_max = c4.number_input("Max shares per order", 1, 100000, 1000)
    live = st.toggle("Live trading (real orders)", value=False)
    if live:
        st.warning("Live mode places **real delivery orders** in your ICICI Direct account.")
    else:
        st.info("Paper mode: trades are simulated at the current price; nothing is sent to ICICI.")

    path = trade.state_path(STATE_DIR, t_symbol, live)
    state = trade.load_state(path, t_capital)
    m = st.columns(3)
    m[0].metric("Cash", rupees(state["cash"]))
    m[1].metric("Shares held", state["qty"])
    m[2].metric("Trades so far", len(state["trades"]))
    if state["trades"]:
        st.dataframe(pd.DataFrame(state["trades"]), width="stretch", hide_index=True)

    if dt.date.today().weekday() >= 5:
        st.caption("It's the weekend - NSE is closed, so prices won't move until Monday.")

    if st.button("Check today's signal", type="primary", disabled=not breeze):
        try:
            with st.spinner("Fetching prices…"):
                st.session_state.decision = trade.evaluate(breeze, t_symbol, int(t_sma), state, int(t_max))
                st.session_state.decision_key = (t_symbol, int(t_sma), live)
        except Exception as e:
            st.error(str(e))
    if not breeze:
        st.caption("Connect to ICICI Direct in the sidebar to check signals.")

    d = st.session_state.get("decision")
    if d and st.session_state.get("decision_key") == (t_symbol, int(t_sma), live):
        m = st.columns(4)
        m[0].metric("Price", "₹{:,.2f}".format(d["price"]))
        m[1].metric("SMA %d" % t_sma, "₹{:,.2f}".format(d["sma"]))
        m[2].metric("Signal", d["action"])
        m[3].metric("Quantity", d["qty"])
        st.plotly_chart(price_chart(d["history"].tail(120), None, "%s - last %d days" % (t_symbol, min(120, len(d["history"])))),
                        width="stretch")

        if d["action"] in (BUY, SELL) and d["qty"] > 0:
            confirmed = True
            if live:
                confirmed = st.checkbox("I confirm: place a REAL %s order for %d %s at market"
                                        % (d["action"], d["qty"], t_symbol))
            label = ("Place real %s order" if live else "Record paper %s") % d["action"].lower()
            if st.button(label, disabled=not confirmed):
                try:
                    order_id = trade.execute(breeze, d, state, path, live)
                    st.session_state.pop("decision")
                    st.success("Done%s." % (" - order id %s. Check the fill in ICICI Direct" % order_id if order_id else ""))
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
        elif d["action"] in (BUY, SELL):
            st.caption("Not enough cash for one share.")
        else:
            st.caption("No trade today.")

    with st.expander("Reset this strategy's record"):
        st.caption("Deletes %s. Use this if the record no longer matches your ICICI holdings." % os.path.basename(path))
        if st.button("Reset", disabled=not os.path.exists(path)):
            os.remove(path)
            st.rerun()
