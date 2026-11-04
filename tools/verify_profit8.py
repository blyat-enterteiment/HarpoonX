#!/usr/bin/env python3
"""Read-only PROFIT8 verification; never fits, replays or selects a recipe.

The frozen Roadmap9 accounting auditor is reused through an explicit report
identity adapter. That predecessor uses floating point tolerances. This module
additionally reconstructs executed cash flows and sizing units with Decimal.
Passing means internal arithmetic verification, not economic acceptance.
"""

from __future__ import annotations

import argparse
import bisect
import gzip
import hashlib
import json
import math
import sys
from collections import Counter
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, localcontext
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from audit_historical_results import AuditFailure, need
from audit_roadmap9_results import audit_report as retained_account_audit
from verify_roadmap9_portfolio import dec as retained_decimal

BAR = 300_000
HOUR = 3_600_000
DAY = 86_400_000
ZERO = Decimal(0)
USD_TOL = Decimal("1e-7")
UNIT_TOL = Decimal("1e-12")
LIMITS = {
    "capitalUsd": 20_000,
    "riskFraction": 0.0025,
    "openRiskFraction": 0.0025,
    "grossFraction": 0.12,
    "assetFraction": 0.12,
    "dailyLoss": 0.02,
    "maxDrawdown": 0.08,
}
OBJECTIVE = "m/E-0.5*(v+m*m)/(E*E)-sqrt(meanVariance)/E"
MODES = {"NATIVE_MAX", "MAX_POSITIVE", "ROBUST_LOG"}


def number(value: Any, code: str = "NUMBER") -> Decimal:
    need(type(value) in (int, float) and math.isfinite(value), code + ":FINITE_NUMBER")
    return retained_decimal(value)


def near(actual: Any, expected: Decimal | int, code: str, tolerance: Decimal = USD_TOL) -> None:
    expected = expected if isinstance(expected, Decimal) else Decimal(expected)
    need(abs(number(actual, code) - expected) <= tolerance, code + ":MISMATCH")


def integer(value: Any, code: str, minimum: int = 0) -> int:
    need(type(value) is int and minimum <= value <= 2**53 - 1, code + ":INTEGER")
    return value


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fail(code: str) -> Any:
    raise AuditFailure(code)


def read(path: Path) -> Any:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        return json.load(handle, parse_constant=lambda value: fail("NONFINITE_JSON:" + value))


def safe_path(root: Path, relative: str) -> Path:
    need(isinstance(relative, str) and not Path(relative).is_absolute(), "RELATIVE_PATH_REQUIRED")
    target = (root / relative).resolve()
    need(target.is_relative_to(root.resolve()) and target.is_file(), "MISSING_OR_OUTSIDE_BOUND_FILE:" + relative)
    return target


def tick_round(value: Decimal, tick: Decimal, *, upward: bool) -> Decimal:
    # The registered numerical guard only handles a mathematical tick boundary.
    guard = Decimal("1e-8")
    units = value / tick + (-guard if upward else guard)
    return units.to_integral_value(rounding=ROUND_CEILING if upward else ROUND_FLOOR) * tick


class DatasetIndex:
    """Validate the supplied clock once and index original bar observations."""

    def __init__(self, dataset: dict[str, Any]):
        self.dataset = dataset
        self.sessions = dataset["sessions"]
        need(bool(self.sessions), "DATASET_EMPTY_CALENDAR")
        self.opens: list[int] = []
        for index, session in enumerate(self.sessions):
            opening = integer(session["open"], "SESSION_OPEN")
            closing = integer(session["close"], "SESSION_CLOSE")
            need(opening < closing and (closing - opening) % BAR == 0, "SESSION_GRID")
            need(not index or opening > self.sessions[index - 1]["close"], "SESSION_CHRONOLOGY")
            need(not index or session["date"] > self.sessions[index - 1]["date"], "SESSION_DATE_ORDER")
            self.opens.append(opening)
        self.series: dict[str, dict[str, Any]] = {}
        self.known: dict[str, list[int]] = {}
        self.by_time: dict[str, dict[int, dict[str, Any]]] = {}
        self.bars = 0
        for series in dataset["series"]:
            symbol = series["symbol"]
            need(symbol not in self.series and isinstance(symbol, str), "DUPLICATE_DATA_SYMBOL")
            need(series["pointValue"] == 1 and number(series["tick"]) > 0, "CASH_SHARE_DATA_UNITS")
            prior_end = prior_known = -1
            for bar in series["bars"]:
                at = integer(bar["t"], "BAR_TIME")
                end = integer(bar["end"], "BAR_END")
                known = integer(bar["availableAt"], "BAR_AVAILABLE_AT")
                need(end == at + BAR and at >= prior_end and known > prior_known, "BAR_CHRONOLOGY_GRID")
                need(end <= known <= end + 60_000, "BAR_AVAILABILITY_CLOCK")
                session = self.session(at)
                need(session is not None and end <= session["close"] and (at - session["open"]) % BAR == 0,
                     "BAR_OUTSIDE_CALENDAR")
                o, high, low, close = [number(bar[key], "OHLC") for key in ("o", "h", "l", "c")]
                need(ZERO < low <= min(o, close) <= max(o, close) <= high, "OHLC_DOMAIN")
                need(number(bar["v"], "VOLUME") >= ZERO, "VOLUME_DOMAIN")
                prior_end, prior_known = end, known
            self.series[symbol] = series
            self.known[symbol] = [bar["availableAt"] for bar in series["bars"]]
            self.by_time[symbol] = {bar["t"]: bar for bar in series["bars"]}
            self.bars += len(series["bars"])
        need(bool(self.series), "DATASET_EMPTY_SERIES")

    def session(self, at: int) -> dict[str, Any] | None:
        position = bisect.bisect_right(self.opens, at) - 1
        if position >= 0 and at < self.sessions[position]["close"]:
            return self.sessions[position]
        return None

    def reference(self, symbol: str, at: int) -> dict[str, Any] | None:
        need(symbol in self.series, "UNKNOWN_SIGNAL_SYMBOL")
        index = bisect.bisect_right(self.known[symbol], at) - 1
        return self.series[symbol]["bars"][index] if index >= 0 else None

    def deadline(self, at: int, hours: int) -> int | None:
        need(hours in (24, 72), "REGISTERED_24_OR_72_HOURS")
        target = at + hours * HOUR
        if self.sessions[-1]["close"] < target:
            return None
        index = bisect.bisect_right(self.opens, target) - 1
        if index < 0:
            return None
        session = self.sessions[index]
        raw = min(target, session["close"] - 2 * BAR)
        return session["open"] + (raw - session["open"]) // BAR * BAR

    def audit_signal(self, signal: dict[str, Any]) -> None:
        at = integer(signal["at"], "SIGNAL_DECISION")
        session = self.session(at)
        need(session is not None and at == session["open"] + HOUR + 1000, "FIXED_DECISION_CLOCK")
        assert session is not None  # Narrow only after the explicit audit failure.
        need(signal["direction"] == 1 and signal["hypothesis"] == "CLOSED_CHANNEL", "FIXED_NATIVE_ENTRY_POLICY")
        metadata = signal.get("metadata", {})
        need(metadata.get("roadmapHorizonHours") in (24, 72), "REGISTERED_24_OR_72_HOURS")
        need(not metadata.get("roadmapExit") and not metadata.get("researchExit"), "FIXED_NATIVE_EXIT_POLICY")
        need(number(signal["stopDistance"]) > ZERO, "POSITIVE_STOP_DISTANCE")
        planned = session["open"] + math.ceil((at - session["open"]) / BAR) * BAR
        need(signal.get("plannedEntryAt", planned) == planned and planned < session["close"] - BAR,
             "CAUSAL_PLANNED_ENTRY")


