"""Operational attacks against native fees, persistent orders and retry timing."""

from __future__ import annotations

import gzip
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from harpoon_quant.roadmap9.costs import (
    FeeProfile,
    NativeFeeLedger,
    calendar_overhead,
    round_trip_break_even,
)
from harpoon_quant.roadmap9.execution import (
    HOUR_MS,
    ExecutionBook,
    RetryBudget,
    latest_exit_dispatch,
)


def crypto_profile() -> FeeProfile:
    return FeeProfile(
        "public-tier1-assumed",
        "BTC",
        "USD",
        Decimal(15),
        Decimal(25),
        "ASSUMED_PUBLIC_TARIFF",
        "https://docs.alpaca.markets/us/docs/crypto-trading",
    )


class NativeFeeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = crypto_profile()
        self.ledger = NativeFeeLedger({"USD": "20000", "BTC": "0"})

    def fill(self, **changes):
        values = {
            "fill_id": "f1",
            "order_id": "o1",
            "side": "buy",
            "qty": "0.1",
            "price": "50000",
            "liquidity_role": "taker",
            "profile": self.profile,
        }
        values.update(changes)
        return self.ledger.apply_fill(**values)

    def test_buy_fee_is_in_crypto_and_pending_is_not_spendable(self):
        self.fill()
        self.assertEqual(self.ledger.balances["USD"], Decimal(15000))
        self.assertEqual(self.ledger.balances["BTC"], Decimal("0.1"))
        self.assertEqual(self.ledger.available("BTC"), Decimal("0.09975"))
        self.assertEqual(
            self.ledger.equity({"USD": 1, "BTC": 50000}), Decimal("19987.5")
        )

    def test_no_fee_activity_never_implies_zero_fee(self):
        self.fill()
        self.assertEqual(self.ledger.report()["pending_fee_count"], 1)
        self.assertEqual(self.ledger.pending("BTC"), Decimal("0.00025"))

    def test_posting_releases_liability_without_double_counting(self):
        self.fill()
        before = self.ledger.equity({"USD": 1, "BTC": 50000})
        self.ledger.post_fee(
            activity_id="cfee1", fill_id="f1", fee_asset="BTC", total_fee="0.00025"
        )
        self.assertEqual(self.ledger.pending("BTC"), 0)
        self.assertEqual(self.ledger.balances["BTC"], Decimal("0.09975"))
        self.assertEqual(self.ledger.equity({"USD": 1, "BTC": 50000}), before)
        self.assertFalse(
            self.ledger.post_fee(
                activity_id="cfee1", fill_id="f1", fee_asset="BTC", total_fee="0.00025"
            )
        )

    def test_corrected_fee_changes_only_delta(self):
        self.fill()
        self.ledger.post_fee(
            activity_id="cfee1", fill_id="f1", fee_asset="BTC", total_fee="0.00025"
        )
        self.ledger.post_fee(
            activity_id="cfee2",
            fill_id="f1",
            fee_asset="BTC",
            total_fee="0.00020",
            corrects_activity_id="cfee1",
        )
        self.assertEqual(self.ledger.balances["BTC"], Decimal("0.09980"))
        with self.assertRaisesRegex(ValueError, "LINEAGE"):
            self.ledger.post_fee(
                activity_id="cfee3", fill_id="f1", fee_asset="BTC", total_fee="0.00019"
            )

    def test_duplicate_fill_and_conflicting_fill(self):
        self.assertTrue(self.fill())
        self.assertFalse(self.fill())
        with self.assertRaisesRegex(ValueError, "CONFLICTING_FILL"):
            self.fill(qty="0.2")
        self.assertEqual(self.ledger.balances["USD"], Decimal(15000))

    def test_unknown_liquidity_blocks_instead_of_assuming_maker(self):
        with self.assertRaisesRegex(ValueError, "LIQUIDITY_UNKNOWN"):
            self.fill(liquidity_role="limit")
        self.assertEqual(self.ledger.balances["USD"], Decimal(20000))

    def test_mixed_partial_roles_are_charged_per_fill(self):
        self.fill(qty="0.04", liquidity_role="maker")
        self.fill(fill_id="f2", qty="0.06", liquidity_role="taker")
        self.assertEqual(self.ledger.pending("BTC"), Decimal("0.00021"))

    def test_versioned_profile_binds_every_rate_and_provenance_field(self):
        self.fill(qty="0.04", liquidity_role="maker")
        balance = dict(self.ledger.balances)
        for change in (
            {"taker_bps": Decimal(99)},
            {"source": "unbound-source"},
            {"origin": "OBSERVED_ACCOUNT"},
        ):
            with (
                self.subTest(change=change),
                self.assertRaisesRegex(ValueError, "ORDER_FEE_CONTRACT_CHANGED"),
            ):
                self.fill(
                    fill_id="f2", qty="0.06", profile=replace(self.profile, **change)
                )
        self.assertEqual(balance, self.ledger.balances)
        self.fill(fill_id="f2", qty="0.06", liquidity_role="taker")
        self.assertEqual(self.ledger.pending("BTC"), Decimal("0.00021"))

    def test_sell_fee_is_in_quote_currency(self):
        self.fill()
        self.fill(fill_id="sell", order_id="o2", side="sell", qty="0.09975")
        self.assertEqual(self.ledger.pending("USD"), Decimal("12.46875"))
        self.assertEqual(
            self.ledger.equity({"USD": 1, "BTC": 50000}), Decimal("19975.03125")
        )

    def test_cannot_sell_fee_reserved_quantity(self):
        self.fill()
        with self.assertRaisesRegex(ValueError, "INSUFFICIENT"):
            self.fill(fill_id="sell", order_id="o2", side="sell", qty="0.1")

    def test_fee_currency_mismatch_and_conflicting_activity(self):
        self.fill()
        with self.assertRaisesRegex(ValueError, "CURRENCY"):
            self.ledger.post_fee(
                activity_id="c1", fill_id="f1", fee_asset="USD", total_fee="12.5"
            )
        self.ledger.post_fee(
            activity_id="c1", fill_id="f1", fee_asset="BTC", total_fee="0.00025"
        )
        with self.assertRaisesRegex(ValueError, "CONFLICTING_FEE"):
            self.ledger.post_fee(
                activity_id="c1", fill_id="f1", fee_asset="BTC", total_fee="0.0001"
            )

    def test_smallest_quantity_is_not_erased(self):
        self.fill(qty="0.00000001")
        self.assertEqual(self.ledger.available("BTC"), Decimal("0.000000009975"))

    def test_equity_fee_stays_in_usd_and_fixed_paid_once(self):
        profile = FeeProfile(
            "stock-model",
            "AAPL",
            "USD",
            Decimal(0),
            Decimal(0),
            "SYNTHETIC_ENGINEERING_ONLY",
            "registered-test-profile",
            "QUOTE_PER_UNIT",
            Decimal("0.005"),
            Decimal("0.01"),
        )
        self.fill(profile=profile, qty="2", price="100")
        self.fill(profile=profile, fill_id="f2", qty="3", price="100")
        self.assertEqual(self.ledger.balances["AAPL"], Decimal(5))
        self.assertEqual(self.ledger.pending("USD"), Decimal("0.035"))
        self.assertFalse(self.fill(profile=profile, qty="2", price="100"))

    def test_round_trip_exact_threshold(self):
        threshold = round_trip_break_even(25, 25)
        self.assertAlmostEqual(float(threshold), 0.005018812695900151, places=14)

    def test_nonfinite_bool_and_negative_fees_rejected(self):
        for value in (True, "NaN", "Infinity", "-1"):
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                round_trip_break_even(value, 25)

    def test_calendar_costs_include_weekend_and_cannot_duplicate(self):
        start = datetime(2026, 11, 6, 0, 0, tzinfo=UTC)
        end = datetime(2026, 11, 9, 0, 0, tzinfo=UTC)
        self.assertEqual(calendar_overhead(start, end, "1"), Decimal(3))
        self.ledger.accrue_overhead(
            accrual_id="weekend", start=start, end=end, usd_per_day=1
        )
        self.assertFalse(
            self.ledger.accrue_overhead(
                accrual_id="weekend", start=start, end=end, usd_per_day=1
            )
        )
        with self.assertRaisesRegex(ValueError, "OVERLAPPING"):
            self.ledger.accrue_overhead(
                accrual_id="again", start=start, end=end, usd_per_day=1
            )

    def test_missing_marks_or_naive_times_are_blocking(self):
        self.fill()
        with self.assertRaisesRegex(ValueError, "MISSING_ASSET_MARK"):
            self.ledger.equity({"USD": 1})
        with self.assertRaisesRegex(ValueError, "AWARE_TIME"):
            calendar_overhead(datetime(2026, 1, 1), datetime(2026, 1, 2), 1)


class ExecutionStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.book = ExecutionBook({"AAPL": "10"})
        self.book.intent(
            client_order_id="sell1",
            campaign_id="campaign",
            symbol="AAPL",
            side="sell",
            qty="4",
            at=100,
            opened_at=0,
            deadline_at=72 * HOUR_MS,
        )
        self.send("SUBMITTED", 110)

    def send(self, kind, at, **kwargs):
        return self.book.receive(
            {
                "event_id": kind + str(at),
                "kind": kind,
                "client_order_id": "sell1",
                "at": at,
                **kwargs,
            }
        )

    def fill(self, at=150, **kwargs):
        values = {
            "execution_id": "exec1",
            "executed_at": 140,
            "qty": "2",
            "price": "100",
            "cumulative_qty": "2",
        }
        values.update(kwargs)
        return self.send("FILL", at, **values)

    def test_timeout_and_lookup_miss_preserve_ambiguity(self):
        self.send("LOOKUP_MISS", 120)
        self.assertEqual(self.book.view("sell1")["status"], "SUBMISSION_UNKNOWN")
        with self.assertRaisesRegex(ValueError, "UNSAFE_RESUBMISSION"):
            self.send("SUBMITTED", 130)
        with self.assertRaisesRegex(ValueError, "UNRESOLVED"):
            self.book.intent(
                client_order_id="sell2",
                campaign_id="campaign",
                symbol="AAPL",
                side="sell",
                qty=4,
                at=140,
                opened_at=0,
                deadline_at=72 * HOUR_MS,
            )

    def test_cancel_pending_cannot_hide_ambiguous_submission(self):
        self.send("CANCEL_REQUEST", 120)
        self.send("LOOKUP_MISS", 125)
        with self.assertRaisesRegex(ValueError, "RECONCILIATION"):
            self.book.receive(
                {
                    "event_id": "bad-reconciliation",
                    "kind": "RECONCILED",
                    "at": 130,
                    "inventory": {"AAPL": "10"},
                }
            )
        health = self.book.health(now=140, last_market_event_at=139)
        self.assertTrue(health["ambiguous_orders"])
        self.assertTrue(health["new_entries_blocked"])
        self.assertFalse(health["alive"])
        self.send("CANCEL_REJECT", 150, cumulative_qty="0")
        self.assertTrue(self.book.view("sell1")["submission_unknown"])
        with self.assertRaisesRegex(ValueError, "REPLACE_REQUEST_STATE"):
            self.send(
                "REPLACE_REQUEST", 160, total_qty="2", new_client_order_id="bad-replace"
            )
        self.send("ACK", 170, broker_order_id="broker1")
        self.assertFalse(self.book.view("sell1")["submission_unknown"])

    def test_terminal_cumulative_cannot_erase_announced_fill_reservation(self):
        self.send("ACK", 120, broker_order_id="broker1")
        self.fill(cumulative_qty="4")
        self.send("CANCEL_REQUEST", 160)
        with self.assertRaisesRegex(ValueError, "TERMINAL_CUMULATIVE"):
            self.send("CANCEL_ACK", 170, cumulative_qty="2")
        self.assertEqual(self.book.reserved_inventory("AAPL"), Decimal(2))
        with self.assertRaisesRegex(ValueError, "DOUBLE_SELL"):
            self.book.intent(
                client_order_id="oversell",
                campaign_id="other",
                symbol="AAPL",
                side="sell",
                qty="8",
                at=180,
                opened_at=0,
                deadline_at=72 * HOUR_MS,
            )
        with self.assertRaisesRegex(ValueError, "RECONCILIATION"):
            self.book.receive(
                {
                    "event_id": "missing-fills",
                    "kind": "RECONCILED",
                    "at": 181,
                    "inventory": {"AAPL": "8"},
                }
            )
        self.send("CANCEL_ACK", 190, cumulative_qty="4")
        self.fill(at=200, executed_at=155, execution_id="late-fill", cumulative_qty="4")
        self.assertEqual(self.book.reserved_inventory("AAPL"), 0)
        self.assertEqual(self.book.inventory["AAPL"], Decimal(6))

    def test_fill_before_ack_is_authoritative_and_late_ack_never_downgrades(self):
        self.fill(qty="4", cumulative_qty="4")
        self.send("ACK", 160, broker_order_id="broker1")
        self.assertEqual(self.book.view("sell1")["status"], "FILLED")
        self.assertEqual(self.book.inventory["AAPL"], Decimal(6))

    def test_execution_duplicate_with_new_message_id_not_double_counted(self):
        self.fill()
        self.fill(at=160)
        self.assertEqual(self.book.inventory["AAPL"], Decimal(8))
        with self.assertRaisesRegex(ValueError, "CONFLICTING_EXECUTION"):
            self.fill(at=170, price="99")

    def test_partial_cancel_announced_late_fill_keeps_reservation(self):
        self.send("ACK", 120, broker_order_id="broker1")
        self.fill()
        self.send("CANCEL_REQUEST", 160)
        self.send("CANCEL_ACK", 200, executed_at=190, cumulative_qty="4")
        self.assertEqual(self.book.reserved_inventory("AAPL"), Decimal(2))
        self.fill(at=220, executed_at=180, execution_id="exec2", cumulative_qty="4")
        self.assertEqual(self.book.inventory["AAPL"], Decimal(6))
        self.assertEqual(self.book.reserved_inventory("AAPL"), 0)

    def test_out_of_order_fill_reports_are_not_cumulative_deltas(self):
        self.fill(at=160, executed_at=150, execution_id="later", cumulative_qty="4")
        self.assertTrue(self.book.view("sell1")["missing_fill_reports"])
        self.fill(at=170, executed_at=140, execution_id="earlier", cumulative_qty="2")
        self.assertEqual(self.book.inventory["AAPL"], Decimal(6))
        self.assertFalse(self.book.view("sell1")["missing_fill_reports"])

    def test_replace_success_request_is_not_terminal_confirmation(self):
        self.send("ACK", 120, broker_order_id="broker1")
        self.send("REPLACE_REQUEST", 130, total_qty="2", new_client_order_id="sell1r")
        self.assertEqual(self.book.view("sell1")["status"], "REPLACE_PENDING")
        self.assertEqual(self.book.reserved_inventory("AAPL"), Decimal(4))
        self.fill(at=160, qty="4", cumulative_qty="4")
        self.send("REPLACE_REJECT", 170)
        self.assertEqual(self.book.view("sell1")["status"], "FILLED")

    def test_cancel_rejection_with_missing_fill_does_not_release_reserve(self):
        self.send("ACK", 120, broker_order_id="broker1")
        self.send("CANCEL_REQUEST", 130)
        self.send("CANCEL_REJECT", 150, cumulative_qty="4")
        self.assertEqual(self.book.reserved_inventory("AAPL"), Decimal(4))
        self.assertTrue(self.book.view("sell1")["missing_fill_reports"])
        self.fill(at=160, qty="4", cumulative_qty="4")
        self.assertEqual(self.book.reserved_inventory("AAPL"), 0)

    def test_replace_ack_keeps_campaign_and_links_new_order_id(self):
        self.send("ACK", 120, broker_order_id="broker1")
        self.send("REPLACE_REQUEST", 130, total_qty="2", new_client_order_id="sell1r")
        self.send("REPLACE_ACK", 140)
        self.assertEqual(self.book.view("sell1r")["deadline_at"], 72 * HOUR_MS)
        self.assertEqual(self.book.reserved_inventory("AAPL"), Decimal(2))
        self.book.receive(
            {
                "event_id": "replacement-broker-ack",
                "kind": "ACK",
                "at": 150,
                "client_order_id": "sell1r",
                "broker_order_id": "replacement-broker-id",
            }
        )
        self.assertEqual(
            self.book.view("sell1r")["broker_order_id"], "replacement-broker-id"
        )
        self.send("ACK", 160, broker_order_id="broker1")
        self.assertEqual(
            self.book.view("sell1r")["broker_order_id"], "replacement-broker-id"
        )
        with self.assertRaisesRegex(ValueError, "STALE_CLIENT_ORDER_ALIAS"):
            self.send("CANCEL_REQUEST", 170)

    def test_rejected_order_releases_only_confirmed_remaining(self):
        self.send("REJECT", 120, cumulative_qty="0")
        self.assertEqual(self.book.reserved_inventory("AAPL"), 0)
        self.book.intent(
            client_order_id="sell2",
            campaign_id="campaign",
            symbol="AAPL",
            side="sell",
            qty=4,
            at=140,
            opened_at=0,
            deadline_at=72 * HOUR_MS,
        )
        self.assertEqual(self.book.reserved_inventory("AAPL"), Decimal(4))

    def test_new_attempt_cannot_reset_campaign_deadline(self):
        self.send("REJECT", 120, cumulative_qty="0")
        with self.assertRaisesRegex(ValueError, "DEADLINE_RESET"):
            self.book.intent(
                client_order_id="sell2",
                campaign_id="campaign",
                symbol="AAPL",
                side="sell",
                qty=4,
                at=140,
                opened_at=140,
                deadline_at=140 + 72 * HOUR_MS,
            )

    def test_two_campaigns_cannot_double_sell_inventory(self):
        with self.assertRaisesRegex(ValueError, "DOUBLE_SELL"):
            self.book.intent(
                client_order_id="sell2",
                campaign_id="other",
                symbol="AAPL",
                side="sell",
                qty=7,
                at=140,
                opened_at=0,
                deadline_at=72 * HOUR_MS,
            )

    def test_post_cancel_execution_is_preserved_as_incident(self):
        self.send("ACK", 120, broker_order_id="broker1")
        self.send("CANCEL_REQUEST", 130)
        self.send("CANCEL_ACK", 140, cumulative_qty="0")
        self.fill(at=170, executed_at=160)
        self.assertEqual(self.book.inventory["AAPL"], Decimal(8))
        self.assertTrue(
            any(s.startswith("POST_CANCEL_EXECUTION") for s in self.book.incidents)
        )

    def test_restart_replays_journal_and_cannot_resubmit_unknown_order(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "orders.json"
            self.book.save(path)
            restored = ExecutionBook.load(path)
            self.assertEqual(restored.snapshot(), self.book.snapshot())
            with self.assertRaisesRegex(ValueError, "UNSAFE_RESUBMISSION"):
                restored.receive(
                    {
                        "event_id": "again",
                        "kind": "SUBMITTED",
                        "client_order_id": "sell1",
                        "at": 120,
                    }
                )
            payload = json.loads(path.read_text())
            payload["events"][0]["qty"] = "8"
            path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "INTEGRITY"):
                ExecutionBook.load(path)

    def test_alive_uses_real_receipt_and_reconciliation_ages(self):
        self.send("ACK", 120, broker_order_id="broker1")
        self.book.receive(
            {
                "event_id": "reconcile",
                "kind": "RECONCILED",
                "at": 130,
                "inventory": {"AAPL": "10"},
            }
        )
        self.assertTrue(self.book.health(now=140, last_market_event_at=135)["alive"])
        self.assertFalse(
            self.book.health(now=20000, last_market_event_at=19999)["alive"]
        )
        self.assertFalse(self.book.health(now=140, last_market_event_at=None)["alive"])

    def test_failed_atomic_write_preserves_previous_recoverable_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "orders.json"
            self.book.save(path)
            before = path.read_bytes()
            self.send("ACK", 120, broker_order_id="broker1")
            with (
                patch(
                    "harpoon_quant.roadmap9.execution.os.replace",
                    side_effect=OSError("disk unavailable"),
                ),
                self.assertRaises(OSError),
            ):
                self.book.save(path)
            self.assertEqual(path.read_bytes(), before)
            restored = ExecutionBook.load(path)
            self.assertEqual(restored.view("sell1")["status"], "SUBMISSION_UNKNOWN")
            self.assertEqual(list(Path(directory).iterdir()), [path])


