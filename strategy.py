def _round2(x):
    return round(float(x),2)

def choose_actual_strike(current, stock_stop, strikes, premiums, liquidity,
                         min_liquidity=0.75, min_premium=20, max_premium=100):
    """Choose only an ACTUAL available strike.
    Prefer a strike below the stock stop (safety), with usable liquidity/premium.
    """
    candidates=[]
    for s in sorted(set(strikes), reverse=True):
        p=float(premiums.get(s,0))
        liq=float(liquidity.get(s,0))
        if s < current and liq >= min_liquidity and min_premium <= p <= max_premium:
            # Lower score is better. Penalize strikes above stop.
            risk_penalty=max(0.0, s-stock_stop)*3
            distance=abs(current-s)
            score=risk_penalty + distance*0.15 - liq*10
            candidates.append((score,s,p,liq))
    if not candidates:
        return None
    return min(candidates, key=lambda z:z[0])

def evaluate_stock(row):
    current=float(row["Current"])
    trigger=float(row["Trigger"])
    stock_stop=float(row["Stock Stop"])
    action = "SELL PE" if current >= trigger else "WAIT"

    chosen=choose_actual_strike(
        current, stock_stop, row["Available Strikes"],
        row["PE Premiums"], row["Liquidity"]
    )

    if chosen is None:
        return {
            "Rank":row["Rank"],"Share":row["Share"],"Current":current,
            "Trigger":trigger,"Stock Stop":stock_stop,
            "PE to Sell":"NO VALID STRIKE","Sell @":None,"T1":None,"T2":None,
            "Option SL":None,"Action":"NO TRADE"
        }

    _,strike,sell,liq=chosen

    # Exit levels are option-premium levels for a short PE.
    # They are based on staged premium decay and validated for correct ordering.
    t1=_round2(sell*0.65)
    t2=_round2(sell*0.35)
    option_sl=_round2(sell*1.40)

    return {
        "Rank":row["Rank"],"Share":row["Share"],"Current":_round2(current),
        "Trigger":_round2(trigger),"Stock Stop":_round2(stock_stop),
        "PE to Sell":f"{strike} PE","Sell @":_round2(sell),
        "T1":t1,"T2":t2,"Option SL":option_sl,
        "Action":action
    }
