"""C38 deterministic research-only ten-band/two-step stop guard tests."""

from __future__ import annotations

import json
import unittest
from dataclasses import asdict, replace

from harpoon_quant.five_level_guard import (
    GridSpec, Inventory, Quote, create_grid, empty_latch, inspect,
    rearm, research_capacity,
)

AT = 1_800_000_000_000


def source(*, symbol: str = "SPY", book: str = "equity",
           price: str = "100.00", atr: str = "4.00",
           spread: str = "0.10", tick: str = "0.01") -> GridSpec:
    return GridSpec(
        symbol=symbol, strategy="NATIVE_BREAKOUT_RESEARCH_ONLY",
        book=book, reference_price=price,
        atr_closed_price=atr, spread_price=spread,
        tick_size=tick, entry_fee_bps="0", exit_fee_bps="0",
        other_roundtrip_friction_bps="15",
        quote_known_at_ms=AT - 200, atr_known_at_ms=AT - 300_000,
        decision_at_ms=AT, original_native_prefilter_seen=True,
        provenance="SYNTHETIC_RESEARCH",
    )


def inventory(
    grid=None, *, held: str = "0", entry: str | None = None,
    pending: str = "0", verified: bool = True,
) -> Inventory:
    return Inventory(
        position_qty=held, actual_entry_price=entry,
        position_grid_generation=grid.generation if held != "0" and grid else None,
        pending_entry_qty=pending,
        pending_entry_grid_generation=grid.generation if pending != "0" and grid else None,
        verified_broker_snapshot=verified,
    )


def quote(bid: str, *, ask: str | None = None, at: int = AT) -> Quote:
    return Quote(
        bid=bid, ask=ask or bid,
        source_at_ms=at - 200,
        locally_known_at_ms=at - 100,
        decision_at_ms=at,
    )


class FiveLevelGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.grid = create_grid(source())
        self.latch = empty_latch(self.grid)

    def measure(self, bid: str, *, state=None, position=None,
                candidate=True, at=AT, protection=True):
        return inspect(
            self.grid, state or self.latch, quote(bid, at=at),
            position or inventory(), c36_research_gate_passed=candidate,
            existing_native_protection_present=protection,
        )

    def test_exactly_five_up_and_five_down_levels(self):
        levels = dict(self.grid.levels)
        self.assertEqual(set(levels), set(range(-5, 6)))
        self.assertEqual(levels[0], "100.00")
        self.assertEqual(levels[-2], "98.00")
        self.assertEqual(levels[5], "105.00")
        self.assertEqual(self.grid.two_levels_lower_than_reference, "98.00")

    def test_step_adapts_to_volatile_crypto_and_real_costs(self):
        g = create_grid(replace(
            source(symbol="BTC/USD", book="crypto", price="100000.00",
                   atr="2000.00", spread="30.00"),
            entry_fee_bps="25", exit_fee_bps="25",
            other_roundtrip_friction_bps="30",
        ))
        self.assertEqual(g.step, "800.00")
        self.assertEqual(g.two_levels_lower_than_reference, "98400.00")
        self.assertEqual(dict(g.levels)[5], "104000.00")

    def test_step_is_rounded_up_to_actual_price_tick(self):
        g = create_grid(source(
            price="100.00", atr="1.03", spread="0.01", tick="0.05"
        ))
        self.assertEqual(g.step, "0.30")
        self.assertEqual(dict(g.levels)[-2], "99.40")

    def test_negative_five_levels_not_accepted(self):
        with self.assertRaisesRegex(ValueError, "FIVE_LOWER_LEVELS"):
            create_grid(source(price="1.00", atr="20.00"))

    def test_one_negative_level_is_warning_not_automatic_entry(self):
        state, row = self.measure("99.00")
        self.assertFalse(state.veto_latched)
        self.assertEqual(row["state"], "C36_RESEARCH_ELIGIBLE_NOT_AN_ORDER")
        self.assertFalse(row["broker_order_sent"])

    def test_exact_minus_two_is_buy_veto(self):
        state, row = self.measure("98.00")
        self.assertTrue(state.veto_latched)
        self.assertEqual(row["state"], "BUY_VETO_LATCHED")
        self.assertTrue(row["crossed_two_levels_below_reference"])
        self.assertFalse(row["broker_order_sent"])

    def test_price_rebound_does_not_reset_veto(self):
        old, _ = self.measure("97.00")
        new, result = self.measure("103.00", state=old, at=AT + 500)
        self.assertTrue(new.veto_latched)
        self.assertEqual(result["state"], "BUY_VETO_LATCHED")

    def test_latch_cannot_be_replaced_by_another_grid_with_same_state(self):
        new_grid = create_grid(replace(
            source(), reference_price="101.00"
        ))
        with self.assertRaisesRegex(ValueError, "GRID_GENERATION"):
            inspect(new_grid, self.latch, quote("103.00"), inventory(),
                    c36_research_gate_passed=True,
                    existing_native_protection_present=False)

    def test_pending_entry_requires_cancel_and_late_fill_reconciliation(self):
        state, row = self.measure(
            "97.50", position=inventory(self.grid, pending="2")
        )
        self.assertEqual(row["state"],
                         "CANCEL_PENDING_ENTRY_AND_RECONCILE_LATE_FILL")
        self.assertTrue(row["pending_entry_cancel_intent_required"])
        self.assertFalse(row["pending_entry_cancel_acknowledged"])
        self.assertTrue(state.veto_latched)

    def test_filled_position_uses_frozen_entry_not_old_anchor(self):
        position = inventory(self.grid, held="2", entry="103.00")
        _, row = self.measure("100.50", position=position)
        self.assertEqual(row["held_position_stop_level"], "101.00")
        self.assertTrue(row["crossed_held_position_two_step_stop"])
        self.assertFalse(row["crossed_two_levels_below_reference"])

    def test_filled_minus_two_requires_exit_but_does_not_claim_fill(self):
        position = inventory(self.grid, held="2", entry="100.00")
        state, row = self.measure("98.00", position=position)
        self.assertEqual(row["state"], "PROTECTIVE_EXIT_REQUIRED_NOT_A_FILL")
        self.assertTrue(row["existing_position_exit_intent_required"])
        self.assertTrue(row["existing_position_is_not_assumed_liquidated"])
        self.assertTrue(state.exit_pending_unconfirmed)
        self.assertFalse(row["actual_broker_stop_fill_proved"])

    def test_held_minus_one_does_not_trigger_stop(self):
        state, row = self.measure("99.00", position=inventory(
            self.grid, held="1", entry="100.00"
        ))
        self.assertFalse(state.exit_pending_unconfirmed)
        self.assertEqual(row["state"], "EXISTING_POSITION_NO_NEW_ENTRY")

    def test_unconfirmed_protective_exit_survives_price_rebound(self):
        position = inventory(self.grid, held="1", entry="100.00")
        first, _ = self.measure("97.00", position=position)
        later, row = self.measure("104.00", position=position,
                                  state=first, at=AT + 500)
        self.assertTrue(later.exit_pending_unconfirmed)
        self.assertEqual(row["state"], "PROTECTIVE_EXIT_REQUIRED_NOT_A_FILL")

    def test_market_staleness_never_grants_buy(self):
        stale = Quote("101.00", "101.10", AT - 60000,
                      AT - 59000, AT)
        _, row = inspect(
            self.grid, self.latch, stale, inventory(),
            c36_research_gate_passed=True,
            existing_native_protection_present=True,
        )
        self.assertEqual(row["state"],
                         "SOURCE_STALE_HALT_BUY_PROTECTION_NOT_RELEASED")
        self.assertTrue(row["existing_native_protection_must_not_be_cancelled"])

    def test_quote_clock_cannot_be_future_or_replayed(self):
        q = Quote("99.00", "99.10", AT + 10, AT + 20, AT)
        with self.assertRaisesRegex(ValueError, "CROSS_CLOCK"):
            inspect(self.grid, self.latch, q, inventory(),
                    c36_research_gate_passed=True,
                    existing_native_protection_present=True)

    def test_quote_bid_ask_cannot_be_crossed(self):
        with self.assertRaisesRegex(ValueError, "CROSSED_QUOTE"):
            inspect(self.grid, self.latch,
                    quote("102.00", ask="101.00"), inventory(),
                    c36_research_gate_passed=True,
                    existing_native_protection_present=True)

    def test_existing_inventory_must_retain_its_original_grid(self):
        with self.assertRaisesRegex(ValueError, "POSITION_OR_RESERVATION"):
            self.measure("97.00", position=Inventory(
                "1", "100.00", "FAKE_GENERATION", "0", None, True
            ))

    def test_no_broker_snapshot_cannot_authorize_buy(self):
        _, row = self.measure("101.00", position=inventory(verified=False))
        self.assertEqual(row["state"],
                         "UNVERIFIED_BROKER_INVENTORY_CASH_ONLY")

    def test_no_c36_cost_adjusted_edge_cannot_authorize_buy(self):
        _, row = self.measure("101.00", candidate=False)
        self.assertEqual(row["state"], "C36_EDGE_GATE_NOT_PROVED_CASH_ONLY")

    def test_rearm_needs_actual_flat_account_and_independent_signal(self):
        breached, _ = self.measure("97.00")
        fresh = create_grid(replace(
            source(price="104.00"), quote_known_at_ms=AT + 400_000,
            decision_at_ms=AT + 410_000, atr_known_at_ms=AT + 100,
        ))
        closes = (
            (AT + 100_000, "101.00"),
            (AT + 200_000, "102.00"),
        )
        with self.assertRaisesRegex(ValueError, "REARM_REQUIRES_NEW_SOURCE"):
            rearm(self.grid, breached, fresh, inventory(),
                  recovery_closes=closes,
                  broker_orders_and_positions_reconciled=False,
                  independent_new_signal_confirmed=True)
        state = rearm(
            self.grid, breached, fresh, inventory(),
            recovery_closes=closes,
            broker_orders_and_positions_reconciled=True,
            independent_new_signal_confirmed=True,
        )
        self.assertFalse(state.veto_latched)
        self.assertEqual(state.generation, fresh.generation)

    def test_rearm_requires_two_later_closed_bars_above_old_anchor(self):
        breached, _ = self.measure("97.00")
        fresh = create_grid(replace(
            source(price="104.00"),
            decision_at_ms=AT + 410_000,
            quote_known_at_ms=AT + 400_000,
            atr_known_at_ms=AT + 100,
        ))
        with self.assertRaisesRegex(ValueError, "REARM_UNCONFIRMED"):
            rearm(self.grid, breached, fresh, inventory(),
                  recovery_closes=(
                      (AT + 100_000, "100.00"),
                      (AT + 200_000, "101.00"),
                  ), broker_orders_and_positions_reconciled=True,
                  independent_new_signal_confirmed=True)

    def test_entry_clock_and_atr_closed_clock_must_not_be_in_future(self):
        with self.assertRaisesRegex(ValueError, "SOURCE_AND_NATIVE"):
            create_grid(replace(source(), atr_known_at_ms=AT + 1))

    def test_grid_requires_native_prefilter_observation(self):
        with self.assertRaisesRegex(ValueError, "SOURCE_AND_NATIVE"):
            create_grid(replace(
                source(), original_native_prefilter_seen=False
            ))

    def test_grid_does_not_accept_unrecognised_tick_size(self):
        with self.assertRaisesRegex(ValueError, "REFERENCE_NOT_ON_KNOWN_TICK"):
            create_grid(source(price="100.01", tick="0.05"))

    def test_risk_capacity_has_original_cash_gross_and_risk_limits(self):
        result = research_capacity(
            self.grid, observed_equity_usd="20000",
            settled_cash_usd="20000", committed_cash_usd="0",
            unsettled_cash_usd="0", already_admitted_gross_usd="0",
            already_reserved_risk_usd="0", admitted_entry_price="100",
            gap_slippage_buffer_bps="40",
            broker_account_reconciled=True,
        )
        notional = float(result["research_notional_max_usd"])
        self.assertLessEqual(notional, 800)
        self.assertLessEqual(notional, 2400)
        self.assertLessEqual(notional *
                             float(result["total_modeled_risk_per_nominal_bps"])
                             / 10000, 50)
        self.assertFalse(result["order_authorized"])

    def test_cash_reservations_can_reduce_notional_to_zero(self):
        r = research_capacity(
            self.grid, observed_equity_usd="20000",
            settled_cash_usd="20000", committed_cash_usd="20000",
            unsettled_cash_usd="0", already_admitted_gross_usd="0",
            already_reserved_risk_usd="0", admitted_entry_price="100",
            gap_slippage_buffer_bps="40",
            broker_account_reconciled=True,
        )
        self.assertEqual(r["research_notional_max_usd"], "0.00")

    def test_no_verified_account_produces_zero_research_size(self):
        r = research_capacity(
            self.grid, observed_equity_usd="20000",
            settled_cash_usd="20000", committed_cash_usd="0",
            unsettled_cash_usd="0", already_admitted_gross_usd="0",
            already_reserved_risk_usd="0", admitted_entry_price="100",
            gap_slippage_buffer_bps="40",
            broker_account_reconciled=False,
        )
        self.assertEqual(r["research_notional_max_usd"], "0.00")

    def test_compound_equity_above_20k_does_not_raise_admission_base(self):
        r = research_capacity(
            self.grid, observed_equity_usd="35000",
            settled_cash_usd="35000", committed_cash_usd="0",
            unsettled_cash_usd="0", already_admitted_gross_usd="0",
            already_reserved_risk_usd="0", admitted_entry_price="100",
            gap_slippage_buffer_bps="40",
            broker_account_reconciled=True,
        )
        self.assertEqual(r["frozen_capital_base_usd"], "20000")
        self.assertLessEqual(float(r["research_notional_max_usd"]), 800)

    def test_negative_market_or_fee_inputs_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "INVALID_"):
            create_grid(replace(source(), spread_price="-1"))

    def test_data_provenance_is_never_upgraded_to_authenticated(self):
        self.assertFalse(self.grid.source_data_independently_authenticated)
        self.assertFalse(self.grid.executable_orders_allowed)
        self.assertEqual(self.grid.N9S, "NO_GO")
        self.assertTrue(json.dumps(asdict(self.grid)))


if __name__ == "__main__":
    unittest.main()
