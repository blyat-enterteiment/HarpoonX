#!/usr/bin/env python3
"""Single finite historical diagnostic family; not an economic approval.

The retained 29/128 journal is copied once into the only allowed descendant.
One atomic transaction reserves all twelve policy/scenario measurements. This does
not reopen the historical family's exhausted budget, mint a fresh holdout, or
make today's local registration independently preregistered evidence.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
import sqlite3
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "quant"))
from harpoon_quant.core import digest  # noqa: E402
from harpoon_quant.recursive import Journal  # noqa: E402

SCHEMA = "HARPOON_QUANT8_REGISTRATION_1"
STUDY = "HARPOON_QUANT8_DIAGNOSTIC_30_17_0"
POLICIES = ["C0", "RIDGE", "SVR", "RIDGE_HURDLE", "HUBER_HURDLE", "HUBER_REGIME_CAP"]
SCENARIOS = ["NOMINAL", "STRESS"]
SLOTS = 12
SOURCE = APP / "evidence/historical_bank_30_16_0/registration/optimizer.descendant.sqlite3"
SOURCE_SHA256 = "d766654661e51dae72674acd02ddd8d89055f2caa59fe28f62cd6011d1edb52b"
SOURCE_HEAD = "e03fb3f98c046180382b6744488168c3c60d373d8b801bdf83d3fe8421c97f17"
SOURCE_SEQUENCE = 82
SOURCE_BUDGET = {"spent": 29, "limit": 128}
OUTPUT = APP / "evidence/core_quant8_30_17_0/registration"
DESCENDANT = "optimizer.descendant.sqlite3"
FORK = "fork_receipt.json"
BINDING = "binding.json"
OVERVIEW = "quant8_registration.json"
KEY = "measurement:quant8:v1:" + STUDY
BASE_PROTOCOL = "research/historical_bank/protocol.json"
DATASET = "evidence/historical_bank_30_16_0/data/research_dataset.json"
# The finite runner imports these directly or transitively. Broader directory
# inventories below bind every local Python model and every runtime/source module
# so a manifest author cannot omit a later-added transitive execution dependency.
REQUIRED_CODE = (
    "tools/quant8_register.py", "tools/run_quant8.py", "tools/quant8_replay.cjs", "tools/quant8_verify.py",
    "tools/historical_bank.cjs", "tools/audit_historical_results.py",
    "tools/historical_bank_data_audit.py", "tools/historical_bank_register.py",
    "tools/measurement_registration.py",
    "quant/harpoon_quant/quant8_models.py", "quant/harpoon_quant/quant8_statistics.py",
    "quant/harpoon_quant/historical_bank.py", "quant/harpoon_quant/calibration.py",
    "quant/harpoon_quant/scalar_svr.py", "quant/harpoon_quant/support.py",
    "quant/harpoon_quant/recursive.py", "quant/harpoon_quant/core.py",
    "quant/harpoon_quant/optimization.py", "quant/harpoon_quant/performance.py",
    "quant/harpoon_quant/measurement_registration.py", "quant/harpoon_quant/study_integrity.py",
    "runtime30/ultimate_replay.js", "runtime30/ultimate_contracts.js",
    "runtime30/ultimate_reservations.js", "runtime30/ultimate_stats.js",
    "runtime30/ultimate_frequency.js", "runtime30/policy.js",
    "xxx/ultimate_replay.ts", "xxx/ultimate_contracts.ts", "xxx/ultimate_reservations.ts",
    "package.json", "package-lock.json", "tsconfig.xxx.json", "quant/requirements-tested.txt",
)
REQUIRED_GLOBS = ("quant/harpoon_quant/*.py", "runtime30/*.js", "xxx/*.ts")
LOCAL_CLOCK = "EXECUTOR_SYSTEM_UTC_NOT_INDEPENDENT_ATTESTATION"


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_JSON_KEY:" + key)
        result[key] = value
    return result


def _number(value: str) -> float:
    result = float(value)
    require(math.isfinite(result), "NONFINITE_JSON_NUMBER")
    return result


def read(path: Path) -> Any:
    require(path.is_file() and not path.is_symlink(), "REGULAR_INPUT_REQUIRED:" + path.name)
    return json.loads(path.read_bytes(), object_pairs_hook=_pairs, parse_float=_number,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("NONFINITE_JSON_CONSTANT:" + value)))


def _sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_once(path: Path, value: Any) -> None:
    encoded = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if path.exists() or path.is_symlink():
        require(path.is_file() and not path.is_symlink() and path.read_bytes() == encoded,
                "ARTIFACT_CONFLICT:" + path.name)
        return
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            require(path.is_file() and not path.is_symlink() and path.read_bytes() == encoded,
                    "ARTIFACT_CONFLICT:" + path.name)
        _sync_directory(path.parent)
    finally:
        os.unlink(temporary)


def snapshot(path: Path, *, immutable: bool = False) -> dict[str, Any]:
    """Read-only audited snapshot; no migration, creation or budget mutation."""
    path = Path(path)
    if path.is_dir():
        path = path / DESCENDANT
    require(path.is_file() and not path.is_symlink(), "EXISTING_REGULAR_JOURNAL_REQUIRED")
    reader = Journal.__new__(Journal)
    reader.db = sqlite3.connect(path.resolve().as_uri() + ("?mode=ro&immutable=1" if immutable else "?mode=ro"), uri=True)
    reader.integrity_report = {}
    try:
        reader.db.execute("BEGIN")
        reader.verify()
        audit = list(reader.db.execute("SELECT seq,payload,previous,h FROM optimizer_audit ORDER BY seq"))
        require(bool(audit), "AUDITED_JOURNAL_REQUIRED")
        states = {key: json.loads(value) for key, value in reader.db.execute("SELECT k,v FROM optimizer_state")}
        return {"audit": audit, "states": states, "budget": states.get("budget"),
                "audit_seq": audit[-1][0], "audit_head": audit[-1][3],
                "holdouts": sorted(reader._holdout_rows()), "integrity": reader.integrity_report}
    finally:
        reader.db.close()


def _source() -> dict[str, Any]:
    require(SOURCE.is_file() and not SOURCE.is_symlink(), "RETAINED_SOURCE_JOURNAL_REQUIRED")
    wal = Path(str(SOURCE) + "-wal")
    require(not wal.exists() or wal.stat().st_size == 0, "SOURCE_WAL_NOT_EMPTY")
    require(sha(SOURCE) == SOURCE_SHA256, "SOURCE_JOURNAL_SHA256_MISMATCH")
    result = snapshot(SOURCE, immutable=True)
    require(result["budget"] == SOURCE_BUDGET and result["audit_seq"] == SOURCE_SEQUENCE
            and result["audit_head"] == SOURCE_HEAD, "SOURCE_29_OF_128_ANCHOR_MISMATCH")
    require(KEY not in result["states"], "SOURCE_ALREADY_RESERVED_THIS_FAMILY")
    return result


def _prepare(protocol_path: Path, manifest_path: Path) -> dict[str, Any]:
    protocol = read(protocol_path)
    require(isinstance(protocol, dict) and protocol.get("study_id") == STUDY, "STUDY_ID_REQUIRED")
    require(protocol.get("origin") == "HISTORICAL", "HISTORICAL_ONLY")
    require(protocol.get("base_protocol") == BASE_PROTOCOL
            and protocol.get("dataset") == DATASET, "EXACT_BASE_PROTOCOL_AND_DATASET_REQUIRED")
    definition_at = protocol.get("definition_recorded_at")
    require(isinstance(definition_at, str) and definition_at, "PROTOCOL_DEFINITION_TIMESTAMP_REQUIRED")
    for flag in ("independent_preregistration", "financial_acceptance_allowed", "live_approved"):
        require(protocol.get(flag) is False, "AUTHORITY_NOT_PERMITTED:" + flag)
    require(protocol.get("execution_allowed", False) is False, "AUTHORITY_NOT_PERMITTED:execution_allowed")
    budget = protocol.get("budget", {})
    require(budget.get("policies") == POLICIES and budget.get("scenarios") == SCENARIOS
            and budget.get("new_policy_scenario_measurements") == SLOTS
            and budget.get("source_budget_spent") == 29
            and budget.get("source_budget_limit") == 128
            and budget.get("descendant_expected_spent") == 41
            and budget.get("cash_is_derived_reference") is True, "FINITE_TWELVE_SLOT_BUDGET_REQUIRED")
    manifest = read(manifest_path)
    if isinstance(manifest, list):
        require(all(isinstance(row, dict) and set(row) == {"path", "sha256"} for row in manifest), "MANIFEST_LIST_SCHEMA")
        rows = [(row["path"], row["sha256"]) for row in manifest]
        base = manifest_path.parent
    else:
        require(isinstance(manifest, dict), "MANIFEST_OBJECT_REQUIRED")
        rows = list(manifest.items())
        base = APP
    require(bool(rows), "EMPTY_SOURCE_MANIFEST")
    hashes: dict[str, str] = {}
    resolved: dict[Path, str] = {}
    for name, expected in rows:
        require(isinstance(name, str) and name and not Path(name).is_absolute(), "MANIFEST_RELATIVE_PATH_REQUIRED")
        require(isinstance(expected, str) and len(expected) == 64 and all(c in "0123456789abcdef" for c in expected), "MANIFEST_SHA256_REQUIRED")
        target = base / name
        require(target.is_file() and not target.is_symlink(), "MANIFEST_REGULAR_SOURCE_REQUIRED:" + name)
        real = target.resolve()
        require(real.is_relative_to(APP.resolve()), "MANIFEST_SOURCE_OUTSIDE_APP:" + name)
        require(name not in hashes and real not in resolved, "MANIFEST_DUPLICATE_SOURCE")
        require(sha(target) == expected, "SOURCE_HASH_MISMATCH:" + name)
        hashes[name] = expected
        resolved[real] = name
    required = {protocol_path.resolve(), (APP / BASE_PROTOCOL).resolve(), (APP / DATASET).resolve(),
                *((APP / name).resolve() for name in REQUIRED_CODE)}
    for pattern in REQUIRED_GLOBS:
        required.update(path.resolve() for path in APP.glob(pattern) if path.is_file())
    missing = sorted(str(path.relative_to(APP.resolve())) for path in required if path not in resolved)
    require(not missing, "MANIFEST_MISSING_REQUIRED_BINDING:" + ",".join(missing))
    identity = {"study_id": STUDY, "protocol_sha256": sha(protocol_path),
                "protocol_definition_recorded_at": definition_at,
                "protocol_definition_timestamp_scope": "HASH_BOUND_PROTOCOL_DECLARATION_NOT_INDEPENDENT_TIME_AUTHENTICATION",
                "manifest_sha256": sha(manifest_path), "source_hashes": dict(sorted(hashes.items())),
                "source_journal": {"sha256": SOURCE_SHA256, "audit_seq": SOURCE_SEQUENCE,
                                   "audit_head": SOURCE_HEAD, "budget": SOURCE_BUDGET},
                "policies": POLICIES, "scenarios": SCENARIOS, "slots": SLOTS}
    return {"schema": "HARPOON_QUANT8_BINDING_1", "identity": identity,
            "identity_hash": digest(identity), "independent_preregistration": False,
            "financial_acceptance_allowed": False, "live_approved": False, "execution_allowed": False}


def _state(path: Path, source: dict[str, Any], plan: dict[str, Any], *, complete: bool) -> dict[str, Any]:
    result = snapshot(path)
    require(result["audit"][:SOURCE_SEQUENCE] == source["audit"], "DESCENDANT_ANCESTRY_MISMATCH")
    require(result["holdouts"] == source["holdouts"], "DESCENDANT_HOLDOUTS_CHANGED")
    events = result["audit"][SOURCE_SEQUENCE:]
    require([json.loads(row[1])["key"] for row in events] in ([], ["budget", KEY]), "DESCENDANT_EXTRA_AUDIT_EVENTS")
    reserved = len(events) == 2
    require(not complete or reserved, "FAMILY_NOT_RESERVED")
    require(set(result["states"]) == set(source["states"]) | ({KEY} if reserved else set()), "DESCENDANT_STATE_KEYS_CHANGED")
    require(all(result["states"][key] == value for key, value in source["states"].items() if key != "budget"), "INHERITED_STATE_CHANGED")
    require(result["budget"] == {"spent": 41 if reserved else 29, "limit": 128}, "DESCENDANT_BUDGET_CHANGED")
    if reserved:
        record = result["states"][KEY]
        require(record.get("identity_hash") == plan["identity_hash"] and record.get("identity") == plan["identity"], "FAMILY_IDENTITY_CONFLICT")
        require(record.get("schema") == SCHEMA and record.get("slots") == SLOTS
                and record.get("budget_before") == 29 and record.get("budget_after") == 41
                and record.get("budget_limit") == 128 and record.get("stage") == "RESERVED"
                and record.get("registered_at_clock") == LOCAL_CLOCK, "FAMILY_RESERVATION_INVALID")
        require(all(record.get(flag) is False for flag in ("independent_preregistration", "financial_acceptance_allowed", "live_approved", "execution_allowed")), "RESERVATION_AUTHORITY_INVALID")
    return result


def _directory(output_dir: Path) -> Path:
    output_dir = Path(output_dir)
    require(not output_dir.is_symlink() and output_dir.resolve() == OUTPUT.resolve(), "SINGLE_CANONICAL_DESCENDANT_REQUIRED")
    descendant = output_dir / DESCENDANT
    require(not descendant.is_symlink(), "DESCENDANT_SYMLINK_NOT_ALLOWED")
    require(not descendant.exists() or not os.path.samefile(descendant, SOURCE), "DESCENDANT_MUST_NOT_ALIAS_SOURCE")
    return output_dir.resolve()


def _checkpoint(path: Path) -> None:
    """Recover a committed WAL before hashing the portable single-file journal."""
    wal = Path(str(path) + "-wal")
    if not wal.exists() or wal.stat().st_size == 0:
        return
    journal = Journal(path)
    try:
        checkpoint = journal.db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        require(checkpoint[0] == 0, "JOURNAL_CHECKPOINT_PENDING")
    finally:
        journal.close()
    require(not wal.exists() or wal.stat().st_size == 0, "JOURNAL_CHECKPOINT_PENDING")
    _sync_directory(path.parent)


def _result(directory: Path, source: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    descendant = directory / DESCENDANT
    current = _state(descendant, source, plan, complete=True)
    record = current["states"][KEY]
    return {"schema": SCHEMA, "study_id": STUDY, "verified": True,
            "identity_hash": plan["identity_hash"], "reservation_hash": digest(record),
            "registered_at": record["registered_at"], "registered_at_clock": record["registered_at_clock"],
            "protocol_definition_recorded_at": plan["identity"]["protocol_definition_recorded_at"],
            "ordering_authority": "LOCAL_AUDIT_SEQUENCE_NOT_EXECUTOR_WALL_CLOCK", "budget_path": [29, 41], "family_slots": SLOTS,
            "descendant_journal": {"path": DESCENDANT, "sha256": sha(descendant),
                                   "audit_seq": current["audit_seq"], "audit_head": current["audit_head"], "budget": current["budget"]},
            "source_journal": plan["identity"]["source_journal"],
            "source_journal_bytes_unchanged": sha(SOURCE) == SOURCE_SHA256,
            "independent_preregistration": False, "financial_acceptance_allowed": False,
            "live_approved": False, "execution_allowed": False,
            "global_deduplicated_search_total": None, "global_search_correction_complete": False,
            "scope": "Twelve finite offline diagnostics; reused past data, no untouched holdout or economic approval."}


def register(protocol_path: Path, source_manifest_path: Path, output_dir: Path) -> dict[str, Any]:
    """Reserve once, or return the byte-stable existing reservation. Never fit."""
    protocol_path, source_manifest_path = Path(protocol_path), Path(source_manifest_path)
    source = _source()
    plan = _prepare(protocol_path, source_manifest_path)
    directory = _directory(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / ".quant8_register.lock"
    require(not lock_path.is_symlink(), "LOCK_SYMLINK_NOT_ALLOWED")
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("REGISTRATION_ALREADY_RUNNING") from exc
        descendant = directory / DESCENDANT
        fork = {"schema": "HARPOON_QUANT8_FORK_1", "identity_hash": plan["identity_hash"],
                "source_journal": plan["identity"]["source_journal"], "descendant_journal": DESCENDANT,
                "copied_once": True, "independent_preregistration": False}
        if (directory / FORK).exists():
            require(read(directory / FORK) == fork, "FORK_IDENTITY_CONFLICT")
            require(descendant.is_file(), "DESCENDANT_MISSING_NO_RESET")
        else:
            require(not (directory / OVERVIEW).exists(), "FORK_MISSING_NO_RESET")
            if descendant.exists():
                require(sha(descendant) == SOURCE_SHA256, "UNRECEIPTED_DESCENDANT_NO_RESET")
            else:
                fd, temporary = tempfile.mkstemp(prefix=".journal.", dir=directory)
                try:
                    with os.fdopen(fd, "wb") as handle:
                        handle.write(SOURCE.read_bytes())
                        handle.flush()
                        os.fsync(handle.fileno())
                    require(sha(Path(temporary)) == SOURCE_SHA256, "SOURCE_COPY_MISMATCH")
                    os.link(temporary, descendant)
                    _sync_directory(directory)
                finally:
                    os.unlink(temporary)
            _write_once(directory / FORK, fork)
        _write_once(directory / BINDING, plan)
        current = _state(descendant, source, plan, complete=False)
        _checkpoint(descendant)
        if (directory / OVERVIEW).exists():
            require(read(directory / OVERVIEW) == _result(directory, source, plan), "REGISTRATION_RECEIPT_CONFLICT")
        if KEY not in current["states"]:
            journal = Journal(descendant)
            try:
                journal.db.execute("PRAGMA synchronous=FULL")
                with journal.transaction():
                    journal.verify()
                    head = journal.db.execute("SELECT h FROM optimizer_audit ORDER BY seq DESC LIMIT 1").fetchone()[0]
                    require(head == current["audit_head"] and journal.get("budget") == SOURCE_BUDGET
                            and journal.get(KEY) is None, "RESERVATION_HEAD_CONFLICT")
                    now = datetime.now(UTC).isoformat()
                    record = {"schema": SCHEMA, "identity_hash": plan["identity_hash"], "identity": plan["identity"],
                              "slots": SLOTS, "budget_before": 29, "budget_after": 41, "budget_limit": 128,
                              "stage": "RESERVED", "registered_at": now, "registered_at_clock": LOCAL_CLOCK, "independent_preregistration": False,
                              "financial_acceptance_allowed": False, "live_approved": False, "execution_allowed": False}
                    journal.put("budget", {"spent": 41, "limit": 128}, now)
                    journal.put(KEY, record, now)
                checkpoint = journal.db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                require(checkpoint[0] == 0, "JOURNAL_CHECKPOINT_PENDING")
            finally:
                journal.close()
            _sync_directory(directory)
        result = _result(directory, source, plan)
        require(result["source_journal_bytes_unchanged"], "SOURCE_CHANGED_DURING_REGISTRATION")
        _write_once(directory / OVERVIEW, result)
        return result


def verify(directory: Path, protocol_path: Path, source_manifest_path: Path) -> dict[str, Any]:
    """Recheck every binding and descendant event, with no writes or debits."""
    source = _source()
    plan = _prepare(Path(protocol_path), Path(source_manifest_path))
    directory = _directory(directory)
    require(read(directory / BINDING) == plan, "BINDING_CONFLICT")
    fork = read(directory / FORK)
    require(fork.get("identity_hash") == plan["identity_hash"]
            and fork.get("source_journal") == plan["identity"]["source_journal"]
            and fork.get("descendant_journal") == DESCENDANT, "FORK_IDENTITY_CONFLICT")
    wal = Path(str(directory / DESCENDANT) + "-wal")
    require(not wal.exists() or wal.stat().st_size == 0, "JOURNAL_CHECKPOINT_REQUIRED_RUN_REGISTER")
    result = _result(directory, source, plan)
    require(result["source_journal_bytes_unchanged"], "SOURCE_CHANGED")
    require(read(directory / OVERVIEW) == result, "REGISTRATION_RECEIPT_CONFLICT")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--source-hashes", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    try:
        result = verify(args.output_dir, args.protocol, args.source_hashes) if args.verify else register(args.protocol, args.source_hashes, args.output_dir)
        print(json.dumps(result, allow_nan=False))
        return 0
    except (ValueError, OSError, TypeError, KeyError, sqlite3.Error) as exc:
        print(json.dumps({"schema": SCHEMA, "verified": False, "reason": str(exc), "financial_acceptance_allowed": False, "execution_allowed": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
