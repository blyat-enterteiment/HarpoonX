#!/usr/bin/env python3
"""Reserve the six fixed historical measurements on one retained descendant.

This is an offline budget registrar, not a financial or production gate. It binds
fitting recipes before their weights exist. It does not run a fit, replay, broker
request, or order. A local registration made today does not turn old prices into
prospective evidence. The retained global search count remains unknown.
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

from harpoon_quant import measurement_registration as measurement  # noqa: E402
from harpoon_quant.core import digest  # noqa: E402
from harpoon_quant.recursive import Journal  # noqa: E402

SCHEMA = "HARPOON_HISTORICAL_BANK_REGISTRATION_1"
SOURCE_SHA256 = "c34112040413d8c6496c90077c9d64044c563cef53e13a2b423db138091f96cd"
SOURCE_HEAD = "df39e861ed2aa086dfb80c782d7924bead338fa6dfc1a28dc202616d5c3c1208"
SOURCE_SEQUENCE = 78
SOURCE_BUDGET = {"spent": 23, "limit": 128}
SCENARIOS = ("NOMINAL", "STRESS")
POLICIES = ("C0", "RIDGE", "SVR")
UNIVERSE = ("AAPL", "MSFT", "SPY", "XLK")
DESCENDANT = "optimizer.descendant.sqlite3"
FORK_FILE = "fork_receipt.json"
OVERVIEW = "historical_bank_registration.json"
REQUIRED_CODE = (
    "tools/historical_bank_register.py",
    "quant/harpoon_quant/measurement_registration.py",
    "quant/harpoon_quant/recursive.py",
    "quant/harpoon_quant/core.py",
    "quant/harpoon_quant/study_integrity.py",
)


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_JSON_KEY:" + key)
        result[key] = value
    return result


def _float(text: str) -> float:
    value = float(text)
    require(math.isfinite(value), "NONFINITE_JSON_NUMBER")
    return value


def _constant(text: str) -> Any:
    raise ValueError("NONFINITE_JSON_CONSTANT:" + text)


def read(path: Path) -> Any:
    return json.loads(path.read_bytes(), object_pairs_hook=_unique,
                      parse_float=_float, parse_constant=_constant)


def _bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def write_once(path: Path, value: Any) -> None:
    """Never overwrite a receipt, including after an interrupted invocation."""
    encoded = _bytes(value)
    if path.exists():
        require(path.is_file() and not path.is_symlink() and path.read_bytes() == encoded,
                "EXISTING_ARTIFACT_CONFLICT:" + path.name)
        return
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)  # Creation is atomic and cannot replace a file.
        except FileExistsError:
            require(path.is_file() and not path.is_symlink() and path.read_bytes() == encoded,
                    "EXISTING_ARTIFACT_CONFLICT:" + path.name)
    finally:
        os.unlink(temporary)


def _snapshot(path: Path, *, immutable: bool = False) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), "EXISTING_REGULAR_JOURNAL_REQUIRED")
    reader = Journal.__new__(Journal)
    suffix = "?mode=ro&immutable=1" if immutable else "?mode=ro"
    reader.db = sqlite3.connect(path.resolve().as_uri() + suffix, uri=True)
    reader.integrity_report = {}
    try:
        reader.db.execute("BEGIN")
        reader.verify()
        audit = list(reader.db.execute("SELECT seq,payload,previous,h FROM optimizer_audit ORDER BY seq"))
        states = {k: json.loads(v) for k, v in reader.db.execute("SELECT k,v FROM optimizer_state")}
        require(bool(audit), "AUDITED_JOURNAL_REQUIRED")
        return {"audit": audit, "states": states, "budget": reader.get("budget"),
                "audit_seq": audit[-1][0], "audit_head": audit[-1][3],
                "holdouts": sorted(reader._holdout_rows()), "integrity": reader.integrity_report}
    finally:
        reader.close()


def source_anchor(path: Path) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), "SOURCE_JOURNAL_REQUIRED")
    wal = Path(str(path) + "-wal")
    require(not wal.exists() or wal.stat().st_size == 0, "SOURCE_WAL_NOT_EMPTY")
    require(sha(path) == SOURCE_SHA256, "SOURCE_JOURNAL_SHA256_MISMATCH")
    result = _snapshot(path, immutable=True)
    require(result["budget"] == SOURCE_BUDGET and result["audit_seq"] == SOURCE_SEQUENCE
            and result["audit_head"] == SOURCE_HEAD, "SOURCE_JOURNAL_ANCHOR_MISMATCH")
    require(not any(k.startswith(measurement.PREFIX) for k in result["states"]),
            "SOURCE_ALREADY_HAS_MEASUREMENT_RESERVATIONS")
    return result


def _manifest(path: Path) -> tuple[dict[str, str], dict[Path, str]]:
    value = read(path)
    if isinstance(value, list):
        require(all(isinstance(row, dict) and set(row) == {"path", "sha256"} for row in value),
                "SOURCE_MANIFEST_ENTRY_SCHEMA")
        rows = [(row["path"], row["sha256"]) for row in value]
        base = path.parent
    else:
        require(isinstance(value, dict), "SOURCE_MANIFEST_SCHEMA")
        rows = list(value.items())
        # Maps use integral-root names, independently of the manifest's folder.
        # List entries retain the documented path-relative-to-manifest form.
        base = APP
    require(bool(rows), "EXPLICIT_SOURCE_HASHES_REQUIRED")
    hashes, resolved = {}, {}
    for name, expected in rows:
        require(isinstance(name, str) and name and not Path(name).is_absolute(),
                "RELATIVE_SOURCE_PATH_REQUIRED")
        require(isinstance(expected, str) and len(expected) == 64
                and all(c in "0123456789abcdef" for c in expected), "SOURCE_HASH_SCHEMA")
        require(name not in hashes, "DUPLICATE_SOURCE_PATH")
        target = (base / name).resolve()
        require(target not in resolved, "DUPLICATE_RESOLVED_SOURCE")
        require(target.is_file() and sha(target) == expected, "SOURCE_HASH_MISMATCH:" + name)
        hashes[name] = expected
        resolved[target] = name
    return dict(sorted(hashes.items())), resolved


def prepare(protocol_path: Path, dataset_path: Path, manifest_path: Path) -> dict[str, Any]:
    """Read and bind inputs; never create a journal or spend budget."""
    protocol, dataset = read(protocol_path), read(dataset_path)
    require(isinstance(protocol, dict) and protocol.get("schema") == "HARPOON_HISTORICAL_BANK_PROTOCOL_1",
            "HISTORICAL_PROTOCOL_SCHEMA")
    require(protocol.get("origin") == "HISTORICAL" and protocol.get("execution") == "MODELED_OHLCV",
            "HISTORICAL_MODELED_ONLY")
    for flag in ("independent_preregistration", "financial_acceptance_allowed", "live_approved"):
        require(protocol.get(flag) is False, "PROTOCOL_AUTHORITY_NOT_PERMITTED:" + flag)
    require(protocol.get("universe") == list(UNIVERSE), "FOUR_ASSET_PROTOCOL_REQUIRED")
    require(protocol.get("native_control") == "NATIVE_HISTORICAL_ULTIMATE"
            and protocol.get("native_control_is_production_coordinator") is False,
            "NATIVE_CONTROL_SCOPE")
    require(set(protocol.get("models", {})) == {"RIDGE", "SVR"}, "TWO_FIXED_MODEL_RECIPES_REQUIRED")
    require(all(protocol["models"][role].get("hyperparameter_search") is False for role in ("RIDGE", "SVR")),
            "HYPERPARAMETER_SEARCH_NOT_PERMITTED")
    require(set(protocol.get("scenarios", {})) == set(SCENARIOS), "TWO_SCENARIOS_REQUIRED")
    budget = protocol.get("budget", {})
    require(budget.get("policies") == list(POLICIES) and budget.get("scenarios") == list(SCENARIOS)
            and budget.get("new_policy_scenario_measurements") == 6
            and "model_fits" not in budget
            and budget.get("unique_model_fit_recipes") == 8
            and budget.get("primary_model_fit_invocations") == 8
            and budget.get("planned_total_fit_invocations_including_exact_verification") == 32
            and budget.get("model_selection_trials") == 0
            and budget.get("source_budget_spent") == 23 and budget.get("source_budget_limit") == 128
            and budget.get("descendant_expected_spent") == 29
            and budget.get("cash_is_derived_reference") is True and budget.get("retry_identical_only") is True,
            "SIX_MEASUREMENT_BUDGET_CONTRACT")
    require(protocol.get("statistics", {}).get("global_deduplicated_search_total") is None
            and protocol["statistics"].get("global_search_correction_complete") is False,
            "GLOBAL_SEARCH_COUNT_UNKNOWN")
    temporal = protocol.get("temporal_design", {})
    require(temporal.get("parameter_selection_from_validation") is False
            and temporal.get("refit_count_per_model_asset") == 1
            and temporal.get("refit_after_validation") is False
            and temporal.get("positions_and_cash_continue_between_phases") is True
            and temporal.get("test_is_prospective") is False, "FIXED_CONTINUOUS_HISTORICAL_DESIGN_REQUIRED")
    require(isinstance(dataset, dict) and dataset.get("schema") == "HARPOON-ULTIMATE-DATA-1",
            "DATASET_SCHEMA")
    require(sorted(row.get("symbol") for row in dataset.get("series", [])) == list(UNIVERSE),
            "DATASET_UNIVERSE_BINDING")
    hashes, resolved = _manifest(manifest_path)
    required = [protocol_path.resolve(), dataset_path.resolve(), *(APP / name for name in REQUIRED_CODE)]
    require(all(path in resolved for path in required), "MANIFEST_MISSING_PROTOCOL_DATASET_OR_REGISTRATION_CODE")
    source_files = dataset.get("provenance", {}).get("files")
    require(isinstance(source_files, list) and bool(source_files), "RETAINED_DATA_SOURCES_REQUIRED")
    provenance_seen = set()
    for item in source_files:
        require(isinstance(item, dict) and isinstance(item.get("name"), str), "DATA_SOURCE_REFERENCE_SCHEMA")
        name = item["name"]
        require(name not in provenance_seen and not Path(name).is_absolute(), "DATA_SOURCE_DUPLICATE_OR_ABSOLUTE")
        provenance_seen.add(name)
        target = (dataset_path.parent / name).resolve()
        require(target.is_file() and sha(target) == item.get("sha256"), "RETAINED_DATA_SOURCE_HASH_MISMATCH:" + name)
    refs = {"protocol": {"path": resolved[protocol_path.resolve()], "sha256": sha(protocol_path)},
            "dataset": {"path": resolved[dataset_path.resolve()], "sha256": sha(dataset_path)},
            "source_manifest": {"sha256": sha(manifest_path)}}
    recipes = {}
    for role in ("RIDGE", "SVR"):
        recipe = {"estimator": protocol["models"][role], "features": protocol["features"],
                  "target": protocol["target"], "periods": protocol["periods"],
                  "temporal_design": temporal, "universe": protocol["universe"],
                  "admission": protocol["admission"]}
        recipes[role] = {"binding_kind": "FIXED_FIT_RECIPE", "recipe": recipe,
                         "recipe_hash": digest(recipe), "fitted_model_hash": None,
                         "fitted_model_hash_reason": "Weights do not exist at this registration; only the fixed fitting procedure is bound."}
    bindings = {}
    for scenario in SCENARIOS:
        request = {"schema": "HARPOON_FUNDED_COMPARISON_REQUEST_1",
                   "purpose": "PREREGISTERED_FIXED_MODEL_MEASUREMENT",
                   "binding_scope": "FIXED_FIT_RECIPE_BEFORE_HISTORICAL_EXECUTION",
                   "production_request_compatible": False,
                   "common_request": {"data_origin": "HISTORICAL", "study_id": protocol["study_id"],
                                      "scenario": scenario, "costs": protocol["scenarios"][scenario],
                                      "protocol": protocol, "input_refs": refs,
                                      "policy_roles": {"C0": "NATIVE_HISTORICAL_ULTIMATE", "RIDGE": "RIDGE", "SVR": "SVR"},
                                      "native_control_is_production_coordinator": False},
                   "models": recipes, "source_hashes": hashes,
                   "independent_preregistration": False, "execution_allowed": False,
                   "financial_acceptance_allowed": False, "global_deduplicated_search_total": None}
        request_canonical = canonical(request)
        binding_hash, _ = measurement._binding(request_canonical)
        bindings[scenario] = {"schema": "HARPOON_HISTORICAL_MEASUREMENT_BINDING_1", "scenario": scenario,
                              "binding_hash": binding_hash, "request_canonical": request_canonical}
    identity = {"study_id": protocol["study_id"], "input_refs": refs,
                "source_hashes": hashes, "scenario_bindings": {k: v["binding_hash"] for k, v in bindings.items()},
                "source_journal": {"sha256": SOURCE_SHA256, "audit_seq": SOURCE_SEQUENCE,
                                   "audit_head": SOURCE_HEAD, "budget": SOURCE_BUDGET}}
    return {"identity": identity, "identity_hash": digest(identity), "bindings": bindings,
            "fit_accounting": {key: budget[key] for key in (
                "unique_model_fit_recipes", "primary_model_fit_invocations",
                "planned_total_fit_invocations_including_exact_verification", "model_selection_trials")},
            "retained_dataset_source_count": len(source_files)}


def _descendant_state(path: Path, source: dict[str, Any], bindings: dict[str, Any]) -> dict[str, Any]:
    snapshot = _snapshot(path)
    audit, states = snapshot["audit"], snapshot["states"]
    require(audit[:SOURCE_SEQUENCE] == source["audit"], "DESCENDANT_ANCESTRY_MISMATCH")
    require(snapshot["holdouts"] == source["holdouts"], "DESCENDANT_HOLDOUTS_CHANGED")
    expected_keys = [measurement.PREFIX + bindings[scenario]["binding_hash"] for scenario in SCENARIOS]
    appended = [json.loads(row[1])["key"] for row in audit[SOURCE_SEQUENCE:]]
    legal_prefixes = ([], ["budget", expected_keys[0]], ["budget", expected_keys[0], "budget", expected_keys[1]])
    require(appended in legal_prefixes, "DESCENDANT_UNREGISTERED_AUDIT_EVENTS")
    count = len(appended) // 2
    require(set(states) == set(source["states"]) | set(expected_keys[:count]), "DESCENDANT_STATE_KEYS_CHANGED")
    require(all(states[key] == value for key, value in source["states"].items() if key != "budget"),
            "DESCENDANT_RETAINED_STATE_CHANGED")
    require(snapshot["budget"] == {"spent": 23 + count * 3, "limit": 128}, "DESCENDANT_BUDGET_CHANGED")
    for i, key in enumerate(expected_keys[:count]):
        record = states[key]
        require(record.get("budget_before") == 23 + i * 3 and record.get("budget_after") == 26 + i * 3
                and record.get("family_slots_after") == 3 + i * 3, "DESCENDANT_RESERVATION_SEQUENCE")
    return snapshot


def register(protocol_path: Path, dataset_path: Path, manifest_path: Path,
             source_journal: Path, output_dir: Path) -> dict[str, Any]:
    protocol_path, dataset_path, manifest_path, source_journal = [
        Path(p).resolve() for p in (protocol_path, dataset_path, manifest_path, source_journal)]
    output_dir = Path(output_dir).resolve()
    descendant = output_dir / DESCENDANT
    require(descendant != source_journal, "SOURCE_CANNOT_BE_DESCENDANT")
    require(not (output_dir / FORK_FILE).is_symlink() and not descendant.is_symlink(), "OUTPUT_SYMLINK_NOT_ALLOWED")
    require(not descendant.exists() or not os.path.samefile(descendant, source_journal),
            "DESCENDANT_MUST_NOT_ALIAS_SOURCE")
    # Validate all immutable inputs before creating the output or opening a writer.
    plan = prepare(protocol_path, dataset_path, manifest_path)
    source = source_anchor(source_journal)
    output_dir.mkdir(parents=True, exist_ok=True)
    lock_path = output_dir / ".historical_bank_register.lock"
    require(not lock_path.is_symlink(), "LOCK_SYMLINK_NOT_ALLOWED")
    with lock_path.open("a+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("REGISTRATION_ALREADY_RUNNING") from exc
        fork_path = output_dir / FORK_FILE
        if fork_path.exists():
            fork = read(fork_path)
            require(fork.get("schema") == "HARPOON_HISTORICAL_JOURNAL_FORK_1"
                    and fork.get("identity_hash") == plan["identity_hash"]
                    and fork.get("identity") == plan["identity"]
                    and fork.get("descendant_journal") == DESCENDANT, "FORK_IDENTITY_CONFLICT")
            require(descendant.is_file(), "DESCENDANT_JOURNAL_MISSING_NO_RESET")
        else:
            require(not (output_dir / OVERVIEW).exists(), "FORK_RECEIPT_MISSING_NO_RESET")
            if descendant.exists():
                require(sha(descendant) == SOURCE_SHA256, "UNRECEIPTED_DESCENDANT_NO_RESET")
            else:
                with descendant.open("xb") as dest, source_journal.open("rb") as src:
                    for chunk in iter(lambda: src.read(1024 * 1024), b""):
                        dest.write(chunk)
                    dest.flush()
                    os.fsync(dest.fileno())
                require(sha(descendant) == SOURCE_SHA256, "DESCENDANT_COPY_HASH_MISMATCH")
            fork = {"schema": "HARPOON_HISTORICAL_JOURNAL_FORK_1",
                    "created_at": datetime.now(UTC).isoformat(),
                    "identity_hash": plan["identity_hash"], "identity": plan["identity"],
                    "source_journal_original_path": str(source_journal),
                    "source_journal_relative_path": os.path.relpath(source_journal, output_dir),
                    "descendant_journal": DESCENDANT, "copied_once": True,
                    "independent_preregistration": False, "execution_allowed": False,
                    "global_deduplicated_search_total": None}
            write_once(fork_path, fork)
        snapshot = _descendant_state(descendant, source, plan["bindings"])
        # Both exact requests are retained before spending the first three slots.
        for scenario in SCENARIOS:
            write_once(output_dir / (scenario + ".binding.json"), plan["bindings"][scenario])
        # A conflicting pre-existing receipt must fail before any further debit.
        for scenario in SCENARIOS:
            receipt_path = output_dir / (scenario + ".registration.json")
            if receipt_path.exists():
                require(not receipt_path.is_symlink(), "REGISTRATION_RECEIPT_SYMLINK")
                prior = read(receipt_path)
                require(prior.get("journal_relative_path") == DESCENDANT, "REGISTRATION_JOURNAL_LOCATOR")
                prior["journal_path"] = str(descendant)
                measurement.verify(prior, plan["bindings"][scenario]["request_canonical"])
        scenarios = {}
        for ordinal, scenario in enumerate(SCENARIOS, 1):
            binding = plan["bindings"][scenario]
            registration = measurement.reserve(descendant, binding["request_canonical"], snapshot["audit_head"])
            registration["journal_relative_path"] = DESCENDANT
            receipt_path = output_dir / (scenario + ".registration.json")
            if receipt_path.exists():
                prior = read(receipt_path)
                # Relocation changes only the journal locator, never reservation identity.
                prior["journal_path"] = str(descendant)
                require(prior == registration, "REGISTRATION_RECEIPT_CONFLICT:" + scenario)
            else:
                write_once(receipt_path, registration)
            checked = measurement.verify(registration, binding["request_canonical"])
            snapshot = _descendant_state(descendant, source, plan["bindings"])
            scenarios[scenario] = {"ordinal": ordinal, "binding_path": scenario + ".binding.json",
                                   "registration_path": scenario + ".registration.json",
                                   "binding_hash": binding["binding_hash"], "registration": registration,
                                   "verification": checked}
        require(snapshot["budget"] == {"spent": 29, "limit": 128}, "FINAL_BUDGET_MISMATCH")
        # Final verification uses the same final head for both, making repeat runs stable.
        for scenario in SCENARIOS:
            item = scenarios[scenario]
            item["verification"] = measurement.verify(item["registration"], plan["bindings"][scenario]["request_canonical"])
        require(sha(source_journal) == SOURCE_SHA256, "SOURCE_CHANGED_DURING_REGISTRATION")
        result = {"schema": SCHEMA, "study_id": plan["identity"]["study_id"],
                  "identity_hash": plan["identity_hash"], "verified": True,
                  "source_journal": plan["identity"]["source_journal"],
                  "descendant_journal": {"path": DESCENDANT, "sha256": sha(descendant),
                                         "audit_seq": snapshot["audit_seq"], "audit_head": snapshot["audit_head"],
                                         "budget": snapshot["budget"]},
                  "fork_receipt": {"path": FORK_FILE, "sha256": sha(fork_path)},
                  "budget_path": [23, 26, 29], "family_slots": 6,
                  "fit_accounting": plan["fit_accounting"],
                  "scenarios": scenarios, "retained_dataset_source_count": plan["retained_dataset_source_count"],
                  "model_binding_kind": "FIXED_FIT_RECIPE", "fitted_model_hashes": None,
                  "independent_preregistration": False, "retrospective_historical_registration": True,
                  "global_deduplicated_search_total": None, "global_search_correction_complete": False,
                  "execution_allowed": False, "financial_acceptance_allowed": False,
                  "live_approved": False, "source_journal_bytes_unchanged": True,
                  "scope": "Six offline measurements reserved, no fit or measurement executed. Local hash consistency is not external authentication or REAL level7 evidence."}
        overview = output_dir / OVERVIEW
        if overview.exists():
            prior = read(overview)
            for item in prior.get("scenarios", {}).values():
                item["registration"]["journal_path"] = str(descendant)
            require(prior == result, "OVERVIEW_CONFLICT")
        else:
            write_once(overview, result)
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--source-hashes", type=Path, required=True)
    parser.add_argument("--source-journal", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = register(args.protocol, args.dataset, args.source_hashes, args.source_journal, args.output_dir)
        print(json.dumps(result, allow_nan=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        print(json.dumps({"schema": SCHEMA, "verified": False, "reason": str(error),
                          "execution_allowed": False, "financial_acceptance_allowed": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
