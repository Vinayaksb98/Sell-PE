
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

st.set_page_config(page_title="BANKNIFTY Explosion Scanner", layout="wide")

# NOTE:
# This version builds the 5-gate underlying scanner automatically from Yahoo Finance.
# Exact live NSE option premium/Greeks require a live option-chain/broker data source.
# Therefore BUY/SL/T1/T2 are only populated after a live option contract is supplied.

@st.cache_data(ttl=60)
def get_banknifty(interval, period):
    for symbol in ["^NSEBANK", "NIFTY_BANK.NS"]:
        try:
            df = yf.download(symbol, interval=interval, period=period,
                             progress=False, auto_adjust=False)
            if df is not None and not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                cols = [c for c in ["Open","High","Low","Close","Volume"] if c in df.columns]
                df = df[cols].copy()
                if "Volume" not in df:
                    df["Volume"] = 0
                if len(df) >= 80:
                    return df, symbol
        except Exception:
            continue
    return pd.DataFrame(), ""

def rsi(s, n=14):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100/(1+rs)

def indicators(d):
    d = d.copy()
    d["ema20"] = d.Close.ewm(span=20, adjust=False).mean()
    d["ema50"] = d.Close.ewm(span=50, adjust=False).mean()
    d["rsi"] = rsi(d.Close)

    prev = d.Close.shift()
    tr = pd.concat([(d.High-d.Low), (d.High-prev).abs(), (d.Low-prev).abs()], axis=1).max(axis=1)
    d["atr"] = tr.ewm(alpha=1/14, adjust=False).mean()

    up = d.High.diff()
    dn = -d.Low.diff()
    pdm = pd.Series(np.where((up>dn)&(up>0),up,0.0), index=d.index)
    mdm = pd.Series(np.where((dn>up)&(dn>0),dn,0.0), index=d.index)
    atr = d["atr"].replace(0,np.nan)
    d["pdi"] = 100*pdm.ewm(alpha=1/14,adjust=False).mean()/atr
    d["mdi"] = 100*mdm.ewm(alpha=1/14,adjust=False).mean()/atr
    dx = 100*(d.pdi-d.mdi).abs()/(d.pdi+d.mdi).replace(0,np.nan)
    d["adx"] = dx.ewm(alpha=1/14,adjust=False).mean()

    tp=(d.High+d.Low+d.Close)/3
    if d.Volume.fillna(0).sum()>0:
        v=d.Volume.replace(0,np.nan)
        d["vwap"]=(tp*d.Volume).rolling(78,min_periods=1).sum()/d.Volume.rolling(78,min_periods=1).sum().replace(0,np.nan)
    else:
        d["vwap"]=tp.rolling(20,min_periods=1).mean()

    mid=d.Close.rolling(20).mean()
    sd=d.Close.rolling(20).std()
    d["bb_width"]=(4*sd/mid).replace([np.inf,-np.inf],np.nan)
    d["bb_width_rank"]=d["bb_width"].rolling(60,min_periods=20).rank(pct=True)

    d["atr_rank"]=d["atr"].rolling(60,min_periods=20).rank(pct=True)
    d["range20h"]=d.High.rolling(20).max().shift(1)
    d["range20l"]=d.Low.rolling(20).min().shift(1)
    d["range"]=d.High-d.Low
    return d

def clamp(x): return float(max(0,min(100,x)))

def evaluate(d):
    d=d.dropna()
    x=d.iloc[-1]; p=d.iloc[-2]

    # Gate 1: regime / compression -> expansion
    compression = (1-x.bb_width_rank)*60 + (1-x.atr_rank)*20
    expansion = 20 if x["range"] > d["range"].rolling(20).mean().iloc[-1] else 0
    regime=clamp(compression+expansion)

    # Direction
    ce=0; pe=0
    if x.Close>x.vwap: ce+=20
    else: pe+=20
    if x.ema20>x.ema50: ce+=20
    else: pe+=20
    if x.pdi>x.mdi: ce+=15
    else: pe+=15
    if x.adx>20 and x.adx>p.adx:
        if x.pdi>x.mdi: ce+=15
        else: pe+=15
    if x.rsi>55 and x.rsi>=p.rsi: ce+=15
    elif x.rsi<45 and x.rsi<=p.rsi: pe+=15
    if x.Close>x.range20h: ce+=15
    elif x.Close<x.range20l: pe+=15

    direction=max(ce,pe)
    side="CE" if ce>pe else "PE"

    # Magnitude: room based on ATR and breakout range
    recent_range=(d.High.iloc[-21:-1].max()-d.Low.iloc[-21:-1].min())
    breakout_strength=abs(x.Close-(x.range20h if side=="CE" else x.range20l))/max(x.atr,1)
    projected=max(recent_range, 3*x.atr)
    magnitude=clamp(30 + min(40, projected/max(x.atr,1)*8) + min(30, breakout_strength*12))

    # Timing: fresh momentum, not overly extended
    fresh=20 if x["range"]>p["range"] else 10
    adx_accel=20 if x.adx>p.adx else 5
    momentum=25 if (side=="CE" and x.rsi>p.rsi) or (side=="PE" and x.rsi<p.rsi) else 10
    extension=abs(x.Close-x.vwap)/max(x.atr,1)
    timing=clamp(fresh+adx_accel+momentum+(30 if extension<2.5 else 5))

    explosion=round(0.20*regime+0.25*direction+0.25*magnitude+0.20*timing+10,1)
    action = "NO TRADE"
    if regime>=65 and direction>=70 and magnitude>=75 and timing>=70 and explosion>=80:
        action=f"🔥 EXPLOSION BUY {side}"
    elif direction>=65 and magnitude>=60:
        action=f"👀 WATCH {side}"

    return x, side, regime, direction, magnitude, timing, clamp(explosion), action

