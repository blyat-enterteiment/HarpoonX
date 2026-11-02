"""Synthetic engineering fixtures; no real strategy performance or broker trades."""

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from harpoon_quant.core import Config
from harpoon_quant.optimization import (
    Policy,
    replay,
    subwindow,
    validate_window,
)
from harpoon_quant.performance import from_equity, hac_variance, report
from harpoon_quant.recursive import Journal, active_policy, tick


def performance(returns, **kw):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return report(
        {
            "origin": "SYNTHETIC_ENGINEERING_ONLY",
            "return_basis": "NET_FLOW_ADJUSTED",
            "returns": returns,
            "times": [
                (start + timedelta(days=i)).isoformat() for i in range(len(returns))
            ],
            "periods_per_year": 365,
            "sampling": "DAILY_UTC_CALENDAR",
            **kw,
        }
    )


def window(start, count):
    days = [(start + timedelta(days=i)).date().isoformat() for i in range(count)]
    ops = []
    for i, day in enumerate(days[:-1]):
        for name, edge, profit in [
            ("STRONG", 0.3, -0.6 if i % 5 == 0 else 1.2),
            ("WEAK", 0.03, 0.1 if i % 5 == 2 else -0.8),
        ]:
            at = start + timedelta(days=i, hours=12)
            end = at + timedelta(days=1)
            ops.append(
                {
                    "id": name + day,
                    "symbol": name,
                    "book": "equity",
                    "factor": name,
                    "at": at.isoformat(),
                    "known_at": at.isoformat(),
                    "label_end": end.isoformat(),
                    "label_known_at": (end + timedelta(minutes=1)).isoformat(),
                    "funding_per_lot": 100.0,
                    "exposure_per_lot": 100.0,
                    "risk_per_lot": 1.0,
                    "max_lots": 5,
                    "robust_edge_per_lot": edge,
                    "roundtrip_cost_per_lot": 0.1,
                    "wealth_by_day": {day: 99.9, end.date().isoformat(): 100 + profit},
                }
            )
    return {"days": days, "opportunities": ops}


def fixture(folder, origin="SYNTHETIC_ENGINEERING_ONLY"):
    limits = {
        "initial_equity": 20000,
        "risk_fraction": 0.0025,
        "open_risk_fraction": 0.015,
        "gross_fraction": 0.5,
        "asset_fraction": 0.12,
        "factor_fraction": 0.5,
        "max_positions": 8,
        "max_drawdown": 0.08,
    }
    binding = {
        "account_id": "SYNTHETIC_TEST_ACCOUNT",
        "execution_hash": "SYNTHETIC_CODE",
        "forecast_hash": "SYNTHETIC_FORECAST",
        "risk_limits": limits,
    }
    develop = window(datetime(2026, 1, 1, tzinfo=UTC), 200)
    holdout = window(datetime(2026, 7, 21, tzinfo=UTC), 60)
    panel = {
        "study_id": "SYNTHETIC_STUDY",
        "origin": origin,
        "binding": binding,
        "net_costs_confirmed": True,
        "cashflows_adjusted": True,
        "complete_opportunity_universe": True,
        "frozen_exit_replay_validated": True,
        "development": develop,
        "holdout_start": holdout["days"][0],
        "holdout_end": holdout["days"][-1],
        "holdout": holdout,
    }
    cfg = {
        "enabled": True,
        "autoPaper": True,
        "statePath": str(Path(folder) / "optimizer.db"),
        "lifetimeTrials": 32,
        "maxTrials": 16,
        "maxGenerations": 3,
        "cpuSeconds": 5,
        "minGainUsd": 5,
        "minHoldoutTrades": 20,
    }
    return panel, cfg, binding


def finish(panel, cfg, binding, now="2026-09-21T00:00:00+00:00", paper=True):
    result = {}
    for _ in range(8):
        result = tick(panel, cfg, binding, now, paper=paper)
        if result["status"] in (
            "PAPER_ACCEPTED",
            "RESEARCH_ACCEPTED",
            "REJECTED",
            "EXHAUSTED",
        ):
            break
    return result


