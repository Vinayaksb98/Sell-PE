import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import date
import yfinance as yf
from math import log, sqrt, exp, erf

st.set_page_config(page_title='PE Sell Strategy Dashboard', page_icon='📉', layout='wide')
st.title('📉 PE SELL — Simple Trade Dashboard')
st.caption('Friday stock scan → select candidate → enter live option data → dashboard shows exact option entry, T1, T2 and stop prices.')

@st.cache_data
def load_universe():
    f = Path(__file__).with_name('nifty500_symbols.csv')
    return [str(x).strip()+'.NS' for x in pd.read_csv(f)['Symbol'].dropna().unique()]

@st.cache_data(ttl=21600, show_spinner=False)
def hist(sym):
    try:
        d=yf.download(sym, period='9mo', interval='1d', auto_adjust=False, progress=False, threads=False)
        if isinstance(d.columns,pd.MultiIndex): d.columns=d.columns.get_level_values(0)
        return d
    except Exception:
        return pd.DataFrame()

def rsi(s,n=14):
    d=s.diff(); up=d.clip(lower=0).ewm(alpha=1/n,adjust=False).mean(); dn=(-d.clip(upper=0)).ewm(alpha=1/n,adjust=False).mean()
    rs=up/dn.replace(0,np.nan); return 100-(100/(1+rs))

