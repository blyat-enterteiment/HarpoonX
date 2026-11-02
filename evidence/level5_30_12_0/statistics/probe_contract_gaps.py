"""Read-only contract probes against the preserved 30.11.0 base.

No predictor, coordinator, bootstrap, financial trial or journal mutation runs.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[2] / "level4_work/HARPOON_XXXUltimate_30_11_0"
sys.path.insert(0, str(BASE / "quant"))
from harpoon_quant.economic_gate import _curves, _parity, artifact_reference  # noqa: E402


def expected_error(label, expected, fn):
    try:
        fn()
    except ValueError as exc:
        return {"probe": label, "expected": expected, "observed": str(exc), "confirmed": str(exc) == expected}
    return {"probe": label, "expected": expected, "observed": "NO_ERROR", "confirmed": False}


protocol = json.loads((BASE / "quant/examples/economic_gate/synthetic_fixture/protocol.json").read_text())
evidence = json.loads((BASE / "quant/examples/economic_gate/synthetic_fixture/input.json").read_text())
report_path = BASE / "quant/examples/funded_comparison/synthetic_report.json"
report = json.loads(report_path.read_text())

results = [expected_error(
    "complete_funded_report_schema_is_rejected_before_reexecution",
    "PARITY_RECEIPT_SCHEMA",
    lambda: _parity({"parity_receipt": artifact_reference(report_path, BASE)}, BASE, protocol),
)]
evidence["policies"]["C0"]["curve"][0]["gross_exposure_fraction"] = 0.01
results.append(expected_error(
    "native_control_exposure_is_rejected_by_legacy_cash_control_contract",
    "C0_HAS_RISK_EXPOSURE",
    lambda: _curves(protocol, evidence),
))
results.append({
    "probe": "producer_preserves_non_authorizing_flags",
    "observed": {k: report[k] for k in ("execution_allowed", "liveApproved", "financial_acceptance_allowed")},
    "confirmed": all(report[k] is False for k in ("execution_allowed", "liveApproved", "financial_acceptance_allowed")),
})
sources = ["quant/harpoon_quant/economic_gate.py", "tools/funded_comparison.cjs", "tools/level4_readiness.cjs", "tools/LEVEL4_READINESS_CONTRACT.txt", "quant/harpoon_quant/measurement_registration.py", "evidence/level4_30_11_0/protocol.json", "evidence/integral_30_10_1/economic_readiness.json"]
result = {
    "schema": "HARPOON_LEVEL5_STATISTICAL_CONTRACT_AUDIT_1",
    "generated_at": datetime.now(UTC).isoformat(),
    "base": str(BASE),
    "scope": "SYNTHETIC_SOFTWARE_CONTRACT_PROBES_AND_SOURCE_INSPECTION_ONLY",
    "new_financial_trials": 0,
    "training_runs": 0,
    "financial_statistics_recomputed": False,
    "source_mutations": 0,
    "source_hashes": {s: hashlib.sha256((BASE / s).read_bytes()).hexdigest() for s in sources},
    "probes": results,
    "all_probes_confirmed": all(x["confirmed"] for x in results),
}
out = Path(__file__).with_name("contract_probe_results.json")
out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
print(json.dumps({"output": str(out), "all_probes_confirmed": result["all_probes_confirmed"], "new_financial_trials": 0}))
