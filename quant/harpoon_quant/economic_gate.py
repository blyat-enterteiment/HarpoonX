"""Offline economic gate for a *paired portfolio* experiment.

This module never fits, trades, changes a search counter or promotes a live model.
It can verify local integrity, not the authenticity of an exchange/broker or an
honest clock.  Financial inference remains conditional on the provenance supplied.
Synthetic regression fixtures can exercise every calculation without constituting
observations, independent validation, or evidence of a profitable strategy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from .core import digest, finite, timestamp

PROTOCOL_SCHEMA = "HARPOON_ECONOMIC_PROTOCOL_1"
INPUT_SCHEMA = "HARPOON_ECONOMIC_EVIDENCE_1"
REPORT_SCHEMA = "HARPOON_ECONOMIC_GATE_1"
REGISTRY_SCHEMA = "HARPOON_PREREGISTRATION_1"
POLICIES = ("C0", "RIDGE", "SVR")
# The already consumed historical HarpoonX search must never become zero merely
# because a different validator is used.  This is a project fact, not a statistical
# claim that 23 covers unknown, unrecorded research.
HISTORICAL_SEARCH_FLOOR = 23
MAX_BOOTSTRAP_REPETITIONS = 500_000
MAX_SESSIONS = 20_000
MAX_RESAMPLED_SESSION_VECTORS = 100_000_000
METRICS = ("svr_log_growth", "svr_minus_ridge", "svr_minus_c0")


def _need(condition: Any, code: str) -> None:
    if not condition:
        raise ValueError(code)


def _number(value: Any, name: str, *, nonnegative: bool = False) -> float:
    result = finite(value, name)
    _need(not nonnegative or result >= 0, "NEGATIVE_" + name)
    return result


def _integer(value: Any, name: str, low: int, high: int) -> int:
    _need(type(value) is int and low <= value <= high, "INVALID_" + name)
    return int(value)


def _hash(value: Any, name: str) -> str:
    _need(isinstance(value, str) and len(value) == 64, "INVALID_" + name)
    _need(all(c in "0123456789abcdef" for c in value), "INVALID_" + name)
    return value


def _equal(a: float, b: float, tolerance: float = 1e-7) -> bool:
    # Tolerance is in USD, plus a small relative allowance for JSON float export.
    return math.isclose(a, b, rel_tol=1e-11, abs_tol=tolerance)


def seal_protocol(protocol: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with a canonical hash.  A hash alone is not preregistration."""
    body = {k: v for k, v in protocol.items() if k != "protocol_hash"}
    return {**body, "protocol_hash": digest(body)}


def _read_registry(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    previous = "GENESIS"
    if not path.exists():
        return entries
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        _need(isinstance(entry, dict), "PREREGISTRY_ENTRY_SCHEMA")
        claimed = entry.get("record_hash")
        body = {k: v for k, v in entry.items() if k != "record_hash"}
        _need(entry.get("schema") == REGISTRY_SCHEMA, "PREREGISTRY_SCHEMA")
        _need(entry.get("sequence") == len(entries) + 1, "PREREGISTRY_SEQUENCE")
        _need(entry.get("previous_hash") == previous, "PREREGISTRY_CHAIN")
        _need(claimed == digest(body), "PREREGISTRY_HASH")
        timestamp(entry["registered_at"])
        _hash(entry["protocol_hash"], "REGISTERED_PROTOCOL_HASH")
        _integer(entry["total_attempts"], "REGISTERED_ATTEMPTS", HISTORICAL_SEARCH_FLOOR, 10_000)
        if entries:
            _need(entry["total_attempts"] >= entries[-1]["total_attempts"], "SEARCH_COUNTER_RESET")
            _need(timestamp(entry["registered_at"]) >= timestamp(entries[-1]["registered_at"]), "PREREGISTRY_CLOCK_REVERSED")
        previous = claimed
        entries.append(entry)
    return entries


def register_protocol(
    protocol: dict[str, Any],
    journal_path: str | Path,
    registered_at: str | None = None,
) -> dict[str, Any]:
    """Append a local preregistration; never edit a financial search journal.

    Real registrations use the system clock.  An explicit time is allowed only
    for an explicitly synthetic engineering fixture.  The receipt detects local
    alteration against a retained head hash; replacing the entire journal and
    its anchor coherently cannot be detected without an external trusted anchor.
    Concurrent writers use an exclusive lock file; a crash leaves a visible lock
    rather than silently creating two different histories.
    """
    _validate_protocol(protocol)
    if registered_at is not None:
        _need(protocol["data_scope"] == "SYNTHETIC_ENGINEERING_ONLY", "CLOCK_OVERRIDE_ONLY_SYNTHETIC")
    at = registered_at or datetime.now(UTC).isoformat()
    _need(timestamp(at) >= timestamp(protocol["created_at"]), "REGISTRATION_BEFORE_PROTOCOL")
    path = Path(journal_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name + ".lock")
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        entries = _read_registry(path)
        total = protocol["search"]["total_attempts"]
        if entries:
            _need(total >= entries[-1]["total_attempts"], "SEARCH_COUNTER_RESET")
            _need(timestamp(at) >= timestamp(entries[-1]["registered_at"]), "PREREGISTRY_CLOCK_REVERSED")
        _need(not any(e["protocol_id"] == protocol["protocol_id"] for e in entries), "PROTOCOL_ALREADY_REGISTERED")
        record = {
            "schema": REGISTRY_SCHEMA,
            "sequence": len(entries) + 1,
            "previous_hash": entries[-1]["record_hash"] if entries else "GENESIS",
            "protocol_id": protocol["protocol_id"],
            "protocol_hash": protocol["protocol_hash"],
            "registered_at": at,
            "total_attempts": total,
            "clock_evidence": "FIXTURE_CLOCK" if registered_at is not None else "LOCAL_SYSTEM_CLOCK",
            "external_time_attestation": None,
        }
        record["record_hash"] = digest(record)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True, allow_nan=False, separators=(",", ":")) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        return record
    finally:
        os.close(fd)
        lock.unlink()


def artifact_reference(path: str | Path, root: str | Path) -> dict[str, str]:
    """Bind a file by raw-byte SHA-256, without reading credentials or URLs."""
    target, base = Path(path).resolve(), Path(root).resolve()
    relative = target.relative_to(base)
    return {"path": relative.as_posix(), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}


