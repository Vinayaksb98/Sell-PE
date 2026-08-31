import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

st.set_page_config(page_title="BANKNIFTY Strategy V2.1", layout="wide")

def ema(s, n):
    return s.ewm(span=n, adjust=False, min_periods=n).mean()

def rsi(s, n=14):
    d = s.diff()
    gain = d.clip(lower=0).ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def true_range(df):
    pc = df["Close"].shift(1)
    return pd.concat([
        df["High"] - df["Low"],
        (df["High"] - pc).abs(),
        (df["Low"] - pc).abs()
    ], axis=1).max(axis=1)

def atr(df, n=14):
    return true_range(df).ewm(alpha=1/n, adjust=False, min_periods=n).mean()

def adx(df, n=14):
    up = df["High"].diff()
    down = -df["Low"].diff()

    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)

    tr = true_range(df)
    atrv = tr.ewm(alpha=1/n, adjust=False, min_periods=n).mean()

    pdi = 100 * plus_dm.ewm(alpha=1/n, adjust=False, min_periods=n).mean() / atrv.replace(0, np.nan)
    mdi = 100 * minus_dm.ewm(alpha=1/n, adjust=False, min_periods=n).mean() / atrv.replace(0, np.nan)
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    adxv = dx.ewm(alpha=1/n, adjust=False, min_periods=n).mean()

    return adxv, pdi, mdi

def add_indicators(df):
    d = df.copy()

    for col in ["Open", "High", "Low", "Close", "Volume"]:
        d[col] = pd.to_numeric(d[col], errors="coerce")

    d["EMA20"] = ema(d["Close"], 20)
    d["EMA50"] = ema(d["Close"], 50)
    d["RSI"] = rsi(d["Close"], 14)
    d["ATR"] = atr(d, 14)
    d["ADX"], d["PDI"], d["MDI"] = adx(d, 14)

    typical = (d["High"] + d["Low"] + d["Close"]) / 3
    pv = typical * d["Volume"]
    vol_roll = d["Volume"].rolling(78, min_periods=5).sum()
    d["VWAP"] = pv.rolling(78, min_periods=5).sum() / vol_roll.replace(0, np.nan)

    avg_vol = d["Volume"].rolling(20, min_periods=5).mean()
    d["VOLR"] = d["Volume"] / avg_vol.replace(0, np.nan)

    mid = d["Close"].rolling(20, min_periods=10).mean()
    std = d["Close"].rolling(20, min_periods=10).std()
    upper = mid + 2 * std
    lower = mid - 2 * std
    d["BBWIDTH"] = (upper - lower) / mid.replace(0, np.nan)

    d["RANGE"] = d["High"] - d["Low"]
    d["BODY"] = (d["Close"] - d["Open"]).abs()
    d["BODY_PCT"] = d["BODY"] / d["RANGE"].replace(0, np.nan)
    d["CLOSE_LOC"] = ((d["Close"] - d["Low"]) / d["RANGE"].replace(0, np.nan)) * 2 - 1

    d["RANGE_HIGH_20"] = d["High"].rolling(20, min_periods=10).max().shift(1)
    d["RANGE_LOW_20"] = d["Low"].rolling(20, min_periods=10).min().shift(1)

    d["ATR_MEDIAN_20"] = d["ATR"].rolling(20, min_periods=10).median()
    d["BB_MEDIAN_20"] = d["BBWIDTH"].rolling(20, min_periods=10).median()

    return d

