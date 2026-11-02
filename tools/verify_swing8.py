#!/usr/bin/env python3
"""Decimal ledger verifier, separate from replay. Same author, not external audit."""
import argparse,gzip,hashlib,json,sys
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'quant'))
from harpoon_quant.multiasset import stamp
D=lambda x:Decimal(str(x));TOL=D('0.000001')

def need(ok,why):
    if not ok:raise ValueError(why)


def verify(directory):
    report=json.loads((directory/'report.json').read_text())
    for rel,h in report['input_sha256'].items():
        p=ROOT/rel;need(p.resolve().is_relative_to(ROOT),'SOURCE_PATH');need(hashlib.sha256(p.read_bytes()).hexdigest()==h,'SOURCE_HASH')
    receipts={}
    for name in report['accounts']:
        a=json.loads(gzip.decompress((directory/(name+'.json.gz')).read_bytes()))
        cash=D(20000);qty={};claims={};cursor=0;maxerror=D(0)
        for row in a['curve']:
            for e in a['events'][cursor:row['event_count']]:
                k=e['kind'];s=e.get('symbol');n=D(e.get('qty',0));px=D(e.get('price',0));fee=D(e.get('fee',0))
                if k=='BUY':
                    need(n>0 and s not in qty,'OVERLAPPING_OR_EMPTY_BUY')
                    need('/' in s or n==n.to_integral(),'WHOLE_EQUITY_LOT')
                    debit=n*px+fee;need(abs(-debit-D(e['cash_delta']))<TOL,'BUY_CASH')
                    need(cash>=debit,'UNFUNDED_ENTRY');cash-=debit;qty[s]=n
                elif k=='SELL':
                    need(s in qty and abs(qty[s]-n)<D('1e-10'),'NAKED_OR_PARTIAL_EXIT')
                    credit=n*px-fee;need(abs(credit-D(e['cash_delta']))<TOL,'SELL_CASH')
                    cash+=credit;del qty[s]
                elif k=='FIXED':
                    need(D(e['cash_delta'])==D(-2 if a['stress'] else -1),'FIXED_COST');cash+=D(e['cash_delta'])
                elif k=='SPLIT':
                    need(s in qty and D(e['ratio'])>0,'SPLIT_WITHOUT_POSITION');qty[s]*=D(e['ratio'])
                elif k=='DIV_EX':
                    need(e['receipt'] not in claims,'DIVIDEND_DUPLICATED');claims[e['receipt']]=D(e['amount'])
                elif k=='DIV_PAY':
                    need(e['receipt'] in claims and abs(claims[e['receipt']]-D(e['cash_delta']))<TOL,'DIVIDEND_PAYMENT')
                    cash+=claims.pop(e['receipt'])
                else:raise ValueError('UNKNOWN_EVENT')
            cursor=row['event_count'];holdings={p['symbol']:p for p in row['positions']}
            need(set(holdings)==set(qty),'INVENTORY_FRAME')
            for s,n in qty.items():need(abs(n-D(holdings[s]['qty']))<D('1e-10'),'INVENTORY_QUANTITY')
            receivables=sum(claims.values(),D(0))
            eq=cash+receivables+sum((qty[s]*D(holdings[s]['mark']) for s in qty),D(0))
            err=abs(eq-D(row['equity']));maxerror=max(maxerror,err)
            need(err<TOL and abs(cash-D(row['cash']))<TOL,'DAILY_LEDGER')
            need(abs(receivables-D(row['receivables']))<TOL,'RECEIVABLE_FRAME')
        need(cursor==len(a['events']) and not qty,'UNRECONCILED_TERMINAL_EVENTS')
        need(abs(cash+sum(claims.values(),D(0))-D(a['terminal_usd']))<TOL,'TERMINAL_VALUE')
        need(abs(D(a['net_usd'])-D(report['accounts'][name]['net_usd']))<TOL,'SUMMARY_VALUE')
        for t in a['trades']:
            entered,exited,planned=map(stamp,(t['entry_at'],t['exit_at'],t['planned_exit']))
            need(stamp(t['signal_known_at'])<entered<=exited<=planned,'CAUSALITY_OR_EXIT_AFTER_PLAN')
            need(24<=(planned-entered).total_seconds()/3600<=72,'PLANNED_SWING_HORIZON')
            need((exited-entered).total_seconds()/3600<=72,'HARD_HOLD_LIMIT')
            need(t['fill_nature']=='MODELED','FALSE_REAL_FILL')
            if t['exit_reason']=='STOP':need(t['exit_price']<=t['stop_at_entry'],'STOP_PRICE')
        need(a['execution_allowed'] is False and a['level8_accredited'] is False,'AUTHORITY')
        receipts[name]={'trades':len(a['trades']),'days':len(a['curve']),'max_decimal_error_usd':float(maxerror)}
    need(report['level8_accredited'] is False and report['observed_live_fills']==0,'UNSUPPORTED_ACCEPTANCE')
    return {'verified':True,'scope':'MODEL_LEDGER_INPUT_HASHES_SIGNAL_AND_HOLDING_CHRONOLOGY',
            'independent_external_audit':False,'accounts':receipts}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);args=p.parse_args()
    print(json.dumps(verify(args.directory),indent=2,sort_keys=True))
