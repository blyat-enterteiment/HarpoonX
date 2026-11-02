"""Mutation tests over archived model accounts. Not independent financial validation."""
import gzip,importlib.util,json,shutil,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('verify_swing',ROOT/'tools/verify_swing8.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class SwingLedgerMutations(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.directory=Path(self.tmp.name)/'run'
        shutil.copytree(ROOT/'evidence/swing8/run_01',self.directory)
    def tearDown(self):self.tmp.cleanup()
    def mutate(self,change):
        p=self.directory/'NOMINAL_BREAKOUT.json.gz';a=json.loads(gzip.decompress(p.read_bytes()));change(a)
        p.write_bytes(gzip.compress(json.dumps(a).encode(),mtime=0))
        with self.assertRaises(ValueError):module.verify(self.directory)
    def test_capital_reset(self):self.mutate(lambda a:a['curve'][100].update(equity=20000))
    def test_cash_delta_forgery(self):
        def change(a):next(e for e in a['events'] if e['kind']=='BUY')['cash_delta']+=10
        self.mutate(change)
    def test_inventory_forgery(self):
        def change(a):next(r for r in a['curve'] if r['positions'])['positions'][0]['qty']+=1
        self.mutate(change)
    def test_signal_from_future(self):self.mutate(lambda a:a['trades'][0].update(signal_known_at=a['trades'][0]['exit_at']))
    def test_holding_over72(self):self.mutate(lambda a:a['trades'][0].update(planned_exit='2026-01-01T12:00:00Z'))
    def test_model_cannot_be_marked_real(self):self.mutate(lambda a:a['trades'][0].update(fill_nature='REAL'))
    def test_promotion_rejected(self):self.mutate(lambda a:a.update(level8_accredited=True))

if __name__=='__main__':unittest.main()
