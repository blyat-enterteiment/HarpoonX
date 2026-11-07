"""Causality, units and acceptance boundaries for the new registered continuation."""

from __future__ import annotations

import copy
import json
import math
import tempfile
import unittest
from pathlib import Path

from run_modulation10 import choose_final_variants, claim_stage, validate_contract

from harpoon_quant.modulation9 import market
from harpoon_quant.modulation9 import make_protocol as old_protocol
from harpoon_quant.modulation10 import (
    MOMENTUM_RULES,
    daily_panel,
    make_protocol,
    momentum_feature,
    nominations,
)


class ProtocolTests(unittest.TestCase):
    def test_exact_catalogue_and_budgets(self) -> None:
        p = make_protocol()
        self.assertEqual(len(p["variants"]), 23)
        self.assertEqual(sum(v["role"] == "candidate" for v in p["variants"]), 18)
        self.assertEqual(len(set(v["id"] for v in p["variants"])), 23)
        self.assertEqual(p["budget"]["development_policy_cost_world_seed_accounts"], 1840)
        self.assertEqual(p["budget"]["final_policy_cost_world_seed_accounts"], 3200)
        validate_contract(p)

    def test_inherited_economic_assumptions_equal(self) -> None:
        old, new = old_protocol(), make_protocol()
        for key in ("generator", "scenarios", "limits"):
            self.assertEqual(new[key], old[key])
        for key, value in old["gates"].items():
            self.assertEqual(new["gates"][key], value)

    def test_generator_law_unchanged_for_identical_seed(self) -> None:
        old, new = old_protocol(), make_protocol()
        for p in (old, new):
            p["generator"]["warmup_sessions"] = 2
            p["generator"]["evaluation_sessions"] = 1
            p["generator"]["buffer_sessions"] = 1
        self.assertEqual(market(old, 910710, "NULL", "fixture"), market(new, 910710, "NULL", "fixture"))

    def test_risk_relaxation_is_rejected(self) -> None:
        p = make_protocol()
        p["limits"]["grossFraction"] = .13
        with self.assertRaisesRegex(ValueError, "INHERITED_CONTRACT"):
            validate_contract(p)

    def test_cost_reduction_is_rejected(self) -> None:
        p = make_protocol()
        p["scenarios"]["NOMINAL"]["external_cost_usd_per_calendar_day"] = .9
        with self.assertRaisesRegex(ValueError, "INHERITED_CONTRACT"):
            validate_contract(p)

    def test_drift_boost_is_rejected(self) -> None:
        p = make_protocol()
        p["generator"]["weak_drift_per_bar"] *= 2
        with self.assertRaisesRegex(ValueError, "INHERITED_CONTRACT"):
            validate_contract(p)

    def test_hurdle_relaxation_is_rejected(self) -> None:
        p = make_protocol()
        p["gates"]["nominal_edge_worlds_adjusted_lower"] = ">0"
        with self.assertRaisesRegex(ValueError, "ACCEPTANCE_GATE"):
            validate_contract(p)

    def test_reused_final_seed_is_rejected(self) -> None:
        p = make_protocol()
        p["stages"]["development"]["seeds"][0] = 940201
        with self.assertRaisesRegex(ValueError, "FRESH_DISJOINT"):
            validate_contract(p)

    def test_overlapping_new_stages_are_rejected(self) -> None:
        p = make_protocol()
        p["stages"]["development"]["seeds"][0] = p["stages"]["final"]["seeds"][0]
        with self.assertRaisesRegex(ValueError, "FRESH_DISJOINT"):
            validate_contract(p)

    def test_final_stays_sealed_after_negative_development(self) -> None:
        p = make_protocol()
        with self.assertRaisesRegex(ValueError, "FINAL_SEALED"):
            choose_final_variants(p, {"candidate_id": p["variants"][0]["id"],
                                     "development_score_positive": False,
                                     "candidate": {"score": -.00001, "risk_feasible": True}})

    def test_zero_is_not_sufficient_to_open_final(self) -> None:
        p = make_protocol()
        with self.assertRaisesRegex(ValueError, "FINAL_SEALED"):
            choose_final_variants(p, {"candidate_id": p["variants"][0]["id"],
                                     "development_score_positive": True,
                                     "candidate": {"score": 0., "risk_feasible": True}})

    def test_control_cannot_be_forged_as_new_candidate(self) -> None:
        with self.assertRaisesRegex(ValueError, "NEW_CANDIDATE"):
            choose_final_variants(make_protocol(), {"candidate_id": "QUALITY_NATIVE72_R0625",
                                  "development_score_positive": True,
                                  "candidate": {"score": .001, "risk_feasible": True}})

    def test_final_keeps_exactly_one_recipe_and_four_controls(self) -> None:
        p = make_protocol()
        candidate = p["variants"][0]["id"]
        got = choose_final_variants(p, {"candidate_id": candidate, "development_score_positive": True,
                                       "candidate": {"score": .00001, "risk_feasible": True}})
        self.assertEqual({v["id"] for v in got}, {candidate, *p["evaluation_control_ids"]})


