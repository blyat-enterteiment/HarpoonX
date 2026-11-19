"""Transaction-order regression tests; doubles are not live database evidence."""

import os
import unittest
from unittest.mock import patch

from research.hf37.hf37_private_migration import DRIVE_ID, FOLDER_ID, NAME, SHA, run


class Cursor:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.db.events.append((self.db.role, sql.split()[0], params))
        if sql.startswith("SELECT"):
            if not self.db.state.get("committed"):
                raise AssertionError("Readback occurred before commit")
            if not self.db.read_only:
                raise AssertionError("Readback session must be read-only")
        if sql == "SET TRANSACTION READ ONLY":
            self.db.read_only = True

    def fetchone(self):
        return self.db.row


class DB:
    def __init__(self, role, events, state, row=None, commit_error=False):
        self.role, self.events, self.state = role, events, state
        self.row, self.commit_error = row, commit_error
        self.closed = False
        self.read_only = False

    def cursor(self):
        return Cursor(self)

    def commit(self):
        self.events.append((self.role, "COMMIT", None))
        if self.commit_error:
            raise OSError("Commit receipt unavailable")
        self.state["committed"] = True

    def rollback(self):
        self.events.append((self.role, "ROLLBACK", None))

    def close(self):
        self.closed = True
        self.events.append((self.role, "CLOSE", None))


class TestHF37PrivateMigration(unittest.TestCase):
    def setUp(self):
        self.events, self.state = [], {}
        self.expected = (DRIVE_ID, FOLDER_ID, NAME, SHA, False)
        self.writer = DB("writer", self.events, self.state)
        self.reader = DB("reader", self.events, self.state, row=self.expected)
        self.connections = [self.writer, self.reader]
        self.calls = 0

    def connect(self):
        if self.calls == 1:
            self.assertTrue(self.writer.closed)
            self.assertTrue(self.state["committed"])
        db = self.connections[self.calls]
        self.calls += 1
        return db

    def execute(self):
        with patch("research.hf37.hf37_private_migration.apply_schema"):
            return run(self.connect)

    def test_missing_private_dsn_fails_closed(self):
        with patch.dict(os.environ, {"HF37_DATABASE_URL": ""}):
            self.assertEqual(run()["status"], "BLOCKED_PRIVATE_DSN_MISSING")

    def test_success_requires_new_read_only_connection_after_commit(self):
        result = self.execute()
        self.assertEqual(result["status"], "POSTGRES_COMMITTED_AND_READBACK_VERIFIED")
        self.assertTrue(result["readback_after_commit"])
        self.assertTrue(result["readback_new_connection"])
        self.assertTrue(result["readback_read_only"])
        self.assertEqual(self.calls, 2)
        self.assertTrue(self.reader.closed)
        self.assertFalse(
            any(e[0] == "writer" and e[1] == "SELECT" for e in self.events)
        )

    def test_commit_failure_never_opens_reader(self):
        self.writer.commit_error = True
        with self.assertRaises(OSError):
            self.execute()
        self.assertEqual(self.calls, 1)
        self.assertTrue(self.writer.closed)
        self.assertIn(("writer", "ROLLBACK", None), self.events)

    def test_each_wrong_field_or_missing_row_rejects_verification(self):
        for i in range(5):
            self.setUp()
            changed = list(self.expected)
            changed[i] = True if i == 4 else "mismatch"
            self.reader.row = tuple(changed)
            with (
                self.subTest(field=i),
                self.assertRaisesRegex(ValueError, "READBACK_MISMATCH"),
            ):
                self.execute()
            self.assertTrue(self.reader.closed)
        self.setUp()
        self.reader.row = None
        with self.assertRaisesRegex(ValueError, "READBACK_MISMATCH"):
            self.execute()

    def test_same_connection_is_rejected(self):
        self.connections[1] = self.writer
        with self.assertRaisesRegex(ValueError, "REQUIRES_NEW_CONNECTION"):
            self.execute()

    def test_readback_connection_failure_does_not_claim_success(self):
        def connect():
            if self.calls:
                raise ConnectionError("Reader unavailable")
            return self.connect()

        with patch("research.hf37.hf37_private_migration.apply_schema"):
            with self.assertRaises(ConnectionError):
                run(connect)
        self.assertTrue(self.writer.closed)
        self.assertTrue(self.state["committed"])

    def test_schema_failure_closes_writer_and_never_opens_reader(self):
        with patch(
            "research.hf37.hf37_private_migration.apply_schema", side_effect=ValueError
        ):
            with self.assertRaises(ValueError):
                run(self.connect)
        self.assertTrue(self.writer.closed)
        self.assertEqual(self.calls, 1)


if __name__ == "__main__":
    unittest.main()
