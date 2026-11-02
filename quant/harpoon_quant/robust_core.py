"""Research allocator with an independent certificate for the proposed whole lots.

The sealed allocator remains unchanged. This entrypoint only accepts a subset
of its proposals (all or cash), never increases risk, and never authorizes orders.
Original residual rows, not bootstrap replication count, drive mean uncertainty.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from . import core


def mean_uncertainty(values: np.ndarray, lag: int = 5) -> dict[str, float | int]:
    """Bartlett HAC SE with IID floor; conditional, not a finite-sample guarantee.

    Lags are observed session rows. Irregular calendar gaps are not interpolated.
    """
    x = np.asarray(values, dtype=float)
    if x.ndim != 1 or len(x) < 20 or not np.isfinite(x).all():
        raise ValueError("UNCERTAINTY_REQUIRES_20_ORIGINAL_ROWS")
    if type(lag) is not int or not 0 <= lag < len(x):
        raise ValueError("HAC_LAG_DOMAIN")
    centered = x - x.mean()
    n = len(x)
    iid = float(centered @ centered) / (n - 1)
    long_run = float(centered @ centered) / n
    for k in range(1, lag + 1):
        long_run += 2 * (1 - k / (lag + 1)) * float(centered[k:] @ centered[:-k]) / n
    return {"mean": float(x.mean()), "standard_error": math.sqrt(max(iid, long_run, 0) / n),
            "original_rows": n, "lag": lag, "iid_variance": iid,
            "hac_long_run_variance": long_run}


def residual_dates(calibration: dict[str, Any], names: list[str], when: str) -> list[str]:
    fit, now = core.timestamp(calibration["available_at"]), core.timestamp(when)
    if fit >= now:
        raise ValueError("CALIBRATION_NOT_AVAILABLE")
    common: set[str] | None = None
    for name in names:
        residuals = calibration["models"][name]["residuals"]
        if not isinstance(residuals, dict):
            raise ValueError("RESIDUAL_MAP_REQUIRED")
        for key, value in residuals.items():
            day = date.fromisoformat(key)
            if key != day.isoformat():
                raise ValueError("CANONICAL_RESIDUAL_DATE_REQUIRED")
            # Date-only evidence does not establish first-received timestamps.
            # At least exclude even a session's UTC end later than calibration.
            end = core.timestamp((day + timedelta(days=1)).isoformat() + "T00:00:00+00:00")
            if end > fit:
                raise ValueError("RESIDUAL_AFTER_CALIBRATION")
            core.finite(value, "RESIDUAL")
        common = set(residuals) if common is None else common & set(residuals)
    dates = sorted(common or [])
    if len(dates) < 20:
        raise ValueError("JOINT_ORIGINAL_RESIDUAL_ROWS_REQUIRED")
    return dates


def certify(request: dict[str, Any], calibration: dict[str, Any], cfg: core.Config,
            proposal: dict[str, Any]) -> dict[str, Any]:
    """Reprice selected integer lots and all holdings, independent of solver slacks."""
    chosen = proposal["selected"]
    candidates = {c["id"]: c for c in request["candidates"]}
    held = request.get("holdings", [])
    if not chosen:
        return {"verified": True, "scope": "NO_NEW_LOTS", "original_rows": 0}
    if len({s["id"] for s in chosen}) != len(chosen):
        raise ValueError("DUPLICATE_SELECTED_ID")
    instruments = [*held, *[candidates[s["id"]] for s in chosen]]
    names = sorted({c["underlying"] for c in instruments})
    dates = residual_dates(calibration, names, request["asof"])
    forecasts = {c["underlying"]: core.predict(calibration, c["underlying"], c["features"], request["asof"], cfg)
                 for c in instruments}
    base, stress, _ = core.scenarios(calibration, forecasts, cfg)
    partial = np.zeros(cfg.scenarios)
    partial_stress = np.zeros(3)
    portfolio = np.zeros(len(dates))
    incremental = np.zeros(len(dates))
    account = request["account"]
    equity = core.finite(account["equity"], "EQUITY", True)
    cash = min(core.finite(account["cash"], "CASH"), core.finite(account["buying_power"], "BUYING_POWER"))
    cash -= core.finite(account.get("pending_cash", 0), "PENDING")
    if cash < 0:
        raise ValueError("NEGATIVE_FREE_CASH")
    funding = gross = 0.0
    factor_gross: dict[str, float] = {}
    asset_gross: dict[str, float] = {}
    underlying_counts: dict[str, int] = {}
    for c in instruments:
        is_held = c in held
        selection = None if is_held else next(s for s in chosen if s["id"] == c["id"])
        lots = 1 if is_held else selection["lots"]
        if type(lots) is not int or lots <= 0:
            raise ValueError("POSITIVE_INTEGER_SELECTED_LOTS_REQUIRED")
        if not is_held:
            quantity = lots * c.get("lot_qty", 1)
            if abs(core.finite(selection["quantity"], "QUANTITY") - quantity) > 1e-9:
                raise ValueError("SELECTED_QUANTITY_MISMATCH")
            if quantity > core.finite(c.get("max_qty", 1e9), "MAX_QUANTITY") + 1e-9:
                raise ValueError("MAX_QUANTITY_EXCEEDED")
        cost, exposure = core.instrument(c, cfg)
        fee = core.finite(c.get("fixed_fee_usd", 0), "FIXED_FEE")
        if fee < 0:
            raise ValueError("NEGATIVE_FIXED_FEE")
        s = c["underlying"]
        original_returns = np.clip(forecasts[s] + np.array([calibration["models"][s]["residuals"][d] for d in dates]), -.95, 2)
        iv = calibration["models"][s].get("iv_residuals")
        original_iv = None
        if c["book"] == "options":
            if not isinstance(iv, dict) or not all(d in iv for d in dates):
                raise ValueError("JOINT_ORIGINAL_IV_REQUIRED")
            original_iv = np.clip(np.array([core.finite(iv[d], "IV_RESIDUAL") for d in dates]), -.8, 2)
        original = core.pnl_lot(c, original_returns, cfg, held=is_held, iv_changes=original_iv) * lots
        sampled = core.pnl_lot(c, base[s], cfg, held=is_held, iv_changes=base.get(s + "::iv")) * lots
        stressed = core.pnl_lot(c, stress[s], cfg, held=is_held, stress=True) * lots
        if not all(np.isfinite(v).all() for v in (original, sampled, stressed)):
            raise ValueError("NONFINITE_CERTIFICATE_VALUATION")
        portfolio += original - (0 if is_held else fee)
        if is_held:
            partial += sampled
            partial_stress += stressed
        else:
            incremental += original - fee
            partial += np.minimum(sampled, 0) - fee
            partial_stress += np.minimum(stressed, 0) - fee
            funding += cost * lots + fee
        gross += exposure * lots
        factor = c.get("factor", s)
        factor_gross[factor] = factor_gross.get(factor, 0) + exposure * lots
        asset_gross[s] = asset_gross.get(s, 0) + exposure * lots
        underlying_counts[s] = underlying_counts.get(s, 0) + 1
    cvar_limit = min(equity * cfg.cvar_fraction,
                     equity * cfg.daily_loss_fraction + min(0, account.get("daily_pnl", 0)))
    es = core.expected_shortfall(-partial, cfg.cvar_alpha)
    stress_loss = float(-partial_stress.min())
    checks = {"cash": funding <= cash + 1e-7,
              "gross": gross <= equity * cfg.gross_fraction + 1e-7,
              "asset": all(x <= equity * cfg.asset_fraction + 1e-7 for x in asset_gross.values()),
              "factor": all(x <= equity * cfg.factor_fraction + 1e-7 for x in factor_gross.values()),
              "position_count": len(instruments) <= cfg.max_positions,
              "one_campaign_per_underlying": max(underlying_counts.values()) <= 1,
              "partial_fill_cvar": es <= cvar_limit + 1e-7,
              "partial_fill_stress": stress_loss <= equity * cfg.stress_fraction + 1e-7}
    if not all(checks.values()):
        raise ValueError("ROUNDED_LOT_CERTIFICATE_FAILED:" + ",".join(k for k, v in checks.items() if not v))
    lag = min(len(dates) - 1, max(5, math.ceil(cfg.horizon_hours / 24)))
    mean = mean_uncertainty(incremental, lag)
    lower = mean["mean"] - cfg.uncertainty_z * mean["standard_error"]
    # Do not relax the legacy lower bound; this is an additional veto.
    if lower < cfg.min_edge_usd:
        raise ValueError("ORIGINAL_PANEL_EDGE_NOT_ROBUST")
    return {"verified": True, "checks": checks, "funding_usd": funding,
            "gross_exposure_usd": gross, "partial_fill_cvar_usd": es,
            "partial_fill_stress_usd": stress_loss, "incremental_mean_uncertainty": mean,
            "incremental_lower_bound_usd": lower,
            "portfolio_original_panel_mean_usd": float(portfolio.mean()),
            "chronology_scope": "UTC session dates checked against calibration; full first-received and label provenance not certified",
            "uncertainty_scope": "Conditional Bartlett HAC with IID floor; not selection-corrected or a profitability certificate"}


def allocate(request: dict[str, Any], calibration: dict[str, Any],
             cfg: core.Config | None = None) -> dict[str, Any]:
    cfg = cfg or core.Config()
    blocked = {"engine": "HARPOON_ROBUST_CORE_RESEARCH_1", "selected": [],
               "execution_allowed": False, "liveApproved": False, "level8_accredited": False,
               "status": "BLOCKED", "config_hash": core.digest(core.asdict(cfg)),
               "request_hash": core.digest(request), "calibration_hash": core.digest(calibration)}
    try:
        candidates, held = request.get("candidates", []), request.get("holdings", [])
        if len(candidates) > 96 or len(held) > 48:
            raise ValueError("INPUT_COMPUTE_CAP")
        ids = [c["id"] for c in [*candidates, *held]]
        if len(ids) != len(set(ids)):
            raise ValueError("DUPLICATE_INPUT_ID")
        names = sorted({c["underlying"] for c in [*candidates, *held]})
        if names:
            residual_dates(calibration, names, request["asof"])
        proposal = core.allocate(request, calibration, cfg)
        certificate = certify(request, calibration, cfg, proposal)
        return {**proposal, **blocked, "selected": proposal["selected"],
                "reason": proposal.get("reason"), "status": "VERIFIED_RESEARCH_PROPOSAL",
                "certificate": certificate}
    except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
        return {**blocked, "reason": str(exc)}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--model", required=True, type=Path)
    p.add_argument("--config", type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    cfg = core.Config(**json.loads(args.config.read_text())) if args.config else core.Config()
    result = allocate(json.loads(args.input.read_text()), json.loads(args.model.read_text()), cfg)
    with args.output.open("x") as handle:
        handle.write(json.dumps(result, allow_nan=False, sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    main()
