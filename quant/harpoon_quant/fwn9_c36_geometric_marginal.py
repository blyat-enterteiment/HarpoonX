"""C36: finite-scenario robust marginal geometric-growth research.

NO market data, broker orders, calibrated probabilities, optimization loop or
M10 final holdout. Conditional on **declared synthetic** scenario laws only.
A scenario is a joint portfolio outcome, never independent asset sampling.
C36 never changes frozen C22/C29 economic gates or 72-hour exit rules.

For candidate j, q=notional/equity, existing funded wealth factors B_omega:
  x_j,omega = gross_return_j,omega - all_in_cost_j,omega - cash_return_omega
  D_j(q) = min_{p: ||p-p0||_1 <= eps} sum p log[(B+q*x)/B].
The SAME adverse distribution is used in both arms of the paired increment.
This is a conditional model score, NOT a population confidence interval.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, fsum, isfinite, log, log1p
from typing import Sequence

ORIGINAL_CAPITAL_USD = 20_000.0
ORIGINAL_GROSS_ADMISSION_FRACTION = 0.12
ORIGINAL_ENTRY_RISK_FRACTION = 0.0025
MAX_HOLD_HOURS = 72
MAX_SCENARIOS = 512
MAX_CANDIDATES = 96


def _number(value: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError(f"{label}: REAL_REQUIRED")
    result = float(value)
    if not isfinite(result):
        raise ValueError(f"{label}: NONFINITE")
    return result


def _vector(values: Sequence[float], label: str) -> tuple[float, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{label}: VECTOR_REQUIRED")
    try:
        data = tuple(_number(v, label) for v in values)
    except TypeError as exc:
        raise ValueError(f"{label}: VECTOR_REQUIRED") from exc
    if not data or len(data) > MAX_SCENARIOS:
        raise ValueError(f"{label}: SCENARIO_COUNT")
    return data


@dataclass(frozen=True)
class ScenarioBook:
    base_wealth_factors: tuple[float, ...]
    probabilities: tuple[float, ...]
    tv_radius: float
    horizon_days: float
    origin: str = "SYNTHETIC_EXPLICIT"

    def __post_init__(self) -> None:
        base = _vector(self.base_wealth_factors, "BASE_WEALTH")
        probs = _vector(self.probabilities, "PROBABILITIES")
        if len(base) != len(probs) or any(x <= 0 for x in base):
            raise ValueError("BASE_WEALTH_POSITIVE_AND_MATCHED")
        if any(p < 0 for p in probs) or abs(fsum(probs) - 1) > 1e-12:
            raise ValueError("PROBABILITY_SIMPLEX")
        eps = _number(self.tv_radius, "TV_RADIUS")
        days = _number(self.horizon_days, "HORIZON_DAYS")
        if not 0 <= eps <= 2 or not 0 < days <= 3:
            raise ValueError("TV_AND_72H_HORIZON")
        if self.origin != "SYNTHETIC_EXPLICIT":
            raise ValueError("C36_ONLY_EXPLICIT_SYNTHETIC_ENGINEERING_LAWS")
        object.__setattr__(self, "base_wealth_factors", base)
        object.__setattr__(self, "probabilities", probs)


@dataclass(frozen=True)
class Candidate:
    asset: str
    strategy: str
    book: str
    gross_returns: tuple[float, ...]
    all_in_costs: tuple[float, ...]
    cash_returns: tuple[float, ...]
    declared_stress_loss: float
    holding_hours: float

    def __post_init__(self) -> None:
        if not self.asset or not self.strategy or self.book not in (
            "equity", "etf", "crypto", "options"
        ):
            raise ValueError("REGISTERED_ASSET_STRATEGY_AND_BOOK_REQUIRED")
        returns = _vector(self.gross_returns, "GROSS_RETURNS")
        costs = _vector(self.all_in_costs, "ALL_IN_COSTS")
        cash = _vector(self.cash_returns, "CASH_RETURNS")
        if len({len(returns), len(costs), len(cash)}) != 1:
            raise ValueError("JOINT_SCENARIO_LENGTH_MISMATCH")
        if any(x < -1 for x in returns) or any(x < 0 for x in costs):
            raise ValueError("LONG_ONLY_PAYOFF_OR_NEGATIVE_COST")
        if any(x <= -1 for x in cash):
            raise ValueError("INVALID_CASH_WEALTH_FACTOR")
        stress = _number(self.declared_stress_loss, "DECLARED_STRESS_LOSS")
        hold = _number(self.holding_hours, "HOLD_HOURS")
        observed_worst = max(0.0, max(c - r for r, c in zip(returns, costs)))
        if stress <= 0 or stress + 1e-12 < observed_worst:
            raise ValueError("STRESS_LOSS_UNDERSTATES_DECLARED_SCENARIOS")
        if not 0 < hold <= MAX_HOLD_HOURS:
            raise ValueError("ORIGINAL_HOLD_72H")
        object.__setattr__(self, "gross_returns", returns)
        object.__setattr__(self, "all_in_costs", costs)
        object.__setattr__(self, "cash_returns", cash)

    def excess(self) -> tuple[float, ...]:
        return tuple(r - cost - cash for r, cost, cash
                     in zip(self.gross_returns, self.all_in_costs,
                            self.cash_returns))


@dataclass(frozen=True)
class FundedHeadroom:
    equity_usd: float
    settled_free_cash_usd: float
    new_gross_admission_headroom_usd: float
    aggregate_uncommitted_risk_usd: float
    hard_capital_usd: float = ORIGINAL_CAPITAL_USD

    def __post_init__(self) -> None:
        values = (self.equity_usd, self.settled_free_cash_usd,
                  self.new_gross_admission_headroom_usd,
                  self.aggregate_uncommitted_risk_usd,
                  self.hard_capital_usd)
        if not all(_number(x, "FUNDED_HEADROOM") >= 0 for x in values):
            raise ValueError("NEGATIVE_FUNDED_HEADROOM")
        if self.equity_usd <= 0 or self.hard_capital_usd != ORIGINAL_CAPITAL_USD:
            raise ValueError("FROZEN_HARDCAP_AND_POSITIVE_EQUITY")

    def q_ceiling(self, candidate: Candidate) -> float:
        """Single NEW admission; never a forced continuous 12% liquidation."""
        effective = min(self.equity_usd, self.hard_capital_usd)
        risk_usd = min(
            ORIGINAL_ENTRY_RISK_FRACTION * effective,
            self.aggregate_uncommitted_risk_usd,
        )
        notional = min(
            ORIGINAL_GROSS_ADMISSION_FRACTION * effective,
            self.new_gross_admission_headroom_usd,
            self.settled_free_cash_usd,
            risk_usd / candidate.declared_stress_loss,
        )
        return max(0.0, notional / self.equity_usd)


def tv_worst_expectation(
    values: Sequence[float], probabilities: Sequence[float], radius: float
) -> float:
    """Exact finite-support L1-ball min by moving mass high -> low.

    This is an optimization over fixed scenario probabilities. The L1
    radius is supplied externally, NOT statistically calibrated by C36.
    """
    u = _vector(values, "UTILITY")
    p = list(_vector(probabilities, "PROBABILITIES"))
    eps = _number(radius, "TV_RADIUS")
    if len(u) != len(p) or any(z < 0 for z in p):
        raise ValueError("UTILITY_PROBABILITY_DOMAIN")
    if abs(fsum(p) - 1) > 1e-12 or not 0 <= eps <= 2:
        raise ValueError("UTILITY_PROBABILITY_SIMPLEX_AND_RADIUS")
    budget = eps / 2
    donors = sorted(range(len(u)), key=lambda i: (-u[i], i))
    receivers = sorted(range(len(u)), key=lambda i: (u[i], i))
    d = r = 0
    while budget > 1e-15 and d < len(u) and r < len(u):
        high, low = donors[d], receivers[r]
        if u[high] <= u[low] + 1e-16:
            break
        available = p[high]
        capacity = 1 - p[low]
        moved = min(budget, available, capacity)
        if moved > 0:
            p[high] -= moved
            p[low] += moved
            budget -= moved
        if p[high] <= 1e-15:
            d += 1
        if 1 - p[low] <= 1e-15:
            r += 1
        if moved <= 1e-15 and p[high] > 1e-15 and 1-p[low] > 1e-15:
            break
    return fsum(x * y for x, y in zip(p, u))


def _log_increment(book: ScenarioBook, excess: tuple[float, ...],
                   q: float) -> tuple[float, ...] | None:
    outputs = []
    for base, x in zip(book.base_wealth_factors, excess):
        z = q * x / base
        if z <= -1:
            return None
        outputs.append(log1p(z))
    return tuple(outputs)


def robust_marginal(book: ScenarioBook, candidate: Candidate, q: float) -> float:
    if len(candidate.gross_returns) != len(book.probabilities):
        raise ValueError("JOINT_ASSET_PORTFOLIO_SCENARIOS_REQUIRED")
    if not 0 <= _number(q, "FRACTION") <= 1:
        raise ValueError("CASH_FUNDED_FRACTION_DOMAIN")
    scores = _log_increment(book, candidate.excess(), q)
    if scores is None:
        return float("-inf")
    return tv_worst_expectation(scores, book.probabilities, book.tv_radius)


def quadratic_certified_lower(
    book: ScenarioBook, candidate: Candidate, q: float, q_ceiling: float
) -> float:
    """Pointwise Taylor lower bound, valid on DECLARED finite scenarios only.

    For |z| <= b < 1: log(1+z) >= z - z*z/[2(1-b)^2].
    An L1-ball worst-case expectation of this minorant cannot exceed the
    exact L1-ball worst-case expected log increment.
    """
    if not 0 <= q <= q_ceiling:
        raise ValueError("LOWER_BOUND_FRACTION_OUTSIDE_ADMISSION_CAP")
    x = candidate.excess()
    if len(x) != len(book.probabilities):
        raise ValueError("LOWER_BOUND_JOINT_SCENARIOS_REQUIRED")
    bound = max(abs(q_ceiling * y / b)
                for b, y in zip(book.base_wealth_factors, x))
    if bound >= 1:
        raise ValueError("TAYLOR_GLOBAL_SCENARIO_CURVATURE_UNBOUNDED")
    vals = []
    for base, y in zip(book.base_wealth_factors, x):
        z = q * y / base
        vals.append(z - z*z/(2*(1-bound)**2))
    return tv_worst_expectation(vals, book.probabilities, book.tv_radius)


def score(book: ScenarioBook, candidate: Candidate,
          headroom: FundedHeadroom) -> dict[str, object]:
    if len(candidate.gross_returns) != len(book.probabilities):
        raise ValueError("JOINT_SCENARIO_VECTOR_REQUIRED")
    limit = headroom.q_ceiling(candidate)
    excess = candidate.excess()
    if limit > 0:
        # A declared scenario may not run out of financed wealth.
        for base, x in zip(book.base_wealth_factors, excess):
            if x < 0:
                limit = min(limit, (base * (1-1e-10)) / -x)
    best = 0.0
    qbest = 0.0
    if limit > 0:
        # The minimum of concave objectives remains concave in q.
        # Golden section handles scenario switches without derivatives.
        left, right = 0.0, limit
        phi = (5**0.5-1)/2
        c, d = right-phi*(right-left), left+phi*(right-left)
        fc, fd = robust_marginal(book,candidate,c), robust_marginal(book,candidate,d)
        for _ in range(85):
            if fc >= fd:
                right, d, fd = d, c, fc
                c = right-phi*(right-left)
                fc = robust_marginal(book,candidate,c)
            else:
                left, c, fc = c, d, fd
                d = left+phi*(right-left)
                fd = robust_marginal(book,candidate,d)
        for q in (0.0, limit, c, d, (left+right)/2):
            value = robust_marginal(book,candidate,q)
            if value > best+1e-13:
                best, qbest = value, q
    selected = qbest > 0 and best > 1e-12
    qbest = qbest if selected else 0.0
    best = best if selected else 0.0
    return {
        "asset": candidate.asset,
        "strategy": candidate.strategy,
        "book": candidate.book,
        "decision": "RESEARCH_ONLY_NONEXECUTABLE" if selected else "CASH",
        "fraction_of_one_funded_book": qbest,
        "notional_usd": qbest*headroom.equity_usd,
        "stress_loss_budget_usd": (
            qbest*headroom.equity_usd*candidate.declared_stress_loss
        ),
        "robust_conditional_delta_log": best,
        "robust_conditional_delta_bps_per_day": 1e4*best/book.horizon_days,
        "max_frozen_new_admission_fraction": headroom.q_ceiling(candidate),
        "synthetic_law_only": True,
        "tv_radius_statistically_calibrated": False,
        "options_executable": False,
        "orders_allowed": False,
        "real_OOS_profit_proved": False,
        "N9S": "NO_GO",
    }


def rank_one_admission(book: ScenarioBook, candidates: Sequence[Candidate],
                       headroom: FundedHeadroom,
                       blocked_assets: frozenset[str] = frozenset()
                       ) -> dict[str, object]:
    """One new opportunity only; next decision requires fresh funded state.

    No independently opened positions, double allocation to one asset,
    account reset, broker side effects or greedy loop over fictitious fills.
    """
    if len(candidates) > MAX_CANDIDATES:
        raise ValueError("CANDIDATE_BUDGET")
    ids = [(c.asset, c.strategy) for c in candidates]
    if len(ids) != len(set(ids)):
        raise ValueError("DUPLICATE_ASSET_STRATEGY")
    if not isinstance(blocked_assets, frozenset):
        raise ValueError("EXISTING_FUNDED_ASSET_SET_REQUIRED")
    ranked = [score(book, c, headroom) for c in candidates
              if c.asset not in blocked_assets]
    ranked.sort(key=lambda r: (
        -float(r["robust_conditional_delta_log"]),
        str(r["asset"]), str(r["strategy"])
    ))
    best = ranked[0] if ranked and ranked[0]["decision"] != "CASH" else None
    return {
        "schema": "HARPOON_C36_SYNTHETIC_MARGINAL_ONE_BOOK_RANKING_1",
        "best": best,
        "candidate_diagnostics": ranked,
        "cash_fallback": best is None,
        "single_new_admission_only": True,
        "account_equity_usd": headroom.equity_usd,
        "no_separate_asset_capital_accounts": True,
        "no_order_authority": True,
        "M10_final_accounts_sealed": 3200,
        "N9S": "NO_GO",
    }


def compound_verified_arithmetic(
    starting_wealth_usd: float, intervals: Sequence[tuple[float, float]]
) -> dict[str, float | str | bool]:
    """Numerical telescoping ONLY; inputs are not authenticated NAV receipts.

    Each interval is (positive already-funded wealth factor, duration days).
    Durations are not treated as repeated independent bars.
    """
    start = _number(starting_wealth_usd, "STARTING_WEALTH")
    if start <= 0 or not intervals:
        raise ValueError("FUNDED_CAPITAL_AND_INTERVALS")
    factors, days = [], []
    for factor, duration in intervals:
        x, d = _number(factor, "FUNDED_FACTOR"), _number(duration, "DAYS")
        if x <= 0 or d <= 0:
            raise ValueError("POSITIVE_WEALTH_AND_TIME")
        factors.append(x)
        days.append(d)
    total_log = fsum(log(x) for x in factors)
    terminal = start*exp(total_log)
    return {
        "origin": "INPUT_FACTORS_UNAUTHENTICATED_ARITHMETIC_ONLY",
        "starting_wealth_usd": start,
        "terminal_wealth_usd": terminal,
        "total_log_growth": total_log,
        "log_growth_bps_per_calendar_day": 1e4*total_log/fsum(days),
        "compounded_simple_return": exp(total_log)-1,
        "same_account_continuity_verified_by_broker": False,
        "N9S": "NO_GO",
    }
