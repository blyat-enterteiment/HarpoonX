from __future__ import annotations

import copy
import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from examples.economic_gate.make_fixture import make_fixture, write_json
from harpoon_quant.core import digest
from harpoon_quant.economic_gate import (
    artifact_reference,
    evaluate_gate,
    paired_block_bootstrap,
    register_protocol,
    seal_protocol,
    verify_gate_report,
)


class EconomicGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.protocol, self.evidence = make_fixture(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def evaluate(self) -> dict:
        return evaluate_gate(self.protocol, self.evidence, artifact_root=self.root)

    def assert_blocked(self, reason: str) -> dict:
        result = self.evaluate()
        self.assertEqual(result["software_validators"]["status"], "BLOCKED")
        self.assertIn(reason, str(result["software_validators"]["errors"]))
        self.assertFalse(result["execution_allowed"])
        self.assertFalse(result["liveApproved"])
        return result

    def refresh_protocol(self) -> None:
        self.protocol = seal_protocol(self.protocol)
        self.evidence["protocol_hash"] = self.protocol["protocol_hash"]
        journal = self.root / "preregistration.jsonl"
        journal.unlink()
        entry = register_protocol(self.protocol, journal, "2029-12-15T00:00:00+00:00")
        self.evidence["preregistration"] = {"journal": artifact_reference(journal, self.root), "record_hash": entry["record_hash"]}

    def change_last_return(self, value: float) -> None:
        item = self.evidence["policies"]["SVR"]
        row = item["curve"][-1]
        row["equity_end_usd"] = row["equity_start_usd"] * (1 + value)
        row["gross_marked_pnl_usd"] = row["equity_end_usd"] - row["equity_start_usd"] + row["fees_in_equity_usd"] + row["operating_costs_in_equity_usd"]
        row["return_net"] = value
        item["terminal"]["cash_usd"] = row["equity_end_usd"]

    def test_synthetic_success_never_promotes_financially(self) -> None:
        result = self.evaluate()
        self.assertEqual(result["software_validators"]["status"], "PASS")
        self.assertTrue(result["statistical_gate_passed"])
        self.assertEqual(result["dictamen"], "VENTAJA_NO_DEMOSTRADA")
        self.assertFalse(result["candidate_for_forward_validation"])
        self.assertFalse(result["financial_approval"])
        self.assertIn("SYNTHETIC_IS_NOT_FINANCIAL_EVIDENCE", result["financial_blockers"])
        self.assertIn("PREDICTOR_PARITY_NOT_VERIFIED", result["financial_blockers"])
        self.assertIn("PARITY_RECEIPT_NOT_FINANCIALLY_ELIGIBLE", result["financial_blockers"])

    def test_report_verifier_recomputes_and_never_authorizes_execution(self) -> None:
        result = self.evaluate()
        verified = verify_gate_report(result, self.protocol, self.evidence, artifact_root=self.root)
        self.assertTrue(verified["recomputed_identically"])
        self.assertTrue(verified["report_integrity_verified"])
        self.assertFalse(verified["execution_allowed"])
        result["liveApproved"] = True
        verified = verify_gate_report(result, self.protocol, self.evidence, artifact_root=self.root)
        self.assertFalse(verified["recomputed_identically"])
        self.assertFalse(verified["report_integrity_verified"])
        self.assertFalse(verified["liveApproved"])

    def test_rehashing_a_forged_candidate_does_not_pass_reexecution(self) -> None:
        result = self.evaluate()
        result["dictamen"] = "CANDIDATO_PARA_VALIDACION_FORWARD"
        result["candidate_for_forward_validation"] = True
        result["financial_blockers"] = []
        result["artifact_hash"] = digest({key: value for key, value in result.items() if key != "artifact_hash"})
        verified = verify_gate_report(result, self.protocol, self.evidence, artifact_root=self.root)
        self.assertTrue(verified["report_integrity_verified"])
        self.assertFalse(verified["recomputed_identically"])
        self.assertEqual(verified["dictamen"], "VENTAJA_NO_DEMOSTRADA")

    def test_protocol_tampering_is_detected(self) -> None:
        self.protocol["minimum_delta_ridge_log_growth"] /= 10
        self.assert_blocked("PROTOCOL_HASH_MISMATCH")

    def test_modified_registry_file_hash_is_detected(self) -> None:
        with (self.root / "preregistration.jsonl").open("a") as stream:
            stream.write("\n")
        self.assert_blocked("ARTIFACT_HASH_MISMATCH")

    def test_registry_chain_is_checked_even_with_updated_file_hash(self) -> None:
        path = self.root / "preregistration.jsonl"
        entry = json.loads(path.read_text())
        entry["previous_hash"] = "FORGED"
        path.write_text(json.dumps(entry) + "\n")
        self.evidence["preregistration"]["journal"] = artifact_reference(path, self.root)
        self.assert_blocked("PREREGISTRY_CHAIN")

    def test_backdated_protocol_after_observation_is_blocked(self) -> None:
        self.evidence["provenance"]["first_final_data_access_at"] = "2029-12-10T00:00:00+00:00"
        self.assert_blocked("PROTOCOL_AFTER_OBSERVATIONS")

    def test_real_clock_cannot_be_overridden_through_registration_api(self) -> None:
        protocol = dict(self.protocol, data_scope="HISTORICAL")
        with self.assertRaisesRegex(ValueError, "CLOCK_OVERRIDE_ONLY_SYNTHETIC"):
            register_protocol(seal_protocol(protocol), self.root / "real_registry.jsonl", "2029-12-15T00:00:00+00:00")

    def test_previously_consumed_final_period_is_blocked(self) -> None:
        self.evidence["provenance"]["prior_final_test_uses"] = ["tuned_after_inspection"]
        self.assert_blocked("FINAL_TEST_ALREADY_CONSUMED")

    def test_search_count_cannot_reset_below_historical_23(self) -> None:
        self.protocol["search"]["total_attempts"] = 1
        self.protocol = seal_protocol(self.protocol)
        self.assert_blocked("INVALID_SEARCH_ATTEMPTS")

    def test_search_journal_count_must_match_protocol(self) -> None:
        path = self.root / "search_history.json"
        history = json.loads(path.read_text())
        history["new_attempts"] = [{"attempt_id": "unreported_candidate"}]
        write_json(path, history)
        self.evidence["search_history"] = artifact_reference(path, self.root)
        self.assert_blocked("SEARCH_TOTAL_MISMATCH")

    def test_duplicate_registry_id_is_not_reregistered(self) -> None:
        with self.assertRaisesRegex(ValueError, "PROTOCOL_ALREADY_REGISTERED"):
            register_protocol(self.protocol, self.root / "preregistration.jsonl", "2029-12-15T00:00:00+00:00")

    def test_units_and_currency_are_verified(self) -> None:
        self.evidence["policies"]["SVR"]["equity_unit"] = "cents"
        self.assert_blocked("FUNDS_UNITS_SVR")

    def test_policy_bindings_are_verified(self) -> None:
        self.evidence["policies"]["RIDGE"]["risk_hash"] = digest("higher_exposure_for_svr")
        self.assert_blocked("RISK_HASH_BINDING_RIDGE")

    def test_universe_binding_is_verified(self) -> None:
        self.evidence["policies"]["SVR"]["universe"] = ["WINNER_CHOSEN_LATER"]
        self.assert_blocked("UNIVERSE_BINDING_SVR")

    def test_capital_reset_between_windows_is_blocked(self) -> None:
        self.evidence["policies"]["SVR"]["curve"][5]["equity_start_usd"] = 20000
        self.assert_blocked("CAPITAL_RESET_OR_DISCONTINUITY_SVR")

    def test_session_ids_are_paired_not_only_lengths(self) -> None:
        self.evidence["policies"]["RIDGE"]["curve"][5]["session_id"] = "different_session"
        self.assert_blocked("PAIRED_SESSION_IDS_MISMATCH")

    def test_session_timing_is_paired(self) -> None:
        self.evidence["policies"]["RIDGE"]["curve"][5]["start_at"] = "2030-01-06T01:00:00+00:00"
        self.assert_blocked("PAIRED_SESSION_TIMES_MISMATCH")

    def test_claimed_returns_cannot_override_reconstructed_returns(self) -> None:
        self.evidence["policies"]["SVR"]["curve"][0]["return_net"] = 0.5
        self.assert_blocked("RETURN_RECONCILIATION_SVR")

    def test_null_fees_are_unknown_not_zero(self) -> None:
        self.evidence["policies"]["RIDGE"]["curve"][0]["fees_in_equity_usd"] = None
        self.assert_blocked("INVALID_FEES")

    def test_double_counted_fee_breaks_pnl_reconciliation(self) -> None:
        self.evidence["policies"]["SVR"]["curve"][0]["fees_in_equity_usd"] *= 2
        self.assert_blocked("FLOW_COST_PNL_RECONCILIATION_SVR")

    def test_unknown_operating_costs_are_not_zero(self) -> None:
        self.evidence["policies"]["SVR"]["curve"][0]["operating_costs_in_equity_usd"] = None
        self.assert_blocked("INVALID_OPERATING_COSTS")

    def test_terminal_inventory_cannot_be_hidden(self) -> None:
        terminal = self.evidence["policies"]["SVR"]["terminal"]
        terminal["positions"] = [{"symbol": "FIXTURE_ETF", "quantity": 10, "mark_usd": 100, "liability_usd": 0, "valuation_side": "BID", "known_at": terminal["at"]}]
        self.assert_blocked("TERMINAL_INVENTORY_RECONCILIATION_SVR")

    def test_terminal_open_position_is_counted_when_reconciled(self) -> None:
        terminal = self.evidence["policies"]["SVR"]["terminal"]
        terminal["positions"] = [{"symbol": "FIXTURE_ETF", "quantity": 10, "mark_usd": 100, "liability_usd": 10, "valuation_side": "BID", "known_at": terminal["at"]}]
        terminal["cash_usd"] -= 990
        self.assertEqual(self.evaluate()["software_validators"]["status"], "PASS")

    def test_insolvency_is_rejected_without_clipping_log_returns(self) -> None:
        item = self.evidence["policies"]["SVR"]
        row = item["curve"][-1]
        row["equity_end_usd"] = -1.0
        row["gross_marked_pnl_usd"] = -1 - row["equity_start_usd"] + row["fees_in_equity_usd"] + row["operating_costs_in_equity_usd"]
        del row["return_net"]
        item["terminal"]["cash_usd"] = -1
        result = self.evaluate()
        self.assertEqual(result["dictamen"], "RECHAZADO")
        self.assertIsNone(result["statistics"])
        self.assertTrue(result["policies"]["SVR"]["insolvency"])
        self.assertIsNone(result["policies"]["SVR"]["mean_log_growth_per_session"])

    def test_drawdown_limit_rejects_candidate(self) -> None:
        self.change_last_return(-0.2)
        result = self.evaluate()
        self.assertIn("DRAWDOWN_LIMIT_EXCEEDED", result["rejection_reasons"])
        self.assertEqual(result["dictamen"], "RECHAZADO")

    def test_exposure_limit_rejects_candidate(self) -> None:
        self.evidence["policies"]["SVR"]["curve"][4]["gross_exposure_fraction"] = 0.8
        result = self.evaluate()
        self.assertIn("EXPOSURE_LIMIT_EXCEEDED", result["rejection_reasons"])

    def test_holding_and_dependency_parameters_are_not_implicit(self) -> None:
        self.protocol["horizon_hours"] = 73
        self.protocol = seal_protocol(self.protocol)
        self.assert_blocked("HORIZON_LIMIT")

    def test_block_shorter_than_dependency_is_blocked(self) -> None:
        self.protocol["dependence"]["dependency_horizon_sessions"] = 5
        self.protocol = seal_protocol(self.protocol)
        self.assert_blocked("BLOCK_SHORTER_THAN_DEPENDENCY")

    def test_final_sample_not_big_enough_is_inconclusive(self) -> None:
        self.protocol["dependence"]["minimum_sessions"] = 100
        self.refresh_protocol()
        result = self.evaluate()
        self.assertEqual(result["statistics"]["status"], "INCONCLUSIVE")
        self.assertIn("SESSION_SAMPLE_BELOW_PREREGISTERED_MINIMUM", result["financial_blockers"])

    def test_tail_precision_is_not_invented(self) -> None:
        self.protocol["statistics"]["bootstrap_repetitions"] = 100
        self.refresh_protocol()
        result = self.evaluate()
        self.assertEqual(result["statistics"]["blocks"], [])
        self.assertIn("BOOTSTRAP_TAIL_RESOLUTION_INSUFFICIENT", result["financial_blockers"])

    def test_bonferroni_accounts_for_attempts_blocks_and_endpoints(self) -> None:
        result = self.evaluate()
        statistics = result["statistics"]
        self.assertEqual(statistics["bonferroni_family_size"], 23 * 1 * 3)
        self.assertAlmostEqual(statistics["one_sided_alpha_per_endpoint"], 0.05 / 69)
        self.assertIsNone(statistics["effective_independent_observations"])

    def test_zero_variance_comparison_is_not_zero_width_proof(self) -> None:
        series = [0.001 + i * 0.00001 for i in range(64)]
        result = paired_block_bootstrap({"C0": [0] * 64, "RIDGE": series, "SVR": series}, self.protocol)
        self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertIn("DEGENERATE_ENDPOINT_VARIANCE", result["reasons"])

    def test_paired_bootstrap_preserves_shared_shocks(self) -> None:
        rng = np.random.default_rng(9)
        common = rng.normal(0, 0.02, 64)
        tiny = rng.normal(0, 0.000001, 64)
        values = {"C0": [0.0] * 64, "RIDGE": common.tolist(), "SVR": (common + 0.002 + tiny).tolist()}
        result = paired_block_bootstrap(values, self.protocol)
        errors = result["blocks"][0]["standard_error_of_bootstrap_means"]
        self.assertLess(errors["svr_minus_ridge"], errors["svr_log_growth"] / 1000)

    def test_loss_reduction_is_not_positive_net_growth(self) -> None:
        for name in ("RIDGE", "SVR"):
            item = self.evidence["policies"][name]
            previous = 20000.0
            for i, row in enumerate(item["curve"]):
                growth = (-0.001 if name == "RIDGE" else -0.0002) + 0.00001 * math.sin(i)
                end = previous * math.exp(growth)
                row.update(equity_start_usd=previous, equity_pre_flow_usd=previous, equity_end_usd=end, gross_marked_pnl_usd=end - previous + row["fees_in_equity_usd"] + row["operating_costs_in_equity_usd"], return_net=end / previous - 1)
                previous = end
            item["terminal"]["cash_usd"] = previous
        result = self.evaluate()
        self.assertEqual(result["dictamen"], "RECHAZADO")
        self.assertIn("NET_ABSOLUTE_PNL_NONPOSITIVE", result["rejection_reasons"])

    def test_self_declared_parity_does_not_replace_artifacts(self) -> None:
        self.evidence["policy_parity_verified"] = True
        del self.evidence["parity_receipt"]
        result = self.evaluate()
        self.assertTrue(any("PARITY_EVIDENCE" in reason for reason in result["financial_blockers"]))
        self.assertFalse(result["candidate_for_forward_validation"])

    def test_parity_mismatched_hash_is_blocked_even_when_passed_true(self) -> None:
        path = self.root / "parity_receipt.json"
        parity = json.loads(path.read_text())
        parity["checks"][0]["observed_hash"] = digest("DIFFERENT")
        parity["artifact_hash"] = digest({k: v for k, v in parity.items() if k != "artifact_hash"})
        write_json(path, parity)
        self.evidence["parity_receipt"] = artifact_reference(path, self.root)
        result = self.evaluate()
        self.assertIn("PARITY_EVIDENCE: PARITY_CHECK_FAILED", result["financial_blockers"])

    def test_source_code_tampering_invalidates_parity(self) -> None:
        (self.root / "fixture_policy.txt").write_text("modified policy\n")
        result = self.evaluate()
        self.assertIn("PARITY_EVIDENCE: ARTIFACT_HASH_MISMATCH", result["financial_blockers"])

    def test_native_c0_predictor_parity_does_not_certify_svr(self) -> None:
        path = self.root / "parity_receipt.json"
        parity = json.loads(path.read_text())
        parity["predictor_parity_verified"] = True
        parity["result"] = {"candidate": "C0"}
        parity["artifact_hash"] = digest({k: v for k, v in parity.items() if k != "artifact_hash"})
        write_json(path, parity)
        self.evidence["parity_receipt"] = artifact_reference(path, self.root)
        result = self.evaluate()
        self.assertTrue(result["parity"]["receipt_predictor_parity_verified_within_its_scope"])
        self.assertFalse(result["parity"]["predictor_parity_verified"])
        self.assertIn("PAIRED_POLICY_PARITY_INCOMPLETE", result["financial_blockers"])

    def test_observed_label_without_observations_is_insufficient(self) -> None:
        self.evidence["provenance"].update(price_origin="OBSERVED", availability="OBSERVED_RECEIPT_TIMESTAMPS")
        result = self.evaluate()
        self.assertTrue(any("OBSERVATIONAL_EVIDENCE" in reason for reason in result["financial_blockers"]))
        self.assertFalse(result["candidate_for_forward_validation"])

    def test_external_artifact_path_is_rejected(self) -> None:
        self.evidence["search_history"]["path"] = "../outside.json"
        self.assert_blocked("ARTIFACT_PATH_OUTSIDE_ROOT")

    def test_missing_prefow_mark_blocks_external_contribution(self) -> None:
        row = self.evidence["policies"]["SVR"]["curve"][-1]
        row["external_flow_usd"] = 100
        row["gross_marked_pnl_usd"] -= 100
        self.assert_blocked("PREFLOW_MARK_REQUIRED_SVR")

    def test_flow_adjustment_uses_measured_preflow_equity(self) -> None:
        for item in self.evidence["policies"].values():
            row = item["curve"][-1]
            start = row["equity_start_usd"]
            before = start * 1.001
            row["equity_pre_flow_usd"] = before
            row["external_flow_usd"] = 1000
            row["flow_count"] = 1
            row["flow_at"] = row["start_at"]
            row["pre_flow_mark_source_hash"] = digest("synthetic_prefow_mark")
            row["equity_end_usd"] += 1000
            row["return_net"] = before / start * row["equity_end_usd"] / (before + 1000) - 1
            item["terminal"]["cash_usd"] = row["equity_end_usd"]
        result = self.evaluate()
        self.assertEqual(result["software_validators"]["status"], "PASS")
        self.assertEqual(result["policies"]["SVR"]["external_flows_usd"], 1000)
        self.assertAlmostEqual(result["policies"]["SVR"]["net_pnl_usd"], result["policies"]["SVR"]["final_equity_usd"] - 21000)

    def test_missing_flow_cost_evidence_does_not_mutate_input(self) -> None:
        before = copy.deepcopy(self.evidence)
        self.evaluate()
        self.assertEqual(before, self.evidence)

    def test_dropping_same_losing_session_from_all_policies_is_detected(self) -> None:
        for item in self.evidence["policies"].values():
            # Remove a terminal session and reconcile the smaller curve.  Equal
            # lengths and session IDs across models alone would not catch this.
            item["curve"].pop()
            item["terminal"]["at"] = item["curve"][-1]["end_at"]
            item["terminal"]["cash_usd"] = item["curve"][-1]["equity_end_usd"]
        self.assert_blocked("PREREGISTERED_SESSIONS_MISMATCH")

    def test_control_with_different_observed_risk_cannot_validate_comparison(self) -> None:
        self.evidence["policies"]["RIDGE"]["curve"][0]["gross_exposure_fraction"] = 0.8
        result = self.evaluate()
        self.assertIn("CONTROL_RISK_LIMITS_EXCEEDED", result["financial_blockers"])

    def test_terminal_borrowing_is_outside_scope(self) -> None:
        terminal = self.evidence["policies"]["SVR"]["terminal"]
        old_equity = terminal["cash_usd"]
        terminal["cash_usd"] = -10
        terminal["positions"] = [{"symbol": "FIXTURE_ETF", "quantity": 1, "mark_usd": old_equity + 10, "liability_usd": 0, "valuation_side": "BID", "known_at": terminal["at"]}]
        self.assert_blocked("TERMINAL_BORROWING_OUTSIDE_SCOPE_SVR")

    def test_bootstrap_compute_budget_has_a_deterministic_bound(self) -> None:
        protocol = copy.deepcopy(self.protocol)
        protocol["statistics"]["bootstrap_repetitions"] = 500000
        data = np.linspace(0.0001, 0.002, 300).tolist()
        result = paired_block_bootstrap({"C0": [0] * 300, "RIDGE": [v / 2 for v in data], "SVR": data}, protocol)
        self.assertIn("BOOTSTRAP_COMPUTE_BUDGET_EXCEEDED", result["reasons"])
        self.assertEqual(result["blocks"], [])

    def test_more_candidate_exposure_is_not_mistaken_for_predictive_improvement(self) -> None:
        for row in self.evidence["policies"]["RIDGE"]["curve"]:
            row["gross_exposure_fraction"] = 0.1
        result = self.evaluate()
        self.assertIn("CANDIDATE_EXPOSURE_NOT_COMPARABLE_TO_RIDGE", result["financial_blockers"])


if __name__ == "__main__":
    unittest.main()
