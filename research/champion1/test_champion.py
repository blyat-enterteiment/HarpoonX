"""Adversarial C41 frozen single-policy / observed provider bars regression tests.

No network, orders, fills or original-C22 economic GO in this test.
"""
from __future__ import annotations

import json
import math
import shutil
import tempfile
import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import evaluate_champion as C


class FrozenChampionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.market, cls.source = C.load_manifest()
        cls.result = C.evaluate()

    def test_new_oct_nov_179_and_prior_376_verified_provider_bars(self):
        self.assertEqual(self.source["market_bars_total"], 555)
        self.assertEqual(self.source["new_oct_nov_market_bars"], 179)
        self.assertEqual(set(self.market), set(C.SYMBOLS))
        self.assertEqual(sorted(len(x) for x in self.market.values()),
                         [95, 95, 95, 135, 135])
        self.assertTrue(self.source["all_csv_git_blob_sha_verified"])

    def test_frozen_before_new_api_query_but_not_independent_time_authority(self):
        self.assertEqual(self.result["frozen_before_new_API_query_commit"],
                         "a8eb6029f026131d375f791f9fc439a4c2a4c44f")
        self.assertFalse(self.result["blocked_contracts"]["external_rfc3161_preregistration"])
        self.assertFalse(self.result["blocked_contracts"]["actual_forward_observation_after_preoutcome_lock"])

    def test_rvol_uses_only_prior_ten_bars_denominator(self):
        bars = self.market["SPY"]
        i = next(i for i,b in enumerate(bars) if b.day >= C.TARGET_START)
        expected = bars[i].volume / (sum(x.volume for x in bars[i-10:i])/10)
        self.assertAlmostEqual(C.rvol10(bars,i),expected)
        self.assertNotIn(bars[i], bars[i-10:i])

    def test_only_prior_closed_volumes_go_into_each_signal(self):
        market = {k:list(v) for k,v in self.market.items()}
        source = C.signals(market)
        changed = {k:list(v) for k,v in market.items()}
        after = date(2026,10,20)
        for symbol in changed:
            changed[symbol] = [
                replace(b,volume=b.volume*1_000_000,high=b.high*2)
                if b.day>after else b
                for b in changed[symbol]
            ]
        left = [(s.symbol,s.signal_day) for s in source if s.signal_day<=after]
        right = [(s.symbol,s.signal_day) for s in C.signals(changed)
                 if s.signal_day<=after]
        self.assertEqual(left,right)

    def test_no_same_day_or_next_day_entry_from_completed_signal(self):
        for s in C.signals(self.market):
            bars=self.market[s.symbol]
            i=next(i for i,b in enumerate(bars) if b.day==s.signal_day)
            self.assertEqual(s.entry_index,i+2)
            self.assertEqual(s.entry_at.date(),bars[i+2].day)
            self.assertGreater(bars[i+2].day,bars[i+1].day)

    def test_rvol_filter_set_to_frozen_1_25(self):
        full = C.signals(self.market,rvol_floor=0)
        filtered = C.signals(self.market,rvol_floor=1.25)
        self.assertTrue(all(x.rvol10>=1.25 for x in filtered))
        self.assertTrue(set(filtered).issubset(set(full)))
        self.assertEqual(self.result["benchmarks"][
            "CHAMPION1_MOMENTUM5_RVOL_GE_1P25_TRAIL2"]["rvol_threshold"],1.25)

    def test_negative_rvol_threshold_is_not_a_useful_strategy(self):
        with self.assertRaisesRegex(ValueError,"RVOL_THRESHOLD"):
            C.signals(self.market,rvol_floor=-1)

    def test_symbol_prices_are_datetime_aware_including_dst_change(self):
        spy_before=C.open_at(date(2026,10,30),"SPY")
        spy_after=C.open_at(date(2026,11,2),"SPY")
        self.assertEqual(spy_before.hour,13)
        self.assertEqual(spy_after.hour,14)
        self.assertEqual(C.open_at(date(2026,11,2),"BTC/USD").hour,0)

    def test_fee_book_and_stress_counts_correctly_two_taker_sides(self):
        self.assertEqual(C.costs("BTC/USD"),100)
        self.assertEqual(C.costs("ETH/USD",stress=True),170)
        self.assertEqual(C.costs("SPY"),13)
        self.assertEqual(C.costs("SPY",stress=True),26)

    def test_open_price_is_only_modelled_at_entry_and_not_input_to_signal(self):
        signals=C.signals(self.market)
        if not signals:
            self.skipTest("no qualifying signals in target")
        first=signals[0]
        data={k:list(v) for k,v in self.market.items()}
        b=data[first.symbol][first.entry_index]
        data[first.symbol][first.entry_index]=replace(
            b,open=b.open*1.01,high=max(b.high,b.open*1.01),
            low=min(b.low,b.open))
        before=[(x.symbol,x.signal_day) for x in signals
                if x.signal_day<=first.signal_day]
        after=[(x.symbol,x.signal_day) for x in C.signals(data)
               if x.signal_day<=first.signal_day]
        self.assertEqual(before,after)

    def test_exit_protection_never_presumes_verified_stop_or_takeprofit_fill(self):
        c=self.result["benchmarks"]["CHAMPION1_MOMENTUM5_RVOL_GE_1P25_TRAIL2"]
        for t in c["trades"]:
            self.assertFalse(t["broker_fill_confirmed"])
            self.assertLessEqual(t["holding_hours"],72)
            self.assertGreaterEqual(t["holding_hours"],0)
            self.assertLessEqual(t["nominal_usd"],800.000001)
            self.assertLessEqual(t["reserved_risk_usd"],50.000001)

    def test_cash_has_exactly_zero_yield_hypothesis(self):
        c=self.result["benchmarks"]["CASH_ZERO_YIELD"]
        self.assertEqual(c["modelled_net_pnl_usd"],0.)
        self.assertEqual(c["terminal_equity_usd"],20000.)

    def test_one_account_ledger_pnl_reconciles_terminal_wealth(self):
        for key in ("CHAMPION1_MOMENTUM5_RVOL_GE_1P25_TRAIL2",
                    "MOMENTUM5_NO_RVOL_TRAIL2_NOT_ORIGINAL",
                    "CHAMPION1_INDEPENDENTLY_RESIZED_COST_STRESS"):
            data=self.result["benchmarks"][key]
            self.assertAlmostEqual(data["terminal_equity_usd"],
                20000.+data["modelled_net_pnl_usd"],places=4)
            self.assertAlmostEqual(
                sum(t["modelled_net_pnl_usd"] for t in data["trades"]),
                data["modelled_net_pnl_usd"],places=3)

    def test_modelled_taker_fees_are_not_broker_cost_receipts(self):
        for key in self.result["benchmarks"]:
            v=self.result["benchmarks"][key]
            if "broker_fills_authenticated" in v:
                self.assertEqual(v["broker_fills_authenticated"],0)
        self.assertFalse(self.result["blocked_contracts"]["alpaca_broker_fills_and_costs_authenticated"])

    def test_order_budget_is_shared_and_hard_original_20k_base(self):
        result=C.simulate(self.market)
        for row in result["trades"]:
            self.assertLessEqual(row["nominal_usd"],.04*20000)
            self.assertLessEqual(row["reserved_risk_usd"],.0025*20000)
        self.assertLessEqual(result["max_holding_hours"],72)

    def test_best_winner_removal_cannot_improve_reported_pnl(self):
        b=self.result["benchmarks"]
        original=b["CHAMPION1_MOMENTUM5_RVOL_GE_1P25_TRAIL2"]["modelled_net_pnl_usd"]
        sensitivity=b["CHAMPION1_LEAVE_BEST_TRADE_OUT_FIXED_NOT_REOPTIMIZED"]
        if sensitivity["excluded_trade_pnl_usd"]>=0:
            self.assertLessEqual(sensitivity["modelled_net_pnl_usd"],original)
        self.assertTrue(sensitivity["not_a_replayed_wealth_path"])

    def test_pair_stress_retains_quantities_and_never_improves_pnl(self):
        b=self.result["benchmarks"]
        original=b["CHAMPION1_MOMENTUM5_RVOL_GE_1P25_TRAIL2"]["modelled_net_pnl_usd"]
        stress=b["CHAMPION1_PAIRED_SAME_TRADES_COST_STRESS"]
        self.assertLessEqual(stress["modelled_net_pnl_usd"],original+1e-7)
        self.assertTrue(stress["nominal_quantities_and_exit_times_held_constant"])

    def test_opportunity_generator_does_not_use_future_prices_as_features(self):
        before=C.signals(self.market)
        after_data={k:list(v) for k,v in self.market.items()}
        for symbol,rows in after_data.items():
            after_data[symbol]=[
                replace(b,high=b.high*3) if b.day>=date(2026,11,10) else b
                for b in rows
            ]
        a=[(x.symbol,x.signal_day) for x in before
           if x.signal_day<date(2026,11,10)]
        b=[(x.symbol,x.signal_day) for x in C.signals(after_data)
           if x.signal_day<date(2026,11,10)]
        self.assertEqual(a,b)

    def test_unsupported_original_C22_comparison_never_fabricated(self):
        self.assertFalse(self.result["blocked_contracts"]["true_original_C22_six_semantic_parity"])
        self.assertFalse(self.result["financialGO"])
        self.assertEqual(self.result["N9S"],"NO_GO")

    def test_no_market_seeds_or_paper_live_orders(self):
        self.assertEqual(self.result["real_orders_created"],0)
        self.assertEqual(self.result["blocked_contracts"]["final_M10_accounts_sealed"],3200)

    def test_dataframe_csv_tamper_is_detected_by_git_blob_sha(self):
        with tempfile.TemporaryDirectory() as temp:
            dest=Path(temp)
            shutil.copytree(C.HERE,dest/"study",ignore=shutil.ignore_patterns("__pycache__"))
            p=dest/"study"/"target"/"BTCUSD_us_1day.csv"
            raw=p.read_bytes()
            p.write_bytes(raw[:-2]+(b"9" if raw[-2:-1]!=b"9" else b"8")+raw[-1:])
            with self.assertRaisesRegex(ValueError,"DATA_BYTES_TAMPERED"):
                C.load_manifest(dest/"study")

    def test_repeated_replay_is_deterministic_on_identical_inputs(self):
        self.assertEqual(self.result,C.evaluate())

    def test_stale_or_future_market_bars_are_not_fabricated(self):
        self.assertEqual(self.market["BTC/USD"][-1].day,TARGET_END if False else C.TARGET_END)
        for name in C.SYMBOLS:
            self.assertEqual(self.market[name][-1].day,C.TARGET_END)

    def test_short_term_reversal_does_not_change_frozen_policy(self):
        rule=json.loads((C.HERE/"FROZEN_BEFORE_NEW_DATA.json").read_text())
        self.assertEqual(rule["single_frozen_candidate"]["rvol10_threshold"],1.25)
        self.assertEqual(rule["single_frozen_candidate"]["holding_max_hours"],72)
        self.assertIn("retune RVOL after Oct-Nov results",rule["forbidden"])


if __name__=="__main__":
    unittest.main()
