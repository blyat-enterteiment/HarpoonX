#!/usr/bin/env python3
"""Six frozen diagnostic measurements and exact reproduction; no strategy search."""
from __future__ import annotations
import argparse,bisect,hashlib,json,math,os,platform,subprocess,sys
from datetime import datetime,UTC
from pathlib import Path
APP=Path(__file__).resolve().parents[1];sys.path.insert(0,str(APP/'tools'))
import residual_register as reg
import residual_model as model
import residual_verify as verifier
import residual_statistics as statistics
from audit_historical_results import audit_report
read=verifier.read;write=verifier.write

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def beta_proxy(reports,data,models):
 sector=next(s for s in data['series'] if s['symbol']=='XLK');bars=sector['bars'];times=[b['availableAt'] for b in bars];opens={b['t']:b['o'] for b in bars};out={}
 for key,r in reports.items():
  rows=[]
  for trade in r['funded']:
   if trade['symbol']=='XLK':beta=1.0
   else: beta=models['models'][trade['symbol']].get('beta')
   j=bisect.bisect_right(times,trade['closed'])-1;start=opens.get(trade['opened'])
   if beta is None or start is None or j<0:raise ValueError('ATTRIBUTION_PRICE_UNAVAILABLE')
   factor=math.prod(e['ratio'] for e in data['splitEvents'] if e['symbol']=='XLK' and trade['opened']<e['at']<=bars[j]['end'])
   proxy_return=bars[j]['c']*factor/start-1;notional=trade['quantity']*trade['entry']
   rows.append({'campaign_id':trade['id'],'beta':beta,'entry_notional_usd':notional,'sector_split_adjusted_price_return':proxy_return,
    'sector_price_beta_proxy_usd':notional*beta*proxy_return,'stock_net_economic_usd':trade.get('netEconomicUsd',trade['netUsd']),
    'difference_is_not_alpha_or_hedge_pnl_usd':trade.get('netEconomicUsd',trade['netUsd'])-notional*beta*proxy_return,
    'sector_last_known_price_at':bars[j]['availableAt']})
  out[key]={'campaigns':rows,'sum_sector_price_beta_proxy_usd':sum(x['sector_price_beta_proxy_usd'] for x in rows),
  'scope':'Descriptive entry-notional beta times sector price-only holding-window return; excludes sector dividends/fees, partial exits, cash and different mark clocks. NOT executable hedge PnL, alpha estimate or risk-neutral comparison.'}
 return out

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--verify-against',type=Path);a=p.parse_args();os.chdir(APP);out=a.output_dir.resolve()
 if out.exists() and any(out.iterdir()):raise ValueError('OUTPUT_MUST_BE_NEW_RETAIN_ALL_ATTEMPTS')
 out.mkdir(parents=True,exist_ok=True)
 record={'schema':'HARPOON_RESIDUAL_RUN_1','started_at':datetime.now(UTC).isoformat(),'status':'STARTED','python':sys.version,'platform':platform.platform(),
 'purpose':'EXACT_REPRODUCTION' if a.verify_against else 'REGISTERED_GLOBALLY_SEEN_DIAGNOSTIC','financial_acceptance_allowed':False,'steps':[]}
 save=lambda n,v:write(out/n,v);save('run_receipt.json',record)
 try:
  protocol_path=APP/'research/residual_30_18/protocol.json';protocol=read(protocol_path)
  save('preflight_verification.json',verifier.verify(protocol_path))
  data=read(APP/protocol['dataset']);fitted=model.fit_models(data,protocol);save('models.json',fitted);save('signals.json',model.generate_signals(data,fitted,protocol))
  env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','PYTHONDONTWRITEBYTECODE':'1'}
  with (out/'replay.log').open('wb') as log:
   result=subprocess.run(['node','tools/residual_replay.cjs',str(protocol_path),str(APP/protocol['dataset']),str(out)],cwd=APP,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=1800)
  record['steps'].append({'name':'replay','exit_code':result.returncode,'log_sha256':sha(out/'replay.log')});save('run_receipt.json',record)
  if result.returncode:raise ValueError('REPLAY_FAILED_RETAINED')
  files=read(out/'reports.json');incidents=read(out/'incidents.json');reports={k:read(out/v) for k,v in files.items()}
  audits={};bound={**protocol,'holding_maximum_hours':protocol['risk_contract']['holding_maximum_calendar_hours']}
  for key,r in reports.items():
   if r['portfolio']['limits']!=protocol['limits']:raise ValueError('RISK_CAP_BINDING:'+key)
   audits[key]=audit_report(r,bound,data,key)
  save('accounting_audit.json',{'verified':True,'verified_scope':'Available complete reports only; incidents retain unknown terminal exposure, never zero returns','family_complete':not incidents,'expected_reports':8,'completed_reports':len(reports),'reports':audits,'financial_acceptance_allowed':False})
  save('statistics.json',statistics.analyze(reports,protocol) if not incidents else {'schema':'HARPOON_RESIDUAL_STATISTICS_BLOCKED_1','status':'INCOMPLETE_FAMILY_NO_VALID_FULL_CONTRAST','incidents':incidents,'financial_acceptance_allowed':False,'candidate_accepted':False,'statistical_gates_evaluable':False,'level8_accredited':False});save('summary.json',{k:r['summary'] for k,r in reports.items()});save('beta_proxy_attribution.json',beta_proxy(reports,data,fitted))
  names=['models.json','signals.json','derivation_verification.json','statistics.json','summary.json','accounting_audit.json','beta_proxy_attribution.json',*files.values(),*incidents.values(),'reports.json','incidents.json']
  hashes={name:sha(out/name) for name in names};save('result_hashes.json',hashes)
  if a.verify_against:
   before=read(a.verify_against/'result_hashes.json');mismatch=sorted(k for k in set(before)|set(hashes) if before.get(k)!=hashes.get(k))
   save('reproduction_verification.json',{'verified':not mismatch,'mismatches':mismatch,'files_compared':len(hashes),'new_policy_variants':0})
   if mismatch:raise ValueError('EXACT_REPRODUCTION_MISMATCH')
  record.update(status='COMPLETE_WITH_RETAINED_INCIDENTS' if incidents else 'COMPLETE',completed_at=datetime.now(UTC).isoformat(),hashes=hashes);save('run_receipt.json',record);print(f'COMPLETE: {len(reports)} reports and {len(incidents)} retained incidents; no financial acceptance')
 except Exception as e:
  record.update(status='FAILED_RETAINED',error=str(e),completed_at=datetime.now(UTC).isoformat());save('run_receipt.json',record);raise
if __name__=='__main__':main()
