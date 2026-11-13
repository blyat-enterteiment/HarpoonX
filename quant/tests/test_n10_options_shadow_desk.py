"""C43 unit and adversarial options tests: synthetic + actual indicative SPY sample.

NO option orders, no exercise, no broker fill inference. All scenario return
probabilities are test inputs, not calibrated market evidence.
"""
from __future__ import annotations

import json
import math
import sys
import unittest
from dataclasses import replace
from pathlib import Path

from harpoon_quant.options_shadow_desk import (
    Book, Expenses, Leg, OptionQuote, Package, Shock, Thesis,
    adapt_alpaca_snapshot, cost_and_funding, european_proxy, parse_occ,
    quote_validate, scenario_economics, validate_package,
)

DAY=86_400_000
DECISION=1_794_597_600_000
ROOT=Path(__file__).resolve().parents[2]


def quote(*,right="C",strike="760.000",bid="1.00",ask="1.25",
          symbol=None,feed="indicative",iv=".22",delta=None,
          mult=100,deliverable="STANDARD_100_SHARES",
          expiry="2026-12-18",clock=DECISION):
    code=("C" if right=="C" else "P")
    digits=int(round(float(strike)*1000))
    return OptionQuote(
        symbol=symbol or f"SPY261218{code}{digits:08d}",
        underlying="SPY",right=right,strike=strike,expiration=expiry,
        multiplier=mult,deliverable=deliverable,
        bid=bid,ask=ask,bid_size=10,ask_size=10,iv=iv,
        delta=delta or (".45" if right=="C" else "-.45"),
        gamma=".02",theta="-.14",vega=".08",
        feed=feed,quote_at_ms=clock-800,received_at_ms=clock-200,
        decision_at_ms=clock,terms_verified_from_broker=False,
    )


def book(**kwargs):
    b=Book("20000","20000","0","0","0","0",True,True,False)
    return replace(b,**kwargs)


def thesis(*,direction="BULL",rvol="1.4"):
    return Thesis("SPY","C42_MOMENTUM_SIGNALS",direction,
                  DECISION-1000,DECISION,rvol,"SYNTHETIC_RESEARCH")


def expenses():
    return Expenses(".50","1.00","30")


def one_call(**changes):
    q=replace(quote(),**changes)
    return Package("LONG_CALL",(Leg(q,"LONG"),),1,thesis())


def one_put():
    return Package("LONG_PUT",(Leg(quote(right="P"),"LONG"),),1,
                   thesis(direction="BEAR"))


def call_vertical():
    long=quote(strike="760.000",bid=".35",ask=".45")
    short=quote(strike="761.000",bid=".20",ask=".30")
    return Package("DEBIT_CALL_VERTICAL",
                   (Leg(long,"LONG"),Leg(short,"SHORT")),1,thesis())


def put_vertical():
    long=quote(right="P",strike="760.000",bid=".35",ask=".45")
    short=quote(right="P",strike="759.000",bid=".20",ask=".30")
    return Package("DEBIT_PUT_VERTICAL",
                   (Leg(long,"LONG"),Leg(short,"SHORT")),1,
                   thesis(direction="BEAR"))


def shocks():
    return (
        Shock("DOWN",".25","-.03",".03",72),
        Shock("SIDEWAYS",".5","0","0",48),
        Shock("UP",".25",".03","-.03",24),
    )


