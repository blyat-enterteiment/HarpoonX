"""Offline contract tests. SQLite transactions and mocked HTTPS, no live archive."""
import hashlib
import hmac
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

from research.hf37 import hf37_gas_pilot as pilot
from research.hf37.gas import bridge_client as bridge


class PilotTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "test.sqlite"
        self.payload = b"synthetic\x00bytes"
        self.digest = hashlib.sha256(self.payload).hexdigest()
        patcher = patch.object(pilot, "DIGEST", self.digest)
        patcher.start()
        self.addCleanup(patcher.stop)
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE hf37_sip_durable_batch (batch_id TEXT PRIMARY KEY, sha256 TEXT, payload BLOB, acquired_at TEXT)")
            db.execute("INSERT INTO hf37_sip_durable_batch VALUES (?,?,?,?)",
                       (pilot.BATCH, self.digest, self.payload, "test"))
        self.connections = 0

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path)
        self.connections += 1

        class Adapter:
            def execute(self, sql, args=()):
                if sql.startswith("SET TRANSACTION"):
                    sql = "PRAGMA query_only=ON"
                if sql.startswith("SELECT pg_advisory"):
                    sql = "SELECT 1"
                sql = sql.replace("%s", "?").replace("DEFAULT now()", "DEFAULT CURRENT_TIMESTAMP")
                return db.execute(sql.replace(" FOR SHARE", ""), args)
        try:
            with db:
                yield Adapter()
        finally:
            db.close()

    def test_success_retry_and_conflict(self):
        def send(data, name):
            self.assertEqual((data, name), (self.payload, pilot.BATCH + ".json.gz"))
            return "file_one"
        expected = pilot.transfer(self.connect, send)
        self.assertEqual(expected["status"], "DRIVE_AND_POSTGRES_READBACK_VERIFIED")
        self.assertEqual(self.connections, 3)
        self.assertEqual(pilot.transfer(self.connect, send), expected)
        with self.assertRaisesRegex(ValueError, "CONFLICT"):
            pilot.transfer(self.connect, lambda *_: "file_two")
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT drive_file_id FROM hf37_sip_drive_receipt").fetchall(), [("file_one",)])

    def test_corruption_and_missing_source_abort_before_send(self):
        send = MagicMock()
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE hf37_sip_durable_batch SET payload=x'00'")
        with self.assertRaisesRegex(ValueError, "CHECKSUM"):
            pilot.transfer(self.connect, send)
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM hf37_sip_durable_batch")
        with self.assertRaisesRegex(ValueError, "MISSING"):
            pilot.transfer(self.connect, send)
        send.assert_not_called()

    def test_remote_failure_then_retry(self):
        with self.assertRaises(TimeoutError):
            pilot.transfer(self.connect, MagicMock(side_effect=TimeoutError))
        self.assertEqual(self.connections, 1)
        self.assertEqual(pilot.transfer(self.connect, lambda *_: "file_one")["bytes"], len(self.payload))

    def test_source_changed_during_upload(self):
        def send(*_):
            with sqlite3.connect(self.path) as db:
                db.execute("UPDATE hf37_sip_durable_batch SET payload=x'00'")
            return "file_one"
        with self.assertRaisesRegex(ValueError, "SOURCE_CHANGED"):
            pilot.transfer(self.connect, send)

    def test_missing_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(pilot.run()["status"], "BLOCKED_GAS_NOT_CONFIGURED")


class TransportTests(unittest.TestCase):
    url = "https://script.google.com/macros/s/test/exec"
    key = "a" * 64

    def test_request_wire_format(self):
        p = json.loads(bridge.request_bytes(b"test", "batch.gz", self.key))
        signed = "\n".join(str(p[k]) for k in ("version", "op", "ts", "nonce", "name", "sha256", "data"))
        self.assertEqual(hmac.new(self.key.encode(), signed.encode(), hashlib.sha256).hexdigest(), p["mac"])
        self.assertEqual(p["data"], "dGVzdA==")

    @patch.object(bridge.http.client, "HTTPSConnection")
    def test_response_and_redirect(self, connect):
        post, get = MagicMock(), MagicMock()
        redirect = post.getresponse.return_value
        redirect.status = 302
        redirect.getheader.return_value = "https://script.googleusercontent.com/macros/echo?id=test"
        data = b"test"
        proof = dict(status="DRIVE_READBACK_VERIFIED", bytes=len(data), file_id="abc", folder_id=bridge.FOLDER_ID,
                     sha256=hashlib.sha256(data).hexdigest())
        response = get.getresponse.return_value
        response.status = 200
        for change in ({}, {"sha256":"wrong"}, {"folder_id":"wrong"}, {"bytes":True}, {"file_id":""}):
            connect.side_effect = [post, get]
            response.read.return_value = json.dumps(proof | change).encode()
            if change:
                with self.assertRaisesRegex(ValueError, "UNVERIFIED"):
                    bridge.upload(data, "test.gz", self.url, self.key)
            else:
                self.assertEqual(bridge.upload(data, "test.gz", self.url, self.key), "abc")
                get.request.assert_called_once_with("GET", "/macros/echo?id=test")
        redirect.getheader.return_value = "https://example.com/redirect"
        connect.side_effect = [post]
        with self.assertRaisesRegex(ValueError, "LOCATION"):
            bridge.upload(data, "test.gz", self.url, self.key)


if __name__ == "__main__":
    unittest.main()
