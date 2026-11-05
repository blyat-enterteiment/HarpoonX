"""Recompute a research qualification from funded accounts, never from a score.

The standard is an internal research mandate, not an industry profitability
rating. Historical evidence cannot authenticate itself or authorize execution.
External gates remain explicit until their observed evidence is reconciled by
the existing forward-admission and independent-review workflow.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from typing import Any

import numpy as np

from .compound import paired_growth
from .multiasset import number, stamp
from .remediation import economic_checks, trade_contributions
from .roadmap9.forward import block_growth_test, digest

STANDARD: dict[str, Any] = {
    "schema": "HARPOON_LEVEL8_RESEARCH_STANDARD_1",
    "interpretation": "INTERNAL_MANDATE_NOT_A_RETURN_FORECAST_OR_UNIVERSAL_SCORE",
    "nominal_annual_net_return": 0.10,
    "stress_net_return_floor": 0.0,
    "max_drawdown": 0.08,
    "max_daily_loss": 0.02,
    "max_holding_hours": 72,
    "max_entry_gross_fraction": 0.12,
    "max_entry_stop_risk_fraction": 0.0025,
    "minimum_calendar_days": 365,
    "minimum_closed_campaigns": 100,
    "minimum_campaigns_per_book": 20,
    "maximum_positive_pnl_symbol_share": 0.50,
    "minimum_forward_calendar_days": 180,
    "statistics": {
        "minimum_observations": 365,
        "block_lengths": [5, 20],
        "draws": 20000,
        "family_endpoints": 16,
        "alpha": 0.05,
        "minimum_mean_log_edge": 0.0,
        "seed": 319,
        "global_search_history_complete": False,
    },
    "execution_allowed": False,
}


def _row(identifier: str, status: str, evidence: Any, remedy: str) -> dict[str, Any]:
    return {"id": identifier, "status": status, "evidence": evidence, "remedy": remedy}


def qualify_history(
    scenarios: dict[str, dict[str, dict[str, Any]]],
    *,
    dividend_symbols: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Eight noncompensating gates, with recomputed local economic diagnostics.

    Caller must first verify the native Decimal ledger and file hashes. This
    function rechecks paired clocks, attribution, risk domains and trade clocks.
    Resampling is a diagnostic on the existing observations, not new trials.
    """
    if set(scenarios) != {"NOMINAL", "STRESS"}:
        raise ValueError("BOTH_COST_SCENARIOS_REQUIRED")
    metrics: dict[str, Any] = {}
    statistical: dict[str, Any] = {}
    pass_economic = pass_risk = pass_support = pass_diversification = True
    for scenario, books in scenarios.items():
        account = books["JOINT"]
        if account["stress"] is not (scenario == "STRESS"):
            raise ValueError("SCENARIO_IDENTITY")
        totals, paired = paired_growth(books)
        economic = economic_checks(
            account, STANDARD["nominal_annual_net_return"], dividend_symbols
        )
        contributions = trade_contributions(account, dividend_symbols)
        initial = number(account["initial_usd"], positive=True)
        nav = np.array([initial, *(r["equity"] for r in account["curve"])])
        daily_logs = np.diff(np.log(nav))
        daily_dd = float(np.max(1 - nav / np.maximum.accumulate(nav)))
        hourly_dd = number(account["hour_grid_drawdown"])
        if not 0 <= daily_dd <= hourly_dd + 1e-10 <= 1 + 1e-10:
            raise ValueError("DRAWDOWN_BELOW_DAILY_PATH")
        holdings = []
        for t in account["trades"]:
            entry, exit_at = stamp(t["entry_at"]), stamp(t["exit_at"])
            hours = (exit_at - entry).total_seconds() / 3600
            if not 0 <= hours <= 72 or abs(hours - number(t["holding_hours"])) > 1e-9:
                raise ValueError("FALSE_HOLDING_DURATION")
            holdings.append(hours)
        gross = number(account["max_entry_gross_fraction"])
        stop_risk = number(account["max_entry_stop_risk_fraction"])
        if gross < 0 or stop_risk < 0:
            raise ValueError("NEGATIVE_EXPOSURE")
        worst_day = float(max(0.0, -np.expm1(daily_logs).min()))
        risk = {
            "hour_grid_drawdown": hourly_dd <= STANDARD["max_drawdown"],
            "daily_loss": worst_day <= STANDARD["max_daily_loss"],
            "entry_gross": gross <= STANDARD["max_entry_gross_fraction"] + 1e-10,
            "entry_stop_risk": stop_risk
            <= STANDARD["max_entry_stop_risk_fraction"] + 1e-10,
        }
        pass_risk &= all(risk.values())
        by_book = Counter(t["book"] for t in contributions)
        by_symbol: dict[str, float] = defaultdict(float)
        for t in contributions:
            by_symbol[t["symbol"]] += t["total_net_usd"]
        positive_pnl = sum(max(0.0, p) for p in by_symbol.values())
        concentration = (
            max([0.0, *by_symbol.values()]) / positive_pnl if positive_pnl else 1.0
        )
        sufficient = (
            economic["days"] >= STANDARD["minimum_calendar_days"]
            and len(contributions) >= STANDARD["minimum_closed_campaigns"]
        )
        diversified = (
            all(
                by_book.get(book, 0) >= STANDARD["minimum_campaigns_per_book"]
                for book in ("equity", "crypto")
            )
            and concentration <= STANDARD["maximum_positive_pnl_symbol_share"]
        )
        pass_support &= sufficient
        pass_diversification &= diversified
        nominal_target = scenario != "NOMINAL" or economic["checks"]["annual_target"]
        # Preserve the same fixed bills in removal diagnostics. No reinvestment
        # or cash reassignment is invented after deleting a winning campaign/day.
        without_best_day = float(
            np.expm1(daily_logs.sum() - max(0.0, daily_logs.max()))
        )
        pass_economic &= (
            nominal_target
            and economic["checks"]["positive_after_costs"]
            and economic["checks"]["positive_without_largest_trade"]
            and without_best_day > 0
        )
        fixed = number(account["fixed_cost_usd"])
        contribution = economic["net_usd"] + fixed
        target_dollars = initial * np.expm1(
            np.log1p(STANDARD["nominal_annual_net_return"]) * economic["days"] / 365
        )
        metrics[scenario] = {
            **economic,
            "paired_log_growth": totals,
            "trade_count": len(contributions),
            "campaigns_per_book": dict(by_book),
            "contribution_by_symbol_usd": dict(sorted(by_symbol.items())),
            "largest_positive_symbol_share": concentration,
            "net_return_without_best_day": without_best_day,
            "risk_checks_on_observed_grid": risk,
            "worst_calendar_day_loss": worst_day,
            "max_holding_hours": max(holdings, default=0.0),
            "fixed_cost_usd": fixed,
            "contribution_after_variable_before_fixed_usd": contribution,
            "break_even_fixed_cost_usd_per_day_on_same_path": contribution
            / economic["days"],
            "shortfall_to_nominal_target_usd": max(
                0.0, float(target_dollars) - economic["net_usd"]
            ),
            "cost_sensitivity_is_replay": False,
        }
        if len(daily_logs) >= 4 * max(STANDARD["statistics"]["block_lengths"]):
            # Derived controls use the same funded-account paths and draw indices.
            controls = {
                "BASELINE": (daily_logs - paired[:, 1]).tolist(),
                "CRYPTO": (daily_logs - paired[:, 2]).tolist(),
                "CASH": (daily_logs - paired[:, 3]).tolist(),
            }
            statistical[scenario] = block_growth_test(
                daily_logs.tolist(), controls, STANDARD["statistics"]
            )
        else:
            statistical[scenario] = {
                "within_family_criterion_passed": False,
                "reason": "TOO_FEW_BLOCKS",
            }
    nominal_dates = [r["day"] for r in scenarios["NOMINAL"]["JOINT"]["curve"]]
    stress_dates = [r["day"] for r in scenarios["STRESS"]["JOINT"]["curve"]]
    if nominal_dates != stress_dates:
        raise ValueError("CROSS_SCENARIO_CALENDAR")
    if (
        scenarios["NOMINAL"]["JOINT"]["initial_usd"]
        != scenarios["STRESS"]["JOINT"]["initial_usd"]
    ):
        raise ValueError("CROSS_SCENARIO_CAPITAL")
    pass_statistics = all(
        v["within_family_criterion_passed"] for v in statistical.values()
    )
    rows = [
        _row(
            "G1_ECONOMIC_EDGE",
            "PASS" if pass_economic else "FAIL",
            metrics,
            "Net nominal >=10% annual, stress >0, positive after removing the largest campaign and best day. Changing these post-result does not validate this study.",
        ),
        _row(
            "G2_STATISTICAL_SUPPORT",
            "PASS" if pass_statistics and pass_support else "FAIL",
            statistical,
            "At least 365 calendar days and 100 closed campaigns per scenario, with all 16 within-family bounds >0. These floors do not guarantee statistical power.",
        ),
        _row(
            "G3_MULTI_ASSET_CONTRIBUTION",
            "PASS" if pass_diversification else "FAIL",
            {
                k: {
                    f: v[f]
                    for f in ("campaigns_per_book", "largest_positive_symbol_share")
                }
                for k, v in metrics.items()
            },
            "At least 20 campaigns per book and no symbol supplies >50% of positive symbol PnL. Book additions must also pass G2.",
        ),
        _row(
            "G4_RISK",
            "BLOCKED" if pass_risk else "FAIL",
            {"grid_checks_passed": pass_risk, "intrabar_risk_verified": False},
            "Reconcile all positions, pending orders and sector exposure against timestamped intrabar marks, including gaps, stale markets and outages. Grid compliance alone is insufficient.",
        ),
        _row(
            "G5_DATA_AND_SELECTION",
            "BLOCKED",
            {"fresh_global_holdout": False, "global_trial_history_complete": False},
            "Provide point-in-time universe including removals, corporate-action coverage, causal source receipts, 72h purged labels, frozen recipe and untouched holdout. Preserve the 119/128 inherited reservation.",
        ),
        _row(
            "G6_EXECUTION_COSTS",
            "BLOCKED",
            {"live_costs_authenticated": False},
            "Use order-costs with filled, partial, cancelled and unfilled orders, fee receipts and fixed bills. Reconcile provenance, participation and every traded class/side without mixing PAPER and LIVE.",
        ),
        _row(
            "G7_PASSIVE_CONTROL",
            "BLOCKED",
            {"risk_matched_passive_verified": False},
            "Preregister a fully funded passive control with lagged risk sizing, the same period and costs. Removing a sleeve is not a risk-matched passive comparison.",
        ),
        _row(
            "G8_PROSPECTIVE_REVIEW",
            "BLOCKED",
            {
                "minimum_forward_calendar_days": STANDARD[
                    "minimum_forward_calendar_days"
                ],
                "observed_forward_days": 0,
            },
            "Reconcile the frozen strategy prospectively for >=180 days through roadmap9 forward admission, then test net and paired stress growth and obtain independent scoped review. Historical diagnostics cannot close this gate.",
        ),
    ]
    return {
        "schema": "HARPOON_LEVEL8_HISTORICAL_REVIEW_1",
        "standard": deepcopy(STANDARD),
        "standard_canonical_sha256": digest(STANDARD),
        "decision": "REJECT"
        if any(r["status"] == "FAIL" for r in rows)
        else "BLOCKED_PENDING_OBSERVED_VALIDATION",
        "gates": rows,
        "gate_counts": dict(Counter(r["status"] for r in rows)),
        "gate_counts_are_not_profitability_scores": True,
        "review_uses_reused_history": True,
        "new_strategy_measurements": 0,
        "level8_accredited": False,
        "execution_allowed": False,
    }
