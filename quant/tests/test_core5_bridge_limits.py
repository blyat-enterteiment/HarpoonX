"""Synthetic regression of actual core bounds; no financial trials or orders."""
from __future__ import annotations

import copy
import json
import unittest

import test_fixed_predictor as fixed_fixture
from test_runtime_observations import runtime_fixture

from harpoon_quant.bridge import from_runtime, runtime_config


class CoreBridgeLimitsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixed_fixture.FixedPredictorTests.setUpClass()
        packet = fixed_fixture.FixedPredictorTests().packet()
        cls.raw = json.loads(packet["request_json"])
        cls.model = json.loads(packet["model_json"])

    def scenario(self, overrides, **state):
        raw = copy.deepcopy(self.raw)
        raw["config"].setdefault("quant", {}).setdefault("config", {}).update(overrides)
        raw.update(state)
        return from_runtime(raw, self.model)

    def test_explicit_core_caps_survive_wider_account_limits(self):
        config = runtime_fixture()["config"]
        tighter = {"max_positions": 1, "gross_fraction": 0.1, "asset_fraction": 0.02,
                   "factor_fraction": 0.03, "daily_loss_fraction": 0.001,
                   "drawdown_fraction": 0.002, "max_quote_age_seconds": 2}
        config["quant"] = {"config": tighter}
        actual = runtime_config(config)
        for key, value in tighter.items():
            with self.subTest(key=key):
                self.assertEqual(getattr(actual, key), value)

    def test_account_caps_survive_wider_core_limits(self):
        config = runtime_fixture()["config"]
        config["quant"] = {"config": {"max_positions": 8, "gross_fraction": 1,
            "asset_fraction": 0.5, "factor_fraction": 1, "daily_loss_fraction": 0.1,
            "drawdown_fraction": 0.2, "max_quote_age_seconds": 90}}
        actual = runtime_config(config)
        for field, account in (("max_positions", "maxPositions"), ("gross_fraction", "totalExposure"),
            ("asset_fraction", "assetExposure"), ("factor_fraction", "factorExposure"),
            ("daily_loss_fraction", "dailyLoss"), ("drawdown_fraction", "maxDrawdown")):
            with self.subTest(field=field):
                self.assertEqual(getattr(actual, field), config[account])
        self.assertEqual(actual.max_quote_age_seconds, config["quoteAgeMs"] / 1000)

    def test_omitted_core_caps_inherit_account_without_applying_default_caps(self):
        config = runtime_fixture()["config"]
        config.update(maxPositions=8, totalExposure=1.2, assetExposure=0.45, factorExposure=0.8,
                      dailyLoss=0.07, maxDrawdown=0.15, quoteAgeMs=30000, slippageBps=2)
        config["quant"] = {"config": {"scenarios": 64}}
        actual = runtime_config(config)
        self.assertEqual(actual.max_positions, 8)
        self.assertEqual(actual.gross_fraction, 1.2)
        self.assertEqual(actual.asset_fraction, 0.45)
        self.assertEqual(actual.factor_fraction, 0.8)
        self.assertEqual(actual.daily_loss_fraction, 0.07)
        self.assertEqual(actual.drawdown_fraction, 0.15)
        self.assertEqual(actual.max_quote_age_seconds, 30)
        self.assertEqual(actual.slippage_bps, 2)
        self.assertEqual(actual.scenarios, 64)

    def test_invalid_core_bound_is_not_hidden_by_account(self):
        for field, bad in (("max_positions", 0), ("max_positions", True), ("gross_fraction", -0.1),
            ("asset_fraction", float("nan")), ("factor_fraction", float("inf")),
            ("daily_loss_fraction", "0.01"), ("slippage_bps", -1), ("max_quote_age_seconds", -1)):
            with self.subTest(field=field, bad=bad):
                config = runtime_fixture()["config"]
                config["quant"] = {"config": {field: bad}}
                with self.assertRaises((ValueError, TypeError)):
                    runtime_config(config)

    def test_invalid_account_bound_is_not_hidden_by_core(self):
        for field, bad in (("maxPositions", 0), ("totalExposure", -1), ("dailyLoss", float("nan")),
                           ("quoteAgeMs", True), ("quoteAgeMs", "1000"), ("slippageBps", -1)):
            with self.subTest(field=field, bad=bad):
                config = runtime_fixture()["config"]
                config["quant"] = {"config": {"daily_loss_fraction": 0.001}}
                config[field] = bad
                with self.assertRaises((ValueError, TypeError)):
                    runtime_config(config)

    def test_slippage_uses_more_conservative_explicit_assumption(self):
        config = runtime_fixture()["config"]
        for local, expected in ((2, 10), (25, 25), (0, 10)):
            with self.subTest(local=local):
                config["quant"] = {"config": {"slippage_bps": local}}
                self.assertEqual(runtime_config(config).slippage_bps, expected)

    def test_observation_uses_resolved_quote_age_in_milliseconds(self):
        raw = runtime_fixture()
        raw["config"]["quant"] = {"config": {"max_quote_age_seconds": 2}}
        for quote_clock in ("at", "received"):
            with self.subTest(quote_clock=quote_clock):
                aged = copy.deepcopy(raw)
                aged["market"]["quotes"]["A"][quote_clock] -= 2001
                output = from_runtime(aged, None, observation_only=True)
                self.assertFalse(output["observations"])
                self.assertIn("OBSERVATION_STALE_OR_UNTIMED_QUOTE", output["rejected"]["observation-only|A"])
                self.assertFalse(output["execution_allowed"])
        raw["market"]["quotes"]["A"]["at"] -= 2000
        self.assertEqual(from_runtime(raw, None, observation_only=True)["status"], "OBSERVATION_CAPTURED")

    def test_strict_asset_gross_or_factor_cap_blocks_unaffordable_lot(self):
        self.assertTrue(self.scenario({})["selected"])
        for field in ("asset_fraction", "gross_fraction", "factor_fraction"):
            with self.subTest(field=field):
                output = self.scenario({field: 0.001})
                self.assertFalse(output["selected"])
                self.assertFalse(output["execution_allowed"])

    def test_stricter_daily_loss_boundary_reaches_allocator(self):
        output = self.scenario({"daily_loss_fraction": 0.001}, daily_pnl=-30)
        self.assertFalse(output["selected"])
        self.assertFalse(output["execution_allowed"])

    def test_stricter_drawdown_boundary_reaches_allocator(self):
        output = self.scenario({"drawdown_fraction": 0.001}, drawdown_fraction=0.002)
        self.assertFalse(output["selected"])
        self.assertFalse(output["execution_allowed"])

    def test_zero_loss_or_drawdown_limit_remains_a_halt(self):
        for field in ("daily_loss_fraction", "drawdown_fraction"):
            with self.subTest(field=field):
                output = self.scenario({field: 0})
                self.assertFalse(output["selected"])
                self.assertFalse(output["execution_allowed"])

    def test_resolution_does_not_mutate_input_or_other_core_parameters(self):
        config = runtime_fixture()["config"]
        config["quant"] = {"config": {"scenarios": 128, "cvar_fraction": 0.007,
                                      "uncertainty_z": 2.5, "max_positions": 2}}
        before = copy.deepcopy(config)
        result = runtime_config(config)
        self.assertEqual(config, before)
        self.assertEqual(result.scenarios, 128)
        self.assertEqual(result.cvar_fraction, 0.007)
        self.assertEqual(result.uncertainty_z, 2.5)


if __name__ == "__main__":
    unittest.main()