class PerformanceTests(unittest.TestCase):
    def test_sortino_uses_total_sample_denominator(self):
        m = performance([0.1, -0.1, 0.1, -0.1])
        self.assertAlmostEqual(m["downside_deviation_per_period"], np.sqrt(0.02 / 4))
        self.assertEqual(m["sortino_per_period"], 0)

    def test_first_loss_counts_in_drawdown(self):
        m = performance([-0.1, 0.2, -0.05])
        self.assertAlmostEqual(m["max_drawdown"], 0.1)
        self.assertEqual(m["max_drawdown_duration_periods"], 1)
        self.assertIsNotNone(m["recovered_at"])

    def test_drawdown_longest_unrecovered_episode(self):
        m = performance([0.1, -0.1, 0, -0.1, 0])
        self.assertEqual(m["max_drawdown_duration_periods"], 4)
        self.assertIsNone(m["recovered_at"])

    def test_zero_downside_is_null_not_infinity(self):
        m = performance([0.01, 0.02, 0.01])
        self.assertIsNone(m["sortino_per_period"])
        json.dumps(m, allow_nan=False)

    def test_cash_deposit_is_not_profit(self):
        _times, returns, initial = from_equity(
            [
                {"at": "2026-01-01T00:00:00Z", "equity": 100},
                {
                    "at": "2026-01-02T00:00:00Z",
                    "equity": 200,
                    "external_flow_after": 100,
                },
                {"at": "2026-01-03T00:00:00Z", "equity": 220},
            ]
        )
        self.assertEqual(initial, 100)
        self.assertEqual(returns[0], 0)
        self.assertAlmostEqual(returns[1], 0.1)

    def test_beginning_cashflow_timing_is_explicit(self):
        _, r, _ = from_equity(
            [
                {"at": "2026-01-01T00:00:00Z", "equity": 100},
                {
                    "at": "2026-01-02T00:00:00Z",
                    "equity": 220,
                    "external_flow_before": 100,
                },
            ]
        )
        self.assertAlmostEqual(r[0], 0.1)

    def test_short_samples_do_not_annualize(self):
        self.assertIsNone(performance([0.01, -0.005] * 20)["sortino_annualized"])
        self.assertIsNotNone(performance([0.01, -0.005] * 60)["sortino_annualized"])

    def test_irregular_calendar_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "IRREGULAR"):
            performance(
                [0.01, -0.01], times=["2026-01-01T00:00:00Z", "2026-01-03T00:00:00Z"]
            )

    def test_nonfinite_and_impossible_returns_rejected(self):
        for x in [np.nan, -1.1]:
            with self.assertRaises(ValueError):
                performance([x, 0])

    def test_net_basis_must_be_declared(self):
        with self.assertRaisesRegex(ValueError, "NET_FLOW"):
            performance([0.01, -0.01], return_basis="PRICE_RETURNS")

    def test_empirical_cvar_fractional_tail(self):
        r = [0.001] * 18 + [-0.1, -0.2]
        self.assertAlmostEqual(performance(r)["historical_cvar95_fraction"], 0.2)

    def test_benchmark_alignment_and_beta(self):
        b = [0.01, -0.01, 0.005, -0.005] * 30
        m = performance([2 * x for x in b], benchmark_returns=b)
        self.assertAlmostEqual(m["benchmark"]["beta"], 2)
        with self.assertRaisesRegex(ValueError, "ALIGNMENT"):
            performance(b, benchmark_returns=[0])

    def test_trial_population_is_required_for_dsr(self):
        m = performance([0.01, -0.005] * 60)
        self.assertIsNone(m["dsr_diagnostic"]["value"])
        m = performance(
            [0.01, -0.005] * 60, trial_sharpes=[0.1, 0.2, 0.3], declared_trials=3
        )
        self.assertGreaterEqual(m["dsr_diagnostic"]["value"], 0)
        self.assertLessEqual(m["dsr_diagnostic"]["value"], 1)

    def test_hac_detects_persistence(self):
        r = np.repeat([0.01, -0.01], 20)
        self.assertGreater(hac_variance(r), np.var(r))

    def test_net_trade_statistics(self):
        m = performance(
            [0.01, -0.01],
            trades=[
                {"net_pnl_usd": 20, "cost_usd": 2},
                {"net_pnl_usd": -10, "cost_usd": 1},
            ],
        )
        self.assertEqual(m["profit_factor"], 2)
        self.assertEqual(m["trade_expectancy_usd"], 5)
        self.assertEqual(m["net_costs_usd"], 3)

    def test_ruin_cannot_be_followed_by_recovery_returns(self):
        self.assertEqual(performance([-0.5, -1, 0])["max_drawdown"], 1)
        with self.assertRaisesRegex(ValueError, "AFTER_RUIN"):
            performance([-1, 0.1])