def basis_weights(quantity: int) -> tuple[int, int]:
    integer(quantity, "BASIS_QUANTITY")
    early = 2 * (quantity // 4)
    return early, quantity - early


def covariance(matrix: Any, code: str) -> list[list[Decimal]]:
    need(isinstance(matrix, list) and len(matrix) == 2 and
         all(isinstance(row, list) and len(row) == 2 for row in matrix), code + ":SHAPE")
    result = [[number(value, code) for value in row] for row in matrix]
    a, b, c, d = (*result[0], *result[1])
    scale = max(abs(b), abs(c), Decimal("1e-30"))
    need(a >= ZERO and d >= ZERO and abs(b - c) <= Decimal("1e-10") * scale,
         code + ":SYMMETRY_DOMAIN")
    middle = (b + c) / 2
    need(a * d - middle * middle >= -Decimal("1e-10") * max(a * d, middle * middle, Decimal("1e-30")),
         code + ":PSD")
    return [[a, middle], [middle, d]]


def quadratic(weights: tuple[int, int], matrix: list[list[Decimal]]) -> Decimal:
    a, b = weights
    return max(ZERO, a * a * matrix[0][0] + 2 * a * b * matrix[0][1] + b * b * matrix[1][1])


def audit_sizing(state: dict[str, Any], code: str = "SIZING") -> int:
    """Check dollar, squared-dollar and dimensionless utility without a fit."""
    receipt = state["profit8Sizing"]
    mode = receipt["mode"]
    need(mode in MODES, code + ":MODE")
    qmax = integer(receipt["qMax"], code + ":QMAX")
    quantity = integer(receipt["quantity"], code + ":QUANTITY")
    need(qmax == state["plan"]["quantity"] and quantity == state["quantity"] and quantity <= qmax,
         code + ":QUANTITY_BINDING")
    ref, equity = number(state["reference"]["price"]), number(state["equity"])
    near(receipt["referencePrice"], ref, code + ":CAUSAL_NORMALIZER")
    near(receipt["equityUsd"], equity, code + ":CONTINUOUS_EQUITY")
    need(ref > ZERO and equity > ZERO, code + ":POSITIVE_UNITS")
    if mode == "NATIVE_MAX":
        need(quantity == qmax and receipt["forecastUsed"] is False and receipt["candidates"] == [],
             code + ":NATIVE_MAXIMUM")
        return 0
    forecast = state["opportunity"]["metadata"]["profit8Forecast"]
    at = state["opportunity"]["at"]
    need(forecast["basis_order"] == ["E", "T"] and len(forecast["mean"]) == 2,
         code + ":NET_BASIS_ORDER")
    trained = integer(forecast["trained_through"], code + ":TRAINED_THROUGH")
    available = integer(forecast["available_at"], code + ":FORECAST_AVAILABLE")
    need(trained < at and trained <= available <= at, code + ":FUTURE_FORECAST")
    near(forecast["normalizer_price"], ref, code + ":FORECAST_NORMALIZER")
    need(receipt["forecastUsed"] is True and receipt["modelId"] == forecast["model_id"] and
         receipt["meanBasis"] == forecast["mean"] and receipt["uncertaintyPenalty"] == 1 and
         receipt["objective"] == OBJECTIVE, code + ":FORECAST_OBJECTIVE_BINDING")
    means = [number(value) for value in forecast["mean"]]
    outcome = covariance(forecast["covariance"], code + ":OUTCOME_COVARIANCE")
    uncertainty = covariance(forecast["mean_covariance"], code + ":MEAN_COVARIANCE")
    need(receipt["covariance"] == forecast["covariance"] and
         receipt["meanCovariance"] == forecast["mean_covariance"], code + ":COVARIANCE_BINDING")
    candidates = receipt["candidates"]
    expected_quantities = list(range(qmax + 1)) if mode == "ROBUST_LOG" else ([0, qmax] if qmax else [0])
    need([row["quantity"] for row in candidates] == expected_quantities, code + ":COMPLETE_INTEGER_CHOICES")
    for candidate in candidates:
        weights = basis_weights(candidate["quantity"])
        need(candidate["basisWeights"] == list(weights), code + ":LOT_BASIS")
        mean = ref * sum((Decimal(q) * value for q, value in zip(weights, means, strict=True)), ZERO)
        variance = ref * ref * quadratic(weights, outcome)
        mean_variance = ref * ref * quadratic(weights, uncertainty)
        se = mean_variance.sqrt()
        utility = mean / equity - (variance + mean * mean) / (2 * equity * equity) - se / equity
        for name, expected in (("meanUsd", mean), ("varianceUsd2", variance),
                               ("meanVarianceUsd2", mean_variance), ("meanSeUsd", se)):
            near(candidate[name], expected, code + ":NET_NO_SECOND_COST:" + name)
        near(candidate["utility"], utility, code + ":DIMENSIONLESS_UTILITY", UNIT_TOL)
    chosen = candidates[0]
    if mode == "MAX_POSITIVE":
        if candidates[-1]["meanUsd"] > 0:
            chosen = candidates[-1]
    else:
        for candidate in candidates:
            if candidate["utility"] > chosen["utility"]:
                chosen = candidate
    need(receipt["chosen"] == chosen and quantity == chosen["quantity"], code + ":REGISTERED_SELECTION")
    return len(candidates)


def audit_trace(trace: dict[str, Any], fee: Decimal, code: str) -> dict[str, Decimal]:
    """Executed cash flows are reconstructed from signed native-share events."""
    quantity = integer(trace["quantity"], code + ":QUANTITY", 1)
    events = trace["inventoryEvents"]
    need(bool(events) and events[0]["quantityDelta"] == quantity and events[0]["kind"] == "ENTRY",
         code + ":ENTRY")
    inventory, net, fees, prior = 0, ZERO, ZERO, -1
    for event in events:
        delta = event["quantityDelta"]
        need(type(delta) is int and delta != 0, code + ":SIGNED_INTEGER_LOT")
        at, known = integer(event["at"], code + ":EVENT_AT"), integer(event["knownAt"], code + ":KNOWN_AT")
        need(at >= prior and known >= at, code + ":EVENT_CLOCK")
        inventory += delta
        need(0 <= inventory <= quantity, code + ":NO_SHORT_OR_DUPLICATE_ENTRY")
        price = number(event["filledPrice"], code + ":FILLED_PRICE")
        need(price > ZERO, code + ":POSITIVE_FILL")
        charge = Decimal(abs(delta)) * fee
        near(event["feeUsd"], charge, code + ":FEE_ONCE_PER_SIDE")
        net -= Decimal(delta) * price + charge
        fees += charge
        prior = at
    need(inventory == 0 and events[0]["at"] == trace["opened"] and events[-1]["at"] == trace["closed"],
         code + ":TERMINAL_INVENTORY_CLOCK")
    dividends = sum((number(item["amountUsd"]) for item in trace["dividendEntitlements"]), ZERO)
    near(trace["entry"], number(events[0]["filledPrice"]), code + ":ENTRY_PRICE")
    near(trace["netUsd"], net, code + ":EXECUTED_CASH_FLOW")
    near(trace["feesUsd"], fees, code + ":FEES")
    near(trace["dividendAccruedUsd"], dividends, code + ":DIVIDEND_ACCRUAL")
    near(trace["netEconomicUsd"], net + dividends, code + ":NET_NO_DOUBLE_COST")
    return {"net": net, "fees": fees, "dividends": dividends, "economic": net + dividends}


def audit_teachers(artifact: dict[str, Any], protocol: dict[str, Any], dataset: dict[str, Any],
                   scenario: str, *, index: DatasetIndex | None = None) -> dict[str, Any]:
    index = index or DatasetIndex(dataset)
    need(artifact["schema"] == "HARPOON_PROFIT8_POLICY_LABELS_1" and artifact["scenario"] == scenario,
         "TEACHER_IDENTITY")
    need(artifact["financial_acceptance_allowed"] is False and artifact["liveApproved"] is False and
         artifact["fixed_calendar_overhead_in_target"] is False and
         artifact["no_fill_targets_retained_as_zero"] is True, "TEACHER_SCOPE")
    labels = artifact["labels"]
    need(len({row["signal_id"] for row in labels}) == len(labels), "TEACHER_DUPLICATE_SIGNAL")
    need(dict(Counter(row["status"] for row in labels)) == artifact["counts"], "TEACHER_COUNTS")
    cost = protocol["scenarios"][scenario]
    fee = number(cost["commission_usd_per_share_per_side"])
    friction = (number(cost["spread_bps"]) / 2 + number(cost["slippage_bps"])) / 10_000
    traces = 0
    for label in labels:
        code = "TEACHER:" + label["signal_id"]
        at = integer(label["decision_at"], code + ":DECISION")
        symbol = label["symbol"]
        need(label["basis_order"] == ["E", "T"] and label["financial_acceptance_allowed"] is False,
             code + ":BASIS_SCOPE")
        known = label["label_known_at"]
        need(label.get("known_at", known) == known, code + ":KNOWN_ALIAS")
        if label["status"] in {"REFUSED_BEFORE_ENTRY", "BLOCKED_UNOBSERVED_PATH"}:
            need(all(label[name] is None for name in ("E", "T", "E_usd", "T_usd", "net_basis", "fill", "fill_flag",
                                                     "quantity1_net_usd", "quantity4_net_usd", "label_known_at")),
                 code + ":MISSING_TAPE_IS_NOT_ZERO_PAYOFF")
            continue
        need(label["status"] in {"OBSERVED_MODELED_PATH", "MODELED_IOC_NO_FILL"}, code + ":STATUS")
        reference = index.reference(symbol, at)
        need(reference is not None, code + ":CAUSAL_REFERENCE")
        assert reference is not None
        ref = number(reference["c"])
        near(label["ref_price"], ref, code + ":REF_PRICE")
        need(label["reference_available_at"] == reference["availableAt"] <= at, code + ":REFERENCE_CLOCK")
        tick = number(index.series[symbol]["tick"])
        limit = tick_round(ref * Decimal("1.003"), tick, upward=False)
        near(label["limit_price"], limit, code + ":COMMON_CAUSAL_IOC")
        deadline = index.deadline(at, label["horizon_hours"])
        need(deadline is not None and label["label_end"] == deadline, code + ":DEADLINE_COHORT")
        assert deadline is not None
        first = index.by_time[symbol].get(label["planned_entry_at"])
        last = index.by_time[symbol].get(deadline)
        need(first is not None and last is not None, code + ":OBSERVED_ENTRY_DEADLINE_REQUIRED")
        assert first is not None and last is not None
        integer(known, code + ":LABEL_KNOWN")
        need(known >= max(first["availableAt"], last["availableAt"]), code + ":PREMATURE_LABEL")
        near(label["gross_entry_open"], number(first["o"]), code + ":RAW_ENTRY_OPEN")
        near(label["gross_deadline_open"], number(last["o"]), code + ":RAW_DEADLINE_OPEN")
        need(label["deadline_bar_available_at"] == last["availableAt"], code + ":DEADLINE_BAR_KNOWN")
        entry = tick_round(number(first["o"]) * (1 + friction), tick, upward=True)
        if label["status"] == "MODELED_IOC_NO_FILL":
            need(entry > limit and label["fill"] is False and label["fill_flag"] == 0,
                 code + ":NO_FILL_OBSERVATION")
            for name in ("E", "T", "E_usd", "T_usd", "quantity1_net_usd", "quantity4_net_usd", "gross_deadline_return"):
                near(label[name], ZERO, code + ":EXPLICIT_ZERO:" + name)
            need(label["net_basis"] == [0, 0], code + ":ZERO_BASES")
            near(label["observed_open_fill_price"], entry, code + ":NO_FILL_PRICE")
            need(known == max(first["availableAt"], last["availableAt"]), code + ":NO_FILL_MATURITY")
            continue
        need(entry <= limit and label["fill"] is True and label["fill_flag"] == 1, code + ":FILL_OBSERVATION")
        near(label["entry_price"], entry, code + ":MODELED_ENTRY_PRICE")
        one, four = label["quantity1_trace"], label["quantity4_trace"]
        need(one["quantity"] == 1 and four["quantity"] == 4 and one["opened"] == four["opened"] == first["t"] and
             one["closed"] == four["closed"] <= deadline and
             one["holdingDeadlineAt"] == four["holdingDeadlineAt"] == deadline,
             code + ":SHARED_POLICY_PATH")
        audited_one = audit_trace(one, fee, code + ":Q1")
        audited_four = audit_trace(four, fee, code + ":Q4")
        for trace in (one, four):
            maximum = integer(trace["maximum_policy_known_at"], code + ":POLICY_KNOWN")
            need(maximum >= max(event["knownAt"] for event in trace["inventoryEvents"]), code + ":EVENT_KNOWLEDGE")
        need(known == max(first["availableAt"], last["availableAt"], one["maximum_policy_known_at"],
                          four["maximum_policy_known_at"]), code + ":EXACT_MATURITY")
        terminal = audited_one["economic"]
        early = (audited_four["economic"] - 2 * terminal) / 2
        for name, expected in (("T_usd", terminal), ("E_usd", early), ("T", terminal / ref), ("E", early / ref),
                               ("quantity1_net_usd", terminal), ("quantity4_net_usd", audited_four["economic"]),
                               ("quantity1_fees_usd", audited_one["fees"]), ("quantity4_fees_usd", audited_four["fees"]),
                               ("quantity1_dividend_usd", audited_one["dividends"]),
                               ("quantity4_dividend_usd", audited_four["dividends"])):
            near(label[name], expected, code + ":PAYOFF_BASIS:" + name)
        need(len(label["net_basis"]) == 2, code + ":BASIS_SHAPE")
        near(label["net_basis"][0], early / ref, code + ":NORMALIZED_E", UNIT_TOL)
        near(label["net_basis"][1], terminal / ref, code + ":NORMALIZED_T", UNIT_TOL)
        near(label["gross_deadline_return"], (number(last["o"]) - number(first["o"])) / ref,
             code + ":GROSS_REFERENCE", UNIT_TOL)
        traces += 2
    return {"verified": True, "labels": len(labels), "counts": artifact["counts"],
            "decimal_policy_traces": traces, "maturity_is_deadline_cohort": True,
            "source_receipt_times_authenticated": False, "fixed_overhead_in_labels": False}


def audit_planning(state: dict[str, Any], index: DatasetIndex, cost: dict[str, Any],
                   records: dict[str, dict[str, Any]], code: str) -> int:
    signal, plan = state["opportunity"], state["plan"]
    index.audit_signal(signal)
    if plan["status"] != "PLANNED":
        need(index.reference(signal["symbol"], signal["at"]) is None, code + ":REFERENCE_REFUSAL")
        return 0
    reference = index.reference(signal["symbol"], signal["at"])
    need(reference is not None, code + ":REFERENCE_REQUIRED")
    assert reference is not None
    for actual in (state["reference"], plan["reference"]):
        near(actual["price"], number(reference["c"]), code + ":REFERENCE_PRICE")
        need(actual["sourceAvailableAt"] == reference["availableAt"] <= signal["at"] and
             actual["sourceBarAt"] == reference["t"] and actual["decisionAt"] == signal["at"],
             code + ":REFERENCE_CLOCK")
    before = state["reservationBefore"]
    near(state["openRisk"], number(before["riskUsd"]), code + ":RESERVED_RISK_BALANCE")
    notional = number(before["notionalUsd"])
    inventory_marks = {mark["id"]: mark for mark in state["inventoryMarks"]}
    for reservation in before["reservations"]:
        if reservation["state"] != "OPENED":
            continue
        bar = index.reference(reservation["symbol"], signal["at"])
        need(bar is not None, code + ":INVENTORY_REFERENCE")
        assert bar is not None
        marked = reservation["quantity"] * number(bar["c"])
        reserved = number(reservation["notionalUsd"])
        notional += max(ZERO, marked - reserved)
        mark = inventory_marks.pop(reservation["id"], None)
        need(mark is not None and mark["fullOriginalQuantity"] == reservation["quantity"],
             code + ":FULL_QUANTITY_RESERVATION")
        near(mark["markedNotionalUsd"], marked, code + ":INVENTORY_MARK")
        near(mark["reservedNotionalUsd"], max(marked, reserved), code + ":CONSERVATIVE_MARK")
    need(not inventory_marks, code + ":UNATTRIBUTED_INVENTORY_MARK")
    near(state["notional"], notional, code + ":MARKED_RESERVED_NOTIONAL")
    tick = number(index.series[signal["symbol"]]["tick"])
    fee = number(cost["commission_usd_per_share_per_side"])
    friction = (number(cost["spread_bps"]) / 2 + number(cost["slippage_bps"])) / 10_000
    limit = tick_round(number(reference["c"]) * Decimal("1.003"), tick, upward=False)
    distance = (number(signal["stopDistance"]) / tick).to_integral_value(rounding=ROUND_CEILING) * tick
    risk_unit = distance + 2 * fee + 2 * limit * friction
    equity = number(state["equity"])
    risk_budget = max(ZERO, min(equity * number(LIMITS["riskFraction"]),
                                equity * number(LIMITS["openRiskFraction"]) - number(before["riskUsd"])))
    notional_budget = max(ZERO, min(equity * number(LIMITS["assetFraction"]),
                                    equity * number(LIMITS["grossFraction"]) - notional))
    cash_budget = number(plan["cashBudgetUsd"])
    qmax = int(max(ZERO, min(risk_budget / risk_unit, notional_budget / limit,
                             cash_budget / (limit + fee))).to_integral_value(rounding=ROUND_FLOOR))
    for name, expected in (("priceCeiling", limit), ("riskUnit", risk_unit), ("roundedStopDistance", distance),
                           ("riskBudgetUsd", risk_budget), ("notionalBudgetUsd", notional_budget)):
        near(plan[name], expected, code + ":EX_ANTE_" + name)
    need(plan["quantity"] == qmax, code + ":NO_FUTURE_PRICE_SIZING")
    if "profit8Sizing" in state:
        candidates = audit_sizing(state, code + ":SIZING")
    else:
        need(qmax == 0, code + ":MISSING_SIZING_RECEIPT")
        candidates = 0
    if "iocPlan" in state:
        near(state["iocPlan"]["priceCeiling"], limit, code + ":QUANTITY_INDEPENDENT_IOC")
    if state.get("reservationStatus") == "RESERVED":
        committed = state["profit8CommittedReservation"]
        quantity = integer(state["quantity"], code + ":COMMITTED_QUANTITY", 1)
        need(committed["quantity"] == quantity and committed["noPartialRelease"] is True and
             committed["upperPriceBoundIsCausal"] is True, code + ":COMMITTED_CONTRACT")
        for field, expected in (("riskUsd", quantity * risk_unit), ("notionalUsd", quantity * limit),
                                ("cashUsd", quantity * (limit + fee))):
            near(committed[field], expected, code + ":COMMITMENT_" + field)
            near(records[signal["id"]][field], expected, code + ":RESERVATION_" + field)
    return candidates


def audit_report(report: dict[str, Any], protocol: dict[str, Any], dataset: dict[str, Any], key: str,
                 *, index: DatasetIndex | None = None, teachers: dict[str, Any] | None = None,
                 signals: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    index = index or DatasetIndex(dataset)
    scenario, _policy = key.split(":")
    need(protocol["limits"] == LIMITS, key + ":FROZEN_RISK_LIMITS")
    need(report["native_control"] == "NATIVE_HISTORICAL_ULTIMATE_PROFIT8" and report["study"] == "PROFIT8",
         key + ":NEW_REPLAY_IDENTITY")
    need(report["metadata"]["continuous"] is True and
         report["metadata"]["entryExecution"] == "IOC_LIMIT_COMMON_CAUSAL_30BPS", key + ":CONTINUOUS_COMMON_IOC")
    # Only identity is adapted. Frozen accounting code and economic inputs stay
    # unchanged. The new committed-reservation amounts are reconciled below.
    adapter = {**report, "native_control": "NATIVE_HISTORICAL_ULTIMATE_ROADMAP9"}
    inherited = retained_account_audit(adapter, protocol, dataset, key)
    cost = protocol["scenarios"][scenario]
    fee = number(cost["commission_usd_per_share_per_side"])
    records = {record["id"]: record for record in report["reservationBook"]["reservations"]}
    signal_map = {signal["id"]: signal for signal in signals} if signals is not None else None
    teacher_map = {(row["symbol"], row["decision_at"], row["horizon_hours"]): row
                   for row in teachers["labels"]} if teachers is not None else None
    candidate_checks = 0
    for state in report["states"]:
        signal = state["opportunity"]
        if signal_map is not None:
            original = signal_map.get(signal["id"])
            need(original is not None and all(signal[name] == value for name, value in original.items()),
                 key + ":STATE_SIGNAL_BINDING")
        candidate_checks += audit_planning(state, index, cost, records, key + ":PLAN:" + signal["id"])
    totals = {"net": ZERO, "fees": ZERO, "dividends": ZERO, "economic": ZERO}
    teacher_matches = 0
    for trade in report["funded"]:
        values = audit_trace(trade, fee, key + ":CASH_FLOW:" + trade["id"])
        totals = {name: totals[name] + value for name, value in values.items()}
        if teacher_map is not None:
            state = next(state for state in report["states"] if state["opportunity"]["id"] == trade["id"])
            signal = state["opportunity"]
            label = teacher_map.get((trade["symbol"], signal["at"], signal["metadata"]["roadmapHorizonHours"]))
            need(label is not None and label["status"] == "OBSERVED_MODELED_PATH", key + ":FUNDED_TEACHER_PATH")
            assert label is not None
            early, terminal = basis_weights(trade["quantity"])
            expected = early * number(label["E_usd"]) + terminal * number(label["T_usd"])
            near(trade["netEconomicUsd"], expected, key + ":EXACT_INTEGER_PAYOFF_IDENTITY")
            teacher_matches += 1
    first, last = report["curve"][0], report["curve"][-1]
    days = last["end_at"] // DAY - (first["start_at"] + 1) // DAY + 1
    overhead = days * number(cost["external_cost_usd_per_calendar_day"])
    near(report["accounting"]["modeledExternalCostsUsd"], overhead, key + ":FIXED_COST_ONCE_PER_CALENDAR_DAY")
    net = totals["economic"] - overhead
    near(report["accounting"]["netEconomicUsd"], net, key + ":DECIMAL_NET_ACCOUNT")
    near(last["equity_end_usd"], Decimal(LIMITS["capitalUsd"]) + net, key + ":DECIMAL_TERMINAL_EQUITY")
    near(sum(row["external_costs_usd"] for row in report["curve"]), overhead, key + ":NO_PHASE_COST_RESET")
    for name, window in protocol.get("reporting_windows", {}).items():
        rows = [row for row in report["curve"] if window["start"] <= row["session_id"] <= window["end"]]
        if rows:
            summary = report["descriptive_windows"][name]
            near(summary["capital_at_phase_start"], number(rows[0]["equity_start_usd"]), key + ":WINDOW_NO_RESET")
            near(summary["economic_pnl_modeled_usd"], number(rows[-1]["equity_end_usd"]) -
                 number(rows[0]["equity_start_usd"]), key + ":WINDOW_PNL")
    return {**inherited, "decimal_cash_flow_verified": True, "decimal_precision": 50,
            "decimal_net_economic_usd": str(net), "calendar_days_charged": days,
            "sizing_candidates_recomputed": candidate_checks, "exact_teacher_payoff_matches": teacher_matches,
            "retained_core_identity_adapter": "PROFIT8_TO_ROADMAP9_IDENTITY_ONLY",
            "retained_core_uses_decimal": False, "new_decimal_layer": True,
            "accounting_core_sha256": sha(ROOT / "tools/audit_roadmap9_results.py")}


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def verify_bindings(directory: Path, root: Path = ROOT) -> dict[str, Any]:
    bindings = read(directory / "source_bindings.json")
    need(isinstance(bindings.get("schema"), str), "BINDING_SCHEMA")
    counts = {}
    for category in ("sources", "data"):
        mapping = bindings[category]
        need(isinstance(mapping, dict) and bool(mapping), "EMPTY_BINDING:" + category)
        for relative, expected in mapping.items():
            need(isinstance(expected, str) and len(expected) == 64 and sha(safe_path(root, relative)) == expected,
                 "BINDING_CHANGED:" + relative)
        counts[category] = len(mapping)
    for name in ("protocol", "recipes"):
        need(sha(directory / (name + ".json")) == bindings[name + "_sha256"], "PACKET_BINDING:" + name)
    return {"verified": True, **counts, "bindings_sha256": sha(directory / "source_bindings.json")}


def audit_rows(rows: list[dict[str, Any]], teachers: dict[str, dict[str, Any]],
               index: DatasetIndex) -> dict[str, dict[str, Any]]:
    by_id = {row["id"]: row for row in rows}
    need(len(by_id) == len(rows), "DUPLICATE_FEATURE_ROW")
    for row in rows:
        at = integer(row["decision_at"], "FEATURE_DECISION")
        need(integer(row["available_at"], "FEATURE_AVAILABLE") <= at, "FUTURE_FEATURE_ROW")
        need(row["residual_latest_at"] <= row["residual_model_at"] <= at, "RESIDUAL_MODEL_CLOCK")
        reference = index.reference(row["symbol"], at)
        need(reference is not None, "ROW_REFERENCE_REQUIRED")
        assert reference is not None
        near(row["reference_price"], number(reference["c"]), "ROW_CAUSAL_REFERENCE")
        session = index.session(at)
        need(session is not None and session["date"] == row["session"], "ROW_SESSION")
        assert session is not None
        for horizon, features in row["features_by_horizon"].items():
            need(len(features) == 11 and all(type(value) in (int, float) and math.isfinite(value) for value in features),
                 "REGISTERED_FEATURE_UNITS")
            deadline = index.deadline(at, int(horizon))
            need(deadline is not None and row["deadline_by_horizon"][horizon] == deadline and
                 row["planned_entry_at"] == session["open"] + 13 * BAR, "ROW_CALENDAR_HORIZON")
            assert deadline is not None
            near(features[6], number(row["residual_z"]), "ROW_RESIDUAL_FEATURE")
            near(features[8], number((deadline - row["planned_entry_at"]) / HOUR), "ROW_HOURS_FEATURE")
            need(features[9] == sum(row["planned_entry_at"] < item["open"] <= deadline for item in index.sessions),
                 "ROW_OVERNIGHT_COUNT")
            need(features[10] == float(row["symbol"] == "MSFT"), "ROW_SYMBOL_FEATURE")
    valid_statuses = {"OBSERVED_MODELED_PATH", "MODELED_IOC_NO_FILL", "FILLED", "NO_FILL"}
    for scenario, artifact in teachers.items():
        for teacher in artifact["labels"]:
            row_id, horizon = teacher["signal_id"].rsplit(":H", 1)
            need(row_id in by_id, "TEACHER_FEATURE_ROW_BINDING")
            row, key = by_id[row_id], scenario + ":" + horizon
            need(teacher["symbol"] == row["symbol"] and teacher["decision_at"] == row["decision_at"],
                 "TEACHER_FEATURE_IDENTITY")
            attached = row["labels"].get(key)
            if teacher["status"] not in valid_statuses:
                need(attached is None, "BLOCKED_LABEL_ADMITTED_TO_FEATURE_ROWS")
                continue
            need(attached is not None and attached["known_at"] == teacher["label_known_at"] and
                 attached["label_end"] == teacher["label_end"] and attached["net_basis"] == teacher["net_basis"] and
                 attached["gross_deadline_return"] == teacher["gross_deadline_return"] and
                 attached["fill"] == teacher["fill"], "TEACHER_TARGET_ALTERED_OR_NO_FILL_DROPPED")
    return by_id


def audit_forecasts(artifact: dict[str, Any], teachers: dict[str, dict[str, Any]],
                    rows: list[dict[str, Any]], protocol: dict[str, Any], index: DatasetIndex) -> dict[str, Any]:
    """Verify hashes and actual training cohorts; do not refit the model."""
    need(artifact["schema"] == "HARPOON_PROFIT8_FORECASTS_1" and
         artifact["financial_acceptance_allowed"] is False and artifact["liveApproved"] is False,
         "FORECAST_ARTIFACT_SCOPE")
    by_id = audit_rows(rows, teachers, index)
    settings = protocol["forecast"]
    valid = {"OBSERVED_MODELED_PATH", "MODELED_IOC_NO_FILL", "FILLED", "NO_FILL"}
    no_fill = {"MODELED_IOC_NO_FILL", "NO_FILL"}
    prepared = sorted(rows, key=lambda row: (row["decision_at"], row["symbol"], row["id"]))
    evaluated = [row for row in prepared if protocol["periods"]["evaluation_start"] <= row["session"]
                 <= protocol["periods"]["evaluation_end"]]
    cohorts: dict[str, list[dict[str, Any]]] = {}
    for scenario in protocol["scenarios"]:
        for horizon in (24, 72):
            key = scenario + ":" + str(horizon)
            cohorts[key] = [row for row in prepared if str(horizon) in row["features_by_horizon"]
                            and row["labels"].get(key, {}).get("status") in valid]
    models = artifact["models"]
    training_rows = retained_no_fills = 0
    for model_id, model in models.items():
        code = "MODEL:" + model_id
        need(model["model_id"] == model_id and model_id == "PROFIT8-" + canonical_hash(
            {name: value for name, value in model.items() if name != "model_id"}), code + ":HASH")
        at = integer(model["model_asof"], code + ":ASOF")
        key = model["key"]
        need(key in cohorts and model["available_at"] == at, code + ":ORIGINAL_MODEL_CLOCK")
        matured = [row for row in cohorts[key] if row["decision_at"] < at and row["labels"][key]["known_at"] < at]
        sessions = sorted({row["session"] for row in matured})[-settings["training_sessions"]:]
        selected = [row for row in matured if row["session"] in set(sessions)]
        need(model["train_ids"] == [row["id"] for row in selected] and model["train_sessions"] == sessions and
             len(sessions) >= settings["minimum_matured_sessions"], code + ":FULL_MATURED_COHORT")
        known = max(row["labels"][key]["known_at"] for row in selected)
        need(model["maximum_label_known_at"] == model["trained_through"] == known < at, code + ":PURGED_MATURITY")
        need(all(model["settings"][name] == settings[name] for name in model["settings"]), code + ":FROZEN_SETTINGS")
        need(model["feature_names"] == settings["features"], code + ":FEATURE_ORDER")
        calibration = model["calibration"]
        validation_sessions = sessions[-settings["calibration_sessions"]:]
        validation = [row for row in selected if row["session"] in set(validation_sessions)]
        first_validation = min(row["decision_at"] for row in validation)
        earlier = [row for row in selected if row["session"] not in set(validation_sessions)]
        training = [row for row in earlier if row["labels"][key]["known_at"] < first_validation]
        purged = [row for row in earlier if row["labels"][key]["known_at"] >= first_validation]
        need(calibration["validation_ids"] == [row["id"] for row in validation] and
             calibration["validation_sessions"] == validation_sessions and
             calibration["train_ids"] == [row["id"] for row in training] and
             calibration["purged_ids"] == [row["id"] for row in purged] and
             calibration["first_validation_at"] == first_validation, code + ":CALIBRATION_PURGE")
        need(len({row["session"] for row in training}) >= settings["minimum_earlier_training_sessions"] and
             calibration["maximum_training_label_known_at"] ==
             max(row["labels"][key]["known_at"] for row in training) < first_validation,
             code + ":CALIBRATION_TRAINING_CLOCK")
        payload = []
        for row in selected:
            label = row["labels"][key]
            status = "NO_FILL" if label["status"] in no_fill else "FILLED"
            payload.append({"id": row["id"], "session": row["session"], "symbol": row["symbol"],
                            "decision_at": row["decision_at"], "available_at": row["available_at"],
                            "reference_price": float(row["reference_price"]),
                            "features": [float(value) for value in row["features_by_horizon"][str(model["horizon_hours"])]],
                            "known_at": label["known_at"], "net_basis": [float(value) for value in label["net_basis"]],
                            "gross_deadline_return": float(label["gross_deadline_return"]), "status": status})
            retained_no_fills += status == "NO_FILL"
        need(model["training_data_hash"] == canonical_hash(payload), code + ":INPUT_HASH")
        need(model["train_label_status_counts"] == dict(Counter(item["status"] for item in payload)),
             code + ":NO_FILL_RETENTION")
        for target in ("net", "gross"):
            metric = calibration[target]
            mse, zero_mse = number(metric["mse"]), number(metric["zero_mse"])
            need(mse >= ZERO and zero_mse >= ZERO, code + ":CALIBRATION_METRIC_DOMAIN")
            passed = mse == ZERO if zero_mse == ZERO else mse / zero_mse <= number(settings["calibration_maximum_mse_ratio"])
            if zero_mse > ZERO:
                near(metric["mse_ratio"], mse / zero_mse, code + ":CALIBRATION_RATIO", UNIT_TOL)
            need(metric["passed"] is passed and model[target]["status"] ==
                 ("READY" if passed else "CALIBRATION_FAILED"), code + ":CALIBRATION_GATE")
        training_rows += len(selected)
    ready = 0
    need(set(artifact["snapshots"]) == set(cohorts), "COMPLETE_FORECAST_HORIZON_MATRIX")
    for key, snapshots in artifact["snapshots"].items():
        need(set(snapshots) == {row["id"] for row in evaluated}, "COMPLETE_SNAPSHOT_ROW_COVERAGE")
        for row_id, snapshot in snapshots.items():
            row = by_id[row_id]
            code = "FORECAST:" + key + ":" + row_id
            need(snapshot["id"] == row_id and snapshot["decision_at"] == row["decision_at"] and
                 snapshot["feature_available_at"] == row["available_at"], code + ":FEATURE_BINDING")
            model_id = snapshot["model_id"]
            if model_id is None:
                need(all(snapshot[target]["status"] != "READY" for target in ("net", "gross")),
                     code + ":READY_WITHOUT_MODEL")
                continue
            need(model_id in models and models[model_id]["key"] == key, code + ":MODEL_BINDING")
            model = models[model_id]
            need(model["available_at"] <= row["decision_at"], code + ":FUTURE_MODEL")
            for target in ("net", "gross"):
                value = snapshot[target]
                if value["status"] != "READY":
                    continue
                payload = value["forecast"] if target == "net" else value
                need(model[target]["status"] == "READY" and payload["model_id"] == model_id and
                     payload["trained_through"] == model["trained_through"] and
                     payload["available_at"] == model["available_at"], code + ":MODEL_AGE_NOT_RESET")
                ttl = settings["maximum_model_and_latest_label_age_hours"] * HOUR
                need(row["decision_at"] - model["available_at"] <= ttl and
                     row["decision_at"] - model["trained_through"] <= ttl, code + ":STALE_MODEL_OR_LABEL")
                near(payload["normalizer_price"], number(row["reference_price"]), code + ":CAUSAL_NORMALIZER")
                if target == "net":
                    need(payload["basis_order"] == ["E", "T"], code + ":NET_BASIS_ORDER")
                    covariance(payload["covariance"], code + ":OUTCOME_COVARIANCE")
                    covariance(payload["mean_covariance"], code + ":MEAN_COVARIANCE")
                ready += 1
    return {"verified": True, "models": len(models), "training_rows_with_reuse": training_rows,
            "no_fill_training_rows_with_reuse": retained_no_fills, "ready_snapshots": ready,
            "training_and_calibration_clocks_bound": True, "training_input_hashes_rebuilt": True,
            "model_refits_executed": 0, "original_source_receipt_times_authenticated": False}


def audit_signal_forecast(signal: dict[str, Any], snapshot: dict[str, Any],
                          family: str, cost: dict[str, Any]) -> None:
    """Bind each registered target to its own saved forecast, without a fit."""
    metadata = signal["metadata"]
    if family in {"CONTINUATION", "REVERSAL"}:
        need("profit8Forecast" not in metadata, "NATIVE_CONTROL_UNEXPECTED_FORECAST")
        return
    actual = metadata["profit8Forecast"]
    if family == "GROSS":
        gross = snapshot["gross"]
        need(gross["status"] == "READY", "GROSS_SNAPSHOT_NOT_READY")
        price = gross["normalizer_price"]
        friction = (cost["spread_bps"] + 2 * cost["slippage_bps"]) / 10_000 + 2 * cost[
            "commission_usd_per_share_per_side"
        ] / price
        mean = gross["mean"] - friction
        expected = {
            "basis_order": ["E", "T"], "mean": [mean, mean],
            "covariance": [[gross["variance"]] * 2 for _ in range(2)],
            "mean_covariance": [[gross["mean_variance"]] * 2 for _ in range(2)],
            "normalizer_price": price, "trained_through": gross["trained_through"],
            "available_at": gross["available_at"], "model_id": gross["model_id"],
            "target": "GROSS_DEADLINE_MINUS_REGISTERED_VARIABLE_COST",
        }
    else:
        need(family in {"NET", "ROBUST"} and snapshot["net"]["status"] == "READY",
             "NET_SNAPSHOT_NOT_READY")
        expected = {**snapshot["net"]["forecast"], "target": "NET_NATIVE_POLICY_PAYOFF_BASIS"}
    need(actual == expected, "SIGNAL_FORECAST_TARGET_BINDING")


def verify(directory: Path, root: Path = ROOT) -> dict[str, Any]:
    directory, root = directory.resolve(), root.resolve()
    bindings = verify_bindings(directory, root)
    protocol, recipes = read(directory / "protocol.json"), read(directory / "recipes.json")
    need(isinstance(recipes, list) and len(recipes) == 10 and len({row["id"] for row in recipes}) == 10,
         "TEN_UNIQUE_REGISTERED_POLICIES")
    candidates = [row for row in recipes if row["role"] == "CANDIDATE"]
    controls = [row["id"] for row in recipes if row["role"] == "CONTROL"]
    need(len(candidates) == 6 and {row["family"] for row in candidates} == {"REVERSAL", "NET", "ROBUST"},
         "THREE_HYPOTHESES_SIX_RECIPES")
    need(len(controls) == 4 and controls == protocol["controls"], "FOUR_DISTINCT_CONTROLS")
    need(set(protocol["scenarios"]) == {"NOMINAL", "STRESS"}, "TWO_FROZEN_COST_SCENARIOS")
    dataset_path = safe_path(root, protocol["dataset"])
    dataset = read(dataset_path)
    need(protocol["dataset"] in read(directory / "source_bindings.json")["data"], "DATASET_NOT_BOUND")
    index = DatasetIndex(dataset)
    bundle, forecasts = read(directory / "signals.json"), read(directory / "forecasts.json.gz")
    rows = read(directory / "rows.json.gz")["rows"]
    teacher_artifacts, teacher_checks, accounts, artifact_hashes = {}, {}, {}, {}
    ids = [recipe["id"] for recipe in recipes]
    recipe_by_id = {recipe["id"]: recipe for recipe in recipes}
    teacher_signals = read(directory / "teacher_signals.json")["signals"]
    expected_teacher_ids = [signal["id"] for signal in teacher_signals]
    need(len(set(expected_teacher_ids)) == len(expected_teacher_ids), "DUPLICATE_TEACHER_PLAN")
    for signal in teacher_signals:
        index.audit_signal(signal)
    with localcontext() as context:
        context.prec = 50
        for scenario in ("NOMINAL", "STRESS"):
            teacher_path = directory / ("teachers_" + scenario + ".json.gz")
            teacher = read(teacher_path)
            need([label["signal_id"] for label in teacher["labels"]] == expected_teacher_ids,
                 "TEACHER_PLAN_COVERAGE:" + scenario)
            teacher_artifacts[scenario] = teacher
            teacher_checks[scenario] = audit_teachers(teacher, protocol, dataset, scenario, index=index)
            artifact_hashes[teacher_path.name] = sha(teacher_path)
            need(set(bundle["signals"][scenario]) == set(ids), "COMPLETE_SIGNAL_MATRIX:" + scenario)
            for recipe in ids:
                signals = bundle["signals"][scenario][recipe]
                need(len({signal["id"] for signal in signals}) == len(signals), "DUPLICATE_SIGNAL_ID")
                for signal in signals:
                    index.audit_signal(signal)
                    row_id = signal["metadata"]["profit8RowId"]
                    key = scenario + ":" + str(signal["metadata"]["roadmapHorizonHours"])
                    snapshot = forecasts["snapshots"][key][row_id]
                    audit_signal_forecast(signal, snapshot, recipe_by_id[recipe]["family"], protocol["scenarios"][scenario])
                path = directory / (scenario + "_" + recipe + ".json.gz")
                report = read(path)
                key = scenario + ":" + recipe
                accounts[key] = audit_report(report, protocol, dataset, key, index=index, teachers=teacher, signals=signals)
                artifact_hashes[path.name] = sha(path)
        forecast_check = audit_forecasts(forecasts, teacher_artifacts, rows, protocol, index)
    for name in ("protocol.json", "recipes.json", "signals.json", "forecasts.json.gz", "rows.json.gz", "teacher_signals.json"):
        artifact_hashes[name] = sha(directory / name)
    need(verify_bindings(directory, root) == bindings, "SOURCES_CHANGED_DURING_AUDIT")
    return {"schema": "HARPOON_PROFIT8_SEPARATE_AUDIT_1", "verified": True,
            "origin": "HISTORICAL_MODELED", "accounts": accounts, "teachers": teacher_checks,
            "forecasts": forecast_check, "bindings": bindings, "artifact_sha256": artifact_hashes,
            "dataset_clock": {"symbols": sorted(index.series), "bars": index.bars, "sessions": len(index.sessions)},
            "verifier_sha256": sha(Path(__file__)), "new_recipes": 0, "new_backtests": 0,
            "same_author_separate_implementation": True, "external_review_completed": False,
            "source_receipt_timing_authenticated": False, "real_fills_present": False,
            "financial_acceptance_allowed": False, "execution_allowed": False,
            "scope": "Retained accounting core plus independent Decimal cash-flow, causal planning and utility-unit checks; no economic acceptance."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.directory)
    except (AuditFailure, KeyError, TypeError, ValueError, OSError) as error:
        result = {"schema": "HARPOON_PROFIT8_SEPARATE_AUDIT_1", "verified": False,
                  "error": str(error), "error_type": type(error).__name__, "financial_acceptance_allowed": False,
                  "execution_allowed": False, "new_backtests": 0}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"verified": result["verified"], "accounts": len(result.get("accounts", {})),
                      **({"error": result["error"]} if "error" in result else {})}))
    if not result["verified"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
