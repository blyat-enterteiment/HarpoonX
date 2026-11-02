"""Synthetic registration fault fixtures only, never observed economic evidence."""
from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import residual_register as r


class ResidualRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="residual-registration-engineering-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source.sqlite3"
        journal = r.Journal(self.source)
        with journal.transaction():
            journal.put("budget", {"spent": 41, "limit": 128}, "2026-01-01T00:00:00Z")
            journal.put("synthetic_engineering_only", True, "2026-01-01T00:00:00Z")
        journal.close()
        s = r.snapshot(self.source)
        self.output = self.root / "evidence/residual_30_18_0/registration"
        self.protocol = self.root / r.PROTOCOL
        self.protocol.parent.mkdir(parents=True)
        self.p = {"study_id": r.STUDY, "origin": "HISTORICAL", "seen_global_history": True,
                  "independent_preregistration": False, "financial_acceptance_allowed": False,
                  "live_approved": False, "definition_recorded_at": "2026-01-01T00:00:00Z",
                  "dataset": r.DATASET, "data_audit": r.DATA_AUDIT,
                  "budget": {"policies": r.POLICIES, "scenarios": r.SCENARIOS,
                    "new_policy_scenario_measurements": 6, "source_budget_spent": 41,
                    "source_budget_limit": 128, "descendant_expected_spent": 47,
                    "cash_is_derived_reference": True}}
        self.protocol.write_text(json.dumps(self.p))
        self.patch = patch.multiple(r, APP=self.root, SOURCE=self.source, OUTPUT=self.output,
            SOURCE_SHA256=r.sha(self.source), SOURCE_SEQUENCE=s["audit_seq"], SOURCE_HEAD=s["audit_head"])
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.source_bytes = self.source.read_bytes()
        self.manifest = self.root / "source_manifest.json"

    def reserve(self):
        return r.reserve(self.protocol, self.output)

    def admit(self):
        return r.admit(self.output, self.protocol, self.manifest)

    def verify(self):
        return r.verify(self.output, self.protocol, self.manifest)

    def build_data(self):
        self.dataset = self.root / r.DATASET
        self.dataset.parent.mkdir(parents=True, exist_ok=True)
        raw_dir = self.dataset.parent / "raw"
        raw_dir.mkdir(exist_ok=True)
        reserved_at = datetime.fromisoformat(r.read(self.output / "reservation.json")["registered_at"])
        self.raw_paths = []
        captures = []
        for i in range(78):
            raw = raw_dir / ("price_%03d.json" % i)
            capture = (reserved_at + timedelta(seconds=i + 1)).isoformat(timespec="microseconds")
            raw.write_text(json.dumps({"synthetic_engineering_fixture": True,
                "request": {"id": "SYNTHETIC_PRICE_%03d" % i, "tool": r.BAR_TOOL},
                "captured_at": capture, "response": {"not_observed_price_data": True}}))
            self.raw_paths.append(raw); captures.append(capture)
        # Calendar/action metadata may legitimately precede this recipe reservation.
        metadata = raw_dir / "calendar.json"
        metadata.write_text(json.dumps({"request": {"tool": "SYNTHETIC_CALENDAR_METADATA"},
            "captured_at": "2020-01-01T00:00:00Z", "synthetic_engineering_fixture": True}))
        self.raw_paths.append(metadata)
        self.raw = self.raw_paths[0]
        self.dataset.write_text(json.dumps({"synthetic_engineering_fixture": True,
            "provenance": {"files": [{"name": str(path.relative_to(self.dataset.parent)), "sha256": r.sha(path)}
                                      for path in self.raw_paths]}}))
        (self.root / r.DATA_AUDIT).write_text(json.dumps({"verified": True, "dataset_sha256": r.sha(self.dataset),
            "capture_clock": {"first_bar_captured_at": min(captures), "last_bar_captured_at": max(captures)},
            "synthetic_engineering_only": True}))
        extra = ["quant/harpoon_quant/extra_fixture.py", "runtime30/extra_fixture.js", "xxx/extra_fixture.ts"]
        for name in [*r.REQUIRED_CODE, *extra]:
            p = self.root / name; p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("# Synthetic hash-only fixture, not financial evidence.\n")
        self.names = [r.PROTOCOL, r.DATASET, r.DATA_AUDIT, *[str(path.relative_to(self.root)) for path in self.raw_paths], *r.REQUIRED_CODE, *extra]
        self.refresh_manifest()

    def refresh_manifest(self):
        self.hashes = {p: r.sha(self.root / p) for p in self.names}
        self.manifest.write_text(json.dumps(self.hashes))

    def rebind_synthetic_raw_and_audit(self):
        data = r.read(self.dataset)
        for item in data["provenance"]["files"]:
            item["sha256"] = r.sha(self.dataset.parent / item["name"])
        self.dataset.write_text(json.dumps(data))
        audit = r.read(self.root / r.DATA_AUDIT)
        audit["dataset_sha256"] = r.sha(self.dataset)
        self.root.joinpath(r.DATA_AUDIT).write_text(json.dumps(audit))
        self.refresh_manifest()

    def test_capture_before_real_reservation_blocked_even_after_protocol_definition(self):
        self.reserve(); self.build_data()
        raw = r.read(self.raw)
        actual = datetime.fromisoformat(r.read(self.output / "reservation.json")["registered_at"])
        raw["captured_at"] = (actual - timedelta(microseconds=1)).isoformat(timespec="microseconds")
        self.raw.write_text(json.dumps(raw)); self.rebind_synthetic_raw_and_audit()
        with self.assertRaisesRegex(ValueError, "PRICE_CAPTURE_PRECEDES_REAL_RESERVATION"):
            self.admit()
        self.assertEqual(r.snapshot(self.output)["budget"]["spent"], 47)
        self.assertNotIn(r.ADMISSION_KEY, r.snapshot(self.output)["states"])

    def test_every_receipt_checked_not_only_first_audit_clock(self):
        self.reserve(); self.build_data()
        raw = r.read(self.raw_paths[37])
        raw["captured_at"] = "2020-01-01T00:00:00Z"
        self.raw_paths[37].write_text(json.dumps(raw)); self.rebind_synthetic_raw_and_audit()
        with self.assertRaisesRegex(ValueError, "PRICE_CAPTURE_PRECEDES_REAL_RESERVATION"):
            self.admit()

    def test_naive_bar_timestamp_is_rejected(self):
        self.reserve(); self.build_data()
        raw = r.read(self.raw); raw["captured_at"] = "2099-01-01T00:00:00"
        self.raw.write_text(json.dumps(raw)); self.rebind_synthetic_raw_and_audit()
        with self.assertRaisesRegex(ValueError, "AWARE_BAR_CAPTURE_TIMESTAMP_REQUIRED"):
            self.admit()

    def test_at_least_78_distinct_price_receipts_required(self):
        self.reserve(); self.build_data()
        raw = r.read(self.raw); raw["request"]["tool"] = "SYNTHETIC_NONPRICE_METADATA"
        self.raw.write_text(json.dumps(raw)); self.rebind_synthetic_raw_and_audit()
        with self.assertRaisesRegex(ValueError, "MINIMUM_78_BAR_RECEIPTS_REQUIRED"):
            self.admit()

    def test_capture_audit_clock_is_reconciled_to_raw_receipts(self):
        self.reserve(); self.build_data()
        audit = r.read(self.root / r.DATA_AUDIT)
        audit["capture_clock"]["first_bar_captured_at"] = "2099-01-01T00:00:00Z"
        self.root.joinpath(r.DATA_AUDIT).write_text(json.dumps(audit)); self.refresh_manifest()
        with self.assertRaisesRegex(ValueError, "AUDIT_BAR_CAPTURE_CLOCK_MISMATCH"):
            self.admit()

    def test_capture_equal_to_reservation_is_allowed_without_rounding(self):
        self.reserve(); self.build_data()
        actual = r.read(self.output / "reservation.json")["registered_at"]
        raw = r.read(self.raw); raw["captured_at"] = actual
        self.raw.write_text(json.dumps(raw)); self.rebind_synthetic_raw_and_audit()
        audit = r.read(self.root / r.DATA_AUDIT); audit["capture_clock"]["first_bar_captured_at"] = actual
        self.root.joinpath(r.DATA_AUDIT).write_text(json.dumps(audit)); self.refresh_manifest()
        self.assertTrue(self.admit()["verified"])
        self.assertTrue(self.verify()["verified"])

    def test_reserve_before_any_prices_or_code_exist(self):
        result = self.reserve()
        self.assertEqual(result["budget_path"], [41, 47])
        self.assertFalse(result["offline_replay_admitted"])
        self.assertFalse((self.root / r.DATASET).exists())
        self.assertEqual(r.snapshot(self.output)["audit_seq"], r.SOURCE_SEQUENCE + 2)
        self.assertEqual(self.source.read_bytes(), self.source_bytes)

    def test_one_admission_appends_one_event_without_extra_debit(self):
        self.reserve(); self.build_data()
        result = self.admit()
        self.assertTrue(result["offline_replay_admitted"])
        self.assertEqual(result["budget"], {"spent": 47, "limit": 128})
        self.assertEqual(result["audit_sequence"], r.SOURCE_SEQUENCE + 3)
        self.assertTrue(result["seen_global_history"])
        self.assertFalse(result["fresh_global_holdout"])
        for key in r.AUTHORITY:
            self.assertIs(result[key], False)
        self.assertEqual(self.source.read_bytes(), self.source_bytes)

    def test_reserve_and_admit_are_idempotent(self):
        first = self.reserve(); self.assertEqual(first, self.reserve())
        self.build_data(); admitted = self.admit()
        before = (self.output / r.DESCENDANT).read_bytes()
        self.assertEqual(admitted, self.admit())
        self.assertEqual(first, self.reserve())
        self.assertEqual(before, (self.output / r.DESCENDANT).read_bytes())

    def test_verify_requires_data_admission(self):
        self.reserve(); self.build_data()
        with self.assertRaises(ValueError):
            self.verify()
        self.assertEqual(r.snapshot(self.output)["budget"]["spent"], 47)

    def test_verify_is_read_only(self):
        self.reserve(); self.build_data(); result = self.admit()
        before = {p.name: p.read_bytes() for p in self.output.iterdir() if p.is_file()}
        self.assertEqual(result, self.verify())
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.output.iterdir() if p.is_file()})

    def test_all_mandatory_bindings_must_be_present(self):
        self.reserve(); self.build_data()
        for name in self.names:
            with self.subTest(missing=name):
                self.manifest.write_text(json.dumps({k: v for k, v in self.hashes.items() if k != name}))
                with self.assertRaisesRegex(ValueError, "MANIFEST_MISSING_REQUIRED_BINDING|RAW_SOURCE_DUPLICATE_OR_UNBOUND"):
                    self.admit()
                self.assertNotIn(r.ADMISSION_KEY, r.snapshot(self.output)["states"])
        self.assertEqual(r.snapshot(self.output)["budget"]["spent"], 47)

    def test_failed_audit_keeps_spent_budget_and_blocks_admission(self):
        self.reserve(); self.build_data()
        (self.root / r.DATA_AUDIT).write_text(json.dumps({"verified": False, "dataset_sha256": r.sha(self.dataset)}))
        self.refresh_manifest()
        with self.assertRaisesRegex(ValueError, "VERIFIED_DATA_AUDIT_BINDING_REQUIRED"):
            self.admit()
        self.assertEqual(r.snapshot(self.output)["budget"]["spent"], 47)

    def test_data_audit_must_bind_exact_dataset(self):
        self.reserve(); self.build_data()
        (self.root / r.DATA_AUDIT).write_text(json.dumps({"verified": True, "dataset_sha256": "0" * 64}))
        self.refresh_manifest()
        with self.assertRaisesRegex(ValueError, "VERIFIED_DATA_AUDIT_BINDING_REQUIRED"):
            self.admit()

    def test_raw_tamper_cannot_be_hidden_by_new_manifest(self):
        self.reserve(); self.build_data(); self.raw.write_text("different")
        self.refresh_manifest()
        with self.assertRaisesRegex(ValueError, "RAW_SOURCE_HASH_MISMATCH"):
            self.admit()

    def test_admitted_code_tamper_is_rejected(self):
        self.reserve(); self.build_data(); self.admit()
        (self.root / r.REQUIRED_CODE[0]).write_text("tampered")
        with self.assertRaisesRegex(ValueError, "SOURCE_HASH_MISMATCH"):
            self.verify()
        self.refresh_manifest()
        with self.assertRaisesRegex(ValueError, "ARTIFACT_CONFLICT"):
            self.admit()
        self.assertEqual(r.snapshot(self.output)["audit_seq"], r.SOURCE_SEQUENCE + 3)

    def test_recipe_cannot_change_after_reservation_or_failure(self):
        self.reserve(); self.p["new_variant"] = True
        self.protocol.write_text(json.dumps(self.p))
        with self.assertRaisesRegex(ValueError, "FORK_IDENTITY_CONFLICT"):
            self.reserve()
        self.assertEqual(r.snapshot(self.output)["budget"]["spent"], 47)

    def test_source_ancestor_cannot_be_reopened(self):
        j = r.Journal(self.source)
        with j.transaction():
            j.put("budget", {"spent": 29, "limit": 128}, "2026-01-01T00:00:01Z")
        j.close()
        with patch.object(r, "SOURCE_SHA256", r.sha(self.source)):
            with self.assertRaisesRegex(ValueError, "SOURCE_41_OF_128_ANCHOR_MISMATCH"):
                self.reserve()

    def test_no_second_descendant(self):
        with self.assertRaisesRegex(ValueError, "SINGLE_CANONICAL_DESCENDANT_REQUIRED"):
            r.reserve(self.protocol, self.root / "other")

    def test_missing_journal_does_not_reset(self):
        self.reserve(); (self.output / r.DESCENDANT).unlink()
        with self.assertRaisesRegex(ValueError, "DESCENDANT_MISSING_NO_RESET"):
            self.reserve()

    def test_reservation_receipt_rebuilt_after_commit(self):
        first = self.reserve(); (self.output / "reservation.json").unlink()
        self.assertEqual(first, self.reserve())
        self.assertEqual(r.snapshot(self.output)["budget"]["spent"], 47)

    def test_admission_receipt_rebuilt_after_commit(self):
        self.reserve(); self.build_data(); first = self.admit()
        (self.output / "admission.json").unlink()
        self.assertEqual(first, self.admit())
        self.assertEqual(r.snapshot(self.output)["audit_seq"], r.SOURCE_SEQUENCE + 3)

    def test_reserve_rollback_is_atomic(self):
        original = r.Journal.put
        def fail(journal, key, value, now):
            if key == r.RESERVE_KEY:
                raise RuntimeError("SYNTHETIC_FAULT")
            return original(journal, key, value, now)
        with patch.object(r.Journal, "put", fail):
            with self.assertRaisesRegex(RuntimeError, "SYNTHETIC_FAULT"):
                self.reserve()
        self.assertEqual(r.snapshot(self.output)["budget"], {"spent": 41, "limit": 128})
        self.assertEqual(self.reserve()["budget_path"], [41, 47])

    def test_admission_failure_does_not_release_budget(self):
        self.reserve(); self.build_data(); original = r.Journal.put
        def fail(journal, key, value, now):
            if key == r.ADMISSION_KEY:
                raise RuntimeError("SYNTHETIC_ADMISSION_FAULT")
            return original(journal, key, value, now)
        with patch.object(r.Journal, "put", fail):
            with self.assertRaisesRegex(RuntimeError, "SYNTHETIC_ADMISSION_FAULT"):
                self.admit()
        self.assertEqual(r.snapshot(self.output)["budget"], {"spent": 47, "limit": 128})
        self.assertNotIn(r.ADMISSION_KEY, r.snapshot(self.output)["states"])
        self.assertTrue(self.admit()["offline_replay_admitted"])

    def test_no_authority_or_fresh_holdout_claims(self):
        for key, value in [(k, True) for k in r.AUTHORITY] + [("seen_global_history", False), ("fresh_global_holdout", True)]:
            with self.subTest(key=key):
                self.protocol.write_text(json.dumps({**self.p, key: value}))
                with self.assertRaises(ValueError):
                    self.reserve()
        self.assertFalse(self.output.exists())

    def test_extra_audit_event_rejected(self):
        self.reserve(); self.build_data(); self.admit()
        journal = r.Journal(self.output / r.DESCENDANT)
        with journal.transaction():
            journal.put("unregistered_trial", 1, "2026-01-01T00:00:02Z")
        journal.close()
        with self.assertRaisesRegex(ValueError, "UNREGISTERED_AUDIT_EVENTS"):
            self.verify()

    def test_corrupt_audit_is_rejected(self):
        self.reserve()
        c = sqlite3.connect(self.output / r.DESCENDANT)
        c.execute("UPDATE optimizer_audit SET h='corrupt' WHERE seq=(SELECT MAX(seq) FROM optimizer_audit)")
        c.commit(); c.close()
        with self.assertRaisesRegex(ValueError, "OPTIMIZER_AUDIT_INTEGRITY"):
            self.reserve()

    def test_symlink_to_source_is_forbidden(self):
        self.output.mkdir(parents=True)
        (self.output / r.DESCENDANT).symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, "DESCENDANT_SYMLINK"):
            self.reserve()
        self.assertEqual(self.source.read_bytes(), self.source_bytes)


if __name__ == "__main__":
    unittest.main()
