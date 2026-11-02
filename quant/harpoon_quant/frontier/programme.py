"""USD5m planning envelope and evidence gates. Never commits expenditure."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..core import digest
from .contracts import require


def validate_programme(programme: dict[str, Any]) -> dict[str, Any]:
    require(programme.get("schema") == "HARPOON_RD_PROGRAMME_1", "PROGRAMME_SCHEMA")
    require(
        programme.get("currency") == "USD"
        and programme.get("planning_budget_usd") == 5_000_000,
        "EXPLICIT_USD5M_PLANNING_ENVELOPE",
    )
    packages = programme["work_packages"]
    require(
        isinstance(packages, list)
        and len({p["id"] for p in packages}) == len(packages),
        "WORK_PACKAGE_IDS",
    )
    total = 0
    for p in packages:
        require(
            type(p["budget_usd"]) is int and p["budget_usd"] > 0, "INTEGER_USD_BUDGET"
        )
        require(
            type(p["spent_usd"]) is int and 0 <= p["spent_usd"] <= p["budget_usd"],
            "SPEND_ENVELOPE",
        )
        total += p["budget_usd"]
    require(total == 5_000_000, "BUDGET_DOES_NOT_RECONCILE")
    ids = [g["id"] for g in programme["gates"]]
    require(
        len(ids) == len(set(ids))
        and all(g["requirements"] for g in programme["gates"]),
        "GATE_IDS_OR_REQUIREMENTS",
    )
    for g in programme["gates"]:
        require(
            all(
                parent in ids and ids.index(parent) < ids.index(g["id"])
                for parent in g["depends_on"]
            ),
            "GATE_DEPENDENCY_ORDER",
        )
    return {
        "valid": True,
        "planning_budget_usd": total,
        "reported_spent_usd": sum(p["spent_usd"] for p in packages),
        "financial_authorization": False,
        "institutional_endorsement": False,
        "programme_hash": digest(programme),
    }


def evidence_gate(
    programme: dict[str, Any], gate_id: str, artifacts: list[dict[str, Any]], root: Path
) -> dict[str, Any]:
    validate_programme(programme)
    matches = [g for g in programme["gates"] if g["id"] == gate_id]
    require(len(matches) == 1, "UNKNOWN_GATE")
    gate = matches[0]
    verified = set()
    for a in artifacts:
        path = (root / a["path"]).resolve()
        require(path.is_relative_to(root.resolve()) and path.is_file(), "EVIDENCE_PATH")
        require(
            hashlib.sha256(path.read_bytes()).hexdigest() == a["sha256"],
            "EVIDENCE_HASH",
        )
        require(a["id"] not in verified, "DUPLICATE_EVIDENCE_ID")
        verified.add(a["id"])
    missing = sorted(set(gate["requirements"]) - verified)
    # Hash existence does not establish scientific correctness, signer identity or financial approval.
    return {
        "gate": gate_id,
        "artifacts_present_and_intact": not missing,
        "missing": missing,
        "dependencies": gate["depends_on"],
        "dependency_approvals_verified": False,
        "scientific_review_passed": False,
        "external_audit_verified": False,
        "spending_authorized": False,
        "promotion_authorized": False,
        "level9_accredited": False,
    }
