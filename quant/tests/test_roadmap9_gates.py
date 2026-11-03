"""The completion catalog must not convert missing or mislabelled evidence to PASS."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from harpoon_quant.roadmap9.gates import (
    close_plan,
    evidence_reference,
    verify_references,
)

ROOT = Path(__file__).resolve().parents[2]


class ClosureTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads((ROOT / "programme/roadmap9/plan.json").read_text())
        self.claims = [{"validator_id": v["id"], "result": "BLOCKED", "evidence": [],
                        "observed_value": "Not measured", "remaining_work": "Original observations required"}
                       for v in self.plan["validators"]]

    def test_missing_contract_cannot_conclude(self):
        with self.assertRaisesRegex(ValueError, "ALL_49"):
            close_plan(self.plan, self.claims[:-1], ROOT, source_commit="a" * 40, source_manifest=[])

    def test_missing_critical_receipt_stays_blocked(self):
        self.claims[0].update(result="PASS", origin="SYNTHETIC_ENGINEERING_ONLY")
        receipt = close_plan(self.plan, self.claims, ROOT, source_commit="a" * 40, source_manifest=[])
        self.assertEqual(receipt["validators"][0]["result"], "BLOCKED")
        self.assertFalse(receipt["all_phases_approved"])
        self.assertFalse(receipt["execution_allowed"])

    def test_synthetic_cannot_satisfy_observed_or_external_gate(self):
        reference = evidence_reference(ROOT, ROOT / "programme/roadmap9/plan.json")
        code = evidence_reference(ROOT, ROOT / "quant/harpoon_quant/roadmap9/gates.py")
        for index in (40, 45, 46):
            self.claims[index].update(result="PASS", origin="SYNTHETIC_ENGINEERING_ONLY", evidence=[reference])
        receipt = close_plan(self.plan, self.claims, ROOT, source_commit="a" * 40, source_manifest=[code])
        for index in (40, 45, 46):
            self.assertEqual(receipt["validators"][index]["result"], "BLOCKED")
            self.assertIn("EXTERNAL_OR_PROSPECTIVE_GATE_NOT_CLOSED_BY_LOCAL_TESTS",
                          receipt["validators"][index]["evidence_errors"])

    def test_hash_mutation_and_path_escape_block(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            item = root / "evidence.json"
            item.write_text('{"result":"FAIL"}')
            reference = evidence_reference(root, item)
            item.write_text('{"result":"PASS"}')
            self.assertTrue(verify_references(root, [reference]))
            reference["path"] = "../outside.json"
            self.assertTrue(verify_references(root, [reference]))

    def test_empty_manifest_or_unversioned_code_cannot_pass(self):
        evidence = evidence_reference(ROOT, ROOT / "programme/roadmap9/plan.json")
        code = evidence_reference(ROOT, ROOT / "quant/harpoon_quant/roadmap9/gates.py")
        self.claims[0].update(result="PASS", origin="SYNTHETIC_ENGINEERING_ONLY", evidence=[evidence])
        for commit, manifest in (("a" * 40, []), ("not-a-commit", [code]), ("a" * 40, [evidence])):
            receipt = close_plan(self.plan, self.claims, ROOT, source_commit=commit, source_manifest=manifest)
            self.assertEqual(receipt["validators"][0]["result"], "BLOCKED")
            self.assertTrue(receipt["source_integrity_errors"])

    def test_successful_ablation_can_still_reject_the_candidate(self):
        reference = evidence_reference(ROOT, ROOT / "quant/harpoon_quant/roadmap9/gates.py")
        for claim, contract in zip(self.claims, self.plan["validators"], strict=True):
            if contract["phase"] == "P08":
                claim.update(result="PASS", origin="HISTORICAL_MODELED", evidence=[reference],
                             candidate_decision="REJECTED_CANDIDATE")
        receipt = close_plan(self.plan, self.claims, ROOT, source_commit="a" * 40, source_manifest=[reference])
        phase = next(p for p in receipt["phases"] if p["id"] == "P08")
        self.assertEqual(phase["phase_decision"], "REJECTED_CANDIDATE")
        self.assertFalse(phase["dependent_phase_promotion_allowed"])

    def test_engineering_failure_blocks_phase_without_inventing_candidate_rejection(self):
        reference = evidence_reference(ROOT, ROOT / "quant/harpoon_quant/roadmap9/gates.py")
        for claim, contract in zip(self.claims, self.plan["validators"], strict=True):
            if contract["phase"] == "P09":
                claim.update(result="FAIL" if contract["id"] == "V040" else "PASS",
                             origin="SYNTHETIC_ENGINEERING_ONLY", evidence=[reference])
        receipt = close_plan(self.plan, self.claims, ROOT, source_commit="a" * 40, source_manifest=[reference])
        phase = next(p for p in receipt["phases"] if p["id"] == "P09")
        self.assertEqual(phase["phase_decision"], "BLOCKED")
        self.assertEqual(phase["candidate_decisions"], [])
        self.assertEqual(phase["results"], {"PASS": 3, "FAIL": 1})
        self.assertFalse(phase["dependent_phase_promotion_allowed"])


if __name__ == "__main__":
    unittest.main()
