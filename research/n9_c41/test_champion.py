"""C41 engineering test; all forecasts and fills in unit cases are synthetic."""
from __future__ import annotations

import unittest
from dataclasses import replace

from champion import (
    ClosedBar, FinancedAccount, MarketSnapshot, Position, evidence_gate,
    evaluate_entry, exit_step, policy_digest,
)

NOW = 1_800_000_000_000


def setup_snapshot(
    *,
    symbol: str = "NVDA", book: str = "equity",
    signal_volume: str = "140",
    gross_lower: str = "300",
    fee: str = "13", momentum: str = "0.03",
    forecast_calibrated: bool = True,
) -> MarketSnapshot:
    first = 100.0
    # Ten source bars and one final bar, momentum last/5th-prior = 3%.
    closes = [first] * 10 + [first * (1 + float(momentum))]
    bars = tuple(ClosedBar(
        at_ms=NOW - (11 - i) * 86_400_000,
        known_at_ms=NOW - (11 - i) * 86_400_000 + 3_600_000,
        close=f"{c:.3f}",
        volume="100" if i < 10 else signal_volume,
    ) for i, c in enumerate(closes))
    return MarketSnapshot(
        symbol=symbol, book=book, decision_at_ms=NOW,
        bars=bars, bid="100.00", ask="100.05",
        quote_known_at_ms=NOW - 100,
        closed_atr="4.00", tick="0.01",
        round_trip_cost_upper_bps=fee,
        pessimistic_gross_return_lower_bps=gross_lower,
        expected_holding_hours=72, native_prefilter_witness=True,
        forecast_is_prospectively_calibrated=forecast_calibrated,
    )


def account(**kwargs: object) -> FinancedAccount:
    a = FinancedAccount(
        equity_usd="20000", settled_cash_usd="20000",
        committed_usd="0", unsettled_usd="0",
        existing_gross_usd="0", reserved_risk_usd="0",
        existing_position_for_symbol=False,
        pending_order_for_symbol=False,
        reconciled_with_broker_receipts=True,
        risk_halted=False,
    )
    return replace(a, **kwargs)


def position() -> Position:
    return Position(
        entry_price="100.00", frozen_step="1.00",
        entry_known_at_ms=NOW,
        highest_known_bid="100.00", protective_stop="98.00",
        trailing_armed=False, exit_pending=False,
        broker_position_qty="8", round_trip_cost_upper_bps="13",
    )


