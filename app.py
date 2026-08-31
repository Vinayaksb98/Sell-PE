import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

st.set_page_config(page_title="BANKNIFTY Strategy V2", layout="wide")

# ============================================================
# Indicator functions
# ============================================================
def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()

def rsi(s, n=14):
    d = s.diff()
    gain = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)

def true_range(df):
    pc = df["Close"].shift()
    return pd.concat([
        df["High"] - df["Low"],
        (df["High"] - pc).abs(),
        (df["Low"] - pc).abs()
    ], axis=1).max(axis=1)

def atr(df, n=14):
    return true_range(df).ewm(alpha=1/n, adjust=False).mean()

def adx(df, n=14):
    up = df["High"].diff()
    down = -df["Low"].diff()

    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)

    tr = true_range(df)
    atrv = tr.ewm(alpha=1/n, adjust=False).mean()

    pdi = 100 * plus_dm.ewm(alpha=1/n, adjust=False).mean() / atrv.replace(0, np.nan)
    mdi = 100 * minus_dm.ewm(alpha=1/n, adjust=False).mean() / atrv.replace(0, np.nan)

    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    adxv = dx.ewm(alpha=1/n, adjust=False).mean()
    return adxv, pdi, mdi

def add_indicators(df):
    d = df.copy()

    d["EMA20"] = ema(d["Close"], 20)
    d["EMA50"] = ema(d["Close"], 50)
    d["RSI"] = rsi(d["Close"], 14)
    d["ATR"] = atr(d, 14)
    d["ADX"], d["PDI"], d["MDI"] = adx(d, 14)

    typical = (d["High"] + d["Low"] + d["Close"]) / 3
    # Rolling/session-neutral approximation for Yahoo intraday data
    d["VWAP"] = (typical * d["Volume"]).rolling(78, min_periods=1).sum() / \
                d["Volume"].rolling(78, min_periods=1).sum().replace(0, np.nan)

    d["VOLR"] = d["Volume"] / d["Volume"].rolling(20).mean().replace(0, np.nan)

    mid = d["Close"].rolling(20).mean()
    std = d["Close"].rolling(20).std()
    upper = mid + 2 * std
    lower = mid - 2 * std
    d["BBWIDTH"] = (upper - lower) / mid.replace(0, np.nan)

    d["RANGE"] = d["High"] - d["Low"]
    d["BODY"] = (d["Close"] - d["Open"]).abs()
    d["BODY_PCT"] = d["BODY"] / d["RANGE"].replace(0, np.nan)

    # Candle close location: +1 near high, -1 near low
    d["CLOSE_LOC"] = ((d["Close"] - d["Low"]) / d["RANGE"].replace(0, np.nan)) * 2 - 1

    d["RANGE_HIGH_20"] = d["High"].rolling(20).max().shift(1)
    d["RANGE_LOW_20"] = d["Low"].rolling(20).min().shift(1)

    d["ATR_MEDIAN_20"] = d["ATR"].rolling(20).median()
    d["BB_MEDIAN_20"] = d["BBWIDTH"].rolling(20).median()

    return d

# ============================================================
# Strategy V2
# ============================================================
def evaluate(d):
    x = d.iloc[-1]
    p = d.iloc[-2]

    bull = 0
    bear = 0
    bull_reasons = []
    bear_reasons = []
    warnings = []

    # 1. Market regime / trend strength
    if x["ADX"] >= 20 and x["ADX"] >= p["ADX"]:
        if x["PDI"] > x["MDI"]:
            bull += 12; bull_reasons.append("ADX rising with bullish DI")
        elif x["MDI"] > x["PDI"]:
            bear += 12; bear_reasons.append("ADX rising with bearish DI")
    else:
        warnings.append("Trend strength weak or not expanding")

    # 2. VWAP location + slope
    vwap_slope = x["VWAP"] - p["VWAP"]
    if x["Close"] > x["VWAP"] and vwap_slope >= 0:
        bull += 15; bull_reasons.append("Price above rising VWAP")
    if x["Close"] < x["VWAP"] and vwap_slope <= 0:
        bear += 15; bear_reasons.append("Price below falling VWAP")

    # 3. EMA structure
    if x["EMA20"] > x["EMA50"] and x["EMA20"] >= p["EMA20"]:
        bull += 12; bull_reasons.append("EMA20 > EMA50 and rising")
    if x["EMA20"] < x["EMA50"] and x["EMA20"] <= p["EMA20"]:
        bear += 12; bear_reasons.append("EMA20 < EMA50 and falling")

    # 4. RSI momentum
    if x["RSI"] >= 55 and x["RSI"] > p["RSI"]:
        bull += 8; bull_reasons.append("RSI bullish momentum")
    if x["RSI"] <= 45 and x["RSI"] < p["RSI"]:
        bear += 8; bear_reasons.append("RSI bearish momentum")

    # 5. Compression -> expansion
    compression = p["BBWIDTH"] <= p["BB_MEDIAN_20"]
    expansion = x["BBWIDTH"] > p["BBWIDTH"] and x["ATR"] > p["ATR"]
    if compression and expansion:
        bull += 8; bear += 8
        bull_reasons.append("Volatility expansion after compression")
        bear_reasons.append("Volatility expansion after compression")

    # 6. Volume participation
    if x["VOLR"] >= 1.2:
        bull += 10; bear += 10
        bull_reasons.append("Relative volume confirmation")
        bear_reasons.append("Relative volume confirmation")
    else:
        warnings.append("Volume confirmation weak")

    # 7. Breakout / breakdown
    breakout = pd.notna(x["RANGE_HIGH_20"]) and x["Close"] > x["RANGE_HIGH_20"]
    breakdown = pd.notna(x["RANGE_LOW_20"]) and x["Close"] < x["RANGE_LOW_20"]

    # 8. Candle quality
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

    # 9. Extension filter: avoid chasing huge move away from VWAP
    extension = abs(x["Close"] - x["VWAP"]) / x["ATR"] if x["ATR"] > 0 else 0
    if extension > 2.5:
        warnings.append("Move extended from VWAP — avoid chasing late entry")
        bull -= 12
        bear -= 12

    # 10. False breakout warning
    if breakout and x["CLOSE_LOC"] < 0:
        bull -= 20
        warnings.append("Potential bullish false-breakout / rejection")
    if breakdown and x["CLOSE_LOC"] > 0:
        bear -= 20
        warnings.append("Potential bearish false-breakdown / rejection")

    bull = max(0, min(100, bull))
    bear = max(0, min(100, bear))

    # Require both score and directional separation
    if bull >= 72 and bull >= bear + 12:
        return "BUY CE", bull, bull_reasons, warnings
    if bear >= 72 and bear >= bull + 12:
        return "BUY PE", bear, bear_reasons, warnings

    return "NO TRADE", max(bull, bear), ["No sufficiently strong directional edge"], warnings

