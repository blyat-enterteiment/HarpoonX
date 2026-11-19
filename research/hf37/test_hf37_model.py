"""Causal, funded-account, failure, and restart checks; no live executions."""

from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import numpy as np

from research.hf37.hf37_model_lab import BASE_NS, make_fixture, run_case, timestamp_ns
from research.hf37.hf37_portfolio import (
    CheckpointStore,
    Costs,
    ModeledBook,
    Position,
    Risk,
    canonical,
    target_weights,
)
from research.hf37.hf37_predictor import (
    DAY_NS,
    Forecast,
    Label,
    Quote,
    Trade,
    fit_return_model,
    pressure_features,
    shrunk_covariance,
)


class TestPressureAndForecast(unittest.TestCase):
    def pressure(self, trades=None, quotes=None):
        baseline = [Trade(10, 10, 100, 10), Trade(11, 11, 100, 10)]
        return pressure_features(
            baseline,
            trades or [Trade(40, 40, 101, 20)],
            quotes or [Quote(30, 30, 99, 101, 100, 100)],
            20,
            50,
            min_baseline=2,
            min_classified=1,
            max_quote_age_ns=100,
        )

    def test_future_quote_rejected(self):
        with self.assertRaisesRegex(ValueError, "FUTURE_QUOTE"):
            self.pressure(quotes=[Quote(30, 60, 99, 101, 100, 100)])

    def test_late_newest_quote_falls_back_to_causal_older_quote(self):
        p = self.pressure(
            quotes=[Quote(30, 30, 99, 101, 100, 100), Quote(39, 45, 98, 102, 100, 100)]
        )
        self.assertTrue(p.available)
        self.assertEqual(p.score, 1)

    def test_baseline_cannot_include_signal_window(self):
        with self.assertRaisesRegex(ValueError, "BASELINE_NOT"):
            pressure_features([Trade(25, 25, 100, 10)], [], [], 20, 50, min_baseline=2)

    def test_stale_quote_and_inside_spread_not_classified(self):
        p = self.pressure(trades=[Trade(40, 40, 100, 20)])
        self.assertFalse(p.available)
        self.assertEqual(p.classified, 0)
        p = pressure_features(
            [Trade(10, 10, 100, 10), Trade(11, 11, 100, 10)],
            [Trade(1000, 1000, 101, 20)],
            [Quote(30, 30, 99, 101, 100, 100)],
            20,
            1100,
            min_baseline=2,
            min_classified=1,
            max_quote_age_ns=100,
        )
        self.assertFalse(p.available)

    def test_invalid_quote_and_nonfinite_trade_rejected(self):
        with self.assertRaises(ValueError):
            self.pressure(quotes=[Quote(30, 30, 102, 101, 100, 100)])
        with self.assertRaises(ValueError):
            self.pressure(trades=[Trade(40, 40, float("nan"), 20)])

    def test_no_labels_cannot_allocate_a_forecast(self):
        forecast = fit_return_model([], BASE_NS, whale=True).predict(1, 1, BASE_NS)
        self.assertFalse(forecast.available)

    def test_future_labels_do_not_change_prediction(self):
        labels = [
            Label(
                BASE_NS + d * DAY_NS,
                BASE_NS + (d + 1) * DAY_NS,
                BASE_NS + (d + 1) * DAY_NS,
                "A",
                "S",
                0.2,
                (-1.0) ** d,
                0.01 * (-1.0) ** d,
            )
            for d in range(60)
        ]
        clock = BASE_NS + 45 * DAY_NS
        one = fit_return_model(labels, clock, whale=True)
        changed = [
            replace(label, gross_return=0.9) if label.known_ns > clock else label
            for label in labels
        ]
        two = fit_return_model(changed, clock, whale=True)
        np.testing.assert_array_equal(one.beta, two.beta)
        self.assertEqual(one.observations, 45)
        self.assertTrue(one.predict(0.2, 1, clock).available)

    def test_same_timestamp_assets_are_one_cluster(self):
        labels = [
            Label(
                BASE_NS, BASE_NS + DAY_NS, BASE_NS + DAY_NS, str(i), "S", 0.2, 0.3, 0.01
            )
            for i in range(100)
        ]
        forecast = fit_return_model(labels, BASE_NS + DAY_NS, whale=True).predict(
            0.2, 0.3, BASE_NS + DAY_NS
        )
        self.assertEqual(forecast.clusters, 1)
        self.assertFalse(forecast.available)

    def test_label_horizon_over_72h_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "OVER_72H"):
            fit_return_model(
                [
                    Label(
                        BASE_NS,
                        BASE_NS + 4 * DAY_NS,
                        BASE_NS + 4 * DAY_NS,
                        "A",
                        "S",
                        0,
                        0,
                        0,
                    )
                ],
                BASE_NS + 5 * DAY_NS,
                whale=True,
            )

    def test_nan_risk_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "NONFINITE"):
            Risk(risk_aversion=float("nan")).validate()

    def test_covariance_is_psd_and_rejects_malformed_panel(self):
        cov = shrunk_covariance([[0.1, 0.1], [-0.1, -0.1], [0, 0]], 2)
        self.assertGreater(np.linalg.eigvalsh(cov).min(), 0)
        with self.assertRaises(ValueError):
            shrunk_covariance([[0.1], [0.2]], 2)

    def test_timestamp_conversion_preserves_microseconds(self):
        self.assertEqual(
            timestamp_ns("2026-10-15T13:30:00.123456Z")
            - timestamp_ns("2026-10-15T13:30:00Z"),
            123456000,
        )