def _artifact(ref: Any, root: Path, *, json_content: bool = True) -> Any:
    _need(isinstance(ref, dict), "ARTIFACT_REFERENCE_REQUIRED")
    _hash(ref.get("sha256"), "ARTIFACT_SHA256")
    _need(isinstance(ref.get("path"), str) and bool(ref["path"]), "ARTIFACT_PATH_REQUIRED")
    path = (root / ref["path"]).resolve()
    _need(path.is_relative_to(root.resolve()), "ARTIFACT_PATH_OUTSIDE_ROOT")
    _need(path.is_file(), "ARTIFACT_NOT_FOUND")
    raw = path.read_bytes()
    _need(hashlib.sha256(raw).hexdigest() == ref["sha256"], "ARTIFACT_HASH_MISMATCH")
    return json.loads(raw) if json_content else path


def _validate_protocol(p: dict[str, Any]) -> None:
    if isinstance(p, dict) and p.get("schema") == "HARPOON_ECONOMIC_PROTOCOL_2":
        from .economic_gate_v2 import validate_protocol
        validate_protocol(p)
        return
    _need(isinstance(p, dict) and p.get("schema") == PROTOCOL_SCHEMA, "PROTOCOL_SCHEMA")
    _need(p.get("protocol_hash") == seal_protocol(p)["protocol_hash"], "PROTOCOL_HASH_MISMATCH")
    _need(isinstance(p.get("protocol_id"), str) and bool(p["protocol_id"]), "PROTOCOL_ID")
    _need(p.get("research_only") is True, "OFFLINE_ONLY")
    _need(p.get("data_scope") in {"SYNTHETIC_ENGINEERING_ONLY", "HISTORICAL", "PAPER", "REAL"}, "DATA_SCOPE")
    _need(p.get("currency") == "USD" and p.get("equity_unit") == "USD", "FUNDS_UNITS")
    _need(_number(p.get("initial_equity_usd"), "INITIAL_EQUITY") > 0, "INITIAL_EQUITY")
    universe = p.get("universe")
    if not isinstance(universe, list) or not universe:
        raise ValueError("UNIVERSE_REQUIRED")
    _need(all(isinstance(s, str) and s for s in universe) and len(set(universe)) == len(universe), "UNIVERSE_DUPLICATE_OR_INVALID")
    for key in ("policy_hash", "risk_hash", "cost_hash", "code_hash"):
        _hash(p.get(key), key.upper())
    _need(0 < _number(p.get("horizon_hours"), "HORIZON") <= 72, "HORIZON_LIMIT")
    _need(0 < _number(p.get("max_drawdown_fraction"), "MAX_DRAWDOWN") < 1, "DRAWDOWN_LIMIT")
    _need(0 < _number(p.get("max_gross_exposure_fraction"), "MAX_EXPOSURE") <= 1, "UNLEVERAGED_SCOPE_ONLY")
    comparison = p["risk_comparison"]
    _need(isinstance(comparison, dict), "RISK_COMPARISON_SCHEMA")
    _need(1 <= _number(comparison.get("maximum_candidate_mean_exposure_ratio"), "EXPOSURE_COMPARISON_RATIO") <= 2, "EXPOSURE_COMPARISON_RATIO")
    _need(0 <= _number(comparison.get("maximum_candidate_mean_exposure_increment"), "EXPOSURE_COMPARISON_INCREMENT") <= 0.1, "EXPOSURE_COMPARISON_INCREMENT")
    _need(isinstance(comparison.get("justification"), str) and bool(comparison["justification"].strip()), "RISK_COMPARISON_JUSTIFICATION")
    _need(_number(p.get("minimum_delta_ridge_log_growth"), "MINIMUM_DELTA_RIDGE") > 0, "ECONOMIC_MINIMUM_REQUIRED")
    _number(p.get("minimum_delta_c0_log_growth"), "MINIMUM_DELTA_C0", nonnegative=True)
    period = p["period"]
    _need(isinstance(period, dict), "PERIOD_SCHEMA")
    times = [timestamp(period[k]) for k in ("train_end", "validation_start", "validation_end", "test_start", "test_end")]
    _need(times[0] < times[1] <= times[2] < times[3] < times[4], "TEMPORAL_PARTITION_OVERLAP")
    sessions = p.get("evaluation_sessions")
    _need(isinstance(sessions, list) and 1 <= len(sessions) <= MAX_SESSIONS, "EVALUATION_CALENDAR_REQUIRED")
    session_ids: set[str] = set()
    previous_end = times[3]
    for session in p["evaluation_sessions"]:
        _need(isinstance(session["session_id"], str) and session["session_id"] not in session_ids, "EVALUATION_CALENDAR_DUPLICATE")
        start, end = timestamp(session["start_at"]), timestamp(session["end_at"])
        _need(previous_end <= start < end <= times[4], "EVALUATION_CALENDAR_ORDER")
        session_ids.add(session["session_id"])
        previous_end = end
    timestamp(p["created_at"])
    wf = p["walk_forward"]
    _need(isinstance(wf, dict), "WALK_FORWARD_SCHEMA")
    _need(wf.get("selection_uses_final_test") is False, "FINAL_TEST_USED_FOR_SELECTION")
    _integer(wf.get("purge_sessions"), "PURGE_SESSIONS", 0, MAX_SESSIONS)
    _integer(wf.get("embargo_sessions"), "EMBARGO_SESSIONS", 0, MAX_SESSIONS)
    _need(isinstance(wf.get("justification"), str) and bool(wf["justification"].strip()), "WALK_FORWARD_JUSTIFICATION")
    dep = p["dependence"]
    _need(isinstance(dep, dict), "DEPENDENCE_SCHEMA")
    _need(dep.get("method") == "CIRCULAR_MOVING_BLOCK" and dep.get("unit") == "PORTFOLIO_SESSION", "DEPENDENCE_METHOD")
    lengths = dep.get("block_lengths")
    _need(isinstance(lengths, list) and 1 <= len(lengths) <= 4, "BLOCK_LENGTHS")
    _need(len(lengths) == len(set(lengths)), "DUPLICATE_BLOCK_LENGTH")
    for length in lengths:
        _integer(length, "BLOCK_LENGTH", 1, MAX_SESSIONS)
    horizon = _integer(dep.get("dependency_horizon_sessions"), "DEPENDENCY_HORIZON", 1, MAX_SESSIONS)
    _need(min(lengths) >= horizon, "BLOCK_SHORTER_THAN_DEPENDENCY")
    _need(wf["purge_sessions"] >= horizon and wf["embargo_sessions"] >= horizon, "PURGE_EMBARGO_SHORTER_THAN_DEPENDENCY")
    _integer(dep.get("minimum_sessions"), "MINIMUM_SESSIONS", 2, MAX_SESSIONS)
    _integer(dep.get("minimum_complete_blocks"), "MINIMUM_BLOCKS", 2, MAX_SESSIONS)
    _need(isinstance(dep.get("justification"), str) and bool(dep["justification"].strip()), "DEPENDENCE_JUSTIFICATION")
    stat = p["statistics"]
    _need(isinstance(stat, dict), "STATISTICS_SCHEMA")
    _need(0 < _number(stat.get("family_alpha"), "FAMILY_ALPHA") <= 0.10, "FAMILY_ALPHA")
    _integer(stat.get("bootstrap_repetitions"), "BOOTSTRAP_REPETITIONS", 100, MAX_BOOTSTRAP_REPETITIONS)
    _integer(stat.get("seed"), "BOOTSTRAP_SEED", 0, 2**32 - 1)
    _integer(stat.get("minimum_tail_draws"), "MINIMUM_TAIL_DRAWS", 20, 1000)
    search = p["search"]
    _need(isinstance(search, dict), "SEARCH_SCHEMA")
    _integer(search.get("total_attempts"), "SEARCH_ATTEMPTS", HISTORICAL_SEARCH_FLOOR, 10_000)
    _need(search.get("historical_attempts") == HISTORICAL_SEARCH_FLOOR, "HISTORICAL_SEARCH_COUNTER_CHANGED")
    _need(search.get("counter_reset") is False, "SEARCH_COUNTER_RESET")


