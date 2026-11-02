#!/usr/bin/env python3
"""Two-stage finite retrospective registration; no order/economic authority.

Stage one reserves the six fixed recipes BEFORE this study's price capture.
Stage two appends exactly one immutable data/code binding BEFORE fitting/replay.
Previously used global history is not made fresh by either local timestamp.
"""
from __future__ import annotations
import argparse
import fcntl
import json
import os
import sqlite3
import sys
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "tools"))
from quant8_register import (Journal, digest, require, sha, read, snapshot,
                             _write_once, _sync_directory, _checkpoint)

SCHEMA = "HARPOON_RESIDUAL_REGISTRATION_1"
STUDY = "HARPOON_INTRADAY_RESIDUAL_30_18_0"
POLICIES = ["RESIDUAL_LONG", "STOCK_THRESHOLD_OFF", "SECTOR_TIMING_CONTROL"]
SCENARIOS = ["NOMINAL", "STRESS"]
SLOTS = 6
SOURCE = APP / "evidence/core_quant8_30_17_0/registration/optimizer.descendant.sqlite3"
SOURCE_SHA256 = "d651758acb6773a2d34b1df81f5f9ed2a33384675ce0aba0490be9906dec57bd"
SOURCE_SEQUENCE = 84
SOURCE_HEAD = "c57b33fdf53e140a4b96afaa5d7c1962d32d5e289a76932a72b1ccc540d18c9c"
SOURCE_BUDGET = {"spent": 41, "limit": 128}
OUTPUT = APP / "evidence/residual_30_18_0/registration"
DESCENDANT = "optimizer.descendant.sqlite3"
PROTOCOL = "research/residual_30_18/protocol.json"
DATASET = "evidence/residual_30_18_0/data/research_dataset.json"
DATA_AUDIT = "evidence/residual_30_18_0/data/data_audit.json"
RESERVE_KEY = "measurement:residual:v1:" + STUDY
ADMISSION_KEY = "measurement:residual:data-admission:v1:" + STUDY
LOCAL_CLOCK = "EXECUTOR_SYSTEM_UTC_NOT_INDEPENDENT_ATTESTATION"
BAR_TOOL = "mcp__codex_apps__alpaca_get_stock_bars"
MINIMUM_PRICE_RECEIPTS = 78
AUTHORITY = {"independent_preregistration": False, "financial_acceptance_allowed": False,
             "live_approved": False, "execution_allowed": False}
REQUIRED_CODE = (
    "tools/residual_register.py", "tools/quant8_register.py", "tools/run_residual.py",
    "tools/residual_verify.py", "tools/residual_data_audit.py", "tools/residual_model.py", "tools/residual_replay.cjs",
    "tools/residual_statistics.py", "tools/residual_forward.py", "tools/audit_historical_results.py", "tools/historical_bank.cjs",
    "tools/historical_bank_register.py", "tools/measurement_registration.py",
    "quant/harpoon_quant/recursive.py", "quant/harpoon_quant/core.py",
    "quant/harpoon_quant/optimization.py", "quant/harpoon_quant/performance.py",
    "package.json", "package-lock.json", "quant/requirements-tested.txt",
)
REQUIRED_GLOBS = ("quant/harpoon_quant/*.py", "runtime30/*.js", "xxx/*.ts", "tools/residual*.py", "tools/residual*.cjs")


def _source() -> dict[str, Any]:
    require(SOURCE.is_file() and not SOURCE.is_symlink(), "RETAINED_SOURCE_REQUIRED")
    wal = Path(str(SOURCE) + "-wal")
    require(not wal.exists() or wal.stat().st_size == 0, "SOURCE_WAL_NOT_EMPTY")
    require(sha(SOURCE) == SOURCE_SHA256, "SOURCE_SHA256_MISMATCH")
    result = snapshot(SOURCE, immutable=True)
    require(result["budget"] == SOURCE_BUDGET and result["audit_seq"] == SOURCE_SEQUENCE
            and result["audit_head"] == SOURCE_HEAD, "SOURCE_41_OF_128_ANCHOR_MISMATCH")
    require(RESERVE_KEY not in result["states"] and ADMISSION_KEY not in result["states"], "FAMILY_ALREADY_IN_SOURCE")
    return result


