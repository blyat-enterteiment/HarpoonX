"""Receipt-driven health, degradation and safe rollback decisions; no transport."""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import Any, cast


def require(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(code)


@dataclass(frozen=True)
class GuardLimits:
    quote_max_age_ms: int = 15_000
    reconciliation_max_age_ms: int = 15_000
    model_max_age_ms: int = 168 * 3_600_000
    daily_loss_fraction: float = 0.02
    drawdown_fraction: float = 0.08
    alpha_min_observations: int = 100
    alpha_min_excess_log_growth: float = 0.0
    cost_min_observations: int = 30
    realized_to_modeled_cost_max_ratio: float = 1.25

    def __post_init__(self) -> None:
        for integer_limit in (self.quote_max_age_ms, self.reconciliation_max_age_ms,
                      self.model_max_age_ms, self.alpha_min_observations, self.cost_min_observations):
            require(type(integer_limit) is int and integer_limit > 0, "GUARD_POSITIVE_INTEGER")
        for fraction_limit in (self.daily_loss_fraction, self.drawdown_fraction):
            require(math.isfinite(fraction_limit) and 0 < fraction_limit < 1, "GUARD_RISK_LIMIT")
        require(math.isfinite(self.alpha_min_excess_log_growth), "GUARD_ALPHA_THRESHOLD")
        require(self.quote_max_age_ms <= 15_000 and self.reconciliation_max_age_ms <= 15_000
                and self.model_max_age_ms <= 168 * 3_600_000, "GUARD_FRESHNESS_CAP")
        require(self.daily_loss_fraction <= .02 and self.drawdown_fraction <= .10, "GUARD_BASELINE_RISK_CAP")
        require(type(self.realized_to_modeled_cost_max_ratio) in (int, float)
                and math.isfinite(self.realized_to_modeled_cost_max_ratio)
                and self.realized_to_modeled_cost_max_ratio > 0, "GUARD_COST_RATIO")


def evaluate_health(state: dict[str, Any], now_ms: int,
                    limits: GuardLimits | None = None) -> dict[str, Any]:
    """A UI timer cannot advance any watermark or turn an absent feed green.

    Model/LLM outages do not erase owned inventory. Reduction readiness still
    requires current market data and a reconciled account. This is a decision
    receipt only; an execution transport must separately enforce authorization.
    """
    cfg = limits or GuardLimits()
    require(type(now_ms) is int and now_ms >= 0, "NOW_CLOCK")
    reasons: list[str] = []
    ages: dict[str, int | None] = {}
    fields = {"market_event_at": cfg.quote_max_age_ms,
              "market_received_at": cfg.quote_max_age_ms,
              "broker_reconciled_at": cfg.reconciliation_max_age_ms,
              "model_trained_at": cfg.model_max_age_ms,
              "latest_label_available_at": cfg.model_max_age_ms}
    for field, maximum in fields.items():
        at = state.get(field)
        valid = type(at) is int and 0 <= at <= now_ms
        age = now_ms - cast(int, at) if valid else None
        ages[field] = age
        if not valid:
            reasons.append("MISSING_OR_FUTURE_" + field.upper())
        elif age is not None and age > maximum:
            reasons.append("STALE_" + field.upper())
    event_at, received_at = state.get("market_event_at"), state.get("market_received_at")
    market_clock_consistent = (type(event_at) is int and type(received_at) is int and event_at <= received_at)
    if not market_clock_consistent:
        reasons.append("MARKET_EVENT_RECEIPT_CLOCK")
    trained_at, label_at = state.get("model_trained_at"), state.get("latest_label_available_at")
    if type(trained_at) is int and type(label_at) is int and label_at > trained_at:
        reasons.append("MODEL_LABEL_CLOCK")
    reconciled = state.get("reconciled") is True and not state.get("ambiguous_orders", [])
    if not reconciled:
        reasons.append("UNRECONCILED_ACCOUNT")
    for key, risk_maximum in (("daily_loss_fraction", cfg.daily_loss_fraction),
                         ("drawdown_fraction", cfg.drawdown_fraction)):
        raw_loss = state.get(key)
        if (not isinstance(raw_loss, (float, int)) or isinstance(raw_loss, bool)
                or not math.isfinite(raw_loss) or raw_loss < 0):
            reasons.append("UNKNOWN_" + key.upper())
        elif raw_loss >= risk_maximum:
            reasons.append("LIMIT_" + key.upper())
    if state.get("predictor_ready") is not True:
        reasons.append("PREDICTOR_UNAVAILABLE")
    if state.get("execution_authority") is not True:
        reasons.append("EXECUTION_AUTHORITY_MISSING")
    observations = state.get("alpha_observations", 0)
    require(type(observations) is int and observations >= 0, "ALPHA_SUPPORT")
    if observations >= cfg.alpha_min_observations:
        raw_growth = state.get("rolling_excess_log_growth")
        if (not isinstance(raw_growth, (int, float)) or isinstance(raw_growth, bool)
                or not math.isfinite(raw_growth)):
            reasons.append("ALPHA_METRIC_UNKNOWN")
        elif raw_growth < cfg.alpha_min_excess_log_growth:
            reasons.append("ALPHA_DEGRADATION")
    cost_observations = state.get("cost_observations", 0)
    require(type(cost_observations) is int and cost_observations >= 0, "COST_SUPPORT")
    if cost_observations >= cfg.cost_min_observations:
        cost_ratio = state.get("realized_to_modeled_cost_ratio")
        if (not isinstance(cost_ratio, (int, float)) or isinstance(cost_ratio, bool)
                or not math.isfinite(cost_ratio) or cost_ratio < 0):
            reasons.append("COST_METRIC_UNKNOWN")
        elif cost_ratio > cfg.realized_to_modeled_cost_max_ratio:
            reasons.append("EXECUTION_COST_DEGRADATION")
    market_ok = (market_clock_consistent and ages["market_received_at"] is not None
                 and ages["market_received_at"] <= cfg.quote_max_age_ms
                 and ages["market_event_at"] is not None and ages["market_event_at"] <= cfg.quote_max_age_ms)
    broker_ok = (ages["broker_reconciled_at"] is not None and
                 ages["broker_reconciled_at"] <= cfg.reconciliation_max_age_ms)
    # A source timestamp cannot be replaced by the time this function was called.
    alive = bool(market_ok and broker_ok and reconciled)
    return {"schema": "HARPOON_ROADMAP_HEALTH_1", "evaluated_at": now_ms,
            "alive": alive, "ages_ms": ages, "blocking_reasons": reasons,
            "entries_ready": not reasons,
            "owned_inventory_management": "REDUCTION_READY" if alive else "RECONCILE_ONLY",
            "execution_allowed": False, "transport_present": False,
            "llm_required_for_risk_management": False,
            "monitoring_statistics_are_caller_supplied_not_source_authenticated": True,
            "monitoring_thresholds_are_engineering_defaults_not_calibrated": True}


def rollback_plan(current: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    """Produce an inventory-preserving rollback intent without cancelling orders.

    Authorization and deployment remain separate. A rejected or unevaluated
    policy cannot be restored merely because its code is available.
    """
    require(target.get("economic_status") == "APPROVED_SCOPED_RELEASE",
            "ROLLBACK_TARGET_NOT_APPROVED")
    require(bool(target.get("code_commit") and target.get("recipe_hash")), "ROLLBACK_IDENTITY")
    require(current.get("reconciled") is True, "ROLLBACK_RECONCILIATION_REQUIRED")
    campaigns = copy.deepcopy(current.get("campaigns", []))
    require(isinstance(campaigns, list), "CAMPAIGN_LIST")
    for campaign in campaigns:
        opened, deadline = campaign.get("opened_at"), campaign.get("original_deadline")
        require(type(opened) is int and type(deadline) is int and
                0 < deadline - opened <= 72 * 3_600_000, "ROLLBACK_ORIGINAL_DEADLINE")
    return {"schema": "HARPOON_ROADMAP_ROLLBACK_1", "target_commit": target["code_commit"],
            "target_recipe_hash": target["recipe_hash"], "pause_new_entries": True,
            "campaigns": campaigns, "pending_orders": copy.deepcopy(current.get("pending_orders", [])),
            "inventory": copy.deepcopy(current.get("inventory", {})),
            "execution_allowed": False, "requires_reconciliation_after_restart": True}
