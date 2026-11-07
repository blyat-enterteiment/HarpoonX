"""Independent causal/generator contracts, never profitability evidence.

These tests create market inputs and nominations only. They do not invoke the
native account replay, compute policy returns or inspect a final holdout.
"""

from __future__ import annotations

import copy
import math
import unittest
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import numpy as np

from harpoon_quant.modulation9 import (
    ENTRIES,
    EXITS,
    RISKS,
    SYMBOLS,
    WORLDS,
    _calendar,
    canonical,
    digest,
    make_protocol,
    market,
    nominations,
    payload,
    recipes,
)
from harpoon_quant.technical_swing import BAR, TechnicalSwing


def _small_protocol(*, warmup: int = 50, evaluation: int = 2) -> dict[str, Any]:
    """Only shorten test fixtures; the registered production manifest is intact."""
    protocol = make_protocol()
    protocol["generator"].update(
        warmup_sessions=warmup, evaluation_sessions=evaluation, buffer_sessions=0
    )
    return protocol


def _fixture() -> tuple[dict[str, Any], dict[str, Any]]:
    """A nonvacuous, fully available fixture that qualifies all four entries."""
    protocol = _small_protocol()
    cfg = protocol["generator"]
    sessions = _calendar(
        cfg["warmup_sessions"] + cfg["evaluation_sessions"], cfg["first_date"]
    )
    series = []
    for symbol_index, symbol in enumerate(SYMBOLS):
        bars = []
        for day, session in enumerate(sessions):
            base = (100.0 + symbol_index * 20.0) * math.exp(
                0.0015 * day + 0.000005 * day * day
            )
            prior_close = base
            for slot in range(78):
                op = close = base
                high, low, volume = base + 1.0, base - 1.0, 100.0
                if day >= cfg["warmup_sessions"]:
                    high, low = base + 0.4, base - 0.4
                    if symbol != SYMBOLS[2] and slot >= 6:
                        scale = 1.0 if symbol_index == 0 else 0.8
                        offsets = {
                            6: 0.15, 7: 0.28, 8: 0.44, 9: 0.52,
                            10: 0.58, 11: 0.64, 12: 0.55, 13: 0.62,
                            14: 0.65, 15: 0.68, 16: 0.75, 17: 0.82,
                        }
                        op = prior_close
                        close = base + scale * offsets.get(slot, 0.95)
                        high, low = max(op, close) + 0.02, min(op, close) - 0.02
                        if slot == 12:
                            low = base + 0.36
                        if slot in (10, 11):
                            volume = 150.0
                        elif slot in (16, 17):
                            volume = 140.0
                at = session["open"] + slot * BAR
                bars.append(
                    {
                        "t": at, "end": at + BAR, "availableAt": at + BAR + 1000,
                        "o": op, "h": high, "l": low, "c": close, "v": volume,
                    }
                )
                prior_close = close
        series.append({"symbol": symbol, "bars": bars})
    return {
        "schema": "HARPOON-ULTIMATE-DATA-1", "origin": "SYNTHETIC",
        "sessions": sessions, "series": series, "splitEvents": [],
    }, protocol


def _through(signals: dict[str, list[dict[str, Any]]], at: int) -> dict[str, Any]:
    return {name: [row for row in rows if row["at"] <= at] for name, rows in signals.items()}


def _on_day(signals: dict[str, list[dict[str, Any]]], opening: int) -> dict[str, Any]:
    return {
        name: [row for row in rows if opening <= row["at"] < opening + 78 * BAR]
        for name, rows in signals.items()
    }


def _replace_prior_closes(data: dict[str, Any], closes: list[float]) -> None:
    for series in data["series"][:2]:
        for day, close in enumerate(closes):
            for bar in series["bars"][day * 78:(day + 1) * 78]:
                bar.update(o=close, c=close, h=close + 1.0, l=close - 1.0)


def _reference_histogram(closes: list[float]) -> float:
    """Scalar recurrence independent of the production helper."""
    fast = slow = closes[0]
    signal = 0.0
    macd = 0.0
    for close in closes[1:]:
        fast += (close - fast) * (2.0 / 13.0)
        slow += (close - slow) * (2.0 / 27.0)
        macd = fast - slow
        signal += (macd - signal) * (2.0 / 10.0)
    return macd - signal


