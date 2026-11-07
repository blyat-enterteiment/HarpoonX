"""Execute the separately registered continuation; a failed development seals final.

No generator/cost/risk/hurdle changes, broker route, hidden retry or parameter fit.
Each execution writes a budget-charged attempt before producing market outcomes.
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

from harpoon_quant.modulation9 import canonical, digest
from harpoon_quant.modulation10 import payload
from run_modulation9 import verify_registration as verify_previous

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "research/modulation10/protocol.json"
REGISTRATION = ROOT / "research/modulation10/registration.json"
ATTEMPTS = ROOT / "research/modulation10/execution_attempts"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")


def new_sources() -> list[Path]:
    paths = [PROTOCOL, Path(__file__).resolve(), ROOT / "tools/analyze_modulation10.py",
             ROOT / "quant/harpoon_quant/modulation10.py",
             ROOT / "quant/tests/test_modulation10.py", ROOT / "quant/tests/test_modulation10_statistics.py",
             ROOT / "tools/modulation10_bridge.cjs", ROOT / "tools/modulation10_test.cjs"]
    native_paths = list((ROOT / "runtime30").glob("modulation10*.cjs"))
    if not native_paths or not (ROOT / "runtime30/modulation10_replay.cjs").is_file():
        raise ValueError("MOD10_NATIVE_IMPLEMENTATION_REQUIRED")
    paths += native_paths
    return sorted(set(paths))


def validate_contract(p: dict[str, Any]) -> None:
    previous = json.loads((ROOT / "research/modulation9/protocol.json").read_text())
    if p["schema"] != "HARPOON_MODULATION10_PROTOCOL_1" or p["origin"] != "SYNTHETIC":
        raise ValueError("MOD10_PROTOCOL_SCHEMA")
    if p["live_approved"] is not False or p["execution_allowed"] is not False:
        raise ValueError("MOD10_OFFLINE_ONLY")
    for key in ("generator", "limits", "scenarios"):
        if p[key] != previous[key]:
            raise ValueError("MOD10_INHERITED_CONTRACT_CHANGED:" + key)
    for key, value in previous["gates"].items():
        if p["gates"].get(key) != value:
            raise ValueError("MOD10_ACCEPTANCE_GATE_CHANGED:" + key)
    seeds_old = {s for stage in previous["stages"].values() for s in stage["seeds"]}
    seeds_new = [s for stage in p["stages"].values() for s in stage["seeds"]]
    if len(seeds_new) != len(set(seeds_new)) or set(seeds_new) & seeds_old:
        raise ValueError("MOD10_FRESH_DISJOINT_SEEDS_REQUIRED")
    if (len(p["variants"]) != 23 or len({v["id"] for v in p["variants"]}) != 23
            or sum(v["role"] == "candidate" for v in p["variants"]) != 18):
        raise ValueError("MOD10_FIXED_CATALOGUE")
    for stage, policies in (("development", 23), ("final", 5)):
        count = len(p["generator"]["worlds"]) * len(p["stages"][stage]["seeds"]) * policies * len(p["scenarios"])
        if count != p["budget"][f"{stage}_policy_cost_world_seed_accounts"]:
            raise ValueError("MOD10_FIXED_EXECUTION_BUDGET")


def register(preregistration_commit: str) -> dict[str, Any]:
    if REGISTRATION.exists():
        raise ValueError("MOD10_REGISTRATION_ALREADY_EXISTS")
    if len(preregistration_commit) != 40 or any(c not in "0123456789abcdef" for c in preregistration_commit):
        raise ValueError("EXACT_GIT_COMMIT_REQUIRED")
    previous = verify_previous()
    p = json.loads(PROTOCOL.read_text())
    validate_contract(p)
    result = {"schema": "HARPOON_MODULATION10_REGISTRATION_1",
              "registered_at_utc": datetime.now(UTC).isoformat(),
              "preregistered_protocol_commit": preregistration_commit,
              "protocol_sha256": sha(PROTOCOL),
              "sources_sha256": {str(path.relative_to(ROOT)): sha(path) for path in new_sources()},
              "previous_sources_sha256": previous["sources_sha256"],
              "previous_registration_sha256": sha(ROOT / "research/modulation9/registration.json"),
              "economic_measurements_before_registration": 0,
              "maximum_account_executions": p["budget"]["supplemental_max_account_executions"],
              "historical_budget_debt_reconciled": False, "execution_allowed": False}
    write(REGISTRATION, result)
    return result


def verify_registration() -> dict[str, Any]:
    previous = verify_previous()
    r = json.loads(REGISTRATION.read_text())
    if (sha(PROTOCOL) != r["protocol_sha256"] or previous["sources_sha256"] != r["previous_sources_sha256"]
            or sha(ROOT / "research/modulation9/registration.json") != r["previous_registration_sha256"]):
        raise ValueError("MOD10_PROTOCOL_OR_PREVIOUS_REGISTRATION_CHANGED")
    for name, expected in r["sources_sha256"].items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or sha(path) != expected:
            raise ValueError("MOD10_REGISTERED_SOURCE_CHANGED:" + name)
    validate_contract(json.loads(PROTOCOL.read_text()))
    return r


def _one(job: tuple[dict[str, Any], int, str, str, list[dict[str, Any]], str]) -> dict[str, Any]:
    p, seed, world, stage, variants, output_str = job
    output = Path(output_str)
    began = time.perf_counter()
    data = payload(p, seed, world, stage, variants)
    input_hash = digest(data)
    with tempfile.TemporaryDirectory(prefix="harpoon-mod10-") as tmp:
        input_path, output_path = Path(tmp) / "input.json", Path(tmp) / "output.json"
        input_path.write_bytes(canonical(data))
        proc = subprocess.run(["node", "tools/modulation10_bridge.cjs", "--input", str(input_path),
                               "--output", str(output_path)], cwd=ROOT, text=True,
                              capture_output=True, timeout=300, check=False)
        if proc.returncode:
            write(output / f"INCIDENT_{world}_{seed}.json", {
                "stage": stage, "world": world, "seed": seed, "input_sha256": input_hash,
                "returncode": proc.returncode, "stderr": proc.stderr[-20000:],
                "budget_charged_accounts": len(variants) * len(p["scenarios"])})
            raise RuntimeError(f"MOD10_NATIVE_REPLAY_FAILED:{world}:{seed}:{proc.stderr[-1000:]}")
        result = json.loads(output_path.read_text())
    accounts = result["accounts"]
    if len(accounts) != len(variants) * len(p["scenarios"]):
        raise ValueError("MOD10_ACCOUNT_COUNT")
    periods = data["protocol"]["periods"]
    days = (datetime.fromisoformat(periods["evaluation_end"]) - datetime.fromisoformat(periods["evaluation_start"])).days + 1
    economic = {"schema": "HARPOON_MODULATION10_PATH_1", "stage": stage, "world": world,
                "seed": seed, "input_sha256": input_hash, "calendar_days": days, "periods": periods,
                "signal_counts": {k: len(v) for k, v in data["signals"].items()},
                "accounts": accounts, "origin": "SYNTHETIC", "execution_allowed": False}
    path = output / f"{world}_{seed}.json.gz"
    path.write_bytes(gzip.compress(canonical(economic), compresslevel=6, mtime=0))
    return {"world": world, "seed": seed, "file": path.name, "accounts": len(accounts),
            "sha256": sha(path), "economic_sha256": digest(economic),
            "wall_seconds": time.perf_counter() - began}


def choose_final_variants(p: dict[str, Any], selected: dict[str, Any]) -> list[dict[str, Any]]:
    if (selected.get("development_score_positive") is not True
            or selected.get("candidate", {}).get("score", 0) <= 0
            or selected.get("candidate", {}).get("risk_feasible") is not True):
        raise ValueError("MOD10_FINAL_SEALED_DEVELOPMENT_NOT_ELIGIBLE")
    if selected.get("candidate_id") not in {v["id"] for v in p["variants"] if v["role"] == "candidate"}:
        raise ValueError("MOD10_FINAL_NEW_CANDIDATE_REQUIRED")
    keep = {selected["candidate_id"], *p["evaluation_control_ids"]}
    variants = [v for v in p["variants"] if v["id"] in keep]
    if len(variants) != 5 or len(keep) != 5:
        raise ValueError("MOD10_FINAL_CANDIDATE_COUNT")
    return variants


def claim_stage(stage: str, output: Path, expected: int, registration: dict[str, Any],
                selection_hash: str | None, registry: Path = ATTEMPTS) -> dict[str, Any]:
    """Atomically charge one stage; failures retain the charge and cannot retry.

    This guards a shared checkout. Cross-checkout scheduling additionally uses
    the published program-state Git lease; a local file is not a remote mutex.
    """
    if stage not in ("development", "final") or expected <= 0:
        raise ValueError("MOD10_INVALID_STAGE_CLAIM")
    registry.mkdir(parents=True, exist_ok=True)
    prior_count = 0
    for path in registry.glob("*.json"):
        prior = json.loads(path.read_text())
        if prior["protocol_sha256"] != registration["protocol_sha256"]:
            raise ValueError("MOD10_STAGE_REGISTRY_PROTOCOL_MISMATCH")
        prior_count += prior["budget_charged_accounts"]
    if prior_count + expected > registration["maximum_account_executions"]:
        raise ValueError("MOD10_CUMULATIVE_EXECUTION_BUDGET")
    attempt = {"stage": stage, "started_at_utc": datetime.now(UTC).isoformat(),
               "budget_charged_accounts": expected, "automatic_retry_allowed": False,
               "protocol_sha256": registration["protocol_sha256"],
               "selection_sha256": selection_hash, "output_directory": str(output.resolve()),
               "scope": "shared_checkout_stage_once_remote_program_git_lease_also_required"}
    # Exclusive creation also closes concurrent duplicate attempts at this stage.
    with (registry / f"{stage}.json").open("x") as handle:
        json.dump(attempt, handle, sort_keys=True, indent=2, allow_nan=False)
        handle.write("\n")
    return attempt


def run(stage: str, output: Path, workers: int, selection: Path | None) -> dict[str, Any]:
    registration = verify_registration()
    p = json.loads(PROTOCOL.read_text())
    if stage not in ("development", "final") or not 1 <= workers <= 4:
        raise ValueError("MOD10_STAGE_OR_WORKERS")
    selection_hash, variants = None, p["variants"]
    if stage == "final":
        if selection is None:
            raise ValueError("MOD10_FINAL_REQUIRES_FROZEN_SELECTION")
        from analyze_modulation10 import validate_selection
        selected = validate_selection(selection, registration["protocol_sha256"])
        variants = choose_final_variants(p, selected)
        selection_hash = selected["selection_sha256"]
    elif selection is not None:
        raise ValueError("MOD10_DEVELOPMENT_SELECTION_FORBIDDEN")
    expected = len(p["generator"]["worlds"]) * len(p["stages"][stage]["seeds"]) * len(variants) * len(p["scenarios"])
    if expected != p["budget"][f"{stage}_policy_cost_world_seed_accounts"]:
        raise ValueError("MOD10_BUDGET_ACCOUNT_COUNT")
    if output.exists():
        raise FileExistsError("MOD10_OUTPUT_ALREADY_EXISTS")
    attempt = claim_stage(stage, output, expected, registration, selection_hash)
    output.mkdir(parents=True, exist_ok=False)
    write(output / "execution_attempt.json", attempt)
    jobs = [(p, seed, world, stage, variants, str(output))
            for world in p["generator"]["worlds"] for seed in p["stages"][stage]["seeds"]]
    began, rows = time.perf_counter(), []
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
        for row in pool.map(_one, jobs):
            rows.append(row)
            print(json.dumps({"stage": stage, "completed_paths": len(rows), "total_paths": len(jobs),
                              "last_path_seconds": round(row["wall_seconds"], 3)}), flush=True)
    verify_registration()
    result = {"schema": "HARPOON_MODULATION10_STAGE_1", "stage": stage,
              "protocol_sha256": registration["protocol_sha256"], "registration_sha256": sha(REGISTRATION),
              "selection_sha256": selection_hash,
              "paths": [{k: v for k, v in row.items() if k != "wall_seconds"} for row in rows],
              "accounts": sum(row["accounts"] for row in rows), "policy_ids": [v["id"] for v in variants],
              "budget_charged_accounts": expected, "execution_allowed": False}
    write(output / "manifest.json", result)
    write(output / "benchmark.json", {"wall_seconds": time.perf_counter() - began,
          "python": platform.python_version(), "workers": workers, "cpu_count": os.cpu_count(),
          "path_seconds": [r["wall_seconds"] for r in rows]})
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