def _recipe(protocol_path: Path) -> dict[str, Any]:
    require(protocol_path.resolve() == (APP / PROTOCOL).resolve(), "EXACT_PROTOCOL_PATH_REQUIRED")
    p = read(protocol_path)
    require(p.get("study_id") == STUDY and p.get("origin") == "HISTORICAL", "STUDY_HISTORICAL_REQUIRED")
    require(p.get("seen_global_history") is True and p.get("fresh_global_holdout", False) is False, "REUSED_GLOBAL_HISTORY_MUST_BE_DISCLOSED")
    for flag in AUTHORITY:
        require(p.get(flag, False) is False, "AUTHORITY_NOT_PERMITTED:" + flag)
    require(all(p.get(flag) is False for flag in ("independent_preregistration", "financial_acceptance_allowed", "live_approved")), "EXPLICIT_AUTHORITY_FALSE_REQUIRED")
    b = p.get("budget", {})
    require(b.get("policies") == POLICIES and b.get("scenarios") == SCENARIOS
            and b.get("new_policy_scenario_measurements") == SLOTS
            and b.get("source_budget_spent") == 41 and b.get("source_budget_limit") == 128
            and b.get("descendant_expected_spent") == 47 and b.get("cash_is_derived_reference") is True,
            "FIXED_SIX_SLOT_41_TO_47_BUDGET_REQUIRED")
    require(p.get("dataset") == DATASET and p.get("data_audit") == DATA_AUDIT, "EXACT_DATA_DESTINATIONS_REQUIRED")
    require(isinstance(p.get("definition_recorded_at"), str) and p["definition_recorded_at"], "DEFINITION_TIMESTAMP_REQUIRED")
    identity = {"study_id": STUDY, "protocol_sha256": sha(protocol_path),
                "definition_recorded_at": p["definition_recorded_at"], "timestamp_scope": "HASH_BOUND_PROTOCOL_DECLARATION",
                "policies": POLICIES, "scenarios": SCENARIOS, "slots": SLOTS,
                "seen_global_history": True, "fresh_global_holdout": False,
                "source": {"sha256": SOURCE_SHA256, "audit_sequence": SOURCE_SEQUENCE,
                           "audit_head": SOURCE_HEAD, "budget": SOURCE_BUDGET}}
    return {"identity": identity, "identity_hash": digest(identity), **AUTHORITY}


def _directory(directory: Path) -> Path:
    directory = Path(directory)
    require(not directory.is_symlink() and directory.resolve() == OUTPUT.resolve(), "SINGLE_CANONICAL_DESCENDANT_REQUIRED")
    target = directory / DESCENDANT
    require(not target.is_symlink(), "DESCENDANT_SYMLINK")
    require(not target.exists() or not os.path.samefile(target, SOURCE), "SOURCE_ALIAS_FORBIDDEN")
    return directory.resolve()


@contextmanager
def _lock(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / ".residual_register.lock"
    require(not lock_path.is_symlink(), "LOCK_SYMLINK")
    with os.fdopen(os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600), "a+b") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("REGISTRATION_ALREADY_RUNNING") from exc
        yield