class _ZeroInnovationRng:
    """Deterministic quadrature point; no stochastic policy experiment."""

    def normal(self, loc: float = 0.0, scale: float = 1.0, size: Any = None) -> Any:
        return float(loc) if size is None else np.full(size, loc, dtype=float)

    def random(self, size: Any = None) -> Any:
        return 0.5 if size is None else np.full(size, 0.5, dtype=float)

    def uniform(self, low: float, high: float, size: Any = None) -> Any:
        midpoint = (low + high) / 2.0
        return midpoint if size is None else np.full(size, midpoint, dtype=float)

    def choice(self, values: Any, size: Any = None, p: Any = None) -> Any:
        chosen = 0.0 if 0.0 in values else float(values[0])
        return chosen if size is None else np.full(size, chosen, dtype=float)


class _SubstepRng(_ZeroInnovationRng):
    pattern = np.array([2.0, -3.0, 1.0, 2.0, -1.0, -2.0, 3.0, -1.0])

    def normal(self, loc: float = 0.0, scale: float = 1.0, size: Any = None) -> Any:
        if size == (78, 8, 3):
            return np.broadcast_to(self.pattern[None, :, None], size).copy()
        return super().normal(loc, scale, size)


class ModulationProtocolTests(unittest.TestCase):
    def test_catalogue_has_36_recipes_three_controls_and_native_risk_caps(self):
        protocol = make_protocol()
        catalogue = recipes()
        self.assertEqual(len(catalogue), 39)
        self.assertEqual(len({row["id"] for row in catalogue}), 39)
        expected = {(entry, exit_name, risk) for entry in ENTRIES for exit_name in EXITS for risk in RISKS}
        self.assertEqual(
            {(row["entry"], row["exit"], row["risk"]) for row in catalogue[:36]}, expected
        )
        self.assertEqual([row["id"] for row in catalogue[36:]], ["CURRENT", "SIMPLE", "CASH"])
        self.assertEqual(protocol["variants"], catalogue)
        limits = protocol["limits"]
        self.assertEqual(limits["capitalUsd"], 20_000)
        self.assertEqual(limits["grossFraction"], 0.12)
        self.assertEqual(limits["assetFraction"], 0.12)
        self.assertEqual(limits["openRiskFraction"], 0.0025)
        self.assertEqual(limits["dailyLoss"], 0.02)
        self.assertEqual(limits["maxDrawdown"], 0.08)
        for row in catalogue:
            self.assertGreater(row["risk"], 0)
            self.assertLessEqual(row["risk"], limits["riskFraction"])
        native = next(row for row in catalogue if row["id"] == "CONFIRMED_NATIVE72_R2500")
        current = next(row for row in catalogue if row["id"] == "CURRENT")
        self.assertEqual(
            {k: v for k, v in native.items() if k != "id"},
            {k: v for k, v in current.items() if k != "id"},
        )
        self.assertFalse(protocol["execution_allowed"])
        self.assertFalse(protocol["live_approved"])

    def test_stage_seed_separation_and_complete_account_budget(self):
        protocol = make_protocol()
        stages, budget = protocol["stages"], protocol["budget"]
        development, final = stages["development"], stages["final"]
        self.assertEqual(len(development["seeds"]), 8)
        self.assertEqual(len(final["seeds"]), 64)
        self.assertFalse(set(development["seeds"]) & set(final["seeds"]))
        self.assertEqual(len(set(development["seeds"])), len(development["seeds"]))
        self.assertEqual(len(set(final["seeds"])), len(final["seeds"]))
        development_accounts = len(protocol["variants"]) * len(development["seeds"]) * len(WORLDS) * len(protocol["scenarios"])
        final_accounts = (final["locked_candidates"] + len(final["controls"])) * len(final["seeds"]) * len(WORLDS) * len(protocol["scenarios"])
        self.assertEqual(development_accounts, budget["development_policy_cost_world_seed_accounts"])
        self.assertEqual(final_accounts, budget["final_policy_cost_world_seed_accounts"])
        self.assertEqual(development_accounts + final_accounts, budget["supplemental_max_account_executions"])
        self.assertEqual(budget["historical_reserved_plus_unincorporated"], 151)
        self.assertFalse(budget["historical_debt_reconciled"])
        self.assertEqual(protocol["statistics"]["final_endpoints"], 4 * len(WORLDS) * len(protocol["scenarios"]))

    def test_calendar_skips_weekends_with_explicit_fixed_utc_sessions(self):
        rows = _calendar(4, "2024-03-08")
        self.assertEqual([row["date"] for row in rows], ["2024-03-08", "2024-03-11", "2024-03-12", "2024-03-13"])
        for row in rows:
            opening = datetime.fromtimestamp(row["open"] / 1000, UTC)
            self.assertLess(opening.weekday(), 5)
            self.assertEqual((opening.hour, opening.minute), (14, 30))
            self.assertEqual(row["close"] - row["open"], 78 * BAR)
        self.assertEqual(rows[1]["open"] - rows[0]["open"], 72 * 60 * 60 * 1000)
        self.assertEqual(_calendar(1, "2024-03-09")[0]["date"], "2024-03-11")


