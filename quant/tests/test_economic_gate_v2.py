from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from examples.economic_gate.make_fixture import make_fixture, write_json
from harpoon_quant.economic_gate import (
    artifact_reference,
    evaluate_gate,
    register_protocol,
    seal_protocol,
)
from harpoon_quant.economic_gate_v2 import (
    ROLES,
    _risk,
    summarize_policy,
    validate_protocol,
    verify_history,
)


def iso(ms: float) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).isoformat()


class EventRiskTests(unittest.TestCase):
    def setUp(self) -> None:
        self.start = int(datetime(2030, 1, 2, 14, tzinfo=UTC).timestamp() * 1000)
        self.p = {"initial_equity_usd": 100, "universe": ["X"],
                  "period": {"test_start": iso(self.start), "test_end": iso(self.start + 2000)},
                  "evaluation_sessions": [{"session_id": "2030-01-02", "start_at": iso(self.start), "end_at": iso(self.start + 2000)}],
                  "max_drawdown_fraction": 0.1, "max_gross_exposure_fraction": 0.5, "horizon_hours": 72}

    def series(self, equities: list[float], inventories: list[float] | None = None, costs: list[float] | None = None, role: str = "SVR") -> dict:
        inventories = inventories or [0] * len(equities)
        costs = costs or [0] * len(equities)
        rows = []
        for i, (equity, inventory, cost) in enumerate(zip(equities, inventories, costs, strict=True)):
            rows.append({"event_id": str(i), "at": self.start + i * 1000, "session_id": "2030-01-02",
                         "cash_usd": equity - inventory, "inventory_value_usd": inventory,
                         "account_equity_usd": equity, "economic_equity_usd": equity - cost,
                         "cumulative_external_cost_usd": cost, "cumulative_fees_usd": 0, "external_flow_usd": 0,
                         "positions": [] if not inventory else [{"symbol": "X", "qty": "1", "market_value": str(inventory)}]})
        return {"role": role, "initial_equity_usd": 100, "events": rows, "maximum_observed_holding_hours": 1,
                "stale_terminal_valuation_symbols": [], "execution_io_failure_count": 0}

    def test_intraday_drawdown_is_not_hidden_by_profitable_close(self) -> None:
        row = summarize_policy(self.series([100, 60, 102]), self.p)
        self.assertEqual(row["net_pnl_usd"], 2)
        self.assertAlmostEqual(row["maximum_drawdown_fraction"], 0.4)
        self.assertIn("EVENT_DRAWDOWN_LIMIT_EXCEEDED", _risk(row, self.p))

    def test_intraday_insolvency_is_not_clipped_after_recovery(self) -> None:
        row = summarize_policy(self.series([100, -1, 102]), self.p)
        self.assertTrue(row["insolvency"])
        self.assertIn("INSOLVENCY_NOT_CLIPPED", _risk(row, self.p))

    def test_peak_exposure_and_duration_survive_a_flat_close(self) -> None:
        row = summarize_policy(self.series([100, 100, 100], [0, 120, 0]), self.p)
        self.assertAlmostEqual(row["maximum_gross_exposure_fraction"], 1.2)
        self.assertAlmostEqual(row["mean_gross_exposure_fraction"], 0.6)
        self.assertIn("EVENT_EXPOSURE_LIMIT_EXCEEDED", _risk(row, self.p))

    def test_positive_nav_cannot_pay_cost_with_unexecuted_sale(self) -> None:
        row = summarize_policy(self.series([100, 100, 102], [0, 95, 97], [0, 6, 6]), self.p)
        self.assertGreater(row["final_equity_usd"], 0)
        self.assertTrue(row["economic_cash_unfunded"])
        self.assertIn("EXTERNAL_COST_FINANCING_NOT_AVAILABLE", _risk(row, self.p))

    def test_cash_is_separate_from_native_control(self) -> None:
        native = self.series([100, 100, 102], [0, 10, 20], role="NATIVE")
        self.assertEqual(summarize_policy(native, self.p)["terminal_inventory"][0]["qty"], "1")
        native["role"] = "CASH"
        with self.assertRaisesRegex(ValueError, "CASH_CONTROL_HAS_TRADING_OR_FINANCING"):
            summarize_policy(native, self.p)

    def test_same_costs_do_not_create_artificial_cash_interest(self) -> None:
        row = summarize_policy(self.series([100, 100, 100], costs=[0, 1, 2], role="CASH"), self.p)
        self.assertEqual(row["net_pnl_usd"], -2)
        self.assertEqual(row["external_cost_usd"], 2)
        self.assertEqual(row["fees_usd"], 0)

    def test_cost_disappearance_or_inventory_mismatch_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "EVENT_COST_FLOW_SCOPE"):
            summarize_policy(self.series([100, 100, 100], costs=[0, 2, 1]), self.p)
        item = self.series([100, 100, 100], [0, 10, 10])
        item["events"][-1]["positions"][0]["market_value"] = "11"
        with self.assertRaisesRegex(ValueError, "EVENT_INVENTORY_IDENTITY"):
            summarize_policy(item, self.p)

    def test_reserve_must_be_visible_in_original_buying_power(self) -> None:
        item = self.series([100, 100, 102], [0, 10, 10], [0, 1, 2])
        item["operating_cash_reserve"] = {"amount_usd": 3, "known_at": self.start - 1, "method": "FIXED_INITIAL_CASH_RESERVE"}
        for row in item["events"]:
            row.update(operating_cash_reserve_usd=3, operating_reserve_known_at=self.start - 1,
                       buying_power_usd=row["cash_usd"] - 3, non_marginable_buying_power_usd=row["cash_usd"] - 3)
        self.assertTrue(summarize_policy(item, self.p)["operating_reserve_verified"])
        item["events"][-1]["buying_power_usd"] += 3
        with self.assertRaisesRegex(ValueError, "OPERATING_RESERVE_NOT_REEXECUTED_IN_ACCOUNT"):
            summarize_policy(item, self.p)

    def test_reserve_deficit_and_late_knowledge_cannot_be_hidden(self) -> None:
        item = self.series([100, 100, 102], [0, 99, 99], [0, 1, 2])
        item["operating_cash_reserve"] = {"amount_usd": 3, "known_at": self.start - 1, "method": "FIXED_INITIAL_CASH_RESERVE"}
        for row in item["events"]:
            row.update(operating_cash_reserve_usd=3, operating_reserve_known_at=self.start - 1,
                       buying_power_usd=row["cash_usd"] - 3, non_marginable_buying_power_usd=row["cash_usd"] - 3)
        self.assertIn("RESERVED_CASH_DEFICIT", _risk(summarize_policy(item, self.p), self.p))
        item["operating_cash_reserve"]["known_at"] = self.start + 1
        with self.assertRaisesRegex(ValueError, "OPERATING_RESERVE_NOT_CAUSAL_OR_UNFUNDED"):
            summarize_policy(item, self.p)

    def test_invented_session_and_early_termination_are_rejected(self) -> None:
        item = self.series([100, 100, 102])
        item["events"][1]["session_id"] = "2030-01-03"
        with self.assertRaisesRegex(ValueError, "V2_PAIRED_SESSION_CALENDAR_MISMATCH"):
            summarize_policy(item, self.p)
        item = self.series([100, 100, 102])
        item["events"].pop()
        with self.assertRaisesRegex(ValueError, "TERMINAL_EVENT_MUST_REACH_TEST_END"):
            summarize_policy(item, self.p)


