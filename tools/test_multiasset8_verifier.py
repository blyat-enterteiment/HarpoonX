"""Mutate complete accounts to test the separate verifier, not its formulas."""
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('verify8',ROOT/'tools/verify_multiasset8.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class LedgerMutations(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.directory=Path(self.temp.name)/'run'
        shutil.copytree(ROOT/'evidence/multiasset8/run_01',self.directory)

    def tearDown(self):self.temp.cleanup()

    def mutate(self,change):
        path=self.directory/'NOMINAL_JOINT.json';value=json.loads(path.read_text())
        change(value);path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):module.verify(self.directory)

    def test_reset_capital_detected(self):
        self.mutate(lambda a:a['curve'][100].update(equity=20000))

    def test_late_quote_detected(self):
        self.mutate(lambda a:a['trades'][0].update(signal_known_at=a['trades'][0]['exit_at']))

    def test_quantity_tampering_detected(self):
        self.mutate(lambda a:a['trades'][0].update(qty=a['trades'][0]['qty']+1))

    def test_holding_excess_detected(self):
        self.mutate(lambda a:a['trades'][0].update(exit_at='2026-01-01T00:00:00Z'))

    def test_promotion_flag_detected(self):
        self.mutate(lambda a:a.update(level8_accredited=True))

    def test_variable_cost_tampering_detected(self):
        self.mutate(lambda a:a['trades'][0].update(net_usd=a['trades'][0]['net_usd']+1))

if __name__=='__main__':unittest.main()