class ExitTimingTests(unittest.TestCase):
    def test_retry_is_bounded_by_attempts_quotes_deadline_and_ambiguity(self):
        budget = RetryBudget()
        valid = {
            "now": 1000,
            "deadline": 10000,
            "quote_at": 0,
            "attempts": 1,
            "order_reconciled": True,
            "market_available": True,
        }
        self.assertEqual(budget.next_at(**valid), 1250)
        for changes in (
            {"attempts": 8},
            {"quote_at": 1001},
            {"deadline": 3000},
            {"order_reconciled": False},
            {"market_available": False},
            {"now": 16000, "deadline": 30000},
        ):
            with self.subTest(changes=changes):
                self.assertIsNone(budget.next_at(**{**valid, **changes}))

    def test_thursday_deadline_sunday_uses_last_friday_window(self):
        # Absolute UTC windows supplied by an exchange-calendar contract.
        dispatch = latest_exit_dispatch(
            original_deadline=72 * HOUR_MS,
            opened_at=0,
            eligible_windows=[(0, 6 * HOUR_MS), (24 * HOUR_MS, 30 * HOUR_MS)],
            execution_budget_ms=2500,
            now=HOUR_MS,
        )
        self.assertEqual(dispatch, 30 * HOUR_MS - 2500)

    def test_half_session_and_dst_do_not_extend_elapsed_limit(self):
        dispatch = latest_exit_dispatch(
            original_deadline=72 * HOUR_MS,
            opened_at=0,
            eligible_windows=[(0, 3 * HOUR_MS), (25 * HOUR_MS, 28 * HOUR_MS)],
            execution_budget_ms=2500,
            now=0,
        )
        self.assertEqual(dispatch, 28 * HOUR_MS - 2500)

    def test_halt_with_no_eligible_window_does_not_invent_liquidation(self):
        self.assertIsNone(
            latest_exit_dispatch(
                original_deadline=72 * HOUR_MS,
                opened_at=0,
                eligible_windows=[],
                execution_budget_ms=2500,
                now=HOUR_MS,
            )
        )


