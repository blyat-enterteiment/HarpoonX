"""Generate three frozen exploratory recipes on globally reused historical data."""
import copy
import json
import math
import sys
from pathlib import Path
import residual_model as model

ROOT=Path(__file__).resolve().parents[1]
POLICIES=['CONTINUATION','STABILIZED_NORMALIZE','REVERSAL_INVALIDATE']

def prepare():
 p=json.loads((ROOT/'research/residual_30_18/protocol.json').read_text())
 data=json.loads((ROOT/p['dataset']).read_text())
 fitted=model.fit_models(data,p);old=model.generate_signals(data,fitted,p)
 panel=model._Panel(data)
 out={s:{k:[] for k in POLICIES} for s in p['scenarios']}
 for day in old['daily_decisions']:
  valid=[c for c in day['candidates'].values() if c['admissible']]
  if not valid:continue
  session=next(s for s in data['sessions'] if s['date']==day['date'])
  for scenario,cost in p['scenarios'].items():
   c=max(valid,key=lambda c:(c['z'],c['symbol']))
   friction=(cost['spread_bps']+2*cost['slippage_bps'])/10000+2*cost['commission_usd_per_share_per_side']/c['price']
   if c['z']>=1.5 and .5*(c['residual']-fitted['models'][c['symbol']]['mu'])>friction+.0005:
    out[scenario]['CONTINUATION'].append({'id':f"R9:{scenario}:CONTINUATION:{day['date']}:{c['symbol']}",
     'symbol':c['symbol'],'hypothesis':'CLOSED_CHANNEL','direction':1,'at':day['at'],
     'plannedEntryAt':day['planned_entry_at'],'index':0,'stopDistance':c['stop_distance'],'regime':.4,
     'metadata':{'economicHypothesis':'RESIDUAL_CONTINUATION_NOT_CALIBRATED_EXPECTATION'}})
   bases=[s for s in old['signals'][scenario]['RESIDUAL_LONG'] if s['at']==day['at']]
   for base in bases:
    symbol=base['symbol'];m=fitted['models'][symbol]
    stock=panel.bars(symbol,session['open'],session['open']+300000)[0]
    sector=panel.bars('XLK',session['open'],session['open']+300000)[0]
    meta={'stock':symbol,'stockOpen':stock['o'],'sectorOpen':sector['o'],'beta':m['beta'],'mu':m['mu'],'sigma':m['sigma']}
    for policy in POLICIES[1:]:
     signal=copy.deepcopy(base);signal['id']=f"R9:{scenario}:{policy}:{day['date']}:{symbol}"
     signal['metadata']['researchExit']={**meta,'mode':'NORMALIZE' if policy=='STABILIZED_NORMALIZE' else 'INVALIDATE'}
     if policy=='STABILIZED_NORMALIZE':
      r={**p['recipe'],'entry_minutes':65}
      at=session['open']+65*60000+1000
      a,ea=panel.shock(symbol,session,r);b,eb=panel.shock('XLK',session,r)
      if ea or eb:continue
      z=(a['return']-m['beta']*b['return']-m['mu'])/m['sigma']
      if not base['metadata']['candidate_z']<z<=-.5:continue
      signal.update(at=at,plannedEntryAt=session['open']+70*60000)
     out[scenario][policy].append(signal)
 return p,data,out

if __name__=='__main__':
 target=Path(sys.argv[1])
 with target.open('x') as f:json.dump(prepare()[2],f,allow_nan=False)
