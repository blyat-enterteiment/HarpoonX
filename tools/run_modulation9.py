"""Run the bounded synthetic study through the native offline account bridge.

Register immutable inputs first. Development sees every fixed recipe. Final
accepts only the recipe named in a separate, hashed selection artifact.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import gzip
import hashlib
import json
import os
import platform
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harpoon_quant.modulation9 import canonical, digest, payload

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "research/modulation9/protocol.json"
REGISTRATION = ROOT / "research/modulation9/registration.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")


def sources() -> list[Path]:
    specific = [PROTOCOL, Path(__file__).resolve(), ROOT / "tools/analyze_modulation9.py",
                ROOT / "tools/modulation9_bridge.cjs", ROOT / "tools/modulation9_test.cjs",
                ROOT / "quant/harpoon_quant/modulation9.py",
                ROOT / "quant/harpoon_quant/technical_swing.py", ROOT / "quant/harpoon_quant/core.py",
                ROOT / "quant/tests/test_modulation9.py", ROOT / "quant/tests/test_modulation9_statistics.py"]
    return sorted(set(specific + list((ROOT / "runtime30").glob("*.js"))
                      + list((ROOT / "runtime30").glob("*.cjs"))))


def register(preregistration_commit: str) -> dict[str, Any]:
    if REGISTRATION.exists():
        raise ValueError("REGISTRATION_ALREADY_EXISTS")
    if len(preregistration_commit) != 40 or any(c not in "0123456789abcdef" for c in preregistration_commit):
        raise ValueError("EXACT_GIT_COMMIT_REQUIRED")
    p = json.loads(PROTOCOL.read_text())
    seeds1, seeds2 = (set(p["stages"][s]["seeds"]) for s in ("development", "final"))
    if seeds1 & seeds2 or len(p["variants"]) != 39:
        raise ValueError("STUDY_DESIGN")
    result = {"schema": "HARPOON_MODULATION9_REGISTRATION_1",
              "registered_at_utc": datetime.now(UTC).isoformat(),
              "preregistered_protocol_commit": preregistration_commit,
              "protocol_sha256": sha(PROTOCOL),
              "sources_sha256": {str(path.relative_to(ROOT)): sha(path) for path in sources()},
              "economic_measurements_before_registration": 0,
              "maximum_account_executions": p["budget"]["supplemental_max_account_executions"],
              "user_authorized_supplemental_exploration": True,
              "historical_budget_debt_reconciled": False,
              "execution_allowed": False}
    write(REGISTRATION, result)
    return result


def verify_registration() -> dict[str, Any]:
    r = json.loads(REGISTRATION.read_text())
    if sha(PROTOCOL) != r["protocol_sha256"]:
        raise ValueError("PROTOCOL_CHANGED_AFTER_REGISTRATION")
    for name, expected in r["sources_sha256"].items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or sha(path) != expected:
            raise ValueError("REGISTERED_SOURCE_CHANGED:" + name)
    return r


def _one(job: tuple[dict[str, Any], int, str, str, list[dict[str, Any]], str]) -> dict[str, Any]:
    p, seed, world, stage, variants, output_str = job
    output = Path(output_str)
    began = time.perf_counter()
    data = payload(p, seed, world, stage, variants)
    input_hash = digest(data)
    with tempfile.TemporaryDirectory(prefix="harpoon-mod9-") as tmp:
        input_path, output_path = Path(tmp) / "input.json", Path(tmp) / "output.json"
        input_path.write_bytes(canonical(data))
        proc = subprocess.run(["node", "tools/modulation9_bridge.cjs", "--input", str(input_path),
                               "--output", str(output_path)], cwd=ROOT, text=True,
                              capture_output=True, timeout=300, check=False)
        if proc.returncode:
            incident = {"stage": stage, "world": world, "seed": seed, "input_sha256": input_hash,
                        "returncode": proc.returncode, "stderr": proc.stderr[-20000:]}
            write(output / f"INCIDENT_{world}_{seed}.json", incident)
            raise RuntimeError(f"NATIVE_REPLAY_FAILED:{world}:{seed}:{proc.stderr[-1000:]}")
        result = json.loads(output_path.read_text())
    accounts = result["accounts"]
    if len(accounts) != len(variants) * 2:
        raise ValueError("ACCOUNT_COUNT")
    periods = data["protocol"]["periods"]
    calendar_days = (datetime.fromisoformat(periods["evaluation_end"])
                     - datetime.fromisoformat(periods["evaluation_start"])).days + 1
    economic = {"schema": "HARPOON_MODULATION9_PATH_1", "stage": stage, "world": world,
                "seed": seed, "input_sha256": input_hash, "calendar_days": calendar_days,
                "periods": periods, "signal_counts": {k: len(v) for k, v in data["signals"].items()},
                "accounts": accounts, "origin": "SYNTHETIC", "execution_allowed": False}
    path = output / f"{world}_{seed}.json.gz"
    path.write_bytes(gzip.compress(canonical(economic), compresslevel=6, mtime=0))
    return {"world": world, "seed": seed, "file": path.name, "accounts": len(accounts),
            "sha256": sha(path), "economic_sha256": digest(economic),
            "wall_seconds": time.perf_counter() - began}


def run(stage: str, output: Path, workers: int, selection: Path | None) -> dict[str, Any]:
    registration = verify_registration()
    p = json.loads(PROTOCOL.read_text())
    if stage not in ("development", "final") or not 1 <= workers <= 4:
        raise ValueError("STAGE_OR_WORKERS")
    selection_hash = None
    variants = p["variants"]
    if stage == "final":
        if selection is None:
            raise ValueError("FINAL_REQUIRES_FROZEN_SELECTION")
        from analyze_modulation9 import validate_selection
        selected = validate_selection(selection, registration["protocol_sha256"])
        selection_hash = selected["selection_sha256"]
        keep = {selected["candidate_id"], "CURRENT", "SIMPLE", "CASH"}
        variants = [v for v in variants if v["id"] in keep]
        if len(variants) != 4:
            raise ValueError("FINAL_CANDIDATE_COUNT")
    elif selection is not None:
        raise ValueError("DEVELOPMENT_DOES_NOT_ACCEPT_SELECTION")
    output.mkdir(parents=True, exist_ok=False)
    jobs = [(p, seed, world, stage, variants, str(output))
            for world in p["generator"]["worlds"] for seed in p["stages"][stage]["seeds"]]
    expected_accounts = len(jobs) * len(variants) * 2
    budget = p["budget"][f"{stage}_policy_cost_world_seed_accounts"]
    if expected_accounts != budget:
        raise ValueError("BUDGET_ACCOUNT_COUNT")
    began = time.perf_counter()
    rows = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
        for row in pool.map(_one, jobs):
            rows.append(row)
            print(json.dumps({"stage": stage, "completed_paths": len(rows), "total_paths": len(jobs),
                              "last_path_seconds": round(row["wall_seconds"], 3)}), flush=True)
    verify_registration()
    result = {"schema": "HARPOON_MODULATION9_STAGE_1", "stage": stage,
              "protocol_sha256": registration["protocol_sha256"],
              "registration_sha256": sha(REGISTRATION), "selection_sha256": selection_hash,
              "paths": [{k: v for k, v in row.items() if k != "wall_seconds"} for row in rows],
              "accounts": sum(row["accounts"] for row in rows),
              "policy_ids": [v["id"] for v in variants], "execution_allowed": False}
    write(output / "manifest.json", result)
    write(output / "benchmark.json", {"wall_seconds": time.perf_counter() - began,
                                     "python": platform.python_version(), "workers": workers,
                                     "cpu_count": os.cpu_count(), "path_seconds": [r["wall_seconds"] for r in rows]})
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--preregistration-commit")
    parser.add_argument("--stage", choices=["development", "final"])
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    if args.register:
        if not args.preregistration_commit:
            parser.error("--preregistration-commit required")
        print(json.dumps(register(args.preregistration_commit)))
    else:
        if not args.stage or args.output_dir is None:
            parser.error("--stage and --output-dir required")
        result = run(args.stage, args.output_dir.resolve(), args.workers, args.selection)
        print(json.dumps({"stage": result["stage"], "accounts": result["accounts"]}))
