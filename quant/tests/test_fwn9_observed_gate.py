"""P9M-A offline integrity fixtures, never observed market evidence."""
from __future__ import annotations

import copy
import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from harpoon_quant.fwn9_observed_gate import (
    SCHEMA,
    audit_receipt_tape,
    journal_preflight,
    receipt_sha256,
)

BINDING = "8ec3932f21de89e7ca92071d9d93b32999af55c15bfb97ec7288d4a0c230b7c4"
NOW = "2026-11-08T07:09:46Z"
H = "a" * 64


def fixture() -> dict:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    days = [(start + timedelta(days=i)).date().isoformat() for i in range(180)]
    dates = [
        "2025-01-11T12:00:00Z", "2025-01-11T12:05:00Z",
        "2025-01-11T13:00:00Z", "2025-01-11T13:30:00Z",
    ]
    events = [
        dict(id="s", order_id="order1", type="SIGNAL", symbol="SYNA",
             forecast_hash=H, effective_at=dates[0], known_at=dates[0]),
        dict(id="b", order_id="order1", type="ENTRY_FILL", quantity=10,
             price="100", fee_usd="0.05", effective_at=dates[1],
             known_at=dates[1]),
        dict(id="x1", order_id="order1", type="EXIT_FILL", quantity=4,
             price="103", fee_usd="0.02", effective_at=dates[2],
             known_at=dates[2]),
        dict(id="x2", order_id="order1", type="EXIT_FILL", quantity=6,
             price="105", fee_usd="0.03", effective_at=dates[3],
             known_at=dates[3]),
    ]
    return dict(schema=SCHEMA, source_nature="PROSPECTIVE_OBSERVED_EXECUTION_RECEIPTS",
                batch_id="engineering_fake", native_checkpoint_sha256=BINDING,
                development_days=days, holdout_start="2025-07-04",
                holdout_end="2025-09-04", events=events,
                labels=[dict(order_id="order1", label_known_at=dates[3],
                             net_usd="41.90")])


def run(tape: dict) -> dict:
    return audit_receipt_tape(
        tape, native_checkpoint_sha256=BINDING,
        externally_pinned_receipt_sha256=receipt_sha256(tape["events"]),
        now=NOW,
    )


class ReceiptIntakeTests(unittest.TestCase):
    def test_full_partial_exit_accounting_and_no_promotion(self) -> None:
        proof = run(fixture())
        self.assertEqual(proof["events_checked"], 4)
        self.assertEqual(proof["filled_campaigns"], 1)
        self.assertEqual(proof["net_receipts_usd"], "41.90")
        self.assertEqual(proof["physical_cash_end_usd"], "20041.90")
        self.assertFalse(proof["optimizer_eligible"])
        self.assertFalse(proof["independent_source_authentication"])
        self.assertEqual(proof["development_days"], 180)

    def test_missing_terminal_receipt(self) -> None:
        f = fixture()
        f["events"].pop()
        with self.assertRaisesRegex(ValueError, "OPEN_OR_PARTIAL_INVENTORY"):
            run(f)

    def test_oversell(self) -> None:
        f = fixture()
        f["events"][-1]["quantity"] = 7
        with self.assertRaisesRegex(ValueError, "OVERSELL"):
            run(f)

    def test_future_information_and_future_labels(self) -> None:
        f = fixture()
        f["events"][1]["known_at"] = "2027-01-01T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "NO_FUTURE_INFORMATION"):
            run(f)
        f = fixture()
        f["labels"][0]["label_known_at"] = "2027-01-01T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "FUTURE_LABEL"):
            run(f)

    def test_reject_model_relabel_even_with_matching_hash(self) -> None:
        f = fixture()
        f["source_nature"] = "HISTORICAL_MODELED_OHLCV"
        with self.assertRaisesRegex(ValueError, "SOURCE_IS_NOT"):
            run(f)

    def test_reject_duplicate_receipt_and_wrong_fee(self) -> None:
        f = fixture()
        f["events"][3]["id"] = "x1"
        with self.assertRaisesRegex(ValueError, "UNIQUE_EVENT_ID"):
            run(f)
        f = fixture()
        f["events"][3]["fee_usd"] = "9"
        with self.assertRaisesRegex(ValueError, "NET_RECONCILIATION"):
            run(f)

    def test_reject_digest_or_binding_or_unanchored_source(self) -> None:
        f = fixture()
        with self.assertRaisesRegex(ValueError, "EXTERNAL_ROOT_REQUIRED"):
            audit_receipt_tape(f, native_checkpoint_sha256=BINDING,
                               externally_pinned_receipt_sha256=None, now=NOW)
        with self.assertRaisesRegex(ValueError, "EXTERNAL_ROOT_REQUIRED"):
            audit_receipt_tape(f, native_checkpoint_sha256=BINDING,
                               externally_pinned_receipt_sha256="0" * 64,
                               now=NOW)
        f["native_checkpoint_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "NATIVE_CHECKPOINT_BINDING"):
            run(f)

    def test_reject_short_development_or_holdout_overlap(self) -> None:
        f = fixture()
        f["development_days"] = f["development_days"][:-1]
        with self.assertRaisesRegex(ValueError, "DEVELOPMENT_180D"):
            run(f)
        f = fixture()
        f["holdout_start"] = f["development_days"][-1]
        with self.assertRaisesRegex(ValueError, "SEALED_HOLDOUT"):
            run(f)
        f = fixture()
        f["holdout_payload"] = {"outcomes": [1]}
        with self.assertRaisesRegex(ValueError, "HOLDOUT_PAYLOAD_FORBIDDEN"):
            run(f)

    def test_reject_hold_beyond_72h(self) -> None:
        f = fixture()
        f["events"][3]["effective_at"] = "2025-01-15T14:00:00Z"
        f["events"][3]["known_at"] = "2025-01-15T14:00:00Z"
        with self.assertRaisesRegex(ValueError, "MAX_HOLD_72H"):
            run(f)

    def test_journal_idempotent_conflict_and_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fwn9.sqlite"
            proof = run(fixture())
            self.assertEqual(journal_preflight(path, proof, NOW), "COMMITTED")
            self.assertEqual(journal_preflight(path, proof, NOW), "UNCHANGED")
            changed = copy.deepcopy(proof)
            changed["net_receipts_usd"] = "0"
            with self.assertRaisesRegex(ValueError, "RESTART_EVIDENCE_CONFLICT"):
                journal_preflight(path, changed, NOW)
            self.assertEqual(journal_preflight(path, proof, NOW), "UNCHANGED")

    def test_journal_corruption_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fwn9.sqlite"
            proof = run(fixture())
            self.assertEqual(journal_preflight(path, proof, NOW), "COMMITTED")
            with sqlite3.connect(path) as db:
                db.execute("UPDATE optimizer_audit SET h='bad' WHERE seq=1")
            with self.assertRaises(ValueError):
                journal_preflight(path, proof, NOW)

    def test_bounded_invalid_fee_and_wrong_receipt_order(self) -> None:
        f = fixture()
        f["events"][2]["fee_usd"] = "NaN"
        with self.assertRaisesRegex(ValueError, "DECIMAL_STRING_REQUIRED"):
            run(f)
        f = fixture()
        f["events"][2]["known_at"] = "2025-01-11T14:00:00Z"
        with self.assertRaisesRegex(ValueError, "KNOWN_AT_SORT_ORDER"):
            run(f)


if __name__ == "__main__":
    unittest.main()
