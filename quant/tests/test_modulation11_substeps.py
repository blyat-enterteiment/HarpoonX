"""Exact-law trace test: engineering fixture, not an economic account."""

from __future__ import annotations

import unittest

from harpoon_quant.modulation10 import make_protocol
from harpoon_quant.modulation11_substeps import export_substeps


class M11SubstepTests(unittest.TestCase):
    def test_unmodified_generator_and_signals(self) -> None:
        protocol = make_protocol()
        report = export_substeps(protocol, 1206101, "NULL", "development")
        self.assertEqual(report["substep_count"], len(report["substeps"]) * 8)
        self.assertEqual(len(report["substeps"]), len(report["dataset"]["sessions"]) * 78 * 3)
        self.assertEqual(len(report["dataset_sha256"]), 64)
        self.assertEqual(len(report["signals_sha256"]), 64)
        self.assertEqual(len(report["substeps_sha256"]), 64)
        self.assertNotIn("substeps", report["signals"])

    def test_final_sealed(self) -> None:
        with self.assertRaisesRegex(ValueError, "M11_FINAL_SEALED"):
            export_substeps(make_protocol(), 1506201, "NULL", "final")

    def test_never_modify_law_or_limits(self) -> None:
        protocol = make_protocol()
        protocol["generator"]["intrabar_substeps"] = 4
        with self.assertRaisesRegex(ValueError, "M11_GRID_CONTRACT_CHANGED"):
            export_substeps(protocol, 1206101, "NULL", "development")