def _preregistration(p: dict[str, Any], data: dict[str, Any], root: Path) -> dict[str, Any]:
    ref = data["preregistration"]
    path = _artifact(ref["journal"], root, json_content=False)
    entries = _read_registry(path)
    matching = [e for e in entries if e["protocol_hash"] == p["protocol_hash"]]
    _need(len(matching) == 1, "PREREGISTRATION_MISSING_OR_DUPLICATE")
    record = matching[0]
    _need(record["record_hash"] == ref.get("record_hash"), "PREREGISTRATION_ANCHOR_MISMATCH")
    _need(record["protocol_id"] == p["protocol_id"], "PREREGISTRATION_ID_MISMATCH")
    _need(record["total_attempts"] == p["search"]["total_attempts"], "PREREGISTRATION_ATTEMPT_MISMATCH")
    first_access = timestamp(data["provenance"]["first_final_data_access_at"])
    _need(timestamp(record["registered_at"]) <= first_access, "PROTOCOL_AFTER_OBSERVATIONS")
    _need(first_access <= timestamp(data["generated_at"]), "OBSERVATIONS_AFTER_REPORT")
    _need(timestamp(record["registered_at"]) >= timestamp(p["created_at"]), "REGISTRATION_BEFORE_PROTOCOL")
    _need(data["provenance"].get("prior_final_test_uses") == [], "FINAL_TEST_ALREADY_CONSUMED")
    history = _artifact(data["search_history"], root)
    _need(history.get("schema") == "HARPOON_SEARCH_HISTORY_1", "SEARCH_HISTORY_SCHEMA")
    _need(history.get("historical_attempts") == HISTORICAL_SEARCH_FLOOR, "SEARCH_COUNTER_RESET")
    attempts = history.get("new_attempts")
    _need(isinstance(attempts, list), "SEARCH_HISTORY_ATTEMPTS")
    ids = [a["attempt_id"] for a in attempts]
    _need(len(ids) == len(set(ids)), "DUPLICATE_ATTEMPT_ID")
    _need(history["historical_attempts"] + len(attempts) == p["search"]["total_attempts"], "SEARCH_TOTAL_MISMATCH")
    _hash(history.get("historical_manifest_sha256"), "HISTORICAL_MANIFEST_HASH")
    _need(timestamp(history["known_through"]) >= timestamp(record["registered_at"]), "SEARCH_HISTORY_STALE")
    _need(timestamp(history["known_through"]) <= timestamp(data["generated_at"]), "SEARCH_HISTORY_FROM_FUTURE")
    # A local fixture may cite a historical count but cannot authenticate it.
    return {
        "verified_local_chain": True,
        "record_hash": record["record_hash"],
        "registered_at": record["registered_at"],
        "clock_evidence": record["clock_evidence"],
        "external_attestation": False,
        "total_attempts": p["search"]["total_attempts"],
        "known_limit": "Coherent replacement of journal, hashes and clock claims needs an external anchor to detect.",
    }


