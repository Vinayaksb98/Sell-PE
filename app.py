import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
import yfinance as yf

st.set_page_config(page_title='PE Sell Strategy Dashboard', page_icon='📉', layout='wide')
st.title('📉 PE SELL — Friday Support & Reversal Scanner')
st.caption('Friday scan → Monday/next trading day confirmation. Dashboard prices for Entry, T1, T2 and Stop are OPTION POSITION prices.')

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
    except Exception: return pd.DataFrame()

def rsi(s,n=14):
    d=s.diff(); up=d.clip(lower=0).ewm(alpha=1/n,adjust=False).mean(); dn=(-d.clip(upper=0)).ewm(alpha=1/n,adjust=False).mean()
    rs=up/dn.replace(0,np.nan); return 100-(100/(1+rs))

def atr(d,n=14):
    prev=d.Close.shift(1); tr=pd.concat([d.High-d.Low,(d.High-prev).abs(),(d.Low-prev).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/n,adjust=False).mean()

def support_zone(d):
    # combine recent swing lows with a lower-price cluster; avoids a single arbitrary percentile
    low=d.Low.tail(60).astype(float); a=atr(d).iloc[-1]
    swings=[]
    for i in range(2,len(low)-2):
        if low.iloc[i] <= low.iloc[i-2:i+3].min(): swings.append(low.iloc[i])
    if not swings: swings=[float(low.tail(20).min())]
    cur=float(d.Close.iloc[-1]); swings=np.array([x for x in swings if x<cur*1.03])
    if len(swings)==0: swings=np.array([float(low.tail(20).min())])
    # densest cluster using ATR-sized bins
    best=max(swings, key=lambda x: ((np.abs(swings-x)<=max(float(a),cur*0.01)).sum(), x)[0])
    touches=((np.abs(swings-best)<=max(float(a),cur*0.01))).sum()
    width=max(float(a)*0.5,cur*0.004)
    return float(best-width), float(best+width), int(touches)

def scan(sym):
    try:
        d=hist(sym)
        if d.empty or len(d)<100: return None
        d=d[['Open','High','Low','Close','Volume']].apply(pd.to_numeric,errors='coerce').dropna()
        c=d.Close; p=float(c.iloc[-1]);
        e20=float(c.ewm(span=20,adjust=False).mean().iloc[-1]); e50=float(c.ewm(span=50,adjust=False).mean().iloc[-1])
        rr=float(rsi(c).iloc[-1]); av=float(atr(d).iloc[-1]); vr=float(d.Volume.iloc[-1]/d.Volume.tail(20).mean())
        slo,shi,touches=support_zone(d); recent=d.tail(3)
        near=p>=slo and (p-slo)<=max(2.0*av,p*0.05)
        # Friday-style reversal proxy: close strong, above prior close and with lower wick
        rng=max(float(d.High.iloc[-1]-d.Low.iloc[-1]),1e-9)
        close_pos=(p-float(d.Low.iloc[-1]))/rng
        reversal=(p>float(c.iloc[-2]) and close_pos>=0.60) or (float(d.Low.iloc[-1])<=shi and p>float(d.Open.iloc[-1]) and close_pos>=0.65)
        trend=(p>=e50*0.97 and e20>=e50*0.98)
        controlled=vr<=1.8
        support_score=min(20, 8+4*touches+(4 if near else 0))
        score=(20 if trend else 8)+support_score+(18 if reversal else 0)+(10 if 40<=rr<=68 else 5)+(10 if controlled else 0)+(10 if vr>=0.8 else 5)+(12 if near else 0)
        if not (trend and near and reversal and 40<=rr<=70): return None
        invalid=slo-max(av*0.5,p*0.006)
        t1=max(p+av*1.2, e20)
        t2=p+av*2.2
        return {'Share Name':sym.replace('.NS',''),'Current':round(p,2),'Support Low':round(slo,2),'Support High':round(shi,2),'Stock Invalidation':round(invalid,2),'Stock T1':round(t1,2),'Stock T2':round(t2,2),'RSI':round(rr,1),'Score':round(score,1),'Action':'🟢 CHECK PE SELL'}
    except Exception: return None

st.sidebar.header('Scanner')
count=st.sidebar.select_slider('Stocks to scan',[50,100,200,300,400,500],value=500)
minimum=st.sidebar.slider('Minimum quality score',50,100,75)
st.sidebar.caption('Yahoo Finance is used only for historical stock-side screening. Enter/verify live option prices separately.')

scan_tab, trade_tab = st.tabs(['📊 Friday Stock Scanner','🎯 Simple PE Trade Dashboard'])

with scan_tab:
    st.subheader('Find only high-quality support + reversal candidates')
    if st.button('🔄 Scan Now',type='primary'):
        rows=[]; syms=load_universe()[:count]; prog=st.progress(0)
        for i,s in enumerate(syms,1):
            x=scan(s)
            if x and x['Score']>=minimum: rows.append(x)
            prog.progress(i/len(syms))
        prog.empty()
        if rows:
            out=pd.DataFrame(rows).sort_values('Score',ascending=False).reset_index(drop=True); out.insert(0,'Rank',range(1,len(out)+1))
            st.dataframe(out,use_container_width=True,hide_index=True)
            st.download_button('⬇️ Download candidates',out.to_csv(index=False).encode(),'pe_sell_candidates.csv','text/csv')
        else: st.warning('No candidate passed. This is acceptable: no trade is better than a weak trade.')

with trade_tab:
    st.subheader('Enter one live option position — dashboard tells you the exact position prices')
    st.info('For a bull put spread, enter the NET CREDIT received and the current NET COST TO CLOSE. T1/T2/Stop should be based on stock structure plus the live spread value, not fixed percentage formulas.')
    c1,c2,c3=st.columns(3)
    with c1:
        stock=st.text_input('Share Name','ABC')
        current=st.number_input('Current Stock Price',min_value=0.01,value=1000.0,step=1.0)
        support=st.number_input('Support / Invalidation Level',min_value=0.01,value=950.0,step=1.0)
    with c2:
        short_strike=st.number_input('PE to SELL (strike)',min_value=0.0,value=950.0,step=1.0)
        hedge_strike=st.number_input('PE HEDGE to BUY (lower strike)',min_value=0.0,value=900.0,step=1.0)
        entry_credit=st.number_input('Net Entry Credit Received',min_value=0.01,value=100.0,step=1.0)
    with c3:
        # User can supply scenario prices from live option chain. No fake universal formula.
        t1=st.number_input('T1 — Net Cost to Close',min_value=0.0,value=60.0,step=1.0)
        t2=st.number_input('T2 — Net Cost to Close',min_value=0.0,value=30.0,step=1.0)
        stop=st.number_input('STOP — Net Cost to Close',min_value=0.01,value=140.0,step=1.0)
    if hedge_strike>=short_strike: st.error('Hedge strike must be LOWER than the PE sold for a bull put spread.')
    elif support<=short_strike: st.warning('Short strike is not below support. Re-check strike safety.')
    else:
        st.markdown('### Your Simple Trade Card')
        cols=st.columns(5)
        vals=[('📉 SELL PE',f'{short_strike:.0f} PE'),('🛡️ BUY HEDGE',f'{hedge_strike:.0f} PE'),('💰 ENTRY CREDIT',f'₹{entry_credit:.2f}'),('🎯 T1 CLOSE COST',f'₹{t1:.2f}'),('🚀 T2 CLOSE COST',f'₹{t2:.2f}')]
        for col,(lab,val) in zip(cols,vals): col.metric(lab,val)
        st.error(f'🛑 STOP: Close the spread if net cost to close reaches ₹{stop:.2f} OR the stock breaks ₹{support:.2f}.')
        st.success(f'{stock}: Enter only after verifying live option-chain liquidity and prices. Your profit happens when the cost to close the spread falls below the entry credit.')
        df=pd.DataFrame([{'Share Name':stock,'Current':current,'Sell PE':short_strike,'Buy Hedge':hedge_strike,'Entry Credit':entry_credit,'T1 Close Cost':t1,'T2 Close Cost':t2,'Stop Close Cost':stop,'Stock Invalidation':support}])
        st.dataframe(df,use_container_width=True,hide_index=True)

st.divider()
st.caption('Research tool only. No guaranteed profit. Live NSE option-chain prices, spreads, liquidity and execution must be verified before trading.')