class FeatureTests(unittest.TestCase):
    def prior(self) -> list[dict]:
        return [{"o": 100. + i, "c": (100. + i) * math.exp(.001 * (1 + i % 3)),
                 "h": (100. + i) * 1.01, "l": (100. + i) * .99,
                 "available_at": i * 1000, "date": f"session-{i:02d}"} for i in range(25)]

    def test_dimensionless_score_and_price_unit_stop(self) -> None:
        prior = self.prior()
        a = momentum_feature(prior, 8, 999999)
        scaled = [{**r, **{k: r[k] * 7 for k in ("o", "h", "l", "c")}} for r in prior]
        b = momentum_feature(scaled, 8, 999999)
        assert a is not None and b is not None
        self.assertAlmostEqual(a["score"], b["score"], places=10)
        self.assertAlmostEqual(b["stop_distance"], 7 * a["stop_distance"], places=10)

    def test_score_excludes_overnight_returns(self) -> None:
        prior = self.prior()
        a = momentum_feature(prior, 8, 999999)
        shifted = [{**r, **{k: r[k] * (1 + i / 20) for k in ("o", "h", "l", "c")}}
                   for i, r in enumerate(prior)]
        b = momentum_feature(shifted, 8, 999999)
        assert a is not None and b is not None
        self.assertAlmostEqual(a["score"], b["score"], places=10)
        self.assertNotAlmostEqual(a["stop_distance"], b["stop_distance"])

    def test_late_history_is_not_visible(self) -> None:
        prior = self.prior()
        prior[-1]["available_at"] = 1000001
        with self.assertRaisesRegex(ValueError, "AVAILABILITY"):
            momentum_feature(prior, 3, 1000000)

    def test_degenerate_dispersion_abstains(self) -> None:
        prior = self.prior()
        for row in prior:
            row["c"] = row["o"]
        self.assertIsNone(momentum_feature(prior, 8, 999999))

    def test_insufficient_stop_history_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "HISTORY"):
            momentum_feature(self.prior()[:20], 3, 999999)


class PrefixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.protocol = make_protocol()
        cls.protocol["generator"]["evaluation_sessions"] = 3
        cls.data = market(cls.protocol, 910711, "NULL", "fixture")
        # Engineered feature fixture, never used for statistical market outcomes.
        for series in cls.data["series"]:
            if series["symbol"] not in ("SYNA", "SYNB"):
                continue
            direction = 1 if series["symbol"] == "SYNA" else -1
            for i in range(40, len(cls.data["sessions"])):
                start = 100 * math.exp(.004 * (i - 40))
                drift = direction * (.002 + .0004 * (i % 3))
                for k, bar in enumerate(series["bars"][i * 78:(i + 1) * 78]):
                    opened, closed = start * math.exp(drift * k / 78), start * math.exp(drift * (k + 1) / 78)
                    bar.update({"o": opened, "c": closed, "h": max(opened, closed) * 1.0001,
                                "l": min(opened, closed) * .9999})

    def test_one_nomination_per_rule_session_and_causal_schedule(self) -> None:
        result = nominations(self.data, self.protocol)
        for name in MOMENTUM_RULES:
            self.assertEqual(len(result[name]), 3)
            self.assertEqual(len({s["at"] for s in result[name]}), 3)
            for signal in result[name]:
                self.assertEqual(signal["symbol"], "SYNA")
                self.assertEqual(signal["plannedEntryAt"] - signal["at"], 299000)
                self.assertLessEqual(signal["sourceAvailableAt"], signal["at"])
                self.assertGreater(signal["stopDistance"], 0)

    def test_future_prices_and_volumes_cannot_change_current_decision(self) -> None:
        baseline = nominations(self.data, self.protocol)
        changed = copy.deepcopy(self.data)
        cutoff = self.data["sessions"][50]["open"] + 301000
        for series in changed["series"]:
            for bar in series["bars"]:
                if bar["availableAt"] > cutoff:
                    for key in ("o", "h", "l", "c", "v"):
                        bar[key] *= 2
        after = nominations(changed, self.protocol)
        for name in MOMENTUM_RULES:
            self.assertEqual([s for s in baseline[name] if s["at"] <= cutoff],
                             [s for s in after[name] if s["at"] <= cutoff])

    def test_world_labels_are_not_features(self) -> None:
        changed = copy.deepcopy(self.data)
        changed["world"] = "UNOBSERVABLE_DIAGNOSTIC_LABEL"
        changed["latent_regime"] = [-1, -1, -1]
        self.assertEqual(nominations(changed, self.protocol), nominations(self.data, self.protocol))

    def test_bad_daily_grid_fails_closed(self) -> None:
        changed = copy.deepcopy(self.data)
        changed["series"][0]["bars"].pop()
        with self.assertRaisesRegex(ValueError, "COMPLETE_SESSION_GRID"):
            daily_panel(changed)


class StageClaimTests(unittest.TestCase):
    def test_repeat_stage_different_output_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reg = {"protocol_sha256": "a" * 64, "maximum_account_executions": 5040}
            claim_stage("development", root / "a", 1840, reg, None, root / "claims")
            with self.assertRaises(FileExistsError):
                claim_stage("development", root / "b", 1840, reg, None, root / "claims")
            stored = json.loads((root / "claims/development.json").read_text())
            self.assertEqual(stored["budget_charged_accounts"], 1840)
            self.assertFalse(stored["automatic_retry_allowed"])

    def test_full_budget_allows_each_stage_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reg = {"protocol_sha256": "a" * 64, "maximum_account_executions": 5040}
            claim_stage("development", root / "a", 1840, reg, None, root)
            claim_stage("final", root / "b", 3200, reg, "selection", root)
            self.assertEqual(sum(json.loads(p.read_text())["budget_charged_accounts"]
                                 for p in root.glob("*.json")), 5040)

    def test_cumulative_budget_cannot_be_exceeded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reg = {"protocol_sha256": "a" * 64, "maximum_account_executions": 5040}
            claim_stage("development", root / "a", 1840, reg, None, root)
            with self.assertRaisesRegex(ValueError, "CUMULATIVE_EXECUTION_BUDGET"):
                claim_stage("final", root / "b", 3201, reg, "selection", root)
            self.assertFalse((root / "final.json").exists())

    def test_protocol_change_cannot_reuse_claim_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reg = {"protocol_sha256": "a" * 64, "maximum_account_executions": 5040}
            claim_stage("development", root / "a", 1840, reg, None, root)
            reg["protocol_sha256"] = "b" * 64
            with self.assertRaisesRegex(ValueError, "REGISTRY_PROTOCOL_MISMATCH"):
                claim_stage("final", root / "b", 3200, reg, "selection", root)


if __name__ == "__main__":
    unittest.main()
