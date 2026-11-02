"""Cash-flow aware portfolio statistics with explicit units and undefined ratios."""

from __future__ import annotations

import math
from datetime import timedelta
from itertools import pairwise
from typing import Any

import numpy as np
from scipy.special import ndtr, ndtri

from .core import digest, expected_shortfall, finite, timestamp


def ratio(numerator: float, denominator: float) -> float | None:
    return float(numerator / denominator) if denominator > 1e-14 else None


def hac_variance(values: np.ndarray, lags: int = 5) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    z = values - values.mean()
    variance = float(np.dot(z, z) / n)
    k = min(lags, n - 1)
    for lag in range(1, k + 1):
        variance += 2 * (1 - lag / (k + 1)) * float(np.dot(z[lag:], z[:-lag]) / n)
    return max(0.0, variance)


def probability_sharpe(values: np.ndarray, threshold: float = 0.0) -> dict[str, Any]:
    n = len(values)
    sd = float(np.std(values, ddof=0)) if n else 0.0
    if n < 30 or sd <= 1e-14:
        return {
            "value": None,
            "status": "INSUFFICIENT_OR_DEGENERATE",
            "scope": "IID moment approximation; not probability of profit",
        }
    mu = float(values.mean())
    sr = mu / sd
    z = (values - mu) / sd
    skew, kurt = float(np.mean(z**3)), float(np.mean(z**4))
    denominator = 1 - skew * sr + (kurt - 1) * sr * sr / 4
    if denominator <= 0:
        return {"value": None, "status": "INVALID_MOMENTS"}
    return {
        "value": float(
            ndtr((sr - threshold) * math.sqrt(n - 1) / math.sqrt(denominator))
        ),
        "threshold_per_period": threshold,
        "status": "APPROXIMATION",
        "scope": "IID moment approximation; not probability of profit",
    }


def deflated_sharpe(
    values: np.ndarray, trial_sharpes: list[float] | None, declared_trials: int
) -> dict[str, Any]:
    if (
        trial_sharpes is None
        or len(trial_sharpes) != declared_trials
        or declared_trials < 2
    ):
        return {"value": None, "status": "COMPLETE_TRIAL_POPULATION_REQUIRED"}
    sr = np.asarray(trial_sharpes, dtype=float)
    if not np.isfinite(sr).all() or not 2 <= declared_trials <= 100000:
        raise ValueError("DSR_TRIALS_DOMAIN")
    sigma = float(np.std(sr, ddof=1))
    gamma = 0.5772156649015329
    threshold = sigma * (
        (1 - gamma) * ndtri(1 - 1 / declared_trials)
        + gamma * ndtri(1 - 1 / (declared_trials * math.e))
    )
    return {
        **probability_sharpe(values, float(threshold)),
        "declared_trials": declared_trials,
        "scope": "DSR diagnostic with zero null mean and full supplied trial dispersion; IID/non-normal moment approximation. Correlated/adaptive search and serial dependence limit interpretation.",
    }


def from_equity(rows: list[dict[str, Any]]) -> tuple[list[str], list[float], float]:
    if len(rows) < 2:
        raise ValueError("TWO_EQUITY_SNAPSHOTS_REQUIRED")
    previous = finite(rows[0]["equity"], "INITIAL_EQUITY", True)
    initial = previous
    times = []
    returns = []
    last = timestamp(rows[0]["at"])
    for row in rows[1:]:
        at = timestamp(row["at"])
        if at <= last:
            raise ValueError("STRICT_EQUITY_TIMES")
        before = finite(row.get("external_flow_before", 0), "FLOW_BEFORE")
        after = finite(row.get("external_flow_after", 0), "FLOW_AFTER")
        denominator = previous + before
        end = finite(row["equity"], "EQUITY")
        if denominator <= 0 or end < 0 or end - after < 0:
            raise ValueError("EQUITY_FLOW_DOMAIN")
        returns.append((end - after) / denominator - 1)
        times.append(row["at"])
        previous = end
        last = at
    return times, returns, initial


