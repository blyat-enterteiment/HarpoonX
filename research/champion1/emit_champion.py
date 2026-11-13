"""C41 reproducible standalone report writer. Observed market bars != fills."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from evaluate_champion import evaluate

HERE=Path(__file__).resolve().parent


def write_reports(root:Path=HERE)->dict[str,object]:
    report=evaluate(root)
    output=root/"artifacts"
    output.mkdir(exist_ok=True)
    data=json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+"\n"
    (output/"C41_CHAMPION1_OBSERVED_BARS_MODELED_FILLS.json").write_text(data)
    keys=[
        "CASH_ZERO_YIELD",
        "MOMENTUM5_NO_RVOL_TRAIL2_NOT_ORIGINAL",
        "CHAMPION1_MOMENTUM5_RVOL_GE_1P25_TRAIL2",
        "CHAMPION1_INDEPENDENTLY_RESIZED_COST_STRESS",
    ]
    with (output/"C41_COMPARISON_MODELED_ONLY.csv").open("w",newline="") as f:
        w=csv.writer(f)
        w.writerow(["policy","terminal_usd","net_modelled_usd","modelled_trades",
                    "assumed_cost_usd","log_growth_bps_per_calendar_day",
                    "real_broker_fill_count","N9S"])
        for key in keys:
            row=report["benchmarks"][key]
            w.writerow([key,row["terminal_equity_usd"],
                        row["modelled_net_pnl_usd"],
                        row.get("closed_modeled_trades",0),
                        row.get("hypothetical_costs_usd",0),
                        row["net_log_growth_bps_per_target_calendar_day"]
                        if "net_log_growth_bps_per_target_calendar_day" in row else 0.,
                        0,"NO_GO"])
    with (output/"C41_TRADES_HYPOTHETICAL_NOT_BROKER.csv").open("w",newline="") as f:
        w=csv.writer(f)
        cols=["policy","symbol","signal_day","rvol10","entry_at","exit_at",
              "holding_hours","nominal_usd","reserved_risk_usd",
              "entry_price","exit_price","exit_reason","modelled_cost_bps",
              "modelled_net_pnl_usd","broker_fill_confirmed"]
        w.writerow(cols)
        for key in keys[1:]:
            for row in report["benchmarks"][key]["trades"]:
                w.writerow([key,*[row[name] for name in cols[1:]]])
    capsule={
        "schema":"HARPOONX_M11_C41_LOCKED_FORWARD_PROXY_EVIDENCE_1",
        "original_frozen_plan_commit_before_download":
            "a8eb6029f026131d375f791f9fc439a4c2a4c44f",
        "report_sha256":hashlib.sha256(data.encode()).hexdigest(),
        "source_markets_covered":report["source"]["new_oct_nov_market_bars"],
        "confirmed_broker_fills":0,
        "actual_prospective_experiment":False,
        "required_original_cash_comparison_complete":False,
        "M10_final_accounts_sealed":3200,
        "financialGO":False,"N9S":"NO_GO",
    }
    (output/"C41_EVIDENCE_NO_GO.json").write_text(
        json.dumps(capsule,sort_keys=True,indent=2)+"\n"
    )
    return capsule


if __name__=="__main__":
    print(json.dumps(write_reports(),sort_keys=True))