# ============================================================
# UI
# ============================================================
st.title("🔥 BANKNIFTY CE / PE STRATEGY V2")
st.caption("Selective expansion strategy | Option premium ≤ ₹50 | Short-dated expiry filter")
st.warning("Educational/backtesting tool. No strategy guarantees profit. Validate with historical and paper trading before risking capital.")

with st.sidebar:
    st.header("Scanner Settings")
    interval = st.selectbox("Timeframe", ["5m", "15m"], index=0)
    period = "5d" if interval == "5m" else "1mo"
    run = st.button("🔄 RUN IMPROVED SCAN", type="primary")

if run:
    with st.spinner("Downloading BANKNIFTY data..."):
        raw = yf.download("^NSEBANK", period=period, interval=interval, progress=False, auto_adjust=False)

    if raw.empty:
        st.error("No BANKNIFTY data returned.")
        st.stop()

    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    raw = raw.dropna()
    if len(raw) < 60:
        st.error("Insufficient data for full strategy calculation.")
        st.stop()

    d = add_indicators(raw)
    d = d.dropna()

    signal, score, reasons, warnings = evaluate(d)
    x = d.iloc[-1]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("BANKNIFTY", f"{x['Close']:,.0f}")
    c2.metric("SIGNAL", "🟢 BUY CE" if signal=="BUY CE" else "🔴 BUY PE" if signal=="BUY PE" else "⚪ NO TRADE")
    c3.metric("SETUP SCORE", f"{score}/100")
    c4.metric("MARKET STRENGTH (ADX)", f"{x['ADX']:.1f}")

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

    levels = pd.DataFrame([{
        "Current": round(x["Close"],2),
        "Trigger": round(x["Close"],2),
        "Underlying Stop": round(stop,2) if pd.notna(stop) else "—",
        "T1": round(t1,2) if pd.notna(t1) else "—",
        "T2": round(t2,2) if pd.notna(t2) else "—"
    }])
    st.dataframe(levels, use_container_width=True, hide_index=True)

    st.subheader("💰 Option Selection Rules")
    option_rules = pd.DataFrame([
        ["Direction", "CE for BUY CE / PE for BUY PE"],
        ["Maximum Premium", "₹50"],
        ["Preferred Premium", "₹30–₹50"],
        ["Aggressive Range", "₹20–₹30"],
        ["Below ₹20", "Exceptional setup only"],
        ["Expiry Priority", "Nearest eligible short-dated expiry"],
        ["Backup Expiry", "Next eligible expiry"],
        ["Longer Expiry", "Reject"],
        ["Selection", "Live option chain must confirm liquidity, spread and premium"],
    ], columns=["Rule","Setting"])
    st.dataframe(option_rules, use_container_width=True, hide_index=True)

    st.subheader("📊 Indicator Status")
    status = pd.DataFrame([
        ["VWAP", "Bullish" if x["Close"]>x["VWAP"] else "Bearish"],
        ["EMA20 / EMA50", "Bullish" if x["EMA20"]>x["EMA50"] else "Bearish"],
        ["RSI", round(x["RSI"],1)],
        ["ADX", round(x["ADX"],1)],
        ["DI+", round(x["PDI"],1)],
        ["DI-", round(x["MDI"],1)],
        ["Relative Volume", round(x["VOLR"],2)],
        ["ATR", round(x["ATR"],2)],
        ["Breakout Level", round(x["RANGE_HIGH_20"],2)],
        ["Breakdown Level", round(x["RANGE_LOW_20"],2)],
    ], columns=["Indicator","Current Status"])
    st.dataframe(status, use_container_width=True, hide_index=True)

    st.subheader("🔒 V2 Improvement Architecture")
    st.code("""Market Regime
      ↓
VWAP + EMA Direction
      ↓
ADX / DI Trend Strength
      ↓
Compression → Expansion
      ↓
Volume Confirmation
      ↓
Breakout / Breakdown
      ↓
Candle Quality Filter
      ↓
False Breakout Filter
      ↓
Extension / Late Entry Filter
      ↓
BUY CE / BUY PE / NO TRADE
      ↓
Premium ≤ ₹50 + Short-Dated Expiry Filter""")

    st.caption("Live option-chain integration is required for automatic selection of the exact strike, live premium and expiry.")

