#!/usr/bin/env python3
"""Deterministic WEAK feasibility bounds; never simulate prices or strategies.

The admission bound is conditional on coherent marked admission and trading at
the actual compensated price process. It is NOT a certificate for native OHLC
threshold fills. Frozen MODULATION9 sources are verified, never rewritten.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from bisect import bisect_right
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

GENERATOR_PATH = "quant/harpoon_quant/modulation9.py"
GENERATOR_SHA256 = "9d4afa402d2b70791f175e79219495f9bbbe25eb3cd0b7e9212cef6bccbd68ab"
PROTOCOL_SHA256 = "de694919b0908fc0ecf474c9612ff7d54fe04db635a385e12ffa0f81abc7780d"

# Constants absent from protocol.json, bound to the exact generator SHA above.
REGIME_POSITIVE_PROBABILITY = 0.4
WEAK_SIGMA_MULTIPLIER = 1.25
ACTIVITY_LOG_MAX = 0.7
MIXTURE_PROBABILITY = 0.004
MIXTURE_SIGMA_MULTIPLIER = 4.0
JUMP_PROBABILITY_PER_SIDE = 0.003
JUMP_DOWN, JUMP_UP = 0.97, 1.03


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_frozen_sources(repo: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    protocol_path = repo / "research/modulation9/protocol.json"
    registration_path = repo / "research/modulation9/registration.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    registration = json.loads(registration_path.read_text(encoding="utf-8"))
    if sha256(protocol_path) != PROTOCOL_SHA256:
        raise ValueError("UNSUPPORTED_PROTOCOL_BYTES")
    if registration["protocol_sha256"] != PROTOCOL_SHA256:
        raise ValueError("REGISTRATION_PROTOCOL_MISMATCH")
    if sha256(repo / GENERATOR_PATH) != GENERATOR_SHA256:
        raise ValueError("UNSUPPORTED_GENERATOR_LAW")
    for relative, expected in registration["sources_sha256"].items():
        if sha256(repo / relative) != expected:
            raise ValueError(f"FROZEN_SOURCE_CHANGED:{relative}")
    return protocol, {
        "protocol_sha256": PROTOCOL_SHA256,
        "registration_sha256": sha256(registration_path),
        "generator_sha256": GENERATOR_SHA256,
        "registered_sources_verified": len(registration["sources_sha256"]),
        "all_registered_sources_match": True,
    }


def calendar_facts(protocol: dict[str, Any]) -> dict[str, Any]:
    cfg = protocol["generator"]
    day = datetime.fromisoformat(cfg["first_date"]).replace(tzinfo=UTC)
    count = cfg["warmup_sessions"] + cfg["evaluation_sessions"] + cfg["buffer_sessions"]
    sessions: list[datetime] = []
    while len(sessions) < count:
        if day.weekday() < 5:
            sessions.append(day.replace(hour=14, minute=30))
        day += timedelta(days=1)
    first = sessions[cfg["warmup_sessions"]]
    last = sessions[cfg["warmup_sessions"] + cfg["evaluation_sessions"] - 1]
    calendar_days = (last.date() - first.date()).days + 1
    substeps = cfg["intrabar_substeps"]
    # Calendar timestamps only. No generator or price process is executed.
    ticks = [int(s.timestamp() * 1000) + (k + 1) * 300_000 // substeps
             for s in sessions for k in range(cfg["bars_per_session"] * substeps)]
    nights = [int(s.timestamp() * 1000) for s in sessions]
    horizon = int(protocol["gates"]["max_holding_elapsed_hours"] * 3_600_000)

    def max_events(times: list[int]) -> int:
        return max(i + 1 - bisect_right(times, t - horizon)
                   for i, t in enumerate(times))

    # A 72-hour interval touches at most four calendar dates. Use all four
    # full sessions/nights in the proof, intentionally looser than the grid.
    covering_dates = math.ceil(horizon / 86_400_000) + 1
    return {
        "evaluation_first_date": first.date().isoformat(),
        "evaluation_last_date": last.date().isoformat(),
        "evaluation_sessions": cfg["evaluation_sessions"],
        "inclusive_charged_calendar_days": calendar_days,
        "total_evaluation_bars": cfg["evaluation_sessions"] * cfg["bars_per_session"],
        "total_evaluation_substeps": cfg["evaluation_sessions"] * cfg["bars_per_session"] * substeps,
        "holding_hours": protocol["gates"]["max_holding_elapsed_hours"],
        "max_substep_events_in_half_open_holding_window": max_events(ticks),
        "max_overnight_events_in_half_open_holding_window": max_events(nights),
        "proof_covering_calendar_dates": covering_dates,
        "proof_upper_full_bars_in_holding_window": covering_dates * cfg["bars_per_session"],
        "proof_upper_overnights_in_holding_window": covering_dates,
        "calendar_definition": cfg["calendar"],
    }


def logsumexp(values: list[float]) -> float:
    maximum = max(values)
    return maximum + math.log(sum(math.exp(x - maximum) for x in values))


def log_bar_moment(q: float, sigma: float) -> float:
    c = q * (q - 1.0) / 2.0
    return logsumexp([
        math.log1p(-MIXTURE_PROBABILITY) + c * sigma**2,
        math.log(MIXTURE_PROBABILITY) + c * (MIXTURE_SIGMA_MULTIPLIER * sigma)**2,
    ])


def log_jump_moment(q: float) -> float:
    p = JUMP_PROBABILITY_PER_SIDE
    return logsumexp([
        math.log1p(-2.0 * p),
        math.log(p) + q * math.log(JUMP_DOWN),
        math.log(p) + q * math.log(JUMP_UP),
    ])


def exposure_fraction(gross_admission: float, relative_price_max: float) -> float:
    return gross_admission * relative_price_max / (1.0 - gross_admission + gross_admission * relative_price_max)


def scenario_bound(protocol: dict[str, Any], calendar: dict[str, Any],
                   drift_scale: float, sigma_scale: float) -> dict[str, Any]:
    cfg = protocol["generator"]
    g = float(protocol["limits"]["grossFraction"])
    capital = float(protocol["limits"]["capitalUsd"])
    days = calendar["inclusive_charged_calendar_days"]
    cost = float(protocol["scenarios"]["NOMINAL"]["external_cost_usd_per_calendar_day"])
    total_cost_ratio = cost * days / capital
    assets = len(protocol["traded_universe"])
    p_favorable = 1.0 - (1.0 - REGIME_POSITIVE_PROBABILITY)**assets
    delta = cfg["weak_drift_per_bar"] * drift_scale
    substeps = cfg["intrabar_substeps"]
    n = calendar["total_evaluation_substeps"]
    bars = calendar["total_evaluation_bars"]
    favorable_step_mean_excess = math.expm1(delta / substeps)
    activity_max = math.exp(ACTIVITY_LOG_MAX)
    bar_sigma = max(cfg["bar_sigma"][:assets]) * WEAK_SIGMA_MULTIPLIER * sigma_scale * activity_max
    night_sigma = max(cfg["overnight_sigma"][:assets]) * sigma_scale * activity_max
    holding_bars = calendar["proof_upper_full_bars_in_holding_window"]
    holding_nights = calendar["proof_upper_overnights_in_holding_window"]

    def envelope(q: int) -> tuple[float, float, int]:
        log_end_moment = (holding_bars * log_bar_moment(q, bar_sigma)
                          + holding_nights * q * (q - 1.0) / 2.0 * night_sigma**2
                          + holding_nights * log_jump_moment(q))
        log_u = (delta * holding_bars + math.log(q / (q - 1.0))
                 + (math.log(assets) + log_end_moment) / q)
        u = math.exp(log_u)
        return exposure_fraction(g, u), u, q

    gamma, u, q = min(envelope(order) for order in range(2, 501))
    # This bound uses f<=1, NOT gamma, in E[shadow terminal wealth]. Exposure
    # and account wealth can be correlated; substituting gamma is unjustified.
    log_shadow_wealth_factor_upper = delta * bars
    fixed_log_penalty_lower = total_cost_ratio * math.exp(-log_shadow_wealth_factor_upper)
    admission_gross_log_upper = n * p_favorable * gamma * favorable_step_mean_excess
    admission_net_log_upper = admission_gross_log_upper - fixed_log_penalty_lower
    continuous_gross_log_upper = n * p_favorable * g * favorable_step_mean_excess
    continuous_log_shadow_factor = n * math.log1p(g * favorable_step_mean_excess)
    continuous_fixed_penalty = total_cost_ratio * math.exp(-continuous_log_shadow_factor)
    first_order_gross = g * p_favorable * delta * bars / days
    hurdle = float(protocol["statistics"]["minimum_effect_daily_log"])
    return {
        "drift_multiplier": drift_scale,
        "sigma_multiplier": sigma_scale,
        "favorable_regime_probability": p_favorable,
        "positive_drift_log_parameter_per_bar": delta,
        "positive_mean_arithmetic_excess_per_substep": favorable_step_mean_excess,
        "max_unmixed_intraday_bar_sigma": bar_sigma,
        "max_overnight_sigma": night_sigma,
        "first_order_continuous_cap_heuristic": {
            "gross_bp_per_calendar_day": first_order_gross * 10000.0,
            "fixed_cost_bp_of_initial_capital_per_calendar_day": cost / capital * 10000.0,
            "net_bp_per_calendar_day": (first_order_gross - cost / capital) * 10000.0,
            "status": "HEURISTIC_NOT_NATIVE_BOUND",
        },
        "continuous_cap_conditional_bound": {
            "net_expected_log_bp_per_calendar_day_upper":
                (continuous_gross_log_upper - continuous_fixed_penalty) / days * 10000.0,
            "status": "VALID_ONLY_IF_CONTINUOUS_PRICE_CONSISTENT_GROSS_CAP",
        },
        "admission_72h_conditional_bound": {
            "moment_order_q": q,
            "moment_search": "Deterministic valid inequalities at integer q=2..500; no trading-policy selection.",
            "expected_max_relative_price_upper": u,
            "uniform_conditional_mean_gross_fraction_upper": gamma,
            "gross_expected_log_bp_per_calendar_day_upper": admission_gross_log_upper / days * 10000.0,
            "fixed_expected_log_penalty_bp_per_calendar_day_lower": fixed_log_penalty_lower / days * 10000.0,
            "net_expected_log_bp_per_calendar_day_upper": admission_net_log_upper / days * 10000.0,
            "hurdle_log_bp_per_calendar_day": hurdle * 10000.0,
            "upper_bound_below_hurdle": admission_net_log_upper / days < hurdle,
            "status": "THEOREM_CONDITIONAL_ON_COHERENT_ADMISSION_AND_PRICE_CONSISTENT_EXECUTION",
            "native_ohlc_replay_infeasibility_certified": False,
        },
    }


def self_checks(protocol: dict[str, Any], calendar: dict[str, Any],
                cases: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "compensated_bar_first_moment_is_one": abs(math.expm1(log_bar_moment(1.0, 0.02))) < 1e-14,
        "symmetric_jump_first_moment_is_one": abs(math.expm1(log_jump_moment(1.0))) < 1e-14,
        "two_asset_positive_regime_probability": abs(1.0 - 0.6**2 - 0.64) < 1e-15,
        "exposure_fraction_at_no_price_change_equals_cap": abs(exposure_fraction(0.12, 1.0) - 0.12) < 1e-15,
        "exposure_fraction_is_increasing_below_one": 0.12 < exposure_fraction(0.12, 2.0) < 1.0,
        "evaluation_calendar_is_126_sessions_176_charged_dates":
            calendar["evaluation_sessions"] == 126 and calendar["inclusive_charged_calendar_days"] == 176,
        "substeps_have_correct_dimensions": calendar["total_evaluation_substeps"] == 126 * 78 * 8,
        "proof_calendar_cover_dominates_observed_event_grid":
            calendar["max_substep_events_in_half_open_holding_window"]
            <= calendar["proof_upper_full_bars_in_holding_window"] * protocol["generator"]["intrabar_substeps"]
            and calendar["max_overnight_events_in_half_open_holding_window"]
            <= calendar["proof_upper_overnights_in_holding_window"],
        "zero_volatility_bar_moment_is_one": abs(math.expm1(log_bar_moment(23.0, 0.0))) < 1e-14,
        "coarser_supported_final_bound_is_not_smaller":
            cases["supported_final_worst_parameters"]["admission_72h_conditional_bound"]["net_expected_log_bp_per_calendar_day_upper"]
            >= cases["development_parameters"]["admission_72h_conditional_bound"]["net_expected_log_bp_per_calendar_day_upper"],
        "all_reported_scalar_results_are_finite": all(
            math.isfinite(case["admission_72h_conditional_bound"]["net_expected_log_bp_per_calendar_day_upper"])
            for case in cases.values()),
        "fixed_cost_unit_is_usd_per_calendar_day":
            protocol["scenarios"]["NOMINAL"]["external_cost_usd_per_calendar_day"]
            * calendar["inclusive_charged_calendar_days"] == 176.0,
    }
    if not all(checks.values()):
        raise AssertionError({name: value for name, value in checks.items() if not value})
    return {"passed": len(checks), "failed": 0, "checks": checks}


def diagnose(repo: Path) -> dict[str, Any]:
    protocol, integrity = verify_frozen_sources(repo)
    calendar = calendar_facts(protocol)
    shift = protocol["generator"]["final_parameter_shift"]
    cases = {
        "development_parameters": scenario_bound(protocol, calendar, 1.0, 1.0),
        "supported_final_worst_parameters": scenario_bound(
            protocol, calendar, max(shift["drift_multiplier_range"]), max(shift["sigma_multiplier_range"])),
    }
    checks = self_checks(protocol, calendar, cases)
    _, integrity_after = verify_frozen_sources(repo)
    if integrity != integrity_after:
        raise ValueError("SOURCE_IDENTITY_CHANGED_DURING_DIAGNOSTIC")
    return {
        "schema": "HARPOON_MODULATION10_DETERMINISTIC_FEASIBILITY_1",
        "origin": "SYNTHETIC_LAW_ANALYSIS_NO_PRICE_PATHS_GENERATED",
        "diagnostic_role": "NONSELECTABLE_THEORETICAL_UPPER_BOUND",
        "registered_source_integrity_before_and_after": integrity,
        "diagnostic_script_sha256": sha256(Path(__file__).resolve()),
        "economic_policy_executions": 0,
        "generator_calls": 0,
        "costs_hurdles_generator_and_frozen_sources_changed": False,
        "native_ohlc_replay_infeasibility_certified": False,
        "theorem_assumptions": [
            "Two tradable assets; long-only; nonnegative cash; no borrowing or external cash inflows.",
            "Predictable trading at the actual compensated substep/overnight prices; no OHLC threshold interpolation.",
            "Every admission caps total risky marked notional at12% of coherent contemporary actual equity.",
            "Every individual holding is liquidated within72 elapsed hours; subsequent sales cannot increase risky holdings.",
            "Zero-interest cash, all variable execution costs nonnegative, fixed nominal cost1USD per charged calendar date.",
            "Positive terminal wealth, otherwise log-growth cannot satisfy the target.",
        ],
        "unresolved_native_engine_bridges": [
            "Admission uses causal available marks and reservations before IOC; equivalence to a coherent contemporary cap must be proved.",
            "Native OHLC fills may pay a threshold between sampled substep prices; a martingale price law alone does not prove self-financing wealth under those fills.",
        ],
        "interpretation": [
            "The bound concerns expected full-horizon calendar-day log growth, not a pathwise maximum or a finite holdout statistic.",
            "The ideal causal current-regime oracle is included in the theorem class; it does not get future prices.",
            "A numerical native replay can exceed this conditional bound if the mathematical assumptions do not describe its execution semantics.",
            "Development score>0 is a different criterion from the nominal final adjusted lower bound>1bp/day.",
            "The .25% open-risk, drawdown, session-loss and discrete-share restrictions are relaxed, making this an upper bound for any subclass satisfying them.",
        ],
        "calendar": calendar,
        "cases": cases,
        "deterministic_self_checks": checks,
        "primary_mathematical_reference": {
            "title": "Amir Dembo, Probability Theory: STAT310/MATH230, Corollary5.2.13 (Doob Lp)",
            "url": "https://web.stanford.edu/class/stats310c/NOTES/lnotes.pdf",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, help="New JSON evidence path; refuses to overwrite.")
    args = parser.parse_args()
    result = diagnose(args.repo.resolve())
    rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(rendered)
        print(json.dumps({"output": str(args.output.resolve()), "sha256": sha256(args.output),
                          "self_checks_passed": result["deterministic_self_checks"]["passed"],
                          "economic_policy_executions": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
