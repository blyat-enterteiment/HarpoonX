"""C36 HarpoonX read-only per-asset/per-strategy incubation matrix.

This is a candidate *filter*, not a signal engine, broker gateway, backtest
evidence source, optimizer approval or license to send orders. The forecasts
and scenarios are inputs, not fitted here. A positive score is never N9 GO.
Original frozen funded cap: min(observed equity, USD 20,000); 12% gross and
0.25% risk apply at admission, not as a continuous liquidation instruction.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isfinite, log1p, sqrt
from statistics import fmean, pstdev
from typing import Literal

Book = Literal["equity", "etf", "crypto", "options"]
Family = Literal["breakout", "momentum", "reversal", "options_shadow"]
RESEARCH_SCHEMA = "HARPOON_FWN9_C36_LOCAL_MULTILAYER_INCUBATOR_1"


@dataclass(frozen=True)
class MarketFeatures:
    relative_volume: float
    volatility_momentum: float
    momentum_bps: float
    breakout_strength: float
    reversal_strength: float
    liquidity_usd: float
    quote_age_ms: int


@dataclass(frozen=True)
class RoundTripCosts:
    """All-in estimates as *bounds*, in bps of the position notional."""

    fee_entry_bps: float
    fee_exit_bps: float
    half_spread_entry_bps: float
    half_spread_exit_bps: float
    impact_entry_bps: float
    impact_exit_bps: float
    slippage_entry_bps: float
    slippage_exit_bps: float

    def total_bps(self) -> float:
        parts = (
            self.fee_entry_bps,
            self.fee_exit_bps,
            self.half_spread_entry_bps,
            self.half_spread_exit_bps,
            self.impact_entry_bps,
            self.impact_exit_bps,
            self.slippage_entry_bps,
            self.slippage_exit_bps,
        )
        if not all(isfinite(x) and x >= 0 for x in parts):
            raise ValueError("C36_INVALID_OR_MISSING_COST_BOUND")
        return sum(parts)


@dataclass(frozen=True)
class Forecast:
    """Forward model outputs, NOT observed prospective performance.

    Scenario IDs must be aligned across different assets to retain dependence.
    scenario_returns_bps are *pre-cost*, on the candidate's holding horizon.
    n_effective must be justified upstream; this function never estimates it.
    """

    expected_gross_bps: float
    standard_error_bps: float
    n_effective: int
    scenario_ids: tuple[str, ...]
    scenario_returns_bps: tuple[float, ...]
    known_at_ms: int
    provenance: Literal["SYNTHETIC_RESEARCH", "OBSERVED_UNATTESTED"]


@dataclass(frozen=True)
class Opportunity:
    symbol: str
    native_strategy_id: str
    book: Book
    family: Family
    factor_bucket: str
    decision_at_ms: int
    quote_known_at_ms: int
    horizon_hours: int
    native_prefilter_observed: bool
    features: MarketFeatures
    costs: RoundTripCosts
    forecast: Forecast
    stop_loss_upper_bps: float


@dataclass(frozen=True)
class FundedBook:
    equity_usd: float
    settled_cash_usd: float
    committed_cash_usd: float
    unsettled_cash_usd: float
    outstanding_gross_usd: float
    outstanding_risk_usd: float
    reconciled: bool
    receipts_complete: bool
    risk_halt: bool
    held_symbols: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResearchPolicy:
    max_quote_age_ms: int = 60_000
    max_horizon_hours: int = 72
    max_admission_gross_fraction: float = 0.12
    max_admission_risk_fraction: float = 0.0025
    hard_capital_usd: float = 20_000.0
    hurdle_bps_per_day: float = 1.0
    confidence_multiplier: float = 2.5
    tail_risk_penalty: float = 0.25
    min_relative_volume: float = 1.5
    min_liquidity_usd: float = 100_000.0
    max_full_spread_bps: float = 40.0
    no_trade_buffer_portfolio_bps: float = 0.25
    max_per_factor_bucket: int = 1


def _positive_finite(value: float) -> bool:
    return isfinite(value) and value >= 0


def _validate_funding(book: FundedBook, policy: ResearchPolicy) -> float:
    values = (
        book.equity_usd,
        book.settled_cash_usd,
        book.committed_cash_usd,
        book.unsettled_cash_usd,
        book.outstanding_gross_usd,
        book.outstanding_risk_usd,
    )
    if not all(_positive_finite(v) for v in values) or book.equity_usd <= 0:
        raise ValueError("C36_INVALID_FUNDED_BOOK")
    if (
        policy.hard_capital_usd != 20_000.0
        or policy.max_admission_gross_fraction != 0.12
        or policy.max_admission_risk_fraction != 0.0025
        or policy.max_horizon_hours != 72
        or policy.hurdle_bps_per_day != 1.0
    ):
        raise ValueError("C36_FROZEN_FINANCIAL_CONTRACT_CHANGED")
    if (
        policy.confidence_multiplier < 0
        or not isfinite(policy.confidence_multiplier)
        or policy.tail_risk_penalty < 0
        or not isfinite(policy.tail_risk_penalty)
        or policy.max_per_factor_bucket < 1
        or policy.max_quote_age_ms < 0
        or policy.min_relative_volume < 0
        or policy.min_liquidity_usd < 0
        or policy.max_full_spread_bps < 0
        or policy.no_trade_buffer_portfolio_bps < 0
    ):
        raise ValueError("C36_INVALID_RESEARCH_FILTER")
    if len(set(book.held_symbols)) != len(book.held_symbols):
        raise ValueError("C36_DUPLICATE_EXISTING_INVENTORY")
    return min(book.equity_usd, policy.hard_capital_usd)


def _validate_evidence(o: Opportunity, policy: ResearchPolicy) -> None:
    if (
        not o.symbol
        or not o.native_strategy_id
        or not o.factor_bucket
        or o.book not in ("equity", "etf", "crypto", "options")
        or o.family not in ("breakout", "momentum", "reversal", "options_shadow")
        or o.horizon_hours < 1
        or o.horizon_hours > policy.max_horizon_hours
        or not isinstance(o.decision_at_ms, int)
        or o.decision_at_ms <= 0
    ):
        raise ValueError("C36_INVALID_ASSET_STRATEGY_IDENTITY")
    f, x = o.features, o.forecast
    if (
        not isinstance(o.quote_known_at_ms, int)
        or not isinstance(x.known_at_ms, int)
        or o.quote_known_at_ms > o.decision_at_ms
        or x.known_at_ms > o.decision_at_ms
        or o.quote_known_at_ms <= 0
        or x.known_at_ms <= 0
        or not isinstance(f.quote_age_ms, int)
        or f.quote_age_ms < 0
    ):
        raise ValueError("C36_FUTURE_INFORMATION_OR_CLOCK")
    features = (
        f.relative_volume,
        f.volatility_momentum,
        f.momentum_bps,
        f.breakout_strength,
        f.reversal_strength,
        f.liquidity_usd,
        x.expected_gross_bps,
        x.standard_error_bps,
        o.stop_loss_upper_bps,
    )
    if not all(isfinite(v) for v in features):
        raise ValueError("C36_NONFINITE_EVIDENCE")
    if (
        x.standard_error_bps < 0
        or o.stop_loss_upper_bps <= 0
        or f.relative_volume < 0
        or f.liquidity_usd < 0
    ):
        raise ValueError("C36_INVALID_LOSS_OR_FEATURE")
    if (
        len(x.scenario_ids) < 8
        or len(x.scenario_ids) != len(x.scenario_returns_bps)
        or len(set(x.scenario_ids)) != len(x.scenario_ids)
        or not all(isinstance(s, str) and s for s in x.scenario_ids)
        or not all(isfinite(r) for r in x.scenario_returns_bps)
        or not isinstance(x.n_effective, int)
        or not (1 <= x.n_effective <= len(x.scenario_ids))
        or x.provenance not in ("SYNTHETIC_RESEARCH", "OBSERVED_UNATTESTED")
    ):
        raise ValueError("C36_MISSING_OR_MISALIGNED_SCENARIOS")
    o.costs.total_bps()


def _feature_gate(o: Opportunity, policy: ResearchPolicy) -> str | None:
    f = o.features
    if not o.native_prefilter_observed:
        return "NO_ORIGINAL_NATIVE_PREFILTER_WITNESS"
    if o.book == "options" or o.family == "options_shadow":
        return "OPTIONS_EXECUTION_AND_ACCOUNTING_UNCERTIFIED"
    if f.quote_age_ms > policy.max_quote_age_ms:
        return "STALE_SOURCE_QUOTE"
    if f.liquidity_usd < policy.min_liquidity_usd:
        return "INSUFFICIENT_LIQUIDITY"
    spread = 2 * (o.costs.half_spread_entry_bps + o.costs.half_spread_exit_bps) / 2
    if spread > policy.max_full_spread_bps:
        return "SPREAD_EXCEEDS_RESEARCH_GATE"
    if f.relative_volume < policy.min_relative_volume:
        return "VOLUME_REGIME_NOT_CONFIRMED"
    if f.volatility_momentum < 0:
        return "VOLATILITY_MOMENTUM_NOT_CONFIRMED"
    if o.family == "breakout" and (
        f.breakout_strength < 1.0 or f.momentum_bps <= 0
    ):
        return "BREAKOUT_NOT_CONFIRMED"
    if o.family == "momentum" and f.momentum_bps <= 0:
        return "MOMENTUM_NOT_CONFIRMED"
    if o.family == "reversal" and f.reversal_strength < 1.0:
        return "REVERSAL_NOT_CONFIRMED"
    return None


def _capacity(
    book: FundedBook, base: float, current_gross: float, current_risk: float,
    loss_bps: float, policy: ResearchPolicy,
) -> float:
    cash = max(0.0, book.settled_cash_usd - book.committed_cash_usd
               - book.unsettled_cash_usd)
    gross = max(0.0, policy.max_admission_gross_fraction * base
                - current_gross)
    risk = max(0.0, policy.max_admission_risk_fraction * base
               - current_risk)
    return min(cash, gross, risk * 10_000 / loss_bps)


def _tail_cvar(losses: tuple[float, ...], confidence: float = 0.95) -> float:
    if not losses:
        raise ValueError("C36_EMPTY_TAIL")
    count = max(1, ceil(len(losses) * (1 - confidence)))
    return fmean(sorted(losses, reverse=True)[:count])


def _economics(
    o: Opportunity, fraction: float, policy: ResearchPolicy,
) -> dict[str, float]:
    cost = o.costs.total_bps()
    f = o.forecast
    mean_lower = (f.expected_gross_bps
                  - policy.confidence_multiplier * f.standard_error_bps)
    lower_net = mean_lower - cost
    scenario_log = tuple(
        log1p(fraction * (gross - cost) / 10_000)
        for gross in f.scenario_returns_bps
    )
    log_mean = fmean(scenario_log)
    log_standard_error = pstdev(scenario_log) / sqrt(f.n_effective)
    tail = _tail_cvar(tuple(max(0.0, -v) for v in scenario_log))
    robust_log = (
        log_mean
        - policy.confidence_multiplier * log_standard_error
        - policy.tail_risk_penalty * tail
    )
    required_portfolio_bps = (
        policy.hurdle_bps_per_day * o.horizon_hours / 24
        + policy.no_trade_buffer_portfolio_bps
    )
    threshold = log1p(required_portfolio_bps / 10_000)
    return {
        "full_round_trip_cost_bps": cost,
        "gross_forecast_lower_bps": mean_lower,
        "net_forecast_lower_bps": lower_net,
        "portfolio_edge_lower_bps": fraction * lower_net,
        "portfolio_hurdle_bps": required_portfolio_bps,
        "scenario_expected_log": log_mean,
        "scenario_log_standard_error": log_standard_error,
        "scenario_loss_cvar95": tail,
        "robust_scenario_log_score": robust_log,
        "portfolio_log_hurdle": threshold,
        "log_margin": robust_log - threshold,
    }


def evaluate_matrix(
    candidates: tuple[Opportunity, ...],
    book: FundedBook,
    policy: ResearchPolicy = ResearchPolicy(),
) -> dict[str, object]:
    """Research-only cohort with a deterministic no-trade option.

    Nothing here estimates forecasts, sets broker orders, creates positions,
    fills, market seeds, or claims prospective profitability. Common scenario
    IDs make cross-asset analysis of dependence possible, but are not a proof
    of their true population probability distribution.
    """
    base = _validate_funding(book, policy)
    if not isinstance(candidates, tuple) or len(candidates) > 512:
        raise ValueError("C36_COHORT_INPUT_LIMIT")
    identity: set[tuple[str, str]] = set()
    scenarios: tuple[str, ...] | None = None
    for o in candidates:
        _validate_evidence(o, policy)
        key = (o.symbol, o.native_strategy_id)
        if key in identity:
            raise ValueError("C36_DUPLICATE_ASSET_STRATEGY")
        identity.add(key)
        if scenarios is None:
            scenarios = o.forecast.scenario_ids
        elif o.forecast.scenario_ids != scenarios:
            raise ValueError("C36_SCENARIO_ALIGNMENT_NOT_CAUSAL")
    prelim: list[tuple[float, str, str, Opportunity]] = []
    rejections: list[dict[str, object]] = []
    capacity = _capacity(
        book, base, book.outstanding_gross_usd,
        book.outstanding_risk_usd, 1.0, policy,
    )
    for o in candidates:
        reason = (
            "FUNDED_BOOK_NOT_RECONCILED"
            if not book.reconciled or not book.receipts_complete or book.risk_halt
            else _feature_gate(o, policy)
        )
        if reason is None and o.symbol in book.held_symbols:
            reason = "ALREADY_HELD_DO_NOT_CHURN"
        if reason is not None:
            rejections.append({"symbol": o.symbol, "strategy": o.native_strategy_id,
                               "reason": reason})
            continue
        cap = _capacity(
            book, base, book.outstanding_gross_usd,
            book.outstanding_risk_usd, o.stop_loss_upper_bps, policy,
        )
        if cap <= 0 or capacity <= 0:
            rejections.append({"symbol": o.symbol, "strategy": o.native_strategy_id,
                               "reason": "NO_FUNDED_ADMISSION_CAPACITY"})
            continue
        economics = _economics(o, cap / base, policy)
        if economics["net_forecast_lower_bps"] <= 0:
            reason = "NO_POSITIVE_PESSIMISTIC_NET_EDGE"
        elif economics["portfolio_edge_lower_bps"] <= economics["portfolio_hurdle_bps"]:
            reason = "NO_TRADE_REGION_AFTER_COST_AND_HURDLE"
        elif economics["log_margin"] <= 0:
            reason = "TAIL_AND_UNCERTAINTY_ERASE_LOG_EDGE"
        else:
            prelim.append((economics["log_margin"], o.symbol,
                           o.native_strategy_id, o))
            continue
        rejections.append({"symbol": o.symbol, "strategy": o.native_strategy_id,
                           "reason": reason, "analysis": economics})
    prelim.sort(key=lambda row: (-row[0], row[1], row[2]))
    chosen: list[dict[str, object]] = []
    current_gross = book.outstanding_gross_usd
    current_risk = book.outstanding_risk_usd
    selected_symbols = set(book.held_symbols)
    groups: set[str] = set()
    for _, _, _, o in prelim:
        if o.symbol in selected_symbols:
            rejections.append({"symbol": o.symbol, "strategy": o.native_strategy_id,
                               "reason": "BETTER_NATIVE_STRATEGY_ALREADY_SELECTED"})
            continue
        if o.factor_bucket in groups:
            rejections.append({"symbol": o.symbol, "strategy": o.native_strategy_id,
                               "reason": "FACTOR_CLUSTER_EXPOSURE_DUPLICATED"})
            continue
        cap = _capacity(book, base, current_gross,
                        current_risk, o.stop_loss_upper_bps, policy)
        if cap <= 0:
            rejections.append({"symbol": o.symbol, "strategy": o.native_strategy_id,
                               "reason": "SHARED_CAPITAL_EXHAUSTED"})
            continue
        analysis = _economics(o, cap / base, policy)
        if (analysis["portfolio_edge_lower_bps"]
                <= analysis["portfolio_hurdle_bps"]
                or analysis["log_margin"] <= 0):
            rejections.append({"symbol": o.symbol, "strategy": o.native_strategy_id,
                               "reason": "MARGINAL_EDGE_VANISHED_AFTER_COMPETITION"})
            continue
        chosen.append({
            "symbol": o.symbol,
            "strategy": o.native_strategy_id,
            "book": o.book,
            "factor_bucket": o.factor_bucket,
            "research_notional_usd": cap,
            "research_loss_budget_usd": cap * o.stop_loss_upper_bps / 10_000,
            "analysis": analysis,
            "selection": "OFFLINE_RESEARCH_SHORTLIST_NOT_ORDER",
        })
        current_gross += cap
        current_risk += cap * o.stop_loss_upper_bps / 10_000
        selected_symbols.add(o.symbol)
        groups.add(o.factor_bucket)
    return {
        "schema": RESEARCH_SCHEMA,
        "original_hard_capital_base_usd": base,
        "beginning_observed_equity_usd": book.equity_usd,
        "candidate_count": len(candidates),
        "shortlisted_count": len(chosen),
        "rejected_count": len(rejections),
        "research_shortlist": chosen,
        "no_trade_diagnostics": rejections,
        "baseline": "CASH",
        "comparison_with_original": "UNOBSERVED",
        "scenario_data_not_empirically_authenticated": True,
        "shortlist_requires_independent_prospective_validation": True,
        "frozen_72h_and_admission_caps_preserved": True,
        "cash_reserve_and_future_profits_not_automatically_reinvested": True,
        "options_execution_certified": False,
        "portfolio_financial_go": False,
        "paper_or_live_orders_allowed": False,
        "holdout_M10_sealed": 3200,
        "N9S": "NO_GO",
    }


def compound_one_book(
    initial_equity_usd: float,
    net_economic_pnls_usd: tuple[float, ...],
) -> tuple[float, ...]:
    """Mechanical identity for one book, not a prediction of growth.

    A new entry's admitted capital is still capped at USD 20,000 by C22/C36
    even if the continuously reconciled NAV grows beyond that amount.
    """
    if not isfinite(initial_equity_usd) or initial_equity_usd <= 0:
        raise ValueError("C36_COMPOUND_BEGINNING_EQUITY")
    path = [initial_equity_usd]
    for pnl in net_economic_pnls_usd:
        if not isfinite(pnl) or path[-1] + pnl <= 0:
            raise ValueError("C36_COMPOUND_INVALID_FINANCED_PNL")
        path.append(path[-1] + pnl)
    return tuple(path)