class ReplayTests(unittest.TestCase):
    def test_policy_cannot_exceed_original_size(self):
        with self.assertRaises(ValueError):
            Policy(1.1, 0)
        with self.assertRaises(ValueError):
            Policy(1, -1)
        self.assertTrue(all(p.risk_scale <= 1 for p in Policy().neighbors()))

    def test_quality_filter_uses_known_forecast(self):
        with tempfile.TemporaryDirectory() as d:
            p, _c, b = fixture(d)
            w = p["development"]
            settings = {**b["risk_limits"], "origin": p["origin"]}
            base = replay(w, Policy(), settings)
            filtered = replay(w, Policy(1, 5), settings)
            self.assertGreater(
                filtered["metrics"]["total_return"], base["metrics"]["total_return"]
            )
            self.assertLess(
                filtered["metrics"]["max_drawdown"], base["metrics"]["max_drawdown"]
            )

    def test_closed_campaigns_do_not_conceal_mtm_loss(self):
        w = window(datetime(2026, 1, 1, tzinfo=UTC), 30)
        for o in w["opportunities"]:
            o["wealth_by_day"][o["at"][:10]] = 50
        settings = {"origin": "SYNTHETIC_ENGINEERING_ONLY"}
        self.assertGreater(replay(w, Policy(), settings)["metrics"]["max_drawdown"], 0)

    def test_missing_daily_marks_are_rejected(self):
        w = window(datetime(2026, 1, 1, tzinfo=UTC), 30)
        w["opportunities"][0]["wealth_by_day"].pop(w["days"][0])
        with self.assertRaisesRegex(ValueError, "MARK_TO_MARKET"):
            validate_window(w, "2026-12-01T00:00:00Z")

    def test_future_labels_rejected(self):
        w = window(datetime(2026, 1, 1, tzinfo=UTC), 30)
        with self.assertRaisesRegex(ValueError, "INCOMPLETE"):
            validate_window(w, "2026-01-10T00:00:00Z")

    def test_split_purges_crossing_labels_and_embargoes_start(self):
        w = window(datetime(2026, 1, 1, tzinfo=UTC), 100)
        s = subwindow(w, 30, 60)
        self.assertTrue(
            all(
                o["at"][:10] >= s["days"][3] and o["label_end"][:10] <= s["days"][-1]
                for o in s["opportunities"]
            )
        )

    def test_cost_stress_does_not_improve_profit(self):
        w = window(datetime(2026, 1, 1, tzinfo=UTC), 60)
        settings = {"origin": "SYNTHETIC_ENGINEERING_ONLY"}
        self.assertLess(
            replay(w, Policy(), settings, cashflow_stress=1.5)["metrics"][
                "total_return"
            ],
            replay(w, Policy(), settings)["metrics"]["total_return"],
        )


