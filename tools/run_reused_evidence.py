"""Audit or reproduce existing evidence without running or validating H1-H3."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from audit_research_budget import audit
from harpoon_quant.evidence_scope import (
    SCHEMA,
    EvidenceError,
    account_record,
    digest,
    hypothesis_status,
    load,
    no_new_claims,
    verify_files,
)

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = "research/reused_evidence/protocol.json"
CAUSAL = "evidence/causal_integrity/report.json"
FORENSIC = "evidence/forensic_opportunity/report.json"
COMPOUND = "evidence/compound_swing/report.json"
VIRTUAL = "evidence/virtual_ab/purged_report.json"


def write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def inspect(root: Path = ROOT) -> dict[str, Any]:
    protocol = load(root / PROTOCOL)
    if (protocol.get("schema") != "HARPOON_REUSED_EVIDENCE_PROTOCOL_1"
            or type(protocol.get("new_policy_budget_units")) is not int
            or protocol["new_policy_budget_units"] != 0
            or protocol.get("new_validation_allowed") is not False):
        raise EvidenceError("PROTOCOL_SCOPE_CHANGED")
    verified = verify_files(root, protocol["bound_files"])
    reports = {name: load(root / name) for name in (CAUSAL, FORENSIC, COMPOUND, VIRTUAL)}
    for name, report in reports.items():
        no_new_claims(report, fresh_field_required=name != FORENSIC)
    hypotheses = hypothesis_status(reports[CAUSAL])
    budget = audit(root)
    if budget != load(root / "research/causal_integrity/budget_audit.json"):
        raise EvidenceError("BUDGET_AUDIT_CHANGED")
    if budget["new_measurements_allowed"] is not False or budget["global_history_complete"] is not False:
        raise EvidenceError("BUDGET_SCOPE_CHANGED_REVIEW_REQUIRED")
    provenance = reports[FORENSIC]["provenance"]
    if (provenance.get("execution") != "MODELED_OHLCV"
            or provenance.get("capture_timestamps_are_original_market_receipts") is not False):
        raise EvidenceError("EXECUTION_PROVENANCE_CHANGED")

    rows = []
    for key, value in sorted(reports[CAUSAL]["accounts"].items()):
        rows.append(account_record(CAUSAL, key, value["net_usd"], value["trades"]))
    for key, value in sorted(reports[COMPOUND]["accounts"].items()):
        rows.append(account_record(COMPOUND, key, value["net_usd"], value["trades"]))
    for key, value in sorted(reports[VIRTUAL]["accounts"].items()):
        rows.append(account_record(VIRTUAL, key, value["net"], value["buys"], virtual=True))
    if len({row["id"] for row in rows}) != len(rows):
        raise EvidenceError("DUPLICATE_ACCOUNT_ID")

    # Relations document dependence, not an estimate of effective sample size.
    inputs = {name: report.get("input_sha256", {}) for name, report in reports.items()}
    inputs[CAUSAL] = load(root / "research/causal_integrity/protocol.json")["bound_files"]
    shared: dict[str, dict[str, Any]] = {}
    for name, hashes in inputs.items():
        for path, sha in hashes.items():
            if "/raw/" not in path and not path.endswith("research_dataset.json"):
                continue
            entry = shared.setdefault(sha, {"paths": [], "reports": []})
            entry["paths"] = sorted(set(entry["paths"] + [path]))
            entry["reports"] = sorted(set(entry["reports"] + [name]))

    return {
        "schema": SCHEMA, "source_head": protocol["source_head"],
        "protocol_sha256": digest(root / PROTOCOL), "verified_source_files": len(verified),
        "source_sha256": verified, "history": "REUSED", "execution": "MODELED",
        "observed_fill_receipts_in_scope": 0, "observed_cost_invoices_in_scope": 0,
        "scope": "ARCHIVED_EVIDENCE_CLASSIFICATION_AND_OPTIONAL_EXACT_REPRODUCTION",
        "fresh_holdout": False, "new_validation": False, "new_strategy_variants_executed": 0,
        "new_policy_budget_units": 0, "hypothesis_results": hypotheses, "budget": budget,
        "accounts": rows, "archived_account_records": len(rows),
        "independent_market_sample_count": None,
        "dependence": {"same_market_across_policies_and_cost_scenarios": True,
                       "control_corrected_are_paired_reproductions": True,
                       "forensic_is_derived_not_an_additional_account": True,
                       "shared_inputs_by_sha256": shared,
                       "warning": "File counts, variants, scenarios and reproductions are not independent events."},
        "forensic": {"source_report": FORENSIC, "entry_candidates": reports[FORENSIC]["entry_candidate_rows"],
                     "decisions": reports[FORENSIC]["decisions_reproduced"], "provenance": provenance,
                     "terminal_labels_are_not_predictors": True},
        "verdict": "NO_NEW_VALIDATION_H1_H2_H3_INCONCLUSIVE",
        "promotion_allowed": False, "execution_allowed": False, "level8_accredited": False,
        "limitations": ["Internal evidence audit, not external validation.",
                        "Hashes verify bytes and lineage, not market truth or profitability.",
                        "Reproduction does not create new history or observed fills.",
                        "This layer cannot admit PAPER, LIVE, synthetic or unseen datasets by relabeling them.",
                        "No inference of strategy equivalence from inactive A/B accounts."],
    }


def reproduce_existing(work: Path, root: Path) -> list[dict[str, Any]]:
    jobs = [
        ("forensic", "tools/run_forensic_opportunity.py", "evidence/forensic_opportunity/sha256.json", ""),
        ("causal", "tools/run_causal_integrity.py", "evidence/causal_integrity/sha256.json", "evidence"),
    ]
    checks = []
    for name, script, manifest, subdir in jobs:
        output = work / name
        start = time.perf_counter()
        env = {**os.environ, "PYTHONPATH": f"{root / 'quant'}:{root / 'tools'}", "OPENBLAS_NUM_THREADS": "1"}
        process = subprocess.run([sys.executable, script, "--output-dir", str(output)],
                                 cwd=root, env=env, capture_output=True, text=True, timeout=240, check=False)
        (work / f"{name}.log").write_text(process.stdout + process.stderr)
        if process.returncode:
            raise EvidenceError(f"REPRODUCTION_FAILED: {name}; {process.stderr[-1500:]}")
        expected = load(root / manifest)
        checked = verify_files(output / subdir, expected)
        checks.append({"family": name, "matched_artifacts": len(checked),
                       "artifact_sha256": checked, "elapsed_seconds": time.perf_counter() - start,
                       "result": "EXACT_ARCHIVED_REPRODUCTION", "new_validation": False})
    return checks


def run(output: Path, *, reproduce: bool = False, root: Path = ROOT) -> dict[str, Any]:
    started = time.perf_counter()
    if output.exists():
        raise EvidenceError("OUTPUT_ALREADY_EXISTS_USE_NEW_DIRECTORY")
    report = inspect(root)
    # Stage in a temporary directory: failed verification cannot leave a PASS delivery.
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="harpoon_reused_") as directory:
        work = Path(directory)
        checks = reproduce_existing(work, root) if reproduce else []
        # Detect input changes during a replay before publishing its classification.
        if inspect(root) != report:
            raise EvidenceError("INPUTS_CHANGED_DURING_RUN")
        output.mkdir(exist_ok=False)
        write(output / "report.json", report)
        write(output / "sha256.json", {"report.json": digest(output / "report.json")})
        write(output / "execution.json", {
            "schema": "HARPOON_REUSED_EVIDENCE_EXECUTION_1",
            "mode": "REPRODUCE_EXISTING" if reproduce else "CLASSIFY_ARCHIVED",
            "report_sha256": digest(output / "report.json"), "reproductions": checks,
            "compound_virtual_replay_this_run": "NOT_RERUN_HASH_AND_REPORT_INSPECTION_ONLY",
            "h1_h2_h3_this_run": "NOT_EXECUTED", "new_validation": False,
            "elapsed_seconds": time.perf_counter() - started, "python": sys.version,
        })
        for path in work.glob("*.log"):
            (output / path.name).write_bytes(path.read_bytes())
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--reproduce-existing", action="store_true")
    args = parser.parse_args()
    try:
        report = run(args.output_dir.resolve(), reproduce=args.reproduce_existing)
    except (EvidenceError, OSError, KeyError, TypeError, ValueError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"status": "FAIL_CLOSED", "error": str(error), "new_validation": False}), file=sys.stderr)
        return 2
    print(json.dumps({"status": "AUDIT_COMPLETE", "verdict": report["verdict"],
                      "source_files": report["verified_source_files"], "new_validation": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
