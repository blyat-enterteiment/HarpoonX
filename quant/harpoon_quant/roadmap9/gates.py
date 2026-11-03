"""Evidence-bound completion receipts for the immutable 49-contract roadmap.

The catalog is not a test runner. This module verifies the referenced evidence
bytes and their declared scope, then computes phase decisions. Missing or
incompatible evidence cannot become a pass. Production authority is never
granted by a locally generated receipt.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

ALLOWED_RESULTS = {"PASS", "FAIL", "BLOCKED", "NOT_RUN"}
OBSERVED_SCOPES = {"OBSERVED_EXECUTION", "PROSPECTIVE_ECONOMICS", "EXTERNAL_REVIEW", "OPERATIONAL_AUTHORIZATION"}


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evidence_reference(root: Path, path: Path) -> dict[str, str]:
    absolute = path.resolve()
    if not absolute.is_relative_to(root.resolve()) or not absolute.is_file():
        raise ValueError("EVIDENCE_PATH_OUTSIDE_REPOSITORY_OR_MISSING")
    return {"path": str(absolute.relative_to(root.resolve())), "sha256": file_hash(absolute)}


def verify_references(root: Path, references: list[dict[str, str]]) -> list[str]:
    errors = []
    for reference in references:
        path = (root / reference["path"]).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            errors.append("EVIDENCE_MISSING_OR_UNSAFE:" + reference["path"])
        elif file_hash(path) != reference["sha256"]:
            errors.append("EVIDENCE_HASH_MISMATCH:" + reference["path"])
    return errors


def close_plan(plan: dict[str, Any], claims: list[dict[str, Any]], root: Path,
               *, source_commit: str, source_manifest: list[dict[str, str]]) -> dict[str, Any]:
    """Conclude this work cycle with a verdict for every original contract.

    A blocked phase can contain implemented, successfully tested components.
    `implementation_status` and `result` intentionally remain separate. A PASS
    on historical engineering never satisfies a later observed-evidence gate.
    """
    expected = {v["id"]: v for v in plan["validators"]}
    if len(expected) != 49 or len({c["validator_id"] for c in claims}) != len(claims):
        raise ValueError("ROADMAP_CONTRACT_IDENTIFIERS")
    actual = {c["validator_id"]: c for c in claims}
    if set(actual) != set(expected):
        raise ValueError("ALL_49_CONTRACTS_REQUIRE_EXPLICIT_VERDICTS")
    source_errors = verify_references(root, source_manifest)
    if not source_manifest or not any(
        reference["path"].startswith(("quant/", "tools/", "src/"))
        and reference["path"].endswith((".py", ".js", ".ts", ".cjs", ".tsx"))
        for reference in source_manifest
    ):
        source_errors.append("CODE_SOURCE_MANIFEST_REQUIRED")
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        source_errors.append("VERSIONED_SOURCE_COMMIT_REQUIRED")
    rows = []
    for identifier, contract in expected.items():
        claim = dict(actual[identifier])
        if claim["result"] not in ALLOWED_RESULTS:
            raise ValueError("VALIDATOR_RESULT")
        if not claim.get("observed_value") or not claim.get("remaining_work"):
            raise ValueError("OBSERVATION_AND_SCOPE_REQUIRED:" + identifier)
        references = claim.get("evidence", [])
        errors = verify_references(root, references) + source_errors
        if claim["result"] == "PASS":
            if not references:
                errors.append("PASS_REQUIRES_EVIDENCE")
            if claim.get("origin") not in contract["accepted_evidence_origins"]:
                errors.append("EVIDENCE_ORIGIN_NOT_ACCEPTED")
            if contract["validation_scope"] in OBSERVED_SCOPES:
                # This local closer does not validate external authority. Signed
                # source/owner/review attestations use the separate admission API.
                errors.append("EXTERNAL_OR_PROSPECTIVE_GATE_NOT_CLOSED_BY_LOCAL_TESTS")
        if errors:
            claim["result"] = "BLOCKED"
        claim["evidence_errors"] = errors
        claim["name"] = contract["name"]
        claim["phase"] = contract["phase"]
        claim["validation_scope"] = contract["validation_scope"]
        rows.append(claim)
    phases = []
    for phase in plan["phases"]:
        group = [v for v in rows if v["phase"] == phase["id"]]
        results = Counter(v["result"] for v in group)
        candidate_decisions = sorted({v["candidate_decision"] for v in group
                                      if v.get("candidate_decision")})
        decision = ("BLOCKED" if results["BLOCKED"] or results["NOT_RUN"] else
                    "REJECTED_CANDIDATE" if results["FAIL"] or
                    "REJECTED_CANDIDATE" in candidate_decisions else "READY_FOR_RESEARCH")
        phases.append({"id": phase["id"], "title": phase["title"], "phase_decision": decision,
                       "results": dict(results), "validator_ids": phase["validator_ids"],
                       "candidate_decisions": candidate_decisions,
                       "dependent_phase_promotion_allowed": False})
    return {"schema": "HARPOON_ROADMAP_WORK_CYCLE_CLOSURE_1", "source_commit": source_commit,
            "plan_sha256": hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False).encode()).hexdigest(),
            "plan_hash_serialization": "CANONICAL_JSON_NOT_FILE_BYTES",
            "work_cycle_concluded": True, "all_phases_approved": False,
            "validator_count": len(rows), "result_counts": dict(Counter(v["result"] for v in rows)),
            "validators": rows, "phases": phases, "source_manifest": source_manifest,
            "source_integrity_errors": source_errors,
            "execution_allowed": False, "live_approved": False, "level9_accredited": False,
            "economic_improvement_accredited": False, "external_review_completed": False,
            "scope": "EXECUTED_OFFLINE_WORK_WITH_EXPLICIT_REMAINING_OBSERVED_AND_EXTERNAL_REQUIREMENTS"}


def render_markdown(receipt: dict[str, Any]) -> str:
    """Generate the readable status from the same machine-readable verdicts."""
    lines = ["# HARPOON — cierre del ciclo de trabajo del plan", "",
             "Este recibo distingue implementación probada de aceptación económica y operativa.",
             "Las fases con requisitos externos pendientes permanecen bloqueadas.", "",
             "| Fase | Resultado | Contratos |", "| --- | --- | --- |"]
    for phase in receipt["phases"]:
        counts = ", ".join(f"{k}: {v}" for k, v in phase["results"].items())
        lines.append(f"| {phase['id']} — {phase['title']} | {phase['phase_decision']} | {counts} |")
    lines += ["", "## Evidencia y trabajo restante", "",
              "| Validador | Resultado | Observado | Pendiente o límite del alcance |",
              "| --- | --- | --- | --- |"]
    for row in receipt["validators"]:
        observed = str(row["observed_value"]).replace("|", "/").replace("\n", " ")
        remaining = str(row["remaining_work"]).replace("|", "/").replace("\n", " ")
        lines.append(f"| {row['validator_id']} — {row['name']} | {row['result']} | {observed} | {remaining} |")
    lines += ["", "Ningún resultado de este documento habilita órdenes, acredita nivel 9 o sustituye revisión externa.", ""]
    return "\n".join(lines)
