# PE Sell Strategy Dashboard

## What it does
- Scans the supplied Nifty universe using Yahoo Finance daily stock data.
- Looks for trend + support zone + controlled pullback + bullish reversal.
- Produces stock candidates for Friday review.
- Provides a simple bull-put-spread trade card for live option execution.

## Important
Yahoo Finance is used for stock-side historical screening only. Live NSE option-chain data is required to choose executable option strikes and live position prices.

## Run
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Dashboard logic
The scanner does not invent a universal premium target formula. T1, T2 and Stop on the trade tab are live position levels to be set from the selected option spread and stock structure.