class ChampionTests(unittest.TestCase):
    def test_versioned_single_candidate_is_fixed(self):
        self.assertEqual(policy_digest(), policy_digest())
        self.assertEqual(len(policy_digest()), 64)

    def test_positive_synthetic_case_is_research_only(self):
        x = evaluate_entry(setup_snapshot(), account())
        self.assertEqual(x["state"], "RESEARCH_SHORTLIST_NOT_AN_ORDER")
        self.assertEqual(x["research_max_notional_usd"], "800.00")
        self.assertFalse(x["native_or_broker_order_authorized"])
        self.assertFalse(x["scenario_lower_bound_actually_proved"])
        self.assertEqual(x["N9S"], "NO_GO")

    def test_rvol_below_1_25_returns_cash(self):
        x = evaluate_entry(setup_snapshot(signal_volume="124"), account())
        self.assertEqual(x["state"], "CASH")
        self.assertEqual(x["reason"], "MOMENTUM_AND_RVOL_NOT_CONFIRMED")

    def test_rvol_at_1_25_is_inclusive(self):
        x = evaluate_entry(setup_snapshot(signal_volume="125"), account())
        self.assertEqual(x["state"], "RESEARCH_SHORTLIST_NOT_AN_ORDER")
        self.assertEqual(x["rvol10"], "1.25")

    def test_momentum_below_required_regime_returns_cash(self):
        x = evaluate_entry(setup_snapshot(momentum="0.005"), account())
        self.assertEqual(x["state"], "CASH")

    def test_crypto_has_stricter_momentum_than_equity(self):
        equity = setup_snapshot(momentum="0.02")
        crypto = setup_snapshot(symbol="BTC/USD", book="crypto",
                                momentum="0.02", fee="100")
        self.assertEqual(
            evaluate_entry(equity, account())["state"],
            "RESEARCH_SHORTLIST_NOT_AN_ORDER",
        )
        self.assertEqual(
            evaluate_entry(crypto, account())["state"], "CASH"
        )

    def test_crypto_cost_must_be_paid_before_selection(self):
        crypto = setup_snapshot(symbol="BTC/USD", book="crypto",
                                fee="100", momentum="0.04",
                                gross_lower="170")
        x = evaluate_entry(crypto, account())
        self.assertEqual(x["state"], "CASH")
        self.assertEqual(x["reason"], "NET_LOWER_BOUND_CANNOT_PAY_HURDLE")

    def test_no_stale_or_unreconciled_forecast_can_buy(self):
        x = evaluate_entry(setup_snapshot(
            forecast_calibrated=False
        ), account())
        self.assertEqual(x["reason"],
                         "LOWER_FORECAST_NOT_PROSPECTIVELY_CALIBRATED")

    def test_old_quote_blocks_even_high_rvol(self):
        s = replace(setup_snapshot(), quote_known_at_ms=NOW - 20000)
        self.assertEqual(
            evaluate_entry(s, account())["reason"], "QUOTE_STALE"
        )

    def test_future_close_bar_cannot_appear_in_signal(self):
        s = setup_snapshot()
        bars = (*s.bars[:-1], replace(
            s.bars[-1], known_at_ms=NOW + 100,
        ))
        with self.assertRaisesRegex(ValueError, "BAR_FUTURE"):
            evaluate_entry(replace(s, bars=bars), account())

    def test_quote_must_not_precede_finished_signal_bar(self):
        s = setup_snapshot()
        s = replace(s, quote_known_at_ms=s.bars[-1].known_at_ms - 1)
        with self.assertRaisesRegex(ValueError, "QUOTE_TIME"):
            evaluate_entry(s, account())

    def test_missing_native_source_witness_fails_closed(self):
        s = replace(setup_snapshot(), native_prefilter_witness=False)
        with self.assertRaisesRegex(ValueError, "SOURCE_OR_HORIZON"):
            evaluate_entry(s, account())

    def test_duplicate_bar_clock_rejected(self):
        s = setup_snapshot()
        bars = (*s.bars[:-1], replace(s.bars[-1], at_ms=s.bars[-2].at_ms))
        with self.assertRaisesRegex(ValueError, "BAR_FUTURE_OR_DUPLICATE"):
            evaluate_entry(replace(s, bars=bars), account())

    def test_all_entries_reconcile_shared_cash_and_risk(self):
        for kwargs in (
            {"reconciled_with_broker_receipts": False},
            {"pending_order_for_symbol": True},
            {"existing_position_for_symbol": True},
            {"risk_halted": True},
        ):
            with self.subTest(kwargs=kwargs):
                x = evaluate_entry(setup_snapshot(), account(**kwargs))
                self.assertEqual(x["state"], "CASH")

    def test_hard_admission_cap_does_not_compound_with_nav(self):
        x = evaluate_entry(setup_snapshot(), account(
            equity_usd="40000", settled_cash_usd="40000"
        ))
        self.assertLessEqual(float(x["research_max_notional_usd"]), 800.0)

    def test_reserved_cash_blocks_new_entry(self):
        x = evaluate_entry(setup_snapshot(), account(
            committed_usd="20000",
        ))
        self.assertEqual(x["reason"], "NO_SETTLED_CAPITAL_OR_RISK_RESERVATION")

    def test_shared_gross_limit_already_consumed(self):
        x = evaluate_entry(setup_snapshot(), account(
            existing_gross_usd="2400",
        ))
        self.assertEqual(x["state"], "CASH")

    def test_hard_72_hours_horizon_cannot_be_relaxed(self):
        s = replace(setup_snapshot(), expected_holding_hours=73)
        with self.assertRaisesRegex(ValueError, "SOURCE_OR_HORIZON"):
            evaluate_entry(s, account())

    def test_exit_arm_plus2_without_executing_partial_sell(self):
        p, x = exit_step(position(), "102.00", NOW+3600000)
        self.assertTrue(p.trailing_armed)
        self.assertEqual(p.protective_stop, "100.00")
        self.assertEqual(x["state"], "HOLD_UNDER_FROZEN_STOP")
        self.assertIsNone(x["hard_takeprofit_ceiling"])
        self.assertFalse(x["broker_order_sent"])

    def test_peak_plus4_preserves_profit_without_hard_tp(self):
        a, _ = exit_step(position(), "104.00", NOW+3600000)
        self.assertEqual(a.protective_stop, "102.00")
        _, r = exit_step(a, "101.00", NOW+7200000)
        self.assertEqual(r["state"], "EXIT_INTENT_NOT_A_FILL")
        self.assertFalse(r["fill_confirmed"])

    def test_rebound_does_not_clear_exit_pending(self):
        a, _ = exit_step(position(), "97.00", NOW+3600000)
        b, r = exit_step(a, "106.00", NOW+7200000)
        self.assertTrue(b.exit_pending)
        self.assertEqual(r["state"], "EXIT_INTENT_NOT_A_FILL")

    def test_time_limit_at_72_hours_requires_exit_intent(self):
        _, r = exit_step(position(), "101.00", NOW+72*3600000)
        self.assertEqual(r["reason"], "MAX_72H")
        self.assertFalse(r["fill_confirmed"])

    def test_entry_stop_cannot_be_reanchored_by_price_rebound(self):
        p, _ = exit_step(position(), "102.00", NOW+3600000)
        self.assertEqual(p.entry_price, "100.00")
        self.assertEqual(p.frozen_step, "1.00")

    def test_no_paper_or_live_financial_go_with_missing_receipts(self):
        g = evidence_gate(
            actual_receipts=0,
            independently_registered_before_first_trial=False,
            original_and_cash_controls_reconciled=False,
            prebar_source_universe_complete=False,
            corrected_log_lower_vs_both_benchmarks_bps_per_day=None,
            independent_review_completed=False,
        )
        self.assertIn("NO_REAL_BROKER_FILL_RECEIPTS", g["missing_or_blocked"])
        self.assertFalse(g["financial_GO"])
        self.assertEqual(g["N9S"], "NO_GO")

    def test_corrected_lower_less_than_hurdle_is_rejected(self):
        g = evidence_gate(
            actual_receipts=30,
            independently_registered_before_first_trial=True,
            original_and_cash_controls_reconciled=True,
            prebar_source_universe_complete=True,
            corrected_log_lower_vs_both_benchmarks_bps_per_day="0.221296",
            independent_review_completed=True,
        )
        self.assertIn("BELOW_OR_EQUAL_FROZEN_1BP_PER_DAY",
                      g["missing_or_blocked"])
        self.assertEqual(g["N9S"], "NO_GO")

    def test_self_asserted_flags_never_auto_promote_to_go(self):
        g = evidence_gate(
            actual_receipts=1000,
            independently_registered_before_first_trial=True,
            original_and_cash_controls_reconciled=True,
            prebar_source_universe_complete=True,
            corrected_log_lower_vs_both_benchmarks_bps_per_day="2.0",
            independent_review_completed=True,
        )
        self.assertTrue(g["externally_reviewable"])
        self.assertTrue(g["automated_GO_prohibited"])
        self.assertFalse(g["financial_GO"])

    def test_boolean_cannot_fabricate_broker_receipt_count(self):
        g = evidence_gate(
            actual_receipts=True,
            independently_registered_before_first_trial=True,
            original_and_cash_controls_reconciled=True,
            prebar_source_universe_complete=True,
            corrected_log_lower_vs_both_benchmarks_bps_per_day="2",
            independent_review_completed=True,
        )
        self.assertIn("NO_REAL_BROKER_FILL_RECEIPTS", g["missing_or_blocked"])

    def test_sealed_m10_is_mandatory(self):
        g = evidence_gate(
            actual_receipts=100,
            independently_registered_before_first_trial=True,
            original_and_cash_controls_reconciled=True,
            prebar_source_universe_complete=True,
            corrected_log_lower_vs_both_benchmarks_bps_per_day="2",
            independent_review_completed=True,
            final_m10_accounts_sealed=3199,
        )
        self.assertIn("SEALED_M10_SOURCE_CHANGED", g["missing_or_blocked"])


if __name__ == "__main__":
    unittest.main()
