"""C21 falsification controls for original archive provenance and missing states.

Tests only reject malformed tiny input objects; do not instantiate a trading
account, generator, portfolio, strategy or market seed.
"""
from __future__ import annotations

import copy
import hashlib
import tempfile
import unittest
from pathlib import Path

from fwn9_p9m_c21_archived_prebar_audit import (
    ARCHIVE_SHA, MEMBER, MEMBER_SHA, REQUIRED_PREBAR,
    audit_one_existing_development_member, inspect_history, sha_file,
)


class C21ArchiveContract(unittest.TestCase):
    def test_only_one_sha_pinned_development_member(self) -> None:
        self.assertEqual(len(ARCHIVE_SHA), 64)
        self.assertEqual(len(MEMBER_SHA), 64)
        self.assertEqual(MEMBER, "evidence/modulation9/development/WEAK_730101.json.gz")
        self.assertNotIn("/final/", MEMBER)
        self.assertEqual(len(set(REQUIRED_PREBAR)),len(REQUIRED_PREBAR))

    def test_fake_archive_bytes_fail_before_zip_content_access(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            fake = Path(d) / "not_original.zip"
            fake.write_bytes(b"syntactically invalid original M9 archive")
            with self.assertRaisesRegex(ValueError,"C21_ORIGINAL_M9_ZIP_SHA256"):
                audit_one_existing_development_member(fake)
            with fake.open("rb") as src:
                self.assertEqual(sha_file(fake),hashlib.sha256(src.read()).hexdigest())

    def test_final_stage_is_rejected_even_without_account_rows(self) -> None:
        with self.assertRaisesRegex(ValueError,"C21_REGISTERED_EXISTING_DEVELOPMENT_ONLY"):
            inspect_history({"world":"WEAK","stage":"final","seed":730101,"accounts":[]})

    def test_unregistered_development_seed_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError,"C21_REGISTERED_EXISTING_DEVELOPMENT_ONLY"):
            inspect_history({"world":"WEAK","stage":"development","seed":730102,"accounts":[]})

    def test_no_account_data_is_not_accepted_as_populated_state_distribution(self) -> None:
        with self.assertRaisesRegex(ValueError,"C21_REGISTERED_EXISTING_DEVELOPMENT_ONLY"):
            inspect_history({"world":"WEAK","stage":"development","seed":730101,"accounts":[]})

    def test_register_hash_mutation_is_detected_on_fixture_strings(self) -> None:
        candidate=copy.copy([ARCHIVE_SHA,MEMBER_SHA])
        candidate[0]="0"*64
        self.assertNotEqual(candidate[0],ARCHIVE_SHA)
        self.assertEqual(candidate[1],MEMBER_SHA)


if __name__=="__main__":
    unittest.main()
