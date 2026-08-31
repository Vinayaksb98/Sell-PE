import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

st.set_page_config(page_title="BANKNIFTY CE/PE Dashboard", layout="wide")

# ============================================================
# DATA
# ============================================================
@st.cache_data(ttl=60)
def load_data(interval, period):
    symbols = ["^NSEBANK", "NIFTY_BANK.NS"]
    errors = []

    for symbol in symbols:
        try:
            df = yf.download(
                symbol, period=period, interval=interval,
                progress=False, auto_adjust=False, group_by="column"
            )
            if df is None or df.empty:
                errors.append(f"{symbol}: no data")
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            need = ["Open", "High", "Low", "Close"]
            if not all(c in df.columns for c in need):
                errors.append(f"{symbol}: OHLC missing")
                continue

            if "Volume" not in df.columns:
                df["Volume"] = 0

            df = df[[c for c in ["Open","High","Low","Close","Volume"] if c in df.columns]]
            df = df.dropna(subset=["Open","High","Low","Close"])

            if len(df) >= 60:
                return df, symbol, errors

            errors.append(f"{symbol}: only {len(df)} usable rows")
        except Exception as e:
            errors.append(f"{symbol}: {type(e).__name__}")

    return pd.DataFrame(), None, errors


# ============================================================
# INDICATORS
# ============================================================
def rsi(close, n=14):
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100/(1+rs)

def add_indicators(df):
    d = df.copy()

    d["EMA20"] = d["Close"].ewm(span=20, adjust=False).mean()
    d["EMA50"] = d["Close"].ewm(span=50, adjust=False).mean()
    d["RSI"] = rsi(d["Close"])

    prev = d["Close"].shift(1)
    tr = pd.concat([
        d["High"]-d["Low"],
        (d["High"]-prev).abs(),
        (d["Low"]-prev).abs()
    ], axis=1).max(axis=1)
    d["ATR"] = tr.ewm(alpha=1/14, adjust=False).mean()

    up = d["High"].diff()
    down = -d["Low"].diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=d.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=d.index)

    atr_s = tr.ewm(alpha=1/14, adjust=False).mean().replace(0, np.nan)
    d["PDI"] = 100 * plus_dm.ewm(alpha=1/14, adjust=False).mean() / atr_s
    d["MDI"] = 100 * minus_dm.ewm(alpha=1/14, adjust=False).mean() / atr_s
    dx = 100 * (d["PDI"]-d["MDI"]).abs() / (d["PDI"]+d["MDI"]).replace(0, np.nan)
    d["ADX"] = dx.ewm(alpha=1/14, adjust=False).mean()

    # Price-weighted VWAP fallback if Yahoo intraday volume is zero.
    typical = (d["High"] + d["Low"] + d["Close"]) / 3
    volume_ok = d["Volume"].fillna(0).sum() > 0

    if volume_ok:
        pv = typical * d["Volume"]
        d["VWAP"] = pv.rolling(78, min_periods=1).sum() / d["Volume"].rolling(78, min_periods=1).sum().replace(0,np.nan)
        d["VOLUME_OK"] = True
        avg_vol = d["Volume"].rolling(20, min_periods=5).mean().replace(0,np.nan)
        d["VOLR"] = d["Volume"] / avg_vol
    else:
        # Do NOT stop the dashboard when Yahoo gives BANKNIFTY volume = 0.
        d["VWAP"] = typical.rolling(20, min_periods=1).mean()
        d["VOLUME_OK"] = False
        d["VOLR"] = np.nan

    mid = d["Close"].rolling(20, min_periods=5).mean()
    std = d["Close"].rolling(20, min_periods=5).std()
    upper = mid + 2*std
    lower = mid - 2*std
    d["BBWIDTH"] = (upper-lower) / mid.replace(0,np.nan)

    d["BODY"] = (d["Close"]-d["Open"]).abs()
    d["RANGE"] = (d["High"]-d["Low"]).replace(0,np.nan)
    d["BODY_PCT"] = d["BODY"]/d["RANGE"]
    d["CLOSE_LOC"] = 2*((d["Close"]-d["Low"])/d["RANGE"]) - 1

    d["BREAKOUT"] = d["High"].rolling(20, min_periods=20).max().shift(1)
    d["BREAKDOWN"] = d["Low"].rolling(20, min_periods=20).min().shift(1)

    return d


