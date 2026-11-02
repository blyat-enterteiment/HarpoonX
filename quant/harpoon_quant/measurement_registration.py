"""Budget reservations for a fixed C0/Ridge/SVR historical measurement.

This extends an existing Journal; it never creates or resets its budget. Local
hashes establish consistency, not independent preregistration or data provenance.
The exact JS-canonical request string avoids cross-language numeric ambiguity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .core import digest
from .recursive import Journal
from .study_integrity import _json

SCHEMA = "HARPOON_MEASUREMENT_REGISTRATION_1"
PREFIX = "measurement:funded:v1:"
SLOTS = 3
MAX_FAMILY_SLOTS = 6
MAX_BYTES = 32 * 1024 * 1024


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


class ReadOnlyJournal(Journal):
    def __init__(self, path: Path):
        require(path.is_file(), "EXISTING_JOURNAL_REQUIRED")
        self.db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        self.db.execute("BEGIN")
        self.integrity_report = {}
        try:
            self.verify()
        except BaseException:
            self.db.close()
            raise


def _head(journal: Journal) -> str:
    row = journal.db.execute("SELECT h FROM optimizer_audit ORDER BY seq DESC LIMIT 1").fetchone()
    require(row is not None, "AUDITED_EXISTING_JOURNAL_REQUIRED")
    return str(row[0])


def _binding(request_canonical: str) -> tuple[str, dict[str, Any]]:
    require(isinstance(request_canonical, str), "REQUEST_CANONICAL_STRING_REQUIRED")
    encoded = request_canonical.encode()
    require(0 < len(encoded) <= MAX_BYTES, "MEASUREMENT_REQUEST_BYTES")
    data = _json(encoded)
    require(data.get("schema") == "HARPOON_FUNDED_COMPARISON_REQUEST_1", "COMPARISON_SCHEMA")
    require(data.get("purpose") == "PREREGISTERED_FIXED_MODEL_MEASUREMENT", "MEASUREMENT_PURPOSE")
    require("registration" not in data, "REGISTRATION_EXCLUDED_FROM_BINDING")
    require(data.get("common_request", {}).get("data_origin") == "HISTORICAL", "HISTORICAL_REQUEST_REQUIRED")
    require(set(data.get("models", {})) == {"RIDGE", "SVR"}, "MODEL_BINDINGS_REQUIRED")
    hashes = data.get("source_hashes")
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError("CODE_BINDINGS_REQUIRED")
    require(all(isinstance(k, str) and isinstance(v, str) and len(v) == 64
                and all(c in "0123456789abcdef" for c in v) for k, v in hashes.items()), "CODE_HASH_SCHEMA")
    return hashlib.sha256(encoded).hexdigest(), data


def _receipt(path: Path, key: str, record: dict[str, Any], head: str) -> dict[str, Any]:
    return {"schema": SCHEMA, "journal_path": str(path.resolve()), "key": key,
            "reservation_hash": digest(record), "audit_head_at_reservation": head}


def reserve(path: Path, request_canonical: str, expected_head: str) -> dict[str, Any]:
    binding_hash, _ = _binding(request_canonical)
    key = PREFIX + binding_hash
    # Reject missing, empty, corrupted or unaudited databases before opening a writer.
    reader = ReadOnlyJournal(path)
    try:
        current = _head(reader)
        existing = reader.get(key)
        require(current == expected_head or existing is not None, "JOURNAL_HEAD_CONFLICT")
        require(isinstance(reader.get("budget"), dict), "EXISTING_BUDGET_REQUIRED")
    finally:
        reader.close()
    journal = Journal(path)
    try:
        with journal.transaction():
            prior = journal.get(key)
            if prior is not None:
                require(prior.get("binding_hash") == binding_hash, "IDEMPOTENCY_BINDING_CONFLICT")
                row = journal.db.execute("SELECT h,payload FROM optimizer_audit WHERE json_extract(payload,'$.key')=? ORDER BY seq DESC LIMIT 1", (key,)).fetchone()
                require(row is not None, "RESERVATION_EVENT_REQUIRED")
                return _receipt(path, key, prior, row[0])
            require(_head(journal) == expected_head, "JOURNAL_HEAD_CONFLICT")
            budget = journal.get("budget")
            require(isinstance(budget, dict) and type(budget.get("spent")) is int
                    and type(budget.get("limit")) is int, "EXISTING_BUDGET_REQUIRED")
            before = budget["spent"]
            family_slots = 0
            for row in journal.db.execute("SELECT k FROM optimizer_state WHERE k LIKE ?", (PREFIX + "%",)):
                prior_record = journal.get(row[0])
                require(prior_record.get("slots") == SLOTS, "MEASUREMENT_FAMILY_RECORD")
                family_slots += prior_record["slots"]
            require(family_slots + SLOTS <= MAX_FAMILY_SLOTS, "MEASUREMENT_FAMILY_BUDGET_EXHAUSTED")
            require(before + SLOTS <= budget["limit"], "LIFETIME_BUDGET_EXHAUSTED")
            now = datetime.now(UTC).isoformat()
            record = {"schema": SCHEMA, "binding_hash": binding_hash, "slots": SLOTS,
                      "policies": ["C0", "RIDGE", "SVR"], "registered_at": now,
                      "budget_before": before, "budget_after": before + SLOTS,
                      "budget_limit_unchanged": budget["limit"], "prior_audit_head": expected_head,
                      "family_slots_after": family_slots + SLOTS, "stage": "RESERVED",
                      "independent_preregistration": False, "grants_order_authority": False}
            journal.put("budget", {**budget, "spent": before + SLOTS}, now)
            journal.put(key, record, now)
            result = _receipt(path, key, record, _head(journal))
        return result
    finally:
        journal.close()


def verify(registration: dict[str, Any], request_canonical: str) -> dict[str, Any]:
    binding_hash, _ = _binding(request_canonical)
    require(registration.get("schema") == SCHEMA, "REGISTRATION_SCHEMA")
    require(registration.get("key") == PREFIX + binding_hash, "RESERVATION_REQUEST_MISMATCH")
    path = Path(registration["journal_path"])
    journal = ReadOnlyJournal(path)
    try:
        record = journal.get(registration["key"])
        require(isinstance(record, dict) and digest(record) == registration.get("reservation_hash"), "RESERVATION_RECORD_MISMATCH")
        require(record.get("schema") == SCHEMA and record.get("binding_hash") == binding_hash
                and record.get("slots") == SLOTS and record.get("policies") == ["C0", "RIDGE", "SVR"]
                and record.get("stage") == "RESERVED", "RESERVATION_BINDING")
        require(record["budget_after"] == record["budget_before"] + SLOTS
                and SLOTS <= record["family_slots_after"] <= MAX_FAMILY_SLOTS, "RESERVATION_BUDGET")
        budget = journal.get("budget")
        require(budget["spent"] >= record["budget_after"]
                and budget["limit"] == record["budget_limit_unchanged"], "RESERVATION_BUDGET_CHANGED")
        event = journal.db.execute("SELECT payload FROM optimizer_audit WHERE h=?", (registration["audit_head_at_reservation"],)).fetchone()
        require(event is not None, "RESERVATION_AUDIT_EVENT_MISSING")
        expected_event = {"key": registration["key"], "value_hash": digest(record), "at": record["registered_at"]}
        require(json.loads(event[0]) == expected_event, "RESERVATION_AUDIT_BINDING")
        return {"verified": True, "binding_hash": binding_hash,
                "budget_before": record["budget_before"], "budget_after": record["budget_after"],
                "slots": SLOTS, "registered_at": record["registered_at"],
                "journal_current_head": _head(journal), "external_authentication": False,
                "execution_allowed": False, "financial_acceptance_allowed": False,
                "scope": "Local reservation integrity; does not authenticate prices, costs or independent preregistration."}
    finally:
        journal.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-stdin", action="store_true")
    parser.add_argument("--binding", type=Path)
    parser.add_argument("--journal", type=Path)
    parser.add_argument("--expected-head")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.verify_stdin:
            raw = sys.stdin.buffer.read(MAX_BYTES + 1)
            require(len(raw) <= MAX_BYTES, "REGISTRATION_STDIN_BYTES")
            data = _json(raw)
            result = verify(data["registration"], data["request_canonical"])
        else:
            require(args.binding is not None and args.journal is not None
                    and args.expected_head is not None and args.output is not None, "BINDING_JOURNAL_EXPECTED_HEAD_OUTPUT_REQUIRED")
            raw = args.binding.read_bytes()
            require(len(raw) <= MAX_BYTES, "BINDING_BYTES")
            data = _json(raw)
            binding_hash, _ = _binding(data["request_canonical"])
            require(data.get("binding_hash") == binding_hash, "BINDING_HASH_MISMATCH")
            result = reserve(args.journal, data["request_canonical"], args.expected_head)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))
        return 0
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as exc:
        print(json.dumps({"verified": False, "reason": str(exc), "execution_allowed": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
