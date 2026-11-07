#!/usr/bin/env python3
"""Decimal ledger verifier, separate from replay. Same author, not external audit."""
import argparse,gzip,hashlib,json,sys
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'quant'))
from harpoon_quant.swing_evidence import verify_account
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
        receipts[name] = verify_account(a)
        need(abs(D(a['net_usd'])-D(report['accounts'][name]['net_usd']))<TOL,'SUMMARY_VALUE')
    need(report['level8_accredited'] is False and report['observed_live_fills']==0,'UNSUPPORTED_ACCEPTANCE')
    return {'verified':True,'scope':'MODEL_LEDGER_INPUT_HASHES_SIGNAL_AND_HOLDING_CHRONOLOGY',
            'independent_external_audit':False,'accounts':receipts}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);args=p.parse_args()
    print(json.dumps(verify(args.directory),indent=2,sort_keys=True))
