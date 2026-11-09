"""P9I-R2 diagnostics must never silently promote archived data."""
from __future__ import annotations
import unittest
from pathlib import Path
from fwn9_p9i_legacy_debt import inspect


class ArchivedDebtTests(unittest.TestCase):
    def test_immutable_archive_debt_is_falsifiable(self) -> None:
        result = inspect(Path(__file__).resolve().parents[1])
        self.assertEqual(result["schema"], "FWN9_P9I_R2_ARCHIVE_DEBT_1")
        self.assertGreaterEqual(result["archive_bound_paths"], 100)
        self.assertEqual(result["m9_frozen_source_mismatch_count"], 0)
        self.assertTrue(result["legacy_profit8_anchor_verified"])
        self.assertEqual(result["global_certification"], "BLOCKED")
        self.assertFalse(result["historical_manifest_modified"])
        self.assertEqual(result["archive_mismatch_count"], len(result["debts"]))
        for row in result["debts"]:
            self.assertIn(row["status"], ("SPLIT_HISTORICAL_LINEAGE", "UNRESOLVED_HISTORICAL_BYTES"))
            self.assertNotEqual(row["archived_expected_sha256"], row["source_head_actual_sha256"])

if __name__ == "__main__":
    unittest.main()
