"""Evidence boundaries for the reused-history test bank; never a trading gate."""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

HYPOTHESES = (
    "H1_CAUSAL_PROFIT_PROTECTION",
    "H2_OVERNIGHT_GAP_RISK",
    "H3_SETUP_CONDITIONAL_GATE",
)
SCHEMA = "HARPOON_REUSED_EVIDENCE_1"


class EvidenceError(ValueError):
    """Missing, changed or contradictory evidence must stop this audit."""


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def contained(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    if Path(name).is_absolute() or ".." in Path(name).parts or not path.is_relative_to(root.resolve()):
        raise EvidenceError(f"UNSAFE_EVIDENCE_PATH: {name}")
    return path


def verify_files(root: Path, expected: Mapping[str, str]) -> dict[str, str]:
    if not expected:
        raise EvidenceError("EMPTY_HASH_MANIFEST")
    verified = {}
    for name, wanted in sorted(expected.items()):
        if not re.fullmatch(r"[0-9a-f]{64}", wanted):
            raise EvidenceError(f"INVALID_SHA256: {name}")
        path = contained(root, name)
        if not path.is_file():
            raise EvidenceError(f"MISSING_EVIDENCE: {name}")
        actual = digest(path)
        if actual != wanted:
            raise EvidenceError(f"SHA256_MISMATCH: {name}; expected={wanted}; actual={actual}")
        verified[name] = actual
    return verified


def load(path: Path) -> dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise EvidenceError(f"NONFINITE_JSON: {value}")

    def unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise EvidenceError(f"DUPLICATE_JSON_KEY: {key}")
            result[key] = value
        return result

    value = json.loads(path.read_bytes(), parse_constant=reject_constant, object_pairs_hook=unique_keys)
    if not isinstance(value, dict):
        raise EvidenceError(f"EXPECTED_JSON_OBJECT: {path.name}")
    return value


def no_new_claims(report: Mapping[str, Any], *, fresh_field_required: bool = True) -> None:
    required = ["execution_allowed", "level8_accredited"]
    if fresh_field_required:
        required.append("fresh_holdout")
    for key in required:
        if report.get(key) is not False:
            raise EvidenceError(f"UNSUPPORTED_CLAIM: {key}")
    if "observed_live_fills" in report and (
        type(report["observed_live_fills"]) is not int or report["observed_live_fills"] != 0
    ):
        raise EvidenceError("UNSUPPORTED_CLAIM: observed_live_fills")


def hypothesis_status(report: Mapping[str, Any]) -> dict[str, Any]:
    if type(report.get("new_strategy_variants_executed")) is not int or report["new_strategy_variants_executed"] != 0:
        raise EvidenceError("UNEXPECTED_STRATEGY_SEARCH")
    results = report.get("hypothesis_results")
    if not isinstance(results, dict) or set(results) != set(HYPOTHESES):
        raise EvidenceError("HYPOTHESIS_NAMESPACE_MISMATCH")
    for name, result in results.items():
        if result != {"nominal": None, "stress": None, "status": "NOT_EXECUTED_BUDGET_BLOCKED"}:
            raise EvidenceError(f"UNSUPPORTED_HYPOTHESIS_RESULT: {name}")
    return {name: {"status": "INCONCLUSIVE_NOT_MEASURED", "nominal_net_usd": None,
                   "stress_net_usd": None, "new_validation": False,
                   "reason": "GLOBAL_BUDGET_UNRECONCILED"} for name in HYPOTHESES}


def account_record(source: str, name: str, net: float, count: int, *, virtual: bool = False) -> dict[str, Any]:
    if isinstance(net, bool) or not math.isfinite(net) or type(count) is not int or count < 0:
        raise EvidenceError(f"INVALID_ACCOUNT_METRICS: {source}:{name}")
    return {
        "id": f"{source}:{name}", "source_report": source, "source_account": name,
        "history": "REUSED", "execution": "MODELED", "costs": "ASSUMED_NOT_INVOICED",
        "result_scope": "ARCHIVED_RESULT_NOT_NEW_ESTIMATE", "net_usd": net,
        "activity_count": count, "activity_unit": "BUY_ORDERS" if virtual else "CLOSED_CAMPAIGNS",
        "effect": "UNIDENTIFIED_NO_BUYS" if virtual and count == 0 else "DESCRIPTIVE_ONLY",
        "new_validation": False, "promotion_allowed": False,
    }