def _state(directory: Path, source: dict[str, Any], recipe: dict[str, Any]) -> dict[str, Any]:
    result = snapshot(directory / DESCENDANT)
    require(result["audit"][:SOURCE_SEQUENCE] == source["audit"], "DESCENDANT_ANCESTRY_MISMATCH")
    require(result["holdouts"] == source["holdouts"], "HOLDOUTS_MUST_REMAIN_UNCHANGED")
    suffix = [json.loads(row[1])["key"] for row in result["audit"][SOURCE_SEQUENCE:]]
    require(suffix in ([], ["budget", RESERVE_KEY], ["budget", RESERVE_KEY, ADMISSION_KEY]), "UNREGISTERED_AUDIT_EVENTS")
    reserved, admitted = len(suffix) >= 2, len(suffix) == 3
    extra = {RESERVE_KEY} if reserved else set()
    if admitted:
        extra.add(ADMISSION_KEY)
    require(set(result["states"]) == set(source["states"]) | extra, "DESCENDANT_STATE_KEYS_CHANGED")
    require(all(result["states"][k] == v for k, v in source["states"].items() if k != "budget"), "INHERITED_STATE_CHANGED")
    require(result["budget"] == {"spent": 47 if reserved else 41, "limit": 128}, "BUDGET_RESET_OR_EXPANSION")
    if reserved:
        r = result["states"][RESERVE_KEY]
        require(r.get("schema") == SCHEMA and r.get("recipe") == recipe and r.get("slots") == 6
                and r.get("budget_before") == 41 and r.get("budget_after") == 47
                and r.get("stage") == "RESERVED_BEFORE_DATA_ADMISSION", "RESERVATION_IDENTITY_CONFLICT")
        require(all(r.get(k) == v for k, v in AUTHORITY.items()), "RESERVATION_AUTHORITY_CHANGED")
    if admitted:
        r = result["states"][ADMISSION_KEY]
        require(r.get("schema") == SCHEMA and r.get("recipe_identity_hash") == recipe["identity_hash"]
                and r.get("stage") == "IMMUTABLE_DATA_CODE_ADMISSION"
                and all(r.get(k) == v for k, v in AUTHORITY.items()), "ADMISSION_IDENTITY_CONFLICT")
    return result


def _reservation_receipt(state: dict[str, Any], recipe: dict[str, Any]) -> dict[str, Any]:
    require(RESERVE_KEY in state["states"], "RECIPES_NOT_RESERVED")
    r = state["states"][RESERVE_KEY]
    return {"schema": SCHEMA, "stage": "RESERVED_BEFORE_DATA_ADMISSION", "verified": True,
            "recipe_identity_hash": recipe["identity_hash"], "reservation_hash": digest(r),
            "registered_at": r["registered_at"], "registered_at_clock": r["registered_at_clock"],
            "audit_sequence_at_reservation": SOURCE_SEQUENCE + 2,
            "audit_head_at_reservation": state["audit"][SOURCE_SEQUENCE + 1][3],
            "budget_path": [41, 47], "slots": 6, "offline_replay_admitted": False,
            "seen_global_history": True, "fresh_global_holdout": False, **AUTHORITY}


def _reserved(directory: Path, protocol_path: Path):
    source, recipe = _source(), _recipe(protocol_path)
    require(read(directory / "recipe_binding.json") == recipe, "RECIPE_BINDING_CONFLICT")
    require(read(directory / "fork_receipt.json") == {"schema": SCHEMA, "recipe_identity_hash": recipe["identity_hash"],
            "source": recipe["identity"]["source"], "descendant": DESCENDANT}, "FORK_IDENTITY_CONFLICT")
    state = _state(directory, source, recipe)
    receipt = _reservation_receipt(state, recipe)
    require(read(directory / "reservation.json") == receipt, "RESERVATION_RECEIPT_CONFLICT")
    return source, recipe, state


