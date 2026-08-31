
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

st.set_page_config(page_title="BANKNIFTY Explosion Trade Scanner", layout="wide")

@st.cache_data(ttl=60)
def load_banknifty(interval, period):
    for symbol in ["^NSEBANK", "NIFTY_BANK.NS"]:
        try:
            df = yf.download(symbol, interval=interval, period=period,
                             progress=False, auto_adjust=False)
            if df is None or df.empty:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            needed = ["Open","High","Low","Close"]
            if not all(c in df.columns for c in needed):
                continue
            if "Volume" not in df.columns:
                df["Volume"] = 0
            df = df[["Open","High","Low","Close","Volume"]].dropna()
            if len(df) >= 80:
                return df, symbol
        except Exception:
            pass
    return pd.DataFrame(), None

def rsi(s, n=14):
    delta = s.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100/(1+rs)

def prepare(df):
    d = df.copy()
    d["EMA20"] = d["Close"].ewm(span=20, adjust=False).mean()
    d["EMA50"] = d["Close"].ewm(span=50, adjust=False).mean()
    d["RSI"] = rsi(d["Close"])

    prev = d["Close"].shift()
    tr = pd.concat([
        d["High"] - d["Low"],
        (d["High"] - prev).abs(),
        (d["Low"] - prev).abs()
    ], axis=1).max(axis=1)
    d["ATR"] = tr.ewm(alpha=1/14, adjust=False).mean()

    up = d["High"].diff()
    down = -d["Low"].diff()
    pdm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=d.index)
    mdm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=d.index)
    atr = d["ATR"].replace(0, np.nan)

    d["PDI"] = 100 * pdm.ewm(alpha=1/14, adjust=False).mean() / atr
    d["MDI"] = 100 * mdm.ewm(alpha=1/14, adjust=False).mean() / atr
    dx = 100 * (d["PDI"] - d["MDI"]).abs() / (d["PDI"] + d["MDI"]).replace(0, np.nan)
    d["ADX"] = dx.ewm(alpha=1/14, adjust=False).mean()

    tp = (d["High"] + d["Low"] + d["Close"]) / 3
    if d["Volume"].fillna(0).sum() > 0:
        d["VWAP"] = (tp*d["Volume"]).rolling(78, min_periods=1).sum() / \
                    d["Volume"].rolling(78, min_periods=1).sum().replace(0, np.nan)
    else:
        d["VWAP"] = tp.rolling(20, min_periods=1).mean()

    mid = d["Close"].rolling(20).mean()
    sd = d["Close"].rolling(20).std()
    d["BBWidth"] = (4*sd/mid).replace([np.inf, -np.inf], np.nan)
    d["BBRank"] = d["BBWidth"].rolling(60, min_periods=20).rank(pct=True)
    d["ATRRank"] = d["ATR"].rolling(60, min_periods=20).rank(pct=True)

    d["BreakHigh"] = d["High"].rolling(20).max().shift(1)
    d["BreakLow"] = d["Low"].rolling(20).min().shift(1)
    d["CandleRange"] = d["High"] - d["Low"]
    return d

def clamp(v):
    return float(max(0, min(100, v)))

