"""Small explicit accounting fixtures; no generator, policy replay or holdout.

The production protocol is copied only into temporary directories, with two
fixture seeds and two accounting dates. The original MODULATION9 globals,
sources, manifests and economic outputs are never patched or modified.
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

from harpoon_quant.modulation9 import canonical, digest
from harpoon_quant.modulation10 import make_protocol

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import analyze_modulation9 as prior  # noqa: E402
import analyze_modulation10 as analysis  # noqa: E402

BEST = "MOM3_Z0_HOLD24_R1250"
OTHER = "MOM8_Z075_HOLD72_R2500"
DATES = ("2025-01-03", "2025-01-06")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="modulation10-statistics-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.protocol_path = self.root / "research/modulation10/protocol.json"
        self.registration_path = self.root / "research/modulation10/registration.json"
        self.p = make_protocol()
        self.p["generator"].update(warmup_sessions=0, evaluation_sessions=2,
                                    buffer_sessions=0, first_date=DATES[0])
        self.p["stages"]["development"]["seeds"] = [11, 12]
        self.p["stages"]["final"]["seeds"] = [21, 22]
        self.p["budget"].update(development_policy_cost_world_seed_accounts=460,
            final_policy_cost_world_seed_accounts=100, supplemental_max_account_executions=560)
        self.rates: dict[tuple[str, str, str], float] = {}
        self.outputs = 0
        self.refresh_contract()

    def refresh_contract(self) -> None:
        _write(self.protocol_path, self.p)
        previous_path = self.root / "research/modulation9/registration.json"
        _write(previous_path, {"sources_sha256": {}})
        self.registration = {"protocol_sha256": _sha(self.protocol_path),
                             "sources_sha256": {}, "previous_sources_sha256": {},
                             "previous_registration_sha256": _sha(previous_path),
                             "execution_allowed": False}
        _write(self.registration_path, self.registration)

    def account(self, variant: dict[str, Any], world: str, seed: int, scenario: str) -> dict[str, Any]:
        vid = variant["id"]
        cost = self.p["scenarios"][scenario]["external_cost_usd_per_calendar_day"]
        fixed = cost * 4
        rate = None
        if variant["entry"] != "CASH" and world in ("TREND", "WEAK"):
            base = {BEST: .0006, "CURRENT": .0002, "SIMPLE": .0001,
                    "M9_BEST": .00015, "QUALITY_NATIVE72_R0625": .00018,
                    "CONFIRMED_NATIVE_QUEUE72_R2500": .0002,
                    "QUALITY_NATIVE_QUEUE72_R0625": .00018}.get(vid, .0004)
            rate = base * (1 if scenario == "NOMINAL" else .5) + (.00001 if seed % 2 else -.00001)
        rate = self.rates.get((vid, world, scenario), rate)
        net = -fixed if rate is None else 20000 * math.expm1(rate * 4)
        total_trading = net + fixed
        profits = [] if abs(total_trading) < 1e-9 else [total_trading * .6, total_trading * .4]
        trades = [{"id": f"fixture:{vid}:{seed}:{i}", "net_usd": profit,
                   "holding_hours": 1, "fees_usd": .02} for i, profit in enumerate(profits)]
        previous = peak = 20000.
        maximum_dd = 0.
        curve = []
        for date, equity, charge in ((DATES[0], 20000 + (profits[0] if profits else 0) - cost, cost),
                                     (DATES[1], 20000 + net, cost * 3)):
            curve.append({"date": date, "equity": equity, "fixed_costs_usd": charge,
                          "portfolio_log_return": math.log(equity / previous),
                          "portfolio_return": equity / previous - 1})
            previous, peak = equity, max(peak, equity)
            maximum_dd = max(maximum_dd, 1 - equity / peak)
        best = max([0., *profits])
        summary = {"net_pnl_usd": net, "final_equity": previous,
            "total_log_return": math.log(previous / 20000),
            "mean_calendar_day_log_return": math.log(previous / 20000) / 4,
            "calendar_days": 4, "sessions": 2,
            "max_event_drawdown": max(maximum_dd, .01 if trades else 0),
            "max_session_drawdown": maximum_dd,
            "worst_session_return": min(p["portfolio_return"] for p in curve),
            "max_hold_hours": 1 if trades else 0, "max_signal_to_exit_hours": 1 if trades else 0,
            "closed_campaigns": len(trades), "best_campaign_usd": best,
            "net_without_best_campaign_usd": net - best,
            "fixed_costs_usd": fixed, "fees_usd": .02 * len(trades),
            "price_pnl_after_spread_slippage_before_commissions_usd": total_trading + .02 * len(trades),
            "terminal_reconciled": True, "cash_reconciliation_error": 0., "denied": 0, "no_fills": 0}
        return {**variant, "scenario": scenario, "summary": summary, "curve": curve,
                "trades": trades, "terminal_reconciled": True}

    def stage(self, name: str, selected: dict[str, Any] | None = None,
              edit: Callable[[dict[str, Any], str, int], None] | None = None,
              final_candidate: str | None = None) -> Path:
        directory = self.root / name
        directory.mkdir(exist_ok=True)
        variants = self.p["variants"]
        if name == "final":
            assert selected is not None
            keep = {final_candidate or selected["candidate_id"], *self.p["evaluation_control_ids"]}
            variants = [v for v in variants if v["id"] in keep]
        paths = []
        for world in self.p["generator"]["worlds"]:
            for seed in self.p["stages"][name]["seeds"]:
                accounts = [self.account(v, world, seed, cost) for v in variants for cost in self.p["scenarios"]]
                if edit:
                    for account in accounts:
                        edit(account, world, seed)
                data = {"stage": name, "world": world, "seed": seed, "calendar_days": 4,
                    "periods": {"evaluation_start": DATES[0], "evaluation_end": DATES[1]},
                    "accounts": accounts, "origin": "SYNTHETIC", "execution_allowed": False}
                path = directory / f"{world}_{seed}.json.gz"
                path.write_bytes(gzip.compress(canonical(data), mtime=0))
                paths.append({"world": world, "seed": seed, "file": path.name,
                    "accounts": len(accounts), "sha256": _sha(path), "economic_sha256": digest(data)})
        manifest = {"stage": name, "protocol_sha256": _sha(self.protocol_path),
            "registration_sha256": _sha(self.registration_path),
            "selection_sha256": selected["selection_sha256"] if selected else None,
            "paths": paths, "accounts": sum(p["accounts"] for p in paths),
            "policy_ids": [v["id"] for v in variants], "execution_allowed": False}
        _write(directory / "manifest.json", manifest)
        return directory

    def corrupt_path(self, directory: Path, edit: Callable[[dict[str, Any]], None]) -> None:
        manifest = json.loads((directory / "manifest.json").read_text())
        item = manifest["paths"][0]
        path = directory / item["file"]
        data = json.loads(gzip.decompress(path.read_bytes()))
        edit(data)
        path.write_bytes(gzip.compress(canonical(data), mtime=0))
        item.update(sha256=_sha(path), economic_sha256=digest(data))
        _write(directory / "manifest.json", manifest)

    def read(self, directory: Path, stage: str = "development") -> tuple[dict[str, Any], list[dict[str, Any]]]:
        return analysis.read_stage(directory, stage, self.protocol_path, self.registration_path)

    def develop(self, edit: Callable[[dict[str, Any], str, int], None] | None = None) -> dict[str, Any]:
        directory = self.stage("development", edit=edit)
        self.outputs += 1
        output = self.root / f"analysis_{self.outputs}"
        self.selection_path = output / "selection.json"
        return analysis.develop(directory, output, self.protocol_path, self.registration_path)

    def validate_selection(self) -> dict[str, Any]:
        return analysis.validate_selection(self.selection_path, _sha(self.protocol_path), self.protocol_path, self.registration_path)

    def rehash_selection(self, edit: Callable[[dict[str, Any]], None]) -> None:
        selected = json.loads(self.selection_path.read_text())
        edit(selected)
        selected.pop("selection_sha256")
        selected["selection_sha256"] = digest(selected)
        _write(self.selection_path, selected)


class RoundContractTests(Fixture):
    def test_registered_catalogue_budget_and_prospective_alpha(self) -> None:
        p = make_protocol()
        self.assertEqual(sum(v["role"] == "candidate" for v in p["variants"]), 18)
        self.assertEqual(len(p["variants"]), 23)
        self.assertEqual(p["budget"]["development_policy_cost_world_seed_accounts"], 1840)
        self.assertEqual(p["budget"]["final_policy_cost_world_seed_accounts"], 3200)
        self.assertEqual(p["statistics"]["final_endpoints"], 50)
        self.assertEqual(p["statistics"]["bootstrap_replicates"], 50000)
        self.assertEqual(p["statistics"]["one_sided_family_alpha"], .025)
        self.assertFalse(p["future_error_budget"]["historical_global_error_control_claimed"])
        self.assertFalse(set(p["stages"]["development"]["seeds"]) & set(p["stages"]["final"]["seeds"]))

    def test_roundtrip_and_pure_helpers_leave_prior_globals_and_sources_unchanged(self) -> None:
        before = (prior.ROOT, prior.PROTOCOL, _sha(Path(prior.__file__)))
        directory = self.stage("development")
        manifest, rows = self.read(directory)
        snapshot = canonical(rows)
        first = analysis.development_evidence(rows, self.p)
        second = analysis.development_evidence(rows, self.p)
        self.assertEqual(canonical(first), canonical(second))
        self.assertEqual(snapshot, canonical(rows))
        self.assertEqual(manifest["accounts"], 460)
        self.assertEqual(len(rows), 460)
        self.assertEqual(before, (prior.ROOT, prior.PROTOCOL, _sha(Path(prior.__file__))))
        self.assertIs(analysis.adjusted_bounds, prior.adjusted_bounds)
        self.assertIs(analysis.validate_account, prior.validate_account)

    def test_protocol_or_registration_binding_cannot_change(self) -> None:
        directory = self.stage("development")
        self.protocol_path.write_bytes(self.protocol_path.read_bytes() + b"\n")
        with self.assertRaises(ValueError):
            self.read(directory)
        self.refresh_contract()
        self.registration["note"] = "changed"
        _write(self.registration_path, self.registration)
        with self.assertRaises(ValueError):
            self.read(directory)

    def test_registered_source_checksum_is_verified(self) -> None:
        source = self.root / "fixture.py"
        source.write_text("# frozen\n")
        self.registration["sources_sha256"] = {"fixture.py": _sha(source)}
        _write(self.registration_path, self.registration)
        directory = self.stage("development")
        source.write_text("# changed\n")
        with self.assertRaises(ValueError):
            self.read(directory)
        self.refresh_contract()
        source.write_text("# previous frozen\n")
        previous_path = self.root / "research/modulation9/registration.json"
        old_sources = {"fixture.py": _sha(source)}
        _write(previous_path, {"sources_sha256": old_sources})
        self.registration.update(previous_sources_sha256=old_sources,
                                 previous_registration_sha256=_sha(previous_path))
        _write(self.registration_path, self.registration)
        directory = self.stage("development")
        self.read(directory)
        source.write_text("# previous changed\n")
        with self.assertRaises(ValueError):
            self.read(directory)

    def test_reducing_tail_resolution_or_changing_hurdles_is_rejected(self) -> None:
        for field in ("replicates", "hurdle"):
            with self.subTest(field=field):
                original = copy.deepcopy(self.p)
                if field == "replicates":
                    self.p["statistics"]["bootstrap_replicates"] = 20000
                else:
                    self.p["selection"]["hurdles"]["NOMINAL"] = 0
                self.refresh_contract()
                with self.assertRaises(ValueError):
                    analysis.load_contract(self.protocol_path, self.registration_path)
                self.p = original
                self.refresh_contract()


class StageIntegrityTests(Fixture):
    def test_duplicate_missing_or_foreign_seed_is_rejected_with_valid_checksums(self) -> None:
        for mutation in ("duplicate", "missing", "foreign"):
            with self.subTest(mutation=mutation):
                directory = self.stage("development")
                if mutation == "foreign":
                    self.corrupt_path(directory, lambda d: d.update(seed=999))
                else:
                    manifest = json.loads((directory / "manifest.json").read_text())
                    manifest["paths"].pop()
                    if mutation == "duplicate":
                        manifest["paths"].append(copy.deepcopy(manifest["paths"][0]))
                    manifest["accounts"] = sum(p["accounts"] for p in manifest["paths"])
                    _write(directory / "manifest.json", manifest)
                with self.assertRaises(ValueError):
                    self.read(directory)

    def test_reserved_context_recipe_and_cost_forgery_are_rejected(self) -> None:
        changes = (lambda a: a.update(seed=999), lambda a: a.update(risk=.1),
                   lambda a: a.update(scenario="STRESS"), lambda a: a.update(id="MISSING"))
        for index, change in enumerate(changes):
            with self.subTest(change=index):
                directory = self.stage("development")
                self.corrupt_path(directory, lambda d, change=change: change(d["accounts"][0]))
                with self.assertRaises(ValueError):
                    self.read(directory)

    def test_bytes_economic_digest_and_path_escape_are_rejected(self) -> None:
        for key in ("sha256", "economic_sha256", "file"):
            with self.subTest(key=key):
                directory = self.stage("development")
                manifest = json.loads((directory / "manifest.json").read_text())
                manifest["paths"][0][key] = "../outside.json.gz" if key == "file" else "0" * 64
                _write(directory / "manifest.json", manifest)
                with self.assertRaises(ValueError):
                    self.read(directory)

    def test_curve_log_and_calendar_semantics_are_enforced(self) -> None:
        edits = (lambda d: d.update(calendar_days=2),
                 lambda d: d["accounts"][0]["curve"][0].update(portfolio_log_return=.1),
                 lambda d: d["accounts"][0]["curve"][0].update(date="2025-01-04"))
        for index, edit in enumerate(edits):
            with self.subTest(edit=index):
                directory = self.stage("development")
                self.corrupt_path(directory, edit)
                with self.assertRaises(ValueError):
                    self.read(directory)


class SelectionTests(Fixture):
    def test_only_new_candidates_compete_and_hurdles_enter_the_score(self) -> None:
        for vid in ("CURRENT", "SIMPLE", "M9_BEST", "QUALITY_NATIVE72_R0625"):
            for world in ("TREND", "WEAK"):
                for scenario in self.p["scenarios"]:
                    self.rates[vid, world, scenario] = .002
        result = self.develop()
        self.assertEqual(result["candidate_count"], 18)
        self.assertEqual(result["selection"]["candidate_id"], BEST)
        self.assertFalse(set(result["ranked_ids"]) & set(self.p["control_ids"]))
        self.assertAlmostEqual(result["selection"]["candidate"]["score"], .0003 - 1.645 * .00001, places=12)
        self.assertTrue(result["final_allowed"])
        self.assertFalse(result["economic_improvement_accredited"])
        self.assertFalse(result["economic_model_feasibility"])
        self.assertEqual(self.validate_selection(), result["selection"])

    def test_positive_net_below_nominal_hurdle_keeps_reserved_final_unopened(self) -> None:
        for variant in self.p["variants"]:
            if variant["role"] == "candidate":
                for world in ("TREND", "WEAK"):
                    for scenario in self.p["scenarios"]:
                        self.rates[variant["id"], world, scenario] = .00005
        result = self.develop()
        self.assertIsNotNone(result["selection"]["candidate_id"])
        self.assertFalse(result["final_allowed"])
        with patch.object(analysis, "read_stage", wraps=analysis.read_stage) as reader:
            with self.assertRaisesRegex(ValueError, "FINAL_REQUIRES_POSITIVE_DEVELOPMENT"):
                analysis.evaluate_final(self.root / "UNOPENED_FINAL", self.selection_path,
                    self.root / "blocked", self.protocol_path, self.registration_path)
        self.assertTrue(all(call.args[1] == "development" for call in reader.call_args_list))
        self.assertFalse((self.root / "UNOPENED_FINAL").exists())
        self.assertFalse((self.root / "blocked").exists())

    def test_no_risk_feasible_candidate_is_preserved_without_inventing_a_winner(self) -> None:
        result = self.develop(edit=lambda a, w, s: a["summary"].update(max_event_drawdown=.09)
                              if a["role"] == "candidate" else None)
        self.assertIsNone(result["selection"]["candidate_id"])
        self.assertIsNone(result["selection"]["candidate"])
        self.assertEqual(result["ranked_ids"], [])
        self.assertFalse(result["final_allowed"])
        with self.assertRaisesRegex(ValueError, "FINAL_REQUIRES_POSITIVE_DEVELOPMENT"):
            self.validate_selection()

    def test_nonpositive_selection_cannot_self_rehash_its_permission_flag(self) -> None:
        for variant in self.p["variants"]:
            if variant["role"] == "candidate":
                for world in ("TREND", "WEAK"):
                    for scenario in self.p["scenarios"]:
                        self.rates[variant["id"], world, scenario] = -.0001
        self.develop()
        self.rehash_selection(lambda s: s.update(final_allowed=True, development_score_positive=True))
        with self.assertRaisesRegex(ValueError, "SELECTION_RULE_MISMATCH"):
            self.validate_selection()

    def test_forged_winner_or_final_read_claim_is_rejected_even_when_rehashed(self) -> None:
        for change in (lambda s: s.update(candidate_id=OTHER), lambda s: s.update(final_results_read=True)):
            self.develop()
            self.rehash_selection(change)
            with self.assertRaises(ValueError):
                self.validate_selection()

    def test_changed_development_receipt_and_selection_digest_are_rejected(self) -> None:
        self.develop()
        selected = json.loads(self.selection_path.read_text())
        selected["candidate"]["score"] += 1
        _write(self.selection_path, selected)
        with self.assertRaises(ValueError):
            self.validate_selection()
        self.develop()
        path = self.root / "development/manifest.json"
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaises(ValueError):
            self.validate_selection()

    def test_queue_ablation_pairs_are_descriptive_and_zero_for_identical_fixtures(self) -> None:
        result = self.develop()
        self.assertEqual(len(result["ablations"]), 20)
        for row in result["ablations"]:
            self.assertEqual(row["mean_paired_daily_log_delta"], 0)
            self.assertEqual(row["mean_paired_net_usd_delta"], 0)
            self.assertFalse(row["confirmatory_inference"])


class FinalStatisticsTests(Fixture):
    def test_fifty_endpoints_include_previous_best_and_keep_controls_paired(self) -> None:
        developed = self.develop()
        for world in ("TREND", "WEAK"):
            for scenario in self.p["scenarios"]:
                self.rates["M9_BEST", world, scenario] = .002
        directory = self.stage("final", developed["selection"])
        with patch.object(analysis, "adjusted_bounds", wraps=analysis.adjusted_bounds) as bounds:
            result = analysis.evaluate_final(directory, self.selection_path, self.root / "final_report",
                self.protocol_path, self.registration_path)
        self.assertEqual(bounds.call_args.args[0].shape, (2, 50))
        self.assertEqual(len(result["endpoints"]), 50)
        self.assertLess(result["endpoints"]["TREND:NOMINAL:M9_BEST"]["lower"], 0)
        self.assertFalse(result["gates"]["paired_edge_improvement_over_all_controls"])
        self.assertFalse(result["gates"]["complete_64_final_paths_per_world_cost"])
        self.assertEqual(result["statistics"]["per_endpoint_alpha"], .0005)
        self.assertEqual(result["statistics"]["approx_tail_replicates"], 25)
        self.assertFalse(result["conditional_n9s_accepted"])
        self.assertFalse(result["execution_allowed"])
        self.assertFalse(result["real_profitability_accredited"])

    def test_final_cannot_substitute_a_different_candidate(self) -> None:
        developed = self.develop()
        directory = self.stage("final", developed["selection"], final_candidate=OTHER)
        with self.assertRaises(ValueError):
            analysis.evaluate_final(directory, self.selection_path, self.root / "forged_final",
                self.protocol_path, self.registration_path)

    def test_final_control_seed_override_cannot_fake_paired_improvement(self) -> None:
        developed = self.develop()
        directory = self.stage("final", developed["selection"])
        self.corrupt_path(directory, lambda d: next(a for a in d["accounts"] if a["id"] == "M9_BEST").update(seed=999))
        with self.assertRaises(ValueError):
            analysis.evaluate_final(directory, self.selection_path, self.root / "wrong_seed_final",
                self.protocol_path, self.registration_path)

    def test_final_profit_does_not_override_risk_or_null_relative_bias(self) -> None:
        developed = self.develop()
        for scenario in self.p["scenarios"]:
            self.rates[BEST, "NULL", scenario] = -.00001
        directory = self.stage("final", developed["selection"], edit=lambda a, w, s:
            a["summary"].update(max_event_drawdown=.09) if a["id"] == BEST else None)
        result = analysis.evaluate_final(directory, self.selection_path, self.root / "blocked_gates",
            self.protocol_path, self.registration_path)
        self.assertFalse(result["gates"]["observed_risk_holding_and_reconciliation"])
        self.assertFalse(result["gates"]["null_has_no_positive_adjusted_absolute_or_cash_relative_lower"])
        self.assertFalse(result["economic_model_feasibility"])

    def test_bootstrap_fifty_columns_is_deterministic_and_jointly_paired(self) -> None:
        cfg = self.p["statistics"]
        base = np.array([-.0003, -.0001, .0001, .0003])
        offsets = np.arange(50) * .00001
        matrix = base[:, None] + offsets
        before = matrix.copy()
        first = analysis.adjusted_bounds(matrix, cfg)
        self.assertEqual(first, analysis.adjusted_bounds(matrix, cfg))
        np.testing.assert_array_equal(matrix, before)
        np.testing.assert_allclose(first["lower"], offsets - .0003, atol=1e-15)
        np.testing.assert_allclose(first["upper"], offsets + .0003, atol=1e-15)
        self.assertEqual(first["nominal_family_confidence"], .975)


if __name__ == "__main__":
    unittest.main()