def premium_model(entry, score):
    # Scenario model only; NOT live option-chain pricing.
    # Used for dashboard planning until live chain integration is added.
    risk = entry * (0.42 if score>=90 else 0.35)
    sl=max(0.05,entry-risk)
    t1=entry*(2.0 if score>=85 else 1.6)
    t2=entry*(3.5 if score>=90 else 2.5)
    maxp=entry*(5.0 if score>=92 else 3.0)
    return sl,t1,t2,maxp

st.title("🔥 BANKNIFTY EXPLOSION SCANNER V4")
st.caption("Five-gate strategy | Direction + Magnitude + Timing | Designed to reject small-movement setups")

with st.sidebar:
    interval=st.selectbox("Timeframe",["5m","15m"],index=0)
    period="5d" if interval=="5m" else "1mo"
    entry=st.number_input("Candidate option premium (for scenario planning)",15.0,25.0,20.0,0.5)
    scan=st.button("SCAN NOW",type="primary")

if not scan:
    st.info("Click SCAN NOW. The scanner will show TRADE, WATCH, or NO TRADE.")
    st.stop()

with st.spinner("Scanning BANKNIFTY..."):
    raw,symbol=get_banknifty(interval,period)
if raw.empty:
    st.error("Could not retrieve BANKNIFTY data from Yahoo Finance.")
    st.stop()

x,side,g1,g2,g3,g4,score,action=evaluate(indicators(raw))

a,b,c,d,e=st.columns(5)
a.metric("BANKNIFTY",f"{x.Close:,.0f}")
b.metric("DIRECTION",side)
c.metric("EXPLOSION SCORE",f"{score:.0f}/100")
d.metric("REGIME", "EXPANSION" if g1>=65 else "NOT READY")
e.metric("ACTION",action)

st.divider()
st.subheader("🥇 MAIN EXPLOSION DECISION")

if action.startswith("🔥"):
    sl,t1,t2,mx=premium_model(entry,score)
    table=pd.DataFrame([{
        "Current":round(x.Close,2),
        "Signal":f"BUY {side}",
        "Option":"LIVE CONTRACT REQUIRED",
        "Scenario Buy @":f"₹{entry:.2f}",
        "Scenario SL @":f"₹{sl:.2f}",
        "T1":f"₹{t1:.2f}",
        "T2":f"₹{t2:.2f}",
        "5× Scenario Max":f"₹{mx:.2f}",
        "Action":action
    }])
    st.dataframe(table,use_container_width=True,hide_index=True)
    st.warning("Premium prices above are scenario calculations. Exact BUY/SL/T1/T2 require live option-chain premium and Greeks.")
else:
    st.dataframe(pd.DataFrame([{
        "Current":round(x.Close,2),"Direction Bias":side,
        "Explosion Score":round(score,1),
        "Reason":"Does not pass all five strict gates",
        "Action":action
    }]),use_container_width=True,hide_index=True)

st.subheader("🚪 FIVE GATES")
gates=pd.DataFrame([
    ["1. Market Regime",round(g1,1),"PASS" if g1>=65 else "FAIL","Compression/volatility environment"],
    ["2. Direction",round(g2,1),"PASS" if g2>=70 else "FAIL","CE or PE directional agreement"],
    ["3. Magnitude",round(g3,1),"PASS" if g3>=75 else "FAIL","Large remaining underlying move"],
    ["4. Timing",round(g4,1),"PASS" if g4>=70 else "FAIL","Fresh expansion, not late"],
    ["5. Combined Explosion",round(score,1),"PASS" if score>=80 else "FAIL","All gates combined"],
],columns=["Gate","Score","Status","Purpose"])
st.dataframe(gates,use_container_width=True,hide_index=True)

st.subheader("📊 CURRENT INDICATORS")
st.dataframe(pd.DataFrame([
    ["VWAP/Mean",round(x.vwap,2)],
    ["EMA 20",round(x.ema20,2)],
    ["EMA 50",round(x.ema50,2)],
    ["RSI",round(x.rsi,1)],
    ["ADX",round(x.adx,1)],
    ["DI+",round(x.pdi,1)],
    ["DI-",round(x.mdi,1)],
    ["ATR",round(x.atr,2)],
],columns=["Indicator","Value"]),use_container_width=True,hide_index=True)

st.info(f"Underlying source: Yahoo Finance ({symbol}). Exact option selection requires live NSE/broker option-chain data. This V4 intentionally rejects normal/small-movement setups.")
