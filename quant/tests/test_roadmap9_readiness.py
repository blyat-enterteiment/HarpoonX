"""Operational and forward-evidence attacks; all fixtures are synthetic."""

from __future__ import annotations

import base64
import copy
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from harpoon_quant.roadmap9.forward import (
    assess_forward,
    block_growth_test,
    canonical,
    digest,
    reconcile_packet,
    verify_attestation,
)
from harpoon_quant.roadmap9.operations import (
    GuardLimits,
    evaluate_health,
    rollback_plan,
)


def fixture():
    protocol = {"registered_at": 1, "calibration_end": 10, "evaluation_start": 1000,
                "evaluation_end": 10_000, "initial_capital_usd": "20000",
                "code_commit": "a" * 40, "recipe_hash": "b" * 64,
                "cost_profile_hash": "c" * 64, "max_quote_age_ms": 15_000,
                "max_model_label_age_ms": 168 * 3_600_000, "max_mark_age_ms": 15000,
                "max_snapshot_gap_ms": 86_400_000, "observation_times": [1000, 10_000],
                "instruments": {"AAPL": {"base": "AAPL", "quote": "USD", "quantity_increment": "1"}}}
    def order(oid, side, when):
        return {"order_id": oid, "client_order_id": "client-" + oid, "campaign_id": "campaign-one",
                "symbol": "AAPL", "side": side, "quantity": "10", "opened_at": 1100,
                "original_deadline": 20_000, "decision_at": when, "submitted_at": when + 1,
                "quote_event_at": when - 2, "quote_available_at": when - 1,
                "latest_training_label_available_at": 999,
                "model_available_at": 1000}
    events = [
        {"event_id": "s0", "kind": "SNAPSHOT", "at": 1000, "received_at": 1001,
         "balances": {"USD": "20000"}, "usd_marks": {"USD": "1"}, "economic_equity_usd": "20000"},
        {"event_id": "f1", "kind": "FILL", "at": 2000, "received_at": 2001,
         "fill_id": "fill1", "order_id": "buy", "quantity": "10", "price": "100",
         "fee_provision_currency": "USD", "fee_provision": "1"},
        {"event_id": "fee1", "kind": "FEE", "at": 3000, "received_at": 3001,
         "fill_id": "fill1", "currency": "USD", "amount": "1"},
        {"event_id": "f2", "kind": "FILL", "at": 6000, "received_at": 6001,
         "fill_id": "fill2", "order_id": "sell", "quantity": "10", "price": "101",
         "fee_provision_currency": "USD", "fee_provision": "1"},
        {"event_id": "fee2", "kind": "FEE", "at": 7000, "received_at": 7001,
         "fill_id": "fill2", "currency": "USD", "amount": "1"},
        {"event_id": "cost", "kind": "EXTERNAL_COST", "at": 8000, "received_at": 8001,
         "cost_id": "invoice-one", "amount_usd": "5", "debited_from_account": False},
        {"event_id": "s1", "kind": "SNAPSHOT", "at": 10000, "received_at": 10001,
         "balances": {"USD": "20008", "AAPL": "0"}, "usd_marks": {"USD": "1"},
         "economic_equity_usd": "20003"}]
    packet = {"schema": "HARPOON_ROADMAP_FORWARD_PACKET_1", "origin": "SYNTHETIC_ENGINEERING_ONLY",
              "account_ref": "SYNTHETIC_TEST_ACCOUNT", "protocol_sha256": digest(protocol),
              "code_commit": protocol["code_commit"], "recipe_hash": protocol["recipe_hash"],
              "cost_profile_hash": protocol["cost_profile_hash"],
              "orders": [order("buy", "buy", 1100), order("sell", "sell", 5100)], "events": events}
    return packet, protocol


