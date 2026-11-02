"""Preserve the complete initial run and recheck only the two corrected files."""
from __future__ import annotations

import difflib
import hashlib
import importlib.util
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "level5_work/HARPOON_XXXUltimate_30_12_0"
EV = ROOT / "level5_evidence"
QA = EV / "final_regression"


def read(p):
    return json.loads(p.read_text())


def write(p, value):
    p.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


spec = importlib.util.spec_from_file_location("release_runner", APP / "tools/verify_remediation.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
original = read(QA / "initial_all_summary.json")
assert original["tests"] == 902
assert {c["name"] for c in original["checks"] if not c["passed"]} == {"ruff", "mypy"}
jobs = [(c["name"] + "_after_fix", c["command"], Path(c["cwd"]), QA)
        for c in original["checks"] if c["name"] in {"ruff", "mypy"}]
jobs.extend(("recheck_" + name, [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", name + ".py", "-v"], APP / "quant", QA)
            for name in ["test_causal_panel", "test_observation_stream"])
with ThreadPoolExecutor(max_workers=4) as pool:
    checks = list(pool.map(lambda arguments: runner.execute(*arguments), jobs))
write(QA / "post_fix_summary.json", {"scope": "Targeted recheck after import ordering and explicit stream selection type guard",
      "checks": checks, "passed": all(c["passed"] for c in checks),
      "repeated_tests_not_additional_cases": sum(c.get("tests") or 0 for c in checks), "financial_trials_created": 0})
assert all(c["passed"] for c in checks)
diff = []
for relative in ["quant/harpoon_quant/causal_panel.py", "quant/tests/test_observation_stream.py"]:
    before = (QA / "before_static_fix" / relative).read_text().splitlines(keepends=True)
    after = (APP / relative).read_text().splitlines(keepends=True)
    diff.extend(difflib.unified_diff(before, after, fromfile="before/" + relative, tofile="after/" + relative))
(QA / "static_fix.patch").write_text("".join(diff))
updated = read(QA / "initial_all_summary.json")
for i, check in enumerate(updated["checks"]):
    if check["name"] in {"ruff", "mypy"}:
        replacement = dict(next(c for c in checks if c["name"] == check["name"] + "_after_fix"))
        replacement["name"] = check["name"]
        replacement["supersedes_failed_check_in"] = "initial_all_summary.json"
        updated["checks"][i] = replacement
updated["passed"] = all(c["passed"] for c in updated["checks"])
updated["post_full_suite_changes"] = {
    "patch": "static_fix.patch", "targeted_verification": "post_fix_summary.json",
    "initial_summary": "initial_all_summary.json",
    "interpretation": "902 unique functional cases passed in full run; only two Python files then corrected and their 28 affected cases rechecked. Static failures superseded by passing executions. Repeated cases not added to total."}
write(QA / "all_summary.json", updated)
freeze = read(EV / "frozen_source_hashes_before_static_fix.json")
now = {name: hashlib.sha256((APP / name).read_bytes()).hexdigest() for name in freeze["files"]}
changed = [name for name, value in now.items() if value != freeze["files"][name]]
assert changed == ["quant/harpoon_quant/causal_panel.py"], changed
write(EV / "frozen_source_hashes.json", {"version": "30.12.0", "stage": "AFTER_TARGETED_STATIC_FIX_VERIFICATION",
      "changes_since_full_run": changed, "files": now})
print(json.dumps({"unique_functional_tests": updated["tests"], "static_pass": updated["passed"],
                  "targeted_repeated_tests": sum(c.get("tests") or 0 for c in checks), "production_changes": changed}))
