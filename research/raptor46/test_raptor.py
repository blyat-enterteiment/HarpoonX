"""C46 Raptor real-IEX-bar retrospective replay and synthetic stop tests.

The 16 screen tickers are post-selected. No SIP, authentic fills, OPRA or
prospective N9 economic certification from a one-day partial-IEX replay.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import assess_breakout as A
import local_fishing_net as F
import replay_net as R


T0=datetime.fromisoformat("2026-11-13T14:30:00+00:00")


def bar(offset:int, o:float, h:float, l:float, c:float, volume:float=250)->A.Bar:
    return A.Bar(T0+timedelta(minutes=5*offset),o,h,l,c,volume)


def config(anchor:float=100,breakout:float=.03)->F.NetConfig:
    return F.NetConfig("SYNTH",anchor,breakout,1.0,.10,13.,150.)


def funded()->F.FundedSnapshot:
    return F.FundedSnapshot(20_000,20_000,0,0,0,0,True,True,False)


def confirmed()->tuple[F.NetState,F.NetConfig]:
    cfg=config()
    state=F.build(cfg)
    a=[bar(0,103,104,102.5,103.2),
       bar(1,103.3,104,103,103.5)]
    for b in a:
        state,_=F.on_completed_bar(state,cfg,b)
    if state.name!="CONFIRMED":
        raise AssertionError("synthetic qualifying two closing bars")
    return state,cfg


class RaptorNetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw,cls.source=A.load()
        cls.touch=A.report()
        cls.result=R.report()

    def test_all_808_provider_bars_sha_and_16_visible_tickers(self):
        self.assertEqual(self.source["original_IEX_5_min_bars"],808)
        self.assertEqual(self.source["selected_visible_symbols"],16)
        self.assertEqual(len(self.raw),16)
        self.assertFalse(self.source["source_is_executable_bid_ask"])
        self.assertFalse(self.source["screener_RVOL_time_of_day_history_available"])

    def test_missing_source_not_invented(self):
        self.assertEqual(len(self.raw["WVAV"]),0)
        self.assertEqual(sum(b.at.date().isoformat()=="2026-11-13"
                             for b in self.raw["ATXG"]),0)
        self.assertEqual(sum(b.at.date().isoformat()=="2026-11-13"
                             for b in self.raw["TGHL"]),2)

    def test_3_percent_touch_also_end_red_two_symbols(self):
        three=self.touch["tests"]["3"]
        self.assertEqual(three["historical_IEX_high_touches"],6)
        self.assertEqual(three[
            "historical_touch_but_day_end_below_previous_IEX"],2)
        self.assertIn("ICMB",three["touch_tickers"])
        self.assertIn("TGEN",three["touch_tickers"])

    def test_4_percent_touch_also_end_red(self):
        four=self.touch["tests"]["4"]
        self.assertEqual(four["historical_IEX_high_touches"],5)
        self.assertEqual(four[
            "historical_touch_but_day_end_below_previous_IEX"],1)
        self.assertIn("ICMB",four["touch_tickers"])

    def test_no_3percent_next_open_is_assumed_broker_fill(self):
        self.assertEqual(self.result["paper_orders"],0)
        self.assertEqual(self.result["live_orders"],0)
        self.assertEqual(self.result["N9S"],"NO_GO")
        self.assertEqual(self.result["N10"],"NO_GO")
        self.assertFalse(self.result[
            "Finviz_full_RVOL_GT5_screen_proved_in_original_hour"])

    def test_30percent_screenshot_winner_tghl_has_only_two_bars(self):
        for p in ("3","4"):
            row=next(x for x in self.result["sensitivity"][p][
                "ticker_rejection_or_state"] if x["symbol"]=="TGHL")
            self.assertEqual(row["posthoc_entry_status"],
                "INSUFFICIENT_PREVIOUS_OR_DAY_5MIN_COVERAGE")
        self.assertTrue(self.result["selection_lookahead_bias_present"])

    def test_3pct_threshold_requires_two_confirmed_closed_bars(self):
        cfg=config()
        state=F.build(cfg)
        state,_=F.on_completed_bar(state,cfg,bar(0,103,104,102.5,103.2))
        self.assertEqual(state.name,"WATCH")
        state,_=F.on_completed_bar(state,cfg,bar(1,103.2,104,103,103.8))
        self.assertEqual(state.name,"CONFIRMED")

    def test_next_open_must_be_contiguous_and_within_chase_ceiling(self):
        state,cfg=confirmed()
        with self.assertRaisesRegex(ValueError,"NEXT_OPEN_NOT_CAUSAL"):
            F.next_open_entry(state,cfg,bar(3,103.5,104,103,104),funded())
        no_buy,reason=F.next_open_entry(
            state,cfg,bar(2,107,108,106,107),funded())
        self.assertEqual(no_buy.name,"CANCELLED_ENTRY")
        self.assertFalse(reason["actual_broker_order"])

    def test_next_open_shadow_buy_and_frozen_two_level_stop(self):
        state,cfg=confirmed()
        entry,reason=F.next_open_entry(
            state,cfg,bar(2,103.5,104,103,103.8),funded())
        self.assertEqual(entry.name,"SHADOW_LONG")
        self.assertEqual(entry.hypothetical_entry,103.5)
        self.assertLess(entry.frozen_initial_stop or 0,103.5)
        self.assertFalse(reason["actual_broker_order"])
        self.assertFalse(reason["take_profit_fixed"])

    def test_entry_bar_low_can_stop_before_high_profit_ratcheting(self):
        state,cfg=confirmed()
        entry,_=F.next_open_entry(
            state,cfg,bar(2,103.5,136,101,135.5),funded())
        stopped,event=F.finish_entry_bar(
            entry,cfg,bar(2,103.5,136,101,135.5))
        self.assertEqual(stopped.name,"SHADOW_STOP_UNVERIFIED")
        self.assertEqual(stopped.exit_model_reason,
                         "FIRST_5MIN_ENTRY_BAR_STOP_TOUCH_UNVERIFIED")
        self.assertFalse(event["actual_broker_fill"])
        self.assertEqual(stopped.protective_trailing_stop,
                         entry.frozen_initial_stop)

    def test_leaves_30percent_winner_running_with_no_fixed_tp(self):
        state,cfg=confirmed()
        entry,_=F.next_open_entry(
            state,cfg,bar(2,103.5,104,103.1,103.8),funded())
        state,_=F.finish_entry_bar(
            entry,cfg,bar(2,103.5,104,103.1,103.8))
        self.assertEqual(state.name,"SHADOW_LONG")
        new,e=F.on_completed_bar(
            state,cfg,bar(3,133,134,132.8,133.7))
        self.assertEqual(new.name,"SHADOW_LONG")
        self.assertGreater(new.protective_trailing_stop or 0,
                           state.protective_trailing_stop or 0)
        self.assertEqual(e["status"],"HOLD_RUNNER_NO_FIXED_TAKE_PROFIT")
        self.assertGreater(new.highest_verified_completed_bar_high or 0,130)

    def test_runner_stop_never_moves_down_when_new_bar_is_lower(self):
        state,cfg=confirmed()
        entry,_=F.next_open_entry(
            state,cfg,bar(2,103.5,104,103.1,103.8),funded())
        state,_=F.finish_entry_bar(entry,cfg,
                                  bar(2,103.5,104,103.1,103.8))
        state,_=F.on_completed_bar(state,cfg,
                                  bar(3,120,121,119.5,120))
        previous=state.protective_trailing_stop or 0
        if state.name=="SHADOW_LONG":
            # model price still above prior stop, but high is lower
            state,_=F.on_completed_bar(state,cfg,
                                      bar(4,120,120.2,119.5,120))
            self.assertGreaterEqual(state.protective_trailing_stop or 0,
                                    previous)

    def test_fake_high_and_low_same_bar_does_not_get_profitable_exit(self):
        state,cfg=confirmed()
        entry,_=F.next_open_entry(
            state,cfg,bar(2,103.5,104,103.1,103.8),funded())
        state,_=F.finish_entry_bar(entry,cfg,
                                  bar(2,103.5,104,103.1,103.8))
        stop=state.protective_trailing_stop or 0
        stopped,e=F.on_completed_bar(
            state,cfg,bar(3,105,140,stop-.1,139))
        self.assertEqual(stopped.name,"SHADOW_STOP_UNVERIFIED")
        self.assertEqual(stopped.exit_model_price,stop)
        self.assertEqual(stopped.protective_trailing_stop,stop)
        self.assertFalse(e["actual_broker_fill"])

    def test_missing_five_minute_bar_halts_new_buy_proxies(self):
        cfg=config()
        state=F.build(cfg)
        state,_=F.on_completed_bar(state,cfg,
                                  bar(0,102,104,101,103.5))
        state,evt=F.on_completed_bar(state,cfg,
                                    bar(2,103,104,102.5,103.6))
        self.assertEqual(state.name,"HALTED_MISSING_SOURCE")
        self.assertTrue(evt["IEX_gap_or_session_break"])

    def test_book_enforces_shared_cash_and_risk(self):
        state,cfg=confirmed()
        nominal,reserved=F.affordable(cfg,state,103.5,funded())
        self.assertLessEqual(nominal,800)
        self.assertLessEqual(reserved,50.000001)
        no_cash=replace(funded(),settled_cash_usd=0.)
        self.assertEqual(F.affordable(cfg,state,103.5,no_cash)[0],0.)

    def test_fees_cannot_make_identical_counterfactual_more_profitable(self):
        for p in ("3","4"):
            c=self.result["sensitivity"][p]["cost_sensitivity"]
            v=[c[str(x)]["hypothetical_one_day_net_pnl_usd"]
               for x in (100.,300.,500.)]
            self.assertGreaterEqual(v[0],v[1])
            self.assertGreaterEqual(v[1],v[2])
            self.assertTrue(all(x["broker_fills"]==0 for x in c.values()))

    def test_one_day_mark_is_not_72h_swing_or_original(self):
        self.assertTrue(self.result[
            "two_day_IEX_observation_not_72_hour_swing_evaluation"])
        self.assertFalse(self.result["N9_population_alpha_FWER_025_certified"])
        for p in ("3","4"):
            for x in self.result["sensitivity"][p]["cost_sensitivity"].values():
                self.assertFalse(x["account_true_profit_reconciled"])

    def test_replay_deterministic_on_sha_pinned_provider_source(self):
        self.assertEqual(self.result,R.report())
        self.assertEqual(self.source["raw_source_sha256"],
                         self.result["source"]["raw_source_sha256"])

    def test_no_trainable_rvol_and_screen_original_membership_claim(self):
        self.assertFalse(self.result[
            "FINVIZ_relative_volume_intraday_over_five_proved"])
        self.assertTrue(self.result[
            "user_screenshot_selected_tickers_after_outcome"])


if __name__=="__main__":
    unittest.main()