class EconomicV2IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.app = Path(__file__).resolve().parents[2]
        env = {**os.environ, "HARPOON_QUANT_PYTHON": sys.executable}
        run = subprocess.run(["node", str(cls.app / "tools/fixtures/level5_fixture.cjs"), str(cls.root)],
                             capture_output=True, text=True, timeout=120, check=False, env=env)
        if run.returncode:
            raise AssertionError(run.stderr)
        cls.derived = json.loads((cls.root / "derived.json").read_text())

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def setUp(self) -> None:
        self.test_temp = tempfile.TemporaryDirectory()
        self.base = Path(self.test_temp.name)
        # Original per-test fixtures are synthetic and do not consume journals.
        self.protocol, self.evidence = make_fixture(self.base)
        b = self.derived["bindings"]
        start, end = b["period"]["start_at"], b["period"]["end_at"]
        first_date = datetime.fromtimestamp(start / 1000, UTC)
        self.protocol.update(schema="HARPOON_ECONOMIC_PROTOCOL_2", policy_roles=ROLES,
                             exposure_measure="EVENT_INTERVAL_TIME_WEIGHTED_LAST_OBSERVED",
                             external_cost_method="VERIFIED_LEDGER_ACCRUAL_TIMESTAMPS",
                             minimum_delta_native_log_growth=0.0, horizon_hours=72,
                             created_at=(first_date - timedelta(days=180)).isoformat(),
                             period={"train_end": (first_date - timedelta(days=170)).isoformat(),
                                     "validation_start": (first_date - timedelta(days=160)).isoformat(),
                                     "validation_end": (first_date - timedelta(days=100)).isoformat(),
                                     "test_start": iso(start), "test_end": iso(end)},
                             evaluation_sessions=[{"session_id": self.derived["policies"]["SVR"]["events"][-1]["session_id"],
                                                   "start_at": iso(start), "end_at": iso(end)}],
                             stress_scenarios=[{"id": "COST_STRESS", "execution_overrides": self.derived["stress"][0]["changes"],
                                                "minimum_net_pnl_usd": 0, "minimum_delta_ridge_usd": 0, "max_drawdown_fraction": 0.1}])
        self.protocol.pop("minimum_delta_c0_log_growth", None)
        for key in ("policy_hash", "risk_hash", "cost_hash", "code_hash", "universe", "initial_equity_usd"):
            self.protocol[key] = b[key]
        self.protocol = seal_protocol(self.protocol)
        self.registry = self.base / "v2_registration.jsonl"
        registered = (first_date - timedelta(days=90)).isoformat()
        record = register_protocol(self.protocol, self.registry, registered)
        generated = iso(end + 1000)
        history = json.loads((self.base / "search_history.json").read_text())
        history["known_through"] = generated
        write_json(self.base / "search_history.json", history)
        # The derived request lives in another temporary fixture directory.
        # Copy its small JSON sources to the root containing the evidence refs.
        for source in self.root.iterdir():
            (self.base / source.name).write_bytes(source.read_bytes())
        self.evidence = {"schema": "HARPOON_ECONOMIC_EVIDENCE_2", "protocol_hash": self.protocol["protocol_hash"],
                         "execution_allowed": False, "liveApproved": False, "generated_at": generated,
                         "provenance": {"first_final_data_access_at": iso(start), "prior_final_test_uses": []},
                         "preregistration": {"journal": artifact_reference(self.registry, self.base), "record_hash": record["record_hash"]},
                         "search_history": artifact_reference(self.base / "search_history.json", self.base),
                         "history_manifest": None,
                         "derivation_request": artifact_reference(self.base / "level5_request.json", self.base)}

    def tearDown(self) -> None:
        self.test_temp.cleanup()

    def test_real_reexecuted_synthetic_pipeline_has_four_policies_and_stress_but_no_approval(self) -> None:
        report = evaluate_gate(self.protocol, self.evidence, artifact_root=self.base)
        self.assertEqual(report["software_validators"]["status"], "PASS", report)
        self.assertEqual(set(report["policies"]), set(ROLES))
        self.assertEqual(len(report["stress"]), 1)
        self.assertTrue(report["derivation"]["complete_derived_comparison"])
        self.assertFalse(report["candidate_for_forward_validation"])
        self.assertFalse(report["level5_criterion_met"])
        self.assertFalse(report["financial_acceptance_allowed"])
        self.assertIn("SYNTHETIC_IS_NOT_FINANCIAL_EVIDENCE", report["financial_blockers"])
        self.assertNotIn("EXTERNAL_COST_CAPITAL_RESERVE_PARITY_UNVERIFIED", report["financial_blockers"])
        self.assertEqual(report["external_cost_financing"]["reserve_effect_on_original_decisions"], "FIXED_RESERVE_REEXECUTED_IN_ALL_POLICIES")
        self.assertEqual(report["score"], 3)

    def test_legacy_cash_role_cannot_be_smuggled_into_v2(self) -> None:
        p = copy.deepcopy(self.protocol)
        p["policy_roles"]["NATIVE"] = "CASH"
        with self.assertRaisesRegex(ValueError, "EXPLICIT_V2_POLICY_ROLES_REQUIRED"):
            validate_protocol(seal_protocol(p))

    def test_no_boolean_or_user_curve_can_replace_reexecution(self) -> None:
        e = {**self.evidence, "curves": {"SVR": {"net_pnl": 99999}}}
        report = evaluate_gate(self.protocol, e, artifact_root=self.base)
        self.assertEqual(report["software_validators"]["status"], "BLOCKED")
        self.assertIn("CALLER_CURVES_NOT_ACCEPTED", report["software_validators"]["errors"])

    def test_protocol_cannot_be_registered_at_test_start(self) -> None:
        self.registry.unlink()
        r = register_protocol(self.protocol, self.registry, self.protocol["period"]["test_start"])
        self.evidence["preregistration"] = {"journal": artifact_reference(self.registry, self.base), "record_hash": r["record_hash"]}
        report = evaluate_gate(self.protocol, self.evidence, artifact_root=self.base)
        self.assertIn("V2_TEST_MUST_START_AFTER_REGISTRATION", report["software_validators"]["errors"])

    def test_unknown_history_and_unbound_family_cannot_be_presented_as_complete(self) -> None:
        manifest = {"schema": "HARPOON_RESEARCH_HISTORY_MANIFEST_2", "global_deduplicated_total": 23,
                    "sources": {k: {"path": "invented", "sha256": "0" * 64} for k in
                                ("quant_journal", "ultimate_registry", "tp32_report", "prior_readiness")}}
        write_json(self.base / "manifest.json", manifest)
        with self.assertRaisesRegex(ValueError, "PRIOR_AUDIT_RELEASE_ANCHOR_MISMATCH"):
            verify_history(artifact_reference(self.base / "manifest.json", self.base), self.base, self.protocol)

    def test_stress_configuration_is_part_of_frozen_protocol(self) -> None:
        p = copy.deepcopy(self.protocol)
        p["stress_scenarios"][0]["execution_overrides"]["slippage_bps"] += 1
        with self.assertRaisesRegex(ValueError, "V2_PROTOCOL_HASH_OR_SCHEMA"):
            validate_protocol(p)
        p = copy.deepcopy(self.protocol)
        p["stress_scenarios"].append(p["stress_scenarios"][0])
        with self.assertRaisesRegex(ValueError, "ONE_PREREGISTERED_STRESS"):
            validate_protocol(seal_protocol(p))


if __name__ == "__main__":
    unittest.main()
