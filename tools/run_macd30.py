"""Research-only scoped adapter. Never alters sealed swing source or broker."""
import gzip,hashlib,json,sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'quant'))
from run_swing8 import inputs
from harpoon_quant.macd30 import make_candidate
from harpoon_quant.swing import replay

def run(output):
    output.mkdir(parents=True,exist_ok=False)
    hourly,daily,sessions,actions,start,end,coverage,manifest=inputs();summary={}
    for stress in (False,True):
        for variant in ('CROSS','CONFIRMED','EARLY'):
            with patch('harpoon_quant.swing.candidate',make_candidate(daily,variant)):
                r=replay(hourly,daily,sessions,actions,'BREAKOUT',stress,start,end)
            name=('STRESS_' if stress else 'NOMINAL_')+variant
            data=json.dumps(r,sort_keys=True,separators=(',',':')).encode();(output/(name+'.json.gz')).write_bytes(gzip.compress(data,mtime=0))
            summary[name]={k:v for k,v in r.items() if k not in ('trades','curve','signals','events')}
            summary[name]['trade_count']=len(r['trades'])
    report={'accounts':summary,'input_sha256':manifest,'level8_accredited':False,'live_fills':0,
            'limitations':['2025_REUSED_HISTORY','PARTIAL_CORPORATE_ACTIONS','NO_NEW_FILLS','NO2026_VALIDATION'],
            'protocol_sha256':hashlib.sha256((ROOT/'research/macd30/protocol.json').read_bytes()).hexdigest()}
    (output/'report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    (output/'sha256.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.glob('*')},indent=2)+'\n')
    print(json.dumps(summary,indent=2))
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,required=True);run(p.parse_args().output_dir)