class TestFundedPortfolio(unittest.TestCase):
    def setUp(self):
        self.clock = BASE_NS
        self.costs, self.risk = Costs(), Risk()
        self.quotes = {
            s: Quote(self.clock - 1, self.clock - 1, 99.95, 100.05, 100000, 100000)
            for s in ("A", "B", "E")
        }
        self.execution = {
            s: replace(
                q, at_ns=self.clock + 1_000_000_000, known_ns=self.clock + 1_000_000_000
            )
            for s, q in self.quotes.items()
        }
        self.forecasts = {
            s: Forecast(True, 0.02, 0.015, 0.0004, 60, 180) for s in self.quotes
        }
        self.sectors = dict.fromkeys(self.quotes, "S")

    def weights(self, book, forecasts=None, quotes=None):
        return target_weights(
            list(self.quotes),
            self.sectors,
            forecasts or self.forecasts,
            quotes or self.quotes,
            np.eye(3) * 0.0004,
            book,
            self.clock,
            self.costs,
            self.risk,
            {"A": "E", "B": "E"},
        )[0]

    def test_uncalibrated_or_nonpositive_edge_stays_cash(self):
        f = {s: Forecast(False, 0.02, 0.015, 0.0004, 1, 1) for s in self.quotes}
        self.assertEqual(sum(self.weights(ModeledBook(), f).values()), 0)
        f = {s: Forecast(True, 0, -0.001, 0.0004, 50, 200) for s in self.quotes}
        self.assertEqual(sum(self.weights(ModeledBook(), f).values()), 0)

    def test_stock_competes_against_etf_upper_bound(self):
        w = self.weights(ModeledBook())
        self.assertEqual(w["A"], 0)
        self.assertEqual(w["B"], 0)
        self.assertGreater(w["E"], 0)

    def test_sector_and_asset_limits_are_enforced(self):
        f = dict(self.forecasts)
        f["E"] = Forecast(True, 0, -0.001, 0.0004, 60, 180)
        w = self.weights(ModeledBook(), f)
        self.assertLessEqual(sum(w.values()), self.risk.max_sector + 1e-7)
        self.assertLessEqual(max(w.values()), self.risk.max_asset + 1e-7)

    def test_future_or_stale_allocation_quote_is_rejected(self):
        for q in (
            replace(self.quotes["A"], known_ns=self.clock + 1),
            replace(self.quotes["A"], at_ns=self.clock - 10_000_000_000),
        ):
            with self.subTest(q=q), self.assertRaises(ValueError):
                self.weights(ModeledBook(), quotes=self.quotes | {"A": q})

    def test_modeled_cash_fees_and_liquidation_reconcile(self):
        book = ModeledBook()
        book.rebalance(
            "buy", self.clock, self.execution, {"A": 0.12}, self.costs, self.risk
        )
        self.assertGreater(book.cash, 0)
        self.assertGreater(book.fees, 0)
        later = {
            s: replace(q, at_ns=q.at_ns + 2, known_ns=q.known_ns + 2)
            for s, q in self.execution.items()
        }
        book.rebalance(
            "sell", self.clock + 1_000_000_001, later, {}, self.costs, self.risk
        )
        self.assertFalse(book.positions)
        expected = 20000 + sum(
            (1 if r["side"] == "SELL" else -1) * r["quantity"] * r["price"] - r["fee"]
            for r in book.receipts
        )
        self.assertAlmostEqual(book.cash, expected)
        self.assertLess(book.cash, 20000)
        self.assertTrue(
            all(r["kind"] == "MODELED_IOC_NOT_BROKER_FILL" for r in book.receipts)
        )

    def test_event_replay_is_idempotent_and_conflict_is_atomic(self):
        book = ModeledBook()
        book.rebalance(
            "x", self.clock, self.execution, {"A": 0.12}, self.costs, self.risk
        )
        before = canonical(book.snapshot())
        book.rebalance(
            "x", self.clock, self.execution, {"A": 0.12}, self.costs, self.risk
        )
        self.assertEqual(canonical(book.snapshot()), before)
        with self.assertRaisesRegex(ValueError, "CONFLICTING_REPLAY"):
            book.rebalance(
                "x", self.clock, self.execution, {"A": 0.10}, self.costs, self.risk
            )
        self.assertEqual(canonical(book.snapshot()), before)

    def test_missing_quote_or_same_clock_never_mutates_book(self):
        for quotes in ({}, {"A": self.quotes["A"]}):
            book = ModeledBook()
            with self.assertRaises(ValueError):
                book.rebalance(
                    "x", self.clock, quotes, {"A": 0.12}, self.costs, self.risk
                )
            self.assertEqual(book.cash, 20000)
            self.assertFalse(book.receipts)

    def test_depth_caps_partial_fills(self):
        quotes = {"A": replace(self.execution["A"], ask_size=10)}
        book = ModeledBook()
        book.rebalance("x", self.clock, quotes, {"A": 0.12}, self.costs, self.risk)
        self.assertEqual(book.positions["A"].quantity, 1)
        self.assertGreater(book.receipts[0]["requested"], 1)

    def test_failed_72h_exit_is_reported_not_hidden(self):
        book = ModeledBook(
            positions={"A": Position(10, self.clock - 3 * DAY_NS + 1_000_000_000, 100)}
        )
        quotes = {"A": replace(self.execution["A"], bid_size=0)}
        book.rebalance("x", self.clock, quotes, {}, self.costs, self.risk)
        self.assertEqual(book.hold_breaches, 1)
        self.assertTrue(book.permanently_halted)
        self.assertEqual(book.positions["A"].quantity, 10)

    def test_adding_never_resets_oldest_holding_clock(self):
        original = self.clock - DAY_NS
        book = ModeledBook(positions={"A": Position(1, original, 100)})
        book.rebalance(
            "x", self.clock, self.execution, {"A": 0.12}, self.costs, self.risk
        )
        self.assertGreater(book.positions["A"].quantity, 1)
        self.assertEqual(book.positions["A"].opened_ns, original)

    def test_failed_time_exit_blocks_other_buys_in_same_event(self):
        book = ModeledBook(
            positions={"A": Position(10, self.clock - 3 * DAY_NS + 1_000_000_000, 100)}
        )
        quotes = self.execution | {"A": replace(self.execution["A"], bid_size=0)}
        book.rebalance(
            "blocked", self.clock, quotes, {"B": 0.12}, self.costs, self.risk
        )
        self.assertNotIn("B", book.positions)
        self.assertFalse(book.receipts)
        self.assertTrue(book.permanently_halted)

    def test_drawdown_halt_persists(self):
        book = ModeledBook(peak=30000)
        self.assertEqual(sum(self.weights(book).values()), 0)
        restored = ModeledBook.restore(book.snapshot())
        self.assertTrue(restored.permanently_halted)

    def test_winner_can_be_retained_below_new_entry_hurdle(self):
        book = ModeledBook(positions={"A": Position(10, self.clock - DAY_NS, 99.95)})
        f = {s: Forecast(True, 0, -0.001, 0.0004, 60, 180) for s in self.quotes}
        f["A"] = Forecast(True, 0.001, 0.001, 0.0004, 60, 180)
        w = self.weights(book, f)
        self.assertGreater(w["A"], 0)
        before = book.positions["A"].quantity
        book.rebalance("retain", self.clock, self.execution, w, self.costs, self.risk)
        self.assertEqual(book.positions["A"].quantity, before)


