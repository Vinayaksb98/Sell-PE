# PE Option Selling Stock Scanner

## Dashboard
Rank | Share | Current | Trigger | Stock Stop | PE to Sell | Sell @ | T1 | T2 | Option SL | Action

## Strategy
1. Analyse historical stock structure using approximately 5 years of daily OHLCV.
2. Identify base/consolidation and meaningful support.
3. Calculate Trigger and Stock Stop.
4. Wait until confirmation permits PE selling.
5. Read current option chain.
6. Select only an actual available PE strike.
7. Require usable premium and liquidity.
8. Manage short-option exits:
   T2 < T1 < Sell @ < Option SL.

## Important
This ZIP is a clean strategy/dashboard starter because the original application source files were not present in this chat. The sample data in app.py is demonstration data and must be replaced with your live data provider/option-chain adapter before real trading use.

Friday has been removed from the workflow.
Cached/historical data is ANALYSIS ONLY and must not generate a live SELL PE signal.
