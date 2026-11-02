"""Exercise the real coordinator verifier without claiming economic parity.

The input and account curves remain synthetic.  A native-C0 replay receipt does
not certify Ridge/SVR predictions or economic bindings.  The expected financial
verdict therefore remains VENTAJA_NO_DEMOSTRADA even when reexecution agrees.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from harpoon_quant.economic_gate import artifact_reference, evaluate_gate

from .make_fixture import write_json


def bind_example(output: Path) -> dict[str, Any]:
    app = Path(__file__).resolve().parents[3]
    output = output.resolve()
    output.relative_to(app)
    output.mkdir(parents=True, exist_ok=True)
    fixture = Path(__file__).resolve().parent / "synthetic_fixture"
    protocol = json.loads((fixture / "protocol.json").read_text())
    evidence = json.loads((fixture / "input.json").read_text())

    def rebase(value: Any) -> Any:
        if isinstance(value, list):
            return [rebase(item) for item in value]
        if isinstance(value, dict):
            if set(value) == {"path", "sha256"}:
                return artifact_reference(fixture / value["path"], app)
            return {key: rebase(item) for key, item in value.items()}
        return value

    evidence = rebase(evidence)
    request = app / "quant" / "examples" / "coordinator_replay" / "synthetic_request.json"
    replay = output / "real_coordinator_receipt.json"
    completed = subprocess.run(["node", str(app / "tools" / "coordinator_replay.cjs"), "--input", str(request), "--output", str(replay)], cwd=app, text=True, capture_output=True, timeout=30, check=False)
    if completed.returncode:
        raise ValueError("OFFLINE_COORDINATOR_EXAMPLE_FAILED: " + completed.stderr[:500])
    receipt = json.loads(replay.read_text())
    evidence["coordinator_input"] = artifact_reference(request, app)
    evidence["coordinator_input_hash"] = receipt["input_hash"]
    evidence["parity_receipt"] = artifact_reference(replay, app)
    evidence["parity_source_files"] = {name: artifact_reference(app / name, app) for name in receipt["source_hashes"]}
    evidence["purpose"] = "SYNTHETIC integration of real coordinator receipt verification. Native C0 parity is not Ridge/SVR economic parity."
    report = evaluate_gate(protocol, evidence, artifact_root=app)
    write_json(output / "protocol.json", protocol)
    write_json(output / "input.json", evidence)
    write_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = bind_example(Path(args.output))
    print(json.dumps({"dictamen": result["dictamen"], "parity": result["parity"], "financial_blockers": result["financial_blockers"], "execution_allowed": result["execution_allowed"]}, sort_keys=True))
