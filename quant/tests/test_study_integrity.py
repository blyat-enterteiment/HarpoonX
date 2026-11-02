"""Sealed-study regression and corruption checks; all mutations use temp copies."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np

from harpoon_quant.recursive import Journal
from harpoon_quant.study_integrity import (
    StudyIntegrityError,
    assert_inputs_unchanged,
    load_verified_study,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "economic_experiment"
spec = importlib.util.spec_from_file_location(
    "sealed_study_analysis", SOURCE / "analyze.py"
)
assert spec is not None and spec.loader is not None
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


@contextmanager
def temporary_study() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="harpoon-integrity-test-") as directory:
        root = Path(directory)
        for name in (
            "study/protocol.json",
            "study/holdout.json",
            "study/finalist.json",
            "study/optimizer.sqlite3",
            "study/decision.json",
            "analysis_protocol.json",
            "evidence/alpaca_calendar.json",
        ):
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SOURCE / name, target)
        frozen = "work/HarpoonX_Motor_Quant/harpoon_quant"
        (root / frozen).mkdir(parents=True)
        for name in ("economic_lab.py", "performance.py", "recursive.py"):
            shutil.copy2(SOURCE / frozen / name, root / frozen / name)
        yield root


def reseal_holdout(root: Path, holdout: dict[str, Any]) -> None:
    """Create a self-consistent but semantically corrupt writer result in a fixture."""
    path = root / "study/holdout.json"
    path.write_text(json.dumps(holdout, allow_nan=False))
    journal = Journal(root / "study/optimizer.sqlite3")
    try:
        state = journal.get("economic:holdout")
        state["result_hash"] = hashlib.sha256(path.read_bytes()).hexdigest()
        with journal.transaction():
            journal.put("economic:holdout", state, datetime.now(UTC).isoformat())
    finally:
        journal.close()


class StudyIntegrityTests(unittest.TestCase):
    def test_historical_analysis_is_numerically_identical_and_read_only(self):
        before = hashlib.sha256(
            (SOURCE / "study/optimizer.sqlite3").read_bytes()
        ).hexdigest()
        actual = analysis.analyze_study(SOURCE)
        expected = json.loads((SOURCE / "study/decision.json").read_text())
        historical = {
            key: value
            for key, value in expected.items()
            if key not in {"integrity", "scenario_roles"}
        }
        self.assertEqual({key: actual[key] for key in historical}, historical)
        self.assertEqual(actual["status"], "REJECTED")
        self.assertEqual(actual["integrity"]["verified_runs"], 45)
        self.assertEqual(
            actual["integrity"]["research_budget"], {"limit": 128, "spent": 23}
        )
        self.assertEqual(
            actual["scenario_roles"]["descriptive_only"],
            ["gaps", "iv_crush", "liquidity", "delay", "outage"],
        )
        self.assertEqual(
            before,
            hashlib.sha256(
                (SOURCE / "study/optimizer.sqlite3").read_bytes()
            ).hexdigest(),
        )

    def test_each_protected_input_rejects_changed_content(self):
        for name in (
            "study/protocol.json",
            "analysis_protocol.json",
            "study/holdout.json",
            "study/finalist.json",
            "evidence/alpaca_calendar.json",
        ):
            with self.subTest(name=name), temporary_study() as root:
                path = root / name
                value = json.loads(path.read_text())
                value["unexpected_mutation"] = True
                path.write_text(json.dumps(value))
                with self.assertRaises(StudyIntegrityError):
                    load_verified_study(root)

    def test_frozen_implementation_is_checked(self):
        with temporary_study() as root:
            path = root / "work/HarpoonX_Motor_Quant/harpoon_quant/economic_lab.py"
            path.write_bytes(path.read_bytes() + b"\n# changed fixture\n")
            with self.assertRaisesRegex(
                StudyIntegrityError, "FROZEN_IMPLEMENTATION_MISMATCH"
            ):
                load_verified_study(root)

    def test_finalist_seal_is_exact_not_a_metric_tolerance(self):
        with temporary_study() as root:
            path = root / "study/finalist.json"
            finalist = json.loads(path.read_text())
            finalist["score"] += 1e-12
            path.write_text(json.dumps(finalist))
            with self.assertRaisesRegex(StudyIntegrityError, "FINALIST_FILE_MISMATCH"):
                load_verified_study(root)

    def test_semantic_corruption_rejected_even_if_writer_updated_hash(self):
        def change_return(run):
            run["returns"][0] += 0.001
            run["mean_log_growth"] = float(np.log1p(run["returns"]).mean())

        def remove_nav(run):
            index = next(
                i for i, event in enumerate(run["ledger"]) if event["kind"] == "NAV"
            )
            run["ledger"].pop(index)

        def change_cash(run):
            next(event for event in run["ledger"] if event["kind"] == "NAV")[
                "cash"
            ] += 1

        def invalid_holding(run):
            trade = run["trades"][0]
            trade["exit_at"] = (
                datetime.fromisoformat(trade["entry_at"]) + timedelta(hours=73)
            ).isoformat()

        cases = [
            (
                "metric",
                lambda r: r["metrics"].__setitem__(
                    "net_profit_usd_on_adjusted_initial_capital", 999
                ),
                "METRICS_RECONCILIATION",
            ),
            (
                "missing_metric",
                lambda r: r["metrics"].pop("max_drawdown"),
                "METRICS_RECONCILIATION:FIELDS",
            ),
            ("dates", lambda r: r["dates"].pop(), "RUN_DATE_ALIGNMENT"),
            ("return", change_return, "RETURNS_NAV_RECONCILIATION"),
            ("missing_nav", remove_nav, "NAV_MARKS_INCOMPLETE"),
            ("cash", change_cash, "CASH_FLOW_RECONCILIATION"),
            ("holding", invalid_holding, "HOLDING_OR_EXIT_TIME"),
            (
                "exit_quantity",
                lambda r: r["trades"][0].__setitem__("lots", 9),
                "POSITION_LOTS_NOT_CLOSED",
            ),
            (
                "exit_pnl",
                lambda r: r["trades"][0].__setitem__("net_pnl_usd", 999),
                "CASH_FLOW_RECONCILIATION",
            ),
        ]
        for name, mutate, error in cases:
            with self.subTest(name=name), temporary_study() as root:
                holdout = json.loads((root / "study/holdout.json").read_text())
                mutate(holdout["results"][0]["runs"]["baseline"])
                reseal_holdout(root, holdout)
                with self.assertRaisesRegex(StudyIntegrityError, error):
                    load_verified_study(root)

    def test_missing_run_and_duplicate_seed_rejected(self):
        for mutation in ("missing_run", "duplicate_seed"):
            with self.subTest(mutation=mutation), temporary_study() as root:
                holdout = json.loads((root / "study/holdout.json").read_text())
                if mutation == "missing_run":
                    holdout["results"][0]["runs"].pop("cost_2")
                else:
                    holdout["results"][1]["seed"] = holdout["results"][0]["seed"]
                reseal_holdout(root, holdout)
                with self.assertRaises(StudyIntegrityError):
                    load_verified_study(root)

    def test_missing_registration_and_changed_inputs_fail_closed(self):
        with temporary_study() as root:
            verified = load_verified_study(root)
            path = root / "analysis_protocol.json"
            path.write_bytes(path.read_bytes() + b" ")
            with self.assertRaises(StudyIntegrityError):
                assert_inputs_unchanged(verified)
        with temporary_study() as root:
            journal = Journal(root / "study/optimizer.sqlite3")
            try:
                with journal.transaction():
                    journal.put(
                        "economic:analysis_protocol", {}, datetime.now(UTC).isoformat()
                    )
            finally:
                journal.close()
            with self.assertRaises(StudyIntegrityError):
                load_verified_study(root)

    def test_malformed_json_and_nonfinite_decision_inputs_rejected(self):
        for content in ('{"value":NaN}', '{"value":1,"value":2}'):
            with self.subTest(content=content), temporary_study() as root:
                (root / "analysis_protocol.json").write_text(content)
                with self.assertRaises(StudyIntegrityError):
                    load_verified_study(root)
        for value in (float("nan"), float("inf")):
            with self.assertRaisesRegex(ValueError, "NONFINITE_DECISION_INPUT"):
                analysis.decide(value, 0.01, 0.01, True, True, True, True)

    def test_rejects_before_calculation_or_writing(self):
        with temporary_study() as root:
            decision = (root / "study/decision.json").read_bytes()
            journal = (root / "study/optimizer.sqlite3").read_bytes()
            path = root / "study/holdout.json"
            path.write_bytes(path.read_bytes() + b" ")
            with patch.object(analysis, "_calculate") as calculate:
                with self.assertRaises(StudyIntegrityError):
                    analysis.main(root)
                calculate.assert_not_called()
            self.assertEqual((root / "study/decision.json").read_bytes(), decision)
            self.assertEqual((root / "study/optimizer.sqlite3").read_bytes(), journal)

    def test_first_registration_failure_preserves_published_file(self):
        with temporary_study() as root:
            original = (root / "study/decision.json").read_bytes()
            result = json.loads(original)
            result["publication_test"] = "TEMPORARY_FAILURE_FIXTURE"
            with (
                patch.object(analysis, "_calculate", return_value=result),
                patch.object(
                    Journal,
                    "put",
                    side_effect=RuntimeError("simulated_register_failure"),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated_register_failure"):
                    analysis.main(root)
            self.assertEqual((root / "study/decision.json").read_bytes(), original)
            self.assertEqual(
                load_verified_study(root).budget, {"limit": 128, "spent": 23}
            )

    def test_failure_after_file_replace_is_pending_and_recoverable(self):
        with temporary_study() as root:
            original = (root / "study/decision.json").read_bytes()
            result = json.loads(original)
            result["publication_test"] = "TEMPORARY_FAILURE_FIXTURE"
            real_put = Journal.put
            calls = 0

            def fail_completion(journal, key, value, now):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise RuntimeError("simulated_completion_failure")
                return real_put(journal, key, value, now)

            with (
                patch.object(analysis, "_calculate", return_value=result),
                patch.object(
                    Journal, "put", autospec=True, side_effect=fail_completion
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "simulated_completion_failure"
                ):
                    analysis.main(root)
            self.assertNotEqual((root / "study/decision.json").read_bytes(), original)
            with self.assertRaisesRegex(
                StudyIntegrityError, "DECISION_PUBLICATION_PENDING"
            ):
                load_verified_study(root)
            recovered = analysis.recover_pending_publication(root)
            self.assertEqual(recovered, result)
            self.assertEqual(
                load_verified_study(root).budget, {"limit": 128, "spent": 23}
            )
            journal = Journal(root / "study/optimizer.sqlite3")
            try:
                self.assertEqual(
                    journal.get("economic:decision")["publication_state"], "COMPLETE"
                )
            finally:
                journal.close()

    def test_budget_change_in_publication_window_is_rejected(self):
        with temporary_study() as root:
            original = (root / "study/decision.json").read_bytes()

            def open_after_budget_update(path):
                journal = Journal(path)
                with journal.transaction():
                    journal.put(
                        "budget",
                        {"limit": 128, "spent": 24},
                        datetime.now(UTC).isoformat(),
                    )
                return journal

            with (
                patch.object(analysis, "_calculate", return_value=json.loads(original)),
                patch.object(analysis, "Journal", side_effect=open_after_budget_update),
            ):
                with self.assertRaisesRegex(
                    StudyIntegrityError, "BUDGET_CHANGED_DURING_ANALYSIS"
                ):
                    analysis.main(root)
            self.assertEqual((root / "study/decision.json").read_bytes(), original)

    def test_decision_explanation_tracks_status(self):
        self.assertIn("Reject", analysis.decision_text("REJECTED", -1))
        self.assertNotIn("cash was superior", analysis.decision_text("REJECTED", 1))
        self.assertIn(
            "insufficient", analysis.decision_text("INSUFFICIENT_EVIDENCE", 1)
        )
        self.assertIn(
            "passed", analysis.decision_text("RESEARCH_ACCEPTED_SYNTHETIC_ONLY", 1)
        )
        self.assertEqual(
            analysis.decide(-1, -0.01, 0.1, True, True, True, True), "REJECTED"
        )
        self.assertEqual(
            analysis.decide(1, 0.01, 0.1, False, True, True, True),
            "INSUFFICIENT_EVIDENCE",
        )


if __name__ == "__main__":
    unittest.main()
