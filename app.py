import streamlit as st
import pandas as pd
from strategy import evaluate_stock

st.set_page_config(page_title="PE Option Selling Stock Scanner", layout="wide")
st.title("PE OPTION SELLING STOCK SCANNER")
st.caption("Base • Support • Strength • Confirmation → SELL PE")
c1,c2,c3,c4=st.columns(4)
c1.metric("Market Status","DATA MODE")
c2.metric("Last Updated","Latest available data")
c3.metric("Stocks Scanned",500)
c4.metric("Data Status","LIVE REQUIRED FOR SIGNAL")

st.info("Friday workflow removed. Cached/historical data is for analysis only and must never create a LIVE SELL PE signal.")

sample = pd.DataFrame([
    {"Rank":1,"Share":"INFY","Current":1144.0,"Trigger":1150.0,"Stock Stop":1110.0,
     "Available Strikes":[1120,1100,1080,1060,1040],"PE Premiums":{1120:145,1100:112,1080:82,1060:58,1040:38},
     "Liquidity":{1120:0.95,1100:0.90,1080:0.88,1060:0.82,1040:0.70},
     "Action":"WAIT"},
    {"Rank":2,"Share":"EXAMPLE","Current":820.0,"Trigger":812.0,"Stock Stop":780.0,
     "Available Strikes":[800,780,760,740],"PE Premiums":{800:95,780:70,760:50,740:34},
     "Liquidity":{800:0.95,780:0.91,760:0.87,740:0.72},"Action":"SELL PE"},
])

results=[]
for _,r in sample.iterrows():
    x=evaluate_stock(r.to_dict())
    results.append(x)

df=pd.DataFrame(results)
cols=["Rank","Share","Current","Trigger","Stock Stop","PE to Sell","Sell @","T1","T2","Option SL","Action"]
st.dataframe(df[cols], use_container_width=True, hide_index=True)

st.subheader("Trade Rules")
st.markdown("""
- **WAIT**: trigger/confirmation not satisfied.
- **SELL PE**: stock structure passes and current data confirms the trigger.
- **PE to Sell**: selected only from the supplied available strike list; the engine never invents a strike.
- **T1/T2**: option buy-back profit levels, therefore `T2 < T1 < Sell @`.
- **Option SL**: loss exit, therefore `Option SL > Sell @`.
- **Stock Stop**: thesis invalidation; exit if stock stop breaks even before option SL.
""")

st.subheader("Database Policy")
st.write("Recommended analysis history: 5 years of daily OHLCV for up to 500 stocks. Historical/cache data is labelled ANALYSIS ONLY. A live trade signal requires current stock and current option-chain data.")