class ForwardEvidenceTests(unittest.TestCase):
    def test_exact_account_reconciliation_includes_external_cost_once(self):
        packet, protocol = fixture()
        receipt = reconcile_packet(packet, protocol)
        self.assertEqual(receipt["net_pnl_usd"], "3")
        self.assertEqual(receipt["fill_count"], 2)
        self.assertFalse(receipt["source_authenticity_verified"])

    def test_duplicate_event_idempotent_conflict_rejected(self):
        packet, protocol = fixture()
        packet["events"].insert(2, copy.deepcopy(packet["events"][1]))
        self.assertEqual(reconcile_packet(packet, protocol)["fill_count"], 2)
        packet["events"][2]["quantity"] = "9"
        with self.assertRaisesRegex(ValueError, "CONFLICTING_EVENT"):
            reconcile_packet(packet, protocol)

    def test_cumulative_quantity_cannot_be_used_as_another_fill(self):
        packet, protocol = fixture()
        packet["events"][1]["quantity"] = "11"
        with self.assertRaisesRegex(ValueError, "CUMULATIVE_OVERFILL"):
            reconcile_packet(packet, protocol)

    def test_balance_mismatch_cannot_be_fixed_by_rehashing(self):
        packet, protocol = fixture()
        packet["events"][-1]["balances"]["USD"] = "30008"
        with self.assertRaisesRegex(ValueError, "BROKER_BALANCE_MISMATCH"):
            reconcile_packet(packet, protocol)

    def test_campaign_deadline_cannot_restart_at_exit(self):
        packet, protocol = fixture()
        packet["orders"][1]["opened_at"] = 5000
        packet["orders"][1]["original_deadline"] = 25000
        with self.assertRaisesRegex(ValueError, "CAMPAIGN_DEADLINE_RESET"):
            reconcile_packet(packet, protocol)

    def test_future_quote_and_label_are_rejected(self):
        for field in ("quote_available_at", "latest_training_label_available_at"):
            packet, protocol = fixture()
            packet["orders"][0][field] = 1101
            with self.assertRaisesRegex(ValueError, "LOOKAHEAD"):
                reconcile_packet(packet, protocol)

    def test_fresh_receipt_cannot_hide_stale_quote_event(self):
        packet, protocol = fixture()
        protocol["max_quote_age_ms"] = 100
        packet["protocol_sha256"] = digest(protocol)
        packet["orders"][0]["quote_event_at"] = 999
        with self.assertRaisesRegex(ValueError, "STALE_DECISION_QUOTE"):
            reconcile_packet(packet, protocol)

    def test_registered_freshness_cannot_expand_original_caps(self):
        for field, value in (("max_quote_age_ms", 15001), ("max_mark_age_ms", True),
                             ("max_model_label_age_ms", 169 * 3_600_000)):
            packet, protocol = fixture()
            protocol[field] = value
            packet["protocol_sha256"] = digest(protocol)
            with self.assertRaisesRegex(ValueError, "PROTOCOL_FRESHNESS_LIMIT"):
                reconcile_packet(packet, protocol)

    def test_cost_invoice_not_counted_twice(self):
        packet, protocol = fixture()
        duplicate = copy.deepcopy(packet["events"][-2])
        duplicate["event_id"] = "other-event-same-invoice"
        packet["events"].insert(-1, duplicate)
        with self.assertRaisesRegex(ValueError, "DUPLICATE_SHARED_COST"):
            reconcile_packet(packet, protocol)

    def test_fee_posting_late_is_pending_not_zero(self):
        packet, protocol = fixture()
        packet["origin"] = "OBSERVED_PAPER"
        packet["events"] = [e for e in packet["events"] if e["event_id"] != "fee2"]
        packet["events"][-1]["balances"]["USD"] = "20009"
        report = assess_forward(packet, protocol, now_ms=20000)
        self.assertEqual(report["blocking_reasons"], ["UNRECONCILED_FEE_ACTIVITIES"])
        self.assertFalse(report["execution_allowed"])

    def test_source_authentication_not_self_attestable(self):
        packet, protocol = fixture()
        packet["origin"] = "OBSERVED_LIVE"
        packet["source_authenticity_verified"] = True
        result = assess_forward(packet, protocol, now_ms=20000)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("SOURCE_AUTHENTICATION", result["blocking_reasons"][0])

    def test_synthetic_and_missing_packets_never_admit(self):
        packet, protocol = fixture()
        self.assertEqual(assess_forward(packet, protocol, now_ms=20000)["status"], "BLOCKED")
        self.assertEqual(assess_forward(None, None)["status"], "BLOCKED")

    def test_incomplete_observation_calendar_rejected(self):
        packet, protocol = fixture()
        protocol["observation_times"] = [1000, 5000, 10000]
        packet["protocol_sha256"] = digest(protocol)
        with self.assertRaisesRegex(ValueError, "REGISTERED_OBSERVATION_COVERAGE"):
            reconcile_packet(packet, protocol)

    def test_native_crypto_fee_inventory_is_not_usd_fee(self):
        packet, protocol = fixture()
        # Buy-only position; the fee removes a fraction of the acquired asset.
        packet["orders"] = packet["orders"][:1]
        packet["events"] = packet["events"][:3] + [packet["events"][-1]]
        packet["events"][1]["fee_provision_currency"] = "AAPL"
        packet["events"][1]["fee_provision"] = "0.025"
        packet["events"][2].update(currency="AAPL", amount="0.025")
        packet["events"][-1].update(balances={"USD": "19000", "AAPL": "9.975"},
            usd_marks={"USD": "1", "AAPL": "100"}, economic_equity_usd="19997.500",
            mark_timestamps={"AAPL": {"event_at": 9999, "available_at": 10000}})
        self.assertEqual(reconcile_packet(packet, protocol)["balances"]["AAPL"], "9.975")

    def test_open_position_past_deadline_is_a_breach_without_a_late_fill(self):
        packet, protocol = fixture()
        packet["origin"] = "OBSERVED_PAPER"
        packet["orders"] = packet["orders"][:1]
        packet["orders"][0]["original_deadline"] = 5000
        packet["events"] = packet["events"][:3] + [packet["events"][-1]]
        packet["events"][-1].update(balances={"USD": "18999", "AAPL": "10"},
            usd_marks={"USD": "1", "AAPL": "100"}, economic_equity_usd="19999",
            mark_timestamps={"AAPL": {"event_at": 9999, "available_at": 10000}})
        result = assess_forward(packet, protocol, now_ms=20000)
        self.assertIn("EXPIRED_RESIDUAL_INVENTORY", result["blocking_reasons"])
        self.assertEqual(len(result["reconciliation"]["expired_residual_inventory"]), 1)

    def test_sell_cannot_borrow_inventory_of_another_campaign(self):
        packet, protocol = fixture()
        packet["orders"][1]["campaign_id"] = "unfunded-other-campaign"
        with self.assertRaisesRegex(ValueError, "CROSS_CAMPAIGN"):
            reconcile_packet(packet, protocol)

    def test_model_available_after_decision_rejected(self):
        packet, protocol = fixture()
        packet["orders"][0]["model_available_at"] = 2000
        with self.assertRaisesRegex(ValueError, "MODEL_AVAILABILITY_LOOKAHEAD"):
            reconcile_packet(packet, protocol)

    def test_nonfinite_and_bool_amounts_rejected(self):
        for invalid in (True, "NaN", "Infinity", "-1"):
            packet, protocol = fixture()
            packet["events"][1]["price"] = invalid
            with self.assertRaises(ValueError):
                reconcile_packet(packet, protocol)


