"""Synthetic engineering fixtures only; no price, profitability or trading evidence."""
from __future__ import annotations

import fcntl
import hashlib
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import quant8_register as reg


class RegistrationTests(unittest.TestCase):
    EXTRA_CODE = ("quant/harpoon_quant/extra_fixture.py", "runtime30/extra_fixture.js", "xxx/extra_fixture.ts")
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="harpoon-quant8-engineering-only-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "prior/optimizer.descendant.sqlite3"
        self.source.parent.mkdir()
        journal = reg.Journal(self.source)
        with journal.transaction():
            journal.put("budget", {"spent": 29, "limit": 128}, "2026-01-01T00:00:00Z")
            journal.put("synthetic_engineering_fixture", {"not_financial_evidence": True}, "2026-01-01T00:00:00Z")
        journal.close()
        anchor = reg.snapshot(self.source)
        self.output = self.root / "evidence/core_quant8_30_17_0/registration"
        self.protocol = self.root / "research/quant8/protocol.json"
        self.protocol.parent.mkdir(parents=True)
        self.data = {"study_id": reg.STUDY, "origin": "HISTORICAL",
                     "independent_preregistration": False, "financial_acceptance_allowed": False,
                     "live_approved": False, "synthetic_engineering_fixture": True,
                     "base_protocol": reg.BASE_PROTOCOL, "dataset": reg.DATASET,
                     "definition_recorded_at": "2026-01-01T00:00:00+00:00",
                     "budget": {"policies": reg.POLICIES, "scenarios": reg.SCENARIOS,
                                "new_policy_scenario_measurements": 12,
                                "source_budget_spent": 29, "source_budget_limit": 128,
                                "descendant_expected_spent": 41, "cash_is_derived_reference": True}}
        self.protocol.write_text(json.dumps(self.data))
        for name in (*reg.REQUIRED_CODE, *self.EXTRA_CODE, reg.BASE_PROTOCOL, reg.DATASET):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# Synthetic code binding fixture, not executable evidence.\n")
        self.manifest = self.root / "source_hashes.json"
        self.refresh_manifest()
        self.patch = patch.multiple(reg, APP=self.root, SOURCE=self.source,
                                    SOURCE_SHA256=reg.sha(self.source),
                                    SOURCE_HEAD=anchor["audit_head"], SOURCE_SEQUENCE=anchor["audit_seq"],
                                    OUTPUT=self.output)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.source_bytes = self.source.read_bytes()

    def refresh_manifest(self):
        names = ["research/quant8/protocol.json", *reg.REQUIRED_CODE, *self.EXTRA_CODE, reg.BASE_PROTOCOL, reg.DATASET]
        self.hashes = {name: reg.sha(self.root / name) for name in names}
        self.manifest.write_text(json.dumps(self.hashes))

    def run_register(self):
        return reg.register(self.protocol, self.manifest, self.output)

    def test_atomic_twelve_slot_reservation_inherits_source(self):
        result = self.run_register()
        self.assertEqual(result["budget_path"], [29, 41])
        self.assertEqual(result["family_slots"], 12)
        self.assertEqual(reg.snapshot(self.output)["budget"], {"spent": 41, "limit": 128})
        self.assertEqual(reg.snapshot(self.output)["audit_seq"], reg.SOURCE_SEQUENCE + 2)
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        for flag in ("financial_acceptance_allowed", "independent_preregistration", "execution_allowed", "live_approved"):
            self.assertIs(result[flag], False)

    def test_idempotence_no_new_debit_or_bytes(self):
        first = self.run_register()
        journal = self.output / reg.DESCENDANT
        before = journal.read_bytes()
        self.assertEqual(self.run_register(), first)
        self.assertEqual(journal.read_bytes(), before)

    def test_verify_is_read_only(self):
        first = self.run_register()
        files = {p.name: p.read_bytes() for p in self.output.iterdir() if p.is_file()}
        self.assertEqual(reg.verify(self.output, self.protocol, self.manifest), first)
        after = {p.name: p.read_bytes() for p in self.output.iterdir() if p.is_file()}
        self.assertEqual(after, files)

    def test_manifest_tamper_refuses_before_output_creation(self):
        (self.root / reg.REQUIRED_CODE[0]).write_text("tampered")
        with self.assertRaisesRegex(ValueError, "SOURCE_HASH_MISMATCH"):
            self.run_register()
        self.assertFalse(self.output.exists())

    def test_manifest_must_bind_protocol_and_registrar(self):
        for name in self.hashes:
            with self.subTest(missing=name):
                self.manifest.write_text(json.dumps({key: value for key, value in self.hashes.items() if key != name}))
                with self.assertRaisesRegex(ValueError, "MANIFEST_MISSING_REQUIRED_BINDING"):
                    self.run_register()
                self.assertFalse(self.output.exists())

    def test_manifest_duplicate_resolved_source_rejected(self):
        self.hashes["tools/../" + reg.REQUIRED_CODE[0]] = self.hashes[reg.REQUIRED_CODE[0]]
        self.manifest.write_text(json.dumps(self.hashes))
        with self.assertRaisesRegex(ValueError, "MANIFEST_DUPLICATE_SOURCE"):
            self.run_register()

    def test_new_identity_cannot_reuse_family(self):
        self.run_register()
        before = reg.snapshot(self.output)["budget"]
        self.data["extra"] = "different recipe"
        self.protocol.write_text(json.dumps(self.data))
        self.refresh_manifest()
        with self.assertRaisesRegex(ValueError, "FORK_IDENTITY_CONFLICT"):
            self.run_register()
        self.assertEqual(reg.snapshot(self.output)["budget"], before)

    def test_missing_descendant_never_resets_budget(self):
        self.run_register()
        (self.output / reg.DESCENDANT).unlink()
        with self.assertRaisesRegex(ValueError, "DESCENDANT_MISSING_NO_RESET"):
            self.run_register()
        self.assertFalse((self.output / reg.DESCENDANT).exists())

    def test_missing_fork_cannot_reset_spent_descendant(self):
        self.run_register()
        (self.output / reg.FORK).unlink()
        with self.assertRaisesRegex(ValueError, "FORK_MISSING_NO_RESET"):
            self.run_register()
        self.assertEqual(reg.snapshot(self.output)["budget"]["spent"], 41)

    def test_crash_after_atomic_debit_can_rebuild_final_receipt(self):
        first = self.run_register()
        (self.output / reg.OVERVIEW).unlink()
        self.assertEqual(self.run_register(), first)
        self.assertEqual(reg.snapshot(self.output)["budget"]["spent"], 41)

    def test_interrupted_unspent_copy_resumes_only_exact_source(self):
        self.output.mkdir(parents=True)
        shutil.copyfile(self.source, self.output / reg.DESCENDANT)
        self.assertEqual(self.run_register()["budget_path"], [29, 41])

    def test_corrupt_receipt_does_not_debit_again(self):
        self.run_register()
        (self.output / reg.OVERVIEW).write_text("{}")
        with self.assertRaisesRegex(ValueError, "REGISTRATION_RECEIPT_CONFLICT"):
            self.run_register()
        self.assertEqual(reg.snapshot(self.output)["budget"]["spent"], 41)

    def test_no_second_descendant_directory(self):
        with self.assertRaisesRegex(ValueError, "SINGLE_CANONICAL_DESCENDANT"):
            reg.register(self.protocol, self.manifest, self.root / "other")
        self.assertFalse((self.root / "other").exists())

    def test_descendant_symlink_and_alias_source_refused(self):
        self.output.mkdir(parents=True)
        (self.output / reg.DESCENDANT).symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, "DESCENDANT_SYMLINK"):
            self.run_register()
        self.assertEqual(self.source.read_bytes(), self.source_bytes)

    def test_source_bytes_tampered_refused(self):
        with self.source.open("ab") as handle:
            handle.write(b"corruption")
        with self.assertRaisesRegex(ValueError, "SOURCE_JOURNAL_SHA256_MISMATCH"):
            self.run_register()
        self.assertFalse(self.output.exists())

    def test_ancestor_23_budget_refused_even_with_new_hash(self):
        journal = reg.Journal(self.source)
        with journal.transaction():
            journal.put("budget", {"spent": 23, "limit": 128}, "2026-01-01T00:00:01Z")
        journal.close()
        with patch.object(reg, "SOURCE_SHA256", reg.sha(self.source)):
            with self.assertRaisesRegex(ValueError, "SOURCE_29_OF_128_ANCHOR_MISMATCH"):
                self.run_register()

    def test_audited_extra_mutation_refused(self):
        self.run_register()
        journal = reg.Journal(self.output / reg.DESCENDANT)
        with journal.transaction():
            journal.put("unregistered_attempt", {}, "2026-01-01T00:00:02Z")
        journal.close()
        with self.assertRaisesRegex(ValueError, "DESCENDANT_EXTRA_AUDIT_EVENTS"):
            reg.verify(self.output, self.protocol, self.manifest)

    def test_audit_corruption_refused(self):
        self.run_register()
        connection = sqlite3.connect(self.output / reg.DESCENDANT)
        connection.execute("UPDATE optimizer_audit SET h='invalid' WHERE seq=(SELECT MAX(seq) FROM optimizer_audit)")
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(ValueError, "OPTIMIZER_AUDIT_INTEGRITY"):
            reg.verify(self.output, self.protocol, self.manifest)

    def test_authority_cannot_be_granted_by_protocol(self):
        for flag in ("financial_acceptance_allowed", "live_approved", "independent_preregistration"):
            with self.subTest(flag=flag):
                data = {**self.data, flag: True}
                self.protocol.write_text(json.dumps(data))
                self.refresh_manifest()
                with self.assertRaisesRegex(ValueError, "AUTHORITY_NOT_PERMITTED"):
                    self.run_register()
        self.assertFalse(self.output.exists())

    def test_fixed_policy_scenario_budget(self):
        for key, value in (("new_policy_scenario_measurements", 13), ("source_budget_spent", 23),
                           ("source_budget_limit", 129), ("descendant_expected_spent", 35),
                           ("cash_is_derived_reference", False), ("policies", reg.POLICIES[:-1])):
            with self.subTest(key=key):
                data = {**self.data, "budget": {**self.data["budget"], key: value}}
                self.protocol.write_text(json.dumps(data))
                self.refresh_manifest()
                with self.assertRaisesRegex(ValueError, "FINITE_TWELVE_SLOT"):
                    self.run_register()

    def test_duplicate_json_key_rejected(self):
        self.protocol.write_text('{"study_id":"a","study_id":"b"}')
        with self.assertRaisesRegex(ValueError, "DUPLICATE_JSON_KEY"):
            self.run_register()

    def test_lock_contention_is_not_retried_or_double_spent(self):
        self.output.mkdir(parents=True)
        with (self.output / ".quant8_register.lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError, "REGISTRATION_ALREADY_RUNNING"):
                self.run_register()
        self.assertFalse((self.output / reg.DESCENDANT).exists())

    def test_atomic_debit_rolls_back_if_reservation_event_fails(self):
        original = reg.Journal.put

        def fail_receipt(journal, key, value, now):
            if key == reg.KEY:
                raise RuntimeError("SYNTHETIC_ENGINEERING_FAULT")
            return original(journal, key, value, now)

        with patch.object(reg.Journal, "put", fail_receipt):
            with self.assertRaisesRegex(RuntimeError, "SYNTHETIC_ENGINEERING_FAULT"):
                self.run_register()
        self.assertEqual(reg.snapshot(self.output)["budget"], {"spent": 29, "limit": 128})
        self.assertNotIn(reg.KEY, reg.snapshot(self.output)["states"])
        self.assertEqual(self.run_register()["budget_path"], [29, 41])

    def test_source_snapshot_does_not_create_wal_or_shm(self):
        before = sorted(p.name for p in self.source.parent.iterdir())
        reg._source()
        after = sorted(p.name for p in self.source.parent.iterdir())
        self.assertEqual(before, after)

    def test_base_protocol_and_dataset_cannot_be_redirected(self):
        for key in ("base_protocol", "dataset"):
            with self.subTest(key=key):
                self.protocol.write_text(json.dumps({**self.data, key: "other.json"}))
                self.refresh_manifest()
                with self.assertRaisesRegex(ValueError, "EXACT_BASE_PROTOCOL_AND_DATASET_REQUIRED"):
                    self.run_register()

    def test_local_clock_is_not_presented_as_authoritative(self):
        result = self.run_register()
        self.assertEqual(result["registered_at_clock"], "EXECUTOR_SYSTEM_UTC_NOT_INDEPENDENT_ATTESTATION")
        self.assertEqual(result["protocol_definition_recorded_at"], self.data["definition_recorded_at"])
        self.assertEqual(result["ordering_authority"], "LOCAL_AUDIT_SEQUENCE_NOT_EXECUTOR_WALL_CLOCK")

    def test_list_manifest_route(self):
        rows = [{"path": key, "sha256": value} for key, value in self.hashes.items()]
        self.manifest.write_text(json.dumps(rows))
        self.assertTrue(self.run_register()["verified"])


if __name__ == "__main__":
    unittest.main()
