"""Read-only synthetic counterexamples for economic v2 event risk functions."""
from __future__ import annotations
import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

APP = Path(sys.argv[1] if len(sys.argv) > 1 else '/workspace/scratch/4ecb05fdc50d/level5_work/HARPOON_XXXUltimate_30_12_0')
sys.path.insert(0, str(APP / 'quant'))
from harpoon_quant.economic_gate_v2 import summarize_policy, _risk

START = '2026-01-05T15:00:00+00:00'
END = '2026-01-05T15:02:00+00:00'
T0 = datetime.fromisoformat(START).timestamp() * 1000
P = {'initial_equity_usd': 100, 'universe': ['AAPL'], 'period': {'test_start': START, 'test_end': END}, 'evaluation_sessions': [{'session_id': '2026-01-05', 'start_at': START, 'end_at': END}], 'max_drawdown_fraction': .20, 'max_gross_exposure_fraction': 1.0, 'horizon_hours': 72}

def item(values, *, role='SVR', inventories=None, costs=None, fees=None):
    rows=[]
    for i, value in enumerate(values):
        inv=0 if inventories is None else inventories[i]
        cost=0 if costs is None else costs[i]
        fee=0 if fees is None else fees[i]
        rows.append({'event_id': f'SYNTH-{i}', 'at': T0+i*60_000, 'session_id': '2026-01-05', 'cash_usd': value-inv, 'inventory_value_usd': inv, 'account_equity_usd': value, 'economic_equity_usd': value-cost, 'cumulative_fees_usd': fee, 'cumulative_external_cost_usd': cost, 'external_flow_usd': 0, 'positions': [{'symbol':'AAPL','qty':1,'market_value':inv}] if inv else []})
    return {'role':role,'initial_equity_usd':100,'events':rows,'maximum_observed_holding_hours':0,'stale_terminal_valuation_symbols':[],'execution_io_failure_count':0}

tests=[]
def capture(name, fn, predicate):
    try:
        value=fn()
        tests.append({'id':name,'passed':bool(predicate(value)),'result':value,'error':None})
    except Exception as exc:
        tests.append({'id':name,'passed':False,'result':None,'error':f'{type(exc).__name__}: {exc}'})

def diagnose(x):
    summary=summarize_policy(x,P)
    return {'summary':summary,'risk_reasons':_risk(summary,P)}

capture('POSITIVE_CONTROL_EVENT_RECONCILIATION',lambda:diagnose(item([100,101,102])),lambda x:x['summary']['net_pnl_usd']==2 and not x['risk_reasons'])
capture('L5-B1-INTRADAY_DRAWDOWN',lambda:diagnose(item([100,60,102])),lambda x:x['summary']['maximum_drawdown_fraction']==.4 and 'EVENT_DRAWDOWN_LIMIT_EXCEEDED' in x['risk_reasons'] and x['summary']['session_count']==1)
capture('L5-B2-INTRADAY_EXPOSURE',lambda:diagnose(item([100,100,102],inventories=[0,120,0])),lambda x:x['summary']['maximum_gross_exposure_fraction']==1.2 and 'EVENT_EXPOSURE_LIMIT_EXCEEDED' in x['risk_reasons'])
capture('L5-B1-INSOLVENCY_THEN_RECOVERY',lambda:diagnose(item([100,-1,102])),lambda x:x['summary']['insolvency'] is True and 'INSOLVENCY_NOT_CLIPPED' in x['risk_reasons'])
capture('L5-C3-ECONOMIC_CASH_UNFUNDED',lambda:diagnose(item([100,100,100],inventories=[0,100,100],costs=[0,10,10])),lambda x:x['summary']['final_equity_usd']==90 and 'EXTERNAL_COST_FINANCING_NOT_AVAILABLE' in x['risk_reasons'])
capture('L5-B3-MULTIPLE_FEES_PRESERVED',lambda:diagnose(item([100,99,97],fees=[0,1,3])),lambda x:x['summary']['fees_usd']==3 and x['summary']['net_pnl_usd']==-3)
capture('L5-C3-CASH_PAYS_IDENTICAL_COST',lambda:diagnose(item([100,100,100],role='CASH',costs=[0,7,10])),lambda x:x['summary']['external_cost_usd']==10 and x['summary']['final_equity_usd']==90 and x['summary']['maximum_gross_exposure_fraction']==0)
try:
    summarize_policy(item([100,99,97],fees=[0,3,1]),P)
    fee_error=None
except Exception as exc:
    fee_error=str(exc)
tests.append({'id':'L5-B3-FEES_CANNOT_DISAPPEAR','passed':fee_error=='EVENT_COST_FLOW_SCOPE','error':fee_error})

result={'scope':'Synthetic function-level adversarial checks, no market/account evidence and no financial experiment','observed_at_utc':datetime.now(timezone.utc).isoformat(),'source_sha256':hashlib.sha256((APP/'quant/harpoon_quant/economic_gate_v2.py').read_bytes()).hexdigest(),'financial_gate_executed':False,'production_edits':0,'new_economic_experiments':0,'passed':sum(x['passed'] for x in tests),'total':len(tests),'tests':tests}
Path(__file__).with_suffix('.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='tests'},ensure_ascii=False))
for row in tests:
    print(json.dumps({'id':row['id'],'passed':row['passed'],'error':row.get('error')},ensure_ascii=False))
raise SystemExit(0 if result['passed']==result['total'] else 1)
