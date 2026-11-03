"""Composite API worker contracts with synthetic receipts, never economic trials."""

from __future__ import annotations

import copy
import json
import subprocess
import unittest
from decimal import Decimal
from pathlib import Path
from typing import Any

from harpoon_quant.roadmap9.integration import process

ROOT = Path(__file__).resolve().parents[2]
BASE = 1_788_800_000_000


def fixture(crypto: bool = False) -> dict[str, Any]:
    script = "process.stdout.write(JSON.stringify(require('./tools/roadmap9_integration_fixture.cjs').fixture(" + str(BASE) + "," + str(crypto).lower() + ")))"
    result = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


class Harness:
    def __init__(self, crypto: bool = False, *, closes_after_first_hour: bool = False):
        self.input = fixture(crypto)
        if closes_after_first_hour:
            self.input["init"]["assets"][0]["schedule"] = [True] + [False] * 71
        self.now = BASE
        self.session: dict[str, Any] | None = None
        self.view: dict[str, Any] = {}
        self.send(self.input["init"])

    def send(self, supplied: dict[str, Any], *, recovery: bool = False) -> dict[str, Any]:
        self.now += 2
        command = {**copy.deepcopy(supplied), "received_at_ms": self.now}
        output = process({"session": self.session, "command": command, "now_ms": self.now,
                          "recovery_required": recovery})
        self.session, self.view = output["session"], output["view"]
        return self.view

    def get(self, *, recovery: bool = False, elapsed: int = 0) -> dict[str, Any]:
        self.now += elapsed
        return process({"session": self.session, "command": None, "now_ms": self.now,
                        "recovery_required": recovery})["view"]

    def reconcile(self, name: str = "reconcile", *, recovery: bool = False) -> dict[str, Any]:
        view = self.get()
        return self.send({"kind": "RECONCILE", "command_id": name, "balances": view["ledger"]["balances"],
                          "inventory": {key: row["execution_net_quantity"] for key, row in
                                        view["inventory_reconciliation"].items()}}, recovery=recovery)

    def ready(self) -> None:
        self.send(self.input["market"])
        self.send(self.input["predictor"])
        self.reconcile()

    def plan(self) -> dict[str, Any]:
        return self.send({"kind": "PLAN", "command_id": "plan", "forecast": self.input["forecast"]})

    def market(self, name: str, price: str) -> dict[str, Any]:
        return self.send({"kind": "MARKET", "command_id": name, "quotes": [{
            "symbol": self.input["symbol"], "bid": price, "ask": price, "event_at_ms": self.now}]})

    def event(self, cid: str, kind: str, label: str, **extra: Any) -> dict[str, Any]:
        return self.send({"kind": "EVENT", "command_id": label,
                          "event": {"kind": kind, "event_id": label, "client_order_id": cid, **extra}})

    def fill_stock(self) -> tuple[str, int]:
        self.ready()
        intent = self.plan()["last_decision"]["simulated_intents"][0]
        cid = intent["client_order_id"]
        self.event(cid, "SUBMITTED", "submitted")
        self.event(cid, "ACK", "ack", broker_order_id="SYNTHETIC-ORDER")
        self.event(cid, "FILL", "fill", qty="2", price="100", liquidity_role="taker",
                   execution_id="execution", executed_at=self.now)
        return cid, intent["deadline_at"]