def score_strategy(d):
    d = d.dropna().copy()
    x, p = d.iloc[-1], d.iloc[-2]

    # Direction
    ce = pe = 0
    if x["Close"] > x["VWAP"]: ce += 20
    else: pe += 20
    if x["EMA20"] > x["EMA50"]: ce += 20
    else: pe += 20
    if x["PDI"] > x["MDI"]: ce += 15
    else: pe += 15
    if x["ADX"] > 20 and x["ADX"] >= p["ADX"]:
        if x["PDI"] > x["MDI"]: ce += 15
        else: pe += 15
    if x["RSI"] >= 55 and x["RSI"] >= p["RSI"]: ce += 15
    elif x["RSI"] <= 45 and x["RSI"] <= p["RSI"]: pe += 15
    if x["Close"] > x["BreakHigh"]: ce += 15
    elif x["Close"] < x["BreakLow"]: pe += 15

    direction = max(ce, pe)
    side = "CE" if ce >= pe else "PE"

    # Regime
    avg_range = d["CandleRange"].iloc[-21:-1].mean()
    expansion_now = 1 if x["CandleRange"] > avg_range else 0
    regime = clamp((1-x["BBRank"])*55 + (1-x["ATRRank"])*20 + expansion_now*25)

    # Magnitude: requires substantial projected underlying room
    recent_range = d["High"].iloc[-31:-1].max() - d["Low"].iloc[-31:-1].min()
    atr_multiple = recent_range / max(float(x["ATR"]), 1)
    fresh_break = 0
    if side == "CE" and x["Close"] > x["BreakHigh"]:
        fresh_break = (x["Close"] - x["BreakHigh"]) / max(float(x["ATR"]), 1)
    if side == "PE" and x["Close"] < x["BreakLow"]:
        fresh_break = (x["BreakLow"] - x["Close"]) / max(float(x["ATR"]), 1)

    magnitude = clamp(25 + min(45, atr_multiple*7) + min(30, fresh_break*15))

    # Timing
    momentum_ok = (side == "CE" and x["RSI"] > p["RSI"]) or (side == "PE" and x["RSI"] < p["RSI"])
    extension = abs(x["Close"] - x["VWAP"]) / max(float(x["ATR"]), 1)
    timing = 20
    timing += 25 if x["ADX"] > p["ADX"] else 5
    timing += 25 if momentum_ok else 5
    timing += 20 if x["CandleRange"] >= avg_range else 10
    timing += 10 if extension < 2.5 else 0
    timing = clamp(timing)

    explosion = clamp(0.20*regime + 0.27*direction + 0.30*magnitude + 0.23*timing)

    # Strict decision: only very strong large-move setups become trade
    if explosion >= 85 and direction >= 75 and magnitude >= 80 and timing >= 75:
        action = f"🔥 BUY {side}"
    else:
        action = "⚪ NO TRADE"

    return x, side, regime, direction, magnitude, timing, explosion, action

def premium_targets(entry, score):
    # Scenario/risk planning only until a live option-chain source is integrated.
    # Target values are intentionally larger for explosion setups, but are not guarantees.
    if score >= 92:
        sl = entry * 0.55
        t1 = entry * 2.5
        t2 = entry * 4.0
        expected = entry * 5.0
    elif score >= 88:
        sl = entry * 0.60
        t1 = entry * 2.2
        t2 = entry * 3.5
        expected = entry * 4.5
    else:
        sl = entry * 0.65
        t1 = entry * 2.0
        t2 = entry * 3.0
        expected = entry * 4.0
    return sl, t1, t2, expected

st.title("🔥 BANKNIFTY HIGH-EXPANSION OPTION SCANNER")
st.caption("Designed for rare large-movement setups • Small-profit setups are rejected")

with st.sidebar:
    st.header("Scanner Settings")
    interval = st.selectbox("Timeframe", ["5m", "15m"], index=0)
    period = "5d" if interval == "5m" else "1mo"
    scenario_premium = st.number_input(
        "Preferred option premium (scenario)",
        min_value=15.0, max_value=25.0, value=20.0, step=0.5
    )
    scan = st.button("🔄 SCAN BANKNIFTY", type="primary")

if not scan:
    st.info("Click SCAN BANKNIFTY to generate the trade dashboard.")
    st.stop()

raw, symbol = load_banknifty(interval, period)
if raw.empty:
    st.error("BANKNIFTY data could not be loaded.")
    st.stop()

x, side, regime, direction, magnitude, timing, explosion, action = score_strategy(prepare(raw))

# TOP SUMMARY
c1,c2,c3,c4,c5 = st.columns(5)
c1.metric("BANKNIFTY CURRENT", f"{x['Close']:,.0f}")
c2.metric("DIRECTION", side)
c3.metric("EXPLOSION SCORE", f"{explosion:.0f}/100")
c4.metric("EXPECTED MOVE", "LARGE" if magnitude >= 80 else "INSUFFICIENT")
c5.metric("ACTION", action)

st.divider()

