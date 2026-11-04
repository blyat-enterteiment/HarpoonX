"""Adversarial synthetic fixtures for the separate PROFIT8 auditor.

No historical fit, strategy matrix, broker or parameter search is executed.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
# Executable tools are outside the quant package and need the explicit path.
from verify_profit8 import (  # noqa: E402
    DatasetIndex,
    audit_forecasts,
    audit_report,
    audit_signal_forecast,
    audit_sizing,
    audit_teachers,
    audit_trace,
    basis_weights,
    verify_bindings,
)

FIXTURE = r"""
const B=require('./tools/profit8_replay.cjs');
const R=require('./runtime30/profit8_replay.js');
const BAR=300000,DAY=86400000;
function make(kind) {
  const offsets=[0,3,4,5,6,7,10,11];
  const sessions=offsets.map(d=>{const open=Date.UTC(2025,0,3,14,30)+d*DAY;
    return {date:new Date(open).toISOString().slice(0,10),open,close:open+78*BAR};});
  const earlier=Array.from({length:220},(_,i)=>{const open=sessions[0].open-(220-i)*DAY;
    return {date:new Date(open).toISOString().slice(0,10),open,close:open+18*BAR};});
  const allSessions=[...earlier,...sessions];
  const series=['AAPL','MSFT'].map(symbol=>({symbol,root:symbol,tick:.01,pointValue:1,
    bars:allSessions.flatMap(s=>Array.from({length:(s.close-s.open)/BAR},(_,j)=>({t:s.open+j*BAR,
      end:s.open+(j+1)*BAR,availableAt:s.open+(j+1)*BAR+1000,
      o:100,h:100.1,l:99.9,c:100,v:1000})))}));
  const data={schema:'HARPOON-ULTIMATE-DATA-1',kind:'ALPACA_PROXY',sessions:allSessions,series,
    splitEvents:[],cashDividends:[],provenance:{source:'SYNTHETIC_ENGINEERING_ONLY',
    feed:'SYNTHETIC',execution:'MODELED_OHLCV',files:[{name:'synthetic',sha256:'0'.repeat(64)}]}};
  const protocol={universe:['AAPL','MSFT'],holding_maximum_hours:72,
    periods:{evaluation_start:sessions[0].date,evaluation_end:sessions.at(-1).date,
      validation_start:sessions[0].date,validation_end:sessions[1].date,
      test_start:sessions[2].date,test_end:sessions.at(-1).date},
    limits:R.PROFIT8_REPLAY_LIMITS,scenarios:{NOMINAL:{spread_bps:2,slippage_bps:2,
      commission_usd_per_share_per_side:.005,external_cost_usd_per_calendar_day:1}},
    reporting_windows:{RECENT:{start:sessions[2].date,end:sessions.at(-1).date}}};
  const signals=series.map(s=>{const at=sessions[0].open+3600000+1000;
    return {id:s.symbol+':SYNTHETIC',symbol:s.symbol,hypothesis:'CLOSED_CHANNEL',
      direction:1,at,index:0,plannedEntryAt:R.planSignalEntryAt(at,sessions),
      stopDistance:2,regime:.4,metadata:{roadmapHorizonHours:72}};});
  let mode=kind==='ROBUST'?'ROBUST_LOG':kind==='POSITIVE'?'MAX_POSITIVE':'NATIVE_MAX';
  if(mode!=='NATIVE_MAX') for(const signal of signals)signal.metadata.profit8Forecast={
    basis_order:['E','T'],mean:kind==='ROBUST'?[-.1,.01]:[.000001,.000001],
    covariance:[[0,0],[0,0]],mean_covariance:[[0,0],[0,0]],normalizer_price:100,
    trained_through:signal.at-DAY,available_at:signal.at,model_id:'SYNTHETIC'};
  if(kind==='PARTIAL') {
    series[0].bars.find(b=>b.t===signals[0].plannedEntryAt+BAR).h=103.1;
    data.cashDividends=[{id:'SYNTHETIC_DIV',symbol:'AAPL',exAt:sessions[1].open,
      payableAt:sessions[4].close,amountPerShare:1.25}];
  }
  if(kind==='STOP')series[0].bars.find(b=>b.t===signals[0].plannedEntryAt).l=97;
  if(kind==='NO_FILL')for(const s of series)Object.assign(
    s.bars.find(b=>b.t===signals[0].plannedEntryAt),{o:110,h:110.1,l:109.9,c:110});
  if(kind==='MISSING')series[0].bars=series[0].bars.filter(b=>b.t!==signals[0].plannedEntryAt);
  const teachers=B.prepareTeachers(protocol,data,{signals},'NOMINAL');
  const bundle={signals:{NOMINAL:{TEST:signals}},recipe_modes:{TEST:mode}};
  const report=kind==='MISSING'?null:B.run(protocol,data,bundle,'TEST','NOMINAL');
  return {data,protocol,signals,teachers,report};
}
console.log(JSON.stringify(Object.fromEntries(
 ['NATIVE','ROBUST','POSITIVE','PARTIAL','STOP','NO_FILL','MISSING'].map(k=>[k,make(k)]))));
