"""MNP risk-adjusted compound score, without manufacturing statistical significance."""
import math
def objective(books,reference="CASH",lambda_dd=1.0,lambda_ruin=10.0,
              ruin_floor=.7):
 if reference not in books:raise ValueError("REFERENCE_MISSING")
 if lambda_dd<0 or lambda_ruin<0 or not 0<ruin_floor<1:
  raise ValueError("INVALID_RISK_PENALTY")
 n=len(books[reference]["wealth"])-1
 if n<1:raise ValueError("NO_SESSIONS")
 out={}
 for name,b in books.items():
  path=b["wealth"]
  if len(path)!=n+1 or any(not math.isfinite(w) or w<=0 for w in path):
   raise ValueError("INVALID_PAIRED_WEALTH")
  log_g=math.log(path[-1]/path[0])/n
  dd=b["max_drawdown"]
  if not 0<=dd<1:raise ValueError("INVALID_DRAWDOWN")
  breached=min(path)<ruin_floor*path[0]
  # Empirical breach indicator is NOT an estimated probability of ruin.
  score=log_g-lambda_dd*dd/n-lambda_ruin*float(breached)/n
  out[name]={"log_growth_per_session":log_g,
    "geometric_growth_per_session":math.expm1(log_g),
    "drawdown":dd,"ruin_floor_breached":breached,
    "risk_penalized_log_score":score}
 base=out[reference]["log_growth_per_session"]
 for name in out:out[name]["paired_log_growth_advantage"]=out[name]["log_growth_per_session"]-base
 return {"status":"DESCRIPTIVE_NOT_INDEPENDENT_OOS","metrics":out,
   "risk_of_ruin_probability_estimated":False,"orders_enabled":False}