class AttestationTests(unittest.TestCase):
    def test_signature_binds_content_scope_and_expiry(self):
        private = Ed25519PrivateKey.generate()
        payload = {"role": "BROKER_SOURCE", "signer_id": "UNIT_TEST_SIGNER",
                   "issued_at": 10, "expires_at": 100, "packet_sha256": "a" * 64}
        attestation = {"key_id": "TEST", "payload": payload,
            "signature": base64.b64encode(private.sign(canonical(payload))).decode()}
        store = {"TEST": {"roles": ["BROKER_SOURCE"], "signer_id": "UNIT_TEST_SIGNER", "test_only": False,
                 "public_key_hex": private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()}}
        args = {"role": "BROKER_SOURCE", "expected": {"packet_sha256": "a" * 64}, "now_ms": 50}
        self.assertTrue(verify_attestation(attestation, store, **args)["verified"])
        payload["packet_sha256"] = "b" * 64
        self.assertFalse(verify_attestation(attestation, store, **args)["verified"])
        payload["packet_sha256"] = "a" * 64
        store["TEST"]["test_only"] = True
        self.assertFalse(verify_attestation(attestation, store, **args)["verified"])
        store["TEST"]["test_only"] = False
        args["now_ms"] = 101
        self.assertFalse(verify_attestation(attestation, store, **args)["verified"])

    def test_author_cannot_sign_external_review_as_self(self):
        private = Ed25519PrivateKey.generate()
        payload = {"role": "EXTERNAL_REVIEW", "signer_id": "AUTHOR", "author_id": "AUTHOR",
                   "issued_at": 10, "expires_at": 100, "verdict": "ACCEPT", "critical_findings": 0}
        attestation = {"key_id": "TEST", "payload": payload,
            "signature": base64.b64encode(private.sign(canonical(payload))).decode()}
        store = {"TEST": {"roles": ["EXTERNAL_REVIEW"], "signer_id": "AUTHOR", "test_only": False,
                 "independent_reviewer": True,
                 "public_key_hex": private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()}}
        result = verify_attestation(attestation, store, role="EXTERNAL_REVIEW", expected={}, now_ms=50)
        self.assertFalse(result["verified"])
        self.assertEqual(result["reason"], "REVIEWER_NOT_INDEPENDENT")


