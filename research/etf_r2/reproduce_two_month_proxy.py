"""Reproduce ETF-R2 September/October OHLC proxy; NOT a CRP or quote-fill backtest."""
from __future__ import annotations
import json,math
from pathlib import Path
SYMBOLS=("SQQQ","TQQQ","HCMT","HIBL","HIBS","TMF","TMV","SPXS","SPXL")
ROOT=Path(__file__).resolve().parent
def calculate(bars):
    if set(bars)!=set(SYMBOLS):raise ValueError("FROZEN_UNIVERSE_MISMATCH")
    dates=[x["timestamp"][:10] for x in bars["SQQQ"]]
    if len(dates)!=43 or any([x["timestamp"][:10] for x in bars[s]]!=dates for s in SYMBOLS):
        raise ValueError("CALENDAR_MISMATCH")
    cash=20000.;rows=[]
    for i in range(2,len(dates)):
        sym=min(SYMBOLS,key=lambda s:bars[s][i-1]["close"]/bars[s][i-2]["close"]-1)
        bar=bars[sym][i];entry=bar["open"]
        if not math.isfinite(entry) or entry<=0 or bar["low"]<=0 or bar["high"]<bar["low"] or bar["volume"]<=0:
            qty=0;exit_price=0.
        else:
            qty=min(math.floor(100/(entry*.02)),math.floor(cash*.25/(entry*1.0007)))
            exit_price=entry*.98 if bar["low"]<=entry*.98 else bar["close"]
        pnl=qty*(exit_price*.9993-entry*1.0007)
        cash+=pnl
        rows.append({"date":dates[i],"symbol":sym,"quantity":qty,"pnl":pnl,"wealth":cash})
    return rows
def main():
    source=json.loads((ROOT/"data/sep_oct_2026_nine_etf_iex_daily.json").read_text())
    result=calculate(source["bars"])
    expected=json.loads((ROOT/"results/sep_oct_2026_two_month_ohlc_proxy.json").read_text())
    if len(result)!=expected["sessions"] or not math.isclose(result[-1]["wealth"],expected["final"],abs_tol=1e-6):
        raise SystemExit("REPRODUCIBILITY_MISMATCH")
    print(json.dumps({"status":"OHLC_PROXY_REPRODUCED_NOT_EXECUTABLE","sessions":len(result),
                      "final_wealth":result[-1]["wealth"],"orders_enabled":False}))
if __name__=="__main__":main()
