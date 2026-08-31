# BANKNIFTY Improved CE/PE Strategy V2.1 - Error Fixed

## Fix included
The previous version could fail with:

`IndexError: single positional indexer is out-of-bounds`

This happened when Yahoo Finance returned insufficient or incomplete intraday data and the indicator DataFrame became empty after filtering.

V2.1 fixes this by:
- Checking Yahoo data before calculations
- Trying a fallback BANKNIFTY symbol
- Using minimum rolling periods instead of requiring every indicator to have full history
- Checking for valid indicator rows before `.iloc[-1]`
- Showing a user-friendly message instead of crashing
- Showing downloaded candles for troubleshooting

## Run
pip install -r requirements.txt
streamlit run app.py

## Strategy
- BUY CE / BUY PE / NO TRADE
- VWAP + slope
- EMA20/EMA50
- RSI
- ADX + DI
- Relative volume
- Compression → expansion
- Breakout/breakdown
- Candle quality
- False breakout warning
- Overextension filter
- Option premium rule ≤ ₹50
- Short-dated expiry rule

Exact live option contract selection still requires an option-chain or broker API.
