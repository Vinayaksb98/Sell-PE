# BANKNIFTY Improved CE/PE Strategy V2

## Improvements over V1
- More selective market-regime filter
- VWAP direction + slope
- EMA 20/50 structure
- ADX + DI trend-strength confirmation
- RSI momentum confirmation
- Bollinger compression -> expansion detection
- ATR expansion
- Relative-volume confirmation
- 20-bar breakout / breakdown
- Candle quality filter
- False breakout / rejection warning
- Late-entry / overextension filter
- BUY CE / BUY PE / NO TRADE
- Maximum option premium rule: ₹50
- Preferred premium range: ₹30–₹50
- Aggressive range: ₹20–₹30
- Short-dated expiry rules

## Run
pip install -r requirements.txt
streamlit run app.py

## Important
Yahoo Finance supplies the BANKNIFTY underlying data.
Exact live option strike, premium, liquidity and expiry require a live option-chain/broker API integration.

No strategy guarantees profit. Backtest and paper trade before real-money trading.
