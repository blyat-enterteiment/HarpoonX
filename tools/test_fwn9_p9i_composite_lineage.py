"""P9I R3: adversarial composite historical lineage tests."""
from __future__ import annotations

import unittest
from pathlib import Path
from typing import ClassVar
from fwn9_p9i_composite_lineage import CompositeResult, diagnostic, verify_composite, EXPECTED_EXCEPTION_PATHS


class CompositeHistoricalTests(unittest.TestCase):
    root: ClassVar[Path]
    r: ClassVar[CompositeResult]

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.r = verify_composite(cls.root)

    def test_all_108_bytes(self) -> None:
        self.assertEqual(self.r.legacy_paths, 105)
        self.assertEqual(self.r.exception_paths, 3)
        self.assertEqual(self.r.composite_mismatches, ())
        self.assertTrue(self.r.composite_bytes_verified)

    def test_no_atomic_snapshot_claim(self) -> None:
        self.assertFalse(self.r.true_atomic_snapshot_verified)
        self.assertFalse(self.r.n9s_certified)

    def test_exact_exception_paths_only(self) -> None:
        self.assertEqual(len(EXPECTED_EXCEPTION_PATHS), 3)
        self.assertEqual(EXPECTED_EXCEPTION_PATHS, frozenset({
            "quant/harpoon_quant/evidence_scope.py",
            "quant/tests/test_evidence_scope.py",
            "tools/run_reused_evidence.py",
        }))

    def test_immutable_ref_is_not_branch(self) -> None:
        self.assertEqual(len(self.r.legacy_source_head), 40)
        self.assertEqual(len(self.r.exception_ref), 40)
        self.assertNotEqual(self.r.legacy_source_head,self.r.exception_ref)

    def test_manifest_unchanged(self) -> None:
        info=diagnostic(self.root)
        self.assertEqual(info["source_modification_count"],0)
        self.assertEqual(info["classification"],"SPLIT_LINEAGE_EXACT_BYTES_NOT_ATOMIC_SNAPSHOT")
        self.assertFalse(info["atomic_snapshot_verified"])

if __name__ == "__main__":
    unittest.main()