def evaluate(d):
    # Use the latest row where all fields needed by the decision engine exist.
    needed = [
        "Close", "Open", "High", "Low", "Volume",
        "EMA20", "EMA50", "RSI", "ATR", "ADX", "PDI", "MDI",
        "VWAP", "VOLR", "BBWIDTH", "BODY_PCT", "CLOSE_LOC"
    ]
    valid = d.dropna(subset=needed)

    if len(valid) < 2:
        return None, None, [], ["Not enough valid intraday candles yet. Try again after more market data is available."]

    x = valid.iloc[-1]
    p = valid.iloc[-2]

    bull = 0
    bear = 0
    bull_reasons = []
    bear_reasons = []
    warnings = []

    if x["ADX"] >= 20 and x["ADX"] >= p["ADX"]:
        if x["PDI"] > x["MDI"]:
            bull += 12; bull_reasons.append("ADX rising with bullish DI")
        elif x["MDI"] > x["PDI"]:
            bear += 12; bear_reasons.append("ADX rising with bearish DI")
    else:
        warnings.append("Trend strength weak or not expanding")

    vwap_slope = x["VWAP"] - p["VWAP"]
    if x["Close"] > x["VWAP"] and vwap_slope >= 0:
        bull += 15; bull_reasons.append("Price above rising VWAP")
    if x["Close"] < x["VWAP"] and vwap_slope <= 0:
        bear += 15; bear_reasons.append("Price below falling VWAP")

    if x["EMA20"] > x["EMA50"] and x["EMA20"] >= p["EMA20"]:
        bull += 12; bull_reasons.append("EMA20 > EMA50 and rising")
    if x["EMA20"] < x["EMA50"] and x["EMA20"] <= p["EMA20"]:
        bear += 12; bear_reasons.append("EMA20 < EMA50 and falling")

    if x["RSI"] >= 55 and x["RSI"] > p["RSI"]:
        bull += 8; bull_reasons.append("RSI bullish momentum")
    if x["RSI"] <= 45 and x["RSI"] < p["RSI"]:
        bear += 8; bear_reasons.append("RSI bearish momentum")

    if pd.notna(p["BB_MEDIAN_20"]) and p["BBWIDTH"] <= p["BB_MEDIAN_20"] and \
       x["BBWIDTH"] > p["BBWIDTH"] and x["ATR"] > p["ATR"]:
        bull += 8; bear += 8
        bull_reasons.append("Volatility expansion after compression")
        bear_reasons.append("Volatility expansion after compression")

    if x["VOLR"] >= 1.2:
        bull += 10; bear += 10
        bull_reasons.append("Relative volume confirmation")
        bear_reasons.append("Relative volume confirmation")
    else:
        warnings.append("Volume confirmation weak")

    breakout = pd.notna(x.get("RANGE_HIGH_20")) and x["Close"] > x["RANGE_HIGH_20"]
    breakdown = pd.notna(x.get("RANGE_LOW_20")) and x["Close"] < x["RANGE_LOW_20"]

    bullish_candle = x["Close"] > x["Open"] and x["BODY_PCT"] >= 0.55 and x["CLOSE_LOC"] >= 0.35
    bearish_candle = x["Close"] < x["Open"] and x["BODY_PCT"] >= 0.55 and x["CLOSE_LOC"] <= -0.35

    if breakout and bullish_candle:
        bull += 20; bull_reasons.append("High-quality breakout candle")
    elif breakout:
        warnings.append("Breakout detected but candle quality weak")

    if breakdown and bearish_candle:
        bear += 20; bear_reasons.append("High-quality breakdown candle")
    elif breakdown:
        warnings.append("Breakdown detected but candle quality weak")

    extension = abs(x["Close"] - x["VWAP"]) / x["ATR"] if x["ATR"] > 0 else 0
    if extension > 2.5:
        warnings.append("Move extended from VWAP — avoid chasing late entry")
        bull -= 12; bear -= 12

    if breakout and x["CLOSE_LOC"] < 0:
        bull -= 20
        warnings.append("Potential bullish false-breakout / rejection")
    if breakdown and x["CLOSE_LOC"] > 0:
        bear -= 20
        warnings.append("Potential bearish false-breakdown / rejection")

    bull = max(0, min(100, bull))
    bear = max(0, min(100, bear))

    if bull >= 72 and bull >= bear + 12:
        return ("BUY CE", bull, bull_reasons, warnings)
    if bear >= 72 and bear >= bull + 12:
        return ("BUY PE", bear, bear_reasons, warnings)

    return ("NO TRADE", max(bull, bear), ["No sufficiently strong directional edge"], warnings)

def download_banknifty(interval, period):
    symbols = ["^NSEBANK", "^NSEBANK.NS"]
    errors = []

    for symbol in symbols:
        try:
            raw = yf.download(
                symbol,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=False,
                group_by="column"
            )
            if raw is None or raw.empty:
                errors.append(f"{symbol}: no data")
                continue

            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)

            required = ["Open", "High", "Low", "Close", "Volume"]
            if not all(c in raw.columns for c in required):
                errors.append(f"{symbol}: required OHLCV columns missing")
                continue

            raw = raw[required].dropna(how="all")
            if len(raw) >= 20:
                return raw, symbol, errors

            errors.append(f"{symbol}: insufficient rows")
        except Exception as e:
            errors.append(f"{symbol}: {type(e).__name__}")

    return pd.DataFrame(), None, errors

st.title("🔥 BANKNIFTY CE / PE STRATEGY V2.1")
st.caption("Fixed version: robust Yahoo Finance data handling and empty-data protection")
st.warning("Educational/backtesting tool. No strategy guarantees profit. Validate before risking capital.")

with st.sidebar:
    st.header("Scanner Settings")
    interval = st.selectbox("Timeframe", ["5m", "15m"], index=0)
    period = "5d" if interval == "5m" else "1mo"
    run = st.button("🔄 RUN IMPROVED SCAN", type="primary")

