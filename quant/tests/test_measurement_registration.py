from __future__ import annotations

import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from harpoon_quant.measurement_registration import (
    ReadOnlyJournal,
    _head,
    reserve,
    verify,
)
from harpoon_quant.recursive import Journal


class MeasurementRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "existing.sqlite3"
        j = Journal(self.path)
        with j.transaction():
            j.put("budget", {"spent": 23, "limit": 128}, "2026-10-01T00:00:00+00:00")
        self.anchor = _head(j)
        j.close()
        self.request = {"schema": "HARPOON_FUNDED_COMPARISON_REQUEST_1",
                        "purpose": "PREREGISTERED_FIXED_MODEL_MEASUREMENT",
                        "common_request": {"data_origin": "HISTORICAL", "id": "fixed"},
                        "models": {"RIDGE": {}, "SVR": {}}, "source_hashes": {"local": "a" * 64}}

    def tearDown(self):
        self.temp.cleanup()

    def canonical(self, request=None):
        return json.dumps(request or self.request, sort_keys=True, separators=(",", ":"))

    def test_reserves_three_slots_and_verifies_read_only(self):
        receipt = reserve(self.path, self.canonical(), self.anchor)
        result = verify(receipt, self.canonical())
        self.assertEqual((result["budget_before"], result["budget_after"]), (23, 26))
        self.assertTrue(result["verified"])
        self.assertFalse(result["external_authentication"])
        before = self.path.read_bytes()
        verify(receipt, self.canonical())
        self.assertEqual(before, self.path.read_bytes())

    def test_idempotent_same_request_never_spends_twice(self):
        first = reserve(self.path, self.canonical(), self.anchor)
        second = reserve(self.path, self.canonical(), self.anchor)
        self.assertEqual(first, second)
        self.assertEqual(verify(second, self.canonical())["budget_after"], 26)

    def test_missing_database_is_not_created(self):
        missing = self.path.parent / "missing.sqlite3"
        with self.assertRaisesRegex(ValueError, "EXISTING_JOURNAL_REQUIRED"):
            reserve(missing, self.canonical(), self.anchor)
        self.assertFalse(missing.exists())

    def test_stale_anchor_rolls_back_without_budget_mutation(self):
        with self.assertRaisesRegex(ValueError, "HEAD_CONFLICT"):
            reserve(self.path, self.canonical(), "b" * 64)
        j = ReadOnlyJournal(self.path)
        self.assertEqual(j.get("budget")["spent"], 23)
        j.close()

    def test_two_fixed_comparisons_exhaust_six_slot_family(self):
        reserve(self.path, self.canonical(), self.anchor)
        altered = copy.deepcopy(self.request)
        altered["common_request"]["id"] = "second"
        j = ReadOnlyJournal(self.path)
        head = _head(j)
        j.close()
        reserve(self.path, self.canonical(altered), head)
        altered["common_request"]["id"] = "third"
        j = ReadOnlyJournal(self.path)
        head = _head(j)
        j.close()
        with self.assertRaisesRegex(ValueError, "FAMILY_BUDGET_EXHAUSTED"):
            reserve(self.path, self.canonical(altered), head)

    def test_modified_models_cannot_reuse_reservation(self):
        receipt = reserve(self.path, self.canonical(), self.anchor)
        self.request["models"]["RIDGE"]["coef"] = [1, 2]
        with self.assertRaisesRegex(ValueError, "REQUEST_MISMATCH"):
            verify(receipt, self.canonical())

    def test_tampered_receipt_is_rejected(self):
        receipt = reserve(self.path, self.canonical(), self.anchor)
        receipt["reservation_hash"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "RECORD_MISMATCH"):
            verify(receipt, self.canonical())

    def test_deleted_budget_fails_integrity(self):
        receipt = reserve(self.path, self.canonical(), self.anchor)
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM optimizer_state WHERE k='budget'")
        with self.assertRaisesRegex(ValueError, "MISSING_AUDITED_KEY"):
            verify(receipt, self.canonical())

    def test_nonfinite_duplicate_keys_and_wrong_origin_rejected(self):
        for raw in [self.canonical()[:-1] + ',"x":NaN}', '{"schema":1,"schema":2}',
                    self.canonical().replace('"HISTORICAL"', '"SYNTHETIC"')]:
            with self.assertRaises(ValueError):
                reserve(self.path, raw, self.anchor)


if __name__ == "__main__":
    unittest.main()