def reserve(protocol_path: Path, output_dir: Path) -> dict[str, Any]:
    """Spend six slots atomically, before data exists. No fit or capture occurs."""
    protocol_path = Path(protocol_path)
    source, recipe = _source(), _recipe(protocol_path)
    directory = _directory(output_dir)
    with _lock(directory):
        target = directory / DESCENDANT
        fork = {"schema": SCHEMA, "recipe_identity_hash": recipe["identity_hash"],
                "source": recipe["identity"]["source"], "descendant": DESCENDANT}
        if (directory / "fork_receipt.json").exists():
            require(read(directory / "fork_receipt.json") == fork, "FORK_IDENTITY_CONFLICT")
            require(target.is_file(), "DESCENDANT_MISSING_NO_RESET")
        else:
            require(not (directory / "reservation.json").exists() and not (directory / "admission.json").exists(), "FORK_MISSING_NO_RESET")
            if target.exists():
                require(sha(target) == SOURCE_SHA256, "UNRECEIPTED_DESCENDANT_NO_RESET")
            else:
                fd, temporary = tempfile.mkstemp(prefix=".journal.", dir=directory)
                try:
                    with os.fdopen(fd, "wb") as handle:
                        handle.write(SOURCE.read_bytes()); handle.flush(); os.fsync(handle.fileno())
                    require(sha(Path(temporary)) == SOURCE_SHA256, "SOURCE_COPY_MISMATCH")
                    os.link(temporary, target); _sync_directory(directory)
                finally:
                    os.unlink(temporary)
            _write_once(directory / "fork_receipt.json", fork)
        _write_once(directory / "recipe_binding.json", recipe)
        state = _state(directory, source, recipe)
        if (directory / "reservation.json").exists():
            require(read(directory / "reservation.json") == _reservation_receipt(state, recipe), "RESERVATION_RECEIPT_CONFLICT")
        if RESERVE_KEY not in state["states"]:
            journal = Journal(target)
            try:
                journal.db.execute("PRAGMA synchronous=FULL")
                with journal.transaction():
                    require(journal.get("budget") == SOURCE_BUDGET and journal.get(RESERVE_KEY) is None, "RESERVATION_CONFLICT")
                    require(journal.db.execute("SELECT h FROM optimizer_audit ORDER BY seq DESC LIMIT 1").fetchone()[0] == state["audit_head"], "AUDIT_HEAD_CONFLICT")
                    now = datetime.now(UTC).isoformat()
                    journal.put("budget", {"spent": 47, "limit": 128}, now)
                    journal.put(RESERVE_KEY, {"schema": SCHEMA, "recipe": recipe, "slots": 6,
                        "budget_before": 41, "budget_after": 47, "stage": "RESERVED_BEFORE_DATA_ADMISSION",
                        "registered_at": now, "registered_at_clock": LOCAL_CLOCK, **AUTHORITY}, now)
            finally:
                journal.close()
        _checkpoint(target)
        result = _reservation_receipt(_state(directory, source, recipe), recipe)
        require(sha(SOURCE) == SOURCE_SHA256, "SOURCE_CHANGED")
        _write_once(directory / "reservation.json", result)
        return result


def _aware_utc(value: Any, reason: str) -> datetime:
    require(isinstance(value, str) and value, reason)
    try:
        parsed = datetime.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(reason) from exc
    require(parsed.tzinfo is not None and parsed.utcoffset() is not None, reason)
    return parsed.astimezone(UTC)