class RecursiveTests(unittest.TestCase):
    def test_missing_data_waits_without_training(self):
        with tempfile.TemporaryDirectory() as d:
            _, c, b = fixture(d)
            r = tick(None, c, b, "2026-07-20T23:00:00Z")
            self.assertEqual(r["status"], "WAIT_DATA")

    def test_recursive_search_persists_and_stops(self):
        with tempfile.TemporaryDirectory() as d:
            p, c, b = fixture(d)
            r = finish(p, c, b)
            self.assertEqual(r["status"], "RESEARCH_ACCEPTED", r)
            self.assertIsNone(active_policy(c["statePath"], b, "2026-09-22T00:00:00Z"))
            j = Journal(c["statePath"])
            self.assertLessEqual(j.get("budget")["spent"], c["lifetimeTrials"])
            j.verify()
            j.close()
            repeated = tick(p, c, b, "2026-09-22T00:00:00Z")
            self.assertEqual(repeated["status"], r["status"])

    def test_future_holdout_is_not_read_during_search(self):
        with tempfile.TemporaryDirectory() as d:
            p, c, b = fixture(d)
            p["holdout"] = {"THIS_WOULD_FAIL_IF_READ": True}
            for _ in range(5):
                r = tick(p, c, b, "2026-07-20T23:00:00Z")
            self.assertEqual(r["status"], "WAIT_HOLDOUT")

    def test_paper_positive_fixture_requires_preregistration_and_observed_flag(self):
        # OBSERVED is a controlled contract fixture here, not empirical evidence.
        with tempfile.TemporaryDirectory() as d:
            p, c, b = fixture(d, "OBSERVED")
            for _ in range(3):
                tick(p, c, b, "2026-07-20T23:00:00Z")
            r = finish(p, c, b)
            self.assertEqual(r["status"], "PAPER_ACCEPTED", r)
            a = active_policy(c["statePath"], b, "2026-09-22T00:00:00Z")
            self.assertGreater(a["policy"]["quality_bps"], 0)
            self.assertLessEqual(a["policy"]["risk_scale"], 1)

    def test_historical_registration_cannot_auto_promote(self):
        with tempfile.TemporaryDirectory() as d:
            p, c, b = fixture(d, "OBSERVED")
            r = finish(p, c, b)
            self.assertEqual(r["status"], "RESEARCH_ACCEPTED")
            self.assertFalse(r["result"]["prospectively_registered"])

    def test_modified_development_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p, c, b = fixture(d)
            tick(p, c, b, "2026-07-20T23:00:00Z")
            p["development"]["opportunities"][0]["robust_edge_per_lot"] += 1
            with self.assertRaisesRegex(ValueError, "MUTATED"):
                tick(p, c, b, "2026-09-21T00:00:00Z")

    def test_budget_cannot_be_reset_by_restart_or_config_change(self):
        with tempfile.TemporaryDirectory() as d:
            p, c, b = fixture(d)
            tick(p, c, b, "2026-07-20T23:00:00Z")
            other = {**c, "lifetimeTrials": 64}
            with self.assertRaisesRegex(ValueError, "FROZEN"):
                tick(p, other, b, "2026-09-21T00:00:00Z")

    def test_holdout_window_cannot_be_reused_by_another_study(self):
        with tempfile.TemporaryDirectory() as d:
            p, c, b = fixture(d)
            finish(p, c, b)
            p["study_id"] = "SECOND"
            with self.assertRaisesRegex(ValueError, "ALREADY_CONSUMED"):
                finish(p, c, b)

    def test_incomplete_economic_evidence_cannot_start_search(self):
        with tempfile.TemporaryDirectory() as d:
            p, c, b = fixture(d)
            p["net_costs_confirmed"] = False
            with self.assertRaisesRegex(ValueError, "EVIDENCE"):
                tick(p, c, b, "2026-09-21T00:00:00Z")

    def test_binding_changes_pause_active_policy(self):
        with tempfile.TemporaryDirectory() as d:
            p, c, b = fixture(d, "OBSERVED")
            for _ in range(3):
                tick(p, c, b, "2026-07-20T23:00:00Z")
            finish(p, c, b)
            a = active_policy(
                c["statePath"],
                {**b, "forecast_hash": "DIFFERENT"},
                "2026-09-22T00:00:00Z",
            )
            self.assertTrue(a["pause_entries"])

    def test_audit_corruption_is_detected(self):
        with tempfile.TemporaryDirectory() as d:
            p, c, b = fixture(d)
            tick(p, c, b, "2026-07-20T23:00:00Z")
            j = Journal(c["statePath"])
            j.db.execute("UPDATE optimizer_state SET v='{}' WHERE k='budget'")
            j.db.commit()
            j.close()
            with self.assertRaisesRegex(ValueError, "INTEGRITY"):
                Journal(c["statePath"])

    def test_quality_envelope_validation(self):
        with self.assertRaisesRegex(ValueError, "QUALITY"):
            Config(min_robust_return_bps=101)


