# BANKNIFTY Explosion Scanner V4

## What this version does
This is a strict five-gate BANKNIFTY scanner:

1. Market regime
2. Direction
3. Magnitude
4. Timing
5. Combined Explosion Score

The scanner is designed to reject ordinary small-movement setups.

## Important
Yahoo Finance supplies the underlying BANKNIFTY data used for the five gates.
Yahoo data does not reliably provide the complete live NSE BANKNIFTY option chain and Greeks required to automatically select an exact ₹20 contract and calculate exact live premium targets.

Therefore, this version clearly labels premium values as scenario planning until a live option-chain data source is connected.

## Run
pip install -r requirements.txt
streamlit run app.py