class ModulationGeneratorTests(unittest.TestCase):
    def test_generator_determinism_provenance_and_no_input_mutation(self):
        protocol = _small_protocol(warmup=0)
        before = canonical(protocol)
        first = market(protocol, 82417, "NULL", "fixture")
        second = market(protocol, 82417, "NULL", "fixture")
        self.assertEqual(canonical(first), canonical(second))
        self.assertNotEqual(digest(first), digest(market(protocol, 82418, "NULL", "fixture")))
        self.assertEqual(canonical(protocol), before)
        expected = digest({"generator": protocol["generator"], "seed": 82417, "world": "NULL", "stage": "fixture"})
        self.assertEqual(first["provenance"]["files"][0]["sha256"], expected)
        self.assertEqual(first["origin"], "SYNTHETIC")
        for series in first["series"]:
            self.assertEqual(len(series["bars"]), 2 * 78)
            for index, bar in enumerate(series["bars"]):
                session, slot = divmod(index, 78)
                self.assertEqual(bar["t"], first["sessions"][session]["open"] + slot * BAR)
                self.assertEqual(bar["end"], bar["t"] + BAR)
                self.assertEqual(bar["availableAt"], bar["end"] + 1000)
                self.assertLessEqual(bar["l"], min(bar["o"], bar["c"]))
                self.assertGreaterEqual(bar["h"], max(bar["o"], bar["c"]))
                self.assertTrue(all(math.isfinite(bar[key]) and bar[key] > 0 for key in ("o", "h", "l", "c", "v")))
                if slot:
                    self.assertEqual(bar["o"], series["bars"][index - 1]["c"])

    def test_stage_and_world_validation_and_no_latent_labels_in_market_data(self):
        protocol = _small_protocol(warmup=0, evaluation=1)
        for world, stage in (("ORACLE", "fixture"), ("NULL", "UNREGISTERED")):
            with self.subTest(world=world, stage=stage), self.assertRaisesRegex(ValueError, "WORLD_OR_STAGE"):
                market(protocol, 82417, world, stage)
        forbidden = {"world", "world_id", "stage", "regime", "latent_regime", "latent_drift", "drift", "future_return", "future_price", "mature_label"}

        def inspect(value: Any) -> None:
            if isinstance(value, dict):
                self.assertFalse(forbidden.intersection(value))
                for child in value.values():
                    inspect(child)
            elif isinstance(value, list):
                for child in value:
                    inspect(child)

        for world in WORLDS:
            inspect(market(protocol, 82417, world, "fixture"))

    def test_null_normal_mixture_and_overnight_mgf_are_one(self):
        """Numerical quadrature verifies the law, not returns of a strategy."""
        protocol = make_protocol()
        cfg = protocol["generator"]
        self.assertEqual(cfg["intrabar_substeps"], 8)
        nodes, weights = np.polynomial.hermite.hermgauss(20)
        standard_normal_nodes = math.sqrt(2.0) * nodes
        normalized_weights = weights / math.sqrt(math.pi)
        for base in (*cfg["bar_sigma"], *cfg["overnight_sigma"]):
            for activity in (math.exp(-0.7), 1.0, math.exp(0.7)):
                compensated = []
                for mixture_scale in (1.0, 4.0):
                    sigma = base * activity * mixture_scale
                    single_substep = np.exp(-0.5 * sigma**2 / 8.0 + sigma / math.sqrt(8.0) * standard_normal_nodes)
                    moment = float(np.dot(normalized_weights, single_substep)) ** 8
                    self.assertAlmostEqual(moment, 1.0, places=13)
                    compensated.append(moment)
                self.assertAlmostEqual(0.996 * compensated[0] + 0.004 * compensated[1], 1.0, places=13)
        self.assertAlmostEqual(0.003 * 0.97 + 0.003 * 1.03 + 0.994, 1.0, places=15)

    def test_actual_null_generator_contains_intraday_and_overnight_compensation(self):
        protocol = _small_protocol(warmup=0)
        with patch("harpoon_quant.modulation9.np.random.default_rng", return_value=_ZeroInnovationRng()):
            data = market(protocol, 82417, "NULL", "fixture")
        for index, series in enumerate(data["series"]):
            sigma = protocol["generator"]["bar_sigma"][index]
            night_sigma = protocol["generator"]["overnight_sigma"][index]
            bars = series["bars"]
            self.assertAlmostEqual(bars[0]["o"] / (100.0, 150.0, 120.0)[index], math.exp(-0.5 * night_sigma**2), places=14)
            self.assertAlmostEqual(bars[78]["o"] / bars[77]["c"], math.exp(-0.5 * night_sigma**2), places=14)
            for bar in (bars[0], bars[77], bars[78]):
                self.assertAlmostEqual(bar["c"] / bar["o"], math.exp(-0.5 * sigma**2), places=13)
                self.assertEqual(bar["h"], bar["o"])
                self.assertEqual(bar["l"], bar["c"])

    def test_ohlc_extremes_reconstruct_from_same_eight_substeps(self):
        protocol = _small_protocol(warmup=0, evaluation=1)
        with patch("harpoon_quant.modulation9.np.random.default_rng", return_value=_SubstepRng()):
            data = market(protocol, 82417, "NULL", "fixture")
        loading = protocol["generator"]["correlation_loading"]
        for index, series in enumerate(data["series"]):
            bar = series["bars"][0]
            sigma = protocol["generator"]["bar_sigma"][index]
            innovations = math.sqrt(1.0 - loading**2) * _SubstepRng.pattern
            increments = -0.5 * sigma**2 / 8.0 + sigma / math.sqrt(8.0) * innovations
            path = bar["o"] * np.exp(np.cumsum(increments))
            self.assertAlmostEqual(bar["c"], float(path[-1]), places=11)
            self.assertAlmostEqual(bar["h"], max(bar["o"], float(np.max(path))), places=11)
            self.assertAlmostEqual(bar["l"], min(bar["o"], float(np.min(path))), places=11)


class ModulationNominationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data, self.protocol = _fixture()
        self.first = self.protocol["generator"]["warmup_sessions"]
        self.opening = self.data["sessions"][self.first]["open"]

    def test_exact_confirmed_and_simple_equivalence_to_native_technical_swing(self):
        before = canonical(self.data)
        result = nominations(self.data, self.protocol)
        native = TechnicalSwing(self.data, list(SYMBOLS[:2]), SYMBOLS[2])
        expected: dict[str, list[dict[str, Any]]] = {"CONFIRMED": [], "SIMPLE": []}
        for session in self.data["sessions"][self.first:]:
            at = session["open"] + 12 * BAR + 1000
            decision = native.decision(at)
            for entry in expected:
                row = decision[entry.lower()]
                if row is not None:
                    expected[entry].append({
                        "id": f"{entry}:{row['symbol']}:{at}", "symbol": row["symbol"],
                        "hypothesis": "CLOSED_CHANNEL", "direction": 1, "index": 0,
                        "at": at, "plannedEntryAt": decision["planned_entry_at"],
                        "stopDistance": row["stop_distance"], "regime": 0.4,
                        "metadata": {"technicalRule": entry, "roadmapHorizonHours": 72},
                    })
        for entry in expected:
            self.assertTrue(expected[entry], "Baseline equivalence must not be vacuous")
            self.assertEqual(result[entry], expected[entry])
        self.assertEqual(canonical(self.data), before)

    def test_future_intraday_and_daily_prices_cannot_change_prefix_nominations(self):
        original = nominations(self.data, self.protocol)
        first_day = _on_day(original, self.opening)
        self.assertTrue(all(first_day.values()), "Fixture must exercise each entry")
        for minutes in (60, 90):
            cutoff = self.opening + minutes * 60_000 + 1000
            changed = copy.deepcopy(self.data)
            touched = 0
            for series in changed["series"]:
                for index, bar in enumerate(series["bars"]):
                    # Includes the currently incomplete bar and all later days;
                    # all observations already available at cutoff are intact.
                    if bar["end"] > cutoff:
                        multiplier = 25.0 if index % 2 else 0.04
                        op, close = bar["o"] * multiplier, bar["c"] * multiplier
                        bar.update(o=op, c=close, h=max(op, close) * 1.1,
                                   l=min(op, close) * 0.9, v=1e8)
                        touched += 1
            self.assertGreater(touched, 0)
            with self.subTest(decision_minutes=minutes):
                self.assertEqual(_through(nominations(changed, self.protocol), cutoff), _through(original, cutoff))

    def test_quality_uses_prior_30_day_return_and_prior_50_close_macd(self):
        prior = [300.0 - 200.0 * day / 18.0 for day in range(19)] + [100.0 + 0.5 * day for day in range(31)]
        self.assertGreater(prior[-1] / prior[-31], 1.0)
        self.assertLess(prior[-1] / prior[0], 1.0)
        self.assertGreater(_reference_histogram(prior), 0.0)
        _replace_prior_closes(self.data, prior)
        result = _on_day(nominations(self.data, self.protocol), self.opening)
        self.assertTrue(result["QUALITY"])
        self.assertTrue(result["RETEST"])

    def test_positive_prior_30_day_return_does_not_override_negative_macd(self):
        prior = [100.0 + day for day in range(45)] + [143.0, 142.0, 141.0, 140.0, 139.0]
        self.assertGreater(prior[-1] / prior[-31], 1.0)
        self.assertLess(_reference_histogram(prior), 0.0)
        _replace_prior_closes(self.data, prior)
        result = _on_day(nominations(self.data, self.protocol), self.opening)
        self.assertTrue(result["CONFIRMED"])
        self.assertFalse(result["QUALITY"])
        self.assertTrue(result["RETEST"], "RETEST has no MACD condition")

    def test_quality_and_retest_refuse_negative_prior_30_day_trend(self):
        _replace_prior_closes(self.data, [200.0 - day for day in range(50)])
        result = _on_day(nominations(self.data, self.protocol), self.opening)
        self.assertTrue(result["CONFIRMED"])
        self.assertFalse(result["QUALITY"])
        self.assertFalse(result["RETEST"])

    def test_history_older_than_50_sessions_cannot_change_current_features(self):
        second_open = self.data["sessions"][self.first + 1]["open"]
        original = _on_day(nominations(self.data, self.protocol), second_open)
        self.assertTrue(original["QUALITY"])
        for series in self.data["series"]:
            for bar in series["bars"][:78]:
                bar.update(o=100_000.0, c=100_000.0, h=100_001.0, l=99_999.0, v=1e8)
        self.assertEqual(_on_day(nominations(self.data, self.protocol), second_open), original)

    def test_quality_volume_upper_bound_does_not_change_confirmed_control(self):
        for series in self.data["series"][:2]:
            for slot in (10, 11):
                series["bars"][self.first * 78 + slot]["v"] = 400.0
        result = _on_day(nominations(self.data, self.protocol), self.opening)
        self.assertTrue(result["CONFIRMED"])
        self.assertFalse(result["QUALITY"])
        self.assertTrue(result["RETEST"])

    def test_retest_uses_90_minute_decision_and_its_own_volume_slot(self):
        for series in self.data["series"][:2]:
            for day in range(self.first):
                for slot in (10, 11):
                    series["bars"][day * 78 + slot]["v"] = 1e6
        result = _on_day(nominations(self.data, self.protocol), self.opening)
        self.assertFalse(result["CONFIRMED"])
        self.assertTrue(result["RETEST"])
        row = result["RETEST"][0]
        self.assertEqual(row["at"], self.opening + 18 * BAR + 1000)
        self.assertEqual(row["plannedEntryAt"], self.opening + 19 * BAR)
        self.assertGreater(row["plannedEntryAt"], row["at"])

    def test_retest_requires_a_breakout_before_the_revisit(self):
        for series in self.data["series"][:2]:
            base = series["bars"][self.first * 78]["o"]
            for slot in range(6, 12):
                series["bars"][self.first * 78 + slot].update(
                    o=base + 0.2, c=base + 0.3, h=base + 0.35, l=base + 0.1
                )
        self.assertFalse(_on_day(nominations(self.data, self.protocol), self.opening)["RETEST"])

    def test_retest_rejects_deep_retrace_even_when_opening_range_floor_holds(self):
        for series in self.data["series"][:2]:
            base = series["bars"][self.first * 78]["o"]
            # Prior ATR=2; level=base+0.4; this is 0.35 below the
            # level, beyond 0.15 ATR, but still above floor=base-0.4.
            series["bars"][self.first * 78 + 12]["l"] = base + 0.05
        result = _on_day(nominations(self.data, self.protocol), self.opening)
        self.assertTrue(result["CONFIRMED"])
        self.assertFalse(result["RETEST"])

    def test_unavailable_prior_daily_features_fail_closed(self):
        prior_last = self.data["series"][0]["bars"][self.first * 78 - 1]
        prior_last["availableAt"] = self.opening + 19 * BAR
        with self.assertRaisesRegex(ValueError, "DAILY_FEATURE_NOT_YET_AVAILABLE"):
            nominations(self.data, self.protocol)

    def test_missing_or_misaligned_daily_grid_fails_closed(self):
        missing = copy.deepcopy(self.data)
        del missing["series"][0]["bars"][40]
        with self.assertRaisesRegex(ValueError, "SYNTHETIC_DAILY_GRID_INCOMPLETE"):
            nominations(missing, self.protocol)
        misaligned = copy.deepcopy(self.data)
        misaligned["series"][0]["bars"][0]["t"] -= 1
        with self.assertRaisesRegex(ValueError, "SYNTHETIC_DAILY_GRID_MISALIGNED"):
            nominations(misaligned, self.protocol)

    def test_external_world_labels_and_future_features_are_ignored(self):
        expected = nominations(self.data, self.protocol)
        self.data.update(world="NULL", latent_regime="PERFECT_ORACLE", future_return=1e12)
        for series in self.data["series"]:
            for bar in series["bars"]:
                bar.update(latent_drift=1000, future_return=-1e12, world="TREND")
        result = nominations(self.data, self.protocol)
        self.assertEqual(result, expected)
        for rows in result.values():
            for row in rows:
                # This native compatibility scalar is constant, not the
                # generator's hidden regime or a fitted forecast.
                self.assertEqual(row["regime"], 0.4)
                self.assertFalse({"world", "latent_drift", "future_return"}.intersection(row))

    def test_payload_preserves_stage_boundary_and_evaluation_dates(self):
        before = canonical(self.protocol)
        with patch("harpoon_quant.modulation9.market", return_value=self.data) as generate:
            result = payload(self.protocol, 82417, "NULL", "fixture", variants=[recipes()[-1]])
        generate.assert_called_once_with(self.protocol, 82417, "NULL", "fixture")
        self.assertEqual(result["protocol"]["periods"], {
            "evaluation_start": self.data["sessions"][self.first]["date"],
            "evaluation_end": self.data["sessions"][-1]["date"],
        })
        self.assertEqual(result["variants"][0]["id"], "CASH")
        self.assertEqual(result["scenario_names"], ["NOMINAL", "STRESS"])
        self.assertEqual(result["signals"], nominations(self.data, self.protocol))
        self.assertEqual(canonical(self.protocol), before)


if __name__ == "__main__":
    unittest.main()
