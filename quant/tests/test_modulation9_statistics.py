"""Statistical/integrity fixtures only; these numbers are not trading evidence.

No generator, nomination, native account replay, or economic holdout is run.
The account fixtures contain two hand-authored accounting dates (Friday and
Monday), four charged calendar days, and two independent fixture identities.
They exercise semantic corruption even when file checksums are recomputed.
"""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
import math
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np

from harpoon_quant.modulation9 import canonical, digest, make_protocol

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import analyze_modulation9 as analysis  # noqa: E402
import run_modulation9 as runner  # noqa: E402

A = "CONFIRMED_PROTECT48_R1250"
B = "QUALITY_RUNNER72_R2500"
DUPLICATE = "CONFIRMED_NATIVE72_R2500"
CONTROLS = ("CURRENT", "SIMPLE", "CASH")
PERIODS = {"evaluation_start": "2025-01-03", "evaluation_end": "2025-01-06"}
CAPITAL, DAYS = 20_000.0, 4


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))


class AccountingFixture(unittest.TestCase):
    """Use a tiny temporary protocol; never alter the registered specification."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="modulation9-statistics-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.protocol_path = self.root / "research/modulation9/protocol.json"
        self.registration_path = self.root / "research/modulation9/registration.json"
        self.p = make_protocol()
        catalogue = {v["id"]: v for v in self.p["variants"]}
        self.p["variants"] = [catalogue[vid] for vid in (A, B, DUPLICATE, *CONTROLS)]
        self.p["generator"].update(
            warmup_sessions=0, evaluation_sessions=2, buffer_sessions=0,
            first_date=PERIODS["evaluation_start"],
        )
        self.p["stages"]["development"]["seeds"] = [101, 102]
        self.p["stages"]["final"]["seeds"] = [201, 202]
        self.p["budget"].update(
            development_policy_cost_world_seed_accounts=120,
            final_policy_cost_world_seed_accounts=80,
            supplemental_max_account_executions=200,
        )
        self.source = self.root / "fixture_source.py"
        self.source.write_text("# Explicit accounting fixture, never a market replay.\n")
        self.refresh_protocol()
        for module, name, value in (
            (analysis, "ROOT", self.root), (analysis, "PROTOCOL", self.protocol_path),
            (analysis, "REGISTRATION", self.registration_path),
            (runner, "ROOT", self.root), (runner, "PROTOCOL", self.protocol_path),
            (runner, "REGISTRATION", self.registration_path),
        ):
            guard = patch.object(module, name, value, create=True)
            guard.start()
            self.addCleanup(guard.stop)
        self.rates: dict[tuple[str, str, str], float] = {}
        self.output_number = 0

    def refresh_protocol(self) -> None:
        _write(self.protocol_path, self.p)
        self.registration = {
            "schema": "HARPOON_MODULATION9_REGISTRATION_1",
            "protocol_sha256": _sha(self.protocol_path),
            "preregistered_protocol_commit": "a" * 40,
            "sources_sha256": {"fixture_source.py": _sha(self.source)},
            "economic_measurements_before_registration": 0,
            "execution_allowed": False,
        }
        _write(self.registration_path, self.registration)

    def account(self, variant: dict[str, Any], world: str, seed: int,
                scenario: str) -> dict[str, Any]:
        """Two explicit closed campaign cash flows and their continuous curve."""
        vid = variant["id"]
        daily_cost = self.p["scenarios"][scenario]["external_cost_usd_per_calendar_day"]
        fixed = daily_cost * DAYS
        rates = {A: .0006, B: .0005, DUPLICATE: .0002,
                 "CURRENT": .0002, "SIMPLE": .0001}
        log_rate = None
        if vid != "CASH" and world in ("TREND", "WEAK"):
            log_rate = rates[vid] * (1.0 if scenario == "NOMINAL" else .5)
            log_rate += .00001 if seed % 2 else -.00001
        log_rate = self.rates.get((vid, world, scenario), log_rate)
        net = -fixed if log_rate is None else CAPITAL * math.expm1(log_rate * DAYS)
        trading = net + fixed
        profits = [] if abs(trading) < 1e-9 else [trading * .6, trading * .4]
        trades = []
        for index, profit in enumerate(profits):
            opened = 1735918200000 + index * 3 * 86_400_000
            fee = .02
            trades.append({
                "id": f"fixture:{vid}:{world}:{seed}:{scenario}:{index}",
                "symbol": "SYNA", "quantity": 1,
                "opened": opened, "closed": opened + 3_600_000,
                "terminal_known_at": opened + 3_600_000,
                "holding_deadline_at": opened + 3_600_000,
                "holding_hours": 1.0, "entry": 100.0, "risk_usd": 10.0,
                "net_usd": profit, "trading_net_usd": profit, "fees_usd": fee,
                "close_mark_peak_pnl_usd": max(0.0, profit),
                "giveback_usd": 0.0, "reason": "FIXTURE", "ambiguous_bars": 0,
                "exit_fills": [{"at": opened + 3_600_000,
                                "known_at": opened + 3_600_000,
                                "quantity": 1, "price": 100.0 + profit + fee,
                                "fee_usd": fee / 2, "reason": "FIXTURE"}],
            })
        first_equity = CAPITAL + (profits[0] if profits else 0.0) - daily_cost
        last_equity = CAPITAL + net
        curve = []
        previous = CAPITAL
        peak, drawdown = CAPITAL, 0.0
        for date, equity, cost in (
            (PERIODS["evaluation_start"], first_equity, daily_cost),
            (PERIODS["evaluation_end"], last_equity, 3 * daily_cost),
        ):
            curve.append({"date": date, "equity": equity,
                          "portfolio_log_return": math.log(equity / previous),
                          "portfolio_return": equity / previous - 1,
                          "fixed_costs_usd": cost})
            previous, peak = equity, max(peak, equity)
            drawdown = max(drawdown, 1 - equity / peak)
        total_log = math.log(last_equity / CAPITAL)
        best = max([0.0, *profits])
        fees = sum(t["fees_usd"] for t in trades)
        summary = {
            "net_pnl_usd": net, "final_equity": last_equity,
            "total_return": net / CAPITAL, "total_log_return": total_log,
            "mean_calendar_day_log_return": total_log / DAYS,
            "calendar_days": DAYS, "sessions": 2,
            "max_event_drawdown": max(drawdown, .01 if trades else 0.0),
            "max_session_drawdown": drawdown,
            "worst_session_return": min(x["portfolio_return"] for x in curve),
            "max_hold_hours": 1.0 if trades else 0.0,
            "max_signal_to_exit_hours": 1.0 if trades else 0.0,
            "closed_campaigns": len(trades), "candidate_signals": len(trades),
            "winning_campaigns": sum(t["net_usd"] > 0 for t in trades),
            "best_campaign_usd": best, "net_without_best_campaign_usd": net - best,
            "fixed_costs_usd": fixed, "fees_usd": fees,
            "explicit_costs_usd": fixed + fees,
            "price_pnl_after_spread_slippage_before_commissions_usd": trading + fees,
            "dividend_accrued_usd": 0.0, "dividend_receivable_usd": 0.0,
            "denied": 0, "no_fills": 0, "terminal_reconciled": True,
            "cash_reconciliation_error": 0.0, "native_reconciliation_error": 0.0,
            "max_trade_ledger_error": 0.0, "terminal_inventory_quantity": 0,
            "terminal_reservations": 0,
        }
        return {**variant, "scenario": scenario, "summary": summary,
                "terminal_reconciled": True, "curve": curve, "trades": trades,
                "event_risk": {"scope": "HAND_AUTHORED_ACCOUNTING_FIXTURE",
                    "observations": 2, "valuationObservations": 2,
                    "commitmentObservations": 0, "maximumReservedRiskUsd": 10.0,
                    "maximumReservedNotionalUsd": 100.0, "maximumReservedCashUsd": 101.0,
                    "maximumConservativeMarkedNotionalUsd": 101.0,
                    "maximumRiskFraction": .0005, "maximumGrossFraction": .0051,
                    "riskOverageObservations": 0, "grossOverageObservations": 0,
                    "cashDeficitObservations": 0, "firstRiskOverage": None,
                    "firstGrossOverage": None, "firstCashDeficit": None}}

    def write_stage(self, stage: str, selection: dict[str, Any] | None = None,
                    edit: Callable[[dict[str, Any], str, int], None] | None = None) -> Path:
        directory = self.root / stage
        directory.mkdir(exist_ok=True)
        variants = self.p["variants"]
        if stage == "final":
            assert selection is not None
            keep = {selection["candidate_id"], *CONTROLS}
            variants = [v for v in variants if v["id"] in keep]
        paths = []
        for world in self.p["generator"]["worlds"]:
            for seed in self.p["stages"][stage]["seeds"]:
                accounts = [self.account(v, world, seed, scenario)
                            for v in variants for scenario in self.p["scenarios"]]
                if edit:
                    for account in accounts:
                        edit(account, world, seed)
                data = {"schema": "HARPOON_MODULATION9_PATH_1", "stage": stage,
                        "world": world, "seed": seed, "calendar_days": DAYS,
                        "periods": PERIODS, "accounts": accounts,
                        "input_sha256": digest({"fixture": True, "world": world, "seed": seed}),
                        "signal_counts": {}, "origin": "SYNTHETIC", "execution_allowed": False}
                path = directory / f"{world}_{seed}.json.gz"
                path.write_bytes(gzip.compress(canonical(data), mtime=0))
                paths.append({"world": world, "seed": seed, "file": path.name,
                              "accounts": len(accounts), "sha256": _sha(path),
                              "economic_sha256": digest(data)})
        manifest = {"schema": "HARPOON_MODULATION9_STAGE_1", "stage": stage,
                    "protocol_sha256": _sha(self.protocol_path),
                    "registration_sha256": _sha(self.registration_path),
                    "selection_sha256": selection["selection_sha256"] if selection else None,
                    "paths": paths, "accounts": sum(x["accounts"] for x in paths),
                    "policy_ids": [v["id"] for v in variants], "execution_allowed": False}
        _write(directory / "manifest.json", manifest)
        return directory

    def corrupt_path(self, directory: Path, edit: Callable[[dict[str, Any]], None],
                     index: int = 0) -> None:
        manifest = json.loads((directory / "manifest.json").read_text())
        item = manifest["paths"][index]
        path = directory / item["file"]
        data = json.loads(gzip.decompress(path.read_bytes()))
        edit(data)
        path.write_bytes(gzip.compress(canonical(data), mtime=0))
        item.update(sha256=_sha(path), economic_sha256=digest(data))
        _write(directory / "manifest.json", manifest)

    def development(self) -> dict[str, Any]:
        directory = self.write_stage("development")
        self.output_number += 1
        self.selection_path = self.root / f"selection_{self.output_number}" / "selection.json"
        return analysis.develop(directory, self.selection_path.parent)

    def final_result(self, edit: Callable[[dict[str, Any], str, int], None] | None = None,
                     development: dict[str, Any] | None = None) -> dict[str, Any]:
        developed = development if development is not None else self.development()
        directory = self.write_stage("final", developed["selection"], edit)
        self.output_number += 1
        return analysis.evaluate_final(directory, self.selection_path,
                                       self.root / f"final_report_{self.output_number}")

    def rehash_selection(self, edit: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        selected = json.loads(self.selection_path.read_text())
        edit(selected)
        selected.pop("selection_sha256", None)
        selected["selection_sha256"] = digest(selected)
        _write(self.selection_path, selected)
        return selected

    def assert_runner_refuses(self, selection: Path | None, stage: str = "final") -> None:
        # If validation lets anything through, the executor guard fails the test.
        with patch.object(runner.concurrent.futures, "ProcessPoolExecutor",
                          side_effect=AssertionError("NO_MARKET_REPLAY_IN_STATISTICS_TESTS")) as pool:
            with self.assertRaises(ValueError):
                runner.run(stage, self.root / "must_not_execute", 1, selection)
            pool.assert_not_called()


class StageIntegrityTests(AccountingFixture):
    def test_complete_hashed_fixture_roundtrip_and_calendar_log_units(self) -> None:
        directory = self.write_stage("development")
        manifest, rows = analysis.read_stage(directory, "development")
        self.assertEqual(manifest["accounts"], 120)
        self.assertEqual(len(rows), 120)
        for row in rows:
            total = math.fsum(x["portfolio_log_return"] for x in row["curve"])
            self.assertAlmostEqual(total, math.log(row["summary"]["final_equity"] / CAPITAL), places=13)
            self.assertAlmostEqual(total / 4, row["summary"]["mean_calendar_day_log_return"], places=13)
            self.assertEqual(row["summary"]["sessions"], 2)
            self.assertEqual(row["calendar_days"], 4)

    def test_wrong_stage_and_protocol_binding_are_rejected(self) -> None:
        directory = self.write_stage("development")
        with self.assertRaises(ValueError):
            analysis.read_stage(directory, "final")
        self.protocol_path.write_bytes(self.protocol_path.read_bytes() + b"\n")
        with self.assertRaises(ValueError):
            analysis.read_stage(directory, "development")

    def test_raw_path_hash_and_economic_hash_are_independent_bindings(self) -> None:
        directory = self.write_stage("development")
        manifest = json.loads((directory / "manifest.json").read_text())
        path = directory / manifest["paths"][0]["file"]
        path.write_bytes(path.read_bytes() + b"damaged")
        with self.assertRaises(ValueError):
            analysis.read_stage(directory, "development")
        directory = self.write_stage("development")
        manifest = json.loads((directory / "manifest.json").read_text())
        manifest["paths"][0]["economic_sha256"] = "0" * 64
        _write(directory / "manifest.json", manifest)
        with self.assertRaises(ValueError):
            analysis.read_stage(directory, "development")

    def test_duplicate_or_missing_path_cannot_be_hidden_by_account_count(self) -> None:
        for duplicate in (False, True):
            with self.subTest(duplicate=duplicate):
                directory = self.write_stage("development")
                manifest = json.loads((directory / "manifest.json").read_text())
                manifest["paths"].pop()
                if duplicate:
                    manifest["paths"].append(copy.deepcopy(manifest["paths"][0]))
                manifest["accounts"] = sum(item["accounts"] for item in manifest["paths"])
                _write(directory / "manifest.json", manifest)
                with self.assertRaises(ValueError):
                    analysis.read_stage(directory, "development")

    def test_missing_cost_or_duplicate_policy_is_rejected_with_valid_hashes(self) -> None:
        for field, value in (("scenario", "STRESS"), ("id", "CURRENT")):
            with self.subTest(field=field):
                directory = self.write_stage("development")
                self.corrupt_path(directory, lambda data: data["accounts"][0].update({field: value}))
                with self.assertRaises(ValueError):
                    analysis.read_stage(directory, "development")

    def test_account_fields_cannot_override_world_seed_stage_or_calendar(self) -> None:
        for key, value in (("world", "GAP"), ("seed", 999),
                           ("stage", "final"), ("calendar_days", 2)):
            with self.subTest(key=key):
                directory = self.write_stage("development")
                self.corrupt_path(directory, lambda data: data["accounts"][0].update({key: value}))
                with self.assertRaises(ValueError):
                    analysis.read_stage(directory, "development")

    def test_foreign_path_seed_or_manifest_identity_is_rejected(self) -> None:
        directory = self.write_stage("development")
        self.corrupt_path(directory, lambda data: data.update(seed=999))
        with self.assertRaises(ValueError):
            analysis.read_stage(directory, "development")

    def test_all_policies_and_costs_use_the_same_calendar(self) -> None:
        directory = self.write_stage("development")
        self.corrupt_path(directory, lambda data: data.update(calendar_days=2))
        with self.assertRaises(ValueError):
            analysis.read_stage(directory, "development")

    def test_curve_log_and_calendar_denominator_corruptions_fail_closed(self) -> None:
        edits = (
            lambda a: a["curve"][0].update(portfolio_log_return=.99),
            lambda a: a["summary"].update(mean_calendar_day_log_return=a["summary"]["total_log_return"] / 2),
            lambda a: a["summary"].update(total_log_return=.99),
            lambda a: a["curve"][0].update(portfolio_return=.99),
        )
        for index, edit in enumerate(edits):
            with self.subTest(corruption=index):
                directory = self.write_stage("development")
                self.corrupt_path(directory, lambda data: edit(data["accounts"][0]))
                with self.assertRaises(ValueError):
                    analysis.read_stage(directory, "development")

    def test_summary_cannot_invent_best_campaign_robustness_or_session_risk(self) -> None:
        for key, value in (("best_campaign_usd", 0),
                           ("net_without_best_campaign_usd", 999),
                           ("worst_session_return", -.001)):
            with self.subTest(key=key):
                directory = self.write_stage("development")
                self.corrupt_path(directory, lambda data: data["accounts"][0]["summary"].update({key: value}))
                with self.assertRaises(ValueError):
                    analysis.read_stage(directory, "development")

    def test_scenario_labels_cannot_swap_nominal_and_stress_accounts(self) -> None:
        directory = self.write_stage("development")
        def swap(data: dict[str, Any]) -> None:
            for account in data["accounts"]:
                account["scenario"] = "STRESS" if account["scenario"] == "NOMINAL" else "NOMINAL"
        self.corrupt_path(directory, swap)
        with self.assertRaises(ValueError):
            analysis.read_stage(directory, "development")

    def test_registration_checksum_is_bound_to_the_stage(self) -> None:
        directory = self.write_stage("development")
        self.registration["economic_measurements_before_registration"] = 1
        _write(self.registration_path, self.registration)
        with self.assertRaises(ValueError):
            analysis.read_stage(directory, "development")


class DevelopmentAndSelectionTests(AccountingFixture):
    def test_selection_uses_development_only_and_locks_exact_evidence(self) -> None:
        with patch.object(analysis, "read_stage", wraps=analysis.read_stage) as reader:
            result = self.development()
        self.assertTrue(all(call.args[1] == "development" for call in reader.call_args_list))
        selected = result["selection"]
        self.assertEqual(selected["candidate_id"], A)
        self.assertEqual(selected["candidate_id"], result["ranked_ids"][0])
        self.assertEqual(selected["development_manifest_sha256"], _sha(self.root / "development/manifest.json"))
        self.assertEqual(selected["selection_sha256"], digest({k: v for k, v in selected.items() if k != "selection_sha256"}))
        self.assertFalse(selected["final_results_read"])
        self.assertFalse(selected["execution_allowed"])
        self.assertFalse(selected["candidate"]["ranking_is_confirmatory_interval"])
        self.assertEqual(analysis.validate_selection(self.selection_path, _sha(self.protocol_path)), selected)

    def test_final_stage_cannot_be_used_to_select(self) -> None:
        developed = self.development()
        directory = self.write_stage("final", developed["selection"])
        with self.assertRaises(ValueError):
            analysis.develop(directory, self.root / "illegal_selection")

    def test_selection_maximizes_worst_edge_cost_score_not_nominal_average(self) -> None:
        for world in ("TREND", "WEAK"):
            self.rates[A, world, "NOMINAL"] = .005
            self.rates[A, world, "STRESS"] = .0001
        selected = self.development()["selection"]
        self.assertEqual(selected["candidate_id"], B)

    def test_current_duplicate_is_excluded_even_if_its_score_wins(self) -> None:
        for world in ("TREND", "WEAK"):
            for scenario in self.p["scenarios"]:
                for vid in (DUPLICATE, "CURRENT"):
                    self.rates[vid, world, scenario] = .002
        result = self.development()
        self.assertNotIn(DUPLICATE, result["ranked_ids"])
        self.assertNotIn(result["selection"]["candidate_id"], CONTROLS)

    def test_risk_infeasible_recipe_neither_wins_nor_dominates_feasible_frontier(self) -> None:
        directory = self.write_stage("development", edit=lambda a, w, s:
            a["summary"].update(max_signal_to_exit_hours=73) if a["id"] == A else None)
        result = analysis.develop(directory, self.root / "feasible_selection")
        candidates = {c["id"]: c for c in result["candidates"]}
        self.assertEqual(result["selection"]["candidate_id"], B)
        self.assertFalse(candidates[A]["risk_feasible"])
        self.assertFalse(candidates[A]["pareto"])
        self.assertTrue(candidates[B]["pareto"])

    def test_no_feasible_candidate_stops_before_final(self) -> None:
        directory = self.write_stage("development", edit=lambda a, w, s:
            a["summary"].update(max_signal_to_exit_hours=73) if a["id"] not in CONTROLS else None)
        with self.assertRaisesRegex(ValueError, "NO_RISK_FEASIBLE_RECIPE"):
            analysis.develop(directory, self.root / "no_selection")

    def test_negative_development_is_diagnostic_and_blocks_economic_promotion(self) -> None:
        for vid in (A, B):
            for world in ("TREND", "WEAK"):
                for scenario in self.p["scenarios"]:
                    self.rates[vid, world, scenario] = -.0001
        developed = self.development()
        self.assertFalse(developed["selection"]["development_score_positive"])
        self.rates.clear()
        final = self.final_result(development=developed)
        self.assertFalse(final["gates"]["development_score_positive"])
        self.assertFalse(final["economic_model_feasibility"])

    def test_selection_digest_tampering_is_refused_by_runner_before_execution(self) -> None:
        self.development()
        selected = json.loads(self.selection_path.read_text())
        selected["candidate_id"] = B
        _write(self.selection_path, selected)
        self.assert_runner_refuses(self.selection_path)

    def test_self_rehashed_wrong_winner_cannot_bypass_development_rule(self) -> None:
        result = self.development()
        alternative = next(c for c in result["candidates"] if c["id"] == B)
        self.rehash_selection(lambda s: s.update(candidate_id=B, candidate=alternative))
        self.assert_runner_refuses(self.selection_path)

    def test_self_rehashed_final_read_or_development_score_claim_is_refused(self) -> None:
        for key, value in (("final_results_read", True), ("development_score_positive", False)):
            with self.subTest(key=key):
                self.development()
                self.rehash_selection(lambda s: s.update({key: value}))
                self.assert_runner_refuses(self.selection_path)

    def test_altered_development_manifest_is_refused_by_runner(self) -> None:
        self.development()
        path = self.root / "development/manifest.json"
        path.write_bytes(path.read_bytes() + b"\n")
        self.assert_runner_refuses(self.selection_path)

    def test_runner_requires_selection_only_in_final(self) -> None:
        self.assert_runner_refuses(None)
        self.development()
        self.assert_runner_refuses(self.selection_path, "development")

    def test_final_analyzer_rechecks_selection_body_and_final_manifest_binding(self) -> None:
        developed = self.development()
        directory = self.write_stage("final", developed["selection"])
        selected = json.loads(self.selection_path.read_text())
        selected["candidate"]["score"] += 1
        _write(self.selection_path, selected)
        with self.assertRaises(ValueError):
            analysis.evaluate_final(directory, self.selection_path, self.root / "bad_final")


class BootstrapContracts(unittest.TestCase):
    def test_bonferroni_40_endpoints_20000_replicates_and_paired_resampling(self) -> None:
        cfg = make_protocol()["statistics"]
        self.assertEqual(cfg["final_endpoints"], 40)
        self.assertEqual(cfg["bootstrap_replicates"], 20_000)
        base = np.array([-.0003, -.0001, .0001, .0003])
        offsets = np.arange(40) * .00001
        matrix = base[:, None] + offsets
        result = analysis.adjusted_bounds(matrix, cfg)
        self.assertAlmostEqual(result["per_endpoint_alpha"], .05 / 40)
        self.assertEqual(result["approx_tail_replicates"], 25)
        self.assertEqual(result["independent_seeds"], 4)
        self.assertEqual(result["nominal_family_confidence"], .95)
        # The extreme four-equal resamples each have mass 1/256 > .00125.
        np.testing.assert_allclose(result["lower"], offsets - .0003, atol=1e-15)
        np.testing.assert_allclose(result["upper"], offsets + .0003, atol=1e-15)
        np.testing.assert_allclose(result["mean"], offsets, atol=1e-15)
        self.assertEqual(result, analysis.adjusted_bounds(matrix, cfg))
        self.assertIn("approximate", result["method"])

    def test_bad_dimensions_nonfinite_and_empty_matrices_are_rejected(self) -> None:
        cfg = make_protocol()["statistics"]
        for matrix in (np.zeros(40), np.zeros((4, 39)), np.empty((0, 40)),
                       np.full((4, 40), np.nan), np.full((4, 40), np.inf)):
            with self.subTest(shape=matrix.shape), self.assertRaises(ValueError):
                analysis.adjusted_bounds(matrix, cfg)


class FinalGateTests(AccountingFixture):
    def test_good_small_fixture_does_not_pass_64_path_gate_or_authorize_execution(self) -> None:
        result = self.final_result()
        self.assertFalse(result["gates"]["complete_64_final_paths_per_world_cost"])
        self.assertTrue(result["gates"]["nominal_edge_absolute_lower_above_1bp_daily"])
        self.assertTrue(result["gates"]["stress_edge_absolute_lower_positive"])
        self.assertTrue(result["gates"]["paired_edge_improvement_over_all_controls"])
        self.assertFalse(result["economic_model_feasibility"])
        self.assertFalse(result["conditional_n9s_accepted"])
        self.assertFalse(result["real_profitability_accredited"])
        self.assertFalse(result["level9_real_accredited"])
        self.assertFalse(result["execution_allowed"])
        self.assertEqual(result["verdict"], "NO_GO")

    def test_final_endpoint_matrix_pairs_same_seeds_worlds_and_costs(self) -> None:
        developed = self.development()
        directory = self.write_stage("final", developed["selection"])
        manifest, rows = analysis.read_stage(directory, "final")
        # Reversing serialized accounts must not change identity-based pairing.
        for index in range(len(manifest["paths"])):
            self.corrupt_path(directory, lambda data: data["accounts"].reverse(), index)
        with patch.object(analysis, "adjusted_bounds", wraps=analysis.adjusted_bounds) as bound:
            analysis.evaluate_final(directory, self.selection_path, self.root / "paired_final")
        matrix = bound.call_args.args[0]
        self.assertEqual(matrix.shape, (2, 40))
        column = 0
        for world in self.p["generator"]["worlds"]:
            for scenario in self.p["scenarios"]:
                for control in ("ABSOLUTE", *CONTROLS):
                    expected = []
                    for seed in self.p["stages"]["final"]["seeds"]:
                        candidate = next(r for r in rows if (r["id"], r["world"], r["scenario"], r["seed"]) == (A, world, scenario, seed))
                        value = candidate["summary"]["mean_calendar_day_log_return"]
                        if control != "ABSOLUTE":
                            baseline = next(r for r in rows if (r["id"], r["world"], r["scenario"], r["seed"]) == (control, world, scenario, seed))
                            value -= baseline["summary"]["mean_calendar_day_log_return"]
                        expected.append(value)
                    np.testing.assert_allclose(matrix[:, column], expected, rtol=0, atol=1e-15)
                    column += 1

    def test_final_control_seed_override_cannot_create_false_paired_advantage(self) -> None:
        developed = self.development()
        directory = self.write_stage("final", developed["selection"])
        self.corrupt_path(directory, lambda data: next(a for a in data["accounts"] if a["id"] == "CASH").update(seed=999))
        with self.assertRaises(ValueError):
            analysis.evaluate_final(directory, self.selection_path, self.root / "unpaired_final")

    def test_profitable_fixture_cannot_override_observed_drawdown_or_holding_breach(self) -> None:
        for key, value in (("max_event_drawdown", .08001), ("max_signal_to_exit_hours", 72.01)):
            with self.subTest(key=key):
                result = self.final_result(edit=lambda a, w, s:
                    a["summary"].update({key: value}) if a["id"] == A else None)
                self.assertFalse(result["gates"]["observed_risk_holding_and_reconciliation"])
                self.assertGreater(result["observed_candidate_risk_violations"], 0)
                self.assertFalse(result["economic_model_feasibility"])

    def test_positive_profit_from_one_best_campaign_does_not_pass_removal_gate(self) -> None:
        developed = self.development()
        def concentrate(account: dict[str, Any], world: str, seed: int) -> None:
            if account["id"] != A or world not in ("TREND", "WEAK"):
                return
            total = sum(t["net_usd"] for t in account["trades"])
            account["trades"][0]["net_usd"] = total
            account["trades"][1]["net_usd"] = 0.0
            account["summary"].update(best_campaign_usd=total,
                net_without_best_campaign_usd=-account["summary"]["fixed_costs_usd"])
        result = self.final_result(edit=concentrate, development=developed)
        self.assertFalse(result["gates"]["edge_profit_survives_removing_each_best_campaign"])
        self.assertFalse(result["economic_model_feasibility"])

    def test_null_cash_advantage_blocks_even_when_absolute_return_is_negative(self) -> None:
        developed = self.development()
        for scenario in self.p["scenarios"]:
            self.rates[A, "NULL", scenario] = math.log((CAPITAL - 1) / CAPITAL) / DAYS
        result = self.final_result(development=developed)
        for scenario in self.p["scenarios"]:
            self.assertLess(result["endpoints"][f"NULL:{scenario}:ABSOLUTE"]["lower"], 0)
            self.assertGreater(result["endpoints"][f"NULL:{scenario}:CASH"]["lower"], 0)
        self.assertFalse(result["gates"]["null_has_no_positive_adjusted_absolute_or_cash_relative_lower"])

    def test_tail_floor_uses_terminal_return_fraction_and_same_cost_cash(self) -> None:
        developed = self.development()
        # A loss of USD120 beyond stressed cash is 0.6%, not 0.6% per day.
        stress_cost = self.p["scenarios"]["STRESS"]["external_cost_usd_per_calendar_day"] * DAYS
        self.rates[A, "GAP", "STRESS"] = math.log((CAPITAL - stress_cost - 120) / CAPITAL) / DAYS
        result = self.final_result(development=developed)
        difference = result["groups"][f"{A}:GAP:STRESS"]["mean_return"] - result["groups"]["CASH:GAP:STRESS"]["mean_return"]
        self.assertAlmostEqual(difference, -.006, places=12)
        self.assertFalse(result["gates"]["tail_world_cost_relative_terminal_loss_within_half_pct"])

    def test_empty_risk_group_and_individual_risk_breaches_fail(self) -> None:
        self.assertFalse(analysis.risk_feasible([]))
        row = self.account(self.p["variants"][0], "TREND", 201, "NOMINAL")
        self.assertTrue(analysis.risk_feasible([row]))
        for key, value in (("max_event_drawdown", .081), ("worst_session_return", -.0201),
                           ("max_signal_to_exit_hours", 72.001), ("final_equity", 0.0)):
            broken = copy.deepcopy(row)
            broken["summary"][key] = value
            with self.subTest(key=key):
                self.assertFalse(analysis.risk_feasible([broken]))
        row["terminal_reconciled"] = False
        self.assertFalse(analysis.risk_feasible([row]))

    def test_nonfinite_account_statistics_are_rejected(self) -> None:
        row = self.account(self.p["variants"][0], "TREND", 201, "NOMINAL")
        for key in ("mean_calendar_day_log_return", "total_log_return", "max_event_drawdown",
                    "worst_session_return", "max_signal_to_exit_hours", "net_without_best_campaign_usd"):
            broken = copy.deepcopy(row)
            broken["summary"][key] = float("nan")
            with self.subTest(key=key), self.assertRaises(ValueError):
                analysis.validate_account(broken, DAYS, PERIODS)


class RegistrationTests(AccountingFixture):
    def test_registration_refuses_changed_source_and_changed_protocol(self) -> None:
        self.assertEqual(runner.verify_registration(), self.registration)
        self.source.write_text("# Changed after registration.\n")
        with self.assertRaises(ValueError):
            runner.verify_registration()
        self.refresh_protocol()
        self.protocol_path.write_bytes(self.protocol_path.read_bytes() + b"\n")
        with self.assertRaises(ValueError):
            runner.verify_registration()

    def test_registered_source_must_remain_within_registered_root(self) -> None:
        self.registration["sources_sha256"] = {"../outside.py": "0" * 64}
        _write(self.registration_path, self.registration)
        with self.assertRaises(ValueError):
            runner.verify_registration()


if __name__ == "__main__":
    unittest.main()
