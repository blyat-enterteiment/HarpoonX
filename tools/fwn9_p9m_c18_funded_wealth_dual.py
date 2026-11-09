#!/usr/bin/env python3
"""C18 funded-wealth conditional WEAK dual: a sharp no-execution-credit baseline.

Analytical only; no strategy calls, market RNG, native account execution or
holdout. A proven model-class upper is not a native-policy certificate.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

M9_PROTOCOL_BLOB = "c49c8156f9d2f109f5eda0fd98d1b7290a837d1a"
M9_GENERATOR_SHA = "9d4afa402d2b70791f175e79219495f9bbbe25eb3cd0b7e9212cef6bccbd68ab"
SCHEMA = "HARPOON_FWN9_M11_C18_FUNDED_WEALTH_GAMMA_DUAL_1"


@dataclass(frozen=True)
class Frozen:
    capital_usd: float = 20000.0
    calendar_days: int = 176
    evaluation_sessions: int = 126
    bars_per_session: int = 78
    substeps_per_bar: int = 8
    weak_drift_per_bar: float = 0.000025
    max_drift_scale: float = 1.1
    hurdle_daily_log: float = 0.0001
    nominal_calendar_per_day: float = 1.0
    stress_calendar_per_day: float = 2.0

    @property
    def steps(self) -> int:
        return self.evaluation_sessions * self.bars_per_session * self.substeps_per_bar

    @property
    def step_delta_upper(self) -> float:
        return self.weak_drift_per_bar * self.max_drift_scale / self.substeps_per_bar

    @property
    def step_gamma(self) -> float:
        return math.expm1(self.step_delta_upper)

    @property
    def uninvested_wealth_factor_bound(self) -> float:
        # A poorly named but useful factor: maximum fully invested gross
        # growth under conditional maximal positive WEAK drift.
        return math.exp(self.steps * self.step_delta_upper)

    @property
    def geometric_wealth_sum(self) -> float:
        return math.expm1(self.steps * self.step_delta_upper) / self.step_gamma

    @property
    def terminal_hurdle_increment(self) -> float:
        return self.capital_usd * math.expm1(
            self.calendar_days * self.hurdle_daily_log
        )


def _git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(  # noqa: S324 - Git identity check, not cryptographic authentication
        f"blob {len(raw)}\0".encode("ascii") + raw
    ).hexdigest()


def check_original(root: Path) -> dict[str, str]:
    protocol = root / "research/modulation9/protocol.json"
    generator = root / "quant/harpoon_quant/modulation9.py"
    if _git_blob_sha1(protocol.read_bytes()) != M9_PROTOCOL_BLOB:
        raise ValueError("C18_ORIGINAL_M9_PROTOCOL_MISMATCH")
    if hashlib.sha256(generator.read_bytes()).hexdigest() != M9_GENERATOR_SHA:
        raise ValueError("C18_ORIGINAL_M9_GENERATOR_MISMATCH")
    p: dict[str, Any] = json.loads(protocol.read_text(encoding="utf-8"))
    g, stats, fees, limits = (
        p["generator"], p["statistics"], p["scenarios"], p["limits"]
    )
    checks: dict[str, bool] = {
        "sessions": g["evaluation_sessions"] == 126,
        "bars": g["bars_per_session"] == 78,
        "substeps": g["intrabar_substeps"] == 8,
        "weak": "WEAK" in g["worlds"],
        "drift": g["weak_drift_per_bar"] == .000025,
        "drift_scale": g["final_parameter_shift"]["drift_multiplier_range"] == [.75, 1.1],
        "capital": limits["capitalUsd"] == 20000,
        "gross_admission_only": limits["grossFraction"] == .12 and
            p["risk_semantics"].startswith("12% gross/name"),
        "risk": limits["openRiskFraction"] == .0025,
        "hurdle": stats["minimum_effect_daily_log"] == .0001,
        "nominal": fees["NOMINAL"]["external_cost_usd_per_calendar_day"] == 1.,
        "stress": fees["STRESS"]["external_cost_usd_per_calendar_day"] == 2.,
    }
    bad = [name for name, valid in checks.items() if not valid]
    if bad:
        raise ValueError("C18_FROZEN_CONTRACT_DRIFT:" + ",".join(bad))
    return {"m9_protocol_git_blob": M9_PROTOCOL_BLOB, "m9_generator_sha256": M9_GENERATOR_SHA}


def _nonnegative_finite(x: float, name: str) -> float:
    if isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x) or x < 0:
        raise ValueError("C18_INVALID_" + name)
    return float(x)


def conditional_bound(
    scenario: str,
    positive_execution_credit_expectation_upper_usd: float | None = None,
    *,
    source_proof_available: bool = False,
) -> dict[str, Any]:
    """E[A] <= (W0+U) * H, and E[WT] <= (W0+U) * R - cost_floor.

    Let X_k=E[W_k], q_k>=0 predictable and cash>=0. Under M9 WEAK
    E[S_{k+1}/S_k | F_k] <= exp(delta), where shocks are compensated.
    With positive execution credit u_k and nonnegative running costs,
    X_{k+1} <= exp(delta)*X_k + u_k. Because u_k>=0 and N finite,
    moving all u_k to time zero is an UPPER bound on every future X_k.
    E[A] <= SUM_k X_k <= (W0+U)*H. Final E[W_T] is separately
    bounded by W0+gamma*A+U-cost_floor.

    Original native OHLC threshold fills do not have proven U, so using
    U=0 is ONLY an idealized ref-price-executable counterfactual.
    """
    f = Frozen()
    if scenario not in ("NOMINAL", "STRESS"):
        raise ValueError("C18_UNKNOWN_SCENARIO")
    if source_proof_available:
        raise ValueError("C18_NO_NATIVE_SOURCE_PROOF_CLAIM_PERMITTED")
    fixed_cost = f.calendar_days * (
        f.nominal_calendar_per_day if scenario == "NOMINAL"
        else f.stress_calendar_per_day
    )
    h = f.terminal_hurdle_increment
    R = f.uninvested_wealth_factor_bound
    H = f.geometric_wealth_sum
    # This negative credit threshold is evidence of an insufficient
    # universal drift upper, not proof of profitability.
    max_u_for_exclusion_usd = (f.capital_usd + h + fixed_cost) / R - f.capital_usd
    exposure_fraction_threshold_u0 = math.expm1(
        math.log((f.capital_usd + h + fixed_cost) / f.capital_usd) / f.steps
    ) / f.step_gamma
    out: dict[str, Any] = {
        "schema": SCHEMA,
        "scenario": scenario,
        "total_intraday_substeps": f.steps,
        "gamma_per_step": f.step_gamma,
        "fully_invested_gross_growth_factor_upper": R,
        "geometric_wealth_factor": H,
        "original_terminal_hurdle_usd": h,
        "calendar_cost_lower_usd": fixed_cost,
        "general_population_A_upper_formula": "(20000+U_EXPECTED_UPPER_USD)*GEOMETRIC_WEALTH_FACTOR",
        "U_native_expected_upper_usd": None,
        "A_native_expected_upper_dollar_substeps": None,
        "original_12_percent_is_continuous_fraction": False,
        "ideal_no_positive_execution_credit_sensitivity_only": True,
        "ideal_U_zero_A_upper_dollar_substeps": f.capital_usd * H,
        "ideal_U_zero_expected_final_wealth_upper_usd": f.capital_usd * R - fixed_cost,
        "ideal_U_zero_daily_log_upper_bps": 10000 / f.calendar_days *
            math.log((f.capital_usd * R - fixed_cost) / f.capital_usd),
        "maximum_U_for_exclusion_at_fully_invested_bound_usd": max_u_for_exclusion_usd,
        "maximum_certified_uniform_exposure_fraction_if_U_zero": exposure_fraction_threshold_u0,
        "exposure_fraction_proven_for_native": False,
        "native_full_population_certified": False,
        "native_fill_executability_certified": False,
        "A_expected_population_bound_for_native_available": False,
        "U_expected_population_bound_for_native_available": False,
        "conditional_math_exclusion": None,
        "N9S": "NO_GO",
        "new_seeds": 0,
        "new_signals": 0,
        "new_economic_accounts": 0,
        "final_M10_opened": 0,
    }
    if positive_execution_credit_expectation_upper_usd is None:
        out["conclusion"] = "UNKNOWN_U_FOR_ORIGINAL_NATIVE_EXECUTION"
        return out
    u = _nonnegative_finite(
        positive_execution_credit_expectation_upper_usd, "U_EXPECTATION"
    )
    A = (f.capital_usd + u) * H
    final = (f.capital_usd + u) * R - fixed_cost
    if not (math.isfinite(A) and math.isfinite(final) and final > 0):
        raise ValueError("C18_INVALID_FINITE_UPPER_RESULT")
    log_upper_bps = (
        10000 / f.calendar_days * math.log(final / f.capital_usd)
    )
    out.update({
        "hypothetical_input_U_expected_upper_usd": u,
        "conditional_class_A_upper_dollar_substeps": A,
        "conditional_class_expected_final_wealth_upper_usd": final,
        "conditional_class_expected_log_upper_bps_per_day": log_upper_bps,
        "conditional_math_exclusion": final < f.capital_usd + h - 1e-9,
        "conclusion": "UNIVERSAL_WEAK_BOUND_NOT_TIGHT_ENOUGH"
            if final >= f.capital_usd + h else
            "EXCLUSION_IF_ALL_ASSUMPTIONS_INDEPENDENTLY_PROVED",
        "never_promote_from_unverified_U": True,
    })
    return out


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--U-expectation-upper", type=float)
    args = parser.parse_args()
    source = check_original(args.root)
    reports = [
        conditional_bound(s, args.U_expectation_upper)
        for s in ("NOMINAL", "STRESS")
    ]
    print("C18_FUNDED_WEALTH_GAMMA_DUAL=" + json.dumps(
        {"source": source, "contract": asdict(Frozen()), "reports": reports},
        sort_keys=True, allow_nan=False
    ))


if __name__ == "__main__":
    main()
