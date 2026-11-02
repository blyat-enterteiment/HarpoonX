"""Reuse Decimal swing ledger verifier through an explicit metadata-only adapter."""
import json,tempfile,shutil,argparse
from pathlib import Path
from verify_swing8 import verify

def check(directory):
    with tempfile.TemporaryDirectory() as tmp:
        target=Path(tmp)
        for path in directory.glob('*.json.gz'):shutil.copyfile(path,target/path.name)
        report=json.loads((directory/'report.json').read_text())
        report['observed_live_fills']=report['live_fills']
        (target/'report.json').write_text(json.dumps(report))
        result=verify(target)
        result['metadata_adapter']='live_fills mapped to observed_live_fills; account bytes unchanged'
        return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args();print(json.dumps(check(a.directory),indent=2,sort_keys=True))
