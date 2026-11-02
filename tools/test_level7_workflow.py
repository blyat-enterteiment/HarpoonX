"""Adversarial orchestration tests. Mocked economics are not market evidence."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

TOOL = Path(__file__).with_name("level7_workflow.py")
SPEC = importlib.util.spec_from_file_location("level7_workflow_under_test", TOOL)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.request = {"schema": module.SCHEMA, "target": 7, "panel_request": None,
                        "economic_protocol": None, "economic_evidence": None,
                        "forward_attribution_request": None}

    def save(self, name, obj):
        raw = json.dumps(obj).encode()
        (self.root / name).write_bytes(raw)
        return {"path": name, "sha256": hashlib.sha256(raw).hexdigest()}

    def test_missing_resources_are_separate_nulls_not_zero_profit_or_score(self):
        out = module.evaluate(self.request, self.root)
        self.assertEqual(out["dictamen"], "VENTAJA_NO_DEMOSTRADA")
        self.assertIsNone(out["economic_score"])
        self.assertIsNone(out["observed_portfolio"])
        self.assertFalse(out["level7_criterion_met"])
        self.assertEqual(out["research_trials_created"], 0)
        self.assertGreaterEqual(len(out["next_actions"]), 5)

    def test_caller_cannot_supply_pass_or_curve(self):
        for name in ("score", "observed_portfolio", "level7_criterion_met", "economic_report"):
            with self.assertRaisesRegex(ValueError, "UNKNOWN_REQUEST_FIELD"):
                module.evaluate({**self.request, name: 7}, self.root)

    def test_changed_file_is_rejected_before_evaluation(self):
        ref = self.save("source.json", {"cost": 5})
        (self.root / "source.json").write_text('{"cost":0}')
        with self.assertRaisesRegex(ValueError, "SOURCE_HASH_MISMATCH"):
            module.load_ref(ref, self.root, [])

    def test_duplicate_keys_are_not_overwritten(self):
        raw = b'{"cost":5,"cost":0}'
        (self.root / "source.json").write_bytes(raw)
        with self.assertRaises(ValueError):
            module.load_ref({"path": "source.json", "sha256": hashlib.sha256(raw).hexdigest()}, self.root, [])

    def test_historical_pass_alone_is_never_seven(self):
        self.request["economic_protocol"] = self.save("protocol.json", {"schema": "HARPOON_ECONOMIC_PROTOCOL_2"})
        self.request["economic_evidence"] = self.save("evidence.json", {"generated_at": "2026-01-01T00:00:00Z"})
        gate = {"level5_criterion_met": True, "dictamen": "CANDIDATO_PARA_VALIDACION_FORWARD"}
        with patch("harpoon_quant.economic_gate_v2.evaluate", return_value=gate) as fixed_gate:
            out = module.evaluate(self.request, self.root)
        fixed_gate.assert_called_once()
        self.assertFalse(out["level7_criterion_met"])
        self.assertIsNone(out["economic_score"])
        self.assertIn("FORWARD_SPEC_MISSING", out["blockers"])
        self.assertIn("FORWARD_ATTRIBUTION_REQUEST_MISSING", out["blockers"])

    def test_historical_rejection_is_not_relabelled_inconclusive(self):
        self.request["economic_protocol"] = self.save("protocol.json", {"schema": "HARPOON_ECONOMIC_PROTOCOL_2"})
        self.request["economic_evidence"] = self.save("evidence.json", {"generated_at": "2026-01-01T00:00:00Z"})
        with patch("harpoon_quant.economic_gate_v2.evaluate", return_value={"level5_criterion_met": False, "dictamen": "RECHAZADO"}):
            out = module.evaluate(self.request, self.root)
        self.assertEqual(out["dictamen"], "RECHAZADO")
        self.assertIsNone(out["economic_score"])

    def test_future_receipt_is_not_evaluated(self):
        self.request["economic_protocol"] = self.save("protocol.json", {"schema": "HARPOON_ECONOMIC_PROTOCOL_2"})
        self.request["economic_evidence"] = self.save("evidence.json", {"generated_at": "2100-01-01T00:00:00Z"})
        with patch("harpoon_quant.economic_gate_v2.evaluate") as evaluator:
            out = module.evaluate(self.request, self.root)
        evaluator.assert_not_called()
        self.assertTrue(any("EVIDENCE_GENERATION_IN_FUTURE" in b for b in out["blockers"]))

    def test_missing_panel_status_is_not_a_success(self):
        self.request["panel_request"] = self.save("panel.json", {})
        with patch("harpoon_quant.causal_panel.build", return_value={"panel": {"origin": "OBSERVED"},
                    "readiness": {"accepted_rows": 1000}, "artifact_hash": "a" * 64}):
            out = module.evaluate(self.request, self.root)
        self.assertIn("CAUSAL_PANEL_NOT_READY", out["blockers"])

    def test_recomputed_missing_input_report_is_deterministic(self):
        self.assertEqual(module.evaluate(self.request, self.root), module.evaluate(self.request, self.root))

    def mocked_forward(self, *, exact=True, fills=2, attributed=True, nature="REAL", timestamp="first", fill_at=500):
        """MOCKS test conjunction logic only; no assertion of a real account."""
        panel = {"panel": {"origin": "OBSERVED"}, "readiness": {"accepted_rows": 100,
                 "status": "PANEL_ADMISSIBLE_NOT_FINANCIALLY_VALIDATED"}, "artifact_hash": "panel"}
        p = {"schema": "HARPOON_ECONOMIC_PROTOCOL_2", "forward_validation": {
            "minimum_economic_pnl_usd": 0, "minimum_mean_log_growth": 0},
             "max_drawdown_fraction": .08, "max_gross_exposure_fraction": .5, "horizon_hours": 72,
             "period": {"test_start": 0, "test_end": 1000}}
        gate = {"level5_criterion_met": True, "dictamen": "CANDIDATO_PARA_VALIDACION_FORWARD",
                "derivation": {"readiness": {"components": {"data": {"artifact_hash": "panel"}}}}}
        forward = {"verified": attributed, "ledger": {"verified": True}, "executionNature": nature,
                   "generated_at": timestamp, "attributed_fill_count": fills,
                   "attributions": [{"at": fill_at} for _ in range(fills)],
                   "risk": {"maximum_observed_holding_hours": 24}}
        summary = {"economic_pnl_usd": 10, "net_external_flows_usd": 0, "external_flow_event_count": 0,
                   "requested_period_boundaries_exact": exact, "insolvency": False,
                   "economic_drawdown_fraction_observed": .01, "maximum_gross_exposure_fraction_observed": .2,
                   "log_returns": [.001, -.0002, .002]}
        stats = {"status": "COMPUTED", "point_mean_log_growth": .001,
                 "blocks": [{"lower_one_sided_mean_log_growth": .0001}]}
        request = {**self.request, "panel_request": self.save("panel.json", {}),
                   "economic_protocol": self.save("protocol.json", p),
                   "economic_evidence": self.save("evidence.json", {"generated_at": "2026-01-01T00:00:00Z"}),
                   "forward_attribution_request": self.save("forward.json", {"expected": None})}
        with ExitStack() as stack:
            stack.enter_context(patch("harpoon_quant.causal_panel.build", return_value=panel))
            stack.enter_context(patch("harpoon_quant.economic_gate_v2.evaluate", return_value=gate))
            stack.enter_context(patch.object(module, "validate_forward_spec", return_value={}))
            stack.enter_context(patch.object(module, "node_attribution", return_value=forward))
            stack.enter_context(patch.object(module, "summarize_observed_portfolio", return_value=summary))
            stack.enter_context(patch.object(module, "bootstrap_forward_growth", return_value=stats))
            return module.evaluate(request, self.root)

    def test_mocked_complete_conjunction_is_seven_without_order_authority(self):
        out = self.mocked_forward()
        self.assertTrue(out["level7_criterion_met"])
        self.assertEqual(out["economic_score"], 7)
        self.assertFalse(out["execution_allowed"])
        self.assertFalse(out["deployment_allowed"])
        self.assertFalse(out["financial_approval"])

    def test_shifted_boundary_profit_cannot_certify_requested_period(self):
        out = self.mocked_forward(exact=False)
        self.assertFalse(out["level7_criterion_met"])
        self.assertIsNone(out["economic_score"])
        self.assertIn("FORWARD_BOUNDARY_ECONOMIC_BRIDGE_REQUIRED", out["blockers"])

    def test_no_trades_does_not_demonstrate_trading_profit(self):
        out = self.mocked_forward(fills=0)
        self.assertFalse(out["level7_criterion_met"])
        self.assertIn("FORWARD_TRADING_ACTIVITY_NOT_DEMONSTRATED", out["blockers"])

    def test_only_late_fills_do_not_create_activity_in_profitable_period(self):
        out = self.mocked_forward(fill_at=1001)
        self.assertFalse(out["level7_criterion_met"])
        self.assertEqual(out["forward_attribution"]["evaluated_period_attributed_fill_count"], 0)
        self.assertIn("FORWARD_TRADING_ACTIVITY_NOT_DEMONSTRATED", out["blockers"])

    def test_profitable_unattributed_account_is_not_seven(self):
        out = self.mocked_forward(attributed=False)
        self.assertFalse(out["level7_criterion_met"])
        self.assertIn("FORWARD_ATTRIBUTION_NOT_VERIFIED", out["blockers"])

    def test_paper_profit_does_not_become_real_profit(self):
        out = self.mocked_forward(nature="PAPER")
        self.assertFalse(out["level7_criterion_met"])
        self.assertIn("REAL_FORWARD_EXECUTION_REQUIRED", out["blockers"])

    def test_verifier_wall_clock_is_not_part_of_reproducible_economic_result(self):
        a = self.mocked_forward(timestamp="first")
        b = self.mocked_forward(timestamp="second")
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
