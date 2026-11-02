"""Reexecute available source diagnostics and explicitly synthetic software fixtures.

No new market lookup, model fit, financial trial, registration or external order.
Run this from a release workspace with the full app argument, not a Python-only ZIP.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--app", required=True, type=Path)
args = parser.parse_args()
app = args.app.resolve()
pub = app / "evidence/integral_30_12_1"
pub.mkdir(parents=True, exist_ok=True)
logs = pub / "reproduction_logs"
logs.mkdir(exist_ok=True)
env = dict(os.environ, HARPOON_QUANT_PYTHON=sys.executable,
           PYTHONDONTWRITEBYTECODE="1", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
           PYTHONPATH=str(app / "quant"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def ref(path, base=pub):
    return {"path": os.path.relpath(path, base), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


checks = []


def run(name, command, expected=0):
    with (logs / (name + ".log")).open("w") as output:
        done = subprocess.run(command, cwd=app, env=env, stdout=output, stderr=subprocess.STDOUT, timeout=300, check=False)
    checks.append({"name": name, "command": command, "exit_code": done.returncode, "expected_exit_code": expected})
    print(json.dumps(checks[-1]), flush=True)
    if done.returncode != expected:
        raise RuntimeError("REPRODUCTION_FAILED:" + name)


run("build", ["node", "node_modules/typescript/bin/tsc", "-p", "tsconfig.xxx.json"])
run("causal_data", [sys.executable, "tools/build_causal_panel.py", "--input", str(pub / "data/request.json"), "--output", str(pub / "data/report.json")])
run("verify_causal_data", [sys.executable, "tools/build_causal_panel.py", "--input", str(pub / "data/request.json"), "--verify", str(pub / "data/report.json"), "--output", str(pub / "data/verification.json")])
coordinator = app / "quant/examples/coordinator_replay"
run("coordinator_fixture", ["node", "tools/coordinator_replay.cjs", "--input", str(coordinator / "synthetic_request.json"), "--output", str(coordinator / "synthetic_report.json")])
run("coordinator_verify", ["node", "tools/coordinator_replay.cjs", "--input", str(coordinator / "synthetic_request.json"), "--verify", str(coordinator / "synthetic_report.json"), "--output", str(coordinator / "synthetic_verification.json")])
funded = app / "quant/examples/funded_comparison"
run("make_fixed_synthetic_request", ["node", "-e", "const fs=require('node:fs');const {syntheticComparison}=require('./tools/fixtures/funded_comparison_fixture.cjs');fs.writeFileSync(process.argv[1],JSON.stringify(syntheticComparison(),null,2)+'\\n');", str(funded / "synthetic_request.json")])
run("funded_fixture", ["node", "tools/funded_comparison.cjs", "--input", str(funded / "synthetic_request.json"), "--output", str(funded / "synthetic_report.json")])
run("funded_verify", ["node", "tools/funded_comparison.cjs", "--input", str(funded / "synthetic_request.json"), "--verify", str(funded / "synthetic_report.json"), "--output", str(funded / "synthetic_verification.json")])
run("legacy_coordinator_gate_fixture", [sys.executable, "-m", "examples.economic_gate.bind_coordinator_example", "--output", str(app / "quant/examples/economic_gate/coordinator_fixture")])
synthetic = app / "quant/examples/level5/synthetic"
run("level5_synthetic_base_and_stress", ["node", "tools/fixtures/level5_fixture.cjs", str(synthetic)])

request4 = {"schema": "HARPOON_LEVEL4_READINESS_REQUEST_1",
            "data": {"request": ref(pub / "data/request.json"), "report": ref(pub / "data/report.json")},
            "comparison": {"request": ref(funded / "synthetic_request.json"), "report": ref(funded / "synthetic_report.json")},
            "ledger": None}
write(pub / "readiness_request.json", request4)
run("level4_available_evidence", ["node", "tools/level4_readiness.cjs", "--input", str(pub / "readiness_request.json"), "--output", str(pub / "readiness_report.json")])
run("level4_verify", ["node", "tools/level4_readiness.cjs", "--input", str(pub / "readiness_request.json"), "--verify", str(pub / "readiness_report.json"), "--output", str(pub / "readiness_verification.json")])
request5 = {"schema": "HARPOON_LEVEL5_DERIVATION_REQUEST_1", "level4": {"request": ref(pub / "readiness_request.json")}, "stress": []}
write(pub / "derived_request.json", request5)
run("level5_available_evidence", ["node", "tools/level5_readiness.cjs", "--input", str(pub / "derived_request.json"), "--output", str(pub / "derived_report.json")])
run("level5_verify", ["node", "tools/level5_readiness.cjs", "--input", str(pub / "derived_request.json"), "--verify", str(pub / "derived_report.json"), "--output", str(pub / "derived_verification.json")])

sys.path.insert(0, str(app / "quant"))
from harpoon_quant.economic_gate import seal_protocol, verify_gate_report
from harpoon_quant.economic_gate_v2 import ROLES
created = datetime.now(UTC).isoformat()
protocol = seal_protocol({"schema": "HARPOON_ECONOMIC_PROTOCOL_2", "protocol_id": "UNREGISTERED_MISSING_EMPIRICAL_INPUTS",
    "status": "DRAFT_NOT_REGISTERED", "created_at": created, "research_only": True, "data_scope": "HISTORICAL",
    "currency": "USD", "equity_unit": "USD", "initial_equity_usd": None, "universe": None,
    "policy_roles": ROLES, "exposure_measure": "EVENT_INTERVAL_TIME_WEIGHTED_LAST_OBSERVED",
    "external_cost_method": "VERIFIED_LEDGER_ACCRUAL_TIMESTAMPS",
    "policy_hash": None, "risk_hash": None, "cost_hash": None, "code_hash": None,
    "minimum_delta_ridge_log_growth": None, "minimum_delta_native_log_growth": None,
    "period": {"train_end": None, "validation_start": None, "validation_end": None, "test_start": None, "test_end": None},
    "evaluation_sessions": None, "stress_scenarios": None, "dependence": None,
    "statistics": None, "risk_comparison": None,
    "null_reason": "No observed account, usable causal models, current limits, new final period or justified statistical specification available. No values are borrowed from synthetic fixtures."})
write(pub / "protocol_draft_not_registered.json", protocol)
evidence = {"schema": "HARPOON_ECONOMIC_EVIDENCE_2", "protocol_hash": protocol["protocol_hash"], "generated_at": created,
    "execution_allowed": False, "liveApproved": False, "derivation_request": ref(pub / "derived_request.json"),
    "history_manifest": ref(pub / "history/manifest.json"), "preregistration": None, "search_history": None}
write(pub / "economic_gate_input.json", evidence)
run("economic_gate_missing_inputs", [sys.executable, "-m", "harpoon_quant.economic_gate", "--protocol", str(pub / "protocol_draft_not_registered.json"),
    "--input", str(pub / "economic_gate_input.json"), "--artifact-root", str(pub), "--output", str(pub / "economic_gate_report.json")], expected=2)
report = json.loads((pub / "economic_gate_report.json").read_text())
verification = verify_gate_report(report, protocol, evidence, artifact_root=pub)
assert verification["recomputed_identically"] and verification["report_integrity_verified"]
write(pub / "economic_gate_verification.json", verification)
write(pub / "reproduction_summary.json", {"checks": checks, "passed": True, "new_financial_trials": 0, "model_fits": 0,
      "expected_blocked_economic_gate": True, "financial_verdict": report["dictamen"], "economic_score": report["score"],
      "synthetic_fixtures_are_financial_evidence": False})
print(json.dumps({"reproduction_complete": True, "score": report["score"], "financial_verdict": report["dictamen"]}))