def _curves(p: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    policies = data["policies"]
    _need(isinstance(policies, dict) and set(policies) == set(POLICIES), "THREE_PAIRED_POLICIES_REQUIRED")
    result: dict[str, Any] = {}
    common_sessions: list[str] | None = None
    common_times: list[tuple[str, str]] | None = None
    common_flows: list[float] | None = None
    for policy in POLICIES:
        item = policies[policy]
        _need(isinstance(item, dict), "POLICY_CURVE_SCHEMA")
        _need(item.get("currency") == p["currency"] and item.get("equity_unit") == p["equity_unit"], "FUNDS_UNITS_" + policy)
        _need(item.get("universe") == p["universe"], "UNIVERSE_BINDING_" + policy)
        for key in ("policy_hash", "risk_hash", "cost_hash", "code_hash"):
            _need(item.get(key) == p[key], key.upper() + "_BINDING_" + policy)
        _need(item.get("valuation") == "EXECUTABLE_SIDE_NET_OF_LIABILITIES", "VALUATION_METHOD_" + policy)
        _need(item.get("all_costs_in_equity") is True, "COSTS_NOT_INCLUDED_" + policy)
        _need(item.get("initial_positions") == [], "INITIAL_INVENTORY_SCOPE_REQUIRES_FLAT")
        curve = item["curve"]
        _need(isinstance(curve, list) and 1 <= len(curve) <= MAX_SESSIONS, "CURVE_LENGTH_" + policy)
        last_equity = p["initial_equity_usd"]
        last_end = timestamp(p["period"]["test_start"])
        logs: list[float] = []
        session_ids: list[str] = []
        times: list[tuple[str, str]] = []
        flows: list[float] = []
        fees = 0.0
        operating = 0.0
        exposure = 0.0
        exposure_sum = 0.0
        wealth = peak = 1.0
        drawdown = 0.0
        insolvency = False
        for row in curve:
            _need(isinstance(row, dict), "CURVE_ROW_SCHEMA")
            sid = row["session_id"]
            _need(isinstance(sid, str) and bool(sid) and sid not in session_ids, "SESSION_ID_DUPLICATE_" + policy)
            start, end = timestamp(row["start_at"]), timestamp(row["end_at"])
            _need(last_end <= start < end <= timestamp(p["period"]["test_end"]), "CURVE_TIME_ORDER_" + policy)
            _need(timestamp(row["data_available_at"]) <= end, "CURVE_FUTURE_DATA_" + policy)
            _hash(row.get("source_hash"), "CURVE_SOURCE_HASH")
            e0 = _number(row.get("equity_start_usd"), "EQUITY_START")
            before = _number(row.get("equity_pre_flow_usd"), "EQUITY_PRE_FLOW")
            flow = _number(row.get("external_flow_usd"), "EXTERNAL_FLOW")
            e1 = _number(row.get("equity_end_usd"), "EQUITY_END")
            gross = _number(row.get("gross_marked_pnl_usd"), "GROSS_MARKED_PNL")
            fee = _number(row.get("fees_in_equity_usd"), "FEES", nonnegative=True)
            cost = _number(row.get("operating_costs_in_equity_usd"), "OPERATING_COSTS", nonnegative=True)
            gross_exposure = _number(row.get("gross_exposure_fraction"), "EXPOSURE", nonnegative=True)
            _need(_equal(e0, last_equity), "CAPITAL_RESET_OR_DISCONTINUITY_" + policy)
            _need(_equal(e1 - e0 - flow, gross - fee - cost), "FLOW_COST_PNL_RECONCILIATION_" + policy)
            if flow == 0:
                _need(_equal(before, e0), "UNNEEDED_PREFLOW_MARK_" + policy)
            else:
                _need(row.get("pre_flow_mark_source_hash") is not None, "PREFLOW_MARK_REQUIRED_" + policy)
                _hash(row["pre_flow_mark_source_hash"], "PREFLOW_MARK_HASH")
                _need(row.get("flow_count") == 1, "MULTIPLE_FLOWS_REQUIRE_SEGMENTED_CURVE")
                _need(start <= timestamp(row["flow_at"]) <= end, "FLOW_TIME_OUTSIDE_INTERVAL")
            if min(e0, before, before + flow, e1) <= 0:
                insolvency = True
                row_return = None
                drawdown = 1.0
            else:
                row_return = (before / e0) * (e1 / (before + flow)) - 1.0
                logs.append(math.log1p(row_return))
                wealth *= 1.0 + row_return
                peak = max(peak, wealth)
                drawdown = max(drawdown, 1.0 - wealth / peak)
            if "return_net" in row:
                _need(row_return is not None and _equal(_number(row["return_net"], "CLAIMED_RETURN"), row_return, 1e-12), "RETURN_RECONCILIATION_" + policy)
            if policy == "C0":
                _need(gross_exposure == 0, "C0_HAS_RISK_EXPOSURE")
            last_equity, last_end = e1, end
            exposure = max(exposure, gross_exposure)
            exposure_sum += gross_exposure
            fees += fee
            operating += cost
            session_ids.append(sid)
            times.append((row["start_at"], row["end_at"]))
            flows.append(flow)
        terminal = item["terminal"]
        _need(isinstance(terminal, dict), "TERMINAL_SCHEMA")
        _need(timestamp(terminal["at"]) == last_end, "TERMINAL_TIME_MISMATCH_" + policy)
        cash = _number(terminal.get("cash_usd"), "TERMINAL_CASH")
        payable = _number(terminal.get("payables_usd"), "TERMINAL_PAYABLES", nonnegative=True)
        inventory = terminal["positions"]
        _need(isinstance(inventory, list), "TERMINAL_INVENTORY_REQUIRED")
        symbols: list[str] = []
        inventory_value = 0.0
        for position in inventory:
            symbol = position["symbol"]
            _need(symbol in p["universe"] and symbol not in symbols, "TERMINAL_POSITION_UNIVERSE")
            symbols.append(symbol)
            quantity = _number(position.get("quantity"), "TERMINAL_QUANTITY", nonnegative=True)
            _need(_number(position.get("mark_usd"), "TERMINAL_MARK") > 0, "TERMINAL_MARK")
            _need(position.get("valuation_side") == "BID", "TERMINAL_MARK_SIDE")
            _need(timestamp(position["known_at"]) <= last_end, "TERMINAL_FUTURE_MARK")
            liability = _number(position.get("liability_usd"), "TERMINAL_LIABILITY", nonnegative=True)
            inventory_value += quantity * position["mark_usd"] - liability
        _need(_equal(cash + inventory_value - payable, last_equity), "TERMINAL_INVENTORY_RECONCILIATION_" + policy)
        _need(cash >= 0 or insolvency, "TERMINAL_BORROWING_OUTSIDE_SCOPE_" + policy)
        if policy == "C0":
            _need(not inventory, "C0_HAS_TERMINAL_INVENTORY")
        if common_sessions is None:
            common_sessions, common_times, common_flows = session_ids, times, flows
        else:
            _need(session_ids == common_sessions, "PAIRED_SESSION_IDS_MISMATCH")
            _need(times == common_times, "PAIRED_SESSION_TIMES_MISMATCH")
            _need(flows == common_flows, "PAIRED_CAPITAL_FLOWS_MISMATCH")
        result[policy] = {
            "sessions": session_ids,
            "log_returns": logs,
            "initial_equity_usd": p["initial_equity_usd"],
            "final_equity_usd": last_equity,
            "external_flows_usd": sum(flows),
            "net_pnl_usd": last_equity - p["initial_equity_usd"] - sum(flows),
            "execution_fees_in_equity_usd": fees,
            "operating_costs_in_equity_usd": operating,
            "mean_log_growth_per_session": None if insolvency else float(np.mean(logs)),
            "geometric_growth_per_session": None if insolvency else math.expm1(float(np.mean(logs))),
            "drawdown_fraction_at_observation_resolution": drawdown,
            "maximum_observed_gross_exposure_fraction": exposure,
            "mean_observed_gross_exposure_fraction": exposure_sum / len(curve),
            "insolvency": insolvency,
            "curve_hash": digest(curve),
            "terminal_hash": digest(terminal),
        }
    _need(common_sessions == [row["session_id"] for row in p["evaluation_sessions"]], "PREREGISTERED_SESSIONS_MISMATCH")
    _need(common_times == [(row["start_at"], row["end_at"]) for row in p["evaluation_sessions"]], "PREREGISTERED_SESSION_TIMES_MISMATCH")
    return result


def paired_block_bootstrap(
    log_returns: dict[str, list[float]], protocol: dict[str, Any]
) -> dict[str, Any]:
    """Resample contiguous blocks of *joint portfolio-session vectors*.

    Percentile lower bounds are approximate under weak stationarity and adequate
    dependence coverage.  Bonferroni allocates family alpha over registered
    attempts, block sizes and three endpoints; it does not repair a biased sample
    or prove finite-sample bootstrap coverage.  Independent trades are not an
    assumption.  Degenerate comparisons are inconclusive, never zero-width proof.
    """
    arrays = {k: np.asarray(log_returns[k], dtype=float) for k in POLICIES}
    n = len(arrays["SVR"])
    _need(n > 0 and all(a.ndim == 1 and len(a) == n and np.all(np.isfinite(a)) for a in arrays.values()), "PAIRED_FINITE_ARRAYS")
    dep, stat = protocol["dependence"], protocol["statistics"]
    lengths = dep["block_lengths"]
    attempts = protocol["search"]["total_attempts"]
    adjusted_alpha = stat["family_alpha"] / (attempts * len(lengths) * len(METRICS))
    repetitions = stat["bootstrap_repetitions"]
    reasons: list[str] = []
    if n < dep["minimum_sessions"]:
        reasons.append("SESSION_SAMPLE_BELOW_PREREGISTERED_MINIMUM")
    if any(n // length < dep["minimum_complete_blocks"] for length in lengths):
        reasons.append("DEPENDENCE_BLOCK_COUNT_INSUFFICIENT")
    if repetitions * adjusted_alpha < stat["minimum_tail_draws"]:
        reasons.append("BOOTSTRAP_TAIL_RESOLUTION_INSUFFICIENT")
    if repetitions * n * len(lengths) > MAX_RESAMPLED_SESSION_VECTORS:
        reasons.append("BOOTSTRAP_COMPUTE_BUDGET_EXCEEDED")
    matrix = np.column_stack((arrays["SVR"], arrays["SVR"] - arrays["RIDGE"], arrays["SVR"] - arrays["C0"]))
    if np.any(np.ptp(matrix, axis=0) <= 1e-14):
        reasons.append("DEGENERATE_ENDPOINT_VARIANCE")
    output: dict[str, Any] = {
        "method": "PAIRED_CIRCULAR_MOVING_BLOCK_PERCENTILE",
        "resampling_unit": "JOINT_PORTFOLIO_SESSION",
        "confidence_family_proposed": 1 - stat["family_alpha"],
        "bonferroni_family_size": attempts * len(lengths) * len(METRICS),
        "one_sided_alpha_per_endpoint": adjusted_alpha,
        "repetitions": repetitions,
        "observed_sessions": n,
        "effective_independent_observations": None,
        "effective_sample_null_reason": "Block count is a dependence diagnostic, not an estimate of independent observations.",
        "tail_draws_expected": repetitions * adjusted_alpha,
        "point_estimates": dict(zip(METRICS, matrix.mean(axis=0).tolist(), strict=True)),
        "status": "INCONCLUSIVE" if reasons else "COMPUTED",
        "reasons": reasons,
        "blocks": [],
        "coverage_guarantee": False,
        "assumptions": ["Weak stationarity of the evaluated session process", "Registered blocks cover material temporal dependence", "Recorded search family covers the evaluated research", "Source observations and accounting are valid"],
    }
    if reasons:
        return output
    rng = np.random.default_rng(stat["seed"])
    for length in lengths:
        blocks = math.ceil(n / length)
        means = np.empty((repetitions, len(METRICS)), dtype=float)
        # Bound the working allocation even for the maximum admitted session count.
        batch_size = max(1, min(256, 500_000 // n))
        offsets = np.arange(length)
        for first in range(0, repetitions, batch_size):
            count = min(batch_size, repetitions - first)
            starts = rng.integers(0, n, size=(count, blocks))
            indices = ((starts[:, :, None] + offsets) % n).reshape(count, -1)[:, :n]
            means[first:first + count] = matrix[indices].mean(axis=1)
        lower = np.quantile(means, adjusted_alpha, axis=0, method="linear")
        upper = np.quantile(means, 1 - adjusted_alpha, axis=0, method="linear")
        output["blocks"].append({
            "length_sessions": length,
            "complete_blocks_observed": n // length,
            "lower_one_sided": dict(zip(METRICS, lower.tolist(), strict=True)),
            "upper_diagnostic": dict(zip(METRICS, upper.tolist(), strict=True)),
            "standard_error_of_bootstrap_means": dict(zip(METRICS, means.std(axis=0, ddof=1).tolist(), strict=True)),
        })
    return output


def _parity(data: dict[str, Any], root: Path, p: dict[str, Any]) -> dict[str, Any]:
    parity = _artifact(data["parity_receipt"], root)
    _need(parity.get("schema") == "HARPOON_COORDINATOR_REPLAY_1", "PARITY_RECEIPT_SCHEMA")
    reexecuted = False
    # JS and Python do not serialize every IEEE-754 number identically.  For the
    # actual coordinator use its fixed, local verifier and canonicalizer, rather
    # than accidentally accepting/rejecting a receipt with a different format.
    # The caller cannot choose executable code; only JSON input under root.
    if "coordinator_input" in data:
        request_path = _artifact(data["coordinator_input"], root, json_content=False)
        receipt_path = _artifact(data["parity_receipt"], root, json_content=False)
        app = Path(__file__).resolve().parents[2]
        verifier = app / "tools" / "coordinator_replay.cjs"
        _need(verifier.is_file(), "COORDINATOR_VERIFIER_MISSING")
        script = "const fs=require('node:fs');const m=require(process.argv[1]);m.verifyReport(JSON.parse(fs.readFileSync(process.argv[2],'utf8')),JSON.parse(fs.readFileSync(process.argv[3],'utf8'))).then(x=>process.stdout.write(JSON.stringify(x))).catch(e=>{process.stderr.write(String(e));process.exit(2)});"
        try:
            completed = subprocess.run(["node", "-e", script, str(verifier), str(request_path), str(receipt_path)], cwd=app, text=True, capture_output=True, timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError("COORDINATOR_VERIFICATION_UNAVAILABLE") from exc
        _need(completed.returncode == 0, "COORDINATOR_REEXECUTION_FAILED")
        verified = json.loads(completed.stdout)
        _need(verified.get("schema") == "HARPOON_COORDINATOR_REPLAY_VERIFICATION_1", "COORDINATOR_VERIFICATION_SCHEMA")
        _need(verified.get("verified") is True and verified.get("mismatches") == [], "COORDINATOR_REEXECUTION_MISMATCH")
        _need(verified.get("input_hash") == parity.get("input_hash"), "COORDINATOR_VERIFICATION_INPUT_BINDING")
        _need(verified.get("expected_artifact_hash") == parity.get("artifact_hash") == verified.get("observed_artifact_hash"), "COORDINATOR_VERIFICATION_REPORT_BINDING")
        reexecuted = True
    else:
        _need(parity.get("artifact_hash") == digest({k: v for k, v in parity.items() if k != "artifact_hash"}), "PARITY_CANONICAL_HASH")
    _need(parity.get("input_hash") == data.get("coordinator_input_hash"), "PARITY_INPUT_BINDING")
    checks = parity.get("checks")
    _need(isinstance(checks, list) and bool(checks), "PARITY_CHECKS_MISSING")
    ids: list[str] = []
    for check in checks:
        _need(isinstance(check.get("id"), str) and check["id"] not in ids, "PARITY_CHECK_ID")
        ids.append(check["id"])
        _hash(check.get("expected_hash"), "PARITY_EXPECTED_HASH")
        _hash(check.get("observed_hash"), "PARITY_OBSERVED_HASH")
        _need(check["expected_hash"] == check["observed_hash"] and check.get("passed") is True and check.get("mismatches") == [], "PARITY_CHECK_FAILED")
    source_hashes = parity.get("source_hashes")
    _need(isinstance(source_hashes, dict) and len(source_hashes) > 0, "PARITY_SOURCE_HASHES_MISSING")
    _need(parity.get("scope") is not None, "PARITY_SCOPE_MISSING")
    # Hash actual source files, not only claimed hashes within a receipt.
    refs = data.get("parity_source_files", {})
    _need(isinstance(refs, dict) and set(source_hashes).issubset(refs), "PARITY_SOURCE_ARTIFACTS_MISSING")
    for name, expected in source_hashes.items():
        _artifact(refs[name], root, json_content=False)
        _need(refs[name]["sha256"] == expected, "PARITY_SOURCE_BINDING")
    binding_verified = all(parity.get("economic_bindings", {}).get(key) == p[key] for key in ("policy_hash", "risk_hash", "cost_hash", "code_hash"))
    result = parity.get("result", {})
    covered = [result["candidate"]] if result.get("candidate") in POLICIES else []
    # A single native-C0 receipt cannot certify Ridge/SVR predictor parity.  A
    # future paired replay must actually emit/reexecute all three results.
    paired_results = parity.get("paired_results", {})
    if isinstance(paired_results, dict):
        covered = sorted(set(covered) | (set(paired_results) & set(POLICIES)))
    paired_coverage = set(covered) == set(POLICIES)
    return {
        "receipt_integrity_verified": True,
        "real_coordinator_reexecuted": reexecuted,
        "economic_bindings_verified": binding_verified,
        "checks_verified": ids,
        "scope": parity["scope"],
        "covered_policies": covered,
        "complete_paired_policy_coverage": paired_coverage,
        "receipt_predictor_parity_verified_within_its_scope": parity.get("predictor_parity_verified") is True,
        "predictor_parity_verified": parity.get("predictor_parity_verified") is True and paired_coverage,
        "financial_acceptance_allowed_by_receipt": parity.get("financial_acceptance_allowed") is True,
        "execution_origin": parity.get("execution_origin"),
        "policy_parity_verified": parity.get("policy_parity_verified") is True,
        "external_validation": False,
    }


def _observational_artifacts(data: dict[str, Any], root: Path, p: dict[str, Any], curves: dict[str, Any]) -> dict[str, Any]:
    """Verify evidence contents and bindings; never certify provider identity.

    This normalized receipt is an integration boundary.  A broker/replay adapter
    must export the exact curves/terminal positions and its raw source artefacts.
    A bool such as `verified:true` or `parity:true` is deliberately insufficient.
    """
    receipts = data["observational_artifacts"]
    raw = _artifact(receipts["observed_prices"], root)
    _need(raw.get("schema") == "HARPOON_OBSERVATION_EXPORT_1", "OBSERVATION_EXPORT_SCHEMA")
    _need(raw.get("origin") == "OBSERVED", "OBSERVATIONS_NOT_OBSERVED")
    _need(isinstance(raw.get("provider"), str) and bool(raw["provider"]), "OBSERVATION_PROVIDER_MISSING")
    _need(raw.get("availability") == "OBSERVED_RECEIPT_TIMESTAMPS", "OBSERVATION_AVAILABILITY_NOT_OBSERVED")
    records = raw.get("records")
    _need(isinstance(records, list) and len(records) > 0, "OBSERVATION_RECORDS_MISSING")
    ids: set[str] = set()
    symbols: set[str] = set()
    for record in records:
        _need(record["event_id"] not in ids, "OBSERVATION_DUPLICATE_EVENT")
        ids.add(record["event_id"])
        _need(record["symbol"] in p["universe"], "OBSERVATION_UNIVERSE")
        symbols.add(record["symbol"])
        _need(timestamp(record["market_at"]) <= timestamp(record["received_at"]), "OBSERVATION_CLOCK_INCONSISTENCY")
        bid = _number(record["bid"], "OBSERVATION_BID")
        ask = _number(record["ask"], "OBSERVATION_ASK")
        _need(0 < bid <= ask, "OBSERVATION_QUOTE_INVALID")
    _need(symbols == set(p["universe"]), "OBSERVATION_UNIVERSE_INCOMPLETE")
    accounts = receipts["accounting"]
    for policy in POLICIES:
        receipt = _artifact(accounts[policy], root)
        _need(receipt.get("schema") == "HARPOON_ECONOMIC_ACCOUNT_RECEIPT_1", "ACCOUNT_RECEIPT_SCHEMA")
        _need(receipt.get("policy") == policy, "ACCOUNT_RECEIPT_POLICY")
        _need(receipt.get("curve_hash") == curves[policy]["curve_hash"], "ACCOUNT_RECEIPT_CURVE_BINDING")
        _need(receipt.get("terminal_hash") == curves[policy]["terminal_hash"], "ACCOUNT_RECEIPT_TERMINAL_BINDING")
        _need(receipt.get("cost_hash") == p["cost_hash"], "ACCOUNT_RECEIPT_COST_BINDING")
        _need(receipt.get("reconciliation_errors") == [], "ACCOUNT_RECONCILIATION_ERRORS")
        _need(receipt.get("origin") in {"HISTORICAL", "PAPER", "REAL"}, "ACCOUNT_RECEIPT_SYNTHETIC")
        underlying = _artifact(receipt["underlying_ledger"], root)
        _need(underlying.get("schema") == "HARPOON_NET_LEDGER_1", "UNDERLYING_LEDGER_REQUIRED")
        _need(underlying.get("blockers") == [], "UNDERLYING_LEDGER_BLOCKED")
        _need(underlying.get("reconciliation", {}).get("status") == "RECONCILED", "UNDERLYING_LEDGER_NOT_RECONCILED")
        _need(receipt.get("observed_prices_sha256") == receipts["observed_prices"]["sha256"], "ACCOUNT_PRICE_SOURCE_BINDING")
        trace = _artifact(receipt["execution_trace"], root)
        _need(trace.get("schema") == "HARPOON_EXECUTION_TRACE_1", "EXECUTION_TRACE_SCHEMA")
        _need(trace.get("origin") in {"MODELED_FROM_OBSERVED", "PAPER", "REAL"}, "EXECUTION_TRACE_ORIGIN")
        _need(trace.get("policy") == policy, "EXECUTION_TRACE_POLICY")
        _need(trace.get("curve_hash") == curves[policy]["curve_hash"], "EXECUTION_TRACE_CURVE_BINDING")
        _need(trace.get("coverage") == "ALL_SIGNALS_ORDERS_FILLS_CANCELS_DISCARDS", "EXECUTION_TRACE_COVERAGE")
        _need(isinstance(trace.get("events"), list), "EXECUTION_EVENTS_MISSING")
        if policy != "C0":
            _need(len(trace["events"]) > 0, "EXECUTION_EVENTS_EMPTY")
    return {"artifact_bindings_verified": True, "observed_price_records": len(records), "provider_claim": raw["provider"], "provider_authenticity": "NOT_INDEPENDENTLY_VERIFIED"}


def _report_base() -> dict[str, Any]:
    return {
        "schema": REPORT_SCHEMA,
        "research_only": True,
        "execution_allowed": False,
        "liveApproved": False,
        "financial_approval": False,
        "financial_acceptance_allowed": False,
        "candidate_for_forward_validation": False,
        "dictamen": "VENTAJA_NO_DEMOSTRADA",
        "software_validators": {"status": "NOT_RUN", "errors": []},
        "preregistration": None,
        "parity": None,
        "observational_artifacts": None,
        "policies": None,
        "statistics": None,
        "financial_blockers": [],
        "limitations": [
            "Software verification is not evidence of profitability.",
            "File hashes verify local integrity; they do not authenticate a broker, a clock, or a complete research history.",
            "Drawdown and exposure are bounded only at the supplied observation resolution; intraperiod gaps need their own risk evidence.",
            "Bootstrap inference is approximate, assumes suitable dependence coverage, and does not guarantee future returns.",
            "No LIVE promotion, model fitting, new financial search attempt, or external order is performed.",
        ],
    }


def evaluate_gate(
    protocol: dict[str, Any],
    evidence: dict[str, Any],
    *,
    artifact_root: str | Path | None = None,
) -> dict[str, Any]:
    """Return deterministic diagnostics and a non-executing research verdict.

    Missing evidence is inconclusive.  Observable insolvency, excessive risk or
    failure of the preregistered economic minimum rejects the candidate.  A
    favorable synthetic calculation can never become a financial candidate.
    """
    if isinstance(protocol, dict) and protocol.get("schema") == "HARPOON_ECONOMIC_PROTOCOL_2":
        from .economic_gate_v2 import evaluate
        return evaluate(protocol, evidence, Path(artifact_root or ".").resolve())
    report = _report_base()
    root = Path(artifact_root or ".").resolve()
    try:
        _need(isinstance(protocol, dict) and isinstance(evidence, dict), "PROTOCOL_AND_EVIDENCE_MUST_BE_OBJECTS")
        report["protocol_hash"] = digest(protocol)
        report["input_hash"] = digest(evidence)
        _validate_protocol(protocol)
        report["protocol_hash"] = protocol["protocol_hash"]
        _need(evidence.get("schema") == INPUT_SCHEMA, "EVIDENCE_SCHEMA")
        _need(evidence.get("protocol_hash") == protocol["protocol_hash"], "INPUT_PROTOCOL_BINDING")
        _need(evidence.get("execution_allowed") is False and evidence.get("liveApproved") is False, "EVIDENCE_MUST_BE_OFFLINE")
        timestamp(evidence["generated_at"])
        report["preregistration"] = _preregistration(protocol, evidence, root)
        curves = _curves(protocol, evidence)
        report["policies"] = {k: {name: v for name, v in row.items() if name not in {"sessions", "log_returns"}} for k, row in curves.items()}
        report["software_validators"] = {"status": "PASS", "errors": [], "scope": "Protocol integrity, paired continuous account arithmetic, units, chronology and terminal inventory"}
    except (ValueError, TypeError, KeyError, OSError, OverflowError, AttributeError) as exc:
        report["software_validators"] = {"status": "BLOCKED", "errors": [str(exc)]}
        report["financial_blockers"].append("INPUT_OR_ACCOUNTING_NOT_VERIFIED")
        report["artifact_hash"] = digest(report)
        return report

    provenance = evidence.get("provenance", {})
    if protocol["data_scope"] == "SYNTHETIC_ENGINEERING_ONLY" or provenance.get("data_origin") == "SYNTHETIC_ENGINEERING_ONLY":
        report["financial_blockers"].append("SYNTHETIC_IS_NOT_FINANCIAL_EVIDENCE")
    if provenance.get("data_origin") != protocol["data_scope"]:
        report["financial_blockers"].append("PROVENANCE_SCOPE_MISMATCH")
    if provenance.get("price_origin") != "OBSERVED":
        report["financial_blockers"].append("OBSERVED_PRICES_REQUIRED")
    if provenance.get("availability") != "OBSERVED_RECEIPT_TIMESTAMPS":
        report["financial_blockers"].append("OBSERVED_AVAILABILITY_REQUIRED")
    try:
        report["parity"] = _parity(evidence, root, protocol)
        for key, code in (("real_coordinator_reexecuted", "REAL_COORDINATOR_NOT_REEXECUTED"), ("economic_bindings_verified", "PARITY_ECONOMIC_BINDINGS_NOT_VERIFIED"), ("complete_paired_policy_coverage", "PAIRED_POLICY_PARITY_INCOMPLETE"), ("policy_parity_verified", "POLICY_PARITY_NOT_VERIFIED"), ("predictor_parity_verified", "PREDICTOR_PARITY_NOT_VERIFIED"), ("financial_acceptance_allowed_by_receipt", "PARITY_RECEIPT_NOT_FINANCIALLY_ELIGIBLE")):
            if report["parity"][key] is not True:
                report["financial_blockers"].append(code)
    except (ValueError, TypeError, KeyError, OSError, AttributeError) as exc:
        report["financial_blockers"].append("PARITY_EVIDENCE: " + str(exc))
    try:
        report["observational_artifacts"] = _observational_artifacts(evidence, root, protocol, curves)
    except (ValueError, TypeError, KeyError, OSError, AttributeError) as exc:
        report["financial_blockers"].append("OBSERVATIONAL_EVIDENCE: " + str(exc))

    rejected: list[str] = []
    if any(row["insolvency"] for row in curves.values()):
        rejected.append("INSOLVENCY_NOT_CLIPPED")
    candidate = curves["SVR"]
    if candidate["drawdown_fraction_at_observation_resolution"] > protocol["max_drawdown_fraction"]:
        rejected.append("DRAWDOWN_LIMIT_EXCEEDED")
    if candidate["maximum_observed_gross_exposure_fraction"] > protocol["max_gross_exposure_fraction"]:
        rejected.append("EXPOSURE_LIMIT_EXCEEDED")
    if any(curves[k]["maximum_observed_gross_exposure_fraction"] > protocol["max_gross_exposure_fraction"] or curves[k]["drawdown_fraction_at_observation_resolution"] > protocol["max_drawdown_fraction"] for k in ("C0", "RIDGE")):
        report["financial_blockers"].append("CONTROL_RISK_LIMITS_EXCEEDED")
    ridge_exposure = curves["RIDGE"]["mean_observed_gross_exposure_fraction"]
    candidate_exposure = candidate["mean_observed_gross_exposure_fraction"]
    comparison = protocol["risk_comparison"]
    if candidate_exposure > ridge_exposure * comparison["maximum_candidate_mean_exposure_ratio"] + 1e-12 or candidate_exposure - ridge_exposure > comparison["maximum_candidate_mean_exposure_increment"] + 1e-12:
        report["financial_blockers"].append("CANDIDATE_EXPOSURE_NOT_COMPARABLE_TO_RIDGE")
    if not rejected:
        statistics = paired_block_bootstrap({k: curves[k]["log_returns"] for k in POLICIES}, protocol)
        report["statistics"] = statistics
        points = statistics["point_estimates"]
        minimums = {"svr_log_growth": 0.0, "svr_minus_ridge": protocol["minimum_delta_ridge_log_growth"], "svr_minus_c0": protocol["minimum_delta_c0_log_growth"]}
        if candidate["net_pnl_usd"] <= 0:
            rejected.append("NET_ABSOLUTE_PNL_NONPOSITIVE")
        for metric in METRICS:
            if points[metric] <= minimums[metric]:
                rejected.append("ECONOMIC_MINIMUM_NOT_MET_" + metric.upper())
        if statistics["status"] != "COMPUTED":
            report["financial_blockers"].extend(statistics["reasons"])
        elif not all(block["lower_one_sided"][key] > minimums[key] for block in statistics["blocks"] for key in METRICS):
            report["financial_blockers"].append("FAMILY_ADJUSTED_LOWER_BOUNDS_DO_NOT_EXCEED_MINIMUMS")
        report["statistical_gate_passed"] = bool(statistics["status"] == "COMPUTED" and not rejected and all(block["lower_one_sided"][key] > minimums[key] for block in statistics["blocks"] for key in METRICS))
    else:
        report["statistical_gate_passed"] = False
    report["rejection_reasons"] = rejected
    if rejected:
        report["dictamen"] = "RECHAZADO"
    elif report.get("statistical_gate_passed") is True and not report["financial_blockers"]:
        report["dictamen"] = "CANDIDATO_PARA_VALIDACION_FORWARD"
        report["candidate_for_forward_validation"] = True
    report["artifact_hash"] = digest(report)
    return report


def verify_gate_report(report: dict[str, Any], protocol: dict[str, Any], evidence: dict[str, Any], *, artifact_root: str | Path | None = None) -> dict[str, Any]:
    """Recompute, then compare.  A self-declared PASS is never an acceptance API."""
    expected = evaluate_gate(protocol, evidence, artifact_root=artifact_root)
    valid = report == expected
    try:
        integrity = isinstance(report, dict) and report.get("artifact_hash") == digest({k: v for k, v in report.items() if k != "artifact_hash"})
    except (ValueError, TypeError, OverflowError):
        integrity = False
    return {
        "schema": "HARPOON_ECONOMIC_GATE_VERIFICATION_1",
        "recomputed_identically": valid,
        "report_integrity_verified": integrity,
        "expected_report_hash": expected["artifact_hash"],
        "dictamen": expected["dictamen"] if valid else "VENTAJA_NO_DEMOSTRADA",
        "execution_allowed": False,
        "liveApproved": False,
        "financial_approval": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline paired net-economic validation; never authorizes trading")
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--artifact-root")
    args = parser.parse_args()
    protocol_path, input_path = Path(args.protocol), Path(args.input)
    report = evaluate_gate(json.loads(protocol_path.read_text()), json.loads(input_path.read_text()), artifact_root=args.artifact_root or input_path.parent)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "dictamen": report["dictamen"], "software_status": report["software_validators"]["status"], "execution_allowed": False}, sort_keys=True))
    return 0 if report["software_validators"]["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
