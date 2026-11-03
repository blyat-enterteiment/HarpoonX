"""Compare all Ruff findings with the explicitly reviewed frozen-source baseline.

No rule or individual diagnostic is suppressed. A matching baseline permits
the CI guard to pass while preserving Ruff's nonzero exit and complete output.
Any changed source, mode, configuration, inventory, version or finding requires
new review; a newly clean result is not silently substituted for frozen evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUFF_VERSION = "0.17.0"
PROFILE = "quant/ruff-roadmap9.toml"
CONFIGURATIONS = ("quant/pyproject.toml", PROFILE)
BASELINE_SCHEMA = "HARPOON_ROADMAP9_REVIEWED_LINT_BASELINE_1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def targets() -> list[str]:
    """One explicit file inventory, identical in local and CI invocation."""
    files = set((ROOT / "quant/harpoon_quant/roadmap9").rglob("*.py"))
    files.update((ROOT / "quant/tests").glob("test_roadmap9*.py"))
    files.update((ROOT / "tools").glob("*roadmap9*.py"))
    if not files:
        raise ValueError("LINT_SOURCE_INVENTORY_EMPTY")
    if any(not p.is_file() or not p.resolve().is_relative_to(ROOT) for p in files):
        raise ValueError("LINT_SOURCE_OUTSIDE_REPOSITORY_OR_MISSING")
    return sorted(str(p.relative_to(ROOT)) for p in files)


def input_snapshot(files: list[str]) -> dict[str, Any]:
    return {
        "target_files": files,
        "source_file_sha256": {name: sha256(ROOT / name) for name in files},
        "git_file_modes": {
            name: "100755" if (ROOT / name).stat().st_mode & 0o111 else "100644"
            for name in files
        },
        "configuration_sha256": {
            name: sha256(ROOT / name) for name in CONFIGURATIONS
        },
    }


def ruff_arguments(files: list[str]) -> list[str]:
    return ["check", "--config", PROFILE, "--no-cache", "--output-format", "json", *files]


def normalize_findings(raw: Any, files: list[str]) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise ValueError("RUFF_JSON_LIST_REQUIRED")
    normalized = []
    for item in raw:
        path = Path(item["filename"]).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError("RUFF_FINDING_OUTSIDE_REPOSITORY")
        name = str(path.relative_to(ROOT))
        if name not in files:
            raise ValueError("RUFF_FINDING_OUTSIDE_INVENTORY")
        row = {"path": name, "code": item["code"], "message": item["message"]}
        if not isinstance(row["code"], str) or not isinstance(row["message"], str):
            raise ValueError("RUFF_DIAGNOSTIC_IDENTITY")
        for location in ("location", "end_location"):
            point = item[location]
            if any(type(point[k]) is not int or point[k] < 1 for k in ("row", "column")):
                raise ValueError("RUFF_DIAGNOSTIC_LOCATION")
            row[location] = {k: point[k] for k in ("row", "column")}
        normalized.append(row)
    return sorted(normalized, key=finding_identity)


def finding_identity(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def compare_baseline(
    baseline: dict[str, Any],
    snapshot: dict[str, Any],
    findings: list[dict[str, Any]],
    arguments: list[str],
    version: str,
) -> dict[str, Any]:
    """Compare full inventories and diagnostics, including unexpected removals."""
    errors = []
    if baseline.get("schema") != BASELINE_SCHEMA:
        errors.append("BASELINE_SCHEMA")
    if version != "ruff " + RUFF_VERSION or baseline.get("ruff_version") != RUFF_VERSION:
        errors.append("RUFF_VERSION_MISMATCH")
    if baseline.get("ruff_arguments") != arguments:
        errors.append("RUFF_ARGUMENTS_OR_TARGET_INVENTORY_CHANGED")
    mismatches: dict[str, Any] = {}
    for key in ("target_files", "source_file_sha256", "git_file_modes", "configuration_sha256"):
        expected, actual = baseline.get(key), snapshot[key]
        if expected != actual:
            errors.append(key.upper() + "_CHANGED")
            if isinstance(expected, dict) and isinstance(actual, dict):
                mismatches[key] = {
                    name: {"expected": expected.get(name), "actual": actual.get(name)}
                    for name in sorted(expected.keys() | actual.keys())
                    if expected.get(name) != actual.get(name)
                }
            else:
                mismatches[key] = {"expected": expected, "actual": actual}
    expected_findings = baseline.get("findings")
    if not isinstance(expected_findings, list):
        errors.append("BASELINE_FINDINGS_LIST_REQUIRED")
        expected_findings = []
    expected_counts = Counter(finding_identity(row) for row in expected_findings)
    actual_counts = Counter(finding_identity(row) for row in findings)
    unexpected = [json.loads(row) for row in (actual_counts - expected_counts).elements()]
    missing = [json.loads(row) for row in (expected_counts - actual_counts).elements()]
    if unexpected:
        errors.append("UNREVIEWED_FINDINGS_PRESENT")
    if missing:
        errors.append("REVIEWED_FINDINGS_UNEXPECTEDLY_REMOVED")
    return {
        "errors": errors,
        "input_mismatches": mismatches,
        "unexpected_findings": unexpected,
        "missing_findings": missing,
    }


def check(output: Path, baseline_path: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    comparison: dict[str, Any] = {}
    before: dict[str, Any] = {}
    findings: list[dict[str, Any]] = []
    arguments: list[str] = []
    version = ""
    version_stderr = ""
    raw = ""
    stderr = ""
    returncode: int | None = None
    baseline_hash: str | None = None
    started = datetime.now(UTC).isoformat()
    try:
        files = targets()
        before = input_snapshot(files)
        arguments = ruff_arguments(files)
        baseline_hash = sha256(baseline_path)
        baseline = json.loads(baseline_path.read_text())
        version_process = subprocess.run(
            [sys.executable, "-m", "ruff", "--version"], cwd=ROOT,
            capture_output=True, text=True, timeout=30, check=False,
        )
        version, version_stderr = version_process.stdout.strip(), version_process.stderr
        if version_process.returncode:
            errors.append("RUFF_VERSION_COMMAND_FAILED")
        process = subprocess.run(
            [sys.executable, "-m", "ruff", *arguments], cwd=ROOT,
            capture_output=True, text=True, timeout=120, check=False,
        )
        raw, stderr, returncode = process.stdout, process.stderr, process.returncode
        findings = normalize_findings(json.loads(raw), files)
        if returncode != (1 if findings else 0):
            errors.append("RUFF_COMMAND_FAILED_OR_EXIT_INCONSISTENT")
        comparison = compare_baseline(baseline, before, findings, arguments, version)
        errors.extend(comparison["errors"])
        if input_snapshot(targets()) != before:
            errors.append("LINT_INPUTS_CHANGED_DURING_EXECUTION")
        if sha256(baseline_path) != baseline_hash:
            errors.append("LINT_BASELINE_CHANGED_DURING_EXECUTION")
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        errors.append(type(exc).__name__ + ":" + str(exc))
    (output / "ruff_raw.json").write_text(raw)
    (output / "ruff_stderr.txt").write_text(stderr)
    (output / "ruff_version.txt").write_text(version + "\n" + version_stderr)
    clean = returncode == 0 and not findings
    report = {
        "schema": "HARPOON_ROADMAP9_LINT_BASELINE_GUARD_1",
        "started_utc": started, "finished_utc": datetime.now(UTC).isoformat(),
        "baseline_file": str(baseline_path), "baseline_sha256": baseline_hash,
        "required_ruff_version": RUFF_VERSION, "observed_ruff_version": version,
        "ruff_arguments": arguments, "input_snapshot": before,
        "ruff_exit_code": returncode, "ruff_clean": clean,
        "finding_count": len(findings),
        "finding_counts_by_rule": dict(sorted(Counter(row["code"] for row in findings).items())),
        "findings": findings, "comparison": comparison, "errors": errors,
        "guard_passed": not errors,
        "verdict": "MATCHED_RECORDED_FINDINGS" if not errors else "FAIL",
        "rules_suppressed_by_guard": False,
        "raw_sha256": sha256(output / "ruff_raw.json"),
        "scope": "EXACT_VERSION_CONFIGURATION_SOURCE_AND_FINDING_BASELINE;NOT_UNIVERSAL_LINT_CLEANLINESS",
        "economic_results_modified": False, "execution_allowed": False,
    }
    (output / "lint_verdict.json").write_text(
        json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path,
                        default=ROOT / "research/roadmap9/lint_baseline.json")
    args = parser.parse_args()
    report = check(args.output, args.baseline)
    print(json.dumps({k: report[k] for k in
        ("guard_passed", "verdict", "ruff_clean", "finding_count", "finding_counts_by_rule", "errors")}))
    if not report["guard_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
