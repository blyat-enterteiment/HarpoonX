"""Synthetic engineering counterexamples, never performance evidence."""

from __future__ import annotations

import copy
import gzip
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from harpoon_quant.qualification import qualify_history
from harpoon_quant.remediation import economic_checks, trade_contributions

ROOT = Path(__file__).resolve().parents[2]


def account(stress=False, dividend=20, second_pnl=-5):
    """A dividend-dominated winner with a later payment and another campaign."""
    initial = 20000
    fee = 2 if stress else 1
    events = []

    def emit(kind, at, **kw):
        events.append(dict(kind=kind, at=at, **kw))

    emit("FIXED", "2025-01-01T00:00Z", cash_delta=-fee)
    emit("BUY", "2025-01-01T12:00Z", symbol="A", cash_delta=-100)
    emit("BUY", "2025-01-01T12:00Z", symbol="B", cash_delta=-100)
    emit("FIXED", "2025-01-02T00:00Z", cash_delta=-fee)
    if dividend:
        emit("DIV_EX", "2025-01-02T01:00Z", receipt="D", symbol="A", amount=dividend)
    emit("SELL", "2025-01-02T12:00Z", symbol="A", cash_delta=101)
    emit("SELL", "2025-01-02T12:00Z", symbol="B", cash_delta=100 + second_pnl)
    if dividend:
        emit("DIV_PAY", "2025-01-02T13:00Z", receipt="D", cash_delta=dividend)
    terminal = initial - 2 * fee + dividend + 1 + second_pnl
    trades = [
        dict(
            symbol=s,
            book="equity",
            entry_at="2025-01-01T12:00Z",
            exit_at="2025-01-02T12:00Z",
            net_usd=pnl,
            holding_hours=24,
        )
        for s, pnl in (("A", 1), ("B", second_pnl))
    ]
    return dict(
        initial_usd=initial,
        terminal_usd=terminal,
        net_usd=terminal - initial,
        stress=stress,
        events=events,
        trades=trades,
        fixed_cost_usd=2 * fee,
        dividend_entitlement_usd=dividend,
        hour_grid_drawdown=0.001,
        max_entry_gross_fraction=0.01,
        max_entry_stop_risk_fraction=0.001,
        curve=[
            dict(day="2025-01-01", equity=initial - fee),
            dict(day="2025-01-02", equity=terminal),
        ],
    )


