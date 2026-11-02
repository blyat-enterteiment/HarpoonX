"""Retain the initial full run and revalidate only the SQLite error-boundary change."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EV = ROOT / "consolidation_evidence"
APP = ROOT / "consolidation_work/HARPOON_XXXUltimate_30_12_1"
QA = EV / "final_regression"
initial = json.loads((QA / "all_summary.json").read_text())
assert initial["tests"] == 919
assert [c["name"] for c in initial["checks"] if not c["passed"]] == ["storage_ruff"]
original = QA / "initial_full_run"
original.mkdir(exist_ok=False)
for path in QA.iterdir():
    if path.is_file() and not path.name.startswith("initial_"):
        shutil.copy2(path, original / path.name)
spec = importlib.util.spec_from_file_location("release_verifier", APP / "tools/verify_remediation.py")
assert spec and spec.loader
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
names = {"store30_deadline_test", "storage_ruff", "storage_mypy"}
rechecks = []
for check in initial["checks"]:
    if check["name"] in names:
        rechecks.append(runner.execute(check["name"], check["command"], APP, QA))
assert all(c["passed"] for c in rechecks)
by_name = {c["name"]: c for c in rechecks}
final = dict(initial)
final["checks"] = [by_name.get(c["name"], c) for c in initial["checks"]]
final["passed"] = all(c["passed"] for c in final["checks"])
final["validation_lineage"] = {
    "initial_full_run": "initial_full_run/all_summary.json",
    "initial_functional_cases_passed": 919,
    "initial_static_failure": "Ruff BLE001: broad exception catch in runtime/store.py",
    "runtime_change": "Expected request/SQLite/zlib exceptions are acknowledged; unexpected failures terminate the worker and require transport reconciliation.",
    "reexecuted_checks": rechecks,
    "repeated_functional_cases": 14,
    "distinct_functional_cases": 919,
    "all_919_rerun_after_targeted_change": False,
    "scope_reason": "Only runtime/store.py exception boundary changed. Replay fingerprints do not include this worker. SQLite/process/acknowledgement tests and Python static checks were repeated; strategy and risk sources remained identical.",
}
(QA / "all_summary.json").write_text(json.dumps(final, ensure_ascii=False, indent=2) + "\n")
frozen_path = EV / "frozen_sources.json"
frozen = json.loads(frozen_path.read_text())
changed = []
for name, old_hash in frozen["files"].items():
    new_hash = hashlib.sha256((APP / name).read_bytes()).hexdigest()
    if new_hash != old_hash:
        changed.append({"path": name, "before": old_hash, "after": new_hash})
assert [c["path"] for c in changed] == ["runtime/store.py"]
frozen["files"]["runtime/store.py"] = changed[0]["after"]
frozen["post_regression_change"] = {
    "initial_manifest": "initial_frozen_sources.json", "changes": changed,
    "validation": "final_regression/all_summary.json#validation_lineage",
}
frozen_path.write_text(json.dumps(frozen, ensure_ascii=False, indent=2) + "\n")
supplement = {
    "initial_evidence": "port_validation.json",
    "initial_evidence_unchanged": True,
    "cause": "Root release Ruff configuration includes BLE001; the earlier targeted Ruff selection did not.",
    "change": changed,
    "checks": rechecks,
    "review": "A second agent reviewed the explicit recoverable exception tuple and confirmed that replay fingerprints do not bind store.py; not an independent external audit.",
    "financial_trials": 0,
    "static_criteria_relaxed": False,
}
(EV / "storage/final_exception_boundary_review.json").write_text(json.dumps(supplement, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"passed": final["passed"], "distinct_tests": final["tests"], "repeated_tests": 14, "changes": changed}, indent=2))
