#!/usr/bin/env python3
"""C17: finite policy-uniform analytic WEAK E[A], E[U] upper envelopes.

Not estimated from seeds or historical accounts. This is a theorem for the
SPECIFIED long funded bar-open-acquire/bar-end-or-earlier-sell policy class.
It is NOT a proof that every native replay campaign obeys its hypotheses.
No 12% continuous cap, no broker availability assumption, no live trading.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from fwn9_p9m_c15_economic_gate import bound

M9_SOURCE_SHA = "9d4afa402d2b70791f175e79219495f9bbbe25eb3cd0b7e9212cef6bccbd68ab"
M9_PROTOCOL_SHA = "de694919b0908fc0ecf474c9612ff7d54fe04db635a385e12ffa0f81abc7780d"
W0 = 20000.0
H = 8
NSESS = 126
NBAR = 78
GAMMA_BARS = NBAR * NSESS
WEAK_DRIFT_MAX = 0.000025 * 1.1
ACTIVITY_MAX = math.exp(0.7)
FINAL_SIGMA_MAX = 1.2
WORLD_SIGMA = 1.25
MIXTURE = ((1.0, .996), (4.0, .004))
SCHEMA = "HARPOON_M11_C17_WEAK_ANALYTIC_POPULATION_UPPER_CONDITIONAL_1"


def norm_cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def analytic_positive_log_call(mu: float, variance: float) -> float:
    """E[(exp(X)-1)+] for normal X; rigorous identity modulo FP error."""
    if not (math.isfinite(mu) and math.isfinite(variance) and variance > 0):
        raise ValueError("C17_GAUSSIAN_CALL_DOMAIN")
    z = math.sqrt(variance)
    return max(0., math.exp(mu + variance/2) *
               norm_cdf((mu+variance)/z) - norm_cdf(mu/z))


def analytic_negative_log_put(mu: float, variance: float) -> float:
    """E[(1-exp(X))+] for normal X; no sample-based fitting."""
    if not (math.isfinite(mu) and math.isfinite(variance) and variance > 0):
        raise ValueError("C17_GAUSSIAN_PUT_DOMAIN")
    z = math.sqrt(variance)
    return max(0., norm_cdf(-mu/z) -
               math.exp(mu+variance/2)*norm_cdf((-mu-variance)/z))


def frozen_m9(root: Path) -> dict[str, Any]:
    generator = root / "quant/harpoon_quant/modulation9.py"
    pfile = root / "research/modulation9/protocol.json"
    if (hashlib.sha256(generator.read_bytes()).hexdigest() != M9_SOURCE_SHA or
            hashlib.sha256(pfile.read_bytes()).hexdigest() != M9_PROTOCOL_SHA):
        raise ValueError("C17_FROZEN_ORIGINAL_M9_SHA_MISMATCH")
    p: dict[str, Any] = json.loads(pfile.read_text(encoding="utf-8"))
    cfg = p["generator"]
    if (
        cfg["intrabar_substeps"] != H or cfg["evaluation_sessions"] != NSESS or
        cfg["bars_per_session"] != NBAR or cfg["weak_drift_per_bar"] != .000025 or
        cfg["final_parameter_shift"]["sigma_multiplier_range"] != [.9, 1.2] or
        cfg["final_parameter_shift"]["drift_multiplier_range"] != [.75, 1.1] or
        cfg["correlation_loading"] != .45 or
        cfg["bar_sigma"][:2] != [.00075, .00085] or
        p["traded_universe"] != ["SYNA", "SYNB"] or
        p["limits"]["capitalUsd"] != W0 or
        p["limits"]["grossFraction"] != .12 or
        p["statistics"]["minimum_effect_daily_log"] != .0001
    ):
        raise ValueError("C17_ORIGINAL_M9_CONFIG_CHANGED")
    return p


def gaussian_bar_positive_parts(sigma_base: float) -> dict[str, float]:
    """Upper positive tail for 8 discrete prefixes of the ORIGINAL M9 log tape.

    Volatility/activity/daily scale maxima from frozen WEAK M9 are used.
    Conditional drift in [-d,+d]; call maximized at +d and put at -d
    by monotonicity in lognormal mean and convex order in variance.
    Mixture drawn independently of the pre-bar predictable inventory.
    """
    sigma = sigma_base * WORLD_SIGMA * FINAL_SIGMA_MAX * ACTIVITY_MAX
    plus = minus = 0.0
    for k in range(1, H+1):
        fraction = k/H
        for multiplier, probability in MIXTURE:
            sigma_k = sigma * multiplier
            variance = sigma_k**2 * fraction
            call_mu = (WEAK_DRIFT_MAX-.5*sigma_k**2)*fraction
            put_mu = (-WEAK_DRIFT_MAX-.5*sigma_k**2)*fraction
            plus += probability*analytic_positive_log_call(call_mu, variance)
            minus += probability*analytic_negative_log_put(put_mu, variance)
    return {"sigma_upper": sigma, "kplus": plus, "kminus": minus,
            "range_upper": plus+minus}


def _conservative_up(value: float) -> float:
    """Round up to 5 significant decimal digits with sizeable FP buffer.

    This is a deliberately coarse numerical report, not a formal interval
    proof of transcendental function evaluation.
    """
    if not (math.isfinite(value) and value >= 0):
        raise ValueError("C17_NONFINITE_ANALYTIC_ENVELOPE")
    if value == 0:
        return 0.0
    power = math.floor(math.log10(value))-4
    scale = 10**power
    return float(math.ceil(value/scale + 1e-8) * scale)


def population_analytic_bounds(p: dict[str, Any]) -> dict[str, Any]:
    if p["generator"]["bar_sigma"][:2] != [.00075, .00085]:
        raise ValueError("C17_UNREGISTERED_VOLATILITY_BASE")
    curves = {
        s: gaussian_bar_positive_parts(float(p["generator"]["bar_sigma"][i]))
        for i, s in enumerate(p["traded_universe"])
    }
    kplus = max(row["kplus"] for row in curves.values())
    r = max(row["range_upper"] for row in curves.values())
    K = 1 + kplus
    N = NSESS * NBAR
    logK = math.log1p(kplus)
    # E(W_beforebar_j) <= W0 * K^j for j=0..N-1.
    # Overnight WEAK is conditionally mean-one and has no trades.
    # Let G = (K^N-1)/(K-1) be this geometric wealth accumulation.
    G = math.expm1(N*logK)/kplus
    A_upper = 8*W0*K*G
    U_upper = W0*r*G
    if not all(map(math.isfinite, (kplus, r, G, A_upper, U_upper))):
        raise ValueError("C17_POPULATION_ENVELOPE_OVERFLOW")
    a_ceil = _conservative_up(A_upper)
    u_ceil = _conservative_up(U_upper)
    scenarios: dict[str, Any] = {}
    for scenario in ("NOMINAL", "STRESS"):
        conditional = bound(
            scenario,
            expected_dollar_substep_exposure_upper=a_ceil,
            expected_positive_execution_credit_upper_usd=u_ceil,
        )
        scenarios[scenario] = {
            "C15_expected_daily_log_upper_bps": conditional["expected_daily_log_upper_bps"],
            "C15_screen": conditional["conditional_economic_screen"],
            "C15_conditional_mathematical_exclusion":
                conditional["math_exclusion_if_inputs_proved"],
            "N9S_native_certification": False,
        }
    return {
        "schema": SCHEMA, "world": "WEAK",
        "scope": "IDEAL_FROZEN_WEAK_LAW_POLICY_CLASS_CONDITIONAL",
        "not_monte_carlo": True,
        "no_market_seeds_or_accounts": True,
        "total_evaluation_bars": N,
        "total_evaluation_substeps_per_asset": N * H,
        "base_capital_usd": W0,
        "per_asset_analytic_positive_parts": curves,
        "Kbar": K,
        "r_bar_upper": r,
        "geometric_wealth_sum": G,
        "mathematical_A_upper_usd_substeps": A_upper,
        "mathematical_U_upper_usd": U_upper,
        "numerically_rounded_A_upper_usd_substeps": a_ceil,
        "numerically_rounded_U_upper_usd": u_ceil,
        "overnight_conditional_expected_wealth_multiplier": 1.0,
        "assumptions": [
            "long cash shares only, no short shares or cash borrowing",
            "wealth nonnegative and all open acquisitions funded using then-known cash",
            "entries only at bar open, no acquisition after same-bar exit",
            "exits always at nonnegative modeled price <= corresponding actual 8-step bar high",
            "sum exiting lots in a bar <= funded lot at bar open",
            "execution-time reference exists inside original source eight-step bar range",
            "pre-bar quantity and admissions independent of CURRENT-bar Gaussian innovation and 4sigma mixture",
            "no positive external funding and fees/calendar charges nonnegative",
            "no beneficial overnight executions, mean-one WEAK overnight move",
            "the 12pct cap is admission/reservation only and NOT a continuous cap",
        ],
        "populational_upper_for_abstract_policy_class": True,
        "full_native_implementation_hypotheses_proved": False,
        "independent_full_native_policy_class_verified": False,
        "exact_native_fill_executability_proved": False,
        "conditional_model_upper_below_original_hurdle": False,
        "tighter_than_original_hurdle": False,
        "N9S": "NO_GO",
        "final_M10_opened": 0,
        "new_signals": 0,
        "new_seeds": 0,
        "new_accounts": 0,
        "recursive_search_reactivated": False,
        "scenario_screens": scenarios,
    }


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print("FWN9_C17_WEAK_POPULATION_ENVELOPE=" +
          json.dumps(population_analytic_bounds(frozen_m9(args.root)), sort_keys=True))


if __name__ == "__main__":
    main()