class OperationsTests(unittest.TestCase):
    def state(self):
        return {"market_event_at": 9999, "market_received_at": 10000, "broker_reconciled_at": 10000,
                "model_trained_at": 5000, "latest_label_available_at": 4000,
                "daily_loss_fraction": 0.001, "drawdown_fraction": 0.002,
                "reconciled": True, "predictor_ready": True, "execution_authority": True}

    def test_timer_does_not_keep_alive_and_llm_not_needed(self):
        state = self.state()
        self.assertTrue(evaluate_health(state, 11000)["alive"])
        self.assertFalse(evaluate_health(state, 26000)["alive"])
        self.assertFalse(evaluate_health(state, 11000)["execution_allowed"])

    def test_missing_predictor_preserves_deterministic_reduction(self):
        state = self.state()
        state["predictor_ready"] = False
        receipt = evaluate_health(state, 11000)
        self.assertFalse(receipt["entries_ready"])
        self.assertEqual(receipt["owned_inventory_management"], "REDUCTION_READY")

    def test_new_receipt_does_not_refresh_an_old_quote(self):
        state = self.state()
        state["market_received_at"] = 26000
        state["broker_reconciled_at"] = 26000
        self.assertFalse(evaluate_health(state, 26000)["alive"])

    def test_ambiguous_order_requires_reconciliation(self):
        state = self.state()
        state["ambiguous_orders"] = ["order-unknown"]
        self.assertEqual(evaluate_health(state, 11000)["owned_inventory_management"], "RECONCILE_ONLY")

    def test_label_after_model_fit_blocks_entry_but_not_feed_health(self):
        state = self.state()
        state["latest_label_available_at"] = 9000
        receipt = evaluate_health(state, 10000)
        self.assertIn("MODEL_LABEL_CLOCK", receipt["blocking_reasons"])
        self.assertFalse(receipt["entries_ready"])
        self.assertTrue(receipt["alive"])
        self.assertEqual(receipt["owned_inventory_management"], "REDUCTION_READY")

    def test_loss_and_alpha_degradation_stop_entries(self):
        state = self.state()
        state.update(daily_loss_fraction=0.02, alpha_observations=100, rolling_excess_log_growth=-0.001)
        result = evaluate_health(state, 11000)
        self.assertIn("ALPHA_DEGRADATION", result["blocking_reasons"])
        self.assertIn("LIMIT_DAILY_LOSS_FRACTION", result["blocking_reasons"])

    def test_measured_cost_degradation_pauses_entries_and_keeps_reduction(self):
        state = self.state()
        state.update(cost_observations=30, realized_to_modeled_cost_ratio=1.26)
        result = evaluate_health(state, 11000)
        self.assertIn("EXECUTION_COST_DEGRADATION", result["blocking_reasons"])
        self.assertFalse(result["entries_ready"])
        self.assertEqual(result["owned_inventory_management"], "REDUCTION_READY")
        state["realized_to_modeled_cost_ratio"] = None
        self.assertIn("COST_METRIC_UNKNOWN", evaluate_health(state, 11000)["blocking_reasons"])

    def test_custom_health_limits_cannot_relax_original_caps(self):
        for options in ({"quote_max_age_ms": 15001}, {"model_max_age_ms": 169 * 3_600_000},
                        {"daily_loss_fraction": .03}, {"drawdown_fraction": .11}):
            with self.assertRaisesRegex(ValueError, "CAP"):
                GuardLimits(**options)

    def test_rollback_preserves_deadlines_and_rejects_failed_policy(self):
        state = {"reconciled": True, "inventory": {"AAPL": 3}, "pending_orders": ["id"],
                 "campaigns": [{"opened_at": 1000, "original_deadline": 20000}]}
        target = {"economic_status": "REJECTED", "code_commit": "a", "recipe_hash": "b"}
        with self.assertRaisesRegex(ValueError, "NOT_APPROVED"):
            rollback_plan(state, target)
        target["economic_status"] = "APPROVED_SCOPED_RELEASE"
        result = rollback_plan(state, target)
        self.assertEqual(result["campaigns"], state["campaigns"])
        self.assertEqual(result["inventory"], state["inventory"])
        self.assertTrue(result["pause_new_entries"])