def _admission_plan(protocol_path: Path, manifest_path: Path, recipe: dict[str, Any],
                    reservation_receipt: dict[str, Any]) -> dict[str, Any]:
    manifest = read(manifest_path)
    if isinstance(manifest, list):
        require(all(isinstance(r, dict) and set(r) == {"path", "sha256"} for r in manifest), "MANIFEST_LIST_SCHEMA")
        rows, base = [(r["path"], r["sha256"]) for r in manifest], manifest_path.parent
    else:
        require(isinstance(manifest, dict) and manifest, "MANIFEST_REQUIRED")
        rows, base = list(manifest.items()), APP
    hashes, resolved = {}, {}
    for name, expected in rows:
        require(isinstance(name, str) and name and not Path(name).is_absolute(), "MANIFEST_RELATIVE_PATH")
        require(isinstance(expected, str) and len(expected) == 64 and all(c in "0123456789abcdef" for c in expected), "MANIFEST_SHA256")
        target = base / name
        require(target.is_file() and not target.is_symlink(), "MANIFEST_REGULAR_FILE:" + name)
        real = target.resolve()
        require(real.is_relative_to(APP.resolve()), "MANIFEST_OUTSIDE_APP")
        require(name not in hashes and real not in resolved, "MANIFEST_DUPLICATE_SOURCE")
        require(sha(target) == expected, "SOURCE_HASH_MISMATCH:" + name)
        hashes[name], resolved[real] = expected, name
    required = {protocol_path.resolve(), (APP / DATASET).resolve(), (APP / DATA_AUDIT).resolve(),
                *((APP / p).resolve() for p in REQUIRED_CODE)}
    for pattern in REQUIRED_GLOBS:
        required.update(p.resolve() for p in APP.glob(pattern) if p.is_file())
    require(required.issubset(resolved), "MANIFEST_MISSING_REQUIRED_BINDING")
    dataset_path = APP / DATASET
    data, audit = read(dataset_path), read(APP / DATA_AUDIT)
    require(audit.get("verified") is True and audit.get("dataset_sha256") == sha(dataset_path), "VERIFIED_DATA_AUDIT_BINDING_REQUIRED")
    sources = data.get("provenance", {}).get("files")
    require(isinstance(sources, list) and sources, "RETAINED_RAW_SOURCES_REQUIRED")
    seen = set()
    reserved_at = _aware_utc(reservation_receipt.get("registered_at"), "AWARE_REAL_RESERVATION_TIMESTAMP_REQUIRED")
    price_captures = {}
    for item in sources:
        name = item.get("name") if isinstance(item, dict) else None
        require(isinstance(name, str) and name and not Path(name).is_absolute(), "RAW_SOURCE_RELATIVE_PATH")
        raw = dataset_path.parent / name
        require(raw.resolve().is_relative_to(dataset_path.parent.resolve()) and raw.is_file() and not raw.is_symlink(), "RAW_SOURCE_PATH")
        require(raw.resolve() not in seen and raw.resolve() in resolved, "RAW_SOURCE_DUPLICATE_OR_UNBOUND")
        require(sha(raw) == item.get("sha256"), "RAW_SOURCE_HASH_MISMATCH")
        seen.add(raw.resolve())
        receipt = read(raw)
        request = receipt.get("request", {}) if isinstance(receipt, dict) else {}
        if request.get("tool") == BAR_TOOL:
            request_id = request.get("id")
            require(isinstance(request_id, str) and request_id and request_id not in price_captures,
                    "UNIQUE_BAR_CAPTURE_ID_REQUIRED")
            captured = _aware_utc(receipt.get("captured_at"), "AWARE_BAR_CAPTURE_TIMESTAMP_REQUIRED")
            require(captured >= reserved_at, "PRICE_CAPTURE_PRECEDES_REAL_RESERVATION:" + request_id)
            price_captures[request_id] = captured.isoformat(timespec="microseconds")
    require(len(price_captures) >= MINIMUM_PRICE_RECEIPTS, "MINIMUM_78_BAR_RECEIPTS_REQUIRED")
    first_capture, last_capture = min(price_captures.values()), max(price_captures.values())
    clock = audit.get("capture_clock", {})
    require(_aware_utc(clock.get("first_bar_captured_at"), "AUDIT_FIRST_CAPTURE_CLOCK_REQUIRED").isoformat(timespec="microseconds") == first_capture
            and _aware_utc(clock.get("last_bar_captured_at"), "AUDIT_LAST_CAPTURE_CLOCK_REQUIRED").isoformat(timespec="microseconds") == last_capture,
            "AUDIT_BAR_CAPTURE_CLOCK_MISMATCH")
    capture_guard = {"registered_at": reservation_receipt["registered_at"],
                     "reservation_hash": reservation_receipt["reservation_hash"],
                     "verified_price_receipts": len(price_captures),
                     "first_bar_captured_at": first_capture, "last_bar_captured_at": last_capture,
                     "all_price_receipts_at_or_after_real_reservation": True,
                     "basis": "LOCAL_RETRIEVAL_RECEIPTS_NOT_ORIGINAL_MARKET_RECEIPTS_OR_INDEPENDENT_TIMESTAMP_ATTESTATION"}
    identity = {"recipe_identity_hash": recipe["identity_hash"], "manifest_sha256": sha(manifest_path),
                "source_hashes": dict(sorted(hashes.items())), "dataset_sha256": sha(dataset_path),
                "data_audit_sha256": sha(APP / DATA_AUDIT), "raw_source_count": len(seen), "capture_after_reservation_guard": capture_guard,
                "seen_global_history": True, "fresh_global_holdout": False}
    return {"identity": identity, "identity_hash": digest(identity), **AUTHORITY}


