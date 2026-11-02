"""Synthetic gate tests only: never collect prices, register or issue orders."""
import copy
import json
import sys
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import residual_forward as f

HASH = "a"*64
OPEN = 1793633400000  # Synthetic fixture: 2026-11-02 14:10 UTC; supplied calendar.
NOW = OPEN + 3*86400000


def fixture():
    from datetime import datetime, timezone
    sid = datetime.fromtimestamp(OPEN/1000, timezone.utc).date().isoformat()
    protocol = {"study_id": "SYNTHETIC_ONLY", "universe": ["AAPL", "MSFT", "XLK"],
                "recipe": {"entry_minutes": 60, "entry_delay_ms": 1000},
                "limits": {"capitalUsd": 20000},
                "scenarios": {"NOMINAL": {"external_cost_usd_per_session": 1}},
                "statistics": {"minimum_observed_sessions": 100, "minimum_closed_candidate_campaigns": 20},
                "forward_plan": {"no_live_orders_authorized": True, "first_possible_session": sid}}
    model = {"schema": "HARPOON_RESIDUAL_MODELS_1", "provenance": {"protocol_sha256": f.digest(protocol)},
             "counts": {"available_models": 2}}
    model["model_payload_sha256"] = f.digest(model)
    receipt = {"verified": True, "offline_replay_admitted": True, "admission_identity_hash": HASH}
    freeze = f.create_freeze(model, protocol, {"tools/example.py": HASH}, receipt, HASH, HASH, OPEN-10000)
    at, close = OPEN+3601000, OPEN+23400000
    def raw(ident, kind, event, received, value, symbol=None):
        r = {"id": ident, "kind": kind, "event_end": event, "original_received_at": received,
             "receipt_clock": "ORIGINAL_FIRST_RECEIVED", "source": "SYNTHETIC_CONTRACT_ONLY",
             "source_receipt_sha256": HASH, "data": value}
        if symbol:
            r["symbol"] = symbol
        return r
    records = [raw("coverage", "CORPORATE_COVERAGE", OPEN, OPEN+1, {}),
               raw("bar", "BAR", OPEN+3600000, OPEN+3601000,
                   {"t": OPEN+3300000, "end": OPEN+3600000, "o": 100, "h": 101, "l": 99, "c": 100, "v": 10}, "AAPL")]
    account = {"session_id": sid, "at": close, "equity_start": 20000, "equity_end": 19999,
               "cash_start": 20000, "cash_end": 19999, "positions_mark_start": 0, "positions_mark_end": 0,
               "receivables_start": 0, "receivables_end": 0, "trading_pnl_usd": 0,
               "dividend_income_usd": 0, "external_costs_usd": 1, "cost_receipt_ids": []}
    bundle = {"schema": f.BUNDLE_SCHEMA, "origin": "FORWARD", "mode": "CONDITIONAL_PAPER", "policy": "RESIDUAL_LONG",
              "created_at": close+1000, "freeze_sha256": freeze["freeze_sha256"],
              "model_artifact_sha256": HASH, "code_hashes": freeze["code_hashes"], "scenario": "NOMINAL",
              "session_calendar": [{"date": sid, "open": OPEN, "close": close}], "receipts": records,
              "decisions": [{"id": "decision", "at": at, "session_id": sid, "receipt_ids": ["bar"],
                             "model_artifact_sha256": HASH, "code_hashes": freeze["code_hashes"]}],
              "corporate_actions": [], "corporate_action_coverage": {"status": "OBSERVED", "start": OPEN,
                  "end": close, "receipt_id": "coverage"}, "account": [account], "campaigns": [], **f.AUTHORITY}
    return freeze, bundle, raw, model, protocol, receipt


