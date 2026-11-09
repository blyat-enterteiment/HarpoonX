#!/usr/bin/env python3
"""C19: source-frozen conditional WEAK close-mark execution credit compensator.

No RNG, no signals or account executions. Does not establish broker executable
fills or prove full native OHLC pathways are predictable / source adapted.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

SCHEMA = "HARPOON_M11_C19_WEAK_CLOSE_MARK_CREDIT_COMPENSATOR_1"
SOURCE_SHA = {
    "quant/harpoon_quant/modulation9.py":
    "9d4afa402d2b70791f175e79219495f9bbbe25eb3cd0b7e9212cef6bccbd68ab",
    "research/modulation9/protocol.json":
    "de694919b0908fc0ecf474c9612ff7d54fe04db635a385e12ffa0f81abc7780d",
    "runtime30/profit8_replay.js":
    "303aa6956cfa0a249f0432bea23894b3ee8e514c60ff011177baabc7a6974810",
}
ASSETS = ("SYNA", "SYNB")
SIGMA_BASE = (.00075, .00085)
D = 0.000025 * 1.1
H = 8
N = 126 * 78
W0 = 20000.0
DAY_COUNT = 176
MIXTURE = ((1.0, 0.996), (4.0, 0.004))


def normal_cdf(z: float) -> float:
    return 0.5 * math.erfc(-z / math.sqrt(2.0))


def put_expected(mu: float, variance: float) -> float:
    """E[(1-exp(X))+] for X ~ normal(mu,variance), source-independent formula."""
    if not (math.isfinite(mu) and math.isfinite(variance) and variance > 0):
        raise ValueError("C19_GAUSSIAN_PUT_INPUT")
    sd = math.sqrt(variance)
    out = normal_cdf(-mu / sd) - math.exp(mu + variance / 2) * (
        normal_cdf((-mu - variance) / sd)
    )
    return max(0.0, out)


def source_integrity(root: Path) -> dict[str, Any]:
    for path, wanted in SOURCE_SHA.items():
        actual = hashlib.sha256((root / path).read_bytes()).hexdigest()
        if actual != wanted:
            raise ValueError("C19_FROZEN_SOURCE_CHANGED:" + path)
    p: dict[str, Any] = json.loads(
        (root / "research/modulation9/protocol.json").read_text(encoding="utf-8")
    )
    cfg,limits = p["generator"],p["limits"]
    frozen = (
        cfg["weak_drift_per_bar"] == 0.000025
        and cfg["bar_sigma"][:2] == list(SIGMA_BASE)
        and cfg["intrabar_substeps"] == H
        and cfg["bars_per_session"] == 78
        and cfg["evaluation_sessions"] == 126
        and cfg["final_parameter_shift"]["sigma_multiplier_range"] == [.9, 1.2]
        and cfg["final_parameter_shift"]["drift_multiplier_range"] == [.75, 1.1]
        and limits["capitalUsd"] == W0
        and limits["grossFraction"] == .12
        and p["traded_universe"] == list(ASSETS)
        and p["statistics"]["minimum_effect_daily_log"] == .0001
    )
    if not frozen:
        raise ValueError("C19_FROZEN_ECONOMIC_MODEL_DRIFT")
    return {"sources_sha256": SOURCE_SHA,"scope":"WEAK_REGISTERED_IDEAL_GAUSSIAN"}


def asset_downward_variation(base_sigma: float) -> float:
    """Upper E[sum_j (P_{j-1}-P_j)+ / S_open] per M9 eight-step bar.

    The 8 future iid normal innovations are conditional on prebar information
    and on a frozen 1x/4x (0.996/0.004) bar-volatility mixture. Use the
    +D drift bound for E[P_(j-1)] and -D for the normalized down-put.
    Separate maximizers are an UPPER, not an exact conditional expectation.
    """
    if base_sigma not in SIGMA_BASE:
        raise ValueError("C19_NONREGISTERED_ASSET_SIGMA")
    sigma = base_sigma * 1.25 * 1.2 * math.exp(.7)
    allowance = 0.0
    for j in range(1,H+1):
        pre_factor = math.exp(D*(j-1)/H)
        for multiple, probability in MIXTURE:
            sd = sigma*multiple
            var = sd**2/H
            negative_drift_mu = (-D - .5*sd**2)/H
            allowance += (
                probability*pre_factor*put_expected(negative_drift_mu,var)
            )
    return allowance


def analytic() -> dict[str, Any]:
    assets = {a:asset_downward_variation(s) for a,s in zip(ASSETS,SIGMA_BASE,strict=True)}
    kappa = max(assets.values())
    lam_min = sum(math.exp(-D*k/H) for k in range(H))
    lam_plus = sum(math.exp(D*k/H) for k in range(H))
    beta = kappa/lam_min
    # The native trade at a bar end has modeled fill <= original high.
    # Hence (fill-close)+ <= (high-close)+ <= sum negative single-step moves.
    # Sell quantity <= funded pre-bar quantity, and knownAt is separate.
    # First exact conditional relationship:
    # E[U_close] <= kappa * E[sum_bar q_pre S_open]
    # E[A] >= lambda_min * E[sum_bar q_pre S_open].
    # This gives E[U_close] <= beta E[A].
    # To compute a global uniform worst-case class bound, use nonnegative
    # cash q_pre*S_open <= W_pre and complete worst-case daily cash financing.
    gross = math.exp(D)+kappa
    geometric = math.expm1(N*math.log(gross))/(gross-1)
    a_max = W0*lam_plus*geometric
    u_max = W0*kappa*geometric
    if not all(map(math.isfinite,(kappa,beta,gross,geometric,a_max,u_max))):
        raise ValueError("C19_FINITE_MOMENT_DOMAIN")
    scenarios = {}
    for scenario,cost_day in (("NOMINAL",1.),("STRESS",2.)):
        max_wealth=W0*gross**N-DAY_COUNT*cost_day
        upper_bps=10000*math.log(max_wealth/W0)/DAY_COUNT
        scenarios[scenario]={
            "expected_log_daily_upper_bps":upper_bps,
            "mathematical_exclusion_of_1bp":upper_bps<1.,
            "lower_calendar_cost_usd":cost_day*DAY_COUNT,
            "native_certificate":False,
        }
    return {
        "schema":SCHEMA,
        "registered_world":"WEAK",
        "per_asset_downward_variation_allowance":assets,
        "max_bar_end_positive_credit_allowance_kappa":kappa,
        "expected_8step_exposure_lower_multiplier":lam_min,
        "expected_8step_exposure_upper_multiplier":lam_plus,
        "positive_execution_credit_per_A_expectation_beta":beta,
        "conditional_population_theorem":"E[U_close]<=beta*E[A] for the funded predictable native bar-end mark class",
        "credit_reference":"native modeled fill at bar.end relative to original bar.c; time open fills relative to bar.o",
        "upper_A_pop_for_model_class_usd_substeps":a_max,
        "upper_U_pop_for_model_class_usd":u_max,
        "upper_wealth_bar_factor":gross,
        "original_12pct_is_continuous_cap":False,
        "full_native_engine_source_adaptedness_proved":False,
        "full_native_fills_executable_at_8steps_proved":False,
        "population_estimated_from_historical_seed":False,
        "numerical_rounding":"FLOAT64_ANALYTIC_NOT_FORMAL_INTERVAL_PROOF",
        "scenarios":scenarios,
        "holdout_M10_accounts_opened":0,
        "new_accounts":0,"new_signals":0,"new_seeds":0,
        "N9S":"NO_GO",
    }


def main() -> None:
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args()
    proof=source_integrity(args.root)
    print("C19_FUNDED_NATIVE_WEAK_CREDIT="+json.dumps(
        {"frozen_source":proof,"math":analytic()},sort_keys=True,allow_nan=False
    ))


if __name__=="__main__":
    main()