def _admission_receipt(state: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    require(ADMISSION_KEY in state["states"], "DATA_CODE_NOT_ADMITTED_NO_REPLAY")
    r = state["states"][ADMISSION_KEY]
    require(r.get("admission") == plan, "IMMUTABLE_ADMISSION_CONFLICT")
    return {"schema": SCHEMA, "stage": "IMMUTABLE_DATA_CODE_ADMISSION", "verified": True,
            "offline_replay_admitted": True, "admission_identity_hash": plan["identity_hash"],
            "admission_record_hash": digest(r), "admitted_at": r["admitted_at"], "admitted_at_clock": LOCAL_CLOCK,
            "audit_sequence": state["audit_seq"], "audit_head": state["audit_head"], "budget": state["budget"],
            "seen_global_history": True, "fresh_global_holdout": False,
            "scope": "Local integrity admission for six offline retrospective diagnostics only; not independent data authentication or a fresh global holdout.", **AUTHORITY}


def admit(output_dir: Path, protocol_path: Path, source_manifest_path: Path) -> dict[str, Any]:
    """Append one data/code admission; never release or debit additional slots."""
    directory, protocol_path = _directory(output_dir), Path(protocol_path)
    with _lock(directory):
        source, recipe, state = _reserved(directory, protocol_path)
        plan = _admission_plan(protocol_path, Path(source_manifest_path), recipe, _reservation_receipt(state, recipe))
        _write_once(directory / "data_code_binding.json", plan)
        if (directory / "admission.json").exists():
            require(read(directory / "admission.json") == _admission_receipt(state, plan), "ADMISSION_RECEIPT_CONFLICT")
        if ADMISSION_KEY not in state["states"]:
            journal = Journal(directory / DESCENDANT)
            try:
                journal.db.execute("PRAGMA synchronous=FULL")
                with journal.transaction():
                    require(journal.get("budget") == {"spent": 47, "limit": 128}
                            and journal.get(ADMISSION_KEY) is None, "ADMISSION_STATE_CONFLICT")
                    require(journal.db.execute("SELECT h FROM optimizer_audit ORDER BY seq DESC LIMIT 1").fetchone()[0] == state["audit_head"], "AUDIT_HEAD_CONFLICT")
                    now = datetime.now(UTC).isoformat()
                    journal.put(ADMISSION_KEY, {"schema": SCHEMA, "stage": "IMMUTABLE_DATA_CODE_ADMISSION",
                        "recipe_identity_hash": recipe["identity_hash"], "admission": plan,
                        "admitted_at": now, "admitted_at_clock": LOCAL_CLOCK, **AUTHORITY}, now)
            finally:
                journal.close()
        _checkpoint(directory / DESCENDANT)
        result = _admission_receipt(_state(directory, source, recipe), plan)
        require(sha(SOURCE) == SOURCE_SHA256, "SOURCE_CHANGED")
        _write_once(directory / "admission.json", result)
        return result


def verify(output_dir: Path, protocol_path: Path, source_manifest_path: Path) -> dict[str, Any]:
    """Read-only runtime gate; reservation alone never permits any fitting/replay."""
    directory, protocol_path = _directory(output_dir), Path(protocol_path)
    source, recipe, state = _reserved(directory, protocol_path)
    plan = _admission_plan(protocol_path, Path(source_manifest_path), recipe, _reservation_receipt(state, recipe))
    require(read(directory / "data_code_binding.json") == plan, "DATA_CODE_BINDING_CONFLICT")
    result = _admission_receipt(state, plan)
    require(read(directory / "admission.json") == result, "ADMISSION_RECEIPT_CONFLICT")
    require(sha(SOURCE) == SOURCE_SHA256, "SOURCE_CHANGED")
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("reserve", "admit", "verify"))
    p.add_argument("--protocol", type=Path, default=APP / PROTOCOL)
    p.add_argument("--output-dir", type=Path, default=OUTPUT)
    p.add_argument("--source-hashes", type=Path)
    a = p.parse_args()
    try:
        if a.action == "reserve":
            result = reserve(a.protocol, a.output_dir)
        else:
            require(a.source_hashes is not None, "SOURCE_MANIFEST_REQUIRED")
            result = (admit if a.action == "admit" else verify)(a.output_dir, a.protocol, a.source_hashes)
        print(json.dumps(result, allow_nan=False)); return 0
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        print(json.dumps({"schema": SCHEMA, "verified": False, "reason": str(exc), **AUTHORITY})); return 2


if __name__ == "__main__":
    raise SystemExit(main())