class TestPersistenceAndIntegration(unittest.TestCase):
    def test_checkpoint_conflicts_and_hash_tampering_are_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.sqlite"
            store = CheckpointStore(path, "config")
            store.save("r", 0, -1, {"a": 1}, {"cash": 20000})
            store.save("r", 0, -1, {"a": 1}, {"cash": 20000})
            self.assertEqual(store.load("r"), (0, {"cash": 20000}))
            with self.assertRaisesRegex(ValueError, "LEASE"):
                store.save("r", 1, -1, {}, {})
            with self.assertRaises(ValueError):
                CheckpointStore(path, "different").load("r")
            with sqlite3.connect(path) as db:
                db.execute("UPDATE journal SET input_hash='tampered'")
            with self.assertRaisesRegex(ValueError, "JOURNAL_HASH"):
                store.load("r")

    def test_restart_matches_uninterrupted_44_asset_account(self):
        fixture = make_fixture("PRESSURE_EDGE", sessions=55, seed=3701)
        with tempfile.TemporaryDirectory() as folder:
            full = run_case(fixture, 1, Path(folder) / "full.sqlite")
            resumed = run_case(
                fixture, 1, Path(folder) / "resume.sqlite", restart_at=45
            )
        self.assertEqual(full["summaries"], resumed["summaries"])
        self.assertEqual(full["wealth_paths"], resumed["wealth_paths"])
        self.assertTrue(resumed["restart_executed"])
        self.assertFalse(resumed["gate"]["enabled"])
        self.assertEqual(resumed["gate"]["reason"], "MISSING_COMPARATOR")
        self.assertEqual(resumed["broker_receipts"], 0)

    def test_preregistered_budget_and_no_live_permissions(self):
        path = Path(__file__).with_name("hf37_model_preregistered.json")
        config = json.loads(path.read_text())
        self.assertEqual(
            len(config["synthetic_worlds"]) * len(config["cost_multipliers"]), 6
        )
        self.assertFalse(config["orders_enabled"])
        self.assertFalse(config["holdout_november_2026_opened"])


if __name__ == "__main__":
    unittest.main()
