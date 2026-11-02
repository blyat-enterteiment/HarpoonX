"""Synthetic engineering counterexample; no model fitting, broker or financial trial."""
from __future__ import annotations
import copy
import json
import sys
from pathlib import Path
APP = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(APP / 'quant'), str(APP / 'quant' / 'tests')]
from test_fixed_predictor import FixedPredictorTests
from harpoon_quant.bridge import from_runtime
from harpoon_quant.core import Config
FixedPredictorTests.setUpClass()
test=FixedPredictorTests()
packet=test.packet()
raw=json.loads(packet['request_json'])
model=json.loads(packet['model_json'])
cases=[]
for name, overrides, state in [
 ('original_fixture', {}, {}),
 ('stricter_asset_cap', {'asset_fraction':0.001}, {}),
 ('stricter_gross_cap', {'gross_fraction':0.001}, {}),
 ('stricter_factor_cap', {'factor_fraction':0.001}, {}),
 ('stricter_daily_loss', {'daily_loss_fraction':0.001}, {'daily_pnl':-30}),
 ('stricter_drawdown', {'drawdown_fraction':0.001}, {'drawdown_fraction':0.002}),
 ('larger_slippage_assumption', {'slippage_bps':500}, {}),
 ('zero_quote_age', {'max_quote_age_seconds':0}, {}),
 ('zero_daily_loss', {'daily_loss_fraction':0}, {}),
 ('zero_drawdown', {'drawdown_fraction':0}, {}),
 ('invalid_zero_positions', {'max_positions':0}, {}),
 ('negative_risk_rejected_direct_but_ignored_in_bridge', {'gross_fraction':-0.1}, {}),
 ('boolean_risk_rejected_direct_but_ignored_in_bridge', {'gross_fraction':False}, {}),
]:
 candidate=copy.deepcopy(raw)
 candidate['config'].setdefault('quant',{}).setdefault('config',{}).update(overrides)
 candidate.update(state)
 direct=None
 try:
  Config(**candidate['config']['quant']['config'])
  direct='ACCEPTED'
 except (TypeError,ValueError) as e: direct=str(e)
 try:
  out=from_runtime(candidate,model)
  selected=[{'id':s['id'],'quantity':s['quantity'],'cash_committed_usd':s.get('cash_committed_usd')} for s in out.get('selected',[])]
  result={'status':out.get('status'),'reason':out.get('reason'),'selected':selected,'execution_allowed':out.get('execution_allowed')}
 except (TypeError,ValueError) as e: result={'exception':type(e).__name__,'reason':str(e)}
 cases.append({'case':name,'core_config':overrides,'account_state':state,'direct_config':direct,'bridge':result})
print(json.dumps({'nature':'SYNTHETIC_ENGINEERING_ONLY','model_fits':0,'financial_trials':0,'app':str(APP),'cases':cases},indent=2))
