#!/usr/bin/env python3
"""Offline prospective-evidence gate, not a collector, scheduler or trading route.

Receipt metadata/hashes are necessary, not proof of source authenticity. This
module never certifies realized profitability or grants level 8. All timestamps
in bundles/freezes are UTC Unix milliseconds. Freeze CLI reads the actual admitted
historical run, checks the local registration, and never backdates or refits it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import time
from datetime import datetime, timezone
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
FREEZE_SCHEMA = "HARPOON_RESIDUAL_FORWARD_FREEZE_1"
BUNDLE_SCHEMA = "HARPOON_RESIDUAL_FORWARD_BUNDLE_1"
AUTHORITY = {"orders_allowed": False, "live_approved": False, "execution_allowed": False,
             "level8_accredited": False, "financial_acceptance_allowed": False, "strategy_approved": False}
RECEIPT_KINDS = {"BAR", "QUOTE", "CORPORATE_ACTION", "CORPORATE_COVERAGE", "FILL", "COST"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def is_hash(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def timestamp(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def create_freeze(models, protocol, code_hashes, admission, model_artifact_sha256,
                  derivation_verification_sha256, frozen_at_ms, historical_run_status="COMPLETE"):
    """Pure constructor. CLI independently obtains admission and current time."""
    require(admission.get("verified") is True and admission.get("offline_replay_admitted") is True
            and is_hash(admission.get("admission_identity_hash")), "FULL_DATA_CODE_ADMISSION_REQUIRED")
    require(timestamp(frozen_at_ms), "FREEZE_TIMESTAMP_REQUIRED")
    require(historical_run_status in {"COMPLETE", "COMPLETE_WITH_RETAINED_INCIDENTS"}, "TERMINAL_RETAINED_RUN_REQUIRED")
    require(models.get("schema") == "HARPOON_RESIDUAL_MODELS_1", "MODEL_SCHEMA")
    require(models.get("provenance", {}).get("protocol_sha256") == digest(protocol), "MODEL_PROTOCOL_BINDING")
    require(models.get("model_payload_sha256") == digest({k: v for k, v in models.items() if k != "model_payload_sha256"}),
            "MODEL_PAYLOAD_BINDING")
    require(models.get("counts", {}).get("available_models", 0) >= 1, "NO_ADMITTED_MODEL_AVAILABLE")
    require(code_hashes and all(isinstance(k, str) and k and is_hash(v) for k, v in code_hashes.items()), "CODE_HASHES_REQUIRED")
    require(is_hash(model_artifact_sha256) and is_hash(derivation_verification_sha256), "ARTIFACT_HASHES_REQUIRED")
    require(protocol.get("forward_plan", {}).get("no_live_orders_authorized") is True, "FORWARD_AUTHORITY_MUST_BE_FALSE")
    limits = protocol["limits"]
    result = {"schema": FREEZE_SCHEMA, "frozen_at": frozen_at_ms,
              "clock_scope": "LOCAL_EXECUTOR_UTC_NOT_INDEPENDENT_ATTESTATION",
              "purpose": "EVIDENCE_PIPELINE_ONLY_NOT_STRATEGY_APPROVAL",
              "historical_run_status": historical_run_status,
              "inherited_historical_incidents": historical_run_status == "COMPLETE_WITH_RETAINED_INCIDENTS",
              "historical_economic_gate_approved": False,
              "policy": "RESIDUAL_LONG",
              "study_id": protocol["study_id"], "protocol_sha256": digest(protocol),
              "admission_identity_hash": admission["admission_identity_hash"],
              "model_artifact_sha256": model_artifact_sha256,
              "model_payload_sha256": models["model_payload_sha256"],
              "model_hash_scope": "artifact=original_file_bytes; payload=canonical_object_without_model_payload_sha256",
              "derivation_verification_artifact_sha256": derivation_verification_sha256,
              "code_hashes": dict(sorted(code_hashes.items())), "universe": list(protocol["universe"]),
              "recipe": dict(protocol["recipe"]), "limits": dict(limits),
              "scenarios": protocol["scenarios"], "forward_plan": protocol["forward_plan"],
              "minimum_sessions": max(100, protocol["statistics"]["minimum_observed_sessions"]),
              "minimum_closed_campaigns": max(20, protocol["statistics"]["minimum_closed_candidate_campaigns"]),
              "minimum_counts_are_sufficient": False, "historical_negative_does_not_authorize_strategy": True,
              **AUTHORITY}
    result["freeze_sha256"] = digest(result)
    return result


def freeze_from_artifacts(protocol_path, artifacts):
    """Read-only registration verification; no additional fit/measurement."""
    import residual_register as reg
    protocol_path, artifacts = Path(protocol_path), Path(artifacts)
    receipt = reg.verify(APP / "evidence/residual_30_18_0/registration", protocol_path,
                         APP / "research/residual_30_18/source_manifest.json")
    protocol, models = read(protocol_path), read(artifacts / "models.json")
    run = read(artifacts / "run_receipt.json")
    require(run.get("status") in {"COMPLETE", "COMPLETE_WITH_RETAINED_INCIDENTS"}, "TERMINAL_RETAINED_RUN_REQUIRED")
    model_sha = file_sha(artifacts / "models.json")
    verification_sha = file_sha(artifacts / "derivation_verification.json")
    require(run.get("hashes", {}).get("models.json") == model_sha
            and run.get("hashes", {}).get("derivation_verification.json") == verification_sha,
            "RUN_ARTIFACT_BYTES_MISMATCH")
    verification = read(artifacts / "derivation_verification.json")
    require(verification.get("verified") is True
            and verification.get("admission_identity_hash") == receipt["admission_identity_hash"]
            and verification.get("hashes", {}).get("models.json") == digest(models), "VERIFIED_MODEL_DERIVATION_REQUIRED")
    binding = read(APP / "evidence/residual_30_18_0/registration/data_code_binding.json")
    registered = binding["identity"]["source_hashes"]
    code = {k: v for k, v in registered.items() if Path(k).suffix in {".py", ".js", ".cjs", ".ts"}
            or k in {"package.json", "package-lock.json", "quant/requirements-tested.txt"}}
    require(all(file_sha(APP / k) == v for k, v in code.items()), "CODE_BYTES_MISMATCH")
    return create_freeze(models, protocol, code, receipt, model_sha, verification_sha,
                         time.time_ns() // 1_000_000, historical_run_status=run["status"])


def bundle_template(freeze=None):
    """An intentionally BLOCKED empty template, not simulated observations."""
    f = freeze or {}
    return {"schema": BUNDLE_SCHEMA, "origin": "FORWARD", "mode": "CONDITIONAL_PAPER", "policy": "RESIDUAL_LONG",
            "created_at": time.time_ns() // 1_000_000, "freeze_sha256": f.get("freeze_sha256"),
            "model_artifact_sha256": f.get("model_artifact_sha256"), "code_hashes": f.get("code_hashes", {}),
            "scenario": "NOMINAL", "session_calendar": [], "receipts": [], "decisions": [],
            "corporate_actions": [], "corporate_action_coverage": {}, "account": [], "campaigns": [],
            "required_receipt_fields": ["id", "kind", "original_received_at", "event_end", "source",
                                        "source_receipt_sha256", "receipt_clock=ORIGINAL_FIRST_RECEIVED", "data"],
            "required_account_fields": ["session_id", "at", "equity_start", "equity_end", "cash_start", "cash_end",
                "positions_mark_start", "positions_mark_end", "receivables_start", "receivables_end",
                "trading_pnl_usd", "dividend_income_usd", "external_costs_usd", "cost_receipt_ids"],
            "note": "Empty means DATA_BLOCKED. Supply original observed records; never fill with synthetic prices/receipts.",
            **AUTHORITY}


def validate_bundle(bundle, freeze):
    """Return structured blockers. Valid is structural admission, never economic proof."""
    errors = []
    def check(ok, code, path):
        if not ok:
            errors.append({"code": code, "path": path})
        return bool(ok)
    if not isinstance(bundle, dict) or not isinstance(freeze, dict):
        errors.append({"code": "OBJECT_INPUTS_REQUIRED", "path": "bundle/freeze"})
        bundle = bundle if isinstance(bundle, dict) else {}
        freeze = freeze if isinstance(freeze, dict) else {}
    minimum_sessions = freeze.get("minimum_sessions", 100)
    minimum_campaigns = freeze.get("minimum_closed_campaigns", 20)
    if not check(isinstance(minimum_sessions, int) and not isinstance(minimum_sessions, bool)
                 and minimum_sessions >= 100, "MINIMUM_SESSION_GATE_INVALID", "freeze.minimum_sessions"):
        minimum_sessions = 100
    if not check(isinstance(minimum_campaigns, int) and not isinstance(minimum_campaigns, bool)
                 and minimum_campaigns >= 20, "MINIMUM_CAMPAIGN_GATE_INVALID", "freeze.minimum_closed_campaigns"):
        minimum_campaigns = 20
    now = time.time_ns() // 1_000_000
    try:
        check(freeze.get("schema") == FREEZE_SCHEMA, "FREEZE_SCHEMA", "freeze")
        check(freeze.get("freeze_sha256") == digest({k: v for k, v in freeze.items() if k != "freeze_sha256"}), "FREEZE_HASH_MISMATCH", "freeze")
        frozen = freeze.get("frozen_at")
        require(timestamp(frozen) and frozen <= now, "FREEZE_TIMESTAMP_INVALID_OR_FUTURE")
        check(all(freeze.get(k) is False for k in AUTHORITY), "FREEZE_AUTHORITY_FORBIDDEN", "freeze")
        check(bundle.get("schema") == BUNDLE_SCHEMA and bundle.get("origin") == "FORWARD", "FORWARD_SCHEMA_OR_ORIGIN", "bundle")
        check(bundle.get("policy") == freeze.get("policy") == "RESIDUAL_LONG", "PRIMARY_POLICY_REQUIRED", "bundle.policy")
        check(all(bundle.get(k) is False for k in AUTHORITY), "BUNDLE_AUTHORITY_FORBIDDEN", "bundle")
        check(bundle.get("freeze_sha256") == freeze["freeze_sha256"], "FREEZE_BINDING", "bundle.freeze_sha256")
        check(bundle.get("model_artifact_sha256") == freeze["model_artifact_sha256"], "MODEL_BYTES_BINDING", "bundle.model_artifact_sha256")
        check(bundle.get("code_hashes") == freeze["code_hashes"], "EXACT_CODE_BINDING", "bundle.code_hashes")
        created = bundle.get("created_at")
        require(timestamp(created) and frozen < created <= now, "BUNDLE_TIMESTAMP_INVALID_OR_FUTURE")
        mode = bundle.get("mode")
        check(mode in {"CONDITIONAL_PAPER", "OBSERVED_EXECUTION"}, "EVIDENCE_MODE_REQUIRED", "bundle.mode")
        scenario = bundle.get("scenario")
        require(scenario in freeze["scenarios"], "FROZEN_COST_SCENARIO_REQUIRED")
        universe = set(freeze["universe"])
        calendar, previous, dates = {}, -1, []
        for i, s in enumerate(bundle["session_calendar"]):
            path = f"session_calendar[{i}]"
            require(isinstance(s.get("date"), str) and timestamp(s.get("open")) and timestamp(s.get("close")), "CALENDAR_FIELDS_REQUIRED")
            check(s["date"] not in calendar and previous < s["open"] < s["close"], "CALENDAR_DUPLICATE_OR_BACKWARD", path)
            check(datetime.fromtimestamp(s["open"]/1000, timezone.utc).date().isoformat() == s["date"], "CALENDAR_DATE_MISMATCH", path)
            check(s["date"] >= freeze["forward_plan"]["first_possible_session"], "SESSION_BEFORE_FROZEN_FORWARD_PLAN", path)
            calendar[s["date"]] = s
            dates.append(s["date"])
            previous = s["close"]
        check(bool(calendar), "SESSION_CALENDAR_REQUIRED", "session_calendar")
        ids, receipts, previous = set(), {}, -1
        economic_item_keys = set()
        def identity(value, path):
            ident = value.get("id")
            require(isinstance(ident, str) and ident, "NONEMPTY_RECORD_ID_REQUIRED")
            check(ident not in ids, "DUPLICATE_RECORD_ID", path)
            ids.add(ident)
            return ident
        for i, r in enumerate(bundle["receipts"]):
            path = f"receipts[{i}]"
            ident = identity(r, path)
            received, event = r.get("original_received_at"), r.get("event_end")
            require(timestamp(received) and timestamp(event), "ORIGINAL_RECEIPT_TIMESTAMPS_REQUIRED")
            check(event <= received <= created, "FUTURE_OR_PRE_EVENT_RECEIPT", path)
            check(received >= previous, "RECEIPT_TIME_BACKWARD", path)
            previous = received
            check(r.get("receipt_clock") == "ORIGINAL_FIRST_RECEIVED" and r.get("modeled_timestamp", False) is False,
                  "MODELED_OR_RECONSTRUCTED_RECEIPT_FORBIDDEN", path)
            check(isinstance(r.get("source"), str) and bool(r["source"]) and is_hash(r.get("source_receipt_sha256")), "ORIGINAL_SOURCE_RECEIPT_REQUIRED", path)
            kind, value = r.get("kind"), r.get("data")
            require(kind in RECEIPT_KINDS and isinstance(value, dict), "RECEIPT_KIND_DATA_REQUIRED")
            if kind in {"BAR", "QUOTE"}:
                check(frozen < received, "FIRST_PRICE_OBSERVED_BEFORE_FREEZE", path)
                check(r.get("symbol") in universe, "PRICE_UNIVERSE", path)
                if kind == "BAR":
                    check(timestamp(value.get("t")) and timestamp(value.get("end")) and value["end"] == event
                          and value["end"] - value["t"] == 300000, "BAR_INTERVAL", path)
                    check(all(finite(value.get(k)) for k in ("o", "h", "l", "c", "v"))
                          and 0 < value["l"] <= min(value["o"], value["c"]) <= max(value["o"], value["c"]) <= value["h"]
                          and value["v"] >= 0, "BAR_OHLCV", path)
                    check(any(s["open"] <= value.get("t", -1) < value.get("end", -1) <= s["close"] for s in calendar.values()), "BAR_OUTSIDE_CALENDAR", path)
                else:
                    check(finite(value.get("bid")) and finite(value.get("ask")) and 0 < value["bid"] <= value["ask"], "QUOTE_PRICE", path)
            elif kind == "FILL":
                check(r.get("symbol") in universe and value.get("side") in {"BUY", "SELL"}
                      and finite(value.get("quantity")) and value["quantity"] > 0
                      and finite(value.get("price")) and value["price"] > 0
                      and isinstance(value.get("broker_execution_id"), str) and bool(value["broker_execution_id"]), "FILL_EVIDENCE_FIELDS", path)
                item_key = (r.get("source"), kind, value.get("broker_execution_id"))
                check(item_key not in economic_item_keys, "DUPLICATE_BROKER_EXECUTION_ITEM", path)
                economic_item_keys.add(item_key)
            elif kind == "COST":
                check(finite(value.get("amount_usd")) and value["amount_usd"] >= 0
                      and value.get("cost_type") in {"TRADING", "EXTERNAL"}
                      and isinstance(value.get("invoice_or_statement_id"), str) and bool(value["invoice_or_statement_id"]), "COST_EVIDENCE_FIELDS", path)
                item_key = (r.get("source"), kind, value.get("invoice_or_statement_id"), value.get("invoice_line_id", ""))
                check(item_key not in economic_item_keys, "DUPLICATE_COST_INVOICE_ITEM", path)
                economic_item_keys.add(item_key)
            receipts[ident] = r
        decisions, previous = {}, -1
        for i, d in enumerate(bundle["decisions"]):
            path = f"decisions[{i}]"
            ident = identity(d, path)
            at = d.get("at")
            require(timestamp(at) and d.get("session_id") in calendar, "DECISION_TIMESTAMP_SESSION_REQUIRED")
            s = calendar[d["session_id"]]
            check(frozen < at <= created and at > previous, "DECISION_TIME_BACKWARD_OR_PRE_FREEZE", path)
            previous = at
            check(at == s["open"] + freeze["recipe"]["entry_minutes"]*60000 + freeze["recipe"]["entry_delay_ms"], "DECISION_CLOCK_RECIPE", path)
            check(d.get("model_artifact_sha256") == freeze["model_artifact_sha256"] and d.get("code_hashes") == freeze["code_hashes"], "DECISION_IDENTITY_BINDING", path)
            references = d.get("receipt_ids")
            require(isinstance(references, list) and references, "DECISION_PRICE_RECEIPTS_REQUIRED")
            check(len(set(references)) == len(references), "DUPLICATE_DECISION_RECEIPT", path)
            for ref in references:
                r = receipts.get(ref)
                check(r is not None and r["kind"] in {"BAR", "QUOTE"}
                      and r["event_end"] <= r["original_received_at"] <= at, "DECISION_UNAVAILABLE_PRICE_RECEIPT", path+":"+str(ref))
            check(any(receipts.get(ref, {}).get("kind") == "BAR" for ref in references), "DECISION_BAR_REQUIRED", path)
            decisions[ident] = d
        check(bool(decisions), "OBSERVED_DECISIONS_REQUIRED", "decisions")
        coverage = bundle["corporate_action_coverage"]
        coverage_receipt = receipts.get(coverage.get("receipt_id"))
        check(coverage.get("status") == "OBSERVED" and coverage_receipt is not None
              and coverage_receipt["kind"] == "CORPORATE_COVERAGE"
              and coverage_receipt["original_received_at"] <= min((d["at"] for d in decisions.values()), default=-1)
              and timestamp(coverage.get("start")) and timestamp(coverage.get("end"))
              and coverage["start"] <= min((d["at"] for d in decisions.values()), default=created)
              and coverage["end"] >= max((d["at"] for d in decisions.values()), default=created),
              "OBSERVED_CORPORATE_ACTION_COVERAGE_REQUIRED", "corporate_action_coverage")
        for i, action in enumerate(bundle["corporate_actions"]):
            path = f"corporate_actions[{i}]"
            identity(action, path)
            known, effective = action.get("known_at"), action.get("effective_at")
            r = receipts.get(action.get("receipt_id"))
            require(timestamp(known) and timestamp(effective), "CORPORATE_OBSERVED_KNOWLEDGE_REQUIRED")
            check(action.get("symbol") in universe and r is not None and r["kind"] == "CORPORATE_ACTION"
                  and action.get("knowledge_source") == "OBSERVED_ORIGINAL_RECEIPT"
                  and r["original_received_at"] == known <= created, "CORPORATE_KNOWLEDGE_RECEIPT_BINDING", path)
            for d in decisions.values():
                if effective <= d["at"]:
                    check(known <= d["at"], "CORPORATE_ACTION_NOT_KNOWN_AT_DECISION", path)
        rows, previous_row, account_dates = bundle["account"], None, []
        allocated_economic_receipts = set()
        def allocate_references(refs, path):
            check(len(set(refs)) == len(refs), "DUPLICATE_ECONOMIC_RECEIPT_REFERENCE", path)
            check(not (set(refs) & allocated_economic_receipts), "ECONOMIC_RECEIPT_REUSED", path)
            allocated_economic_receipts.update(refs)
        cash_cost_evidence = True
        components = ("cash", "positions_mark", "receivables")
        for i, row in enumerate(rows):
            path = f"account[{i}]"
            sid = row.get("session_id")
            require(sid in calendar, "ACCOUNT_SESSION_REQUIRED")
            check(sid not in account_dates and (not account_dates or sid > account_dates[-1]), "ACCOUNT_DUPLICATE_OR_BACKWARD", path)
            account_dates.append(sid)
            check(row.get("at") == calendar[sid]["close"] and row["at"] <= created, "ACCOUNT_CLOSE_TIMESTAMP", path)
            fields = ["equity_start", "equity_end", "trading_pnl_usd", "dividend_income_usd", "external_costs_usd"]
            fields += [f"{k}_{edge}" for k in components for edge in ("start", "end")]
            require(all(finite(row.get(k)) for k in fields), "ACCOUNT_NUMERIC_FIELDS_REQUIRED")
            check(all(row[f"{k}_{edge}"] >= 0 for k in components for edge in ("start", "end")), "LONG_ONLY_NONNEGATIVE_ACCOUNT", path)
            for edge in ("start", "end"):
                check(abs(row[f"equity_{edge}"] - sum(row[f"{k}_{edge}"] for k in components)) <= 1e-7, "ACCOUNT_COMPONENT_RECONCILIATION", path)
            check(abs(row["equity_end"]-row["equity_start"]-row["trading_pnl_usd"]-row["dividend_income_usd"]+row["external_costs_usd"]) <= 1e-7, "ACCOUNT_PNL_RECONCILIATION", path)
            check(row["external_costs_usd"] >= 0 and row.get("deposits_usd", 0) == 0 and row.get("withdrawals_usd", 0) == 0, "CAPITAL_FLOW_OR_COST_CONTRACT", path)
            if previous_row is None:
                check(row["equity_start"] == freeze["limits"]["capitalUsd"] and row["cash_start"] == row["equity_start"], "INITIAL_CAPITAL_BINDING", path)
            else:
                check(all(abs(row[k+"_start"]-previous_row[k+"_end"]) <= 1e-7 for k in ("equity", *components)), "DISCONTINUOUS_CAPITAL", path)
            previous_row = row
            cost_ids = row.get("cost_receipt_ids", [])
            require(isinstance(cost_ids, list), "COST_RECEIPT_LIST_REQUIRED")
            allocate_references(cost_ids, path)
            observed_costs = [receipts.get(ref) for ref in cost_ids]
            cost_complete = bool(observed_costs) and all(c and c["kind"] == "COST" and c["data"]["cost_type"] == "EXTERNAL" for c in observed_costs)
            if cost_complete:
                cost_complete = abs(sum(c["data"]["amount_usd"] for c in observed_costs)-row["external_costs_usd"]) <= 1e-7
                cost_complete = cost_complete and all(calendar[sid]["open"] <= c["event_end"] <= row["at"] for c in observed_costs)
            cash_cost_evidence = cash_cost_evidence and cost_complete
            if mode == "CONDITIONAL_PAPER":
                check(row["external_costs_usd"] == freeze["scenarios"][scenario]["external_cost_usd_per_session"], "FIXED_COST_NOT_CHARGED_ONCE_PER_SESSION", path)
            elif mode == "OBSERVED_EXECUTION":
                check(cost_complete, "OBSERVED_EXTERNAL_COST_RECEIPTS_REQUIRED", path)
        expected_dates = [d for d in dates if calendar[d]["close"] <= created]
        check(bool(rows) and account_dates == expected_dates, "CONTINUOUS_ALL_SESSION_ACCOUNT_REQUIRED", "account")
        campaign_count, fill_cost_evidence, campaign_decisions = 0, True, set()
        for i, c in enumerate(bundle["campaigns"]):
            path = f"campaigns[{i}]"
            identity(c, path)
            d = decisions.get(c.get("decision_id"))
            check(c.get("decision_id") not in campaign_decisions, "MULTIPLE_CAMPAIGNS_FOR_ONE_DECISION", path)
            campaign_decisions.add(c.get("decision_id"))
            opened, closed = c.get("opened_at"), c.get("closed_at")
            require(d is not None and timestamp(opened) and timestamp(closed), "CAMPAIGN_DECISION_CLOCK_REQUIRED")
            check(d["at"] < opened <= closed <= created and closed-d["at"] <= 72*3600000, "CAMPAIGN_72_CALENDAR_HOURS", path)
            check(c.get("symbol") in universe, "CAMPAIGN_UNIVERSE", path)
            fill_refs, cost_refs = c.get("fill_receipt_ids", []), c.get("cost_receipt_ids", [])
            require(isinstance(fill_refs, list) and isinstance(cost_refs, list), "CAMPAIGN_RECEIPT_LISTS_REQUIRED")
            allocate_references(fill_refs+cost_refs, path)
            fills, costs = [receipts.get(ref) for ref in fill_refs], [receipts.get(ref) for ref in cost_refs]
            complete = len(fills) >= 2 and bool(costs) and all(r and r["kind"] == "FILL" and r.get("symbol") == c["symbol"]
                and opened <= r["event_end"] <= closed for r in fills) and all(r and r["kind"] == "COST" and r["data"]["cost_type"] == "TRADING" for r in costs)
            if complete:
                buys = sum(r["data"]["quantity"] for r in fills if r["data"]["side"] == "BUY")
                sells = sum(r["data"]["quantity"] for r in fills if r["data"]["side"] == "SELL")
                complete = buys > 0 and abs(buys-sells) <= 1e-8
                ordered = sorted(fills, key=lambda r: (r["event_end"], r["id"]))
                inventory = 0
                for r in ordered:
                    inventory += r["data"]["quantity"] * (1 if r["data"]["side"] == "BUY" else -1)
                    complete = complete and inventory >= -1e-8
                complete = complete and ordered[0]["event_end"] == opened and ordered[-1]["event_end"] == closed
                complete = complete and all(opened <= r["event_end"] <= closed for r in costs)
            fill_cost_evidence = fill_cost_evidence and complete
            if mode == "OBSERVED_EXECUTION":
                check(complete, "OBSERVED_MATCHED_FILL_AND_COST_RECEIPTS_REQUIRED", path)
            campaign_count += 1
        observed_evidence = mode == "OBSERVED_EXECUTION" and cash_cost_evidence and fill_cost_evidence
        sessions_count = len(rows)
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        errors.append({"code": "REQUIRED_FIELD_OR_CONTRACT", "path": str(exc)})
        observed_evidence, sessions_count, campaign_count = False, 0, 0
    valid = not errors
    return {"schema": "HARPOON_RESIDUAL_FORWARD_GATE_1", "valid": valid,
            "status": "ADMITTED_RECORDS_ONLY" if valid else "DATA_BLOCKED", "blocking_reasons": errors,
            "real_economics_evidence_complete": False,
            "observed_execution_receipts_structurally_complete": valid and observed_evidence,
            "economic_evidence_class": "OBSERVED_EXECUTION_RECORDS_REQUIRE_AUTHENTICATION" if valid and observed_evidence else "CONDITIONAL_PAPER_ONLY",
            "source_authenticity_independently_verified": False, "real_profitability_validated": False,
            "observed_sessions": sessions_count, "closed_campaigns": campaign_count,
            "minimum_count_gates": {"sessions": sessions_count >= minimum_sessions,
                "campaigns": campaign_count >= minimum_campaigns, "sufficient_for_level8": False},
            "strategy_performance_or_signal_derivation_validated_by_this_module": False,
            "fill_pnl_to_account_mark_ledger_reconciliation_required": True,
            "risk_limits_or_intraday_execution_certified": False, **AUTHORITY}


def write_once(path, value):
    with Path(path).open("x") as f:
        f.write(json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+"\n")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest="command", required=True)
    f = commands.add_parser("freeze")
    f.add_argument("--protocol", type=Path, default=APP/"research/residual_30_18/protocol.json")
    f.add_argument("--artifacts", type=Path, required=True)
    f.add_argument("--output", type=Path, required=True)
    t = commands.add_parser("template")
    t.add_argument("--freeze", type=Path)
    t.add_argument("--output", type=Path, required=True)
    v = commands.add_parser("validate")
    v.add_argument("--bundle", type=Path, required=True)
    v.add_argument("--freeze", type=Path, required=True)
    v.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.command == "freeze":
        result = freeze_from_artifacts(args.protocol, args.artifacts)
    elif args.command == "template":
        result = bundle_template(read(args.freeze) if args.freeze else None)
    else:
        result = validate_bundle(read(args.bundle), read(args.freeze))
    write_once(args.output, result)
    print(json.dumps({"output": str(args.output), "orders_allowed": False, "valid": result.get("valid")}))
    if args.command == "validate" and not result["valid"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