class CompositeIntegrationTests(unittest.TestCase):
    def test_real_allocator_fill_fee_equity_and_no_authority(self):
        harness = Harness()
        _, deadline = harness.fill_stock()
        self.assertEqual(harness.view["ledger"]["pending_native_fees"]["USD"], "0.210")
        self.assertEqual(Decimal(harness.view["equity_usd"]), Decimal("19999.790"))
        posted = harness.send({"kind": "FEE", "command_id": "fee", "activity_type": "FEE",
            "activity_id": "activity", "fill_id": "execution", "fee_asset": "USD", "total_fee": "0.21"})
        self.assertEqual(Decimal(posted["equity_usd"]), Decimal("19999.79"))
        self.assertEqual(posted["ledger"]["pending_fee_count"], 0)
        ready = harness.reconcile("after-fee")
        self.assertTrue(ready["alive"])
        self.assertEqual(ready["campaigns"]["AAPL"]["original_deadline"], deadline)
        for key in ("execution_allowed", "orders_allowed", "real_fills_present", "financial_acceptance_allowed"):
            self.assertFalse(ready[key])

    def test_late_fill_after_cancel_restart_and_delayed_fees(self):
        harness = Harness()
        harness.ready()
        order = harness.plan()["last_decision"]["simulated_intents"][0]
        cid = order["client_order_id"]
        harness.event(cid, "SUBMITTED", "submitted")
        harness.event(cid, "ACK", "ack", broker_order_id="SYNTHETIC")
        harness.event(cid, "FILL", "partial-1", qty="1", price="100", liquidity_role="taker",
                      execution_id="fill-1", executed_at=harness.now)
        harness.event(cid, "CANCEL_REQUEST", "cancel")
        second_execution_at = harness.now
        cancelled = harness.event(cid, "CANCEL_ACK", "cancel-ack", cumulative_qty="2", executed_at=harness.now)
        self.assertEqual(cancelled["orders"][cid]["remaining_reserved_qty"], "1")
        self.assertFalse(harness.get(recovery=True)["alive"])
        with self.assertRaisesRegex(ValueError, "RECONCILIATION_MISMATCH"):
            harness.reconcile("premature", recovery=True)
        filled = harness.event(cid, "FILL", "partial-2", qty="1", price="100", liquidity_role="taker",
                               execution_id="fill-2", executed_at=second_execution_at, cumulative_qty="2")
        self.assertEqual(filled["orders"][cid]["remaining_reserved_qty"], "0")
        for i, amount in ((1, "0.205"), (2, "0.005")):
            harness.send({"kind": "FEE", "command_id": "fee-" + str(i), "activity_type": "FEE",
                          "activity_id": "fee-" + str(i), "fill_id": "fill-" + str(i),
                          "fee_asset": "USD", "total_fee": amount}, recovery=True)
        result = harness.reconcile("restored-account", recovery=True)
        self.assertTrue(result["alive"])
        self.assertEqual(Decimal(result["equity_usd"]), Decimal("19999.79"))
        self.assertEqual(result["campaigns"]["AAPL"]["original_deadline"], order["deadline_at"])

    def test_native_fee_delta_net_inventory_and_pending_fee_sale_reservation(self):
        harness = Harness(crypto=True)
        harness.send(harness.input["market"])
        harness.reconcile()
        before = harness.get()
        self.assertEqual(before["inventory_reconciliation"]["BTC/USD"]["available_native_quantity"], "0.9975")
        reduced = harness.send({"kind": "REDUCE", "command_id": "reduce", "symbol": "BTC/USD"})
        intent = reduced["last_decision"]["simulated_intents"][0]
        self.assertEqual(Decimal(intent["qty"]), Decimal("0.9975"))
        self.assertEqual(intent["deadline_at"], BASE + 71 * 3_600_000)
        posted = harness.send({"kind": "FEE", "command_id": "native-fee", "activity_type": "CFEE",
            "activity_id": "CFEE-1", "fill_id": "opening-execution", "fee_asset": "BTC", "total_fee": "0.003"})
        row = posted["inventory_reconciliation"]["BTC/USD"]
        self.assertEqual(Decimal(row["gross_fill_quantity"]), 1)
        self.assertEqual(Decimal(row["posted_native_fee_quantity"]), Decimal(".003"))
        self.assertEqual(Decimal(row["execution_net_quantity"]), Decimal(".997"))
        self.assertIn("RESERVED_NATIVE_ASSET_DEFICIT", posted["simulation_blockers"])
        self.assertFalse(posted["alive"])
        restored = harness.get(recovery=True)
        self.assertEqual(restored["ledger"]["balances"]["BTC"], "0.997")
        self.assertEqual(restored["orders"][intent["client_order_id"]]["qty"], intent["qty"])

    def test_predictor_outage_keeps_deterministic_reduction_and_original_deadline(self):
        harness = Harness(crypto=True)
        harness.send(harness.input["market"])
        harness.reconcile()
        off = {**harness.input["predictor"], "ready": False}
        harness.send(off)
        self.assertFalse(harness.get()["simulated_entries_ready"])
        reduction = harness.send({"kind": "REDUCE", "command_id": "reduce", "symbol": "BTC/USD", "qty": "0.5"})
        self.assertEqual(reduction["last_decision"]["simulated_intents"][0]["qty"], "0.5")
        self.assertFalse(reduction["llm_required"])
        with self.assertRaisesRegex(ValueError, "SESSION_ALREADY_INITIALIZED"):
            harness.send({**harness.input["init"], "command_id": "reset"})

    def test_fee_larger_than_provision_preserves_insolvency_not_previous_equity(self):
        harness = Harness()
        harness.fill_stock()
        posted = harness.send({"kind": "FEE", "command_id": "large-fee", "activity_type": "FEE",
            "activity_id": "large-activity", "fill_id": "execution", "fee_asset": "USD", "total_fee": "20001"})
        self.assertEqual(Decimal(posted["ledger"]["balances"]["USD"]), Decimal("-201"))
        self.assertEqual(Decimal(posted["equity_usd"]), Decimal("-1"))
        self.assertIn("NEGATIVE_SETTLED_BALANCE", posted["simulation_blockers"])
        self.assertEqual(harness.get(recovery=True)["ledger"]["balances"], posted["ledger"]["balances"])

    def test_duplicate_command_replays_once_conflict_and_invalid_frame_leave_state(self):
        harness = Harness()
        harness.fill_stock()
        fee = {"kind": "FEE", "command_id": "fee", "activity_type": "FEE", "activity_id": "fee",
               "fill_id": "execution", "fee_asset": "USD", "total_fee": "0.21"}
        harness.send(fee)
        before = copy.deepcopy(harness.session)
        duplicate = harness.send(fee)
        self.assertTrue(duplicate["duplicate_command"])
        self.assertEqual(harness.session, before)
        with self.assertRaisesRegex(ValueError, "CONFLICTING_COMMAND_ID"):
            harness.send({**fee, "total_fee": "1"})
        self.assertEqual(harness.session, before)
        with self.assertRaisesRegex(ValueError, "OFFLINE_FIELDS"):
            harness.send({"kind": "MARKET", "command_id": "bad-market", "quotes": [], "calendar": []})
        self.assertEqual(harness.session, before)

    def test_get_age_and_restart_cannot_relabel_old_receipts_as_alive(self):
        harness = Harness()
        harness.ready()
        before = copy.deepcopy(harness.session)
        self.assertTrue(harness.get()["alive"])
        self.assertFalse(harness.get(recovery=True)["alive"])
        stale = harness.get(elapsed=15001)
        self.assertFalse(stale["alive"])
        self.assertIn("STALE_MARKET_EVENT_AT", stale["simulation_blockers"])
        self.assertEqual(harness.session, before)

    def test_forecast_binding_and_authority_escalation_are_rejected(self):
        harness = Harness()
        harness.ready()
        before = copy.deepcopy(harness.session)
        for field, value in (("for_decision_at", "2099-01-01T00:00:00Z"), ("execution_allowed", True)):
            forecast = {**harness.input["forecast"], field: value}
            with self.assertRaises(ValueError):
                harness.send({"kind": "PLAN", "command_id": "forged-" + field, "forecast": forecast})
            self.assertEqual(harness.session, before)
        with self.assertRaisesRegex(ValueError, "AUTHORITY_OR_SNAPSHOT"):
            harness.send({"kind": "PREDICTOR", "command_id": "llm", "llm": {"approve": True}})

    def test_native_fee_correction_is_delta_once_after_restart(self):
        harness = Harness(crypto=True)
        fee = {"kind": "FEE", "command_id": "first-fee", "activity_type": "CFEE", "activity_id": "first-fee",
               "fill_id": "opening-execution", "fee_asset": "BTC", "total_fee": ".003"}
        harness.send(fee)
        correction = {**fee, "command_id": "correction", "activity_id": "correction",
                      "corrects_activity_id": "first-fee", "total_fee": ".002"}
        result = harness.send(correction, recovery=True)
        self.assertEqual(Decimal(result["inventory_reconciliation"]["BTC/USD"]["execution_net_quantity"]), Decimal(".998"))
        harness.send(correction, recovery=True)
        self.assertEqual(harness.get()["ledger"]["balances"]["BTC"], "0.998")

    def test_calendar_slots_are_not_reanchored_by_market_or_status_refresh(self):
        harness = Harness(crypto=True, closes_after_first_hour=True)
        harness.ready()
        closes_at = BASE + 2 + 3_600_000
        harness.now = closes_at - 10
        harness.market("just-before-close", "100")
        harness.reconcile("just-before-close-account")
        harness.now = closes_at - 1
        view = harness.get()
        self.assertTrue(view["alive"])
        self.assertEqual(view["valid_until_ms"], closes_at - 1)
        harness.now = closes_at
        self.assertFalse(harness.get()["alive"])
        market = copy.deepcopy(harness.input["market"])
        market["command_id"] = "new-market"
        market["quotes"][0]["event_at_ms"] = harness.now
        harness.send(market)
        harness.reconcile("new-reconcile")
        self.assertIn("CALENDAR_CLOSED_OR_OUTSIDE_COVERAGE", harness.view["simulation_blockers"])
        self.assertEqual(harness.view["health"]["owned_inventory_management"], "RECONCILE_ONLY")
        before = copy.deepcopy(harness.session)
        with self.assertRaisesRegex(ValueError, "REDUCTION_RECONCILE_ONLY"):
            harness.send({"kind": "REDUCE", "command_id": "closed-reduce", "symbol": "BTC/USD"})
        self.assertEqual(harness.session, before)

    def test_changed_cost_or_calendar_contract_stays_blocked_after_balance_reconciliation(self):
        for contract in ("COST", "CALENDAR"):
            harness = Harness()
            harness.ready()
            view = harness.send({"kind": "CONTRACT_CHANGE", "command_id": "change", "symbol": "AAPL",
                                 "contract": contract, "observed_hash": "f" * 64})
            self.assertIn("CONTRACT_CHANGED:" + contract + ":AAPL", view["simulation_blockers"])
            self.assertFalse(view["alive"])
            harness.reconcile("balance-only")
            with self.assertRaisesRegex(ValueError, "OFFLINE_PLAN_NOT_READY"):
                harness.plan()

    def test_proposal_deadline_is_used_and_opening_campaigns_cannot_overlap(self):
        harness = Harness()
        harness.ready()
        view = harness.plan()
        result = view["last_decision"]
        deadline = result["simulated_intents"][0]["deadline_at"]
        from datetime import datetime
        proposed = result["decision"]["actions"][0]["proposed_new_deadline"]
        self.assertEqual(deadline, int(datetime.fromisoformat(proposed).timestamp() * 1000))
        opening = fixture(crypto=True)["init"]
        extra = copy.deepcopy(opening["opening_events"][0])
        extra.update(event_id="second-intent", client_order_id="second-buy", campaign_id="second-campaign",
                     at=BASE, opened_at=BASE-1000, deadline_at=BASE+72*3_600_000)
        opening["opening_events"].append(extra)
        with self.assertRaisesRegex(ValueError, "CAMPAIGN_RESET_OR_OVERLAP"):
            process({"session": None, "command": {**opening, "received_at_ms": BASE+1},
                     "now_ms": BASE+1, "recovery_required": False})

    def test_expired_exposure_blocks_fresh_account_and_keeps_receipts_and_deadline(self):
        harness = Harness()
        _, deadline = harness.fill_stock()
        harness.send({"kind": "FEE", "command_id": "fee", "activity_type": "FEE", "activity_id": "fee",
                      "fill_id": "execution", "fee_asset": "USD", "total_fee": "0.21"})
        harness.reconcile("before-expiry")
        harness.now = deadline + 1
        market = copy.deepcopy(harness.input["market"])
        market["command_id"] = "fresh-after-expiry"
        market["quotes"][0]["event_at_ms"] = harness.now
        harness.send(market)
        view = harness.reconcile("fresh-account-after-expiry")
        self.assertFalse(view["alive"])
        self.assertFalse(view["simulated_entries_ready"])
        self.assertEqual(view["health"]["owned_inventory_management"], "RECONCILE_ONLY")
        self.assertIn("CAMPAIGN_DEADLINE_EXPIRED_WITH_EXPOSURE", view["simulation_blockers"])
        self.assertEqual(view["expired_campaigns"][0]["original_deadline"], deadline)
        self.assertEqual(Decimal(view["expired_campaigns"][0]["net_inventory"]), 2)
        before = copy.deepcopy(harness.session)
        with self.assertRaisesRegex(ValueError, "RECONCILE_ONLY"):
            harness.send({"kind": "REDUCE", "command_id": "late-reduce", "symbol": "AAPL"})
        with self.assertRaisesRegex(ValueError, "PLAN_NOT_READY"):
            harness.send({"kind": "PLAN", "command_id": "late-plan", "forecast": harness.input["forecast"]})
        self.assertEqual(harness.session, before)
        correction = harness.send({"kind": "FEE", "command_id": "late-fee-correction", "activity_type": "FEE",
            "activity_id": "late-correction", "corrects_activity_id": "fee", "fill_id": "execution",
            "fee_asset": "USD", "total_fee": "0.22"})
        self.assertEqual(Decimal(correction["equity_usd"]), Decimal("19999.78"))
        self.assertEqual(correction["campaigns"]["AAPL"]["original_deadline"], deadline)

    def test_expired_unfilled_intention_is_exposure_even_with_zero_inventory(self):
        harness = Harness()
        harness.ready()
        intent = harness.plan()["last_decision"]["simulated_intents"][0]
        harness.now = intent["deadline_at"]
        view = harness.get()
        self.assertIn("CAMPAIGN_DEADLINE_EXPIRED_WITH_EXPOSURE", view["simulation_blockers"])
        self.assertEqual(Decimal(view["expired_campaigns"][0]["net_inventory"]), 0)
        self.assertEqual(view["expired_campaigns"][0]["pending_order_ids"], [intent["client_order_id"]])

    def test_campaign_validity_is_exclusive_and_model_validity_only_limits_entries(self):
        harness = Harness()
        _, deadline = harness.fill_stock()
        harness.send({"kind": "FEE", "command_id": "fee", "activity_type": "FEE", "activity_id": "fee",
                      "fill_id": "execution", "fee_asset": "USD", "total_fee": "0.21"})
        harness.now = deadline - 10
        harness.market("just-before-deadline", "100")
        harness.reconcile("just-before-deadline-reconcile")
        harness.now = deadline - 1
        view = harness.get()
        self.assertTrue(view["alive"])
        self.assertEqual(view["valid_until_ms"], deadline - 1)
        self.assertEqual(view["campaign_exposures"][0]["original_deadline"], deadline)
        self.assertEqual(view["expired_campaigns"], [])
        harness.now = deadline
        self.assertFalse(harness.get()["alive"])

        fresh = Harness()
        fresh.ready()
        age_limit = 168 * 3_600_000
        expiry = fresh.now + 10
        fresh.send({"kind": "PREDICTOR", "command_id": "almost-old", "ready": True,
                    "model_trained_at_ms": expiry - age_limit, "latest_label_at_ms": expiry - age_limit})
        fresh.now = expiry
        view = fresh.get()
        self.assertTrue(view["simulated_entries_ready"])
        self.assertEqual(view["entry_valid_until_ms"], expiry)
        self.assertGreater(view["valid_until_ms"], expiry)
        fresh.now += 1
        expired = fresh.get()
        self.assertTrue(expired["alive"])
        self.assertFalse(expired["simulated_entries_ready"])
        self.assertEqual(expired["health"]["owned_inventory_management"], "REDUCTION_READY")

    def test_daily_loss_uses_pre_receipt_utc_anchor_after_profitable_prior_day(self):
        harness = Harness()
        harness.fill_stock()
        harness.send({"kind": "FEE", "command_id": "fee", "activity_type": "FEE", "activity_id": "fee",
                      "fill_id": "execution", "fee_asset": "USD", "total_fee": "0.21"})
        prior = harness.market("prior-day-profit", "1100")
        self.assertEqual(Decimal(prior["equity_usd"]), Decimal("21999.79"))
        harness.now = (harness.now // 86_400_000 + 1) * 86_400_000
        harness.market("next-day-loss", "850")
        view = harness.reconcile("next-day-account")
        risk = view["daily_risk"]
        self.assertEqual(Decimal(risk["anchor_equity_usd"]), Decimal("21999.79"))
        self.assertEqual(Decimal(risk["daily_pnl_usd"]), Decimal("-500"))
        self.assertGreater(Decimal(view["equity_usd"]), 20000)
        self.assertGreater(risk["daily_loss_fraction"], .02)
        self.assertLess(risk["daily_loss_fraction"], .08)
        self.assertIn("LIMIT_DAILY_LOSS_FRACTION", view["simulation_blockers"])
        self.assertNotIn("LIMIT_DRAWDOWN_FRACTION", view["simulation_blockers"])
        self.assertFalse(view["simulated_entries_ready"])
        with self.assertRaisesRegex(ValueError, "PLAN_NOT_READY"):
            harness.send({"kind": "PLAN", "command_id": "daily-limit-plan", "forecast": harness.input["forecast"]})
        self.assertEqual(harness.get(recovery=True)["daily_risk"], risk)

    def test_first_quote_overnight_gap_is_loss_and_get_cannot_reset_anchor(self):
        harness = Harness()
        harness.fill_stock()
        harness.send({"kind": "FEE", "command_id": "fee", "activity_type": "FEE", "activity_id": "fee",
                      "fill_id": "execution", "fee_asset": "USD", "total_fee": "0.21"})
        prior = harness.market("before-gap", "1100")
        harness.now = (harness.now // 86_400_000 + 1) * 86_400_000
        before_quote = harness.get()
        self.assertEqual(before_quote["daily_risk"]["anchor_equity_usd"], prior["equity_usd"])
        gap = harness.market("first-overnight-quote", "800")
        self.assertEqual(Decimal(gap["daily_risk"]["daily_pnl_usd"]), Decimal("-600"))
        self.assertGreater(gap["daily_risk"]["daily_loss_fraction"], .02)
        self.assertEqual(gap["daily_risk"]["high_water_equity_usd"], prior["equity_usd"])
        harness.market("later-same-day-quote", "900")
        later = harness.get(recovery=True)
        self.assertEqual(later["daily_risk"]["anchor_equity_usd"], prior["equity_usd"])
        self.assertEqual(Decimal(later["daily_risk"]["daily_pnl_usd"]), Decimal("-400"))
        before = copy.deepcopy(harness.session)
        with self.assertRaisesRegex(ValueError, "OFFLINE_FIELDS"):
            harness.send({**harness.input["predictor"], "command_id": "forge-anchor", "daily_anchor_equity_usd": "1"})
        self.assertEqual(harness.session, before)

    def test_missing_prior_mark_and_insolvency_are_explicit_daily_risk_blocks(self):
        harness = Harness(crypto=True)
        harness.now = (harness.now // 86_400_000 + 1) * 86_400_000
        view = harness.market("first-ever-mark-next-day", "50")
        self.assertIsNone(view["daily_risk"]["anchor_equity_usd"])
        self.assertIsNone(view["daily_risk"]["daily_loss_fraction"])
        self.assertIn("DAILY_RISK_ANCHOR_UNAVAILABLE", view["simulation_blockers"])
        self.assertEqual(harness.get(recovery=True)["daily_risk"], view["daily_risk"])
        harness = Harness()
        harness.fill_stock()
        view = harness.send({"kind": "FEE", "command_id": "insolvent-fee", "activity_type": "FEE",
            "activity_id": "insolvent-fee", "fill_id": "execution", "fee_asset": "USD", "total_fee": "20001"})
        self.assertIn("RISK_EQUITY_NONPOSITIVE", view["simulation_blockers"])
        self.assertIsNone(view["daily_risk"]["daily_loss_fraction"])

    def test_journal_capacity_128_blocks_readiness_and_preserves_inventory_on_129(self):
        harness = Harness()
        harness.fill_stock()
        harness.send({"kind": "FEE", "command_id": "fee", "activity_type": "FEE", "activity_id": "fee",
                      "fill_id": "execution", "fee_asset": "USD", "total_fee": "0.21"})
        harness.reconcile("before-capacity")
        while harness.view["journal_command_count"] < 127:
            harness.send({**harness.input["predictor"],
                          "command_id": "capacity-" + str(harness.view["journal_command_count"])})
        self.assertTrue(harness.view["alive"])
        self.assertTrue(harness.view["simulated_entries_ready"])
        inventory = copy.deepcopy(harness.view["inventory_reconciliation"])
        ledger = copy.deepcopy(harness.view["ledger"])
        last = {**harness.input["predictor"], "command_id": "capacity-128"}
        full = harness.send(last)
        self.assertEqual(full["journal_command_count"], 128)
        self.assertFalse(full["alive"])
        self.assertFalse(full["simulated_entries_ready"])
        self.assertEqual(full["health"]["owned_inventory_management"], "RECONCILE_ONLY")
        self.assertIn("OFFLINE_JOURNAL_CAPACITY_EXHAUSTED", full["simulation_blockers"])
        self.assertEqual(full["inventory_reconciliation"], inventory)
        self.assertEqual(full["ledger"], ledger)
        before = copy.deepcopy(harness.session)
        with self.assertRaisesRegex(ValueError, "OFFLINE_JOURNAL_BOUND"):
            harness.send({**harness.input["predictor"], "command_id": "capacity-129"})
        self.assertEqual(harness.session, before)
        duplicate = harness.send(last)
        self.assertTrue(duplicate["duplicate_command"])
        self.assertFalse(duplicate["simulated_entries_ready"])
        self.assertEqual(harness.session, before)
        restarted = harness.get(recovery=True)
        self.assertEqual(restarted["inventory_reconciliation"], inventory)
        self.assertEqual(restarted["ledger"], ledger)
        self.assertIn("OFFLINE_JOURNAL_CAPACITY_EXHAUSTED", restarted["simulation_blockers"])


if __name__ == "__main__":
    unittest.main()
