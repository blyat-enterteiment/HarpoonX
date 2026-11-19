"""HF37 preregistered sector/whale research universe.
Candidate membership is contemporary and MUST NOT be treated as point-in-time.
No whale identities inferred from OHLCV, and no orders.
"""
import hashlib,json
SECTORS={
"Information Technology":(("NVDA","MSFT","AAPL"),"XLK"),
"Communication Services":(("META","GOOGL","NFLX"),"XLC"),
"Consumer Discretionary":(("AMZN","TSLA","HD"),"XLY"),
"Consumer Staples":(("WMT","COST","PG"),"XLP"),
"Financials":(("JPM","BAC","GS"),"XLF"),
"Health Care":(("LLY","UNH","ABBV"),"XLV"),
"Industrials":(("CAT","GE","DE"),"XLI"),
"Energy":(("XOM","CVX","COP"),"XLE"),
"Materials":(("LIN","FCX","NEM"),"XLB"),
"Utilities":(("NEE","SO","DUK"),"XLU"),
"Real Estate":(("PLD","AMT","EQIX"),"XLRE")}
def manifest():
    symbols=[s for stocks,etf in SECTORS.values() for s in stocks]
    etfs=[etf for _,etf in SECTORS.values()]
    if len(SECTORS)!=11 or len(symbols)!=33 or len(set(symbols))!=33 or len(set(etfs))!=11:
        raise ValueError("UNIVERSE_INTEGRITY")
    canonical=json.dumps(SECTORS,sort_keys=True,separators=(",",":")).encode()
    return {"phase":"HF37_WHALE_FOOTPRINT","sectors":len(SECTORS),"stocks":len(symbols),
      "sector_etfs":len(etfs),"candidate_universe":SECTORS,
      "universe_sha256":hashlib.sha256(canonical).hexdigest(),
      "selection":"EXPLORATORY_CONVENIENCE_NOT_POINT_IN_TIME",
      "data_gate":"TRADE_AND_QUOTE_EVENTS_REQUIRED",
      "feed_iex_not_sip":True,"whale_identity_known":False,
      "production_sizing_allowed":False,"holdout_november_2026_opened":False,
      "orders_enabled":False,"status":"NO_GO_DATA_ACQUISITION_REQUIRED"}
if __name__=="__main__":
    print("HF37_MANIFEST "+json.dumps(manifest(),sort_keys=True),flush=True)
