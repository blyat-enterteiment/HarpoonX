"""Run the six previously registered historical measurements, without a broker.

No search, optimization loop, new budget or promotion is created here. Repeating
the identical registered computation must use a new output directory and retain
the same descendant Journal. A pre-existing result is never silently replaced.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

APP = Path(__file__).resolve().parents[1]


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=APP / "research/historical_bank/protocol.json")
    parser.add_argument("--registration-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--verify-against", type=Path)
    args = parser.parse_args()
    output, data, registration, protocol = (p.resolve() for p in (args.output_dir, args.data_dir, args.registration_dir, args.protocol))
    if output.exists() and any(output.iterdir()):
        raise ValueError("OUTPUT_DIRECTORY_MUST_BE_NEW; retain earlier results and incident files")
    output.mkdir(parents=True, exist_ok=True)
    dataset = data / "research_dataset.json"
    env = {**os.environ, "PYTHONPATH": str(APP / "quant"), "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1",
           "HARPOON_QUANT_PYTHON": sys.executable, "PYTHONDONTWRITEBYTECODE": "1"}
    record = {"schema": "HARPOON_HISTORICAL_RUN_RECEIPT_1", "started_at": datetime.now(UTC).isoformat(),
              "protocol_sha256": file_hash(protocol), "dataset_sha256": file_hash(dataset),
              "purpose": "EXACT_REPRODUCTION" if args.verify_against else "REGISTERED_SIX_MEASUREMENTS",
              "execution_nature": "MODELED_OHLCV", "data_nature": "HISTORICAL", "steps": [],
              "financial_acceptance_allowed": False, "liveApproved": False, "deployment_allowed": False,
              "environment": {"python": sys.version, "platform": platform.platform(),
                              "machine": platform.machine(), "blas_threads": 1}}
    save(output / "run_receipt.json", record)
    def step(name: str, command: list[str]) -> None:
        started = time.perf_counter()
        with (output / (name + ".log")).open("wb") as stream:
            process = subprocess.run(command, cwd=APP, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=1800, check=False)
        item = {"name": name, "command": command, "exit_code": process.returncode,
                "elapsed_seconds": time.perf_counter() - started, "log_sha256": file_hash(output / (name + ".log"))}
        record["steps"].append(item)
        save(output / "run_receipt.json", record)
        print(json.dumps({"step": name, "exit_code": process.returncode, "seconds": item["elapsed_seconds"]}), flush=True)
        if process.returncode:
            raise RuntimeError("STEP_FAILED:" + name + "; retained log and any incidents in " + str(output))
    base = ["--protocol", str(protocol)]
    node_base = [*base, "--dataset", str(dataset), "--registration-dir", str(registration), "--output-dir", str(output)]
    py = [sys.executable, "-B", "-m", "harpoon_quant.historical_bank"]
    try:
        step("01_data_audit", [sys.executable, "-B", "tools/historical_bank_data_audit.py", "--data-dir", str(data), "--report", str(output / "data_audit.json")])
        step("02_prepare", ["node", "tools/historical_bank.cjs", "prepare", *node_base])
        step("03_features", [*py, "features", *base, "--dataset", str(dataset), "--signals", str(output / "signals.json"), "--output", str(output / "feature_panel.json")])
        step("04_fit", [*py, "fit", *base, "--panel", str(output / "feature_panel.json"), "--labels", str(output / "training_labels.json"), "--output", str(output / "models.json")])
        step("05_predict", [*py, "predict", *base, "--panel", str(output / "feature_panel.json"), "--models", str(output / "models.json"), "--output", str(output / "admissions.json")])
        step("06_replay", ["node", "tools/historical_bank.cjs", "replay", *node_base])
        step("07_statistics", [*py, "statistics", *base, "--reports", str(output / "reports.json"), "--output", str(output / "statistics.json")])
        reports = json.loads((output / "reports.json").read_text())
        summary = {key: json.loads((output / name).read_text())["summary"] for key, name in reports.items()}
        save(output / "summary.json", summary)
        reproducible = ["signals.json", "training_labels.json", "models.json", "admissions.json", "statistics.json", "summary.json", *reports.values()]
        manifest = {name: file_hash(output / name) for name in reproducible}
        save(output / "result_hashes.json", manifest)
        if args.verify_against:
            prior = json.loads((args.verify_against / "result_hashes.json").read_text())
            mismatches = [name for name in sorted(set(prior) | set(manifest)) if prior.get(name) != manifest.get(name)]
            save(output / "reproduction_verification.json", {"schema": "HARPOON_HISTORICAL_EXACT_REPRODUCTION_1",
                "verified": not mismatches, "mismatches": mismatches, "files_compared": len(manifest),
                "new_policy_variants": 0, "same_descendant_journal": True, "financial_acceptance_allowed": False})
            if mismatches:
                raise ValueError("REPRODUCTION_MISMATCH:" + ",".join(mismatches))
        record.update(status="COMPLETE", completed_at=datetime.now(UTC).isoformat(), result_hashes=manifest)
        save(output / "run_receipt.json", record)
        print(json.dumps({"status": "COMPLETE", "output": str(output), "policy_scenario_measurements": 6,
                          "dictamen": "VENTAJA_NO_DEMOSTRADA", "real_level7": False}), flush=True)
        return 0
    except Exception as error:
        record.update(status="INTERRUPTED_RETAINED", error=str(error), completed_at=datetime.now(UTC).isoformat())
        save(output / "run_receipt.json", record)
        print(json.dumps({"status": record["status"], "error": str(error), "output": str(output)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
