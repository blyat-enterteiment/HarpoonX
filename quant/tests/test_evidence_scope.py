"""Engineering assertions only: none of these tests validates trading alpha."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from run_reused_evidence import inspect, run

from harpoon_quant.evidence_scope import (
    HYPOTHESES,
    EvidenceError,
    account_record,
    hypothesis_status,
    load,
    no_new_claims,
    verify_files,
)


def no_experiment():
    return {"new_strategy_variants_executed": 0,
            "hypothesis_results": {name: {"nominal": None, "stress": None,
                                         "status": "NOT_EXECUTED_BUDGET_BLOCKED"} for name in HYPOTHESES}}


class EvidenceScopeTests(unittest.TestCase):
    def test_missing_tampered_and_empty_manifest_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            expected = {"data": hashlib.sha256(b"original").hexdigest()}
            with self.assertRaisesRegex(EvidenceError, "MISSING_EVIDENCE"):
                verify_files(root, expected)
            (root / "data").write_bytes(b"original")
            self.assertEqual(verify_files(root, expected), expected)
            (root / "data").write_bytes(b"modified")
            with self.assertRaisesRegex(EvidenceError, "SHA256_MISMATCH"):
                verify_files(root, expected)
            with self.assertRaisesRegex(EvidenceError, "EMPTY_HASH"):
                verify_files(root, {})

    def test_paths_cannot_escape_root_including_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "root"
            root.mkdir()
            outside = Path(folder) / "outside"
            outside.write_bytes(b"data")
            (root / "link").symlink_to(outside)
            for name in ("../outside", str(outside), "link"):
                with self.subTest(name=name), self.assertRaisesRegex(EvidenceError, "UNSAFE"):
                    verify_files(root, {name: hashlib.sha256(b"data").hexdigest()})

    def test_duplicate_keys_and_nonfinite_json_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.json"
            for content in ('{"fresh_holdout":false,"fresh_holdout":true}', '{"net":NaN}', '[]'):
                path.write_text(content)
                with self.subTest(content=content), self.assertRaises(EvidenceError):
                    load(path)

    def test_boolean_claims_are_strict_not_truthy(self):
        valid = {"execution_allowed": False, "level8_accredited": False, "fresh_holdout": False}
        no_new_claims(valid)
        for key in valid:
            for bad in (True, "false", 0, None):
                value = {**valid, key: bad}
                with self.subTest(key=key, bad=bad), self.assertRaises(EvidenceError):
                    no_new_claims(value)
        with self.assertRaises(EvidenceError):
            no_new_claims({**valid, "observed_live_fills": 1})

    def test_hypotheses_are_unknown_not_zero_or_refuted(self):
        result = hypothesis_status(no_experiment())
        self.assertEqual(set(result), set(HYPOTHESES))
        for row in result.values():
            self.assertIsNone(row["nominal_net_usd"])
            self.assertIsNone(row["stress_net_usd"])
            self.assertEqual(row["status"], "INCONCLUSIVE_NOT_MEASURED")
            self.assertFalse(row["new_validation"])

    def test_hypothesis_result_cannot_be_forged_or_old_namespace_reused(self):
        valid = no_experiment()
        for scenario in ("nominal", "stress"):
            changed = copy.deepcopy(valid)
            changed["hypothesis_results"][HYPOTHESES[0]][scenario] = 0
            with self.assertRaisesRegex(EvidenceError, "UNSUPPORTED_HYPOTHESIS"):
                hypothesis_status(changed)
        for bad in (1, False, "0", None):
            with self.assertRaisesRegex(EvidenceError, "STRATEGY_SEARCH"):
                hypothesis_status({**valid, "new_strategy_variants_executed": bad})
        with self.assertRaisesRegex(EvidenceError, "NAMESPACE"):
            hypothesis_status({**valid, "hypothesis_results": {"H1_OLD_PROFIT8": {}}})

    def test_inactive_virtual_is_not_equivalence(self):
        row = account_record("matrix", "NOMINAL_A", -365, 0, virtual=True)
        self.assertEqual(row["effect"], "UNIDENTIFIED_NO_BUYS")
        self.assertFalse(row["promotion_allowed"])
        self.assertEqual(row["costs"], "ASSUMED_NOT_INVOICED")

    def test_invalid_economic_numbers_fail(self):
        for net, count in ((float("nan"), 1), (float("inf"), 1), (0, -1), (0, True), (True, 0)):
            with self.subTest(net=net, count=count), self.assertRaises(EvidenceError):
                account_record("test", "NOMINAL", net, count)

    def test_positive_archived_result_cannot_promote(self):
        row = account_record("fixture", "positive", 1_000_000, 500)
        self.assertEqual(row["history"], "REUSED")
        self.assertEqual(row["execution"], "MODELED")
        self.assertFalse(row["new_validation"])
        self.assertFalse(row["promotion_allowed"])

    def test_repository_integration_and_shared_lineage(self):
        result = inspect()
        self.assertEqual(result["archived_account_records"], 26)
        self.assertEqual(len(result["accounts"]), 26)
        self.assertIsNone(result["independent_market_sample_count"])
        self.assertFalse(result["new_validation"])
        self.assertEqual(result["budget"]["reserved_plus_unincorporated"], 151)
        self.assertEqual(result["new_policy_budget_units"], 0)
        self.assertTrue(any(len(v["reports"]) > 1 for v in result["dependence"]["shared_inputs_by_sha256"].values()))
        confirmed = [r for r in result["accounts"] if r["source_account"] == "corrected:NOMINAL_CONFIRMED"]
        self.assertAlmostEqual(confirmed[0]["net_usd"], 4.88)

    def test_delivery_is_deterministic_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            first, second = Path(folder) / "first", Path(folder) / "second"
            run(first)
            run(second)
            self.assertEqual((first / "report.json").read_bytes(), (second / "report.json").read_bytes())
            self.assertEqual((first / "sha256.json").read_bytes(), (second / "sha256.json").read_bytes())
            execution = json.loads((first / "execution.json").read_bytes())
            self.assertEqual(execution["reproductions"], [])
            self.assertEqual(execution["h1_h2_h3_this_run"], "NOT_EXECUTED")
            with self.assertRaisesRegex(EvidenceError, "OUTPUT_ALREADY_EXISTS"):
                run(first)

    def test_integrity_failure_cannot_create_pass_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            protocol_path = root / "research/reused_evidence/protocol.json"
            protocol_path.parent.mkdir(parents=True)
            protocol_path.write_text(json.dumps({"schema": "HARPOON_REUSED_EVIDENCE_PROTOCOL_1",
                "new_policy_budget_units": 0, "new_validation_allowed": False,
                "bound_files": {"missing": "0" * 64}}))
            output = root / "delivery"
            with self.assertRaisesRegex(EvidenceError, "MISSING_EVIDENCE"):
                run(output, root=root)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
