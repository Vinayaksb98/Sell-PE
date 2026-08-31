# BANKNIFTY CE/PE Dashboard V3

This version restores the dashboard structure discussed with the user.

## Main dashboard
- BANKNIFTY Current
- Market regime
- BUY CE / BUY PE / NO TRADE
- Setup quality
- RSI
- Main Trade Call table
- Current
- Trigger
- Underlying stop
- CE/PE direction
- Premium rule ₹20–₹50
- Weekly/next eligible expiry rule
- T1 and T2
- Option selection rules
- Indicator purpose and current status

## Important fix
Yahoo Finance often reports BANKNIFTY index Volume as 0. V3 no longer stops because of this.
Volume confirmation becomes neutral, while price/trend indicators continue to work.

## Run
pip install -r requirements.txt
streamlit run app.py