# ============================================================
# SIGNAL ENGINE
# ============================================================
def evaluate(d):
    valid = d.dropna(subset=["Close","EMA20","EMA50","RSI","ATR","ADX","PDI","MDI","VWAP"])
    if len(valid) < 2:
        return {"signal":"NO TRADE","score":0,"reasons":["Waiting for enough candles"],"warnings":[],"x":None}

    x = valid.iloc[-1]
    p = valid.iloc[-2]

    ce = 0
    pe = 0
    reasons = []
    warnings = []

    # Trend
    if x["EMA20"] > x["EMA50"]:
        ce += 15; reasons.append("EMA trend bullish")
    elif x["EMA20"] < x["EMA50"]:
        pe += 15; reasons.append("EMA trend bearish")

    # VWAP / dynamic mean
    if x["Close"] > x["VWAP"]:
        ce += 15; reasons.append("Price above VWAP/mean")
    elif x["Close"] < x["VWAP"]:
        pe += 15; reasons.append("Price below VWAP/mean")

    # ADX / DI
    if x["ADX"] >= 20:
        if x["PDI"] > x["MDI"]:
            ce += 15; reasons.append("Directional strength bullish")
        else:
            pe += 15; reasons.append("Directional strength bearish")
    else:
        warnings.append("Weak trend strength")

    # RSI momentum
    if x["RSI"] >= 55 and x["RSI"] >= p["RSI"]:
        ce += 10; reasons.append("RSI bullish momentum")
    elif x["RSI"] <= 45 and x["RSI"] <= p["RSI"]:
        pe += 10; reasons.append("RSI bearish momentum")

    # Breakout/breakdown
    if pd.notna(x["BREAKOUT"]) and x["Close"] > x["BREAKOUT"]:
        if x["BODY_PCT"] >= 0.50 and x["CLOSE_LOC"] >= 0.25:
            ce += 25; reasons.append("High-quality bullish breakout")
        else:
            warnings.append("Bullish breakout but candle quality weak")

    if pd.notna(x["BREAKDOWN"]) and x["Close"] < x["BREAKDOWN"]:
        if x["BODY_PCT"] >= 0.50 and x["CLOSE_LOC"] <= -0.25:
            pe += 25; reasons.append("High-quality bearish breakdown")
        else:
            warnings.append("Bearish breakdown but candle quality weak")

    # Volume is optional because Yahoo frequently reports 0 for index volume
    if bool(x["VOLUME_OK"]) and pd.notna(x["VOLR"]) and x["VOLR"] >= 1.2:
        ce += 5; pe += 5
        reasons.append("Volume expansion")
    elif not bool(x["VOLUME_OK"]):
        warnings.append("Yahoo index volume unavailable — volume filter neutral")

    # Don't chase extreme move
    ext = abs(x["Close"]-x["VWAP"]) / x["ATR"] if x["ATR"] > 0 else 0
    if ext > 2.8:
        ce -= 15; pe -= 15
        warnings.append("Move is extended — no chase entry")

    ce = max(0,min(100,ce))
    pe = max(0,min(100,pe))

    if ce >= 60 and ce >= pe + 10:
        signal = "BUY CE"; score = ce
    elif pe >= 60 and pe >= ce + 10:
        signal = "BUY PE"; score = pe
    else:
        signal = "NO TRADE"; score = max(ce,pe)

    return {"signal":signal,"score":score,"ce":ce,"pe":pe,"reasons":reasons,"warnings":warnings,"x":x}


# ============================================================
# OPTION PLAN (rule based until live option chain is connected)
# ============================================================
def option_plan(signal, x):
    if signal == "NO TRADE":
        return "—", "Wait for valid CE/PE setup", "—", "—", "—"

    side = "CE" if signal == "BUY CE" else "PE"
    price = float(x["Close"])
    atr = float(x["ATR"])

    # Underlying levels
    trigger = price
    if side == "CE":
        stop = price - 0.9*atr
        t1 = price + 1.3*atr
        t2 = price + 2.4*atr
    else:
        stop = price + 0.9*atr
        t1 = price - 1.3*atr
        t2 = price - 2.4*atr

    return side, trigger, stop, t1, t2


# ============================================================
# UI
# ============================================================
st.title("🔥 BANKNIFTY CE / PE TRADING DASHBOARD")
st.caption("Strategy: Trend → Compression/Expansion → Breakout/Breakdown → Confirmation → CE/PE")
st.info("Option rule: Premium ₹20–₹50 | Prefer nearest expiry or next eligible expiry only")

with st.sidebar:
    st.header("SCAN SETTINGS")
    interval = st.selectbox("Chart timeframe", ["5m","15m"], index=0)
    period = "5d" if interval == "5m" else "1mo"
    run = st.button("🔄 SCAN BANKNIFTY", type="primary")