# THIS IS THE PRIMARY DASHBOARD TABLE — THE USER'S REQUESTED FORMAT
st.subheader("🥇 MAIN TRADE CALL")

if action.startswith("🔥 BUY"):
    sl, t1, t2, expected = premium_targets(scenario_premium, explosion)

    # Placeholder contract because exact live option chain is not connected.
    contract = f"BANKNIFTY {side} (Live strike required)"

    trade = pd.DataFrame([{
        "Rank": "🥇 1",
        "Current": f"{x['Close']:,.0f}",
        "Signal": f"BUY {side}",
        "Option Contract": contract,
        "BUY @": f"₹{scenario_premium:.2f}",
        "OPTION SL": f"₹{sl:.2f}",
        "SELL @ T1": f"₹{t1:.2f}",
        "SELL @ T2": f"₹{t2:.2f}",
        "EXPECTED MAX": f"₹{expected:.2f}",
        "Potential": f"{((expected/scenario_premium)-1)*100:.0f}%",
        "Action": action
    }])
else:
    trade = pd.DataFrame([{
        "Rank": "—",
        "Current": f"{x['Close']:,.0f}",
        "Signal": f"{side} BIAS",
        "Option Contract": "No contract selected",
        "BUY @": "—",
        "OPTION SL": "—",
        "SELL @ T1": "—",
        "SELL @ T2": "—",
        "EXPECTED MAX": "Movement too small",
        "Potential": "Rejected",
        "Action": "⚪ NO TRADE"
    }])

st.dataframe(trade, use_container_width=True, hide_index=True)

# PREMIUM TARGET CARDS — only shown for a valid high-expansion trade
if action.startswith("🔥 BUY"):
    st.subheader("💰 EXACT TRADE PLAN")
    a,b,c,d = st.columns(4)
    a.metric("BUY OPTION @", f"₹{scenario_premium:.2f}")
    b.metric("STOP LOSS @", f"₹{sl:.2f}")
    c.metric("SELL T1 @", f"₹{t1:.2f}", f"+{((t1/scenario_premium)-1)*100:.0f}%")
    d.metric("SELL T2 @", f"₹{t2:.2f}", f"+{((t2/scenario_premium)-1)*100:.0f}%")
else:
    st.warning("⚪ NO TRADE — Direction may exist, but the model does not detect enough large-movement potential. No small-profit trade is displayed.")

st.divider()

# SECONDARY ANALYSIS BELOW THE MAIN TRADE TABLE
st.subheader("🔥 EXPLOSION ANALYSIS")
scores = pd.DataFrame([
    ["Market Regime", round(regime,1), "Compression / expansion environment"],
    ["Direction", round(direction,1), "CE vs PE alignment"],
    ["Magnitude", round(magnitude,1), "Remaining BANKNIFTY movement potential"],
    ["Timing", round(timing,1), "Freshness of the move"],
    ["Explosion Score", round(explosion,1), "Final high-expansion decision"],
], columns=["Factor","Score","Meaning"])
st.dataframe(scores, use_container_width=True, hide_index=True)

st.subheader("📌 CURRENT STRATEGY STATUS")
status = pd.DataFrame([
    ["Market Regime", "PASS" if regime >= 65 else "FAIL", f"{regime:.0f}/100"],
    ["Direction", "PASS" if direction >= 75 else "FAIL", f"{direction:.0f}/100"],
    ["Large Movement", "PASS" if magnitude >= 80 else "FAIL", f"{magnitude:.0f}/100"],
    ["Timing", "PASS" if timing >= 75 else "FAIL", f"{timing:.0f}/100"],
    ["Final Explosion Setup", "PASS" if action.startswith("🔥 BUY") else "REJECT", f"{explosion:.0f}/100"],
], columns=["Check","Status","Score"])
st.dataframe(status, use_container_width=True, hide_index=True)

st.caption(
    f"Underlying data source: Yahoo Finance ({symbol}). "
    "The scanner automatically evaluates BANKNIFTY direction and large-movement potential. "
    "Exact live strike, bid/ask, option premium and Greeks require a live option-chain or broker data integration. "
    "Any premium targets in this version are scenario values, not live market quotes or guarantees."
)
