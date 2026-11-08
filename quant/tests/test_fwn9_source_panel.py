"""M11 P9M-B purely constructed fixture tests, not market evidence."""
from __future__ import annotations

import base64
import copy
import tempfile
import unittest
from datetime import date
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from harpoon_quant.fwn9_observed_gate import receipt_sha256
from harpoon_quant.fwn9_source_panel import (
    SCHEMA, audit_panel, digest, journal_panel, signing_bytes,
)
from quant.tests.test_fwn9_observed_gate import BINDING, NOW, fixture

SECRET = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
KEY = SECRET.public_key().public_bytes(
    serialization.Encoding.Raw, serialization.PublicFormat.Raw,
)
ID = "TEST_ONLY_NOT_INDEPENDENT"


def resign(panel: dict) -> None:
    panel["signature_b64"] = base64.b64encode(
        SECRET.sign(signing_bytes(panel))).decode()


def sample() -> tuple[dict, dict]:
    tape = fixture()
    for e in tape["events"]:
        for name in ("effective_at", "known_at"):
            e[name] = e[name].replace("2025-01-11", "2025-01-10")
    tape["labels"][0]["label_known_at"] = "2025-01-10T13:30:00Z"
    marks = []
    opps = []
    last = {}
    as_of = {}
    for d in tape["development_days"]:
        weekday = date.fromisoformat(d).weekday() < 5
        for sym in ("SYNA", "SYNB"):
            if weekday:
                last[sym] = "100" if sym == "SYNA" else "90"
                as_of[sym] = d + "T21:00:00Z"
            marks.append(dict(day=d, symbol=sym, price=last[sym],
                              kind="OBSERVED_QUOTE" if weekday else "CARRY_FORWARD",
                              as_of=as_of[sym], known_at=d + "T23:00:00Z"))
            if weekday:
                ids = ["order1"] if d == "2025-01-10" and sym == "SYNA" else []
                opps.append(dict(day=d, symbol=sym, signal_order_ids=ids,
                                 status="SIGNALS" if ids else "NO_SIGNAL",
                                 known_at=d + "T23:01:00Z"))
    panel = dict(schema=SCHEMA, batch_id=tape["batch_id"], attestor_id=ID,
                 native_checkpoint_sha256=BINDING, tape_sha256=digest(tape),
                 receipt_sha256=receipt_sha256(tape["events"]),
                 label_sha256=receipt_sha256(tape["labels"]),
                 marks=marks, opportunities=opps)
    resign(panel)
    return tape, panel


def check(tape: dict, panel: dict) -> dict:
    return audit_panel(tape, panel, trusted_public_keys={ID: KEY},
                       native_checkpoint_sha256=BINDING, now=NOW)


class OfflinePanelTests(unittest.TestCase):
    def test_signed_engineering_not_observed(self) -> None:
        t, p = sample()
        result = check(t, p)
        self.assertEqual(result["marks_checked"], 360)
        self.assertEqual(result["end_equity_usd"], "19861.90")
        self.assertEqual(result["cash_benchmark_usd"], "19820")
        self.assertFalse(result["independent_source_attested"])
        self.assertFalse(result["optimizer_eligible"])

    def test_no_trust_root(self) -> None:
        t, p = sample()
        with self.assertRaisesRegex(ValueError, "TRUST_ROOT_MISSING"):
            audit_panel(t, p, trusted_public_keys={},
                        native_checkpoint_sha256=BINDING, now=NOW)

    def test_no_key_from_payload(self) -> None:
        t, p = sample()
        p["public_key"] = "UNTRUSTED"
        with self.assertRaisesRegex(ValueError, "UNTRUSTED_PAYLOAD_KEY"):
            check(t, p)

    def test_mutated_mark_signature(self) -> None:
        t, p = sample()
        p["marks"][0]["price"] = "1000"
        with self.assertRaisesRegex(ValueError, "INVALID_SIGNATURE"):
            check(t, p)

    def test_mutated_label_sha(self) -> None:
        t, p = sample()
        t["labels"][0]["label_known_at"] = "2025-01-10T13:31:00Z"
        with self.assertRaisesRegex(ValueError, "SIGNED_TAPE_BINDING"):
            check(t, p)

    def test_missing_marks(self) -> None:
        t, p = sample()
        p["marks"].pop()
        resign(p)
        with self.assertRaisesRegex(ValueError, "MARK_COVERAGE"):
            check(t, p)

    def test_missing_opportunities(self) -> None:
        t, p = sample()
        p["opportunities"].pop()
        resign(p)
        with self.assertRaisesRegex(ValueError, "UNIVERSE_COVERAGE"):
            check(t, p)

    def test_duplicate_opportunity(self) -> None:
        t, p = sample()
        p["opportunities"][-1] = copy.deepcopy(p["opportunities"][0])
        resign(p)
        with self.assertRaisesRegex(ValueError, "OPPORTUNITY_DUP"):
            check(t, p)

    def test_signed_forged_universe(self) -> None:
        t, p = sample()
        p["opportunities"][0]["signal_order_ids"] = ["fake"]
        resign(p)
        with self.assertRaisesRegex(ValueError, "OPPORTUNITY_SIGNAL_MISMATCH"):
            check(t, p)

    def test_stale_or_future_mark(self) -> None:
        t, p = sample()
        p["marks"][0]["known_at"] = "2027-01-01T00:00:00Z"
        resign(p)
        with self.assertRaisesRegex(ValueError, "CAUSAL_MARK"):
            check(t, p)

    def test_weekend_mark_manipulation(self) -> None:
        t, p = sample()
        idx = next(i for i, m in enumerate(p["marks"]) if m["kind"] == "CARRY_FORWARD")
        p["marks"][idx]["price"] = "200"
        resign(p)
        with self.assertRaisesRegex(ValueError, "WEEKEND_CARRY"):
            check(t, p)

    def test_journal_restart_conflict(self) -> None:
        t, p = sample()
        report = check(t, p)
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "audit.sqlite"
            self.assertEqual(journal_panel(file, report, NOW), "COMMITTED")
            self.assertEqual(journal_panel(file, report, NOW), "UNCHANGED")
            changed = dict(report, end_equity_usd="0")
            with self.assertRaisesRegex(ValueError, "RESTART_CONFLICT"):
                journal_panel(file, changed, NOW)


if __name__ == "__main__":
    unittest.main()
