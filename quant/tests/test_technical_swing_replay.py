"""Replay the public research command against the six archived economic accounts."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class ReplayIntegration(unittest.TestCase):
    def test_six_accounts_reconcile_and_match_archived_outcomes(self):
        expected = json.loads(
            (ROOT / "evidence/technical_swing/results.json").read_bytes()
        )
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "reproduction"
            subprocess.run(
                [
                    sys.executable,
                    "tools/run_technical_swing.py",
                    "--output-dir",
                    str(out),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                timeout=180,
                env={
                    **os.environ,
                    "PYTHONPATH": os.pathsep.join(
                        [str(ROOT / "quant"), str(ROOT / "tools")]
                    ),
                    "OPENBLAS_NUM_THREADS": "1",
                    "OMP_NUM_THREADS": "1",
                },
            )
            actual = json.loads((out / "results.json").read_bytes())
        self.assertEqual(actual["decision"], expected["decision"])
        self.assertEqual(set(actual["accounts"]), set(expected["accounts"]))
        self.assertFalse(actual["execution_allowed"])
        for name, account in expected["accounts"].items():
            with self.subTest(name=name):
                observed = actual["accounts"][name]
                self.assertTrue(observed["decimal_reconciled"])
                self.assertEqual(observed["closed"], account["closed"])
                self.assertEqual(observed["net_usd"], account["net_usd"])
                self.assertLessEqual(observed["max_decision_to_exit_hours"], 72)
                self.assertAlmostEqual(
                    observed["max_event_drawdown"],
                    account["max_event_drawdown"],
                    places=10,
                )
        for name, bounds in expected["lower_mean_daily_log_growth"].items():
            for metric, value in bounds.items():
                self.assertAlmostEqual(
                    actual["lower_mean_daily_log_growth"][name][metric],
                    value,
                    places=12,
                )