class ForwardTests(unittest.TestCase):
    def setUp(self):
        self.freeze, self.bundle, self.raw, self.model, self.protocol, self.admission = fixture()
        self.clock = patch.object(f.time, "time_ns", return_value=NOW*1_000_000)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def result(self):
        return f.validate_bundle(self.bundle, self.freeze)

    def assertBlocked(self, code):
        result = self.result()
        self.assertFalse(result["valid"], result)
        self.assertIn(code, {e["code"] for e in result["blocking_reasons"]})
        self.assertFalse(result["orders_allowed"])
        self.assertFalse(result["level8_accredited"])

    def test_valid_paper_records_never_claim_real_economics_or_level(self):
        result = self.result()
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["economic_evidence_class"], "CONDITIONAL_PAPER_ONLY")
        self.assertFalse(result["real_economics_evidence_complete"])
        self.assertFalse(result["real_profitability_validated"])
        self.assertEqual(result["observed_sessions"], 1)
        self.assertFalse(result["minimum_count_gates"]["sufficient_for_level8"])

    def test_empty_template_is_blocked_not_fake_observation(self):
        result = f.validate_bundle(f.bundle_template(self.freeze), self.freeze)
        self.assertFalse(result["valid"])
        self.assertFalse(result["orders_allowed"])

    def test_malformed_inputs_return_structured_blockers(self):
        for bundle, freeze in [(None, self.freeze), (self.bundle, None), ([], [])]:
            result = f.validate_bundle(bundle, freeze)
            self.assertFalse(result["valid"])
            self.assertFalse(result["orders_allowed"])
        self.freeze["minimum_sessions"] = "100"
        self.assertBlocked("MINIMUM_SESSION_GATE_INVALID")

    def test_reservation_alone_cannot_create_freeze(self):
        for receipt in [{"verified": True}, {"verified": True, "offline_replay_admitted": False, "admission_identity_hash": HASH}]:
            with self.assertRaisesRegex(ValueError, "FULL_DATA_CODE_ADMISSION_REQUIRED"):
                f.create_freeze(self.model, self.protocol, {"x.py": HASH}, receipt, HASH, HASH, OPEN-1)

    def test_freeze_and_model_hash_tampering_fail(self):
        self.freeze["limits"]["capitalUsd"] = 10
        self.assertBlocked("FREEZE_HASH_MISMATCH")

    def test_code_identity_requires_exact_mapping_not_only_subset(self):
        self.bundle["code_hashes"] = {**self.bundle["code_hashes"], "unregistered.py": HASH}
        self.assertBlocked("EXACT_CODE_BINDING")

    def test_model_original_bytes_hash_required(self):
        self.bundle["model_artifact_sha256"] = "b"*64
        self.assertBlocked("MODEL_BYTES_BINDING")

    def test_first_price_receipt_before_freeze_blocked(self):
        b = self.bundle["receipts"][1]
        b["original_received_at"] = self.freeze["frozen_at"]
        self.assertBlocked("FIRST_PRICE_OBSERVED_BEFORE_FREEZE")

    def test_modeled_timestamp_cannot_be_promoted(self):
        self.bundle["receipts"][1]["receipt_clock"] = "MODELED_AVAILABLE_AT"
        self.assertBlocked("MODELED_OR_RECONSTRUCTED_RECEIPT_FORBIDDEN")

    def test_missing_original_timestamp_not_imputed(self):
        del self.bundle["receipts"][1]["original_received_at"]
        self.assertBlocked("REQUIRED_FIELD_OR_CONTRACT")

    def test_receipt_after_decision_is_not_available(self):
        self.bundle["receipts"][1]["original_received_at"] += 1
        self.assertBlocked("DECISION_UNAVAILABLE_PRICE_RECEIPT")

    def test_future_receipts_blocked(self):
        self.bundle["receipts"][1]["original_received_at"] = NOW+1
        self.assertBlocked("FUTURE_OR_PRE_EVENT_RECEIPT")

    def test_backward_receipt_time_blocked(self):
        self.bundle["receipts"].reverse()
        self.assertBlocked("RECEIPT_TIME_BACKWARD")

    def test_duplicate_ids_blocked(self):
        self.bundle["decisions"][0]["id"] = "bar"
        self.assertBlocked("DUPLICATE_RECORD_ID")

    def test_calendar_and_decision_clock_required(self):
        self.bundle["decisions"][0]["at"] += 300000
        self.assertBlocked("DECISION_CLOCK_RECIPE")

    def test_observed_corporate_coverage_not_missing_or_modeled(self):
        self.bundle["corporate_action_coverage"]["status"] = "ASSUMED"
        self.assertBlocked("OBSERVED_CORPORATE_ACTION_COVERAGE_REQUIRED")

    def test_corporate_action_known_later_blocks_earlier_effective_decision(self):
        known = self.bundle["decisions"][0]["at"]+100
        self.bundle["receipts"].append(self.raw("ca-receipt", "CORPORATE_ACTION", known, known, {}))
        self.bundle["corporate_actions"].append({"id": "ca", "symbol": "AAPL", "effective_at": OPEN,
            "known_at": known, "receipt_id": "ca-receipt", "knowledge_source": "OBSERVED_ORIGINAL_RECEIPT"})
        self.assertBlocked("CORPORATE_ACTION_NOT_KNOWN_AT_DECISION")

    def test_continuous_capital_cannot_reset_next_session(self):
        s = self.bundle["session_calendar"][0]
        new_s = {"date": "2026-11-03", "open": s["open"]+86400000, "close": s["close"]+86400000}
        self.bundle["session_calendar"].append(new_s)
        self.bundle["created_at"] = new_s["close"]+1000
        row = copy.deepcopy(self.bundle["account"][0])
        row.update(session_id=new_s["date"], at=new_s["close"])
        self.bundle["account"].append(row)
        self.assertBlocked("DISCONTINUOUS_CAPITAL")

    def test_missing_cash_session_not_silently_skipped(self):
        self.bundle["account"] = []
        self.assertBlocked("CONTINUOUS_ALL_SESSION_ACCOUNT_REQUIRED")

    def test_fixed_cost_charged_once_even_with_no_campaign(self):
        row = self.bundle["account"][0]
        row.update(external_costs_usd=0, equity_end=20000, cash_end=20000)
        self.assertBlocked("FIXED_COST_NOT_CHARGED_ONCE_PER_SESSION")

    def test_real_mode_without_cost_invoices_is_blocked(self):
        self.bundle["mode"] = "OBSERVED_EXECUTION"
        self.assertBlocked("OBSERVED_EXTERNAL_COST_RECEIPTS_REQUIRED")

    def campaign(self):
        d = self.bundle["decisions"][0]
        opened, closed = d["at"]+299000, d["at"]+3600000
        self.bundle["campaigns"] = [{"id": "campaign", "decision_id": d["id"], "symbol": "AAPL",
            "opened_at": opened, "closed_at": closed, "fill_receipt_ids": [], "cost_receipt_ids": []}]
        return opened, closed

    def test_72_calendar_hours_not_three_sessions(self):
        self.campaign()
        self.bundle["campaigns"][0]["closed_at"] = self.bundle["decisions"][0]["at"]+72*3600000+1
        self.assertBlocked("CAMPAIGN_72_CALENDAR_HOURS")

    def observed_fixture(self):
        opened, closed = self.campaign()
        self.bundle["mode"] = "OBSERVED_EXECUTION"
        records = [self.raw("buy", "FILL", opened, opened+1, {"side": "BUY", "quantity": 1, "price": 100, "broker_execution_id": "B"}, "AAPL"),
                   self.raw("sell", "FILL", closed, closed+1, {"side": "SELL", "quantity": 1, "price": 100.01, "broker_execution_id": "S"}, "AAPL"),
                   self.raw("trade-cost", "COST", closed, closed+2, {"cost_type": "TRADING", "amount_usd": .01, "invoice_or_statement_id": "T"}),
                   self.raw("external", "COST", closed, closed+3, {"cost_type": "EXTERNAL", "amount_usd": 1, "invoice_or_statement_id": "E"})]
        self.bundle["receipts"].extend(records)
        self.bundle["campaigns"][0].update(fill_receipt_ids=["buy", "sell"], cost_receipt_ids=["trade-cost"])
        self.bundle["account"][0]["cost_receipt_ids"] = ["external"]

    def test_observed_execution_receipts_still_do_not_certify_profitability(self):
        self.observed_fixture()
        result = self.result()
        self.assertTrue(result["valid"], result)
        self.assertFalse(result["real_economics_evidence_complete"])
        self.assertTrue(result["observed_execution_receipts_structurally_complete"])
        self.assertFalse(result["source_authenticity_independently_verified"])
        self.assertFalse(result["real_profitability_validated"])
        self.assertFalse(result["orders_allowed"])

    def test_economic_receipts_cannot_repeat_inside_campaign(self):
        self.observed_fixture()
        self.bundle["campaigns"][0]["fill_receipt_ids"] *= 2
        self.assertBlocked("DUPLICATE_ECONOMIC_RECEIPT_REFERENCE")

    def test_economic_receipts_cannot_reuse_between_campaigns(self):
        self.observed_fixture()
        clone = copy.deepcopy(self.bundle["campaigns"][0])
        clone["id"] = "second-campaign"
        self.bundle["campaigns"].append(clone)
        self.assertBlocked("ECONOMIC_RECEIPT_REUSED")
        self.assertBlocked("MULTIPLE_CAMPAIGNS_FOR_ONE_DECISION")

    def test_cloned_invoice_different_record_id_is_still_duplicate(self):
        self.observed_fixture()
        clone = copy.deepcopy(self.bundle["receipts"][-1])
        clone["id"] = "forged-invoice-copy"
        self.bundle["receipts"].append(clone)
        self.assertBlocked("DUPLICATE_COST_INVOICE_ITEM")

    def test_cloned_execution_different_record_id_is_still_duplicate(self):
        self.observed_fixture()
        clone = copy.deepcopy(next(r for r in self.bundle["receipts"] if r["id"] == "buy"))
        clone["id"] = "forged-fill-copy"
        self.bundle["receipts"].append(clone)
        self.bundle["receipts"].sort(key=lambda r: r["original_received_at"])
        self.assertBlocked("DUPLICATE_BROKER_EXECUTION_ITEM")

    def test_coverage_receipt_after_decision_is_not_knowledge(self):
        self.bundle["receipts"][0]["original_received_at"] = self.bundle["decisions"][0]["at"]+1
        self.bundle["receipts"].sort(key=lambda r: r["original_received_at"])
        self.assertBlocked("OBSERVED_CORPORATE_ACTION_COVERAGE_REQUIRED")

    def test_sell_before_buy_not_long_only_observed_campaign(self):
        self.observed_fixture()
        for r in self.bundle["receipts"]:
            if r["id"] == "buy":
                r["data"]["side"] = "SELL"
            elif r["id"] == "sell":
                r["data"]["side"] = "BUY"
        self.assertBlocked("OBSERVED_MATCHED_FILL_AND_COST_RECEIPTS_REQUIRED")

    def test_cli_freeze_checks_registration_before_opening_artifacts(self):
        verify = Mock(side_effect=ValueError("NOT_ADMITTED"))
        with patch.dict(sys.modules, {"residual_register": SimpleNamespace(verify=verify)}):
            with self.assertRaisesRegex(ValueError, "NOT_ADMITTED"):
                f.freeze_from_artifacts(Path("missing-protocol"), Path("missing-artifacts"))
        verify.assert_called_once()

    def test_cli_freeze_binds_original_bytes_current_clock_without_refit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            protocol_path, artifacts = root/"protocol.json", root/"artifacts"
            artifacts.mkdir()
            protocol_path.write_text(json.dumps(self.protocol))
            (artifacts/"models.json").write_text(json.dumps(self.model, indent=2))
            verification = {"verified": True, "admission_identity_hash": HASH,
                            "hashes": {"models.json": f.digest(self.model)}}
            (artifacts/"derivation_verification.json").write_text(json.dumps(verification))
            hashes = {name: f.file_sha(artifacts/name) for name in ("models.json", "derivation_verification.json")}
            (artifacts/"run_receipt.json").write_text(json.dumps({"status": "COMPLETE", "hashes": hashes}))
            code = root/"tools/example.py"
            code.parent.mkdir()
            code.write_text("# Synthetic contract only\n")
            binding = root/"evidence/residual_30_18_0/registration/data_code_binding.json"
            binding.parent.mkdir(parents=True)
            binding.write_text(json.dumps({"identity": {"source_hashes": {"tools/example.py": f.file_sha(code)}}}))
            verify = Mock(return_value=self.admission)
            with patch.object(f, "APP", root), patch.dict(sys.modules, {"residual_register": SimpleNamespace(verify=verify)}):
                freeze = f.freeze_from_artifacts(protocol_path, artifacts)
                self.assertEqual(freeze["frozen_at"], NOW)
                self.assertEqual(freeze["model_artifact_sha256"], hashes["models.json"])
                self.assertNotEqual(freeze["model_artifact_sha256"], freeze["model_payload_sha256"])
                self.assertFalse(freeze["orders_allowed"])
                self.assertFalse(freeze["inherited_historical_incidents"])
                (artifacts/"run_receipt.json").write_text(json.dumps({"status": "COMPLETE_WITH_RETAINED_INCIDENTS", "hashes": hashes}))
                incident_freeze = f.freeze_from_artifacts(protocol_path, artifacts)
                self.assertTrue(incident_freeze["inherited_historical_incidents"])
                self.assertFalse(incident_freeze["strategy_approved"])
                self.assertFalse(incident_freeze["historical_economic_gate_approved"])
                (artifacts/"models.json").write_text(json.dumps(self.model))
                with self.assertRaisesRegex(ValueError, "RUN_ARTIFACT_BYTES_MISMATCH"):
                    f.freeze_from_artifacts(protocol_path, artifacts)

    def test_authority_bits_cannot_be_enabled(self):
        self.bundle["orders_allowed"] = True
        self.assertBlocked("BUNDLE_AUTHORITY_FORBIDDEN")

    def test_freeze_constructor_binds_models_and_unavailable_model_fails(self):
        bad = copy.deepcopy(self.model)
        bad["counts"]["available_models"] = 0
        bad["model_payload_sha256"] = f.digest({k: v for k, v in bad.items() if k != "model_payload_sha256"})
        with self.assertRaisesRegex(ValueError, "NO_ADMITTED_MODEL_AVAILABLE"):
            f.create_freeze(bad, self.protocol, {"x.py": HASH}, self.admission, HASH, HASH, OPEN-1)

    def test_write_once_never_replaces_freeze(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/"freeze.json"
            f.write_once(path, self.freeze)
            with self.assertRaises(FileExistsError):
                f.write_once(path, {"forged": True})
            self.assertEqual(json.loads(path.read_text()), self.freeze)


if __name__ == "__main__":
    unittest.main()
