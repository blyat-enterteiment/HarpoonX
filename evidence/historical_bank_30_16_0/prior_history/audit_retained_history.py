"""Read-only retained-history audit. No trials, fitting, reservations or orders.

Uses SQLite's immutable read-only connection only after checking an empty WAL.
Outputs a new inventory; original project artifacts are never rewritten.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value, canonical=True) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=canonical, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def chain_check(rows, *, canonical, previous_field, initial=None):
    head = initial if initial is not None else (rows[0][previous_field] if rows else None)
    for row in rows:
        body = {k: v for k, v in row.items() if k != "hash"}
        if row[previous_field] != head or digest(body, canonical) != row["hash"]:
            return {"verified": False, "head": None, "records": len(rows)}
        head = row["hash"]
    return {"verified": True, "head": head, "records": len(rows)}


def audit(root: Path):
    names = [
        "quant/economic_experiment/study/optimizer.sqlite3",
        "quant/economic_experiment/study/optimizer.sqlite3-wal",
        "quant/economic_experiment/study/protocol.json",
        "quant/economic_experiment/analysis_protocol.json",
        "evidence/ultimate/registry.json", "evidence/ultimate/report.json",
        "research/tp32/protocol.json", "evidence/tp32/report.json",
        "evidence/integral_30_12_1/review/branches/history_extension.json",
        "evidence/integral_30_12_1/history/manifest.json",
        "evidence/portfolio_validity_30_13_1/comparison/registration.json",
        "evidence/portfolio_validity_30_13_1/comparison/continuation_journal.jsonl",
        "evidence/portfolio_30_14_0/registration.json", "evidence/portfolio_30_14_0/journal.jsonl",
        "evidence/portfolio_30_14_0/new_market_data/import_assessment.json",
        "evidence/level7_30_15_0/data_research/corporate_actions_assessment.json",
        "evidence/level7_30_15_0/protocol_draft_not_registered.json",
        "quant/harpoon_quant/measurement_registration.py", "quant/harpoon_quant/economic_gate_v2.py",
        "quant/harpoon_quant/economic_gate.py", "quant/harpoon_quant/calibration.py", "quant/harpoon_quant/scalar_svr.py",
    ]
    sources = {name: {"sha256": sha(root / name), "bytes": (root / name).stat().st_size} for name in names}
    load = lambda name: json.loads((root / name).read_text())
    wal = root / "quant/economic_experiment/study/optimizer.sqlite3-wal"
    if wal.stat().st_size:
        raise ValueError("NONEMPTY_WAL_REQUIRES_SEPARATELY_BOUND_READONLY_SNAPSHOT")
    sys.path.insert(0, str(root / "quant"))
    from harpoon_quant.recursive import Journal
    db = root / "quant/economic_experiment/study/optimizer.sqlite3"
    journal = Journal.__new__(Journal)  # Deliberately do not call the writer constructor.
    journal.db = sqlite3.connect(db.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    journal.integrity_report = {}
    try:
        journal.verify()
        keys = [r[0] for r in journal.db.execute("SELECT k FROM optimizer_state ORDER BY k")]
        trial_keys = [k for k in keys if k.startswith(("trial:", "economic:trial:"))]
        budget = journal.get("budget")
        sequence, head = journal.db.execute("SELECT seq,h FROM optimizer_audit ORDER BY seq DESC LIMIT 1").fetchone()
        quant = {"source": names[0], "read_mode": "SQLITE_MODE_RO_IMMUTABLE_WAL_EMPTY",
                 "budget": budget, "unused_local_capacity_arithmetic": budget["limit"] - budget["spent"],
                 "capacity_is_new_authorization": False,
                 "audit_head": {"sequence": sequence, "hash": head}, "integrity": journal.integrity_report,
                 "trial_record_count": len(trial_keys), "trial_keys": trial_keys,
                 "measurement_reservations": [k for k in keys if k.startswith("measurement:funded:v1:")],
                 "trial_records_with_native_v2_identity_at_top_level": [k for k in trial_keys
                     if all(field in journal.get(k) for field in ("attempt_id", "code_hash", "data_hash", "policy_hash"))]}
    finally:
        journal.close()
    ultimate = load("evidence/ultimate/registry.json")
    records = ultimate["chain"]
    trial = ultimate["trial"]
    registrations = [r for r in records if r["action"] == "REGISTER"]
    u = {"chain": chain_check(records, canonical=True, previous_field="previous", initial="GENESIS"),
         "exported_trial": {k: trial[k] for k in ("id", "slots", "status", "attempts", "registeredAt", "protocolHash", "codeHash", "datasetHash")},
         "registered_trial_ids_in_chain": [r["trialId"] for r in registrations],
         "registered_ids_without_full_trial_object_in_export": [r["trialId"] for r in registrations if r["trialId"] != trial["id"]],
         "complete_family_spent": None,
         "null_reason": "The export includes one trial object and a chain with other registered IDs; this is not the full cumulative family state."}
    branch = load("evidence/integral_30_12_1/review/branches/history_extension.json")
    u["retained_branch_review"] = {"source": names[8], "old_slots": branch["old_slots"],
        "branch_slots_documented": branch["branch_slots"], "additional_slots_documented": branch["additional_slots"],
        "additional_records": branch["additional_records"],
        "original_branch_trial_store_in_this_integral": None,
        "status": "DOCUMENTED_IN_RETAINED_REVIEW_NOT_NEWLY_VERIFIED_FROM_ORIGINAL_BRANCH_STORE"}
    corrections = []
    for registration, history, canonical, previous in (
        (names[10], names[11], True, "previous"), (names[12], names[13], False, "previous_hash")):
        r = load(registration)
        rows = [json.loads(line) for line in (root / history).read_text().splitlines() if line]
        c = chain_check(rows, canonical=canonical, previous_field=previous)
        registered_hash = rows[0].get("registration_sha256") or rows[0].get("payload", {}).get("registration_sha256")
        c["registration_hash_verified"] = registered_hash == sources[registration]["sha256"]
        corrections.append({"trial_id": r["trial_id"], "registration": registration, "journal": history,
            "new_variants": r.get("new_candidate_variants", r.get("new_variant_count")), "fits_allowed": r["fits_allowed"],
            "financial_acceptance_allowed": r["financial_acceptance_allowed"], "chain": c})
    tp = load("evidence/tp32/report.json")
    report = {"schema": "HARPOON_RETAINED_HISTORY_AUDIT_1", "source_root": str(root),
        "scope": "READ_ONLY_LOCAL_INTEGRITY_AND_RETAINED_LINEAGE_NOT_EXTERNAL_AUTHENTICATION",
        "quant": quant, "ultimate": u,
        "tp32": {"trial_count": tp["trialCount"], "policies": list(tp["tables"]), "windows": tp["windows"], "promotion": tp["promotion"]},
        "correction_continuations": corrections,
        "source_manifest_global_count": load("evidence/integral_30_12_1/history/manifest.json")["global_deduplicated_total"],
        "global_deduplicated_search_total": None,
        "global_null_reason": "Different family units, incomplete native identities, missing full Ultimate trial and branch source state, and separately recorded continuation variants.",
        "observed_used_windows": {"ultimate": load("evidence/ultimate/report.json")["windows"], "tp32": tp["windows"]},
        "new_2026_10_market_data": load(names[14]), "corporate_actions_status": load(names[15])["importer_status"],
        "latest_protocol_status": {k: load(names[16]).get(k) for k in ("protocol_id", "status", "protocol_hash", "registration_performed")},
        "sources": sources, "source_bytes_unchanged_after_audit": all(sha(root / n) == v["sha256"] for n, v in sources.items()),
        "financial_experiments_executed": 0, "models_fitted": 0, "budget_reservations_created": 0,
        "execution_allowed": False, "financial_acceptance_allowed": False, "level7_accredited": False}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.source_root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"output": str(args.output.resolve()), "sha256": sha(args.output),
        "quant_budget": report["quant"]["budget"], "ultimate_chain": report["ultimate"]["chain"],
        "corrections_verified": all(x["chain"]["verified"] and x["chain"]["registration_hash_verified"] for x in report["correction_continuations"]),
        "global_search_total": None, "source_bytes_unchanged": report["source_bytes_unchanged_after_audit"]}))


if __name__ == "__main__":
    main()