if run:
    with st.spinner("Downloading BANKNIFTY data from Yahoo Finance..."):
        raw, symbol, errors = download_banknifty(interval, period)

    if raw.empty:
        st.error("Yahoo Finance did not return usable BANKNIFTY data right now.")
        st.info("This is usually a temporary data-provider or intraday availability issue. Please try again later.")
        with st.expander("Technical details"):
            st.write(errors)
        st.stop()

    d = add_indicators(raw)
    result = evaluate(d)

    if result[0] is None:
        st.warning("⚪ NO TRADE — not enough valid candles for all indicators.")
        st.info("The app is working, but the data currently available is insufficient to calculate the full strategy safely.")
        st.dataframe(raw.tail(20), use_container_width=True)
        st.stop()

    signal, score, reasons, warnings = result

    valid_close = d["Close"].dropna()
    x = d.loc[valid_close.index[-1]]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("BANKNIFTY", f"{x['Close']:,.0f}")
    c2.metric("SIGNAL", "🟢 BUY CE" if signal=="BUY CE" else "🔴 BUY PE" if signal=="BUY PE" else "⚪ NO TRADE")
    c3.metric("SETUP SCORE", f"{score}/100")
    c4.metric("MARKET STRENGTH (ADX)", f"{x['ADX']:.1f}" if pd.notna(x["ADX"]) else "Calculating")

    st.caption(f"Yahoo Finance symbol used: {symbol}")

    st.subheader("🎯 Strategy Decision")
    if signal == "BUY CE":
        st.success("🟢 BUY CE SETUP: bullish expansion conditions passed.")
    elif signal == "BUY PE":
        st.error("🔴 BUY PE SETUP: bearish expansion conditions passed.")
    else:
        st.info("⚪ NO TRADE: the strategy is intentionally selective.")

    left, right = st.columns(2)
    with left:
        st.subheader("✅ Confirmations")
        for r in reasons:
            st.write("•", r)
    with right:
        st.subheader("⚠️ Risk / Rejection Filters")
        if warnings:
            for w in warnings:
                st.write("•", w)
        else:
            st.write("• No major rejection filter triggered")

    st.subheader("📈 Underlying Trade Levels")
    if signal == "BUY CE":
        stop = x["Close"] - 0.9*x["ATR"]
        t1 = x["Close"] + 1.3*x["ATR"]
        t2 = x["Close"] + 2.4*x["ATR"]
    elif signal == "BUY PE":
        stop = x["Close"] + 0.9*x["ATR"]
        t1 = x["Close"] - 1.3*x["ATR"]
        t2 = x["Close"] - 2.4*x["ATR"]
    else:
        stop=t1=t2=np.nan

    st.dataframe(pd.DataFrame([{
        "Current": round(x["Close"],2),
        "Trigger": round(x["Close"],2),
        "Underlying Stop": round(stop,2) if pd.notna(stop) else "—",
        "T1": round(t1,2) if pd.notna(t1) else "—",
        "T2": round(t2,2) if pd.notna(t2) else "—"
    }]), use_container_width=True, hide_index=True)

    st.subheader("💰 Option Selection Rules")
    st.dataframe(pd.DataFrame([
        ["Direction", "CE for BUY CE / PE for BUY PE"],
        ["Maximum Premium", "₹50"],
        ["Preferred Premium", "₹30–₹50"],
        ["Aggressive Range", "₹20–₹30"],
        ["Expiry Priority", "Nearest eligible short-dated expiry"],
        ["Backup Expiry", "Next eligible expiry"],
        ["Longer Expiry", "Reject"],
        ["Exact Contract", "Requires live option-chain/broker API"],
    ], columns=["Rule","Setting"]), use_container_width=True, hide_index=True)

    st.subheader("📊 Indicator Status")
    rows = [
        ["VWAP", "Bullish" if x["Close"] > x["VWAP"] else "Bearish"],
        ["EMA20 / EMA50", "Bullish" if x["EMA20"] > x["EMA50"] else "Bearish"],
        ["RSI", round(x["RSI"],1) if pd.notna(x["RSI"]) else "—"],
        ["ADX", round(x["ADX"],1) if pd.notna(x["ADX"]) else "—"],
        ["DI+", round(x["PDI"],1) if pd.notna(x["PDI"]) else "—"],
        ["DI-", round(x["MDI"],1) if pd.notna(x["MDI"]) else "—"],
        ["Relative Volume", round(x["VOLR"],2) if pd.notna(x["VOLR"]) else "—"],
        ["ATR", round(x["ATR"],2) if pd.notna(x["ATR"]) else "—"],
    ]
    st.dataframe(pd.DataFrame(rows, columns=["Indicator","Current Status"]),
                 use_container_width=True, hide_index=True)

    with st.expander("Latest downloaded BANKNIFTY candles"):
        st.dataframe(raw.tail(30), use_container_width=True)

