"""Exercise the registered multiasset command on the original historical inputs."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class CompoundIntegration(unittest.TestCase):
    def test_funded_reruns_obey_caps_and_reconcile(self):
        reference = json.loads(
            (ROOT / "evidence/compound_swing/report.json").read_bytes()
        )
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "replay"
            subprocess.run(
                [
                    sys.executable,
                    "tools/run_compound_swing.py",
                    "--output-dir",
                    str(out),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                timeout=120,
                env={
                    **os.environ,
                    "PYTHONPATH": os.pathsep.join(
                        [str(ROOT / "tools"), str(ROOT / "quant")]
                    ),
                    "OPENBLAS_NUM_THREADS": "1",
                    "OMP_NUM_THREADS": "1",
                },
            )
            result = json.loads((out / "report.json").read_bytes())
            audit = json.loads((out / "audit.json").read_bytes())
        self.assertTrue(audit["verified"])
        self.assertEqual(result["decision"], reference["decision"])
        self.assertEqual(len(result["accounts"]), 8)
        for name, a in result["accounts"].items():
            with self.subTest(name=name):
                self.assertEqual(a["trades"], reference["accounts"][name]["trades"])
                self.assertAlmostEqual(
                    a["net_usd"], reference["accounts"][name]["net_usd"], places=6
                )
                self.assertLessEqual(a["max_hold_hours"], 72)
                self.assertLessEqual(a["max_entry_gross"], 0.12 + 1e-10)
                self.assertLessEqual(a["max_entry_open_risk"], 0.0025 + 1e-10)
                self.assertEqual(audit["accounts"][name]["days"], 365)
                self.assertLess(audit["accounts"][name]["max_decimal_error_usd"], 1e-6)
                if name.endswith("EQUITY_ETF"):
                    self.assertEqual(a["crypto_trades"], 0)
                if name.endswith("_CRYPTO"):
                    self.assertEqual(a["trades"], a["crypto_trades"])
