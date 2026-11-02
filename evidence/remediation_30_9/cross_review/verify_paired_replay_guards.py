"""Reproduce the four bounded cross-review cases; no broker and no fitting."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = Path(os.environ.get("HARPOON_APP_ROOT", ROOT / "remediation_work/HARPOON_XXXUltimate_30_9_0"))
sys.path.insert(0, str(APP / "quant"))

from harpoon_quant.core import digest  # noqa: E402
from harpoon_quant.paired_replay import run_paired_replay  # noqa: E402


def main() -> None:
    directory = Path(__file__).resolve().parent
    saved = json.loads((directory / "paired_replay_boundaries.json").read_text())
    cases = {
        "leveraged_etf_factor_domain": saved["etf_input"],
        "withdrawal_beyond_available_cash": saved["withdrawal_input"],
    }
    fixture = json.loads(
        (APP / "quant/examples/paired_replay/synthetic_request.json").read_text()
    )
    malformed = copy.deepcopy(fixture)
    model = copy.deepcopy(malformed["models"]["SVR"][0])
    model["schema"] = "HARPOON_QUANT_CALIBRATION_1"
    model.pop("model_kind", None)
    model["artifact_hash"] = digest(
        {key: value for key, value in model.items() if key != "artifact_hash"}
    )
    malformed["models"]["RIDGE"] = [model]
    cases["ridge_header_with_nested_svr"] = malformed
    duplicate = copy.deepcopy(fixture)
    model = copy.deepcopy(duplicate["models"]["RIDGE"][0])
    model["available_at"] = model["available_at"].replace("+00:00", "Z")
    duplicate["models"]["RIDGE"].append(model)
    cases["same_model_instant_different_spelling"] = duplicate

    checks = []
    for name, data in cases.items():
        result = run_paired_replay(data)
        checks.append(
            {
                "case": name,
                "input_hash": digest(data),
                "status": result["status"],
                "reason": result.get("reason"),
                "blockers": result.get("readiness", {}).get("blockers"),
                "no_financial_acceptance": result["financial_acceptance_allowed"]
                is False,
                "no_external_execution": result["execution_allowed"] is False,
                "pass": result["status"] == "MEDICION_BLOQUEADA"
                and result.get("policies") is None,
            }
        )
    output = {
        "nature": "SYNTHETIC_ENGINEERING_ONLY",
        "review": "Read-only cross-review; same team, not blind external validation.",
        "source_sha256": hashlib.sha256(
            (APP / "quant/harpoon_quant/paired_replay.py").read_bytes()
        ).hexdigest(),
        "checks": checks,
        "all_pass": all(item["pass"] for item in checks),
    }
    (directory / "paired_replay_guards_verified.json").write_text(
        json.dumps(output, indent=2) + "\n"
    )
    print(json.dumps(output, indent=2))
    if not output["all_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