class ProspectiveStatisticsTests(unittest.TestCase):
    def settings(self):
        return {"minimum_observations": 20, "block_lengths": [5, 10], "draws": 1000,
                "family_endpoints": 3, "alpha": 0.05, "minimum_mean_log_edge": 0.00001,
                "seed": 20261102, "global_search_history_complete": False}

    def test_positive_synthetic_series_does_not_repair_incomplete_search_history(self):
        result = block_growth_test([0.001] * 30, {"CASH": [0.] * 30, "BASELINE": [0.] * 30}, self.settings())
        self.assertTrue(result["within_family_criterion_passed"])
        self.assertEqual(result["decision"], "NO_CONCLUSION")
        self.assertFalse(result["financial_acceptance_allowed"])

    def test_paired_controls_and_support_are_mandatory(self):
        with self.assertRaisesRegex(ValueError, "PAIRED_CONTROLS"):
            block_growth_test([0.001] * 30, {}, self.settings())
        settings = self.settings()
        settings["minimum_observations"] = 100
        result = block_growth_test([0.001] * 30, {"CASH": [0.] * 30, "BASELINE": [0.] * 30}, settings)
        self.assertFalse(result["support_sufficient"])

    def test_boolean_flag_cannot_certify_global_selection_correction(self):
        settings = self.settings()
        settings["global_search_history_complete"] = True
        result = block_growth_test([0.001] * 30, {"CASH": [0.] * 30, "BASELINE": [0.] * 30}, settings)
        self.assertFalse(result["global_search_correction_certified"])


if __name__ == "__main__":
    unittest.main()
