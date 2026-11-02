"""Synthetic-only financial invariants, fault injections and causal integration."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harpoon_quant.core import timestamp
from harpoon_quant.frontier.contracts import Settings
from harpoon_quant.frontier.paths import fit, validate_paths
from harpoon_quant.multiasset import calibrate_fills
from harpoon_quant.synthetic9 import ORIGIN
from harpoon_quant.synthetic9.bank import run_account, state_for
from harpoon_quant.synthetic9.events import link, number, unlink
from harpoon_quant.synthetic9.execution import calibration, event, simulate_order
from harpoon_quant.synthetic9.faults import (
    T0,
    account_from,
    fault_matrix,
    fixture_order,
)
from harpoon_quant.synthetic9.ledger import Ledger
from harpoon_quant.synthetic9.market import WORLDS, quotes, world
from harpoon_quant.synthetic9.review import audit_account
from harpoon_quant.synthetic9.storage import (
    load_gzip,
    sha256,
    verify_manifest,
    write_gzip,
)

ROOT = Path(__file__).resolve().parents[2]


def bought(force="FULL", cash=20000):
    ledger = Ledger(cash)
    decision, order = fixture_order()
    events = [decision, *simulate_order(order, 73, force=force)]
    for body in events:
        ledger.apply(body)
    return ledger, events


def mark(ledger, events, *, at=T0 + 10000, bid=101.0):
    body = event(
        "MARK", "last-mark", at, quotes={"AAPL": {"bid": bid, "ask": bid + 0.02}}
    )
    ledger.apply(body)
    events.append(body)
    return account_from(ledger, events)


def sell_order(ledger, identity="SELL", qty=2.0, symbol="AAPL"):
    at = ledger.now + 1000
    quote = {"bid": 89.99, "ask": 90.01, "quote_at": at, "received_at": at}
    decision = event(
        "DECISION",
        identity + "D",
        at,
        decision_id=identity + "D",
        quotes={symbol: quote},
    )
    order = event(
        "SUBMIT",
        identity,
        at + 1,
        order_id=identity,
        decision_id=identity + "D",
        symbol=symbol,
        book="equity",
        side="sell",
        qty=qty,
        decision_bid=quote["bid"],
        decision_ask=quote["ask"],
        limit_price=None,
        fee_bps=2.0,
        fixed_fee_usd=0.01,
    )
    return decision, order


class ExecutionLedgerTests(unittest.TestCase):
    def test_known_cash_and_native_units(self):
        ledger, events = bought()
        fill = events[-1]
        self.assertEqual(ledger.quantity("AAPL"), 2)
        self.assertAlmostEqual(
            ledger.cash, 20000 - 2 * fill["price"] - fill["fee_usd"], places=7
        )
        self.assertTrue(audit_account(mark(ledger, events))["verified"])

    def test_partial_cancel_has_only_received_quantity(self):
        ledger, events = bought("PARTIAL_CANCEL")
        self.assertEqual(ledger.quantity("AAPL"), 1)
        self.assertEqual(ledger.reserved(), 0)
        self.assertTrue(audit_account(mark(ledger, events))["verified"])

    def test_cancel_ack_keeps_reserve_for_announced_late_fill(self):
        decision, order = fixture_order()
        events = [decision, *simulate_order(order, 73, force="LATE_FILL")]
        ledger = Ledger()
        for body in events[:-1]:
            ledger.apply(body)
        self.assertEqual(ledger.quantity("AAPL"), 1)
        self.assertGreater(ledger.reserved(), 105)
        ledger.apply(events[-1])
        self.assertEqual(ledger.quantity("AAPL"), 2)
        self.assertEqual(ledger.reserved(), 0)

    def test_fixed_order_fee_is_paid_once_on_two_fills(self):
        ledger, events = bought("LATE_FILL")
        fills = [e for e in events if e["kind"] == "FILL"]
        self.assertEqual(len(fills), 2)
        self.assertAlmostEqual(
            ledger.fees, 2 * fills[0]["price"] * 0.0002 + 0.01, places=7
        )

    def test_duplicate_delivery_is_idempotent_and_conflict_rejected(self):
        ledger, events = bought()
        cash = ledger.cash
        ledger.apply(copy.deepcopy(events[-1]))
        self.assertEqual(cash, ledger.cash)
        self.assertEqual(ledger.duplicate_deliveries, 1)
        corrupt = copy.deepcopy(events[-1])
        corrupt["fee_usd"] += 1
        with self.assertRaisesRegex(ValueError, "CONFLICTING_DUPLICATE"):
            ledger.apply(corrupt)

    def test_halt_never_produces_a_fill(self):
        decision, order = fixture_order()
        ledger = Ledger()
        for body in [
            decision,
            *simulate_order(order, 73, force="FULL", open_market=False),
        ]:
            ledger.apply(body)
        self.assertEqual(ledger.quantity("AAPL"), 0)
        self.assertEqual(ledger.cash, 20000)

    def test_pending_sale_cannot_fund_purchase(self):
        ledger = Ledger()
        decision, order = fixture_order(qty=190.0)
        for body in [decision, *simulate_order(order, 73, force="FULL")]:
            ledger.apply(body)
        decision, sell = sell_order(ledger, qty=190.0)
        ledger.apply(decision)
        ledger.apply(sell)
        buy = copy.deepcopy(order)
        buy.update(
            id="NEWBUY",
            order_id="NEWBUY",
            decision_id=decision["decision_id"],
            at=sell["at"] + 1,
            occurred_at=sell["at"] + 1,
            qty=20.0,
            decision_bid=89.99,
            decision_ask=90.01,
        )
        with self.assertRaisesRegex(ValueError, "UNCONFIRMED_SALES_NOT_FUNDING"):
            ledger.apply(buy)

    def test_pending_sell_reserves_inventory(self):
        ledger, _ = bought()
        decision, order = sell_order(ledger)
        ledger.apply(decision)
        ledger.apply(order)
        duplicate = copy.deepcopy(order)
        duplicate.update(
            id="DOUBLESELL",
            order_id="DOUBLESELL",
            at=order["at"] + 1,
            occurred_at=order["at"] + 1,
        )
        with self.assertRaisesRegex(ValueError, "NO_SHORT_OR_DOUBLE_SELL"):
            ledger.apply(duplicate)

    def test_roundtrip_loss_and_common_expense_survive_reconciliation(self):
        ledger, events = bought()
        decision, order = sell_order(ledger)
        for body in [decision, *simulate_order(order, 81, force="FULL")]:
            ledger.apply(body)
            events.append(body)
        expense = event("OVERHEAD", "COST", ledger.now + 1, usd=1)
        ledger.apply(expense)
        events.append(expense)
        packet = mark(ledger, events, at=ledger.now + 1, bid=90)
        self.assertEqual(ledger.quantity("AAPL"), 0)
        self.assertLess(ledger.cash, 19980)
        self.assertTrue(audit_account(packet)["verified"])

    def test_closed_campaign_can_start_an_actual_new_campaign(self):
        ledger, _ = bought()
        decision, order = sell_order(ledger)
        for body in [decision, *simulate_order(order, 81, force="FULL")]:
            ledger.apply(body)
        later = ledger.now + 1000
        d, o = fixture_order()
        d.update(id="D2", decision_id="D2", at=later, occurred_at=later)
        d["quotes"]["AAPL"].update(quote_at=later, received_at=later)
        o.update(
            id="O2",
            order_id="O2",
            decision_id="D2",
            at=later + 1,
            occurred_at=later + 1,
            campaign_id="SECOND",
            deadline_at=later + 72 * 3600000,
        )
        for body in [d, *simulate_order(o, 73, force="FULL")]:
            ledger.apply(body)
        self.assertEqual(ledger.positions["AAPL"]["campaign_id"], "SECOND")
        self.assertGreater(ledger.positions["AAPL"]["opened_at"], later)

    def test_increasing_position_cannot_reset_original_deadline(self):
        ledger, _ = bought()
        d, o = fixture_order()
        later = ledger.now + 1000
        d.update(id="D2", decision_id="D2", at=later, occurred_at=later)
        d["quotes"]["AAPL"].update(quote_at=later, received_at=later)
        o.update(
            id="O2",
            order_id="O2",
            decision_id="D2",
            at=later + 1,
            occurred_at=later + 1,
            deadline_at=later + 72 * 3600000,
        )
        ledger.apply(d)
        with self.assertRaisesRegex(ValueError, "CAMPAIGN_RESET"):
            ledger.apply(o)

    def test_impossible_exit_is_recorded_without_erasing_inventory(self):
        ledger, events = bought()
        packet = mark(ledger, events, at=T0 + 73 * 3600000)
        self.assertEqual(ledger.quantity("AAPL"), 2)
        self.assertEqual(len(ledger.breaches), 1)
        self.assertEqual(audit_account(packet)["deadline_breaches"], 1)

    def test_number_domains_reject_bool_nan_and_infinity(self):
        for value in (True, float("nan"), float("inf"), -1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                number(value)

    def test_fractional_crypto_is_not_converted_to_equity_shares(self):
        decision, order = fixture_order(qty=0.02, symbol="BTC/USD", book="crypto")
        ledger = Ledger()
        for body in [decision, *simulate_order(order, 73, force="PARTIAL_CANCEL")]:
            ledger.apply(body)
        self.assertEqual(ledger.quantity("BTC/USD"), 0.01)
        self.assertEqual(ledger.quantity("AAPL"), 0)

    def test_single_smallest_crypto_unit_is_not_erased(self):
        decision, order = fixture_order(qty=1e-8, symbol="BTC/USD", book="crypto")
        ledger = Ledger()
        bodies = [decision, *simulate_order(order, 73, force="LATE_FILL")]
        for body in bodies:
            ledger.apply(body)
        self.assertEqual(ledger.quantity("BTC/USD"), 1e-8)
        end = event(
            "MARK",
            "dust-mark",
            T0 + 10000,
            quotes={"BTC/USD": {"bid": 100.0, "ask": 100.01}},
        )
        ledger.apply(end)
        self.assertEqual(len(ledger.report()["positions"]), 1)
        self.assertTrue(audit_account(account_from(ledger, [*bodies, end]))["verified"])

    def test_more_than_eight_quantity_decimals_is_rejected(self):
        decision, order = fixture_order(qty=1e-9, symbol="BTC/USD", book="crypto")
        ledger = Ledger()
        ledger.apply(decision)
        with self.assertRaisesRegex(ValueError, "NATIVE_QUANTITY_PRECISION"):
            ledger.apply(order)

    def test_fault_matrix_checks_both_implementations(self):
        matrix = fault_matrix()
        self.assertEqual(matrix["passed"], 18)
        self.assertTrue(matrix["all_expected_behaviors"])
        self.assertTrue(
            all(
                r.get("separate_decimal_rejection")
                for r in matrix["cases"]
                if r["result"] == "EXPECTED_REJECTION"
            )
        )


class AdversarialReviewTests(unittest.TestCase):
    def setUp(self):
        ledger, events = bought()
        self.packet = mark(ledger, events)

    def test_rehashed_invalid_fill_is_detected_by_semantics(self):
        packet = copy.deepcopy(self.packet)
        events = unlink(packet["event_chain"])
        fill = next(e for e in events if e["kind"] == "FILL")
        fill["qty"] = 3.0
        fill["available_qty"] = 3.0
        packet["event_chain"] = link(events)
        with self.assertRaisesRegex(ValueError, "AUDIT_FILL_CUMULATIVE"):
            audit_account(packet)

    def test_forged_final_cash_is_detected(self):
        self.packet["ledger"]["cash_usd"] += 100
        with self.assertRaisesRegex(ValueError, "AUDIT_FINAL_CASH"):
            audit_account(self.packet)

    def test_forged_mark_equity_is_detected(self):
        self.packet["ledger"]["curve"][-1]["equity_usd"] += 100
        with self.assertRaisesRegex(ValueError, "AUDIT_equity_usd"):
            audit_account(self.packet)

    def test_relabeling_as_real_or_external_is_rejected(self):
        for key in (
            "real_fills_present",
            "real_prospective_validation",
            "external_review_completed",
            "execution_allowed",
            "level9_accredited",
        ):
            packet = copy.deepcopy(self.packet)
            packet[key] = True
            with (
                self.subTest(key=key),
                self.assertRaisesRegex(ValueError, "AUDIT_FALSE_AUTHORITY"),
            ):
                audit_account(packet)

    def test_changing_origin_to_observed_is_rejected(self):
        self.packet["origin"] = "OBSERVED"
        with self.assertRaisesRegex(ValueError, "AUDIT_SYNTHETIC_ONLY"):
            audit_account(self.packet)

    def test_chain_corruption_is_rejected(self):
        self.packet["event_chain"][-1]["event"]["quotes"]["AAPL"]["bid"] += 1
        with self.assertRaisesRegex(ValueError, "EVENT_HASH"):
            audit_account(self.packet)

    def test_observed_fill_calibrator_refuses_synthetic_schema(self):
        with self.assertRaises(ValueError):
            calibrate_fills(
                {
                    "schema": "HARPOON_SYNTHETIC_COST_CALIBRATION_1",
                    "origin": ORIGIN,
                    "mode": "LIVE",
                }
            )

    def test_reviewer_imports_neither_simulator_nor_ledger(self):
        code = "import sys; from harpoon_quant.synthetic9.review import audit_account; assert not any('harpoon_quant.synthetic9.'+x in sys.modules for x in ['bank','ledger','execution'])"
        subprocess.run(
            [sys.executable, "-B", "-c", code],
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": "quant"},
            check=True,
            capture_output=True,
        )


class CausalBankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol = json.loads(
            (ROOT / "research/synthetic9/protocol.json").read_text()
        )
        cls.protocol.update(warmup_weeks=24, evaluation_weeks=1)
        cls.costs = calibration([1901, 1907])
        cls.data = world(701, "TREND_BREAK", cls.protocol)

    def test_worlds_are_finite_normalized_causal_path_contracts(self):
        for name in WORLDS:
            data = world(701, name, self.protocol)
            for row in data["samples"]:
                validate_paths(row, 4, 8)
                self.assertLess(
                    timestamp(row["features_known_at"]), timestamp(row["start_at"])
                )
            self.assertEqual(data["origin"], ORIGIN)

    def test_calibration_fills_are_linked_and_known_before_forward(self):
        self.assertEqual(len(self.costs["samples"]), 320)
        self.assertFalse(self.costs["real_fills_calibrated"])
        for row, stream in zip(
            self.costs["samples"],
            self.costs["isolated_execution_streams_not_account_ledgers"],
            strict=True,
        ):
            self.assertEqual(row["order_id"], stream[-1]["order_id"])
            self.assertEqual(row["price"], stream[-1]["price"])
            self.assertLess(
                timestamp(row["known_at"]),
                timestamp(self.data["samples"][24]["start_at"]),
            )

    def test_cash_pays_all_seven_days_and_no_capital_reset(self):
        protocol = {**self.protocol, "evaluation_weeks": 3}
        data = world(701, "NULL", protocol)
        r = run_account(
            data,
            protocol,
            self.costs,
            seed=701,
            world_name="NULL",
            scenario="NOMINAL",
            strategy="CASH",
        )
        self.assertEqual(r["metrics"]["terminal_equity_usd"], 20000 - 21)
        self.assertEqual([w["cash_usd"] for w in r["weekly"]], [19993, 19986, 19979])
        self.assertEqual(r["metrics"]["account_resets"], 0)
        self.assertTrue(audit_account(r)["verified"])

    def test_double_cost_includes_all_common_overhead(self):
        r = run_account(
            self.data,
            self.protocol,
            self.costs,
            seed=701,
            world_name="TREND_BREAK",
            scenario="DOUBLE_COST",
            strategy="CASH",
        )
        self.assertEqual(r["metrics"]["terminal_equity_usd"], 20000 - 14)
        self.assertEqual(r["metrics"]["overhead_usd"], 14)
        self.assertTrue(audit_account(r)["verified"])

    def test_reported_log_growth_is_independently_verified(self):
        r = run_account(
            self.data,
            self.protocol,
            self.costs,
            seed=701,
            world_name="TREND_BREAK",
            scenario="NOMINAL",
            strategy="CASH",
        )
        r["metrics"]["terminal_log_growth"] += 0.01
        with self.assertRaisesRegex(ValueError, "AUDIT_LOG_GROWTH"):
            audit_account(r)

    def test_opening_quote_includes_current_known_gap(self):
        data = world(701, "LIQUIDITY_SHOCK", self.protocol)
        row = data["samples"][-1]
        q = quotes(row, 24)["AAPL"]
        mid = (q["bid"] + q["ask"]) / 2
        self.assertAlmostEqual(mid, row["entry_prices"][0] * row["ohlc"][0][24][0])
        self.assertLess(mid, row["entry_prices"][0] * row["ohlc"][0][23][3])

    def test_protective_exit_reacts_to_known_opening_gap(self):
        data = copy.deepcopy(self.data)
        for path in data["samples"][-1]["ohlc"]:
            for h in range(72):
                path[h] = [1.0 if h < 24 else 0.9] * 4
        r = run_account(
            data,
            self.protocol,
            self.costs,
            seed=701,
            world_name="TREND_BREAK",
            scenario="NOMINAL",
            strategy="FIXED_SAME_LOT_CAP",
        )
        exits = [
            item["event"]
            for item in r["event_chain"]
            if item["event"]["kind"] == "SUBMIT" and item["event"]["side"] == "sell"
        ]
        self.assertTrue(exits)
        at = round(timestamp(data["samples"][-1]["start_at"]).timestamp() * 1000)
        self.assertLess(min(e["at"] for e in exits), at + 25 * 3600000)
        self.assertTrue(audit_account(r)["verified"])

    def test_fixed_policy_generates_real_simulator_events_and_reconciles(self):
        r = run_account(
            self.data,
            self.protocol,
            self.costs,
            seed=701,
            world_name="TREND_BREAK",
            scenario="DOUBLE_COST_GAP",
            strategy="FIXED_SAME_LOT_CAP",
        )
        self.assertGreater(r["metrics"]["fill_count"], 0)
        self.assertTrue(audit_account(r)["verified"])
        self.assertLessEqual(
            r["execution_diagnostics"]["notional_weighted_fill_ratio"], 1
        )

    def test_core_uses_only_earlier_labels_and_never_authorizes(self):
        r = run_account(
            self.data,
            self.protocol,
            self.costs,
            seed=701,
            world_name="TREND_BREAK",
            scenario="NOMINAL",
            strategy="CORE",
        )
        cr = r["core_receipts"][0]
        self.assertNotIn(self.data["samples"][24]["id"], cr["training_ids"])
        self.assertLess(
            timestamp(cr["maximum_training_known_at"]),
            timestamp(cr["calibration_available_at"]),
        )
        self.assertFalse(cr["receipt"]["execution_allowed"])
        self.assertTrue(audit_account(r)["verified"])

    def test_future_current_window_cannot_change_first_decision(self):
        other = copy.deepcopy(self.data)
        for path in other["samples"][-1]["ohlc"]:
            for h, values in enumerate(path):
                if h:
                    path[h] = [v * 0.8 for v in values]
        args = dict(
            seed=701, world_name="TREND_BREAK", scenario="NOMINAL", strategy="CORE"
        )
        a = run_account(self.data, self.protocol, self.costs, **args)
        b = run_account(other, self.protocol, self.costs, **args)
        self.assertEqual(
            a["core_receipts"][0]["receipt"]["receipt_hash"],
            b["core_receipts"][0]["receipt"]["receipt_hash"],
        )

    def test_synthetic_model_and_costs_keep_explicit_origins(self):
        data = {**self.data, "samples": self.data["samples"][:24]}
        now = self.data["samples"][24]["start_at"]
        model = fit(data, now, Settings())
        state = state_for(
            Ledger(), self.data["samples"][24], self.costs, 1, 0, "FIXTURE"
        )
        self.assertEqual(model["origin"], ORIGIN)
        self.assertTrue(all(a["cost_origin"] == "ASSUMED" for a in state["assets"]))
        self.assertEqual(
            quotes(self.data["samples"][24], 0)["AAPL"]["quote_at"],
            round(timestamp(now).timestamp() * 1000),
        )


class ArtifactTests(unittest.TestCase):
    def test_gzip_is_deterministic_private_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a.gz", Path(tmp) / "b.gz"
            write_gzip(a, {"origin": ORIGIN, "x": [1, 2]})
            write_gzip(b, {"x": [1, 2], "origin": ORIGIN})
            self.assertEqual(a.read_bytes(), b.read_bytes())
            self.assertEqual(a.stat().st_mode & 0o777, 0o600)
            self.assertEqual(load_gzip(a)["x"], [1, 2])
            with self.assertRaises(FileExistsError):
                write_gzip(a, {})

    def test_manifest_rejects_path_escape_and_content_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            item = root / "item.json.gz"
            write_gzip(item, {"x": 1})
            valid = {
                "artifacts_sha256": {"item.json.gz": sha256(item)},
                "sources_sha256": {"item.json.gz": sha256(item)},
            }
            verify_manifest(root, root, valid)
            invalid = copy.deepcopy(valid)
            invalid["artifacts_sha256"] = {"../escape": "0" * 64}
            with self.assertRaisesRegex(ValueError, "PACKET_PATH"):
                verify_manifest(root, root, invalid)
            item.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "PACKET_HASH"):
                verify_manifest(root, root, valid)
