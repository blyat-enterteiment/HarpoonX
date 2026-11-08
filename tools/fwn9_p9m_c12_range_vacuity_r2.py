"""C12: lower bound on the expected *upper-envelope RHS*, not trading profit.

Uses the ideal independent-Gaussian WEAK law registered by M9. The model
does not claim anything about finite PRNG support, signals or broker fills.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from fractions import Fraction
from pathlib import Path
from typing import Any

M9_GENERATOR_BLOB = "b73f03b6d0ff2396e54c527b1da227953a1fdcc7"
M9_PROTOCOL_BLOB = "c49c8156f9d2f109f5eda0fd98d1b7290a837d1a"
CALENDAR_DAYS = 176


def git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()  # noqa: S324 - Git blob identity


def require(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(f"C12_ORIGINAL_CONTRACT_MISMATCH_{code}")


def source_integrity(root: Path) -> dict[str, str]:
    frozen = {
        "quant/harpoon_quant/modulation9.py": M9_GENERATOR_BLOB,
        "research/modulation9/protocol.json": M9_PROTOCOL_BLOB,
    }
    for path, original in frozen.items():
        require(git_blob_sha1((root / path).read_bytes()) == original, path)
    source = (root / "quant/harpoon_quant/modulation9.py").read_text(encoding="utf-8")
    for needle in (
        'activity = float(math.exp(max(-.7, min(.7, log_activity))))',
        'base_sigma = np.array(cfg["bar_sigma"]) * sigma_scale * (1.25 if world == "WEAK" else 1.)',
        'z = loading * common_z + math.sqrt(1 - loading**2) * rng.normal(size=(78, substeps, 3))',
        'mixture = np.where(rng.random((78, 3)) < .004, 4., 1.)',
        'sigmas = base_sigma[None, :] * activity * mixture',
        'sigmas[:, None, :] / math.sqrt(substeps) * z',
    ):
        require(needle in source, "GAUSSIAN_SOURCE_DECOMPOSITION")
    return frozen


def check_contract(p: dict[str, Any]) -> None:
    g = p["generator"]
    limits = p["limits"]
    checks = {
        "universe": p["traded_universe"] == ["SYNA", "SYNB"],
        "WEAK": "WEAK" in g["worlds"],
        "capital": limits["capitalUsd"] == 20000,
        "gross_admission": limits["grossFraction"] == 0.12,
        "asset_admission": limits["assetFraction"] == 0.12,
        "risk": limits["riskFraction"] == 0.0025,
        "open_risk": limits["openRiskFraction"] == 0.0025,
        "daily_loss": limits["dailyLoss"] == 0.02,
        "drawdown": limits["maxDrawdown"] == 0.08,
        "sessions": g["evaluation_sessions"] == 126,
        "bars": g["bars_per_session"] == 78,
        "substeps": g["intrabar_substeps"] == 8,
        "sigma_SYNA": g["bar_sigma"][0] == 0.00075,
        "loading": g["correlation_loading"] == 0.45,
        "min_final_sigma": g["final_parameter_shift"]["sigma_multiplier_range"][0] == 0.9,
        "hurdle": p["statistics"]["minimum_effect_daily_log"] == 0.0001,
        "fixed_nominal": p["scenarios"]["NOMINAL"]["external_cost_usd_per_calendar_day"] == 1,
        "fixed_stress": p["scenarios"]["STRESS"]["external_cost_usd_per_calendar_day"] == 2,
        "weak_drift": g["weak_drift_per_bar"] == 0.000025,
        "holding": p["gates"]["max_holding_elapsed_hours"] == 72,
    }
    for name, ok in checks.items():
        require(bool(ok), name)


def bound(p: dict[str, Any], stage: str) -> dict[str, float | str | bool | int]:
    """E log R >= E|log(S_T/S_0)| >= sqrt(2/pi)*sqrt(N)*sigma_min.

    After conditioning on activity, regimes, mixtures, common shocks, gaps
    and overnight moves, the idiosyncratic z terms remain independent normals.
    For any conditional mean, E|N(mu,variance)| >= sqrt(2*variance/pi).
    Two OHLC endpoints from 126 full evaluation sessions belong to C11 R.
    """
    check_contract(p)
    if stage not in ("development", "final"):
        raise ValueError("C12_INVALID_STAGE")
    g = p["generator"]
    scale = 1.0 if stage == "development" else float(
        g["final_parameter_shift"]["sigma_multiplier_range"][0]
    )
    n = int(g["evaluation_sessions"]) * int(g["bars_per_session"]) * int(g["intrabar_substeps"])
    sub = int(g["intrabar_substeps"])
    load = float(g["correlation_loading"])
    sigma = (
        float(g["bar_sigma"][0]) * 1.25 * scale * math.exp(-0.7)
        * math.sqrt(1 - load**2) / math.sqrt(sub)
    )
    expectation_lower = math.sqrt(2 / math.pi) * math.sqrt(n) * sigma
    fixed_ratio = CALENDAR_DAYS / 20000
    return {
        "stage": stage, "independent_gaussian_steps": n,
        "min_idiosyncratic_step_sigma": sigma,
        "E_log_R_lower": expectation_lower,
        "C10_C11_RHS_lower_bp_per_day": expectation_lower * 10000 / CALENDAR_DAYS,
        "unchanged_hurdle_bp_per_day": 1.0,
        "hypothetical_net_RHS_lower_bp_per_day": (
            expectation_lower + math.log1p(-fixed_ratio)
        ) * 10000 / CALENDAR_DAYS,
        "RHS_lower_exceeds_hurdle": expectation_lower > CALENDAR_DAYS / 10000,
        "requires_J_positive": False,
        "certifies_native_N9S_impossibility": False,
    }


def rational_certificate() -> dict[str, str | bool | float]:
    """Conservative exact rational inequalities (separate from FP arithmetic).

    sqrt(2/pi)>.79, sqrt(126*78*8)>280, exp(-.7)>.49,
    sqrt(1-.45**2)>.89, sqrt(8)<2.83;
    log(1-x)>=-x/(1-x), x=176/20000.
    """
    r = Fraction(79, 100) * 280 * Fraction(75, 100000)
    r *= Fraction(5, 4) * Fraction(9, 10) * Fraction(49, 100)
    r *= Fraction(89, 100) / Fraction(283, 100)
    conservative_net = r - Fraction(176, 20000 - 176)
    hurdle = Fraction(176, 10000)
    require(conservative_net > hurdle, "RATIONAL_HURDLE")
    return {
        "rational_E_log_R_lower": str(r),
        "rational_discounted_lower": str(conservative_net),
        "rational_hurdle": str(hurdle),
        "discounted_lower_bp_per_day": float(conservative_net * 10000 / 176),
        "strictly_above_original_hurdle": conservative_net > hurdle,
    }


def report(root: Path) -> dict[str, Any]:
    checked = source_integrity(root)
    p: dict[str, Any] = json.loads((root / "research/modulation9/protocol.json").read_text())
    return {
        "schema": "FWN9_C12_RANGE_ENVELOPE_AUDIT_1",
        "registered_git_blobs": checked,
        "world": "WEAK", "basis": "IDEAL_GAUSSIAN_NOT_FINITE_PRNG_SAMPLE",
        "stages": [bound(p, "development"), bound(p, "final")],
        "rational_certificate": rational_certificate(),
        "finding": "GLOBAL_C10_C11_RANGE_UPPER_ENVELOPE_MATHEMATICALLY_VACUOUS_FOR_1BP",
        "native_infeasibility_certified": False,
        "economic_accounts": 0, "new_seeds": 0,
        "final_M10_opened": 0, "prospective_alpha_spent": 0,
        "operational_gates_complete": False,
        "OHLC_substep_equivalence": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(report(args.root), sort_keys=True))


if __name__ == "__main__":
    main()
