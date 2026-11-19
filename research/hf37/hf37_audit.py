"""HF37 coverage audit of existing archived historical IEX daily data.
No intraday tape invented; zero whale alpha trials without trades and quotes.
"""
import json
from research.hf30.hf30_regime import load,STOCKS,ETFS
from research.hf37.hf37_universe import SECTORS,manifest
def audit():
    dates,data,sha=load()
    candidate={s for names,etf in SECTORS.values() for s in names}
    benchmark={etf for names,etf in SECTORS.values()}
    overlap=sorted(candidate&STOCKS)
    etf_overlap=sorted(benchmark&ETFS)
    return {"phase":"HF37_DATA_GATE","status":"NO_GO_TRADE_QUOTE_TAPE_MISSING",
      "archived_daily_feed":"IEX","archived_daily_sessions":len(dates),
      "archive_sha256":sha,"candidate_stock_overlap":overlap,
      "candidate_sector_etf_overlap":etf_overlap,
      "missing_candidate_stocks":sorted(candidate-STOCKS),
      "missing_sector_etfs":sorted(benchmark-ETFS),
      "observed_hf37_intraday_trades":0,"observed_hf37_intraday_quotes":0,
      "whale_alpha_estimated":False,"capital_initial_usd":20000,
      "original_exact_comparison":False,"orders_enabled":False,
      "holdout_november_2026_opened":False}
if __name__=="__main__":
    print("HF37_AUDIT "+json.dumps(audit(),sort_keys=True),flush=True)
