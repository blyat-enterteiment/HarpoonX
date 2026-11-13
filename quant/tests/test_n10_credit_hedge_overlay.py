"""C45 four-leg credit strategies, scenario and early-assignment funding tests.

Every fixture is synthetic engineering data. Real market liquidity and fills
are NOT verified. A condor is short-vol carry, NOT crash insurance.
"""
from __future__ import annotations

import math
import unittest
from dataclasses import replace

from harpoon_quant.options_credit_hedge_overlay import (
    CreditFourLeg,
    MarketRegime,
    cohort_identity,
    credit_risk,
    exit_72h_european_proxy,
    expiry_payoff,
    select_research_structure,
)
from harpoon_quant.options_shadow_desk import (
    Book,
    Expenses,
    OptionQuote,
)

AT=1_794_597_600_000


def quote(right:str,strike:int,*,bid:str,ask:str)->OptionQuote:
    return OptionQuote(
        symbol=f"SPY261218{right}{strike*1000:08d}",
        underlying="SPY",right=right,
        strike=str(strike),expiration="2026-12-18",
        multiplier=100,deliverable="STANDARD_100_SHARES",
        bid=bid,ask=ask,bid_size=30,ask_size=35,
        iv=".2",delta=("-0.2" if right=="P" else ".2"),
        gamma=".01",theta="-.1",vega=".6",
        feed="indicative",quote_at_ms=AT-600,
        received_at_ms=AT-100,decision_at_ms=AT,
        terms_verified_from_broker=False,
    )


def condor(*,short_put:int=96,short_call:int=104)->CreditFourLeg:
    return CreditFourLeg(
        "IRON_CONDOR",
        quote("P",short_put-1,bid=".15",ask=".25"),
        quote("P",short_put,bid=".60",ask=".70"),
        quote("C",short_call,bid=".55",ask=".65"),
        quote("C",short_call+1,bid=".18",ask=".30"),
        contracts=1,
    )


def butterfly()->CreditFourLeg:
    return CreditFourLeg(
        "IRON_BUTTERFLY",
        quote("P",99,bid=".15",ask=".25"),
        quote("P",100,bid=".72",ask=".82"),
        quote("C",100,bid=".53",ask=".63"),
        quote("C",101,bid=".18",ask=".30"),
        contracts=1,
    )


def funded(**overrides:object)->Book:
    return replace(
        Book("20000","20000","0","0","0","0",True,True,False),
        **overrides
    )


def costs()->Expenses:
    return Expenses(".65","0","30")


def regime(*,rvol:str="1.0",mom:str="0",iv:str=".3",
           rv:str=".2")->MarketRegime:
    return MarketRegime(
        "SPY",AT-300,AT,rvol,mom,iv,rv
    )