def report(data: dict[str, Any], *, schema_version: int = 2) -> dict[str, Any]:
    if schema_version not in (1, 2):
        raise ValueError("PERFORMANCE_SCHEMA_VERSION")
    if schema_version == 1 and (
        data.get("sampling") != "DAILY_UTC_CALENDAR"
        or data.get("periods_per_year") != 365
        or "initial_at" in data or "cost_reporting" in data
        or not isinstance(data.get("trades"), list)
        or any(t.get("cost_usd") is None for t in data["trades"])
    ):
        raise ValueError("LEGACY_METRICS_REQUIRE_COMPLETE_DAILY_TRADE_INPUTS")
    if data.get("origin") not in ("OBSERVED", "SYNTHETIC_ENGINEERING_ONLY"):
        raise ValueError("PERFORMANCE_ORIGIN_REQUIRED")
    if data.get("return_basis") != "NET_FLOW_ADJUSTED":
        raise ValueError("NET_FLOW_ADJUSTED_RETURNS_REQUIRED")
    if "equity" in data:
        times, rs, initial = from_equity(data["equity"])
    else:
        times, rs = data["times"], data["returns"]
        initial = finite(data.get("initial_equity", 1), "INITIAL_EQUITY", True)
    if len(times) != len(rs) or not 2 <= len(rs) <= 200000:
        raise ValueError("PERFORMANCE_SAMPLE_DOMAIN")
    ts = [timestamp(t) for t in times]
    if any(a >= b for a, b in pairwise(ts)):
        raise ValueError("STRICT_RETURN_TIMES")
    r = np.asarray(rs, dtype=float)
    if not np.isfinite(r).all() or (r < -1).any():
        raise ValueError("RETURN_DOMAIN")
    zeros = np.flatnonzero(r == -1)
    if len(zeros) and np.any(r[zeros[0] + 1 :] != 0):
        raise ValueError("NONZERO_RETURNS_AFTER_RUIN")
    periods = finite(data["periods_per_year"], "PERIODS_PER_YEAR", True)
    if periods > 525600:
        raise ValueError("FREQUENCY_BOUND")
    sampling = data.get("sampling", "EXPLICIT_PERIODS")
    if sampling == "DAILY_UTC_CALENDAR" and (
        periods != 365 or any((b - a).total_seconds() != 86400 for a, b in pairwise(ts))
    ):
        raise ValueError("IRREGULAR_DAILY_CALENDAR")
    rf = finite(data.get("risk_free_annual", 0), "RISK_FREE")
    mar = finite(data.get("target_annual", 0), "MAR")
    if min(rf, mar) <= -1:
        raise ValueError("RATE_DOMAIN")
    rf_period = math.expm1(math.log1p(rf) / periods)
    target = math.expm1(math.log1p(mar) / periods)
    excess = r - rf_period
    shortfall = np.minimum(r - target, 0)
    downside = float(np.sqrt(np.mean(shortfall**2)))
    sd = float(np.std(excess, ddof=1))
    hac = math.sqrt(hac_variance(excess))
    nav = np.cumprod(1 + r)
    if not np.isfinite(nav).all():
        raise ValueError("COMPOUNDING_OVERFLOW")
    levels = np.r_[1.0, nav]
    peaks = np.maximum.accumulate(levels)
    dd = 1 - levels / peaks
    trough = int(np.argmax(dd))
    peak = int(np.argmax(levels[: trough + 1]))
    recovered = next(
        (i for i in range(trough + 1, len(levels)) if levels[i] >= levels[peak]), None
    )
    duration = 0
    longest = 0
    for v in dd[1:]:
        duration = duration + 1 if v > 1e-12 else 0
        longest = max(longest, duration)
    mu = float(np.mean(r))
    total = float(nav[-1] - 1)
    sortino = ratio(float(np.mean(r - target)), downside)
    sharpe = ratio(float(np.mean(excess)), sd)
    hac_sharpe = ratio(float(np.mean(excess)), hac)
    span = (ts[-1] - ts[0]).total_seconds() / 86400
    annual_eligible = (
        len(r) >= 60
        and span >= 90
        and sampling in ("DAILY_UTC_CALENDAR", "EXPLICIT_PERIODS")
    )
    annual_growth = (
        math.expm1(float(np.mean(np.log1p(r))) * periods)
        if annual_eligible and not len(zeros)
        else None
    )
    losses = -r
    var = float(np.quantile(losses, 0.95))
    es = expected_shortfall(losses, 0.95)
    benchmark = data.get("benchmark_returns")
    benchmark_report: dict[str, Any] = {
        "status": "NOT_SUPPLIED",
        "beta": None,
        "alpha_per_period": None,
        "information_ratio": None,
        "tracking_error": None,
    }
    if benchmark is not None:
        b = np.asarray(benchmark, dtype=float)
        if b.shape != r.shape or not np.isfinite(b).all() or (b < -1).any():
            raise ValueError("BENCHMARK_ALIGNMENT")
        active = r - b
        bvar = float(np.var(b, ddof=1))
        beta = float(np.cov(r, b, ddof=1)[0, 1] / bvar) if bvar > 1e-20 else None
        tracking = float(np.std(active, ddof=1))
        benchmark_report = {
            "status": "ALIGNED",
            "beta": beta,
            "alpha_per_period": float(np.mean(excess) - beta * np.mean(b - rf_period))
            if beta is not None
            else None,
            "information_ratio": ratio(float(active.mean()), tracking),
            "tracking_error": tracking,
        }
    supplied_trades = "trades" in data
    trades = data.get("trades", [])
    pnl = np.asarray([finite(t["net_pnl_usd"], "TRADE_NET_PNL") for t in trades])
    gains = float(np.maximum(pnl, 0).sum())
    costs_complete = supplied_trades and all(t.get("cost_usd") is not None for t in trades)
    costs = [finite(t["cost_usd"], "COST") for t in trades if t.get("cost_usd") is not None]
    if any(c < 0 for c in costs):
        raise ValueError("NEGATIVE_TRADING_COST")
    downside_count = int(np.sum(r < target))
    source_initial = timestamp(data["equity"][0]["at"]) if "equity" in data else None
    declared_initial = timestamp(data["initial_at"]) if data.get("initial_at") is not None else None
    if source_initial is not None and declared_initial is not None and source_initial != declared_initial:
        raise ValueError("INITIAL_TIME_CONFLICT")
    initial_time = declared_initial or source_initial
    if initial_time is None and sampling == "FIXED_INTERVAL_OBSERVATIONS":
        raise ValueError("INITIAL_TIME_REQUIRED")
    initial_time_basis = "OBSERVED_INPUT" if initial_time is not None else "LEGACY_DECLARED_PERIOD_CONVENTION"
    if initial_time is None:
        initial_time = ts[0] - timedelta(days=365 / periods)
    if initial_time >= ts[0]:
        raise ValueError("INVALID_INITIAL_TIME")
    timeline = [initial_time, *ts]
    cost_reporting = data.get("cost_reporting")
    if cost_reporting is not None:
        if not isinstance(cost_reporting, dict) or not isinstance(cost_reporting.get("scope"), str) or not cost_reporting["scope"]:
            raise ValueError("COST_REPORTING_SCOPE_REQUIRED")
        cost_reporting = dict(cost_reporting)
        for name in ("total_costs_usd", "reported_broker_costs_usd", "declared_external_costs_usd"):
            value = cost_reporting.get(name)
            cost_reporting[name] = None if value is None else finite(value, name.upper())
        net_costs = cost_reporting["total_costs_usd"]
    else:
        net_costs = sum(costs) if costs_complete else None
        cost_reporting = {"total_costs_usd": None,
                          "supplied_trade_costs_usd": net_costs,
                          "scope": "SUPPLIED_TRADE_COSTS_ONLY_NOT_UNDECLARED_ACCOUNT_OR_EXTERNAL_COSTS"}
    actual_pnl = None
    if "equity" in data:
        actual_pnl = (
            finite(data["equity"][-1]["equity"], "EQUITY")
            - initial
            - sum(
                finite(row.get("external_flow_before", 0), "FLOW")
                + finite(row.get("external_flow_after", 0), "FLOW")
                for row in data["equity"][1:]
            )
        )
    result = {
        "cashflow_adjusted_actual_net_pnl_usd": actual_pnl,
        "schema": "HARPOON_PERFORMANCE_" + str(schema_version),
        "origin": data["origin"],
        "return_basis": data["return_basis"],
        "n_periods": len(r),
        "first_period_end": times[0],
        "initial_at": initial_time.isoformat(),
        "initial_at_basis": initial_time_basis,
        "last_period_end": times[-1],
        "periods_per_year": periods,
        "sampling": sampling,
        "span_days_between_period_ends": span,
        "annualization_eligible": annual_eligible,
        "total_return": total,
        "net_profit_usd_on_adjusted_initial_capital": total * initial,
        "geometric_mean_per_period": float(np.expm1(np.mean(np.log1p(r))))
        if not len(zeros)
        else -1.0,
        "mean_return_per_period": mu,
        "volatility_per_period": sd,
        "downside_deviation_per_period": downside,
        "below_target_periods": downside_count,
        "sharpe_per_period": sharpe,
        "sharpe_hac_per_period": hac_sharpe,
        "sortino_per_period": sortino,
        "sharpe_annualized": sharpe * math.sqrt(periods)
        if annual_eligible and sharpe is not None
        else None,
        "sharpe_hac_annualized": hac_sharpe * math.sqrt(periods)
        if annual_eligible and hac_sharpe is not None
        else None,
        "sortino_annualized": sortino * math.sqrt(periods)
        if annual_eligible and sortino is not None
        else None,
        "cagr_annualized_from_declared_periods": annual_growth,
        "max_drawdown": float(dd.max()),
        "current_drawdown": float(dd[-1]),
        "max_drawdown_duration_periods": longest,
        "peak_at": timeline[peak].isoformat(),
        "trough_at": timeline[trough].isoformat(),
        "recovered_at": timeline[recovered].isoformat()
        if recovered is not None
        else None,
        "recovery_periods": recovered - peak if recovered is not None else None,
        "ulcer_index": float(np.sqrt(np.mean(dd[1:] ** 2))),
        "calmar": ratio(annual_growth, float(dd.max()))
        if annual_growth is not None
        else None,
        "max_drawdown_usd_on_adjusted_capital": float(np.max(peaks - levels) * initial),
        "recovery_factor": ratio(total, float(np.max(peaks - levels))),
        "historical_var95_fraction": var,
        "historical_cvar95_fraction": es,
        "omega": ratio(
            float(np.maximum(r - target, 0).sum()),
            float(-np.minimum(r - target, 0).sum()),
        ),
        "profit_factor": ratio(gains, float(-np.minimum(pnl, 0).sum())),
        "win_rate": float(np.mean(pnl > 0)) if len(pnl) else None,
        "trade_expectancy_usd": float(pnl.mean()) if len(pnl) else None,
        "trade_count": len(pnl) if supplied_trades else None,
        "net_costs_usd": net_costs,
        "cost_reporting": cost_reporting,
        "benchmark": benchmark_report,
        "psr_diagnostic": probability_sharpe(excess),
        "dsr_diagnostic": deflated_sharpe(
            excess, data.get("trial_sharpes"), data.get("declared_trials", 1)
        ),
        "undefined_note": "Zero denominators or insufficient observations return null, never infinity. Portfolio mark-to-market series, not averaging trade percentage returns.",
        "data_hash": digest(data),
        "trade_authorization": False,
    }
    if schema_version == 1:
        # Exact serialization contract of sealed daily historical experiments.
        # Do not rewrite old receipts or relax their strict field comparison.
        for field in ("initial_at", "initial_at_basis", "cost_reporting"):
            del result[field]
    return result