class LoopSafetyTests(unittest.TestCase):
    def test_concurrent_tick_cannot_duplicate_reserved_trials(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        from unittest.mock import patch

        import harpoon_quant.recursive as module

        started, release = Event(), Event()
        original = module.development_score

        def slow(*args):
            started.set()
            release.wait(5)
            return original(*args)

        with tempfile.TemporaryDirectory() as d:
            p, c, b = fixture(d)
            with (
                patch.object(module, "development_score", slow),
                ThreadPoolExecutor(2) as pool,
            ):
                first = pool.submit(tick, p, c, b, "2026-07-20T23:00:00Z")
                self.assertTrue(started.wait(3))
                second = tick(p, c, b, "2026-07-20T23:00:00Z")
                self.assertEqual(second["status"], "BUSY")
                release.set()
                first.result()
            j = Journal(c["statePath"])
            self.assertEqual(j.get("budget")["spent"], 3)
            j.close()

    def test_failed_cpu_attempts_still_consume_budget(self):
        from itertools import chain, repeat
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as d:
            p, c, b = fixture(d)
            with patch(
                "harpoon_quant.recursive.time.perf_counter",
                side_effect=chain([0], repeat(100)),
            ):
                tick(p, c, b, "2026-07-20T23:00:00Z")
            j = Journal(c["statePath"])
            self.assertEqual(j.get("budget")["spent"], 3)
            j.close()
            r = tick(p, c, b, "2026-07-21T00:00:00Z")
            self.assertEqual(r["status"], "EXHAUSTED")

    def test_deterioration_pauses_new_entries_without_releasing_risk_limits(self):
        with tempfile.TemporaryDirectory() as d:
            p, c, b = fixture(d, "OBSERVED")
            for _ in range(3):
                tick(p, c, b, "2026-07-20T23:00:00Z")
            finish(p, c, b)
            result = tick(p, c, b, "2026-09-22T00:00:00Z", live_drawdown=0.09)
            self.assertEqual(result["status"], "RISK_PAUSED")
            self.assertTrue(
                active_policy(c["statePath"], b, "2026-09-22T00:00:00Z")[
                    "pause_entries"
                ]
            )

    def test_expired_active_policy_is_not_silently_reused(self):
        with tempfile.TemporaryDirectory() as d:
            p, c, b = fixture(d, "OBSERVED")
            for _ in range(3):
                tick(p, c, b, "2026-07-20T23:00:00Z")
            finish(p, c, b)
            self.assertTrue(
                active_policy(c["statePath"], b, "2027-01-01T00:00:00Z")[
                    "pause_entries"
                ]
            )

    def test_batched_bootstrap_matches_original_reference(self):
        from harpoon_quant.calibration import block_lower
        from harpoon_quant.recursive import paired_lower

        r = np.random.default_rng(3).normal(0.001, 0.01, 80)
        self.assertAlmostEqual(
            paired_lower(r, 3), block_lower(r, attempts=3), places=12
        )

    def test_core_economic_quality_floor_changes_actual_allocation(self):
        from test_quant import calibration, candidate, request

        from harpoon_quant.core import allocate

        data = request([candidate()])
        model = calibration(mu=0.003)
        base = allocate(data, model, Config(slippage_bps=0, uncertainty_z=0))
        restricted = allocate(
            data,
            model,
            Config(slippage_bps=0, uncertainty_z=0, min_robust_return_bps=100),
        )
        self.assertTrue(base["selected"])
        self.assertEqual(restricted["selected"], [])


class EconomicRejectionTests(unittest.TestCase):
    def test_ratio_improvement_without_net_profit_cannot_promote(self):
        with tempfile.TemporaryDirectory() as d:
            p, c, b = fixture(d)
            for o in p["holdout"]["opportunities"]:
                o["wealth_by_day"][o["label_end"][:10]] = o["funding_per_lot"]
            result = finish(p, c, b)
            self.assertEqual(result["status"], "REJECTED")
            self.assertFalse(result["result"]["passed"])
            self.assertIsNone(active_policy(c["statePath"], b, "2026-09-22T00:00:00Z"))

    def test_flow_adjusted_dollar_profit_and_twr_capital_are_distinct(self):
        rows = [
            {"at": "2026-01-01T00:00:00Z", "equity": 100},
            {"at": "2026-01-02T00:00:00Z", "equity": 200, "external_flow_after": 100},
            {"at": "2026-01-03T00:00:00Z", "equity": 220},
        ]
        m = report(
            {
                "origin": "SYNTHETIC_ENGINEERING_ONLY",
                "return_basis": "NET_FLOW_ADJUSTED",
                "equity": rows,
                "periods_per_year": 365,
                "sampling": "DAILY_UTC_CALENDAR",
            }
        )
        self.assertAlmostEqual(m["cashflow_adjusted_actual_net_pnl_usd"], 20)
        self.assertAlmostEqual(m["net_profit_usd_on_adjusted_initial_capital"], 10)


class PromotionModeTests(unittest.TestCase):
    def test_active_paper_policy_cannot_follow_account_into_live_mode(self):
        from unittest.mock import patch

        from harpoon_quant.bridge import from_runtime

        config = dict(
            mode="live",
            maxPositions=8,
            totalExposure=0.5,
            assetExposure=0.12,
            factorExposure=0.5,
            dailyLoss=0.02,
            maxDrawdown=0.08,
            slippageBps=1,
            quoteAgeMs=1000,
            quant={"optimizer": {"enabled": True, "statePath": "unused"}},
        )
        with patch(
            "harpoon_quant.recursive.active_policy",
            return_value={"policy": {"risk_scale": 0.5, "quality_bps": 10}},
        ):
            result = from_runtime({"now": 0, "market": {}, "config": config}, {})
        self.assertFalse(result["execution_allowed"])
        self.assertEqual(result["reason"], "OPTIMIZER_POLICY_PAPER_ONLY")
