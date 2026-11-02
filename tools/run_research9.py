#!/usr/bin/env python3
"""Reproduce the bounded exploratory family; retain accounts, failures and hashes."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from audit_historical_results import audit_report
from profitability_forensics import analyze_report
from residual_statistics import block_means

ROOT=Path(__file__).resolve().parents[1]
POLICIES=['CONTINUATION','STABILIZED_NORMALIZE','REVERSAL_INVALIDATE']
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,value):Path(p).write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n')

def verify_sources():
 frozen=read(ROOT/'research/research9_30_19/freeze.json')
 amendment=read(ROOT/'research/research9_30_19/amendment_01.json')
 expected={**frozen['source_sha256'],**amendment['source_sha256']}
 for p,h in expected.items():
  if sha(ROOT/p)!=h:raise ValueError('FROZEN_SOURCE_MISMATCH:'+p)
 return expected

def summarize(out):
 p=read(ROOT/'research/residual_30_18/protocol.json');data=read(ROOT/p['dataset'])
 results={};audits={};series=[];labels=[];incidents={}
 for scenario in ['NOMINAL','STRESS']:
  controls={k:read(ROOT/f'evidence/residual_30_18_0/run_completed/{scenario}_{k}.json') for k in ['RESIDUAL_LONG','STOCK_THRESHOLD_OFF','CASH']}
  for policy in POLICIES:
   key=scenario+':'+policy;file=out/(scenario+'_'+policy+'.json')
   if not file.exists():
    incidents[key]=read(out/(scenario+'_'+policy+'.incident.json'));continue
   r=read(file);audits[key]=audit_report(r,{**p,'holding_maximum_hours':72},data,key)
   results[key]=analyze_report(r)
   dates=[x['session_id'] for x in r['curve']]
   x=np.array([a['portfolio_log_return'] for a in r['curve']])
   labels.append(key+':growth');series.append(x)
   for name,c in controls.items():
    if dates!=[a['session_id'] for a in c['curve']]:raise ValueError('UNPAIRED_SESSIONS')
    labels.append(key+':minus:'+name);series.append(x-np.array([a['portfolio_log_return'] for a in c['curve']]))
 bounds={}
 if not incidents:
  matrix=np.array(series).T
  # Familywise descriptive lower tails only; global search not corrected.
  for block in [5,20]:
   draws=block_means(matrix,block,120000,1811)
   bounds[str(block)]={label:float(v) for label,v in zip(labels,np.quantile(draws,.05/24,axis=0),strict=True)}
 result={'schema':'HARPOON_RESEARCH9_DIAGNOSTIC_1','accounts':results,'accounting_audits':audits,'incidents':incidents,
  'lower_bounds_mean_session_log_return':bounds,'statistics_scope':'Descriptive post-registration diagnostics on globally reused history, 24 endpoints, blocks5/20,120000 draws. Not confirmatory or global selection correction.',
  'positive_net_both_cost_scenarios':{policy:all(results.get(s+':'+policy,{}).get('net_modeled_usd',float('-inf'))>0 for s in ['NOMINAL','STRESS']) for policy in POLICIES},
  'new_policy_scenario_variants':6,'engineering_retry_after_initial_failure':True,'history_already_seen':True,
  'level9_accredited':False,'liveApproved':False,'orders_allowed':False,'promotion_allowed':False}
 write(out/'diagnosis.json',result)
 hashes={f.name:sha(f) for f in sorted(out.glob('*.json')) if f.name!='result_hashes.json'}
 write(out/'result_hashes.json',hashes)
 return result

def main():
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('--output-dir',required=True,type=Path);a.add_argument('--summarize-existing',action='store_true');args=a.parse_args();out=args.output_dir.resolve()
 verify_sources()
 if not args.summarize_existing:
  if out.exists() and any(out.iterdir()):raise ValueError('OUTPUT_MUST_BE_NEW')
  out.mkdir(parents=True,exist_ok=True)
  subprocess.run([sys.executable,'-B','tools/research9_prepare.py',str(out/'signals.json')],cwd=ROOT,check=True)
  with (out/'replay.log').open('w') as log:subprocess.run(['node','tools/research9_replay.cjs',str(out)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
 result=summarize(out);print(json.dumps({'completed_accounts':len(result['accounts']),'incidents':len(result['incidents']),'positive_both_cost_scenarios':result['positive_net_both_cost_scenarios'],'level9_accredited':False}))

if __name__=='__main__':main()
