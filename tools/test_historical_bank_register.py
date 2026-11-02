"""Hermetic registration checks; no training, market replay, or study reservation."""

from __future__ import annotations

import copy
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import historical_bank_register as bank


class HistoricalBankRegisterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="historical-registration-unit-")
        self.root = Path(self.temp.name)
        self.protocol_path = self.root / "protocol.json"
        self.dataset_path = self.root / "research_dataset.json"
        self.manifest_path = self.root / "source_hashes.json"
        self.source = self.root / "source.sqlite3"
        self.output = self.root / "registration"
        self.protocol = bank.read(bank.APP / "research/historical_bank/protocol.json")
        self.protocol["study_id"] = "SYNTHETIC_REGISTRATION_CONTRACT_TEST_ONLY"
        self.write(self.protocol_path, self.protocol)
        raw = self.root / "retained_raw.json"
        self.write(raw, {"test_fixture": True, "prices": [], "not_financial_evidence": True})
        self.dataset = {"schema": "HARPOON-ULTIMATE-DATA-1", "kind": "SYNTHETIC_REGISTRATION_FIXTURE",
                        "provenance": {"files": [{"name": raw.name, "sha256": bank.sha(raw)}]},
                        "series": [{"symbol": name, "bars": []} for name in bank.UNIVERSE]}
        self.write(self.dataset_path, self.dataset)
        shutil.copyfile(bank.APP / "quant/economic_experiment/study/optimizer.sqlite3", self.source)
        self.original_bytes = self.source.read_bytes()
        self.refresh_manifest()

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value, sort_keys=True, allow_nan=False) + "\n")

    def refresh_manifest(self):
        paths = [self.protocol_path, self.dataset_path, *(bank.APP / name for name in bank.REQUIRED_CODE)]
        self.manifest = {os.path.relpath(path, bank.APP): bank.sha(path) for path in paths}
        self.write(self.manifest_path, self.manifest)

    def run_registration(self, output=None):
        return bank.register(self.protocol_path, self.dataset_path, self.manifest_path,
                             self.source, output or self.output)

    def budget(self):
        return bank._snapshot(self.output / bank.DESCENDANT)["budget"]

    def interrupted_nominal(self):
        original = bank.measurement.reserve
        calls = 0
        def stop_before_stress(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("SIMULATED_INTERRUPTION_BEFORE_STRESS")
            return original(*args)
        with patch.object(bank.measurement, "reserve", side_effect=stop_before_stress):
            with self.assertRaisesRegex(RuntimeError, "SIMULATED_INTERRUPTION"):
                self.run_registration()
        self.assertEqual(self.budget(), {"spent": 26, "limit": 128})

    def test_six_measurements_repeat_without_reset_or_double_spend(self):
        first = self.run_registration()
        immutable = {p.name: p.read_bytes() for p in self.output.iterdir()
                     if p.is_file() and not p.name.endswith(("-wal", "-shm", ".lock"))}
        second = self.run_registration()
        self.assertEqual(first, second)
        self.assertEqual(first["budget_path"], [23, 26, 29])
        self.assertEqual(first["family_slots"], 6)
        self.assertEqual(first["fit_accounting"]["unique_model_fit_recipes"], 8)
        self.assertEqual(first["fit_accounting"]["planned_total_fit_invocations_including_exact_verification"], 32)
        self.assertEqual([first["scenarios"][s]["ordinal"] for s in bank.SCENARIOS], [1, 2])
        self.assertEqual(first["descendant_journal"]["audit_seq"], 82)
        self.assertEqual(self.budget(), {"spent": 29, "limit": 128})
        for name, raw in immutable.items():
            self.assertEqual((self.output / name).read_bytes(), raw, name)
        self.assertEqual(self.source.read_bytes(), self.original_bytes)

    def test_binding_is_recipe_not_fitted_weights_or_production_coordinator(self):
        result = self.run_registration()
        for scenario in bank.SCENARIOS:
            item = result["scenarios"][scenario]
            binding = bank.read(self.output / item["binding_path"])
            request = json.loads(binding["request_canonical"])
            self.assertTrue(bank.measurement.verify(item["registration"], binding["request_canonical"])["verified"])
            self.assertEqual(request["common_request"]["data_origin"], "HISTORICAL")
            self.assertEqual(request["common_request"]["policy_roles"]["C0"], "NATIVE_HISTORICAL_ULTIMATE")
            self.assertFalse(request["production_request_compatible"])
            for model in request["models"].values():
                self.assertEqual(model["binding_kind"], "FIXED_FIT_RECIPE")
                self.assertIsNone(model["fitted_model_hash"])
            self.assertEqual(request["source_hashes"], self.manifest)
        for flag in ("financial_acceptance_allowed", "execution_allowed", "live_approved", "independent_preregistration"):
            self.assertIs(result[flag], False)
        self.assertIsNone(result["global_deduplicated_search_total"])

    def test_prepare_is_read_only(self):
        plan = bank.prepare(self.protocol_path, self.dataset_path, self.manifest_path)
        self.assertEqual(set(plan["bindings"]), set(bank.SCENARIOS))
        self.assertFalse(self.output.exists())
        self.assertEqual(self.source.read_bytes(), self.original_bytes)

    def test_changed_source_code_hash_fails_before_output(self):
        self.manifest[next(iter(self.manifest))] = "0" * 64
        self.write(self.manifest_path, self.manifest)
        with self.assertRaisesRegex(ValueError, "SOURCE_HASH_MISMATCH"):
            self.run_registration()
        self.assertFalse(self.output.exists())

    def test_missing_protected_dependency_fails_before_output(self):
        self.manifest.pop(os.path.relpath(bank.APP / bank.REQUIRED_CODE[0], bank.APP))
        self.write(self.manifest_path, self.manifest)
        with self.assertRaisesRegex(ValueError, "MANIFEST_MISSING"):
            self.run_registration()
        self.assertFalse(self.output.exists())

    def test_source_bytes_cannot_be_changed_or_reanchored(self):
        with self.source.open("ab") as handle:
            handle.write(b"tamper")
        with self.assertRaisesRegex(ValueError, "SOURCE_JOURNAL_SHA256_MISMATCH"):
            self.run_registration()
        self.assertFalse(self.output.exists())

    def test_uncheckpointed_source_is_rejected(self):
        Path(str(self.source) + "-wal").write_bytes(b"pending")
        with self.assertRaisesRegex(ValueError, "SOURCE_WAL_NOT_EMPTY"):
            self.run_registration()
        self.assertFalse(self.output.exists())

    def test_changed_protocol_cannot_reuse_budget(self):
        self.run_registration()
        self.protocol["admission"]["minimum_predicted_net_return_bps"] += 1
        self.write(self.protocol_path, self.protocol)
        self.refresh_manifest()
        with self.assertRaisesRegex(ValueError, "FORK_IDENTITY_CONFLICT"):
            self.run_registration()
        self.assertEqual(self.budget()["spent"], 29)

    def test_missing_descendant_never_recopies_source(self):
        self.run_registration()
        (self.output / bank.DESCENDANT).unlink()
        with self.assertRaisesRegex(ValueError, "DESCENDANT_JOURNAL_MISSING_NO_RESET"):
            self.run_registration()
        self.assertFalse((self.output / bank.DESCENDANT).exists())

    def test_interruption_reuses_nominal_reservation(self):
        self.interrupted_nominal()
        nominal = (self.output / "NOMINAL.registration.json").read_bytes()
        final = self.run_registration()
        self.assertEqual((self.output / "NOMINAL.registration.json").read_bytes(), nominal)
        self.assertEqual(final["budget_path"], [23, 26, 29])
        self.assertEqual(self.budget()["spent"], 29)

    def test_tampered_nominal_receipt_blocks_before_stress_debit(self):
        self.interrupted_nominal()
        path = self.output / "NOMINAL.registration.json"
        receipt = bank.read(path)
        receipt["reservation_hash"] = "0" * 64
        self.write(path, receipt)
        with self.assertRaisesRegex(ValueError, "RESERVATION_RECORD_MISMATCH"):
            self.run_registration()
        self.assertEqual(self.budget()["spent"], 26)

    def test_unauthorized_coherent_journal_append_does_not_reset(self):
        self.interrupted_nominal()
        journal = bank.Journal(self.output / bank.DESCENDANT)
        try:
            with journal.transaction():
                journal.put("unregistered-attempt", {"truth": "not a reserved measurement"}, "2026-11-01T00:00:00Z")
        finally:
            journal.close()
        with self.assertRaisesRegex(ValueError, "DESCENDANT_UNREGISTERED_AUDIT_EVENTS"):
            self.run_registration()
        self.assertEqual(self.budget()["spent"], 26)

    def test_deleted_audit_state_cannot_reset_budget(self):
        self.run_registration()
        with sqlite3.connect(self.output / bank.DESCENDANT) as db:
            db.execute("DELETE FROM optimizer_state WHERE k='budget'")
        with self.assertRaisesRegex(ValueError, "MISSING_AUDITED_KEY"):
            self.run_registration()

    def test_hardlink_to_source_is_rejected_before_writing(self):
        self.output.mkdir()
        os.link(self.source, self.output / bank.DESCENDANT)
        with self.assertRaisesRegex(ValueError, "DESCENDANT_MUST_NOT_ALIAS_SOURCE"):
            self.run_registration()
        self.assertEqual(self.source.read_bytes(), self.original_bytes)

    def test_relocation_rebases_only_journal_locator(self):
        result = self.run_registration()
        relocated = self.root / "relocated"
        shutil.copytree(self.output, relocated)
        before = {name: (relocated / name).read_bytes() for name in (bank.FORK_FILE, bank.OVERVIEW, "NOMINAL.registration.json")}
        moved = self.run_registration(relocated)
        self.assertEqual(moved["identity_hash"], result["identity_hash"])
        for scenario in bank.SCENARIOS:
            self.assertEqual(moved["scenarios"][scenario]["registration"]["journal_path"], str(relocated / bank.DESCENDANT))
            self.assertEqual(moved["scenarios"][scenario]["registration"]["reservation_hash"],
                             result["scenarios"][scenario]["registration"]["reservation_hash"])
        for name, raw in before.items():
            self.assertEqual((relocated / name).read_bytes(), raw)

    def test_missing_or_modified_original_data_source_blocks(self):
        (self.root / "retained_raw.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "RETAINED_DATA_SOURCE_HASH_MISMATCH"):
            self.run_registration()
        self.assertFalse(self.output.exists())

    def test_list_manifest_paths_are_relative_to_manifest_directory(self):
        entries = [{"path": os.path.relpath((bank.APP / name).resolve(), self.root), "sha256": value}
                   for name, value in self.manifest.items()]
        self.write(self.manifest_path, entries)
        result = self.run_registration()
        self.assertTrue(result["verified"])
        self.assertEqual(self.budget()["spent"], 29)

    def test_old_fit_count_cannot_hide_exact_verification_invocations(self):
        altered = copy.deepcopy(self.protocol)
        altered["budget"]["model_fits"] = 8
        self.write(self.protocol_path, altered)
        self.refresh_manifest()
        with self.assertRaisesRegex(ValueError, "SIX_MEASUREMENT_BUDGET_CONTRACT"):
            self.run_registration()
        self.assertFalse(self.output.exists())

    def test_authority_budget_or_universe_escalation_is_rejected(self):
        mutations = (("live_approved", True), ("independent_preregistration", True),
                     ("universe", ["AAPL", "MSFT", "SPY", "XLK", "NVDA"]))
        for field, value in mutations:
            with self.subTest(field=field):
                altered = copy.deepcopy(self.protocol)
                altered[field] = value
                self.write(self.protocol_path, altered)
                self.refresh_manifest()
                with self.assertRaises(ValueError):
                    self.run_registration()
                self.assertFalse(self.output.exists())

    def test_duplicate_keys_and_nonfinite_protocol_are_rejected(self):
        for text in ('{"schema":1,"schema":2}', '{"number":1e999}', '{"number":NaN}'):
            with self.subTest(text=text):
                self.protocol_path.write_text(text)
                with self.assertRaises(ValueError):
                    self.run_registration()
                self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
