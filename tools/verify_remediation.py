"""Reproduce the affected release gates without a broker or financial trial.

Node fixtures use their existing synthetic test clock. Every file runs in its
own process; TAP counts individual cases, not merely test-file containers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NODE_SUITES = (
    "store30_deadline_test.cjs",
    "collect_runtime_evidence_test.cjs",
    "xxx_test.cjs",
    "xxx_conformance_test.cjs",
    "xxx_health_test.cjs",
    "xxx_selector_test.cjs",
    "xxx_tp32_test.cjs",
    "xxx_operational_test.cjs",
    "xxx_partial_entry_risk_test.cjs",
    "core5_runtime_test.cjs",
    "ultimate_test.cjs",
    "quant_bridge_test.cjs",
    "quant_svr_integration_test.cjs",
    "quant_discovery_regression_test.cjs",
    "xxx_session_regression_test.cjs",
    "quant_remediation_integration_test.cjs",
    "quant_net_ledger_test.cjs",
    "quant_net_continuity_test.cjs",
    "quant_coordinator_replay_test.cjs",
    "quant_autonomy_integration_test.cjs",
    "quant_observation_archive_test.cjs",
    "quant_dashboard_evidence_test.cjs",
    "funded_comparison_test.cjs",
    "funded_operating_reserve_test.cjs",
    "level4_runtime_integration_test.cjs",
    "level4_readiness_test.cjs",
    "quant_observation_snapshot_test.cjs",
    "level5_readiness_test.cjs",
    "integral_distribution_test.cjs",
)


def execute(name: str, command: list[str], cwd: Path, output: Path) -> dict:
    started = time.perf_counter()
    logfile = output / (name + ".log")
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", HARPOON_QA_OUTPUT_DIR=str(output),
                       HARPOON_QUANT_PYTHON=sys.executable,
                       PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""))
    if name == "ultimate_test":
        # This inherited suite declares a historical cutoff after the Oct15
        # fixture used by other suites. Preserve its cutoff and advance only
        # its synthetic test clock to a later regular trading session.
        environment["HARPOON_TEST_CLOCK_ANCHOR"] = "2026-10-30T15:00:00Z"
    with logfile.open("w") as stream:
        try:
            completed = subprocess.run(
                command, cwd=cwd, env=environment, stdout=stream,
                stderr=subprocess.STDOUT, timeout=600, check=False,
            )
            code = completed.returncode
        except subprocess.TimeoutExpired:
            stream.write("\nRELEASE_GATE_TIMEOUT_600_SECONDS\n")
            code = 124
    content = logfile.read_text()
    result = {
        "name": name, "command": command, "cwd": str(cwd), "exit_code": code,
        "duration_seconds": time.perf_counter() - started,
        "log": logfile.name,
        "log_sha256": hashlib.sha256(logfile.read_bytes()).hexdigest(),
    }
    if "--test" in command or name == "level5_readiness_test":
        for field in ("tests", "pass", "fail", "cancelled", "skipped", "todo"):
            found = re.findall(r"^# " + field + r" (\d+)\s*$", content, re.MULTILINE)
            result[field] = int(found[-1]) if found else None
        result["passed"] = code == 0 and result["tests"] is not None and result["fail"] == 0
    elif "unittest" in command:
        found = re.search(r"Ran (\d+) tests? in", content)
        result["tests"] = int(found[1]) if found else None
        result["passed"] = code == 0 and result["tests"] is not None and "\nOK" in content
    else:
        result["passed"] = code == 0
    print(json.dumps({k: result.get(k) for k in ("name", "exit_code", "tests", "passed")}), flush=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("all", "node", "python", "static"), default="all")
    parser.add_argument("--output", type=Path, default=ROOT / "evidence" / "remediation_runs")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    checks = []
    if args.suite in {"all", "node", "static"}:
        checks.append(execute("typescript_build", ["node", "node_modules/typescript/bin/tsc", "-p", "tsconfig.xxx.json"], ROOT, output))
        if not checks[-1]["passed"]:
            (output / (args.suite + "_summary.json")).write_text(json.dumps({"checks": checks, "passed": False}, indent=2) + "\n")
            return 1
    if args.suite in {"all", "node"}:
        for filename in NODE_SUITES:
            command = [
                "node", "--no-use-env-proxy", "--require", "./tools/quant_clock.cjs",
                "--test", "--test-isolation=none", "--test-reporter=tap", "--test-force-exit", "--test-timeout=30000",
                "tools/" + filename,
            ]
            if filename == "level5_readiness_test.cjs":
                # Nested isolated replays alter process hooks. Execute this
                # test module directly and count its individual TAP cases;
                # a test-runner wrapper can collapse them to one file result.
                command = ["node", "--no-use-env-proxy", "--require", "./tools/quant_clock.cjs", "--test-reporter=tap", "tools/" + filename]
            checks.append(execute(filename[:-4], command, ROOT, output))
    if args.suite in {"all", "python"}:
        checks.append(execute("quant_unittest", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], ROOT / "quant", output))
        checks.append(execute("integral_installer_unittest", [sys.executable, "-m", "unittest", "discover", "-s", "tools", "-p", "test_ultimate_install.py", "-v"], ROOT, output))
    if args.suite in {"all", "static"}:
        for filename in ("runtime/store30.cjs", "runtime/discovery.cjs", "runtime/quant_bridge.cjs", "tools/coordinator_replay.cjs", "tools/observation_replay_input.cjs", "tools/funded_comparison.cjs", "tools/fixed_predictor_worker.cjs", "tools/level4_readiness.cjs", "tools/level5_readiness.cjs", "tools/export_observation_snapshot.cjs", *("tools/" + item for item in NODE_SUITES)):
            checks.append(execute("syntax_" + Path(filename).stem, ["node", "--check", filename], ROOT, output))
        modules = ["harpoon_quant/core.py", "harpoon_quant/calibration.py", "harpoon_quant/scalar_svr.py", "harpoon_quant/paired_replay.py", "harpoon_quant/bridge.py", "harpoon_quant/__main__.py", "harpoon_quant/economic_gate.py", "harpoon_quant/economic_gate_v2.py", "harpoon_quant/performance.py", "harpoon_quant/study_integrity.py", "harpoon_quant/fixed_predictor.py", "harpoon_quant/measurement_registration.py", "harpoon_quant/causal_panel.py"]
        checks.append(execute("ruff", [sys.executable, "-m", "ruff", "check", *modules, "tests/test_instrument_metadata.py", "tests/test_paired_replay.py", "tests/test_runtime_observations.py", "tests/test_economic_gate.py", "tests/test_economic_gate_v2.py", "tests/test_performance_provenance.py", "tests/test_measurement_registration.py", "tests/test_causal_panel.py", "tests/test_observation_stream.py", "tests/test_fixed_predictor.py", "tests/test_core5_numeric.py", "tests/test_core5_bridge_limits.py"], ROOT / "quant", output))
        checks.append(execute("mypy", [sys.executable, "-m", "mypy", "--follow-imports=silent", *modules], ROOT / "quant", output))
        checks.append(execute("adapters_ruff", [sys.executable, "-m", "ruff", "check", "tools/build_causal_panel.py", "tools/measurement_registration.py"], ROOT, output))
        checks.append(execute("installer_ruff", [sys.executable, "-m", "ruff", "check", "deploy/ultimate_install.py", "tools/test_ultimate_install.py"], ROOT, output))
        checks.append(execute("installer_mypy", [sys.executable, "-m", "mypy", "--follow-imports=silent", "deploy/ultimate_install.py"], ROOT, output))
        checks.append(execute("storage_ruff", [sys.executable, "-m", "ruff", "check", "runtime/store.py"], ROOT, output))
        checks.append(execute("storage_mypy", [sys.executable, "-m", "mypy", "--follow-imports=silent", "runtime/store.py"], ROOT, output))
        checks.append(execute("storage_js_types", ["node", "node_modules/typescript/bin/tsc", "--allowJs", "--checkJs", "--noEmit", "--skipLibCheck", "--target", "ES2022", "--module", "node16", "--types", "node", "runtime/store30.cjs"], ROOT, output))
        for filename in ("install.sh", "status.sh", "stop.sh"):
            checks.append(execute("shell_" + Path(filename).stem, ["bash", "-n", filename], ROOT, output))
    result = {
        "scope": "Affected offline software gates; no trading performance assertion",
        "suite": args.suite, "python": sys.version, "checks": checks,
        "tests": sum(item.get("tests") or 0 for item in checks),
        "passed": all(item["passed"] for item in checks),
        "financial_trials_created": 0,
    }
    (output / (args.suite + "_summary.json")).write_text(json.dumps(result, indent=2) + "\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
