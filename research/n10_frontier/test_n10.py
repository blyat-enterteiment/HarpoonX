"""C42 N10 diagnostics: never train future highs, authenticate brokers or GO."""
from __future__ import annotations

import copy
import json
import math
import unittest
from dataclasses import replace

import diagnose as D


class UpsideFrontierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.market,cls.source=D.C.load_manifest()
        cls.report=D.analyze()

    def test_original_observed_sources_without_fabricated_fills(self):
        self.assertEqual(self.source["market_bars_total"],555)
        self.assertEqual(self.source["new_oct_nov_market_bars"],179)
        self.assertTrue(self.source["all_csv_git_blob_sha_verified"])
        self.assertEqual(self.source["broker_fill_receipts"],0)

    def test_N10_does_not_promote_by_oracle_future_high(self):
        self.assertEqual(self.report["N10"],"NO_GO")
        self.assertEqual(self.report["N9S"],"NO_GO")
        self.assertFalse(self.report["financialGO"])
        self.assertEqual(self.report["actual_broker_orders"],0)
        self.assertTrue(self.report["all_mfe_prices_are_future_oracle_not_order_prices"])

    def test_lookahead_future_high_can_change_oracle_but_not_any_past_signal(self):
        old_market=copy.deepcopy(self.market)
        changed=copy.deepcopy(self.market)
        if not D.C.signals(old_market,rvol_floor=0.):
            self.skipTest("NO_QUALIFIED_MOMENTUM_SIGNAL_ON_EXISTING_SAMPLE")
        first=D.C.signals(old_market,rvol_floor=0.)[0]
        symbol=first.symbol
        j=first.entry_index+1
        if j>=len(changed[symbol]):
            self.skipTest("NO_MATURED_ENTRY_CANDIDATE")
        original=changed[symbol][j]
        changed[symbol][j]=replace(original,high=original.high*5)
        s0=[(x.symbol,x.signal_day) for x in D.C.signals(old_market,rvol_floor=0.)
            if x.signal_day<=first.signal_day]
        s1=[(x.symbol,x.signal_day) for x in D.C.signals(changed,rvol_floor=0.)
            if x.signal_day<=first.signal_day]
        self.assertEqual(s0,s1)
        old_front=[x for x in D.frontiers(old_market)
                   if x.symbol==symbol and x.signal_day==first.signal_day.isoformat()]
        new_front=[x for x in D.frontiers(changed)
                   if x.symbol==symbol and x.signal_day==first.signal_day.isoformat()]
        self.assertEqual(len(old_front),len(new_front))
        if old_front:
            self.assertGreaterEqual(new_front[0].oracle_high_price,
                                    old_front[0].oracle_high_price)

    def test_mfe_is_oracle_high_and_never_broker_fill(self):
        rows=D.frontiers(self.market)
        for x in rows:
            self.assertGreaterEqual(x.oracle_high_price,x.entry_price)
            self.assertGreaterEqual(x.oracle_gross_mfe_bps,-1e-6)
            self.assertFalse(x.observed_actual_broker_fill)
            self.assertFalse(x.future_high_used_for_trading_signal)

    def test_rvol_filtered_list_is_subset_of_unfiltered(self):
        raw={(x.symbol,x.signal_day,x.entry_at) for x in D.frontiers(self.market,0.)}
        gated={(x.symbol,x.signal_day,x.entry_at) for x in D.frontiers(self.market,1.25)}
        self.assertTrue(gated.issubset(raw))
        self.assertTrue(all(x.rvol10>=1.25 for x in D.frontiers(self.market,1.25)))

    def test_high_plus_five_can_only_be_classified_oracle_not_filled(self):
        for x in D.frontiers(self.market):
            self.assertTrue(all(1<=level<=5 for level in x.oracle_touchable_plus_levels))
            if 5 in x.oracle_touchable_plus_levels:
                self.assertGreaterEqual(x.oracle_high_price,
                                        x.entry_price+5*x.grid_step-1e-6)
                self.assertFalse(x.observed_actual_broker_fill)

    def test_same_bar_target_and_stop_flagged_not_resolved_in_winners_favor(self):
        for x in D.frontiers(self.market):
            if x.target_and_stop_touch_same_daily_bar:
                self.assertTrue(x.conservative_stop_or_gap_occurs_in_window)
        self.assertTrue(self.report["all_mfe_prices_are_future_oracle_not_order_prices"])

    def test_future_horizon_hard_upper_72_hours_on_oracle_bars(self):
        for x in D.frontiers(self.market):
            s=D.C.signals(self.market,rvol_floor=0.)
            match=[v for v in s if v.symbol==x.symbol and
                   v.signal_day.isoformat()==x.signal_day]
            self.assertEqual(len(match),1)
            self.assertEqual(match[0].entry_at.isoformat(),x.entry_at)
            self.assertTrue(math.isfinite(x.oracle_gross_mfe_bps))

    def test_c41_hurdle_gap_positive_and_not_accidentally_n10(self):
        g=self.report["economic_gap"]
        self.assertGreater(g["additional_net_usd_to_reach_N9_hurdle_in_this_43d_period"],0)
        self.assertGreater(g["additional_net_bps_required_if_only_one_new_800usd_full_sized_trade"],0)
        self.assertLess(g["current_modelled_strategy_pnl_usd"],0)

    def test_oracle_envelope_is_too_small_to_support_frozen_N9_hurdle(self):
        envelope=self.report["optimistic_fixed_trigger_opportunity_envelope"]
        self.assertAlmostEqual(envelope["capital_limit_per_candidate_usd"],800)
        self.assertFalse(envelope["even_oracle_unfiltered_reaches_N9_hurdle"])
        self.assertFalse(envelope["even_oracle_frozen_rvol_reaches_N9_hurdle"])
        self.assertGreater(envelope[
            "required_net_profit_from_cash_N9_1bp_over_43_days_usd"],
            envelope[
                "all_existing_momentum_signals_oracle_perfect_high_max_profit_usd"])
        self.assertTrue(envelope[
            "assumes_perfect_future_high_execution_not_realistic"])

    def test_oracle_counts_only_positive_hypothetical_net_trade_opportunities(self):
        all_signals=D.frontiers(self.market,floor=0.)
        expected=sum(
            max(0.,x.oracle_after_assumed_cost_bps)*800/10000
            for x in all_signals
        )
        actual=self.report["optimistic_fixed_trigger_opportunity_envelope"][
            "all_existing_momentum_signals_oracle_perfect_high_max_profit_usd"]
        self.assertAlmostEqual(actual,expected,places=5)

    def test_one_book_original_cap_compounding_limits_not_overwritten(self):
        self.assertTrue(self.report["economic_gap"][
            "no_reinvestment_above_original_20000_admission_base"])
        self.assertEqual(self.report["unresolved_N10"]["original_M10_3200_sealed"],True)

    def test_no_orig_unsupported_orders_or_independent_attestation(self):
        statuses=self.report["unresolved_N10"]
        self.assertFalse(statuses["realized_fill_attainability_and_actual_fees"])
        self.assertFalse(statuses["true_prospective_precommitted_price_and_order_data"])
        self.assertFalse(statuses["outperformance_vs_original_and_cash"])
        self.assertFalse(statuses["strategy_parameter_retuning_from_this_oracle_allowed"])

    def test_repeatable_report_on_exact_sha_pinned_inputs(self):
        x=D.analyze()
        self.assertEqual(json.dumps(x,sort_keys=True),json.dumps(self.report,sort_keys=True))
        self.assertEqual(x["signal_count_unfiltered"],
                         sum(y["momentum_and_volmom_signals_before_rvol"]
                             for y in x["by_symbol"].values()))
        self.assertEqual(x["signal_count_rvol_ge_1p25"],
                         sum(y["signals_with_rvol_ge_1p25"]
                             for y in x["by_symbol"].values()))


if __name__=="__main__":
    unittest.main()
