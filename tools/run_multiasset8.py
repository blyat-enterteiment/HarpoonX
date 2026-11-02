#!/usr/bin/env python3
"""Reproduce only the frozen multiasset study; no network and no broker writes."""
import argparse
import hashlib
import gzip
import json
import math
import sys
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'quant'))
from harpoon_quant.multiasset import normalize,replay,stamp
from harpoon_quant.robust_core import mean_uncertainty


def run(output: Path):
    output.mkdir(parents=True,exist_ok=False)
    raw=ROOT/'research/multiasset8/raw'
    paths=sorted(raw.glob('*hourly_2025.json.gz'))
    protocol=json.loads((ROOT/'research/multiasset8/protocol.json').read_text())
    panel,coverage=normalize([json.loads(gzip.decompress(p.read_bytes())) for p in paths],protocol['data']['symbols'],
                             stamp('2025-01-01T00:00:00Z'),stamp('2026-01-01T00:00:00Z'))
    manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    manifest['research/multiasset8/protocol.json']=hashlib.sha256((ROOT/'research/multiasset8/protocol.json').read_bytes()).hexdigest()
    accounts={}
    for stress in (False,True):
        for mode in ('JOINT','SLEEVES','CASH'):
            key=('STRESS_' if stress else 'NOMINAL_')+mode
            result=replay(panel,mode,stress)
            accounts[key]={k:v for k,v in result.items() if k not in ('trades','curve')}
            accounts[key]['trade_count']=len(result['trades'])
            accounts[key]['by_book']={b:{'trades':sum(t['book']==b for t in result['trades']),
                'net_before_shared_fixed_usd':sum(t['net_usd'] for t in result['trades'] if t['book']==b)} for b in ('equity','crypto')}
            accounts[key]['quarter_end_equity_usd']={str(q):[r['equity'] for r in result['curve'] if (int(r['day'][5:7])-1)//3+1==q][-1] for q in range(1,5)}
            (output/(key+'.json')).write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    comparison={}
    for prefix in ('NOMINAL_','STRESS_'):
        curves=[]
        for mode in ('JOINT','SLEEVES'):
            r=json.loads((output/(prefix+mode+'.json')).read_text())
            e=np.array([20000]+[v['equity'] for v in r['curve']])
            curves.append(np.diff(np.log(e)))
        paired=mean_uncertainty(curves[0]-curves[1],5)
        paired['descriptive_lower_mean_2_576se']=paired['mean']-2.576*paired['standard_error']
        comparison[prefix]=paired
    report={'schema':'HARPOON_MULTI_ASSET8_RESULT_1','accounts':accounts,'coverage':coverage,'manifest':manifest,
            'joint_minus_sleeves_daily_log_growth':comparison,'level8_accredited':False,
            'observed_live_fills':0,'calibration_status':'BLOCKED_NO_BROKER_ACTIVITY_ACCESS_OR_CAUSAL_RECEIPTS',
            'data_kind':'PROVIDER_RETURNED_HISTORICAL_OHLCV','fill_kind':'MODELED',
            'source_authenticity_independently_verified':False,'execution_allowed':False,
            'limitations':['FIXED_UNIVERSE_SURVIVORSHIP_NOT_RESOLVED','HISTORICAL_PERIOD_ALREADY_SEEN',
              'NO_FRESH_HOLDOUT','ASSUMED_BAR_AVAILABILITY','IEX_NOT_CONSOLIDATED_VOLUME_OR_NBBO',
              'NO_INTRABAR_RISK_OR_EXECUTABLE_QUOTES','INTRADAY_2H_NOT_SWING_VALIDATION',
              'NO_PROVEN_NET_ALPHA','COSTS_ASSUMED_NOT_OBSERVED','CASH_SETTLEMENT_NOT_MODELED']}
    (output/'report.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    checks={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.glob('*.json'))}
    (output/'sha256.json').write_text(json.dumps(checks,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'accounts':accounts,'level8_accredited':False},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,required=True)
    run(p.parse_args().output_dir)