class OptionsShadowDeskTests(unittest.TestCase):
    def test_occ_contract_parser_strike_expiry_and_right(self):
        root,expiry,right,strike=parse_occ("SPY261218C00760000")
        self.assertEqual((root,expiry.isoformat(),right,str(strike)),
                         ("SPY","2026-12-18","C","760"))

    def test_occ_malformed_and_adjusted_nonstandard_fails_closed(self):
        for bad in ("SPY2612C00076000","SPY1261218C00760000",
                    "SPY261218X00760000","SPY261218C_BAD",""):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                parse_occ(bad)

    def test_long_call_and_put_direction_and_premium_are_distinct(self):
        for p in (one_call(),one_put()):
            validate_package(p)
            r=cost_and_funding(p,book(),expenses())
            self.assertEqual(r["gross_debit_cash_usd"],"125.00")
            self.assertFalse(r["funded_in_research_only"])
            self.assertFalse(r["options_execution_allowed"])

    def test_debit_call_vertical_spread_exact_cash_and_risk(self):
        p=call_vertical()
        r=cost_and_funding(p,book(),expenses())
        self.assertEqual(r["gross_debit_cash_usd"],"25.00")
        self.assertEqual(r["estimated_roundtrip_fees_usd"],"3.00")
        self.assertEqual(r["maximum_premium_loss_plus_estimated_fees_usd"],
                         "28.00")
        self.assertEqual(r["expiry_max_profit_for_vertical_only_usd"],"72.00")
        self.assertTrue(r["funded_in_research_only"])
        self.assertFalse(r["physical_delivery_funding_proved"])
        self.assertTrue(r["assignment_intraday_share_exposure_possible"])

    def test_debit_put_vertical_mirror_and_synthetic_only(self):
        p=put_vertical()
        m=validate_package(p)
        self.assertEqual(m["right"],"P")
        r=cost_and_funding(p,book(),expenses())
        self.assertEqual(r["maximum_premium_loss_plus_estimated_fees_usd"],
                         "28.00")
        self.assertFalse(r["options_execution_allowed"])

    def test_vertical_short_naked_position_is_rejected(self):
        p=call_vertical()
        for legs in ((p.legs[1],),(p.legs[1],p.legs[1])):
            with self.subTest(legs=legs),self.assertRaises(ValueError):
                validate_package(replace(p,legs=legs))

    def test_vertical_wrong_way_short_is_rejected(self):
        p=call_vertical()
        wrong=replace(p,legs=(Leg(p.legs[1].quote,"LONG"),Leg(p.legs[0].quote,"SHORT")))
        with self.assertRaisesRegex(ValueError,"WRONG_WAY_VERTICAL"):
            validate_package(wrong)

    def test_put_strategy_requires_bearish_underlying_thesis(self):
        p=one_put()
        with self.assertRaisesRegex(ValueError,"DIRECTION"):
            validate_package(replace(p,thesis=thesis(direction="BULL")))

    def test_call_strategy_requires_bullish_underlying_thesis(self):
        p=one_call()
        with self.assertRaisesRegex(ValueError,"DIRECTION"):
            validate_package(replace(p,thesis=thesis(direction="BEAR")))

    def test_nonstandard_deliverable_or_multiplier_is_unsafe(self):
        for updates in ({"multiplier":10},
                        {"deliverable":"ADJUSTED_OR_UNKNOWN"}):
            with self.subTest(updates=updates),self.assertRaisesRegex(
                    ValueError,"CONTRACT_TERMS"):
                quote_validate(replace(quote(),**updates))

    def test_put_delta_cannot_be_positive(self):
        with self.assertRaisesRegex(ValueError,"INCONSISTENT_OPTION_DELTA"):
            quote_validate(replace(quote(right="P"),delta=".5"))

    def test_causally_stale_quote_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"STALE_CROSSED"):
            quote_validate(replace(quote(),quote_at_ms=DECISION-100_000))

    def test_bid_greater_than_ask_rejected(self):
        with self.assertRaisesRegex(ValueError,"STALE_CROSSED"):
            quote_validate(replace(quote(),bid="2.0",ask="1.5"))

    def test_marked_quotes_expiring_soon_are_blocked(self):
        q=quote(symbol="SPY261120C00760000",expiry="2026-11-20")
        with self.assertRaisesRegex(ValueError,"EXPIRY_TOO_CLOSE"):
            quote_validate(q)

    def test_original_twenty_thousand_cash_cap_is_immutable(self):
        r=cost_and_funding(call_vertical(),book(equity_usd="25000",
                                                  settled_cash_usd="25000"),
                           expenses())
        self.assertEqual(r["frozen_common_capital_base_usd"],"20000")
        self.assertEqual(r["original_gross_admission_fraction"],".12")
        self.assertEqual(r["original_risk_admission_fraction"],".0025")

    def test_risk_cap_50_usd_blocks_two_option_spreads(self):
        p=replace(call_vertical(),contracts=2)
        r=cost_and_funding(p,book(),expenses())
        self.assertEqual(r["maximum_premium_loss_plus_estimated_fees_usd"],
                         "56.00")
        self.assertFalse(r["funded_in_research_only"])

    def test_unsettled_and_committed_cash_block_funding(self):
        for modifications in (
            {"settled_cash_usd":"0"},
            {"committed_cash_usd":"20000"},
            {"unsettled_cash_usd":"20000"},
            {"already_reserved_risk_usd":"50"},
            {"already_admitted_gross_usd":"2400"},
        ):
            with self.subTest(x=modifications):
                x=cost_and_funding(call_vertical(),book(**modifications),
                                   expenses())
                self.assertFalse(x["funded_in_research_only"])

    def test_snapshot_uncertainty_or_risk_halt_blocks_funding(self):
        for changes in (
            {"reconciled":False},
            {"receipts_complete":False},
            {"risk_halt":True},
        ):
            with self.subTest(x=changes):
                self.assertFalse(cost_and_funding(call_vertical(),
                       book(**changes),expenses())["funded_in_research_only"])

    def test_even_cash_funded_long_vertical_is_not_delivery_funded(self):
        r=cost_and_funding(call_vertical(),book(),expenses())
        self.assertTrue(r["funded_in_research_only"])
        self.assertGreater(float(r[
            "worst_case_share_delivery_notional_for_liquidity_check_usd"]),
            20_000)
        self.assertFalse(r["physical_delivery_funding_proved"])
        self.assertFalse(r["options_execution_allowed"])

    def test_long_put_or_call_could_also_exercise_shares(self):
        for p in (one_call(),one_put()):
            r=cost_and_funding(p,book(),expenses())
            self.assertGreater(float(r[
                "worst_case_share_delivery_notional_for_liquidity_check_usd"]),
                20_000)
            self.assertFalse(r["physical_delivery_funding_proved"])

    def test_bsm_european_put_call_parity_with_dividends(self):
        c=european_proxy(100,100,.2,.5,"C",risk_free=.03,
                         dividend_yield=.01)
        p=european_proxy(100,100,.2,.5,"P",risk_free=.03,
                         dividend_yield=.01)
        parity=100*math.exp(-.01*.5)-100*math.exp(-.03*.5)
        self.assertAlmostEqual(c-p,parity,places=9)

    def test_bsm_intrinsic_deep_itm_and_positive_finite(self):
        c=european_proxy(100,95,.25,.04,"C")
        self.assertTrue(math.isfinite(c) and c>0)
        with self.assertRaisesRegex(ValueError,"ANALYTIC_MODEL"):
            european_proxy(100,95,-1,.05,"C")

    def test_scenario_probs_should_sum_to_exactly_one(self):
        bad=(Shock("A",".5",".02",".01",24),
             Shock("B",".3","-.02","-.01",48),
             Shock("C",".1","0","0",72))
        with self.assertRaisesRegex(ValueError,"NOT_NORMALIZED"):
            scenario_economics(call_vertical(),book(),expenses(),
                               spot="760",shocks=bad)

    def test_horizon_beyond_72_hours_rejected(self):
        vals=list(shocks())
        vals[1]=replace(vals[1],holding_hours=73)
        with self.assertRaisesRegex(ValueError,"MAX_72H_HOLD"):
            scenario_economics(call_vertical(),book(),expenses(),
                               spot="760",shocks=tuple(vals))

    def test_iv_scenario_can_be_negative_change_but_positive_total(self):
        v=scenario_economics(call_vertical(),book(),expenses(),
                             spot="760",shocks=shocks())
        self.assertEqual(len(v["scenarios"]),3)
        self.assertFalse(v["scenario_first_passage_target_before_stop_proved"])
        self.assertFalse(v["scenario_probabilities_verified_against_future_outcomes"])
        self.assertFalse(v["execution_allowed"])
        self.assertEqual(v["N10"],"NO_GO")

    def test_option_scenario_winning_probability_is_only_user_assumption(self):
        v=scenario_economics(call_vertical(),book(),expenses(),
                             spot="760",shocks=shocks())
        probability=float(v["user_scenario_probability_of_positive_modeled_mark"])
        self.assertTrue(0<=probability<=1)
        self.assertFalse(v["independently_OPRA_reconciled"])
        self.assertFalse(v["option_early_exercise_assignment_delivery_modelled"])

    def test_snapshot_real_indicative_sample_adapter_never_authenticates(self):
        f=ROOT/"research/n10_options/observed_indicative_SPY_2026-11-13.json"
        obj=json.loads(f.read_text())
        self.assertEqual(obj["feed"],"indicative")
        self.assertEqual(obj["real_option_fills"],0)
        seen=0
        for chain in obj["chains"]:
            at=chain["local_connector_return_timestamp_ms"]
            for record in chain["records"]:
                q=adapt_alpaca_snapshot(
                    record,underlying="SPY",decision_at_ms=at+1,
                    received_at_ms=at,feed="indicative"
                )
                self.assertFalse(q.terms_verified_from_broker)
                self.assertEqual(q.feed,"indicative")
                self.assertEqual(q.multiplier,100)
                seen+=1
        self.assertEqual(seen,16)

    def test_provider_behind_clock_or_missing_ask_is_rejected(self):
        record={
            "symbol":"SPY261218C00760000",
            "latest_quote":{"timestamp":"2026-11-13T00:00:00Z",
                            "bid_price":1,"ask_price":2,
                            "bid_size":1,"ask_size":1},
            "greeks":{"delta":.5,"gamma":.02,"theta":-.1,"vega":.09},
            "implied_volatility":.22,
        }
        with self.assertRaises(ValueError):
            adapt_alpaca_snapshot(record,underlying="SPY",
                decision_at_ms=DECISION,received_at_ms=DECISION-1,
                feed="indicative")

    def test_provider_adjusted_root_not_representable_as_std_spy(self):
        q=replace(quote(),symbol="SPY1261218C00760000")
        with self.assertRaises(ValueError):
            quote_validate(q)

    def test_positive_forecast_and_an_appraisal_cannot_create_option_order(self):
        v=scenario_economics(call_vertical(),book(),expenses(),
                             spot="760",shocks=shocks())
        self.assertEqual(v["broker_option_orders_or_fills"],0)
        self.assertFalse(v["portfolio_options_enabled"])
        self.assertEqual(v["N9S"],"NO_GO")
        self.assertEqual(v["N10"],"NO_GO")


if __name__=="__main__":
    unittest.main()
