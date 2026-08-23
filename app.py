import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
import yfinance as yf

st.set_page_config(page_title="Setup 4 - PE Sell", page_icon="📉", layout="wide")
st.title("📉 SETUP 4 — SUPPORT → REVERSAL → PE SELL")
st.caption("Stock-side scanner with PE premium bands: ₹0–20, ₹20–40, ₹40–60, ₹60–80, ₹80–100.")

@st.cache_data
def load_universe():
    f=Path(__file__).with_name("nifty500_symbols.csv")
    return [str(x).strip()+".NS" for x in pd.read_csv(f)["Symbol"].dropna().unique()]

@st.cache_data(ttl=21600, show_spinner=False)
def get_history(sym):
    try:
        return yf.download(sym,period="6mo",interval="1d",auto_adjust=False,progress=False,threads=False)
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=43200, show_spinner=False)
def get_info(sym):
    try: return yf.Ticker(sym).get_info()
    except Exception: return {}

def pct(x):
    try:return float(x)*100
    except:return np.nan

def scan(sym):
    try:
        i=get_info(sym); mc=i.get("marketCap")
        if not mc or mc<100_000_000_000:return None
        d=get_history(sym)
        if d.empty:return None
        if isinstance(d.columns,pd.MultiIndex):d.columns=d.columns.get_level_values(0)
        d=d[["High","Low","Close","Volume"]].apply(pd.to_numeric,errors="coerce").dropna()
        if len(d)<80:return None
        c,h,l,v=d.Close,d.High,d.Low,d.Volume
        p=float(c.iloc[-1]); b=d.tail(45)
        support=float(b.Low.quantile(.20))
        ema5=float(c.ewm(span=5,adjust=False).mean().iloc[-1])
        ema10=float(c.ewm(span=10,adjust=False).mean().iloc[-1])
        delta=c.diff(); gain=delta.clip(lower=0).rolling(14).mean(); loss=(-delta.clip(upper=0)).rolling(14).mean()
        rsi=float(100-100/(1+gain.iloc[-1]/loss.iloc[-1])) if loss.iloc[-1] else 50
        vr=float(v.iloc[-1]/v.tail(20).mean()) if v.tail(20).mean()>0 else np.nan
        near=(p>=support and (p-support)/p<=.08)
        reversal=(p>ema5 and p>float(c.iloc[-4]) and p>float(c.iloc[-2]))
        fund=25
        roe=pct(i.get("returnOnEquity")); growth=pct(i.get("revenueGrowth")); margin=pct(i.get("profitMargins"))
        if np.isfinite(roe):fund+=15 if roe>=15 else 8 if roe>=10 else 0
        if np.isfinite(growth):fund+=10 if growth>=8 else 5 if growth>0 else 0
        if np.isfinite(margin) and margin>0:fund+=5
        if i.get("operatingCashflow",0)>0:fund+=10
        score=fund+(20 if near else 0)+(15 if reversal else 0)+(10 if rsi>=50 else 5)+(10 if np.isfinite(vr) and vr>=1.2 else 5)
        if not near or not reversal:return None
        return {"Stock":sym.replace(".NS",""),"Spot":p,"Support":support,"Invalidation":support*.97,
                "RSI":rsi,"EMA5":ema5,"EMA10":ema10,"Volume Ratio":vr,"Fundamental":fund,
                "Support":20,"Reversal":15,"Score":score,
                "Signal":"🟢 PE SELL CANDIDATE" if score>=75 else "🟡 WATCH"}
    except Exception:return None

st.sidebar.header("Filters")
bands=st.sidebar.multiselect("PE premium bands",["₹0–20","₹20–40","₹40–60","₹60–80","₹80–100"],default=["₹0–20","₹20–40","₹40–60","₹60–80","₹80–100"])
count=st.sidebar.select_slider("Stocks to scan",[50,100,200,300,400,500],value=100)
minimum=st.sidebar.slider("Minimum score",50,100,75)

st.info("Premium bands are the option-selection filter. Yahoo Finance is used for the stock-side setup. Verify live NSE option-chain premium, OI, IV, volume, bid/ask, expiry and hedge before trading.")

if st.button("🔄 Scan Setup 4",type="primary"):
    rows=[]
    progress=st.progress(0)
    symbols=load_universe()[:count]
    for n,s in enumerate(symbols,1):
        x=scan(s)
        if x and x["Score"]>=minimum:rows.append(x)
        progress.progress(n/len(symbols))
    progress.empty()
    if rows:
        out=pd.DataFrame(rows).sort_values("Score",ascending=False).reset_index(drop=True)
        out.insert(0,"Rank",range(1,len(out)+1))
        st.success(f"{len(out)} stock candidates found. Now confirm the PE contract on NSE.")
        st.dataframe(out,use_container_width=True,hide_index=True)
        st.download_button("⬇️ Download CSV",out.to_csv(index=False).encode(),"setup4_candidates.csv","text/csv")
    else:st.warning("No candidates passed the filters. Scan more stocks or lower the score.")

st.divider()
st.warning("⚠️ Research only. Prefer defined-risk bull put spreads (sell higher PE + buy lower PE) instead of naked PE selling. A premium below ₹100 does not make a trade safe.")