class QualificationTests(unittest.TestCase):
    def test_remove_dividend_entitlement_even_after_sale_payment(self):
        a = account()
        result = economic_checks(a)
        self.assertEqual(result["largest_trade_economic_contribution_usd"], 21)
        self.assertEqual(result["net_less_largest_trade"], -7)
        self.assertFalse(result["checks"]["positive_without_largest_trade"])
        self.assertEqual(sum(r["total_net_usd"] for r in trade_contributions(a)), 16)

    def test_dividend_changes_largest_winner_identity(self):
        result = economic_checks(account(second_pnl=15))
        self.assertEqual(result["largest_trade_economic_contribution_usd"], 21)
        self.assertEqual(result["net_less_largest_trade"], 13)

    def test_legacy_dividend_needs_verified_symbol_map(self):
        a = account()
        event = next(e for e in a["events"] if e["kind"] == "DIV_EX")
        del event["symbol"]
        with self.assertRaisesRegex(ValueError, "DIVIDEND_ATTRIBUTION"):
            economic_checks(a)
        self.assertEqual(
            economic_checks(a, dividend_symbols={"D": "A"})["attributed_dividends_usd"],
            20,
        )

    def test_conflicting_or_duplicate_dividend_fails(self):
        a = account()
        with self.assertRaisesRegex(ValueError, "DIVIDEND_ATTRIBUTION"):
            economic_checks(a, dividend_symbols={"D": "B"})
        a["events"].insert(5, copy.deepcopy(a["events"][4]))
        with self.assertRaisesRegex(ValueError, "DIVIDEND_ATTRIBUTION"):
            economic_checks(a)

    def test_trade_pnl_and_terminal_cannot_be_forged(self):
        for field in ("trade", "terminal", "dividend"):
            a = account()
            if field == "trade":
                a["trades"][0]["net_usd"] += 1
            elif field == "terminal":
                a["terminal_usd"] += 1
            else:
                a["dividend_entitlement_usd"] += 1
            with self.subTest(field=field), self.assertRaises(ValueError):
                trade_contributions(a)

    def test_payment_is_not_double_counted(self):
        a = account()
        a["events"] = [e for e in a["events"] if e["kind"] != "DIV_PAY"]
        self.assertEqual(economic_checks(a)["attributed_dividends_usd"], 20)

    @staticmethod
    def scenarios():
        return {
            s: {
                b: account(stress=s == "STRESS", dividend=0, second_pnl=2)
                for b in ("JOINT", "EQUITY_ETF", "CRYPTO", "CASH")
            }
            for s in ("NOMINAL", "STRESS")
        }

    def test_positive_backtest_flags_never_authenticate_itself(self):
        scenarios = self.scenarios()
        for books in scenarios.values():
            for a in books.values():
                a.update(
                    level8_accredited=True, fresh_holdout=True, origin="OBSERVED_LIVE"
                )
        result = qualify_history(scenarios)
        self.assertFalse(result["level8_accredited"])
        self.assertFalse(result["execution_allowed"])
        self.assertEqual(result["gate_counts"], {"FAIL": 3, "BLOCKED": 5})

    def test_actual_hold_duration_is_recomputed(self):
        scenarios = self.scenarios()
        scenarios["NOMINAL"]["JOINT"]["trades"][0]["holding_hours"] = 1
        with self.assertRaisesRegex(ValueError, "FALSE_HOLDING_DURATION"):
            qualify_history(scenarios)

    def test_grid_drawdown_cannot_hide_daily_loss(self):
        scenarios = self.scenarios()
        scenarios["NOMINAL"]["JOINT"]["hour_grid_drawdown"] = 0
        with self.assertRaisesRegex(ValueError, "DRAWDOWN_BELOW"):
            qualify_history(scenarios)

    def test_cost_scenario_cannot_be_relabeled(self):
        scenarios = self.scenarios()
        scenarios["STRESS"] = scenarios["NOMINAL"]
        with self.assertRaisesRegex(ValueError, "SCENARIO_IDENTITY"):
            qualify_history(scenarios)

    def test_cli_rejects_existing_evidence_with_nonzero_promotion_exit(self):
        env = {**os.environ, "PYTHONPATH": "quant:tools", "OPENBLAS_NUM_THREADS": "1"}
        command = [
            sys.executable,
            "-B",
            "tools/review_compound_evidence.py",
            "evidence/compound_swing",
            "--require-level8",
        ]
        result = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True, env=env, timeout=60
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        review = json.loads(result.stdout)
        self.assertTrue(review["ledger_verified"])
        self.assertEqual(review["qualification"]["decision"], "REJECT")
        self.assertEqual(
            review["qualification"]["gate_counts"], {"FAIL": 3, "BLOCKED": 5}
        )
        self.assertFalse(review["level8_accredited"])
        nominal = review["accounts"]["NOMINAL"]
        self.assertAlmostEqual(nominal["net_usd"], -250.68871465029224, places=6)

    def test_changed_account_bytes_are_rejected_before_analysis(self):
        directory = ROOT / "evidence/compound_swing"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "report.json").write_bytes((directory / "report.json").read_bytes())
            for p in directory.glob("*.json.gz"):
                a = json.loads(gzip.decompress(p.read_bytes()))
                a["unexpected_added_field"] = True
                (out / p.name).write_bytes(gzip.compress(json.dumps(a).encode()))
            result = subprocess.run(
                [sys.executable, "-B", "tools/review_compound_evidence.py", str(out)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONPATH": "quant:tools"},
                timeout=30,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CHANGED_ACCOUNT", result.stderr)
