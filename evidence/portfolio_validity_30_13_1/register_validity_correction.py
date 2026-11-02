"""Local append-only record for one fixed-selection validity repair.

This records a continuation without resetting or mutating either legacy journal.
It is not independent preregistration or approval to trade.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REGISTRATION = ROOT / "comparison/registration.json"
JOURNAL = ROOT / "comparison/continuation_journal.jsonl"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def append(action, payload, previous):
    events = [json.loads(line) for line in JOURNAL.read_text().splitlines()] if JOURNAL.exists() else []
    if events:
        assert events[-1]["hash"] == previous
    event = {"sequence": len(events)+1, "at": now(), "action": action,
             "payload": payload, "previous": previous}
    event["hash"] = digest(event)
    with JOURNAL.open("a", encoding="utf8") as out:
        out.write(canonical(event)+"\n")
    return event["hash"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["register", "complete"])
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--candidate", type=Path)
    args = parser.parse_args()
    if args.mode == "register":
        assert not REGISTRATION.exists() and not JOURNAL.exists(), "Existing registration must not be overwritten or reset"
        assert not (ROOT/"comparison/candidate_attempt_started.json").exists(), "Candidate already attempted"
        assert args.baseline and args.candidate
        baseline, candidate = args.baseline.resolve(), args.candidate.resolve()
        binding = json.loads(subprocess.check_output([
            "node", str(ROOT/"comparison/compare_frozen_portfolio.cjs"),
            "bindings", str(baseline), str(candidate)], text=True))
        historical = json.loads((baseline/"evidence/ultimate/registry.json").read_text())
        quant_path = baseline/"evidence/level5_30_12_0/history/optimizer.sqlite3"
        conn = sqlite3.connect(quant_path.as_uri()+"?mode=ro&immutable=1", uri=True)
        try:
            quant_budget = json.loads(conn.execute("SELECT v FROM optimizer_state WHERE k='budget'").fetchone()[0])
            seq, head = conn.execute("SELECT seq,h FROM optimizer_audit ORDER BY seq DESC LIMIT 1").fetchone()
        finally:
            conn.close()
        anchors = {
            "ultimate_export_sha256": sha(baseline/"evidence/ultimate/registry.json"),
            "ultimate_chain_head": historical["chain"][-1]["hash"],
            "ultimate_preserved_trial_slots": historical["trial"]["slots"],
            "quant_journal_sha256": sha(quant_path), "quant_budget_unchanged": quant_budget,
            "quant_audit_head": {"sequence": seq, "hash": head},
        }
        assert historical["trial"]["slots"] == 18 and quant_budget == {"limit":128, "spent":23}
        registration = {
            "schema": "HARPOON_EXPLORATORY_CORRECTION_REGISTRATION_1",
            "purpose": "ONE_VALIDITY_REPAIR_FIXED_SELECTION",
            "trial_id": "HARPOON_VALIDITY_REPAIR_20261101_01",
            "registered_at": now(), "registered_before_candidate_execution": True,
            "new_variant_count": 1, "fits_allowed": 0,
            "original_selection_frozen": True, "financial_acceptance_allowed": False,
            "execution_allowed": False, "liveApproved": False,
            "independent_external_preregistration": False,
            "data_scope": "REUSED_HISTORICAL_PREPARED_BARS_MODELED_EXECUTION",
            "information_already_observed": "Original 31 campaigns, 119.75 USD and attribution; the candidate result has not been evaluated.",
            "corrections": [
                "Calendar-feasible CLOSED_CHANNEL deadline anchored at decision; no late fictional exit or discarded open exposure.",
                "Quantity from a price available at the decision; fixed quantity at later modeled fill, with conservative capital/risk feasibility checks.",
            ],
            "unchanged_choices": ["universe SPY/XLK", "433 original opportunities", "16 original fold selections",
                                  "initial capital and exposure ceilings", "cost coefficients", "signal thresholds",
                                  "exit variants other than admissible holding deadline", "observation period"],
            "primary_outputs": ["evaluation completeness", "modeled trading PnL", "continuous portfolio growth",
                                "maximum modeled holding time", "open unresolved exposure", "fill feasibility incidents"],
            "secondary_outputs": ["difference from forensic control", "asset contributions", "entry/exit cohorts",
                                  "number of campaigns", "maximum drawdown", "capital release and skipped opportunities"],
            "interpretation_precommitted": {
                "effect_attribution": "Combined repair package; neither individual correction is causally isolated.",
                "technical_acceptance": "No unresolved exposure, no future input used for quantity, no modeled holding over72h, all fill feasibility checks pass.",
                "incomplete_or_unfunded_path": "Retain exposure and incident; total PnL is null; do not resize, censor or impute zero.",
                "unknown_external_costs": "Remain null, so a positive modeled trading PnL is not complete economic profitability.",
                "financial_acceptance": "No level6 or other financial promotion. This is not a new holdout and does not compare against Ridge.",
                "unfavorable_result": "Publish without retuning; an operational correctness repair is not selected by whether its PnL rises.",
            },
            "exploration_accounting": {
                "preserved_legacy_history": anchors,
                "new_joint_repair_variants": 1,
                "new_search_budget_created": False,
                "global_deduplicated_total": None,
                "global_total_reason": "Legacy studies use different slot definitions and overlapping periods; do not sum their counters.",
                "legacy_journal_mutations": 0,
                "retuning_or_additional_variants_allowed_by_this_record": False,
            },
            "bindings": binding,
            "calendar_and_cost_provenance": "Retained modeled assumptions; original149raw source files and actual account evidence are absent.",
        }
        REGISTRATION.write_text(json.dumps(registration, indent=2, ensure_ascii=False)+"\n", encoding="utf8")
        head = append("REGISTER_ONE_CORRECTION", {"trial_id":registration["trial_id"],
                    "registration_sha256":sha(REGISTRATION), "new_variants":1,
                    "prior_history":anchors}, digest(anchors))
        print(json.dumps({"registration":str(REGISTRATION), "sha256":sha(REGISTRATION), "journal_head":head,
                          "new_variants_registered":1, "financial_acceptance_allowed":False}))
    else:
        registration = json.loads(REGISTRATION.read_text())
        events = [json.loads(line) for line in JOURNAL.read_text().splitlines()]
        assert len(events) == 1 and events[0]["action"] == "REGISTER_ONE_CORRECTION", "Do not overwrite a completed trial"
        assert events[0]["payload"]["registration_sha256"] == sha(REGISTRATION)
        result_path = ROOT/"comparison/candidate/result.json"
        result = json.loads(result_path.read_text())
        assert result["registration"]["trial_id"] == registration["trial_id"]
        assert result["registration"]["sha256"] == sha(REGISTRATION)
        head = append("COMPLETE_ONE_CORRECTION", {"trial_id":registration["trial_id"],
                      "result_sha256":sha(result_path), "status":result["result"]["status"],
                      "modeled_trading_pnl_usd":result["result"]["netUsd"],
                      "new_variants_cumulative_in_this_continuation":1,
                      "financial_acceptance_allowed":False}, events[-1]["hash"])
        print(json.dumps({"completed":True, "journal_head":head,
                          "status":result["result"]["status"], "net_usd":result["result"]["netUsd"]}))


if __name__ == "__main__":
    main()
