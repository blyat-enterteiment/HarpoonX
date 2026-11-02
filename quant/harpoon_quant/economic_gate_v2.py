"""Economic v2 bridge: reexecuted funded policies, event risk and frozen history.

The v1 CASH=C0 contract remains unchanged. No fitting, budget reservations or
external orders occur here. All statistical inference reuses the v1 estimator.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
from pathlib import Path
from typing import Any

from .core import digest, timestamp
from .measurement_registration import ReadOnlyJournal
from .study_integrity import _json

SCHEMA = "HARPOON_ECONOMIC_PROTOCOL_2"
EVIDENCE_SCHEMA = "HARPOON_ECONOMIC_EVIDENCE_2"
ROLES = {"SVR": "CANDIDATE", "RIDGE": "FIXED_BENCHMARK", "NATIVE": "PRODUCER_C0", "CASH": "DETERMINISTIC_NO_ENTRY"}
# Retained 30.10.1 audit and the read-only verified 23-slot Quant prefix.
# These are local release anchors, not external authentication.
PRIOR_AUDIT_SHA256 = "c0b0556536ac5426b0bc9f6329e470eea1c28e542418407784700c5102536b7d"
HISTORICAL_QUANT_HEAD = "df39e861ed2aa086dfb80c782d7924bead338fa6dfc1a28dc202616d5c3c1208"


def _v1() -> Any:
    from . import economic_gate
    return economic_gate


def legacy_protocol(p: dict[str, Any]) -> dict[str, Any]:
    """Only an internal numeric API adapter; never re-register/relabel old data."""
    return _v1().seal_protocol({**p, "schema": _v1().PROTOCOL_SCHEMA,
                               "minimum_delta_c0_log_growth": p["minimum_delta_native_log_growth"]})


def validate_protocol(p: dict[str, Any]) -> None:
    v = _v1()
    v._need(p.get("schema") == SCHEMA and p.get("protocol_hash") == v.seal_protocol(p)["protocol_hash"], "V2_PROTOCOL_HASH_OR_SCHEMA")
    v._need(p.get("policy_roles") == ROLES, "EXPLICIT_V2_POLICY_ROLES_REQUIRED")
    v._need(p.get("exposure_measure") == "EVENT_INTERVAL_TIME_WEIGHTED_LAST_OBSERVED", "EXPOSURE_MEASURE_MUST_BE_FROZEN")
    v._need(p.get("external_cost_method") == "VERIFIED_LEDGER_ACCRUAL_TIMESTAMPS", "OBSERVED_COST_TIMING_METHOD_REQUIRED")
    v._validate_protocol(legacy_protocol(p))
    stress = p.get("stress_scenarios")
    if not isinstance(stress, list) or len(stress) != 1:
        raise ValueError("ONE_PREREGISTERED_STRESS_WITHIN_SIX_SLOTS_REQUIRED")
    for s in stress:
        v._need(isinstance(s.get("id"), str) and bool(s["id"]), "STRESS_ID_REQUIRED")
        changes = s.get("execution_overrides")
        v._need(isinstance(changes, dict) and bool(changes) and set(changes) <= {"fees_bps_per_side", "fee_per_fill_usd", "slippage_bps"}, "STRESS_EXECUTION_OVERRIDE_SCOPE")
        for key, value in changes.items():
            v._number(value, "STRESS_" + key, nonnegative=True)
        v._number(s.get("minimum_net_pnl_usd"), "STRESS_MIN_NET_PNL", nonnegative=True)
        v._number(s.get("minimum_delta_ridge_usd"), "STRESS_MIN_DELTA_RIDGE", nonnegative=True)
        v._need(0 < v._number(s.get("max_drawdown_fraction"), "STRESS_MAX_DD") <= p["max_drawdown_fraction"], "STRESS_RISK_CANNOT_BE_WEAKENED")


def read_artifact(ref: Any, root: Path, *, raw: bool = False) -> Any:
    path = _v1()._artifact(ref, root, json_content=False)
    _v1()._need(path.stat().st_size <= 192 * 1024 * 1024, "V2_ARTIFACT_BYTES_BOUND")
    return path if raw else _json(path.read_bytes())


def reexecute_derivation(ref: Any, root: Path) -> dict[str, Any]:
    v = _v1()
    request = read_artifact(ref, root, raw=True)
    app = Path(__file__).resolve().parents[2]
    tool = app / "tools/level5_readiness.cjs"
    v._need(tool.is_file(), "LEVEL5_FIXED_ADAPTER_MISSING")
    environment = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8",
                   "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
    # Reuse the already selected local Python interpreter, not arbitrary input code.
    import sys
    environment["HARPOON_QUANT_PYTHON"] = str(Path(sys.executable).absolute())
    try:
        run = subprocess.run(["node", str(tool), "--input", str(request)], cwd=app,
                             text=True, capture_output=True, timeout=180, check=False, env=environment)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("V2_REEXECUTION_UNAVAILABLE") from exc
    v._need(run.returncode == 0, "V2_REEXECUTION_FAILED:" + run.stderr[-1000:])
    v._need(len(run.stdout.encode()) <= 192 * 1024 * 1024, "V2_DERIVED_OUTPUT_BOUND")
    out = _json(run.stdout.encode())
    v._need(out.get("schema") == "HARPOON_LEVEL5_DERIVED_EVIDENCE_1", "V2_DERIVED_SCHEMA")
    v._need(all(out.get(k) is False for k in ("execution_allowed", "liveApproved", "financial_acceptance_allowed")), "V2_AUTHORITY_MUST_REMAIN_FALSE")
    return dict(out)


def summarize_policy(item: dict[str, Any], p: dict[str, Any]) -> dict[str, Any]:
    """Reconcile every economic event before aggregating the paired sessions."""
    v = _v1()
    role = item["role"]
    v._need(role in ROLES, "UNKNOWN_POLICY_ROLE")
    rows = item["events"]
    v._need(isinstance(rows, list) and 1 <= len(rows) <= 100_000, "EVENT_CURVE_BOUND")
    initial = v._number(item["initial_equity_usd"], "INITIAL_EQUITY")
    v._need(v._equal(initial, p["initial_equity_usd"]), "INITIAL_EQUITY_BINDING")
    start_ms, end_ms = (timestamp(p["period"][k]).timestamp() * 1000 for k in ("test_start", "test_end"))
    # core.timestamp returns an aware datetime; replay timestamps are milliseconds.
    peak, dd, exposure_max, area, previous_exposure = initial, 0.0, 0.0, 0.0, 0.0
    previous_at, previous_cost, previous_fee = start_ms, 0.0, 0.0
    insolvency = False
    unfunded = False
    reserve = item.get("operating_cash_reserve")
    reserve_verified = False
    reserved_cash_deficit = False
    if reserve is not None:
        v._need(isinstance(reserve, dict) and reserve.get("method") == "FIXED_INITIAL_CASH_RESERVE", "OPERATING_RESERVE_METHOD")
        amount = v._number(reserve.get("amount_usd"), "OPERATING_RESERVE", nonnegative=True)
        v._need(amount <= initial and v._number(reserve.get("known_at"), "RESERVE_KNOWLEDGE_TIME") < start_ms, "OPERATING_RESERVE_NOT_CAUSAL_OR_UNFUNDED")
        reserve_verified = True
    sessions: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for row in rows:
        at = v._number(row["at"], "EVENT_TIME")
        v._need(previous_at <= at <= end_ms and row["event_id"] not in seen, "EVENT_CHRONOLOGY_OR_DUPLICATION")
        seen.add(row["event_id"])
        cash = v._number(row["cash_usd"], "CASH")
        inventory = v._number(row["inventory_value_usd"], "INVENTORY", nonnegative=True)
        account = v._number(row["account_equity_usd"], "ACCOUNT_EQUITY")
        economic = v._number(row["economic_equity_usd"], "ECONOMIC_EQUITY")
        cost = v._number(row["cumulative_external_cost_usd"], "COST", nonnegative=True)
        fees = v._number(row["cumulative_fees_usd"], "FEES", nonnegative=True)
        v._need(v._equal(cash + inventory, account) and v._equal(account - cost, economic), "EVENT_ACCOUNT_IDENTITY")
        v._need(row["external_flow_usd"] == 0 and cost >= previous_cost and fees >= previous_fee, "EVENT_COST_FLOW_SCOPE")
        positions = row["positions"]
        v._need(isinstance(positions, list) and v._equal(sum(v._number(float(x["market_value"]), "POSITION_VALUE", nonnegative=True) for x in positions), inventory), "EVENT_INVENTORY_IDENTITY")
        v._need(all(x["symbol"] in p["universe"] and float(x["qty"]) >= 0 for x in positions), "EVENT_POSITION_UNIVERSE")
        if role == "CASH":
            v._need(not positions and inventory == 0 and fees == 0 and v._equal(cash, initial), "CASH_CONTROL_HAS_TRADING_OR_FINANCING")
        if economic <= 0 or account <= 0:
            insolvency = True
            dd = max(dd, 1.0)
        unfunded = unfunded or cash - cost < -1e-7
        if reserve is not None:
            v._need(row.get("operating_cash_reserve_usd") == reserve["amount_usd"] and
                    row.get("operating_reserve_known_at") == reserve["known_at"] and
                    v._equal(v._number(row.get("buying_power_usd"), "BUYING_POWER"), cash - reserve["amount_usd"]) and
                    v._equal(v._number(row.get("non_marginable_buying_power_usd"), "NON_MARGINABLE_BUYING_POWER"), cash - reserve["amount_usd"]),
                    "OPERATING_RESERVE_NOT_REEXECUTED_IN_ACCOUNT")
            reserve_verified = reserve_verified and cost <= reserve["amount_usd"]
            reserved_cash_deficit = reserved_cash_deficit or cash < reserve["amount_usd"] - 1e-7
        peak = max(peak, economic)
        dd = max(dd, 1 - economic / peak)
        exposure = inventory / economic if economic > 0 else 0.0
        area += previous_exposure * (at - previous_at)
        exposure_max = max(exposure_max, exposure)
        previous_at, previous_exposure, previous_cost, previous_fee = at, exposure, cost, fees
        sid = row["session_id"]
        if sid not in sessions:
            sessions[sid] = {"session_id": sid, "start_at": at, "end_at": at, "equity_end_usd": economic}
        sessions[sid].update(end_at=at, equity_end_usd=economic)
    v._need(previous_at == end_ms, "TERMINAL_EVENT_MUST_REACH_TEST_END")
    calendar = p["evaluation_sessions"]
    v._need(list(sessions) == [r["session_id"] for r in calendar], "V2_PAIRED_SESSION_CALENDAR_MISMATCH")
    # Cost timestamps can precede a market session. Returns belong to that session's
    # economic interval; no weekend/after-hours pseudo-session is created.
    log_returns = []
    previous_equity = initial
    for expected in calendar:
        row = sessions[expected["session_id"]]
        declared_end = timestamp(expected["end_at"]).timestamp() * 1000
        v._need(row["end_at"] == declared_end, "V2_SESSION_END_NOT_BOUND")
        value = row["equity_end_usd"]
        if previous_equity > 0 and value > 0:
            log_returns.append(math.log(value / previous_equity))
        previous_equity = value
    return {"role": role, "initial_equity_usd": initial, "final_equity_usd": previous_equity,
            "net_pnl_usd": previous_equity - initial, "insolvency": insolvency,
            "economic_cash_unfunded": unfunded, "maximum_drawdown_fraction": dd,
            "operating_cash_reserve": reserve, "operating_reserve_verified": reserve_verified,
            "reserved_cash_deficit": reserved_cash_deficit,
            "maximum_gross_exposure_fraction": exposure_max,
            "mean_gross_exposure_fraction": area / (end_ms - start_ms),
            "fees_usd": previous_fee, "external_cost_usd": previous_cost,
            "session_count": len(calendar), "event_count": len(rows), "log_returns": log_returns,
            "maximum_observed_holding_hours": item["maximum_observed_holding_hours"],
            "stale_terminal_valuation_symbols": item["stale_terminal_valuation_symbols"],
            "execution_io_failure_count": item["execution_io_failure_count"],
            "curve_hash": digest(rows), "terminal_inventory": rows[-1]["positions"],
            "valuation_resolution": "REPLAY_EVENTS_AND_DOCUMENTED_COST_ACCRUALS;UNOBSERVED_MARKET_PATH_UNKNOWN"}


def _pointer(obj: Any, pointer: str) -> Any:
    _v1()._need(isinstance(pointer, str) and pointer.startswith("/"), "IDENTITY_POINTER_REQUIRED")
    for part in pointer[1:].split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        obj = obj[int(key)] if isinstance(obj, list) else obj[key]
    return obj


def verify_history(manifest_ref: Any, root: Path, p: dict[str, Any]) -> dict[str, Any]:
    """Read actual family artifacts; incomplete identities remain null, not 23."""
    v = _v1()
    manifest = read_artifact(manifest_ref, root)
    v._need(manifest.get("schema") == "HARPOON_RESEARCH_HISTORY_MANIFEST_2", "HISTORY_MANIFEST_SCHEMA")
    refs = manifest["sources"]
    v._need(set(refs) == {"quant_journal", "ultimate_registry", "tp32_report", "prior_readiness"}, "ALL_KNOWN_HISTORY_FAMILIES_REQUIRED")
    v._need(refs["prior_readiness"]["sha256"] == PRIOR_AUDIT_SHA256, "PRIOR_AUDIT_RELEASE_ANCHOR_MISMATCH")
    prior = read_artifact(refs["prior_readiness"], root)
    anchored_sources = {x["id"]: x for x in prior["provenance"]["sources"]}
    for family in ("ultimate_registry", "tp32_report"):
        v._need(refs[family]["sha256"] == anchored_sources[family]["sha256"], "HISTORICAL_FAMILY_NOT_BOUND_TO_PRIOR_AUDIT")
    ultimate = read_artifact(refs["ultimate_registry"], root)
    tp = read_artifact(refs["tp32_report"], root)
    v._need(prior.get("schema") == "HARPOON_ECONOMIC_READINESS_1", "PRIOR_READINESS_REQUIRED")
    v._need(ultimate["trial"]["protocol"]["schema"] == "HARPOON-ULTIMATE-PROTOCOL-1" and tp["schema"] == "HARPOON-WF-REPORT-32-1", "HISTORICAL_FAMILY_SCHEMA")
    journal_path = read_artifact(refs["quant_journal"], root, raw=True)
    wal = journal_path.with_name(journal_path.name + "-wal")
    if wal.exists() and wal.stat().st_size:
        bound_wal = read_artifact(manifest.get("quant_journal_wal"), root, raw=True)
        v._need(bound_wal == wal, "QUANT_JOURNAL_WAL_NOT_BOUND")
    journal = ReadOnlyJournal(journal_path)
    try:
        budget = journal.get("budget")
        head = journal.db.execute("SELECT h FROM optimizer_audit ORDER BY seq DESC LIMIT 1").fetchone()[0]
        v._need(head == manifest.get("quant_audit_head"), "QUANT_HISTORY_HEAD_MISMATCH")
        v._need(journal.db.execute("SELECT 1 FROM optimizer_audit WHERE h=?", (HISTORICAL_QUANT_HEAD,)).fetchone() is not None, "HISTORICAL_QUANT_PREFIX_MISSING")
        spent = v._integer(budget["spent"], "QUANT_SPENT", v.HISTORICAL_SEARCH_FLOOR, 10_000)
        v._need(budget["limit"] == prior["trial_accounting"]["quant_economic"]["budget_limit"], "HISTORICAL_BUDGET_LIMIT_CHANGED")
        family_counts = {"QUANT": spent, "ULTIMATE": int(ultimate["trial"]["slots"]), "TP32": int(tp["trialCount"])}
        v._need(family_counts["ULTIMATE"] >= 18 and family_counts["TP32"] >= 3, "HISTORICAL_FAMILY_COUNTER_RESET")
        mapping = manifest.get("attempt_identity_map")
        total: int | None = None
        if mapping is not None:
            v._need(isinstance(mapping, list), "IDENTITY_MAP_REQUIRED")
            covered: set[tuple[str, int]] = set()
            records: set[tuple[str, str]] = set()
            identities: set[str] = set()
            for entry in mapping:
                family, slot = entry["family"], entry["slot"]
                v._need(family in family_counts and type(slot) is int and 0 <= slot < family_counts[family] and (family, slot) not in covered, "IDENTITY_MAP_SLOT_COVERAGE")
                if family == "QUANT":
                    record = journal.get(entry["journal_key"])
                    identity = _pointer(record, entry["pointer"])
                    location = entry["journal_key"] + entry["pointer"]
                else:
                    identity = _pointer(ultimate if family == "ULTIMATE" else tp, entry["pointer"])
                    location = entry["pointer"]
                v._need((family, location) not in records, "DUPLICATED_HISTORY_SOURCE_ROW")
                v._need(isinstance(identity, dict) and isinstance(identity.get("attempt_id"), str), "NATIVE_ATTEMPT_IDENTITY_UNAVAILABLE")
                verified = {k: v._hash(identity.get(k), "IDENTITY_" + k) for k in ("code_hash", "data_hash", "policy_hash")}
                verified["attempt_id"] = identity["attempt_id"]
                covered.add((family, slot))
                records.add((family, location))
                identities.add(digest(verified))
            v._need(covered == {(f, i) for f, n in family_counts.items() for i in range(n)}, "INCOMPLETE_HISTORY_IDENTITY_COVERAGE")
            total = len(identities)
        v._need(manifest.get("global_deduplicated_total") == total, "GLOBAL_COUNT_NOT_DERIVED_FROM_SOURCE_IDENTITIES")
        # Reopen immutable byte references after the SQLite read transaction too.
        read_artifact(refs["quant_journal"], root, raw=True)
        if wal.exists() and wal.stat().st_size:
            read_artifact(manifest.get("quant_journal_wal"), root, raw=True)
        reservation_heads = [str(row[0]) for row in journal.db.execute(
            "SELECT h FROM optimizer_audit WHERE json_extract(payload,'$.key') LIKE 'measurement:funded:v1:%'").fetchall()]
    finally:
        journal.close()
    # Explicitly read every preserved source named by the previous audit. Its
    # own byte hash alone cannot authenticate the underlying historical claims.
    historical_refs = manifest.get("historical_source_files", {})
    prior_sources = prior.get("provenance", {}).get("sources", [])
    v._need(isinstance(prior_sources, list) and len(prior_sources) > 0, "PRIOR_HISTORY_SOURCE_MANIFEST_MISSING")
    for source in prior_sources:
        if source.get("relative_path") and source.get("sha256"):
            r = historical_refs.get(source["relative_path"])
            v._need(r is not None and r.get("sha256") == source["sha256"], "PRIOR_HISTORY_SOURCE_NOT_BOUND")
            read_artifact(r, root, raw=True)
    periods = []
    for name, node in prior.get("financial_evidence", {}).items():
        for key in ("period", "holdout"):
            values = node.get(key, {})
            if isinstance(values, dict):
                dates = [str(values[x]) for x in ("from", "through", "holdoutFrom", "holdoutThrough") if x in values]
                if len(dates) >= 2:
                    periods.append({"family": name, "from": min(dates), "through": max(dates)})
        if node.get("holdout_from") and node.get("holdout_through"):
            periods.append({"family": name, "from": node["holdout_from"], "through": node["holdout_through"]})
    periods.append({"family": "TP32", "from": tp["windows"]["oosFrom"], "through": tp["windows"]["holdoutThrough"]})
    known = str(prior.get("generated_at", ""))
    v._need(bool(known), "PRIOR_REVIEW_TIME_MISSING")
    start, end = p.get("period", {}).get("test_start"), p.get("period", {}).get("test_end")
    overlap: bool | None = None
    freshness: bool | None = None
    if start is not None and end is not None:
        overlap = any(timestamp(x["from"] + "T00:00:00+00:00") < timestamp(end) and
                      timestamp(x["through"] + "T23:59:59+00:00") >= timestamp(start) for x in periods)
        freshness = timestamp(known) < timestamp(start) and not overlap
    return {"source_bytes_and_quant_journal_verified": True, "family_counts": family_counts,
            "global_deduplicated_total": total, "global_null_reason": None if total is not None else "Native per-attempt identities across historical families remain unresolved; separate counters are not summed.",
            "known_test_overlap": overlap, "known_periods": periods,
            "test_after_known_history": freshness,
            "freshness_null_reason": "No final test period has been frozen." if freshness is None else None,
            "quant_measurement_reservation_heads": reservation_heads,
            "search_coverage_verified": total is not None and total == p["search"]["total_attempts"],
            "manifest_sha256": manifest_ref["sha256"], "external_authentication": False}


def _risk(summary: dict[str, Any], p: dict[str, Any]) -> list[str]:
    errors = []
    if summary["insolvency"]:
        errors.append("INSOLVENCY_NOT_CLIPPED")
    if summary["economic_cash_unfunded"]:
        errors.append("EXTERNAL_COST_FINANCING_NOT_AVAILABLE")
    if summary["reserved_cash_deficit"]:
        errors.append("RESERVED_CASH_DEFICIT")
    if summary["maximum_drawdown_fraction"] > p["max_drawdown_fraction"]:
        errors.append("EVENT_DRAWDOWN_LIMIT_EXCEEDED")
    if summary["maximum_gross_exposure_fraction"] > p["max_gross_exposure_fraction"]:
        errors.append("EVENT_EXPOSURE_LIMIT_EXCEEDED")
    if summary["maximum_observed_holding_hours"] > p["horizon_hours"]:
        errors.append("HOLDING_HORIZON_EXCEEDED")
    if summary["stale_terminal_valuation_symbols"]:
        errors.append("TERMINAL_MARK_STALE")
    if summary["execution_io_failure_count"]:
        errors.append("EXECUTION_IO_FAILURES_PRESENT")
    return errors


def evaluate(protocol: dict[str, Any], evidence: dict[str, Any], root: Path) -> dict[str, Any]:
    v = _v1()
    out = v._report_base()
    out.update(schema="HARPOON_ECONOMIC_GATE_2", score=3, level5_criterion_met=False,
               policy_roles=ROLES, derivation=None, history=None, stress=None,
               protocol_hash=protocol.get("protocol_hash"), input_hash=digest(evidence))
    blockers = out["financial_blockers"]
    rejected: list[str] = []
    try:
        validate_protocol(protocol)
        v._need(evidence.get("schema") == EVIDENCE_SCHEMA and evidence.get("protocol_hash") == protocol["protocol_hash"], "V2_INPUT_PROTOCOL_BINDING")
        v._need(all(evidence.get(k) is False for k in ("execution_allowed", "liveApproved")), "V2_INPUT_OFFLINE_ONLY")
        v._need("policies" not in evidence and "curves" not in evidence, "CALLER_CURVES_NOT_ACCEPTED")
        timestamp(evidence["generated_at"])
        out["preregistration"] = v._preregistration(protocol, evidence, root)
        registered = timestamp(out["preregistration"]["registered_at"])
        v._need(registered < timestamp(protocol["period"]["test_start"]), "V2_TEST_MUST_START_AFTER_REGISTRATION")
        v._need(timestamp(protocol["period"]["test_end"]) <= timestamp(evidence["generated_at"]), "TEST_NOT_COMPLETE")
        try:
            history_input = read_artifact(evidence["search_history"], root)
            v._need(isinstance(evidence.get("history_manifest"), dict) and
                    history_input.get("historical_manifest_sha256") == evidence["history_manifest"]["sha256"], "V2_HISTORY_MANIFEST_NOT_BOUND_TO_SEARCH_HISTORY")
            history = verify_history(evidence["history_manifest"], root, protocol)
            out["history"] = history
            if not history["search_coverage_verified"]:
                blockers.append("GLOBAL_SEARCH_HISTORY_UNRESOLVED")
            if history["known_test_overlap"]:
                blockers.append("FINAL_TEST_OVERLAPS_PREVIOUS_USE")
            if history["test_after_known_history"] is not True:
                blockers.append("FINAL_TEST_FRESHNESS_UNVERIFIED")
        except (ValueError, TypeError, KeyError, OSError, AttributeError) as exc:
            blockers.append("HISTORY_EVIDENCE:" + str(exc))
        derived = reexecute_derivation(evidence["derivation_request"], root)
        out["derivation"] = {k: val for k, val in derived.items() if k not in {"policies", "stress"}}
        blockers.extend(derived["financial_blockers"])
        if out["history"] is not None:
            heads = out["history"]["quant_measurement_reservation_heads"]
            receipts = [derived.get("comparison", {}).get("registration", {})] + [s.get("registration", {}) for s in derived["stress"]]
            if any(r.get("audit_head_at_reservation") not in heads for r in receipts):
                blockers.append("COMPARISON_RESERVATIONS_NOT_IN_VERIFIED_HISTORY_JOURNAL")
        v._need(derived.get("complete_derived_comparison") is True, "COMPLETE_REEXECUTED_COMPARISON_REQUIRED")
        b = derived["bindings"]
        for key in ("policy_hash", "risk_hash", "cost_hash", "code_hash", "universe", "initial_equity_usd"):
            v._need(b[key] == protocol[key], "V2_DERIVED_BINDING_" + key.upper())
        v._need(b["period"]["start_at"] == timestamp(protocol["period"]["test_start"]).timestamp() * 1000 and
                b["period"]["end_at"] == timestamp(protocol["period"]["test_end"]).timestamp() * 1000, "V2_TEST_PERIOD_BINDING")
        v._need(b["maximum_holding_hours"] <= protocol["horizon_hours"], "CONFIG_HOLDING_HORIZON_BINDING")
        curves = {role: summarize_policy(derived["policies"][role], protocol) for role in ROLES}
        # Same grid and costs across all controls, including no-entry CASH.
        base_grid = [(r["event_id"], r["at"], r["session_id"], r["cumulative_external_cost_usd"]) for r in derived["policies"]["SVR"]["events"]]
        v._need(all([(r["event_id"], r["at"], r["session_id"], r["cumulative_external_cost_usd"]) for r in derived["policies"][role]["events"]] == base_grid for role in ROLES), "V2_EVENTS_OR_EXTERNAL_COSTS_NOT_PAIRED")
        out["policies"] = {role: {k: val for k, val in row.items() if k != "log_returns"} for role, row in curves.items()}
        for role, row in curves.items():
            for reason in _risk(row, protocol):
                (rejected if role == "SVR" else blockers).append(role + ":" + reason)
        if candidate_cost := curves["SVR"]["external_cost_usd"]:
            verified_reserve = all(row["operating_reserve_verified"] for row in curves.values())
            if not verified_reserve:
                blockers.append("EXTERNAL_COST_CAPITAL_RESERVE_PARITY_UNVERIFIED")
            out["external_cost_financing"] = {"external_cost_usd": candidate_cost,
                "economic_cash_nonnegative": not curves["SVR"]["economic_cash_unfunded"],
                "reserve_effect_on_original_decisions": "FIXED_RESERVE_REEXECUTED_IN_ALL_POLICIES" if verified_reserve else None,
                "reason": "Original shared reserve was reexecuted in every policy." if verified_reserve else "No verified shared capital reserve in the original policy comparison."}
        candidate, benchmark = curves["SVR"], curves["RIDGE"]
        ratio = protocol["risk_comparison"]
        if (candidate["mean_gross_exposure_fraction"] > benchmark["mean_gross_exposure_fraction"] * ratio["maximum_candidate_mean_exposure_ratio"] + 1e-12 or
                candidate["mean_gross_exposure_fraction"] - benchmark["mean_gross_exposure_fraction"] > ratio["maximum_candidate_mean_exposure_increment"] + 1e-12):
            blockers.append("CANDIDATE_EXPOSURE_NOT_COMPARABLE_TO_RIDGE")
        stress_results = []
        expected_scenarios = {x["id"]: x for x in protocol["stress_scenarios"]}
        v._need(set(expected_scenarios) == {x["id"] for x in derived["stress"]}, "PREREGISTERED_STRESS_COVERAGE")
        for scenario in derived["stress"]:
            spec = expected_scenarios[scenario["id"]]
            v._need(scenario["changes"] == spec["execution_overrides"], "STRESS_NOT_PREREGISTERED_OVERRIDES")
            summaries = {role: summarize_policy(scenario["policies"][role], protocol) for role in ROLES}
            sr, br = summaries["SVR"], summaries["RIDGE"]
            reasons = _risk(sr, {**protocol, "max_drawdown_fraction": spec["max_drawdown_fraction"]})
            for role in ("RIDGE", "NATIVE", "CASH"):
                for reason in _risk(summaries[role], protocol):
                    blockers.append(scenario["id"] + ":" + role + ":" + reason)
            if sr["net_pnl_usd"] <= spec["minimum_net_pnl_usd"]:
                reasons.append("STRESS_ABSOLUTE_NET_MINIMUM_NOT_MET")
            if sr["net_pnl_usd"] - br["net_pnl_usd"] <= spec["minimum_delta_ridge_usd"]:
                reasons.append("STRESS_RIDGE_INCREMENTAL_MINIMUM_NOT_MET")
            if reasons:
                rejected.extend(scenario["id"] + ":" + x for x in reasons)
            stress_results.append({"id": scenario["id"], "passed": not reasons, "reasons": reasons,
                                   "reservation_verified": scenario["reservation_verified"],
                                   "policies": {r: {k: val for k, val in row.items() if k != "log_returns"} for r, row in summaries.items()}})
        out["stress"] = stress_results
        if protocol["data_scope"] == "SYNTHETIC_ENGINEERING_ONLY":
            blockers.append("SYNTHETIC_IS_NOT_FINANCIAL_EVIDENCE")
        if protocol["data_scope"] != "HISTORICAL":
            blockers.append("V2_REPLAY_SCOPE_IS_HISTORICAL_MODELED_ONLY")
        if derived["readiness"]["score"] == 4:
            out["score"] = 4
        out["software_validators"] = {"status": "PASS", "errors": [], "scope": "Reexecuted three-policy coordinator, fixed estimators, event accounting, CASH and preregistered stress"}
        if not any(x["insolvency"] for x in curves.values()):
            stats = v.paired_block_bootstrap({"SVR": curves["SVR"]["log_returns"], "RIDGE": curves["RIDGE"]["log_returns"], "C0": curves["NATIVE"]["log_returns"]}, legacy_protocol(protocol))
            # Preserve the existing estimator and make the external control name explicit.
            out["statistics"] = json.loads(json.dumps(stats).replace('"svr_minus_c0"', '"svr_minus_native"'))
            minimums = {"svr_log_growth": 0, "svr_minus_ridge": protocol["minimum_delta_ridge_log_growth"], "svr_minus_c0": protocol["minimum_delta_native_log_growth"]}
            if candidate["net_pnl_usd"] <= 0:
                rejected.append("NET_ABSOLUTE_PNL_NONPOSITIVE")
            for key, minimum in minimums.items():
                if stats["point_estimates"][key] <= minimum:
                    rejected.append("ECONOMIC_MINIMUM_NOT_MET_" + key.replace("c0", "native").upper())
            lower = stats["status"] == "COMPUTED" and all(block["lower_one_sided"][key] > minimum for block in stats["blocks"] for key, minimum in minimums.items())
            out["statistical_gate_passed"] = lower and not rejected
            if stats["status"] != "COMPUTED":
                blockers.extend(stats["reasons"])
            elif not lower:
                blockers.append("FAMILY_ADJUSTED_LOWER_BOUNDS_DO_NOT_EXCEED_MINIMUMS")
        else:
            out["statistical_gate_passed"] = False
    except (ValueError, TypeError, KeyError, OSError, OverflowError, AttributeError) as exc:
        out["software_validators"] = {"status": "BLOCKED", "errors": [str(exc)]}
        blockers.append("V2_EVIDENCE_NOT_VERIFIED")
    out["rejection_reasons"] = rejected
    if rejected:
        out["dictamen"] = "RECHAZADO"
    elif out.get("statistical_gate_passed") and not blockers and out["score"] == 4:
        out.update(dictamen="CANDIDATO_PARA_VALIDACION_FORWARD", candidate_for_forward_validation=True,
                   level5_criterion_met=True, score=5)
    out["artifact_hash"] = digest(out)
    return out
