"""Describe the existing funded path; do not change holdings or run a strategy."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


def decompose(curve: dict) -> dict:
    initial = float(curve["initial_capital_usd"])
    previous = initial
    dollars: dict[str, float] = {}
    log_contributions: dict[str, float] = {}
    logs = []
    arithmetic_returns = []
    for row in curve["sessions"]:
        start, end = float(row["equity_start_usd"]), float(row["equity_end_usd"])
        if start <= 0 or end <= 0:
            raise ValueError("NONPOSITIVE_EQUITY_NO_LOG_ATTRIBUTION")
        if not math.isclose(start, previous, abs_tol=1e-7):
            raise ValueError("CAPITAL_CONTINUITY_MISMATCH")
        pnl = {k: float(v) for k, v in row["asset_pnl_usd"].items()}
        if not math.isclose(math.fsum(pnl.values()), end-start, abs_tol=1e-7):
            raise ValueError("ASSET_PNL_DOES_NOT_RECONCILE")
        r = (end-start)/start
        log_r = math.log1p(r)
        # Exact additive attribution of total log growth along the existing path.
        # This allocation is descriptive; it is not the effect of excluding an asset.
        factor = log_r/r if r else 1.0
        for symbol, value in pnl.items():
            dollars[symbol] = dollars.get(symbol, 0.0) + value
            log_contributions[symbol] = log_contributions.get(symbol, 0.0) + factor*value/start
        logs.append(log_r)
        arithmetic_returns.append(r)
        previous = end
    log_growth = math.fsum(logs)
    total_return = math.expm1(log_growth)
    assert math.isclose(math.fsum(log_contributions.values()), log_growth, abs_tol=1e-12)
    assert math.isclose(total_return, previous/initial-1, abs_tol=1e-12)
    assert math.isclose(math.fsum(dollars.values()), previous-initial, abs_tol=1e-7)
    return {
        "scope": "DESCRIPTIVE_ATTRIBUTION_OF_FROZEN_MODELED_FUNDED_PATH",
        "new_financial_trials": 0,
        "financial_acceptance_allowed": False,
        "initial_capital_usd": initial,
        "final_model_equity_usd": previous,
        "modeled_trading_pnl_usd": previous-initial,
        "external_operating_costs_usd": None,
        "external_cost_reason": "Not documented in this retained portfolio; no zero-cost assumption added.",
        "sessions": len(logs),
        "compound_return": total_return,
        "total_log_growth": log_growth,
        "geometric_mean_per_session": math.expm1(log_growth/len(logs)),
        "asset_dollar_contributions": dollars,
        "asset_total_return_contributions_common_initial_capital": {k:v/initial for k,v in dollars.items()},
        "asset_log_growth_contributions": log_contributions,
        "log_attribution_formula": "sum_t [(PnL_i,t / E_t-1) * log1p(r_portfolio,t) / r_portfolio,t]; ratio=1 when r=0",
        "limitations": [
            "Asset log contributions are an exact allocation convention on this fixed path, not standalone asset returns.",
            "No counterfactual asset exclusion or alternative compounding policy was executed.",
            "Growth conversion does not estimate incremental profit caused by reinvestment.",
            "Baseline holding-limit violations and missing original raw provenance remain material.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--curve", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.curve.read_bytes()
    report = decompose(json.loads(raw))
    report["curve_sha256"] = hashlib.sha256(raw).hexdigest()
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k:report[k] for k in ["sessions", "modeled_trading_pnl_usd", "compound_return", "asset_dollar_contributions", "asset_log_growth_contributions"]}))


if __name__ == "__main__":
    main()