class ArchivedExecutionReplayTests(unittest.TestCase):
    def test_original_breaches_repaired_and_replay_is_deterministic(self):
        from harpoon_quant.roadmap9.execution_replay import replay_account

        root = Path(__file__).resolve().parents[2]
        source_file = (
            root
            / "evidence/synthetic9/run_01/accounts/TREND_BREAK_4103_NOMINAL_CORE.json.gz"
        )
        with gzip.open(source_file, "rt") as stream:
            source = json.load(stream)
        protocol = json.loads(
            (root / "research/roadmap9/execution_protocol.json").read_text()
        )
        self.assertEqual(source["metrics"]["deadline_breach_count"], 2)
        first = replay_account(source, protocol)
        second = replay_account(source, protocol)
        self.assertEqual(first["event_chain"], second["event_chain"])
        self.assertTrue(first["entry_events_preserved"])
        self.assertTrue(first["separate_decimal_audit"]["verified"])
        self.assertEqual(first["metrics"]["deadline_breach_count"], 0)
        self.assertEqual(first["metrics"]["open_position_count"], 0)
        self.assertFalse(first["entry_policy_recomputed"])
        self.assertFalse(first["execution_allowed"])
        self.assertEqual(first["core_receipts"], [])


if __name__ == "__main__":
    unittest.main()