class FourLegCreditRiskTests(unittest.TestCase):
    def test_iron_condor_pays_credit_not_insurance(self):
        r=credit_risk(condor(),funded(),costs())
        self.assertEqual(float(r["net_credit_price_per_share_at_bid_ask"]),.60)
        self.assertAlmostEqual(float(r["full_roundtrip_fees_assumed_usd"]),5.2)
        self.assertAlmostEqual(float(r["net_expiry_max_gain_usd"]),54.8)
        self.assertAlmostEqual(float(r["expiry_max_loss_plus_fees_usd"]),45.2)
        self.assertEqual(r["options_strategy_risk_role"],
                         "SHORT_VOL_PREMIUM_SELLING_NOT_A_DOWNSIDE_HEDGE")

    def test_iron_condor_best_payoff_inside_shorts_at_expiry(self):
        c=condor()
        r=expiry_payoff(c,funded(),costs(),"100")
        self.assertAlmostEqual(float(r["expiry_net_contractual_pnl_usd"]),54.8)

    def test_iron_condor_right_tail_and_crash_both_lose(self):
        c=condor()
        for price in ("50","200"):
            r=expiry_payoff(c,funded(),costs(),price)
            self.assertAlmostEqual(float(r["expiry_net_contractual_pnl_usd"]),
                                   -45.2)
            self.assertTrue(r["early_assignment_intraday_PnL_can_differ"])

    def test_credit_condor_break_even_after_all_costs(self):
        r=credit_risk(condor(),funded(),costs())
        self.assertAlmostEqual(float(r["expiry_profit_lower_break_even_spot"]),
                               95.452)
        self.assertAlmostEqual(float(r["expiry_profit_upper_break_even_spot"]),
                               104.548)
        c=condor()
        for price in ("95.452","104.548"):
            net=expiry_payoff(c,funded(),costs(),price)
            self.assertAlmostEqual(float(net["expiry_net_contractual_pnl_usd"]),0)

    def test_same_center_iron_butterfly_payoff_is_narrower(self):
        c=butterfly()
        x=credit_risk(c,funded(),costs())
        self.assertEqual(x["kind"],"IRON_BUTTERFLY")
        self.assertAlmostEqual(float(x["credit_cash_usd"]),70)
        self.assertAlmostEqual(float(x["expiry_max_loss_plus_fees_usd"]),35.2)
        self.assertAlmostEqual(float(x["net_expiry_max_gain_usd"]),64.8)
        self.assertAlmostEqual(float(expiry_payoff(
            c,funded(),costs(),"100")["expiry_net_contractual_pnl_usd"]),64.8)
        self.assertAlmostEqual(float(expiry_payoff(
            c,funded(),costs(),"120")["expiry_net_contractual_pnl_usd"]),-35.2)

    def test_50dollar_frozen_risk_cap_accepts_only_premium_hedged_risk(self):
        r=credit_risk(condor(),funded(),costs())
        self.assertTrue(r["research_premium_risk_funded"])
        self.assertFalse(r["options_execution_allowed"])
        self.assertEqual(r["original_risk_budget_left_usd"],"50.0000")

    def test_risk_exhausts_with_two_contracts(self):
        c=replace(condor(),contracts=2)
        r=credit_risk(c,funded(),costs())
        self.assertAlmostEqual(float(r["expiry_max_loss_plus_fees_usd"]),90.4)
        self.assertFalse(r["research_premium_risk_funded"])

    def test_book_remaining_risk_rejects_existing_spend(self):
        r=credit_risk(condor(),funded(already_reserved_risk_usd="40"),costs())
        self.assertFalse(r["research_premium_risk_funded"])

    def test_unreconciled_book_rejects_credit_strategy(self):
        for bad in (
            funded(receipts_complete=False),
            funded(reconciled=False),
            funded(risk_halt=True),
            funded(settled_cash_usd="0")
        ):
            r=credit_risk(condor(),bad,costs())
            self.assertFalse(r["research_premium_risk_funded"])

    def test_frozen_initial_20k_base_not_relaxed_by_compound(self):
        b=funded(equity_usd="29000",settled_cash_usd="29000")
        r=credit_risk(condor(),b,costs())
        self.assertEqual(r["original_cash_capital_base_usd"],"20000")

    def test_conservative_assignment_stress_exceeds_one_book_capital(self):
        c=condor(short_put=760,short_call=770)
        r=credit_risk(c,funded(),costs())
        self.assertGreater(float(r[
            "conservative_both_short_assignments_share_notional_usd"]),150000)
        self.assertFalse(r["American_assignment_share_liquidity_funded"])
        self.assertFalse(r["American_early_assignment_exercise_pin_risk_verified"])
        self.assertFalse(r["options_execution_allowed"])

    def test_risk_asymmetric_wings_uses_larger_width(self):
        c=condor()
        far=replace(c,long_put=quote("P",94,bid=".15",ask=".25"))
        r=credit_risk(far,funded(),costs())
        self.assertGreater(float(r["expiry_max_loss_plus_fees_usd"]),100)
        self.assertFalse(r["research_premium_risk_funded"])

    def test_crossed_or_insufficient_option_quote_rejected(self):
        c=condor()
        bad=replace(c,short_call=replace(c.short_call,bid="1.50",ask=".65"))
        with self.assertRaisesRegex(ValueError,"STALE_CROSSED"):
            credit_risk(bad,funded(),costs())

    def test_different_expirations_rejected(self):
        c=condor()
        wrong=replace(c,long_call=replace(
            c.long_call,expiration="2026-12-25"
        ))
        with self.assertRaises(ValueError):
            credit_risk(wrong,funded(),costs())

    def test_nonatomic_option_snapshot_rejected(self):
        c=condor()
        bad=replace(c,long_call=replace(
            c.long_call,quote_at_ms=AT-10000
        ))
        with self.assertRaisesRegex(ValueError,"NONATOMIC_FOUR_LEG"):
            credit_risk(bad,funded(),costs())

    def test_mixed_index_or_symbol_underlying_rejected(self):
        c=condor()
        bad=replace(c,long_put=replace(
            c.long_put,underlying="XSP"
        ))
        with self.assertRaises(ValueError):
            credit_risk(bad,funded(),costs())

    def test_duplicate_leg_not_a_real_condor(self):
        c=condor()
        with self.assertRaisesRegex(ValueError,"FOUR_DISTINCT"):
            credit_risk(replace(c,short_put=c.long_put),funded(),costs())

    def test_credit_quotes_no_credit_not_an_income_strategy(self):
        c=condor()
        c=replace(c,short_put=replace(
            c.short_put,bid=".01"
        ))
        with self.assertRaisesRegex(ValueError,"POSITIVE_CREDIT"):
            credit_risk(c,funded(),costs())

    def test_credit_bigger_than_width_rejected_not_arbitrage(self):
        c=condor()
        c=replace(c,short_put=replace(
            c.short_put,bid="1.2",ask="1.3"
        ),short_call=replace(c.short_call,bid="1.1",ask="1.2"))
        with self.assertRaisesRegex(ValueError,"NO_ARBITRAGE"):
            credit_risk(c,funded(),costs())

    def test_net_credit_eaten_by_fees_is_rejected(self):
        c=condor()
        c=replace(c,short_put=replace(
            c.short_put,bid=".30",ask=".40"
        ),short_call=replace(c.short_call,bid=".27",ask=".37"))
        # Credit .02/share =2USD is less than 5.20USD fee
        with self.assertRaisesRegex(ValueError,"NET_PREMIUM"):
            credit_risk(c,funded(),costs())

    def test_genuine_rvol_elevated_breakout_not_condor_regime(self):
        s=select_research_structure(regime(rvol="1.8",mom=".03"))
        self.assertEqual(s["allowed_structures_research_only"],())
        self.assertEqual(s["risk_role"],"CASH_NO_EDGE_ATTESTED")

    def test_high_implied_over_realized_quiet_regime_is_short_vol_hypothesis(self):
        r=select_research_structure(regime())
        self.assertEqual(r["allowed_structures_research_only"],
                         ("IRON_CONDOR","IRON_BUTTERFLY"))
        self.assertFalse(r["regime_source_statistically_calibrated"])
        self.assertFalse(r["broker_orders_authorized"])

    def test_bear_momentum_with_volume_prefers_debit_hedge_not_condor(self):
        r=select_research_structure(regime(rvol="1.5",mom="-.03"))
        self.assertEqual(r["allowed_structures_research_only"],
                         ("LONG_PUT_DEBIT_VERTICAL_FROM_C43",))
        self.assertEqual(r["risk_role"],"DOWNSIDE_HEDGE_RESEARCH_NOT_EXECUTION")

    def test_source_future_clock_not_a_causal_hedge(self):
        with self.assertRaisesRegex(ValueError,"CAUSAL_MARKET_CLOCK"):
            select_research_structure(replace(
                regime(),known_at_ms=AT+10
            ))

    def test_IV_lower_than_realized_vol_cannot_sell_condor(self):
        r=select_research_structure(regime(iv=".15",rv=".25"))
        self.assertEqual(r["risk_role"],"CASH_NO_EDGE_ATTESTED")

    def test_72h_european_price_scenario_changes_without_claiming_fill(self):
        c=condor()
        x=exit_72h_european_proxy(
            c,funded(),costs(),"100",
            iv_change_absolute="0",holding_hours=24
        )
        stressed=exit_72h_european_proxy(
            c,funded(),costs(),"100",
            iv_change_absolute=".10",holding_hours=24
        )
        self.assertTrue(math.isfinite(float(x["modelled_net_pnl_usd"])))
        self.assertTrue(math.isfinite(float(stressed["modelled_net_pnl_usd"])))
        self.assertFalse(x["quote_fill_attainability_verified"])
        self.assertFalse(x["short_leg_assignment_modelled"])
        self.assertFalse(x["probability_of_TP_before_STOP_calibrated"])

    def test_73h_or_negative_IV_scenario_rejected(self):
        for holding_hours,iv in ((73,"0"),(12,"-.50")):
            with self.subTest(h=holding_hours,iv=iv),self.assertRaises(ValueError):
                exit_72h_european_proxy(
                    condor(),funded(),costs(),"100",
                    iv_change_absolute=iv,holding_hours=holding_hours
                )

    def test_structure_identity_sha256_changes_with_cost_or_quote(self):
        a=cohort_identity(condor(),funded(),costs())
        b=cohort_identity(condor(),funded(),replace(
            costs(),per_leg_per_side_usd=".70"
        ))
        self.assertNotEqual(a,b)
        self.assertEqual(len(a),64)
        self.assertEqual(cohort_identity(condor(),funded(),costs()),a)

    def test_credit_positions_are_always_no_go_regardless_of_premia(self):
        for c in (condor(),butterfly()):
            x=credit_risk(c,funded(),costs())
            self.assertFalse(x["options_execution_allowed"])
            self.assertEqual((x["N9S"],x["N10"]),("NO_GO","NO_GO"))


if __name__=="__main__":
    unittest.main()
