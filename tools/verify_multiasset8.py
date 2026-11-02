#!/usr/bin/env python3
"""Separate ledger verification, Decimal accounting; no trading or model fitting."""
import argparse
import gzip
import hashlib
import json
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'quant'))
from harpoon_quant.multiasset import stamp

ROOT=Path(__file__).resolve().parents[1]
D=lambda v:Decimal(str(v))
TOL=Decimal('0.0000001')


def need(ok,reason):
    if not ok:raise ValueError(reason)


def verify(directory):
    report=json.loads((directory/'report.json').read_text())
    for rel,expected in report['manifest'].items():
        path=ROOT/rel
        need(path.resolve().is_relative_to(ROOT),'PATH_ESCAPE')
        need(hashlib.sha256(path.read_bytes()).hexdigest()==expected,'INPUT_HASH')
        if path.suffix=='.gz':json.loads(gzip.decompress(path.read_bytes()))
    receipts={}
    for name,summary in report['accounts'].items():
        account=json.loads((directory/(name+'.json')).read_text())
        by_day=defaultdict(list)
        for t in account['trades']:
            entered,exited=stamp(t['entry_at']),stamp(t['exit_at'])
            need(stamp(t['signal_known_at'])<entered<exited,'SIGNAL_OR_FILL_CHRONOLOGY')
            need((exited-entered).total_seconds()<=72*3600,'HOLDING_72H')
            qty,entry,exit_=map(D,(t['qty'],t['entry_price'],t['exit_price']))
            rate=D(.0035 if t['book']=='crypto' else .0005)*(2 if account['stress'] else 1)
            debit=qty*entry*(1+rate);credit=qty*exit_*(1-rate)
            need(qty>0 and (t['book']=='crypto' or qty==qty.to_integral()),'LOT_DOMAIN')
            need(qty*entry<=D(t['observed_trailing_capacity_usd'])+TOL,'CAPACITY')
            need(abs(debit-D(t['debit_usd']))<TOL and abs(credit-D(t['credit_usd']))<TOL,'FILL_VALUE')
            need(abs(credit-debit-D(t['net_usd']))<TOL,'TRADE_NET')
            need(t['fill_nature']=='MODELED','MODEL_MISLABEL')
            by_day[t['entry_at'][:10]].append((t,debit,credit))
        cash=D(account['initial_usd']);max_error=D(0)
        cost=D(2 if account['stress'] else 1)
        for row in account['curve']:
            cash-=cost
            entries=by_day[row['day']]
            gross=sum((D(t['qty'])*D(t['entry_price']) for t,d,c in entries),D(0))
            crypto=sum((D(t['qty'])*D(t['entry_price']) for t,d,c in entries if t['book']=='crypto'),D(0))
            need(gross<=D('.6')*cash+TOL and crypto<=D('.2')*cash+TOL,'EXPOSURE_CAP')
            need(all(D(t['qty'])*D(t['entry_price'])<=D('.2')*cash+TOL for t,d,c in entries),'SINGLE_NAME_CAP')
            debit=sum((d for t,d,c in entries),D(0));credit=sum((c for t,d,c in entries),D(0))
            need(cash>=debit,'UNFUNDED_BUYS')
            cash+=credit-debit
            error=abs(cash-D(row['equity']));max_error=max(error,max_error)
            need(error<TOL and row['positions']==0,'DAILY_LEDGER')
        need(abs(cash-D(account['terminal_usd']))<TOL,'TERMINAL_EQUITY')
        need(abs(cash-D(20000)-D(summary['net_usd']))<TOL,'SUMMARY_NET')
        need(account['execution_allowed'] is False and account['level8_accredited'] is False,'AUTHORITY')
        receipts[name]={'verified_trades':len(account['trades']),'days':len(account['curve']),
                        'max_decimal_ledger_error_usd':float(max_error)}
    need(report['level8_accredited'] is False and report['observed_live_fills']==0,'UNSUPPORTED_ACCEPTANCE')
    return {'verified':True,'scope':'MODELED_ACCOUNT_ARITHMETIC_CHRONOLOGY_INPUT_HASHES_ONLY',
            'independent_external_validation':False,'accounts':receipts}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--compare',type=Path);args=p.parse_args()
    receipt=verify(args.directory)
    if args.compare:
        verify(args.compare)
        for name in json.loads((args.directory/'report.json').read_text())['accounts']:
            a=json.loads((args.directory/(name+'.json')).read_text())
            b=json.loads((args.compare/(name+'.json')).read_text())
            need(len(a['trades'])==len(b['trades']),'REPLAY_TRADE_COUNT')
            for x,y in zip(a['trades'],b['trades'],strict=True):
                for field in ('symbol','book','entry_at','exit_at','signal_known_at','qty','entry_price','exit_price','fill_nature'):
                    need(x[field]==y[field],'REPLAY_EXACT_'+field)
                for field in ('debit_usd','credit_usd','net_usd','modeled_cost_usd'):
                    need(abs(D(x[field])-D(y[field]))<TOL,'REPLAY_CURRENCY_'+field)
            need(len(a['curve'])==len(b['curve']),'REPLAY_DAYS')
            for x,y in zip(a['curve'],b['curve'],strict=True):
                need(x['day']==y['day'] and abs(D(x['equity'])-D(y['equity']))<TOL,'REPLAY_CURVE')
        receipt['reference_accounts_reproduced']=True
        receipt['currency_comparison_tolerance_usd']=float(TOL)
        receipt['trade_quantity_price_identity_comparison']='EXACT'
    print(json.dumps(receipt,indent=2,sort_keys=True))
