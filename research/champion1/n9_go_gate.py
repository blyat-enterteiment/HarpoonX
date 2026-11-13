"""C41 formal N9-S acceptance gate: fails closed on modeled historical prices.

Never upgrades this research artifact into an authenticated prospective broker
study; no API requests and no trading authority.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from evaluate_champion import CAPITAL, HERE, evaluate, load_manifest

SCHEMA="HARPOONX_M11_C41_N9S_ACCEPTANCE_GATE_RESEARCH_1"


def audit(root: Path=HERE) -> dict[str,object]:
    artifact=root/"artifacts"
    source_report=artifact/"C41_CHAMPION1_OBSERVED_BARS_MODELED_FILLS.json"
    capsule_path=artifact/"C41_EVIDENCE_NO_GO.json"
    raw=source_report.read_bytes()
    received=json.loads(raw)
    capsule=json.loads(capsule_path.read_bytes())
    if (
        hashlib.sha256(raw).hexdigest()!=capsule["report_sha256"]
        or capsule.get("original_frozen_plan_commit_before_download")
        !="a8eb6029f026131d375f791f9fc439a4c2a4c44f"
    ):
        raise ValueError("C41G_REPORT_SHA_OR_FROZEN_POLICY_MISMATCH")
    fresh=evaluate(root)
    if received!=fresh or received.get("schema")!=(
        "HARPOONX_M11_C41_CHAMPION1_FORWARD_PROXY_REPLAY_1"
    ):
        raise ValueError("C41G_REPORT_NOT_EQUAL_SOURCE_REPLAY")
    market,source=load_manifest(root)
    if set(market)!={"SPY","QQQ","NVDA","BTC/USD","ETH/USD"} or (
        source["new_oct_nov_market_bars"]!=179
        or source["market_bars_total"]!=555
        or not source["all_csv_git_blob_sha_verified"]
    ):
        raise ValueError("C41G_OBSERVED_SOURCE_NOT_RECONCILED")
    v=received["benchmarks"]
    cash=v["CASH_ZERO_YIELD"]
    champion=v["CHAMPION1_MOMENTUM5_RVOL_GE_1P25_TRAIL2"]
    no_rvol=v["MOMENTUM5_NO_RVOL_TRAIL2_NOT_ORIGINAL"]
    paired=v["CHAMPION1_PAIRED_SAME_TRADES_COST_STRESS"]
    resized=v["CHAMPION1_INDEPENDENTLY_RESIZED_COST_STRESS"]
    sensitivity=v["CHAMPION1_LEAVE_BEST_TRADE_OUT_FIXED_NOT_REOPTIMIZED"]
    pnl=float(champion["modelled_net_pnl_usd"])
    daily_log=float(champion["net_log_growth_bps_per_target_calendar_day"])
    observed_trade_count=int(champion["closed_modeled_trades"])
    required_terminal=CAPITAL*math.exp(43/10_000)
    if (
        not all(math.isfinite(float(vv)) for vv in (
            pnl,daily_log,champion["terminal_equity_usd"],
            no_rvol["modelled_net_pnl_usd"],
            paired["modelled_net_pnl_usd"],
            resized["modelled_net_pnl_usd"],
        ))
        or received["financialGO"] is not False
        or received["N9S"]!="NO_GO"
    ):
        raise ValueError("C41G_INCONSISTENT_ECONOMICS_OR_UNAUTHORIZED_GO")
    failures=[]
    if pnl<=0 or daily_log<=1.0:
        failures.append("MODELED_NET_LOG_GROWTH_NOT_ABOVE_FROZEN_1BP_PER_DAY")
    if float(paired["modelled_net_pnl_usd"])<=0:
        failures.append("PAIRED_TRANSACTION_COST_STRESS_NOT_PROFITABLE")
    if float(resized["modelled_net_pnl_usd"])<=0:
        failures.append("RESIZED_TRANSACTION_COST_STRESS_NOT_PROFITABLE")
    if observed_trade_count<5:
        failures.append("FEWER_THAN_FIVE_MODELED_TRADES_NO_POPULATION_EVIDENCE")
    if float(sensitivity["modelled_net_pnl_usd"])<=0:
        failures.append("LEAVE_ONE_BEST_TRADE_OUT_DOES_NOT_SHOW_POSITIVE_EDGE")
    for x in (
        "BROKER_PRIVATE_FILLS_AND_COMPLETE_FEES_UNOBSERVED",
        "ORIGINAL_C22_SIX_POLICIES_SEMANTIC_PARITY_UNPROVED",
        "NO_INDEPENDENT_RFC3161_PREOUTCOME_REGISTRATION",
        "NO_GENUINE_PROSPECTIVE_ALLOCATION_AND_BROKER_EXECUTION",
        "NO_FWER_CORRECTED_POPULATION_NET_WEALTH_LOWER_BOUND",
        "M10_FINAL_HOLDOUT_MUST_REMAIN_SEALED",
    ):
        failures.append(x)
    return {
        "schema":SCHEMA,
        "source_csv_sha_verified":True,
        "report_sha256":capsule["report_sha256"],
        "frozen_candidate_before_target_data_api_commit":
            "a8eb6029f026131d375f791f9fc439a4c2a4c44f",
        "period":"2026-10-01_to_2026-11-12",
        "calendar_days":43,
        "capital_usd":CAPITAL,
        "hurdle_daily_bps_original":1.0,
        "required_terminal_for_1bp_per_calendar_day_usd":
            round(required_terminal,6),
        "champion_modelled_terminal_usd":champion["terminal_equity_usd"],
        "champion_modelled_net_pnl_usd":pnl,
        "champion_modelled_daily_log_bps":daily_log,
        "champion_modeled_trades":observed_trade_count,
        "ablation_without_RVOL_modelled_pnl_usd":
            no_rvol["modelled_net_pnl_usd"],
        "modelled_loss_avoided_vs_no_RVOL_usd":round(
            pnl-float(no_rvol["modelled_net_pnl_usd"]),6
        ),
        "cost_paired_stress_usd":paired["modelled_net_pnl_usd"],
        "cost_resized_stress_usd":resized["modelled_net_pnl_usd"],
        "cash_reference_usd":cash["terminal_equity_usd"],
        "original_six_C22_reference_usd":None,
        "actual_broker_fill_count":0,
        "independently_timed_external_registration":False,
        "genuine_prospective_observation":False,
        "can_accept_production_orders":False,
        "can_restart_recursive_optimizer":False,
        "unmet_acceptance_conditions":failures,
        "economic_study_status":"HYPOTHESIS_NOT_DEMONSTRATED_AND_C41_MODELED_PNL_NEGATIVE",
        "independent_statistical_audit_completed":False,
        "financialGO":False,
        "N9S":"NO_GO",
        "M10_final_sealed":3200,
    }


def main()->None:
    result=audit()
    out=HERE/"artifacts"/"C41_N9_GO_GATE_FAIL_CLOSED.json"
    out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print(json.dumps({
        "schema":result["schema"],"financialGO":False,"N9S":"NO_GO",
        "unmet_count":len(result["unmet_acceptance_conditions"]),
        "modelled_net_pnl_usd":result["champion_modelled_net_pnl_usd"],
        "required_terminal_usd":result[
            "required_terminal_for_1bp_per_calendar_day_usd"
        ],
    },sort_keys=True))


if __name__=="__main__":
    main()
