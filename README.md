# BANKNIFTY High-Expansion Option Scanner V5

## Corrected dashboard layout

The MAIN TRADE CALL is now the primary dashboard section and contains:

Rank | Current | Signal | Option Contract | BUY @ | OPTION SL | SELL @ T1 | SELL @ T2 | EXPECTED MAX | Potential | Action

The Five Gates are no longer the main dashboard. They are moved below the trade call as supporting analysis.

## Strict strategy behavior

If the model detects only a normal or small move:
- NO TRADE
- No fake Buy/Sell targets

If a strict high-expansion setup passes:
- BUY CE or BUY PE
- Premium-based BUY / SL / T1 / T2 / Expected Max scenario

## Important live-data limitation

Yahoo Finance supplies the BANKNIFTY underlying data. Exact live option contract selection and exact option premium require a live NSE option chain or broker API.