def atr(d,n=14):
    prev=d.Close.shift(1); tr=pd.concat([d.High-d.Low,(d.High-prev).abs(),(d.Low-prev).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/n,adjust=False).mean()

def support_zone(d):
    low=d.Low.tail(60).astype(float); a=float(atr(d).iloc[-1]); swings=[]
    for i in range(2,len(low)-2):
        if low.iloc[i] <= low.iloc[i-2:i+3].min(): swings.append(float(low.iloc[i]))
    if not swings: swings=[float(low.tail(20).min())]
    cur=float(d.Close.iloc[-1]); swings=np.array([x for x in swings if x<cur*1.03])
    if len(swings)==0: swings=np.array([float(low.tail(20).min())])
    band=max(a,cur*0.01)
    best=max(swings, key=lambda x: ((np.abs(swings-x)<=band).sum(), x)[0])
    touches=int((np.abs(swings-best)<=band).sum()); width=max(a*0.5,cur*0.004)
    return float(best-width), float(best+width), touches

def scan(sym):
    try:
        d=hist(sym)
        if d.empty or len(d)<100: return None
        d=d[['Open','High','Low','Close','Volume']].apply(pd.to_numeric,errors='coerce').dropna()
        c=d.Close; p=float(c.iloc[-1]); e20=float(c.ewm(span=20,adjust=False).mean().iloc[-1]); e50=float(c.ewm(span=50,adjust=False).mean().iloc[-1])
        rr=float(rsi(c).iloc[-1]); av=float(atr(d).iloc[-1]); vr=float(d.Volume.iloc[-1]/d.Volume.tail(20).mean())
        slo,shi,touches=support_zone(d)
        near=p>=slo and (p-slo)<=max(2.0*av,p*0.05)
        rng=max(float(d.High.iloc[-1]-d.Low.iloc[-1]),1e-9); close_pos=(p-float(d.Low.iloc[-1]))/rng
        reversal=(p>float(c.iloc[-2]) and close_pos>=0.60) or (float(d.Low.iloc[-1])<=shi and p>float(d.Open.iloc[-1]) and close_pos>=0.65)
        trend=(p>=e50*0.97 and e20>=e50*0.98); controlled=vr<=1.8
        support_score=min(20,8+4*touches+(4 if near else 0))
        score=(20 if trend else 8)+support_score+(18 if reversal else 0)+(10 if 40<=rr<=68 else 5)+(10 if controlled else 0)+(10 if vr>=0.8 else 5)+(12 if near else 0)
        if not (trend and near and reversal and 40<=rr<=70): return None
        invalid=slo-max(av*0.5,p*0.006)
        # Stock scenario levels used only internally to estimate option targets.
        t1=max(p+av*1.2,e20); t2=p+av*2.2
        return {'Share Name':sym.replace('.NS',''),'Current':round(p,2),'Support Low':round(slo,2),'Support High':round(shi,2),'Stock Stop':round(invalid,2),'Stock T1':round(t1,2),'Stock T2':round(t2,2),'RSI':round(rr,1),'Score':round(score,1)}
    except Exception:
        return None

# Black-Scholes put value used only as a scenario estimate after the user supplies live IV and expiry.
def norm_cdf(x): return 0.5*(1+erf(x/sqrt(2)))
def bs_put(S,K,T,r,sigma):
    if T<=0: return max(K-S,0.0)
    if sigma<=0: return max(K*exp(-r*T)-S,0.0)
    d1=(log(S/K)+(r+0.5*sigma*sigma)*T)/(sigma*sqrt(T)); d2=d1-sigma*sqrt(T)
    return K*exp(-r*T)*norm_cdf(-d2)-S*norm_cdf(-d1)

st.sidebar.header('Scanner')
count=st.sidebar.select_slider('Stocks to scan',[50,100,200,300,400,500],value=500)
minimum=st.sidebar.slider('Minimum quality score',50,100,75)
st.sidebar.caption('Yahoo Finance is used for stock screening. Live option premium / IV / expiry must be entered or verified from a live option chain.')

if 'candidates' not in st.session_state: st.session_state.candidates=pd.DataFrame()

scan_tab, trade_tab = st.tabs(['📊 Scan Friday Candidates','🎯 FINAL PE SELL DASHBOARD'])

with scan_tab:
    st.subheader('High-quality stock candidates')
    st.caption('The support details are kept here for analysis. They are intentionally NOT shown in the final trading dashboard.')
    if st.button('🔄 Scan Now',type='primary'):
        rows=[]; syms=load_universe()[:count]; prog=st.progress(0)
        for i,s in enumerate(syms,1):
            x=scan(s)
            if x and x['Score']>=minimum: rows.append(x)
            prog.progress(i/len(syms))
        prog.empty()
        if rows:
            out=pd.DataFrame(rows).sort_values('Score',ascending=False).reset_index(drop=True); out.insert(0,'Rank',range(1,len(out)+1))
            st.session_state.candidates=out
            st.dataframe(out,use_container_width=True,hide_index=True)
        else:
            st.warning('No candidate passed. No trade is better than a weak trade.')

with trade_tab:
    st.subheader('Only the prices you need to trade')
    st.caption('Select a scanned stock, enter the LIVE option data, and the system estimates T1/T2 from stock scenario levels instead of using fixed percentage targets.')
    cand=st.session_state.candidates
    if cand.empty:
        st.info('Run the Friday scan first. You can still test the dashboard using manual values below.')
        names=['Manual']
        selected=st.selectbox('Select Share',names)
        base={'Share Name':'Manual','Current':1000.0,'Stock Stop':950.0,'Stock T1':1030.0,'Stock T2':1060.0,'Score':0.0}
    else:
        selected=st.selectbox('Select Share',cand['Share Name'].tolist())
        base=cand.loc[cand['Share Name']==selected].iloc[0].to_dict()

    a,b,c,d = st.columns(4)
    with a:
        current=st.number_input('Current Stock Price',min_value=0.01,value=float(base['Current']),step=1.0)
        stock_stop=st.number_input('Stock Stop',min_value=0.01,value=float(base['Stock Stop']),step=1.0)
    with b:
        short_strike=st.number_input('PE Strike to SELL',min_value=0.01,value=max(1.0,float(round(current*0.95))),step=1.0)
        hedge_strike=st.number_input('Hedge PE Strike (lower)',min_value=0.01,value=max(1.0,float(round(current*0.90))),step=1.0)
    with c:
        short_ltp=st.number_input('LIVE Short PE Premium',min_value=0.01,value=100.0,step=0.5)
        hedge_ltp=st.number_input('LIVE Hedge PE Premium',min_value=0.0,value=0.0,step=0.5)
    with d:
        iv_pct=st.number_input('Live IV %',min_value=1.0,max_value=200.0,value=25.0,step=1.0)
        expiry=st.date_input('Expiry Date',value=date.today())

    stock_t1=float(base.get('Stock T1',current*1.03)); stock_t2=float(base.get('Stock T2',current*1.06))
    net_entry=short_ltp-hedge_ltp
    days=max((expiry-date.today()).days,1); T=days/365; sigma=iv_pct/100; r=0.06
    # Position value to close at stock scenario levels. Time is reduced modestly for scenario holding periods.
    def close_value(S, hold_days):
        t=max((days-hold_days)/365,0.00001)
        short_val=bs_put(S,short_strike,t,r,sigma)
        hedge_val=bs_put(S,hedge_strike,t,r,sigma) if hedge_ltp>0 else 0.0
        return max(short_val-hedge_val,0.0)
    # Scenario exits are derived from actual stock targets, not a fixed premium-decay formula.
    t1_close=close_value(stock_t1,max(1,min(3,days//4 or 1)))
    t2_close=close_value(stock_t2,max(2,min(7,days//2 or 2)))
    stop_close=close_value(stock_stop,1)

    if hedge_strike>=short_strike:
        st.error('Hedge strike must be lower than the PE strike sold.')
    else:
        final=pd.DataFrame([{
            'Rank': int(base.get('Rank',1)),
            'Share Name': base['Share Name'],
            'Current': round(current,2),
            'PE to Sell': f'{short_strike:.0f} PE',
            'SELL @': round(short_ltp,2),
            'T1': round(t1_close,2),
            'T2': round(t2_close,2),
            'SL': round(stop_close,2),
            'Action': '🟢 SELL PE' if net_entry>0 else '🟡 CHECK INPUTS'
        }])
        st.dataframe(final,use_container_width=True,hide_index=True)
        st.markdown('### Simple Trade Instruction')
        x1,x2,x3,x4=st.columns(4)
        x1.metric('📉 SELL PE @',f'₹{short_ltp:.2f}')
        x2.metric('🎯 T1 — Buy Back @',f'₹{t1_close:.2f}')
        x3.metric('🚀 T2 — Buy Back @',f'₹{t2_close:.2f}')
        x4.metric('🛑 STOP — Exit @',f'₹{stop_close:.2f}')
        st.caption(f'Internal scenario levels used: Stock T1 ₹{stock_t1:.2f}, Stock T2 ₹{stock_t2:.2f}, Stock Stop ₹{stock_stop:.2f}. These are hidden from the final table to keep the dashboard simple.')
        st.download_button('⬇️ Download Final Trade Dashboard',final.to_csv(index=False).encode(),'final_pe_trade_dashboard.csv','text/csv')

st.divider()
st.caption('Research tool only. No guaranteed profit. Option scenario prices are estimates and live NSE option-chain execution prices must be verified before trading.')
