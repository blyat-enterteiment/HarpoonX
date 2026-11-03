"""Adversarial checks for reservation identity and honest prior-budget import."""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from harpoon_quant.roadmap9.registry import (
    RECIPE_FIELDS,
    begin_measurement,
    digest,
    documented_history,
    freeze_registry,
    record_measurement,
    verify_registry,
)


class RegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "trials.jsonl"
        self.output = Path(self.temporary.name) / "result.json"
        self.output.write_text('{"origin":"SYNTHETIC_ENGINEERING_ONLY","net":-1}\n')
        self.recipes = [
            {
                "id": f"R{i + 1}",
                "hypothesis": f"H{i // 2 + 1}",
                "scenarios": ["NOMINAL", "STRESS"],
                **{
                    field: {"fixture_contract": field, "version": 1}
                    for field in RECIPE_FIELDS
                },
            }
            for i in range(6)
        ]
        self.bindings = {
            k: digest({"fixture": k}) for k in ("code", "data", "settings", "plan")
        }
        self.history = {
            "reported_spent": 53,
            "limit": 128,
            "global_history_complete": False,
            "sources": [{"path": "prior/freeze.json", "sha256": "1" * 64}],
        }

    def freeze(self) -> dict:
        return freeze_registry(self.path, self.recipes, self.history, self.bindings)

    def test_separate_recipe_and_scenario_budgets_preserve_prior_count(self) -> None:
        receipt = self.freeze()
        self.assertEqual(receipt["recipe_count"], 6)
        self.assertEqual(receipt["reserved_policy_scenario_measurements"], 12)
        self.assertEqual(receipt["prior_reported_measurements"], 53)
        self.assertEqual(receipt["reported_plus_reserved_measurements"], 65)
        self.assertFalse(receipt["global_history_complete"])
        self.assertFalse(receipt["financial_acceptance_allowed"])

    def history_fixture(self) -> Path:
        root = Path(self.temporary.name) / "prior_project"
        bodies = {
            "evidence/residual_30_18_0/registration/admission.json": {
                "budget": {"spent": 47, "limit": 128}
            },
            "research/research9_30_19/freeze.json": {
                "new_policy_scenario_measurements": 6,
                "declared_budget_parent": 47,
                "declared_budget_after": 53,
                "declared_budget_limit": 128,
                "global_budget_independently_reconciled": False,
                "history_already_seen": True,
            },
            "research/research9_30_19/amendment_01.json": {
                "retained_engineering_retry": "fixture"
            },
        }
        for name, body in bodies.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(body) + "\n")
        return root

    def test_documented_history_retains_actual_bytes_and_incomplete_scope(self) -> None:
        root = self.history_fixture()
        history = documented_history(root)
        self.assertEqual(history["reported_spent"], 53)
        self.assertEqual(history["inherited_admitted_count"], 47)
        self.assertFalse(history["global_history_complete"])
        self.assertFalse(history["independent_preregistration"])
        for source in history["sources"]:
            self.assertEqual(
                source["sha256"],
                hashlib.sha256((root / source["path"]).read_bytes()).hexdigest(),
            )

    def test_documented_history_rejects_discontinuous_counts(self) -> None:
        root = self.history_fixture()
        path = root / "research/research9_30_19/freeze.json"
        body = json.loads(path.read_text())
        body["declared_budget_after"] = 6
        path.write_text(json.dumps(body))
        with self.assertRaisesRegex(ValueError, "DISCONTINUITY"):
            documented_history(root)

    def test_identical_freeze_is_idempotent(self) -> None:
        first = self.freeze()
        before = self.path.read_bytes()
        self.assertEqual(self.freeze(), first)
        self.assertEqual(self.path.read_bytes(), before)

    def test_seventh_recipe_is_rejected_before_file_created(self) -> None:
        recipes = [*self.recipes, {**self.recipes[0], "id": "R7"}]
        with self.assertRaisesRegex(ValueError, "RECIPE_BUDGET"):
            freeze_registry(self.path, recipes, self.history, self.bindings)
        self.assertFalse(self.path.exists())

    def test_lifetime_budget_cannot_be_reset_or_overrun(self) -> None:
        for count in (0, -1, 120, True):
            with self.subTest(count=count), self.assertRaises(ValueError):
                freeze_registry(
                    self.path,
                    self.recipes,
                    {**self.history, "reported_spent": count},
                    self.bindings,
                )
        self.assertFalse(self.path.exists())

    def test_missing_contract_and_false_history_completeness_are_rejected(self) -> None:
        recipes = copy.deepcopy(self.recipes)
        del recipes[0]["exit"]
        with self.assertRaisesRegex(ValueError, "INCOMPLETE_RECIPE:exit"):
            freeze_registry(self.path, recipes, self.history, self.bindings)
        with self.assertRaisesRegex(ValueError, "COMPLETENESS"):
            freeze_registry(
                self.path,
                self.recipes,
                {**self.history, "global_history_complete": True},
                self.bindings,
            )

    def test_post_result_recipe_or_binding_change_is_rejected(self) -> None:
        self.freeze()
        recipes = copy.deepcopy(self.recipes)
        recipes[0]["exit"] = {"changed_after_result": True}
        with self.assertRaisesRegex(ValueError, "FROZEN_RECIPE_CHANGED"):
            freeze_registry(self.path, recipes, self.history, self.bindings)
        with self.assertRaisesRegex(ValueError, "BINDING_CHANGED"):
            begin_measurement(
                self.path, "R1", "NOMINAL", {**self.bindings, "code": "f" * 64}
            )

    def test_result_requires_previously_started_registered_measurement(self) -> None:
        self.freeze()
        with self.assertRaisesRegex(ValueError, "UNIQUE_START"):
            record_measurement(self.path, "R1", "NOMINAL", self.output)
        with self.assertRaisesRegex(ValueError, "UNREGISTERED"):
            begin_measurement(self.path, "R7", "NOMINAL", self.bindings)
        self.assertEqual(verify_registry(self.path)["started_measurements"], 0)

    def test_start_and_result_retries_consume_no_additional_budget(self) -> None:
        self.freeze()
        begin_measurement(self.path, "R1", "NOMINAL", self.bindings)
        begin_measurement(self.path, "R1", "NOMINAL", self.bindings)
        record_measurement(self.path, "R1", "NOMINAL", self.output)
        before = self.path.read_bytes()
        result = record_measurement(self.path, "R1", "NOMINAL", self.output)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(result["started_measurements"], 1)
        self.assertEqual(result["completed_measurements"], 1)
        self.assertEqual(result["reported_plus_reserved_measurements"], 65)

    def test_changed_result_is_neither_overwritten_nor_accepted(self) -> None:
        self.freeze()
        begin_measurement(self.path, "R1", "NOMINAL", self.bindings)
        record_measurement(self.path, "R1", "NOMINAL", self.output)
        before = self.path.read_bytes()
        self.output.write_text('{"net":1000}\n')
        with self.assertRaisesRegex(ValueError, "RESULT_CONFLICT"):
            record_measurement(self.path, "R1", "NOMINAL", self.output)
        with self.assertRaisesRegex(ValueError, "RESULT_HASH_CHANGED"):
            verify_registry(self.path)
        self.assertEqual(before, self.path.read_bytes())

    def test_tampered_chain_and_rehashed_impossible_transition_are_rejected(
        self,
    ) -> None:
        self.freeze()
        begin_measurement(self.path, "R1", "NOMINAL", self.bindings)
        events = [json.loads(x) for x in self.path.read_text().splitlines()]
        events[1]["payload"]["recipe_id"] = "R7"
        self.path.write_text("".join(json.dumps(e) + "\n" for e in events))
        with self.assertRaisesRegex(ValueError, "CHAIN_HASH"):
            verify_registry(self.path)
        events[1]["hash"] = digest(
            {k: events[1][k] for k in ("sequence", "previous", "payload")}
        )
        self.path.write_text("".join(json.dumps(e) + "\n" for e in events))
        with self.assertRaisesRegex(ValueError, "UNREGISTERED"):
            verify_registry(self.path)

    def test_nan_and_unbound_dataset_are_rejected(self) -> None:
        recipes = copy.deepcopy(self.recipes)
        recipes[0]["allocation"] = {"weight": float("nan")}
        with self.assertRaises(ValueError):
            freeze_registry(self.path, recipes, self.history, self.bindings)
        with self.assertRaisesRegex(ValueError, "MISSING_BINDING:data"):
            freeze_registry(
                self.path,
                self.recipes,
                self.history,
                {k: v for k, v in self.bindings.items() if k != "data"},
            )

    def test_full_matrix_retains_no_authority_and_no_new_observation_claim(
        self,
    ) -> None:
        self.freeze()
        for recipe in self.recipes:
            for scenario in recipe["scenarios"]:
                begin_measurement(self.path, recipe["id"], scenario, self.bindings)
                record_measurement(self.path, recipe["id"], scenario, self.output)
        result = verify_registry(self.path, self.recipes)
        self.assertEqual(result["completed_measurements"], 12)
        self.assertFalse(result["execution_allowed"])
        self.assertFalse(result["level9_accredited"])
        self.assertFalse(result["global_selection_correction_verified"])


if __name__ == "__main__":
    unittest.main()
