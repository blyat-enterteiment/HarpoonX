"""C43 shared-book options research is not permission to trade."""
from __future__ import annotations

import unittest
from dataclasses import replace

from harpoon_quant.options_shadow_desk import (
    Book, Expenses, Leg, OptionQuote, Package, Shock, Thesis,
)
from harpoon_quant.options_shadow_portfolio import Proposal, shadow_portfolio

AT=1_794_597_600_000


def q(root:str, strike:int, side:str)->OptionQuote:
    return OptionQuote(
        symbol=f"{root}261218C{strike*1000:08d}",
        underlying=root,right="C",strike=f"{strike}.0",
        expiration="2026-12-18",multiplier=100,
        deliverable="STANDARD_100_SHARES",
        bid=".35" if side=="long" else ".20",
        ask=".45" if side=="long" else ".30",
        bid_size=10,ask_size=10,iv=".25",
        delta=".45" if side=="long" else ".35",
        gamma=".02",theta="-.1",vega=".08",
        feed="indicative",quote_at_ms=AT-1000,
        received_at_ms=AT-100,decision_at_ms=AT,
        terms_verified_from_broker=False,
    )


def pkg(root:str,strategy:str)->Package:
    long=q(root,100,"long")
    short=q(root,101,"short")
    th=Thesis(root,strategy,"BULL",AT-5000,AT,"1.4","SYNTHETIC_RESEARCH")
    return Package("DEBIT_CALL_VERTICAL",
                   (Leg(long,"LONG"),Leg(short,"SHORT")),1,th)


def shocks(root:str):
    return (
        Shock("SYSTEMIC_DOWN",".25","-.03",".02",72),
        Shock("SYSTEMIC_FLAT",".50","0","0",48),
        Shock("SYSTEMIC_UP",".25",".03","-.02",24),
    )


def base()->Book:
    return Book("20000","20000","0","0","0","0",True,True,False)


def exp()->Expenses:
    return Expenses(".50","1.00","30")


class SharedBookTests(unittest.TestCase):
    def test_two_distinct_assets_share_50_usd_risk_budget(self):
        rows=(Proposal(pkg("SPY","SPY_MOM"),"100",shocks("SPY")),
              Proposal(pkg("QQQ","QQQ_MOM"),"100",shocks("QQQ")))
        output=shadow_portfolio(rows,base(),exp())
        self.assertEqual(output["cohort_candidates"],2)
        self.assertEqual(output["shadow_rows"][0]["shadow_state"],
                         "SHADOW_RESEARCH_FUNDED_NOT_EXECUTION")
        self.assertEqual(output["shadow_rows"][1]["shadow_state"],
                         "SHADOW_RISK_OR_LIQUIDITY_UNFUNDED")
        self.assertEqual(output["shadow_total_reserved_premium_usd"],"25.00")
        self.assertEqual(output["shadow_total_reserved_risk_usd"],"28.00")
        self.assertFalse(output["output_can_be_promoted_to_orders"])

    def test_same_underlying_different_strategy_cannot_duplicate_campaign(self):
        a=Proposal(pkg("SPY","SPY_MOM"),"100",shocks("SPY"))
        b=Proposal(pkg("SPY","SPY_BREAKOUT"),"100",shocks("SPY"))
        with self.assertRaisesRegex(ValueError,"DUPLICATE_UNDERLYING"):
            shadow_portfolio((a,b),base(),exp())

    def test_unaligned_systemic_scenarios_not_falsely_independent(self):
        a=Proposal(pkg("SPY","SPY_MOM"),"100",shocks("SPY"))
        b=Proposal(pkg("QQQ","QQQ_MOM"),"100",tuple(reversed(shocks("QQQ"))))
        with self.assertRaisesRegex(ValueError,"COMMON_JOINT_SCENARIOS"):
            shadow_portfolio((a,b),base(),exp())

    def test_cross_decision_timestamp_not_atomic(self):
        a=Proposal(pkg("SPY","SPY_MOM"),"100",shocks("SPY"))
        b_pkg=pkg("QQQ","QQQ_MOM")
        b=Proposal(replace(b_pkg,thesis=replace(
            b_pkg.thesis,decision_at_ms=AT+1000)),"100",shocks("QQQ"))
        with self.assertRaisesRegex(ValueError,"CROSS_CLOCK_COHORT"):
            shadow_portfolio((a,b),base(),exp())

    def test_delivery_risk_blocks_even_affordable_spy_760_spread(self):
        p=pkg("SPY","SPY_760")
        qlong=replace(q("SPY",760,"long"),bid=".35",ask=".45")
        qshort=replace(q("SPY",761,"short"),bid=".20",ask=".30")
        p=replace(p,legs=(Leg(qlong,"LONG"),Leg(qshort,"SHORT")))
        r=shadow_portfolio((Proposal(p,"760",shocks("SPY")),),base(),exp())
        self.assertEqual(r["shadow_rows"][0]["shadow_state"],
                         "SHADOW_PREMIUM_AFFORDABLE_DELIVERY_UNFUNDED")
        self.assertEqual(r["shadow_total_reserved_premium_usd"],"0")
        self.assertEqual(r["real_position_positions_opened"],0)

    def test_unreconciled_broker_inventory_never_allocates_shadow_funding(self):
        p=Proposal(pkg("SPY","S"),"100",shocks("SPY"))
        x=shadow_portfolio((p,),replace(base(),reconciled=False),exp())
        self.assertEqual(x["shadow_total_reserved_premium_usd"],"0")
        self.assertEqual(x["N10"],"NO_GO")

    def test_readonly_scenario_joint_outcomes_are_not_broker_pnl(self):
        p=Proposal(pkg("SPY","S"),"100",shocks("SPY"))
        x=shadow_portfolio((p,),base(),exp())
        self.assertEqual(set(x["joint_scenario_modeled_net_usd"]),
                         {"SYSTEMIC_DOWN","SYSTEMIC_FLAT","SYSTEMIC_UP"})
        self.assertTrue(x["scenarios_joint_not_iid"])
        self.assertFalse(x["source_and_fills_independently_authenticated"])
        self.assertFalse(x["broker_cash_mutated"])
        self.assertEqual(x["N9S"],"NO_GO")

    def test_unknown_shock_scenario_probability_rejected(self):
        p=Proposal(pkg("SPY","S"),"100",(
            Shock("A",".2",".01","0",24),
            Shock("B",".2","-.01","0",48),
            Shock("C",".2","0","0",72),
        ))
        with self.assertRaisesRegex(ValueError,"NOT_NORMALIZED"):
            shadow_portfolio((p,),base(),exp())


if __name__=="__main__":
    unittest.main()
