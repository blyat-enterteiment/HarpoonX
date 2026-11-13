"""N10 C43 common-funded-book options shadow portfolio, no broker actions.

Unlike separate per-contract profits, every candidate is admitted against
ONE shared 20k-capped cash/risk envelope. A candidate is never executable.
Scenario identifiers must match for a joint (not independent) distribution.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from decimal import Decimal

from .options_shadow_desk import (
    Book, Expenses, Package, Shock, cost_and_funding, money,
    scenario_economics,
)

SCHEMA="HARPOONX_M11_C43_OPTIONS_SHARED_CAPITAL_SHADOW_PORTFOLIO_1"


@dataclass(frozen=True)
class Proposal:
    package: Package
    spot: str
    shocks: tuple[Shock,...]
    rates: str=".03"
    dividend_yield: str=".01"


def shadow_portfolio(
    proposals: tuple[Proposal,...], start: Book, expenses: Expenses
) -> dict[str,object]:
    if not isinstance(proposals,tuple) or not (1 <= len(proposals) <= 16):
        raise ValueError("C43P_PROPOSAL_COHORT")
    decisions={p.package.thesis.decision_at_ms for p in proposals}
    if len(decisions)!=1:
        raise ValueError("C43P_CROSS_CLOCK_COHORT_NOT_ATOMIC")
    keys:set[str]=set()
    aligned:tuple[tuple[str,str,int],...]|None=None
    current=start
    rows=[]
    joint:dict[str,Decimal]={}
    probs:dict[str,Decimal]={}
    for proposal in proposals:
        p=proposal.package
        identity=p.thesis.underlying
        if identity in keys:
            raise ValueError("C43P_DUPLICATE_UNDERLYING_ACTIVE_CAMPAIGN")
        keys.add(identity)
        plan=tuple((s.scenario_id,s.probability,s.holding_hours)
                   for s in proposal.shocks)
        if aligned is None:
            aligned=plan
        elif aligned!=plan:
            raise ValueError("C43P_COMMON_JOINT_SCENARIOS_REQUIRED")
        v=scenario_economics(
            p,current,expenses,spot=proposal.spot,shocks=proposal.shocks,
            rate=proposal.rates,dividend_yield=proposal.dividend_yield
        )
        funded=v["funding"]
        assert isinstance(funded,dict)
        permitted=funded["funded_in_research_only"] is True
        # Do NOT accept an option to a funded trade portfolio when physical
        # exercise/assignment delivery is not financed. We may still keep
        # it as a shadow research row without consuming any real cash.
        delivery_ok=funded["physical_delivery_funding_proved"] is True
        if permitted and delivery_ok:
            # Even delivery-fundable is still research only: no option
            # execution permitted on non-independent data/quotes.
            status="SHADOW_RESEARCH_FUNDED_NOT_EXECUTION"
        elif permitted:
            status="SHADOW_PREMIUM_AFFORDABLE_DELIVERY_UNFUNDED"
        else:
            status="SHADOW_RISK_OR_LIQUIDITY_UNFUNDED"
        rows.append({
            "underlying":p.thesis.underlying,
            "strategy":p.thesis.strategy_id,
            "kind":p.kind,
            "risk_model":funded,
            "expected_modelled_net_pnl_usd":v["expected_modelled_net_pnl_usd"],
            "worst_user_shock_modelled_net_pnl_usd":
                v["worst_user_shock_modelled_net_pnl_usd"],
            "shadow_state":status,
            "options_execution_permitted":False,
        })
        if not permitted or not delivery_ok:
            continue
        # No leg is actually submitted. These reservations exist only inside
        # this synthetic allocator run, never in the broker account.
        premium=money(str(funded["gross_debit_cash_usd"]),"PREMIUM")
        risk=money(str(funded[
            "maximum_premium_loss_plus_estimated_fees_usd"]),"RISK")
        current=replace(
            current,
            committed_cash_usd=str(
                money(current.committed_cash_usd,"COMMITTED")+premium
            ),
            already_admitted_gross_usd=str(
                money(current.already_admitted_gross_usd,"GROSS")+premium
            ),
            already_reserved_risk_usd=str(
                money(current.already_reserved_risk_usd,"RISK")+risk
            ),
        )
        for shock,scen in zip(proposal.shocks,v["scenarios"]):
            assert isinstance(scen,dict)
            sid=shock.scenario_id
            w=money(shock.probability,"WEIGHT",positive=True)
            probs[sid]=w
            joint[sid]=joint.get(sid,Decimal(0))+Decimal(
                str(scen["modelled_net_pnl_usd"])
            )
    estimated_joint_expectation=sum(
        probs[sid]*net for sid,net in joint.items()
    ) if joint else Decimal(0)
    return {
        "schema":SCHEMA,
        "starting_equity_usd":start.equity_usd,
        "one_funded_cash_risk_book":True,
        "scenarios_joint_not_iid":True,
        "cohort_candidates":len(proposals),
        "shadow_rows":rows,
        "joint_scenario_modeled_net_usd":{
            k:str(v) for k,v in sorted(joint.items())
        },
        "joint_scenario_expected_modelled_net_usd":
            str(estimated_joint_expectation),
        "shadow_total_reserved_premium_usd":str(
            money(current.committed_cash_usd,"AFTER_COMMITTED")
            -money(start.committed_cash_usd,"BEFORE_COMMITTED")
        ),
        "shadow_total_reserved_risk_usd":str(
            money(current.already_reserved_risk_usd,"AFTER_RISK")
            -money(start.already_reserved_risk_usd,"BEFORE_RISK")
        ),
        "input_sha256":hashlib.sha256(json.dumps({
            "proposals":[asdict(p) for p in proposals],
            "book":asdict(start),"expenses":asdict(expenses),
        },sort_keys=True,separators=(",",":")).encode()).hexdigest(),
        "real_position_positions_opened":0,
        "broker_cash_mutated":False,
        "real_option_assignment_protection_verified":False,
        "source_and_fills_independently_authenticated":False,
        "probabilities_calibrated_on_future_broker_realizations":False,
        "output_can_be_promoted_to_orders":False,
        "N9S":"NO_GO","N10":"NO_GO",
    }
