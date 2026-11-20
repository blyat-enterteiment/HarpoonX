import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from research.hf37.hf37_cohort_archive import build_zip, frozen_batches
from research.hf37.hf38_drive import Drive


class TestDrive(unittest.TestCase):
    def test_first_frozen_batch_requires_exact_bytes_and_identity(self):
        batches = frozen_batches()
        self.assertEqual(len(batches), 106392)
        batch_id, identity = batches[0]

        def request(url, key, secret):
            self.assertIn("feed=sip", url)
            kind = "quotes" if "/quotes?" in url else "trades"
            t = identity["start"]
            record = (
                {"t": t, "bp": 100, "ap": 101, "bs": 10, "as": 10}
                if kind == "quotes" else {"t": t, "p": 100, "s": 10, "i": 1, "x": "V"}
            )
            return {kind: [record], "next_page_token": None}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "batch.zip"
            build_zip(path, root, identity, request, ("test-key", "test-secret"))
            raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        metadata = {"id": "file", "parents": ["folder"], "trashed": False,
                    "name": f"{batch_id}.zip", "mimeType": "application/zip",
                    "appProperties": {"batch_id": batch_id, "sha256": digest}}

        class MemoryDrive(Drive):
            def open(self, url, data=None, content_type=None):
                return io.BytesIO(raw if "alt=media" in url else json.dumps(metadata).encode())

        store = MemoryDrive("test-token")
        self.assertEqual(store.verify("file", "folder", batch_id, identity, digest), digest)
        with self.assertRaisesRegex(ValueError, "DRIVE_SHA256_MISMATCH"):
            store.verify("file", "folder", batch_id, identity, "f" * 64)
        with self.assertRaisesRegex(ValueError, "ARCHIVE_IDENTITY_MISMATCH"):
            store.verify("file", "folder", batch_id, dict(identity, symbol="SPY"), digest)
        with self.assertRaisesRegex(ValueError, "DRIVE_METADATA_MISMATCH"):
            store.verify("file", "other-folder", batch_id, identity, digest)