if run:
    with st.spinner("Loading BANKNIFTY data..."):
        raw, symbol, errors = load_data(interval, period)

    if raw.empty:
        st.error("BANKNIFTY data is temporarily unavailable from Yahoo Finance.")
        st.write(errors)
        st.stop()

    d = add_indicators(raw)
    result = evaluate(d)
    x = result["x"]

    if x is None:
        st.warning("Waiting for enough candles. Please try again later.")
        st.stop()

    signal = result["signal"]
    score = result["score"]
    side, trigger, stop, t1, t2 = option_plan(signal, x)

    # ================= HEADER METRICS =================
    a,b,c,dcol,e = st.columns(5)
    a.metric("BANKNIFTY", f"{x['Close']:,.0f}")
    b.metric("MARKET", "BULLISH" if signal=="BUY CE" else "BEARISH" if signal=="BUY PE" else "NEUTRAL")
    c.metric("SIGNAL", "🟢 BUY CE" if signal=="BUY CE" else "🔴 BUY PE" if signal=="BUY PE" else "⚪ NO TRADE")
    dcol.metric("SETUP QUALITY", f"{score}/100")
    e.metric("RSI", f"{x['RSI']:.1f}")

    st.divider()

    # ================= MAIN TRADE TABLE =================
    st.subheader("🎯 MAIN TRADE CALL")

    if signal == "NO TRADE":
        table = pd.DataFrame([{
            "Rank":"—",
            "Stock":"BANKNIFTY",
            "Current":round(float(x["Close"]),2),
            "Trigger":"WAIT",
            "Stock Stop":"—",
            "PE to Sell":"—",
            "Sell @":"—",
            "T1":"—",
            "T2":"—",
            "Option SL":"—",
            "Action":"⚪ NO TRADE"
        }])
    else:
        table = pd.DataFrame([{
            "Rank":"🥇 1",
            "Stock":"BANKNIFTY",
            "Current":round(float(x["Close"]),2),
            "Trigger":round(trigger,2),
            "Stock Stop":round(stop,2),
            "CE/PE":side,
            "Premium Filter":"₹20–₹50",
            "Expiry":"This week / Next eligible",
            "T1":round(t1,2),
            "T2":round(t2,2),
            "Option SL":"Live option SL after contract selection",
            "Action":"🟢 BUY CE" if side=="CE" else "🔴 BUY PE"
        }])

    st.dataframe(table, use_container_width=True, hide_index=True)

    # ================= TRADE CARD =================
    left, right = st.columns([1,1])

    with left:
        st.subheader("📌 WHY THIS SIGNAL")
        if signal == "NO TRADE":
            st.write("• Conditions are mixed or not strong enough.")
            st.write("• Strategy protects capital by avoiding forced trades.")
        else:
            for r in result["reasons"]:
                st.write("•", r)

        st.subheader("⚠️ RISK FILTERS")
        for w in result["warnings"]:
            st.write("•", w)
        if not result["warnings"]:
            st.write("• No major rejection filter triggered")

    with right:
        st.subheader("💰 OPTION SELECTION")
        option_df = pd.DataFrame([
            ["Direction", side if signal != "NO TRADE" else "Wait"],
            ["Premium", "₹20–₹50 only"],
            ["Preferred", "₹30–₹50"],
            ["Expiry", "Nearest weekly expiry"],
            ["Backup", "Next eligible expiry"],
            ["Long expiry", "Not allowed"],
            ["Exact strike", "Requires live option chain"],
        ], columns=["Parameter","Rule"])
        st.dataframe(option_df, use_container_width=True, hide_index=True)

    # ================= INDICATORS =================
    st.subheader("📊 STRATEGY INDICATOR STATUS")
    indicators = pd.DataFrame([
        ["VWAP / Mean", round(float(x["VWAP"]),2), "Bullish" if x["Close"] > x["VWAP"] else "Bearish",
         "Shows intraday price bias"],
        ["EMA 20 / 50", f"{x['EMA20']:.0f} / {x['EMA50']:.0f}",
         "Bullish" if x["EMA20"] > x["EMA50"] else "Bearish",
         "Identifies trend direction"],
        ["RSI", round(float(x["RSI"]),1),
         "Bullish" if x["RSI"]>=55 else "Bearish" if x["RSI"]<=45 else "Neutral",
         "Measures momentum"],
        ["ADX", round(float(x["ADX"]),1),
         "Strong" if x["ADX"]>=20 else "Weak",
         "Measures trend strength"],
        ["DI+ / DI-", f"{x['PDI']:.1f} / {x['MDI']:.1f}",
         "Bullish" if x["PDI"]>x["MDI"] else "Bearish",
         "Shows directional control"],
        ["ATR", round(float(x["ATR"]),2), "Volatility",
         "Used for stop and target distance"],
        ["Volume", "Yahoo unavailable" if not bool(x["VOLUME_OK"]) else "Available",
         "Neutral" if not bool(x["VOLUME_OK"]) else "Active",
         "Confirms participation when available"],
    ], columns=["Indicator","Current","Bias","Purpose"])
    st.dataframe(indicators, use_container_width=True, hide_index=True)

    st.caption(f"Data source: Yahoo Finance | Symbol used: {symbol}")
    st.caption("The dashboard intentionally does not show the raw candle table. Exact live option strike/premium/expiry requires option-chain data integration.")
else:
    st.markdown("""
    ### How the dashboard works

    **1. Trend Direction** → EMA 20/50 + VWAP  
    **2. Strength** → ADX + DI  
    **3. Momentum** → RSI  
    **4. Entry Quality** → Breakout / Breakdown + candle quality  
    **5. Protection** → false-breakout and overextension filters  
    **6. Trade Output** → BUY CE / BUY PE / NO TRADE  
    **7. Option Rules** → ₹20–₹50 premium and nearest eligible weekly expiry
    """)