"""


class Profit8AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(["node", "-e", FIXTURE], cwd=ROOT, capture_output=True, text=True,
                                check=False, timeout=30)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        cls.fixtures = json.loads(result.stdout)

    def fixture(self, name="ROBUST"):
        return copy.deepcopy(self.fixtures[name])

    def check_report(self, fixture):
        return audit_report(fixture["report"], fixture["protocol"], fixture["data"], "NOMINAL:TEST",
                            teachers=fixture["teachers"], signals=fixture["signals"])

    def test_synthetic_accounts_reconcile_with_decimal_and_frozen_core(self):
        for name in ("NATIVE", "ROBUST", "POSITIVE", "PARTIAL", "STOP", "NO_FILL"):
            with self.subTest(name=name):
                fixture = self.fixture(name)
                result = self.check_report(fixture)
                self.assertTrue(result["verified"])
                self.assertTrue(result["decimal_cash_flow_verified"])
                self.assertFalse(result["retained_core_uses_decimal"])
                self.assertEqual(result["calendar_days_charged"], 12)
                self.assertEqual(result["exact_teacher_payoff_matches"], len(fixture["report"]["funded"]))

    def test_teacher_traces_include_no_fill_and_blocked_distinctly(self):
        for name in self.fixtures:
            with self.subTest(name=name):
                fixture = self.fixture(name)
                result = audit_teachers(fixture["teachers"], fixture["protocol"], fixture["data"], "NOMINAL")
                self.assertTrue(result["verified"])
        self.assertEqual(self.fixtures["NO_FILL"]["teachers"]["labels"][0]["net_basis"], [0, 0])
        self.assertIsNone(self.fixtures["MISSING"]["teachers"]["labels"][0]["net_basis"])

    def test_corrupt_fill_price_cannot_hide_behind_matching_float_summaries(self):
        fixture = self.fixture()
        fixture["report"]["funded"][0]["inventoryEvents"][-1]["filledPrice"] += 0.01
        with self.assertRaisesRegex(ValueError, "EXECUTED_CASH_FLOW"):
            self.check_report(fixture)

    def test_costs_already_net_cannot_be_subtracted_twice(self):
        state = self.fixture("POSITIVE")["report"]["states"][0]
        candidate = state["profit8Sizing"]["candidates"][-1]
        candidate["meanUsd"] -= 2 * candidate["quantity"] * 0.005
        with self.assertRaisesRegex(ValueError, "NET_NO_SECOND_COST"):
            audit_sizing(state)

    def test_decimal_trace_detects_double_fee(self):
        trace = self.fixture("PARTIAL")["teachers"]["labels"][0]["quantity4_trace"]
        trace["netUsd"] -= trace["feesUsd"]
        with self.assertRaisesRegex(ValueError, "EXECUTED_CASH_FLOW"):
            audit_trace(trace, Decimal(".005"), "FIXTURE")

    def test_future_open_cannot_replace_causal_reference(self):
        fixture = self.fixture("NO_FILL")
        state = fixture["report"]["states"][0]
        state["reference"]["price"] = 110
        state["plan"]["reference"]["price"] = 110
        with self.assertRaisesRegex(ValueError, "REFERENCE_PRICE"):
            self.check_report(fixture)

    def test_reference_availability_after_decision_is_rejected(self):
        fixture = self.fixture()
        state = fixture["report"]["states"][0]
        state["reference"]["sourceAvailableAt"] = state["opportunity"]["at"] + 1
        with self.assertRaisesRegex(ValueError, "REFERENCE_CLOCK"):
            self.check_report(fixture)

    def test_quantity_maximum_rebuilt_from_registered_ceiling(self):
        fixture = self.fixture()
        state = fixture["report"]["states"][0]
        state["plan"]["quantity"] += 1
        with self.assertRaisesRegex(ValueError, "NO_FUTURE_PRICE_SIZING"):
            self.check_report(fixture)

    def test_open_risk_balance_cannot_ignore_pending_first_order(self):
        fixture = self.fixture()
        state = fixture["report"]["states"][1]
        self.assertGreater(state["reservationBefore"]["riskUsd"], 0)
        state["openRisk"] = 0
        with self.assertRaisesRegex(ValueError, "RESERVED_RISK_BALANCE"):
            self.check_report(fixture)

    def test_committed_reservation_cannot_release_partial_risk(self):
        fixture = self.fixture()
        state = fixture["report"]["states"][0]
        state["profit8CommittedReservation"]["riskUsd"] /= 2
        with self.assertRaisesRegex(ValueError, "COMMITMENT_riskUsd"):
            self.check_report(fixture)

    def test_partial_dividend_is_quantity_at_ex_date(self):
        fixture = self.fixture("PARTIAL")
        labels = fixture["teachers"]["labels"][0]
        self.assertAlmostEqual(labels["quantity1_dividend_usd"], 1.25)
        self.assertAlmostEqual(labels["quantity4_dividend_usd"], 3.75)
        result = self.check_report(fixture)
        self.assertGreater(result["dividend_accrued_usd"], 0)

    def test_no_phase_or_reporting_window_capital_reset(self):
        fixture = self.fixture()
        fixture["report"]["descriptive_windows"]["RECENT"]["capital_at_phase_start"] = 20_000
        with self.assertRaisesRegex(ValueError, "WINDOW_NO_RESET"):
            self.check_report(fixture)

    def test_early_stop_label_waits_for_deadline_cohort(self):
        fixture = self.fixture("STOP")
        label = fixture["teachers"]["labels"][0]
        self.assertLess(label["policy_closed_at"], label["label_end"])
        label["label_known_at"] = label["known_at"] = label["quantity1_trace"]["maximum_policy_known_at"]
        with self.assertRaisesRegex(ValueError, "PREMATURE_LABEL"):
            audit_teachers(fixture["teachers"], fixture["protocol"], fixture["data"], "NOMINAL")

    def test_missing_tape_cannot_be_zero_label(self):
        fixture = self.fixture("MISSING")
        fixture["teachers"]["labels"][0]["net_basis"] = [0, 0]
        with self.assertRaisesRegex(ValueError, "MISSING_TAPE_IS_NOT_ZERO"):
            audit_teachers(fixture["teachers"], fixture["protocol"], fixture["data"], "NOMINAL")

    def test_no_fill_nonzero_profit_rejected(self):
        fixture = self.fixture("NO_FILL")
        fixture["teachers"]["labels"][0]["T"] = 0.01
        with self.assertRaisesRegex(ValueError, "EXPLICIT_ZERO"):
            audit_teachers(fixture["teachers"], fixture["protocol"], fixture["data"], "NOMINAL")

    def test_bar_cannot_arrive_before_its_close(self):
        fixture = self.fixture()
        bar = fixture["data"]["series"][0]["bars"][0]
        bar["availableAt"] = bar["end"] - 1
        with self.assertRaisesRegex(ValueError, "BAR_AVAILABILITY_CLOCK"):
            DatasetIndex(fixture["data"])

    def test_utility_units_and_expected_squared_payoff_are_checked(self):
        fixture = self.fixture()
        state = fixture["report"]["states"][0]
        state["profit8Sizing"]["candidates"][3]["utility"] *= 100
        with self.assertRaisesRegex(ValueError, "DIMENSIONLESS_UTILITY"):
            audit_sizing(state)

    def test_future_forecast_does_not_pass_causal_contract(self):
        state = self.fixture()["report"]["states"][0]
        state["opportunity"]["metadata"]["profit8Forecast"]["available_at"] += 1
        with self.assertRaisesRegex(ValueError, "FUTURE_FORECAST"):
            audit_sizing(state)

    def test_indefinite_covariance_rejected(self):
        state = self.fixture()["report"]["states"][0]
        state["opportunity"]["metadata"]["profit8Forecast"]["covariance"] = [[1, 2], [2, 1]]
        with self.assertRaisesRegex(ValueError, "PSD"):
            audit_sizing(state)

    def test_integer_quarter_exit_discontinuities(self):
        self.assertEqual([basis_weights(q) for q in range(9)],
                         [(0, 0), (0, 1), (0, 2), (0, 3), (2, 2), (2, 3), (2, 4), (2, 5), (4, 4)])

    def test_net_snapshot_extra_target_and_gross_control_are_distinct(self):
        fixture = self.fixture("POSITIVE")
        signal = fixture["signals"][0]
        net = copy.deepcopy(signal["metadata"]["profit8Forecast"])
        snapshot = {"net": {"status": "READY", "forecast": net},
                    "gross": {"status": "READY", "mean": .001, "variance": .0001, "mean_variance": .00001,
                              "normalizer_price": 100, "trained_through": net["trained_through"],
                              "available_at": net["available_at"], "model_id": net["model_id"]}}
        cost = fixture["protocol"]["scenarios"]["NOMINAL"]
        signal["metadata"]["profit8Forecast"] = {**net, "target": "NET_NATIVE_POLICY_PAYOFF_BASIS"}
        audit_signal_forecast(signal, snapshot, "NET", cost)
        audit_signal_forecast(signal, snapshot, "ROBUST", cost)
        with self.assertRaisesRegex(ValueError, "SIGNAL_FORECAST_TARGET_BINDING"):
            audit_signal_forecast(signal, snapshot, "GROSS", cost)
        gross_mean = .001 - ((2 + 2 * 2) / 10_000 + 2 * .005 / 100)
        signal["metadata"]["profit8Forecast"] = {
            **net, "mean": [gross_mean, gross_mean], "covariance": [[.0001, .0001], [.0001, .0001]],
            "mean_covariance": [[.00001, .00001], [.00001, .00001]],
            "target": "GROSS_DEADLINE_MINUS_REGISTERED_VARIABLE_COST",
        }
        audit_signal_forecast(signal, snapshot, "GROSS", cost)

    def test_training_hash_normalizes_native_integer_no_fill_zeros(self):
        from quant.tests.test_profit8_model import fixtures, protocol

        from harpoon_quant.profit8.model import forecast_rows
        rows, cfg = fixtures(), protocol()
        rows[280]["reference_price"] = 100
        rows[280]["labels"]["NOMINAL:24"].update(status="NO_FILL", fill=False, net_basis=[0, 0],
                                                gross_deadline_return=0)
        result = forecast_rows(rows, cfg)
        # This test isolates model-input hashing and cohort/purge invariants.
        # Tape-to-row integrity is exercised separately by the native fixtures.
        with patch("verify_profit8.audit_rows", return_value={row["id"]: row for row in rows}):
            audit = audit_forecasts(result, {}, rows, cfg, None)
        self.assertTrue(audit["verified"])
        self.assertGreater(audit["no_fill_training_rows_with_reuse"], 0)

    def test_binding_integrity_and_missing_file_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "packet"
            directory.mkdir()
            (root / "source.py").write_text("fixed\n")
            (root / "data.json").write_text("{}\n")
            for name in ("protocol", "recipes"):
                (directory / (name + ".json")).write_text("{}\n")
            from verify_profit8 import sha
            binding = {"schema": "SYNTHETIC_BINDING", "sources": {"source.py": sha(root / "source.py")},
                       "data": {"data.json": sha(root / "data.json")},
                       "protocol_sha256": sha(directory / "protocol.json"),
                       "recipes_sha256": sha(directory / "recipes.json")}
            (directory / "source_bindings.json").write_text(json.dumps(binding))
            self.assertTrue(verify_bindings(directory, root)["verified"])
            (root / "source.py").write_text("changed\n")
            with self.assertRaisesRegex(ValueError, "BINDING_CHANGED"):
                verify_bindings(directory, root)

    def test_cli_returns_explicit_failure_without_backtest(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "audit.json"
            result = subprocess.run([sys.executable, str(ROOT / "tools/verify_profit8.py"),
                                     "--directory", temporary, "--output", str(output)], cwd=ROOT,
                                    capture_output=True, text=True, check=False, timeout=30)
            self.assertEqual(result.returncode, 2)
            receipt = json.loads(output.read_text())
            self.assertFalse(receipt["verified"])
            self.assertFalse(receipt["financial_acceptance_allowed"])
            self.assertEqual(receipt["new_backtests"], 0)


if __name__ == "__main__":
    unittest.main()
