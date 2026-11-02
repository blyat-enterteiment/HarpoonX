#!/usr/bin/env python3
"""Bounded read-only swing study; no strategy search or broker calls."""
import argparse,gzip,hashlib,json,sys,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'quant'))
from harpoon_quant.multiasset import normalize,stamp
from harpoon_quant.swing import NY,UTC,normalize_daily,replay
from harpoon_quant.robust_core import mean_uncertainty
from datetime import datetime


def response(path):
    d=json.loads(path.read_text())
    r=d.get('response',d);s=r.get('structuredContent',{})
    if 'result' in s:return json.loads(s['result'])
    if r.get('content'):return json.loads(next(x['text'] for x in r['content'] if x['type']=='text'))
    return r


def inputs():
    protocol=json.loads((ROOT/'research/swing8/protocol.json').read_text())
    amendment=json.loads((ROOT/'research/swing8/amendment_01.json').read_text())
    start,end=map(stamp,amendment['evaluation_period'])
    sources=[ROOT/'research/swing8/protocol.json',ROOT/'research/swing8/amendment_01.json']
    hp=sorted((ROOT/'research/multiasset8/raw').glob('*hourly_2025.json.gz'));sources+=hp
    hourly,coverage=normalize([json.loads(gzip.decompress(p.read_bytes())) for p in hp],protocol['symbols'],start,end)
    calpath=ROOT/'evidence/residual_30_18_0/data/raw/calendar.json';sources.append(calpath)
    cal=response(calpath)['calendar'];sessions={}
    for r in cal:
        sessions[r['date']]={k:datetime.fromisoformat(r[k]).replace(tzinfo=NY).astimezone(UTC) for k in ('open','close')}
    dp=[ROOT/'research/multiasset8/raw'/n for n in ('equity_daily.json.gz','crypto_daily.json.gz')];sources+=dp
    daily=normalize_daily([json.loads(gzip.decompress(p.read_bytes())) for p in dp],sessions)
    ap=ROOT/'evidence/residual_30_18_0/data/raw/corporate_actions.json';sources.append(ap)
    announcements=response(ap)['announcements'];actions=[]
    for key,rows in announcements.items():
        for a in rows:
            if key=='cash_dividends':actions.append({'kind':'dividend','symbol':a['symbol'],'date':a['ex_date'],
                     'rate':float(a['rate']),'pay':a['payable_date'],'id':a['id']})
            elif key in ('forward_splits','reverse_splits'):
                actions.append({'kind':'split','symbol':a['symbol'],'date':a['ex_date'],
                      'ratio':float(a['new_rate'])/float(a['old_rate']),'id':a['id']})
            elif rows:raise ValueError('UNSUPPORTED_CORPORATE_ACTION:'+key)
    manifests={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    return hourly,daily,sessions,actions,start,end,coverage,manifests


def run(output):
    output.mkdir(parents=True,exist_ok=False);started=time.perf_counter()
    hourly,daily,sessions,actions,start,end,coverage,manifest=inputs()
    summaries={};logs={}
    for stress in (False,True):
        for rule in ('BREAKOUT','GAP','RETEST','CASH'):
            key=('STRESS_' if stress else 'NOMINAL_')+rule
            result=replay(hourly,daily,sessions,actions,rule,stress,start,end)
            path=output/(key+'.json.gz');encoded=json.dumps(result,sort_keys=True,separators=(',',':')).encode()
            path.write_bytes(gzip.compress(encoded,mtime=0))
            summary={k:v for k,v in result.items() if k not in ('events','trades','curve','signals')}
            summary['trades']=len(result['trades']);summary['by_book']={b:{'trades':sum(t['book']==b for t in result['trades']),
                'net_before_fixed_and_dividends_usd':sum(t['net_usd'] for t in result['trades'] if t['book']==b)}for b in ('equity','crypto')}
            summary['max_holding_hours']=max([t['holding_hours'] for t in result['trades']],default=0)
            summary['min_planned_holding_hours']=min([(stamp(t['planned_exit'])-stamp(t['entry_at'])).total_seconds()/3600 for t in result['trades']],default=0)
            summary['exit_reasons']={reason:sum(t['exit_reason']==reason for t in result['trades']) for reason in ('TIME','TARGET','STOP','GAP_STOP')}
            summary['gross_before_all_costs_usd']=result['net_usd']+result['fixed_cost_usd']+result['variable_cost_usd']
            summaries[key]=summary
            e=np.array([20000]+[r['equity'] for r in result['curve']]);logs[key]=np.diff(np.log(e))
    stats={}
    for key,x in logs.items():
        if key.endswith('_CASH'):continue
        cash='STRESS_CASH' if key.startswith('STRESS_') else 'NOMINAL_CASH'
        stat=mean_uncertainty(x-logs[cash],5);stat['descriptive_lower_mean_3se']=stat['mean']-3*stat['standard_error'];stats[key]=stat
    report={'schema':'HARPOON_SWING8_STUDY_1','accounts':summaries,'coverage':coverage,'input_sha256':manifest,
        'daily_log_growth_vs_cash':stats,'corporate_action_covered_symbols':['AAPL','MSFT','XLK'],
        'full_equity_corporate_action_coverage':False,'2026_extension_executed':False,
        'observed_live_fills':0,'costs_fill_calibrated':False,'level8_accredited':False,'execution_allowed':False,
        'signal_accuracy_proven':False,'source_availability_assumed':True,
        'runtime_seconds':time.perf_counter()-started,
        'limitations':['OHLC_MODEL_NOT_EXECUTABLE_QUOTES','PARTIAL_CORPORATE_ACTION_COVERAGE',
          'NO_NEW_UNIVERSE_CONSTITUENTS_OR_DELISTINGS','HISTORY_REUSED','NO_FRESH_HOLDOUT',
          'HOURLY_PATH_AND_LIQUIDITY_UNVERIFIED','2026_PROVIDER_TIMEOUTS','NO_REAL_FILL_CALIBRATION']}
    (output/'report.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.glob('*'))}
    (output/'sha256.json').write_text(json.dumps(hashes,sort_keys=True,indent=2)+'\n')
    print(json.dumps(summaries,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,required=True);args=p.parse_args();run(args.output_dir)
