#!/usr/bin/env python3
"""C15: conservative funded-wealth exclusion screen for frozen M9 WEAK.

This is a mathematical *conditional* screen, NOT a native full-population
certificate. It consumes no stochastic market draws, opens no final accounts,
and cannot authorize live/paper orders. Bound inputs MUST come from separate,
independently audited, population-level certificates; a single replay is not one.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

M9_PROTOCOL_GIT_BLOB = "c49c8156f9d2f109f5eda0fd98d1b7290a837d1a"
ORIGINAL_DAYS = 176
ORIGINAL_SESSIONS = 126
ORIGINAL_BARS_PER_SESSION = 78
ORIGINAL_SUBSTEPS_PER_BAR = 8
ORIGINAL_CAPITAL = 20000.0
ORIGINAL_HURDLE = 0.0001
ORIGINAL_WEAK_DRIFT_PER_BAR = 0.000025
ORIGINAL_MAX_DRIFT_MULT = 1.1
ORIGINAL_FEES = {"NOMINAL": 1.0, "STRESS": 2.0}
SCHEMA = "HARPOON_FWN9_C15_FUNDED_WEAK_EXPECTED_WEALTH_SCREEN_1"


@dataclass(frozen=True)
class Contract:
    original_days: int = ORIGINAL_DAYS
    sessions: int = ORIGINAL_SESSIONS
    bars_per_session: int = ORIGINAL_BARS_PER_SESSION
    substeps_per_bar: int = ORIGINAL_SUBSTEPS_PER_BAR
    capital_usd: float = ORIGINAL_CAPITAL
    daily_log_hurdle: float = ORIGINAL_HURDLE
    weak_drift_per_bar: float = ORIGINAL_WEAK_DRIFT_PER_BAR
    maximal_drift_multiplier: float = ORIGINAL_MAX_DRIFT_MULT

    @property
    def total_intraday_steps(self) -> int:
        return self.sessions * self.bars_per_session * self.substeps_per_bar

    @property
    def max_conditional_price_drift_per_step(self) -> float:
        return math.expm1(
            self.weak_drift_per_bar * self.maximal_drift_multiplier
            / self.substeps_per_bar
        )

    @property
    def terminal_hurdle_increment_usd(self) -> float:
        return self.capital_usd * math.expm1(
            self.original_days * self.daily_log_hurdle
        )


def git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(
        f"blob {len(raw)}\0".encode("ascii") + raw
    ).hexdigest()  # noqa: S324 - used for Git source identity, never cryptosecurity


def verify_original_protocol(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if git_blob_sha1(raw) != M9_PROTOCOL_GIT_BLOB:
        raise ValueError("C15_FROZEN_M9_GIT_BLOB_MISMATCH")
    p: dict[str, Any] = json.loads(raw)
    g, lim, stats, scenarios, gates = (p[k] for k in (
        "generator", "limits", "statistics", "scenarios", "gates"
    ))
    checks: dict[str, bool] = {
        "capital": lim["capitalUsd"] == ORIGINAL_CAPITAL,
        "admission_only": lim["grossFraction"] == .12 and
            lim["assetFraction"] == .12 and
            p["risk_semantics"].startswith("12% gross/name and0.25% risk are admission"),
        "risk": lim["openRiskFraction"] == .0025,
        "daily_loss": lim["dailyLoss"] == .02,
        "drawdown": lim["maxDrawdown"] == .08,
        "world": "WEAK" in g["worlds"],
        "assets": p["traded_universe"] == ["SYNA", "SYNB"],
        "sessions": g["evaluation_sessions"] == ORIGINAL_SESSIONS,
        "bars": g["bars_per_session"] == ORIGINAL_BARS_PER_SESSION,
        "substeps": g["intrabar_substeps"] == ORIGINAL_SUBSTEPS_PER_BAR,
        "drift": g["weak_drift_per_bar"] == ORIGINAL_WEAK_DRIFT_PER_BAR,
        "drift_support": g["final_parameter_shift"]["drift_multiplier_range"] == [.75, 1.1],
        "stat_hurdle": stats["minimum_effect_daily_log"] == ORIGINAL_HURDLE,
        "gate_hurdle": gates["nominal_edge_worlds_adjusted_lower"] == ">0.0001 daily net log",
        "nominal_fee": scenarios["NOMINAL"]["external_cost_usd_per_calendar_day"] == 1.0,
        "stress_fee": scenarios["STRESS"]["external_cost_usd_per_calendar_day"] == 2.0,
        "hold72": gates["max_holding_elapsed_hours"] == 72,
    }
    wrong = [k for k, valid in checks.items() if not valid]
    if wrong:
        raise ValueError("C15_FROZEN_M9_CONTRACT_CHANGED:" + ",".join(wrong))
    return {"registered_git_blob": M9_PROTOCOL_GIT_BLOB,
            "verified_rules": sorted(checks)}


def finite_nonnegative(name: str, x: float) -> float:
    if not isinstance(x, (int, float)) or not math.isfinite(x) or x < 0:
        raise ValueError("C15_INVALID_" + name)
    return float(x)


def bound(
    scenario: str,
    expected_dollar_substep_exposure_upper: float | None = None,
    expected_positive_execution_credit_upper_usd: float | None = None,
    separately_proved_extra_cost_lower_usd: float = 0.0,
    contract: Contract = Contract(),
) -> dict[str, Any]:
    """Return a sharp first-moment Jensen screen, with no proof upgrade.

    A = E_WEAK sum(q_before[a,t]*S[a,t]), covering every intraday substep,
    not just held campaigns; q must be predictable and funded long-only.
    U >= E_WEAK sum(positive execution-price credits relative to tradable
    substep reference); *not* merely observed favorable replay marks.
    C lower bound is calendar fee plus separately proved nonnegative costs.

    Under frozen WEAK, E[S_next-S|F_pre] <= gamma*S for long shares;
    overnight compensated shocks/jumps contribute zero conditional mean.
    E W_T <= W0 + gamma*A + U - C.  Jensen then bounds E log(W_T/W0).
    Lack of a certificate on A or U cannot be treated as zero.
    """
    if scenario not in ORIGINAL_FEES:
        raise ValueError("C15_INVALID_COST_SCENARIO")
    extra = finite_nonnegative("EXTRA_COST_LOWER", separately_proved_extra_cost_lower_usd)
    cost_floor = ORIGINAL_FEES[scenario] * contract.original_days + extra
    hurdle_usd = contract.terminal_hurdle_increment_usd
    gamma = contract.max_conditional_price_drift_per_step
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "scenario": scenario,
        "unit": "USD expected wealth, 176 calendar-day mean log",
        "original_capital_usd": contract.capital_usd,
        "calendar_days": contract.original_days,
        "intraday_steps": contract.total_intraday_steps,
        "WEAK_max_drift_multiplier": contract.maximal_drift_multiplier,
        "gamma_per_step": gamma,
        "terminal_hurdle_increment_usd": hurdle_usd,
        "fixed_calendar_cost_lower_usd": ORIGINAL_FEES[scenario] * contract.original_days,
        "total_cost_lower_usd": cost_floor,
        "exposure_dollar_steps_threshold_if_U_is_zero":
            (hurdle_usd + cost_floor) / gamma,
        "full_native_population_certified": False,
        "native_executable_fill_equivalence_certified": False,
        "M10_final_accounts_opened": 0,
        "new_economic_accounts": 0,
        "N9S_admission_verdict": "NO_GO",
    }
    if (expected_dollar_substep_exposure_upper is None
            or expected_positive_execution_credit_upper_usd is None):
        result.update({
            "conditional_economic_screen": "UNIDENTIFIED_MISSING_POPULATION_BOUNDS",
            "math_exclusion_if_inputs_proved": None,
            "expected_daily_log_upper_bps": None,
            "incomplete_evidence": [
                "population upper expectation of actual predictable dollar-substep inventory",
                "population upper expectation of positive execution credits on tradeable substeps",
                "complete native funding/receipts/partial-rejection/outage/multicell proof"
            ],
        })
        return result
    a = finite_nonnegative("EXPOSURE_UPPER", expected_dollar_substep_exposure_upper)
    u = finite_nonnegative("EXECUTION_CREDIT_UPPER", expected_positive_execution_credit_upper_usd)
    drift_wealth_upper = gamma * a + u - cost_floor
    expected_final_wealth_upper = contract.capital_usd + drift_wealth_upper
    if expected_final_wealth_upper <= 0:
        raise ValueError("C15_INCONSISTENT_EXPECTED_WEALTH_UPPER")
    upper_bps = (
        10000 / contract.original_days *
        math.log(expected_final_wealth_upper / contract.capital_usd)
    )
    result.update({
        "expected_dollar_substep_exposure_upper": a,
        "expected_positive_execution_credit_upper_usd": u,
        "expected_final_wealth_upper_usd": expected_final_wealth_upper,
        "expected_daily_log_upper_bps": upper_bps,
        "math_exclusion_if_inputs_proved":
            drift_wealth_upper < hurdle_usd,
        "conditional_economic_screen": (
            "EXCLUDED_IF_POPULATION_BOUNDS_INDEPENDENTLY_PROVED"
            if drift_wealth_upper < hurdle_usd else
            "NOT_EXCLUDED_BY_THIS_UPPER_BOUND"
        ),
        "input_proof_integrity_independently_verified": False,
        "not_a_final_go_certificate": True,
    })
    return result


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--protocol", type=Path)
    p.add_argument("--scenario", choices=tuple(ORIGINAL_FEES), default="NOMINAL")
    p.add_argument("--exposure-upper", type=float)
    p.add_argument("--execution-credit-upper", type=float)
    p.add_argument("--extra-cost-floor", type=float, default=0.0)
    args = p.parse_args()
    provenance = (
        verify_original_protocol(args.protocol) if args.protocol
        else {"registered_git_blob": M9_PROTOCOL_GIT_BLOB,
              "source_verification": "NOT_RUN_NO_PROTOCOL_PATH"}
    )
    out = bound(args.scenario, args.exposure_upper, args.execution_credit_upper,
                args.extra_cost_floor)
    print(json.dumps({"frozen_provenance": provenance,
                      "contract": asdict(Contract()),
                      "screen": out}, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
