"""Adversarial provenance checks; no historical file overwritten."""
from __future__ import annotations
import hashlib
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from fwn9_p9i_provenance import Provenance, safe_path, verify_expected, git_reader, promotion_gate


class ProvenanceTests(unittest.TestCase):
    def test_safe_path(self) -> None:
        self.assertEqual(safe_path("runtime30/profit8_replay.js"), "runtime30/profit8_replay.js")
        for bad in ("../x", "/absolute", "a/../b", "a//b", "a\\b", "a/./b", ""):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                safe_path(bad)

    def test_sha_match(self) -> None:
        expected = hashlib.sha256(b"historic").hexdigest()
        n, errors = verify_expected({"x": expected}, lambda _: b"historic")
        self.assertEqual((n, errors), (1, ()))

    def test_sha_mismatch_is_not_rewritten(self) -> None:
        expected = hashlib.sha256(b"old").hexdigest()
        _, errors = verify_expected({"x": expected}, lambda _: b"new")
        self.assertEqual(len(errors), 1)
        self.assertIn("SHA256_MISMATCH", errors[0])

    def test_missing_file(self) -> None:
        def fail(_: str) -> bytes:
            raise FileNotFoundError()
        n, errors = verify_expected({"x": "a" * 64}, fail)
        self.assertEqual(n, 1)
        self.assertIn("UNAVAILABLE", errors[0])

    def test_invalid_manifest(self) -> None:
        for manifest in ({}, {"a": "wrong"}, {"../x": "a" * 64}):
            with self.subTest(manifest=manifest), self.assertRaises(ValueError):
                verify_expected(manifest, lambda _: b"")

    def test_git_ref_must_be_immutable(self) -> None:
        with TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                git_reader(Path(folder), "main")

    def test_promotion_fails_closed_on_missing_operations(self) -> None:
        p = Provenance("a"*40, 108, (), 47, (), "1"*64, "2"*64, "2"*64, True, True, True)
        state: dict[str, object] = {"m11_phase9h": {
            "successful_ci":42444975973, "source_native_ledger_identity_one_fixture":True,
            "all_native_decisions_covered":False, "native_infeasibility_certified":False,
            "p9b_no_fill_valclock_closed":False}, "goal_accepted":False, "eligible_candidates":0}
        self.assertEqual(promotion_gate(p, state)["status"], "BLOCKED")
        self.assertFalse(promotion_gate(p, state)["all_native_decisions_covered"])
        self.assertEqual(promotion_gate(replace(p, archive_failures=("bad",), archive_verified=False),state)["status"],"BLOCKED")

    def test_forged_metadata_cannot_promote(self) -> None:
        p = Provenance("a"*40, 108, (), 47, (), "1"*64, "2"*64,
                       "2"*64, True, True, True)
        state: dict[str, object] = {"m11_phase9h": {
            "successful_ci": 42444975973, "source_native_ledger_identity_one_fixture": True,
            "all_native_decisions_covered": True, "native_infeasibility_certified": True,
            "p9b_no_fill_valclock_closed": True}, "goal_accepted": True, "eligible_candidates": 42}
        self.assertEqual(promotion_gate(p, state)["status"], "BLOCKED")

    def test_missing_historical_record_fails(self) -> None:
        p = Provenance("a"*40, 1, (), 1, (), "a"*64,"b"*64,"b"*64, True,True,True)
        with self.assertRaises(AssertionError):
            promotion_gate(p, {})
if __name__ == "__main__":
    unittest.main()
