"""Regression probes for local journal corruption, not evidence of trading alpha."""

from __future__ import annotations

import json
import runpy
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from harpoon_quant.core import digest
from harpoon_quant.recursive import Journal, active_policy, tick

ROOT = Path(__file__).resolve().parents[1]
_fixtures = runpy.run_path(str(Path(__file__).with_name("test_recursive.py")))
fixture = _fixtures["fixture"]
finish = _fixtures["finish"]


def copy_sqlite(source: Path, destination: Path) -> None:
    """Copy database and WAL without opening or modifying the source journal."""
    for suffix in ("", "-wal", "-shm"):
        src = Path(str(source) + suffix)
        if src.is_file():
            shutil.copy2(src, Path(str(destination) + suffix))


def legacy_journal(path: Path, *, receipt: bool = True, active: bool = False) -> None:
    """Construct a pre-patch schema with unlinked holdouts and an intact audit."""
    db = sqlite3.connect(path)
    db.executescript(
        "CREATE TABLE optimizer_state(k TEXT PRIMARY KEY,v TEXT NOT NULL,h TEXT NOT NULL);"
        "CREATE TABLE optimizer_audit(seq INTEGER PRIMARY KEY,payload TEXT NOT NULL,previous TEXT NOT NULL,h TEXT NOT NULL);"
        "CREATE TABLE optimizer_holdouts(lo TEXT,hi TEXT,domain TEXT,campaign TEXT,PRIMARY KEY(lo,hi,domain));"
    )
    state = {"id": "LEGACY", "stage": "REJECTED" if receipt else "HOLDOUT_RUNNING"}
    if receipt:
        state["result"] = {
            "baseline": {
                "first_period_end": "2026-07-01T23:59:59+00:00",
                "last_period_end": "2026-08-29T23:59:59+00:00",
            }
        }
    values = [("budget", {"limit": 32, "spent": 3}), ("campaign:LEGACY", state)]
    if active:
        values.append(
            (
                "active",
                {
                    "campaign_id": "LEGACY",
                    "status": "PAPER_ACCEPTED",
                    "origin": "OBSERVED",
                    "binding": {},
                    "valid_until": "2027-01-01T00:00:00+00:00",
                    "policy": {"risk_scale": 1, "quality_bps": 0},
                    "pause_entries": False,
                },
            )
        )
    previous = "GENESIS"
    for key, value in values:
        h = digest(value)
        event = {"key": key, "value_hash": h, "at": "2026-08-30T00:00:00+00:00"}
        current = digest({"event": event, "previous": previous})
        db.execute(
            "INSERT INTO optimizer_audit(payload,previous,h) VALUES(?,?,?)",
            (json.dumps(event, sort_keys=True), previous, current),
        )
        db.execute(
            "INSERT INTO optimizer_state VALUES(?,?,?)", (key, json.dumps(value), h)
        )
        previous = current
    db.execute(
        "INSERT INTO optimizer_holdouts VALUES(?,?,?,?)",
        ("2026-07-01", "2026-08-29", "ORIGINAL_DOMAIN", "LEGACY"),
    )
    db.commit()
    db.close()


def logical_snapshot(path: Path) -> dict[str, list[tuple]]:
    with sqlite3.connect(path) as db:
        return {
            table: db.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
            for table in ("optimizer_audit", "optimizer_state", "optimizer_holdouts")
        }


class JournalIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.template_dir = tempfile.TemporaryDirectory()
        panel, config, binding = fixture(cls.template_dir.name)
        result = finish(panel, config, binding)
        if result["status"] != "RESEARCH_ACCEPTED":
            raise AssertionError(result["status"])
        cls.template = Path(config["statePath"])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.template_dir.cleanup()

    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "optimizer.db"

    def copied_completed_journal(self) -> None:
        copy_sqlite(self.template, self.path)

    def mutate(self, statement: str, parameters: tuple = ()) -> None:
        with sqlite3.connect(self.path) as db:
            db.execute(statement, parameters)

    def assert_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "INTEGRITY"):
            journal = Journal(self.path)
            journal.close()

    def test_new_and_empty_legacy_database_open_without_state_migration(self) -> None:
        j = Journal(self.path)
        self.assertEqual(
            j.db.execute("SELECT count(*) FROM optimizer_audit").fetchone()[0], 0
        )
        self.assertIsNone(j.get("budget"))
        j.close()
        before = logical_snapshot(self.path)
        j = Journal(self.path)
        j.verify()
        j.close()
        self.assertEqual(before, logical_snapshot(self.path))

    def test_audited_budget_deletion_is_detected_on_open(self) -> None:
        self.copied_completed_journal()
        self.mutate("DELETE FROM optimizer_state WHERE k='budget'")
        self.assert_rejected()

    def test_audited_campaign_deletion_is_detected(self) -> None:
        self.copied_completed_journal()
        self.mutate("DELETE FROM optimizer_state WHERE k LIKE 'campaign:%'")
        self.assert_rejected()

    def test_budget_deletion_cannot_restart_tick_or_train(self) -> None:
        panel, config, binding = fixture(self.folder.name)
        tick(panel, config, binding, "2026-07-20T23:00:00Z")
        self.mutate("DELETE FROM optimizer_state WHERE k='budget'")
        before = logical_snapshot(self.path)
        with patch(
            "harpoon_quant.recursive.development_score",
            return_value={"score": -1e6, "admissible": False},
        ) as train:
            with self.assertRaisesRegex(ValueError, "INTEGRITY"):
                tick(panel, config, binding, "2026-07-20T23:00:00Z")
            train.assert_not_called()
        self.assertEqual(before, logical_snapshot(self.path))

    def test_missing_budget_on_already_open_connection_is_not_absence(self) -> None:
        self.copied_completed_journal()
        j = Journal(self.path)
        self.addCleanup(j.close)
        j.db.execute("DELETE FROM optimizer_state WHERE k='budget'")
        j.db.commit()
        with self.assertRaisesRegex(ValueError, "INTEGRITY"):
            j.get("budget")

    def test_deleted_holdout_row_is_detected(self) -> None:
        self.copied_completed_journal()
        self.mutate("DELETE FROM optimizer_holdouts")
        self.assert_rejected()

    def test_edited_holdout_fields_are_detected(self) -> None:
        for field, value in (
            ("lo", "2026-07-22"),
            ("hi", "2026-09-30"),
            ("domain", "ANOTHER_DOMAIN"),
            ("campaign", "ANOTHER_CAMPAIGN"),
        ):
            with self.subTest(field=field):
                for suffix in ("", "-wal", "-shm"):
                    Path(str(self.path) + suffix).unlink(missing_ok=True)
                self.copied_completed_journal()
                self.mutate(f"UPDATE optimizer_holdouts SET {field}=?", (value,))
                self.assert_rejected()

    def test_deleting_linked_holdout_state_is_detected(self) -> None:
        self.copied_completed_journal()
        with sqlite3.connect(self.path) as db:
            linked = db.execute(
                "SELECT k FROM optimizer_state WHERE k LIKE 'journal:holdout:%'"
            ).fetchall()
        self.assertTrue(linked)
        self.mutate("DELETE FROM optimizer_state WHERE k LIKE 'journal:holdout:%'")
        self.assert_rejected()

    def test_commit_verification_rolls_back_row_deletion(self) -> None:
        self.copied_completed_journal()
        before = logical_snapshot(self.path)
        j = Journal(self.path)
        try:
            with self.assertRaisesRegex(ValueError, "INTEGRITY"):
                with j.transaction():
                    j.db.execute("DELETE FROM optimizer_holdouts")
            j.verify()
        finally:
            j.close()
        self.assertEqual(before, logical_snapshot(self.path))

    def test_legitimate_original_historical_journals_remain_readable_without_migration(
        self,
    ) -> None:
        for name in ("initial_optimizer.sqlite3", "optimizer.sqlite3"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                source = ROOT / "economic_experiment" / "study" / name
                self.assertTrue(
                    source.is_file(), "Packaged original journal is required"
                )
                path = Path(folder) / name
                copy_sqlite(source, path)
                before = logical_snapshot(path)
                j = Journal(path)
                try:
                    j.verify()
                    self.assertGreater(j.get("budget")["spent"], 0)
                finally:
                    j.close()
                self.assertEqual(before, logical_snapshot(path))

    def test_legacy_budget_deletion_is_detected_without_migration(self) -> None:
        legacy_journal(self.path)
        self.mutate("DELETE FROM optimizer_state WHERE k='budget'")
        self.assert_rejected()

    def test_legacy_holdout_deletion_is_detected_from_audited_campaign(self) -> None:
        legacy_journal(self.path)
        self.mutate("DELETE FROM optimizer_holdouts")
        self.assert_rejected()

    def test_legacy_interval_edit_is_detected_from_receipt(self) -> None:
        legacy_journal(self.path)
        self.mutate("UPDATE optimizer_holdouts SET lo='2026-07-02'")
        self.assert_rejected()

    def test_legacy_domain_edit_cannot_release_consumed_window(self) -> None:
        legacy_journal(self.path)
        self.mutate("UPDATE optimizer_holdouts SET domain='ALTERED_DOMAIN'")
        j = Journal(self.path)
        try:
            self.assertTrue(hasattr(j, "integrity_report"))
            self.assertEqual(j.integrity_report["coverage"], "LEGACY_PARTIAL")
            with self.assertRaisesRegex(ValueError, "ALREADY_CONSUMED"):
                j.assert_holdout_available(
                    "2026-07-01", "2026-08-29", "ORIGINAL_DOMAIN"
                )
        finally:
            j.close()

    def test_legacy_unknown_interval_blocks_new_reservation(self) -> None:
        legacy_journal(self.path, receipt=False)
        j = Journal(self.path)
        try:
            self.assertTrue(hasattr(j, "integrity_report"))
            self.assertFalse(
                j.integrity_report["legacy_holdouts"][0]["interval_verified"]
            )
            with self.assertRaisesRegex(
                ValueError, "LEGACY_HOLDOUT_INTERVAL_UNVERIFIED"
            ):
                j.assert_holdout_available("2026-10-01", "2026-12-01", "NEW_DOMAIN")
        finally:
            j.close()

    def test_legacy_unknown_interval_cannot_activate_policy(self) -> None:
        legacy_journal(self.path, receipt=False, active=True)
        result = active_policy(str(self.path), {}, "2026-09-01T00:00:00Z")
        self.assertTrue(result["pause_entries"])
        self.assertEqual(result["reason"], "LEGACY_HOLDOUT_INTERVAL_UNVERIFIED")

    def test_transaction_checks_corruption_after_open(self) -> None:
        self.copied_completed_journal()
        j = Journal(self.path)
        self.addCleanup(j.close)
        self.mutate("DELETE FROM optimizer_state WHERE k='budget'")
        with self.assertRaisesRegex(ValueError, "INTEGRITY"):
            with j.transaction():
                self.fail("Transaction body must not execute after corruption")


if __name__ == "__main__":
    unittest.main()
