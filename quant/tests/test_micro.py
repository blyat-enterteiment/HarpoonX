import copy
import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import numpy as np
from test_quant import candidate

from harpoon_quant.context import guard, resample_15min
from harpoon_quant.core import Config, instrument, pnl_lot
from harpoon_quant.curves import CurveStore, surface, validate_surface
from harpoon_quant.data_client import AlpacaData
from harpoon_quant.microstructure import markouts, normalize, summarize
from harpoon_quant.support import (
    evaluate_support,
    fit_support,
    kernel_output,
    matrix,
    scaling,
)

AT = datetime(2026, 10, 29, 14, tzinfo=UTC)


def quote(second, bid=99.0, ask=101.0, bs=3.0, az=1.0, known=None):
    at = (AT + timedelta(seconds=second)).isoformat()
    return {
        "t": at,
        "known_at": known or at,
        "bp": bid,
        "ap": ask,
        "bs": bs,
        "as": az,
        "c": ["R"],
    }


def trade(second, price=101.0, size=2.0):
    return {
        "t": (AT + timedelta(seconds=second)).isoformat(),
        "p": price,
        "s": size,
        "c": ["@"],
    }


def panel(count=300):
    rng = np.random.default_rng(17)
    x = rng.normal(0, 0.001, count)
    y = 0.7 * x + rng.normal(0, 0.0005, count)
    out = {}
    for name, values in (("A", x), ("B", y)):
        rows = []
        price = 100.0
        for i, value in enumerate(values):
            price *= np.exp(value)
            start = AT - timedelta(minutes=5 * (count - i))
            rows.append(
                {
                    "start": start.isoformat(),
                    "end": (start + timedelta(minutes=5)).isoformat(),
                    "known_at": (start + timedelta(minutes=5)).isoformat(),
                    "session": "SYNTHETIC_CONTIGUOUS",
                    "close": price,
                    "volume": 10,
                }
            )
        out[name] = rows
    return out


def curve():
    return surface(
        panel(),
        AT.isoformat(),
        feed="sip",
        origin="SYNTHETIC_ENGINEERING_ONLY",
        windows=(32, 64),
        lags=(-1, 0, 1),
    )


def cost_panel():
    rng = np.random.default_rng(31)
    rows = []
    for i in range(240):
        at = datetime(2026, 1, 1, 15, tzinfo=UTC) + timedelta(days=i)
        x = rng.normal()
        z = rng.uniform(-0.8, 0.8)
        rows.append(
            {
                "at": at.isoformat(),
                "features_known_at": at.isoformat(),
                "label_end": (at + timedelta(hours=24)).isoformat(),
                "label_known_at": (at + timedelta(hours=24, minutes=1)).isoformat(),
                "features": {"spread_tw_bps": 5 + x, "imbalance_tw": z},
                "target_extra_bps": max(
                    0.0, 5 + 2 * np.tanh(x) + z + rng.normal(0, 0.15)
                ),
            }
        )
    return {
        "origin": "SYNTHETIC_ENGINEERING_ONLY",
        "feed": "sip",
        "horizon_hours": 24,
        "feature_names": ["spread_tw_bps", "imbalance_tw"],
        "rows": rows,
    }


class MicroTests(unittest.TestCase):
    def test_time_weighted_units(self):
        out = summarize(
            [quote(0), quote(1, 100, 102, 2, 2)],
            [],
            (AT + timedelta(seconds=2)).isoformat(),
            window_seconds=2,
        )
        self.assertAlmostEqual(
            out["features"]["spread_tw_bps"], (200 + 20000 / 101) / 2
        )
        self.assertAlmostEqual(out["features"]["imbalance_tw"], 0.25)
        self.assertAlmostEqual(out["features"]["weighted_mid_deviation_bps"], 25)

    def test_historical_stock_size_transition(self):
        a = quote(0)
        a["t"] = "2025-11-02T14:00:00+00:00"
        self.assertEqual(normalize(a, "quote")["bs"], 300)
        a["t"] = "2025-11-03T14:00:00+00:00"
        self.assertEqual(normalize(a, "quote")["bs"], 3)

    def test_option_units_are_not_stock_lots(self):
        a = quote(0)
        a["t"] = "2025-01-02T14:00:00+00:00"
        self.assertEqual(normalize(a, "quote", "options")["bs"], 3)

    def test_explicit_units_override_date(self):
        a = quote(0)
        a.update(t="2025-01-02T14:00:00+00:00", size_unit="shares")
        self.assertEqual(normalize(a, "quote")["bs"], 3)

    def test_crossed_and_zero_bbo_rejected(self):
        for q in [quote(0, 101, 100), quote(0, 0, 100), quote(0, 99, 101, 0)]:
            with self.assertRaises(ValueError):
                normalize(q, "quote")

    def test_unknown_conditions_rejected(self):
        q = quote(0)
        q["c"] = ["UNKNOWN"]
        with self.assertRaisesRegex(ValueError, "CONDITION"):
            normalize(q, "quote")

    def test_future_event_cannot_change_features(self):
        qs = [quote(0), quote(1)]
        before = summarize(
            qs, [], (AT + timedelta(seconds=2)).isoformat(), window_seconds=2
        )
        after = summarize(
            [*qs, quote(100, 300, 301)],
            [],
            (AT + timedelta(seconds=2)).isoformat(),
            window_seconds=2,
        )
        self.assertEqual(before["features"], after["features"])

    def test_late_receipt_is_not_replayed_as_live(self):
        late = (AT + timedelta(seconds=100)).isoformat()
        qs = [quote(0, known=late), quote(1, known=late)]
        out = summarize(
            qs, [], (AT + timedelta(seconds=2)).isoformat(), window_seconds=2
        )
        self.assertEqual(out["quote_events"], 0)
        out = summarize(
            qs,
            [],
            (AT + timedelta(seconds=2)).isoformat(),
            window_seconds=2,
            clock="EVENT_TIME_REPLAY",
        )
        self.assertEqual(out["quote_events"], 2)
        self.assertFalse(out["execution_data_eligible"])

    def test_duplicates_do_not_manufacture_intensity(self):
        qs = [quote(0), quote(1)]
        out = summarize(
            qs + qs, [], (AT + timedelta(seconds=2)).isoformat(), window_seconds=2
        )
        self.assertEqual(out["quote_events"], 2)
        self.assertEqual(out["rejected"]["DUPLICATE"], 2)

    def test_trade_quote_join_excludes_equal_or_future_quote(self):
        out = summarize(
            [quote(0), quote(1)],
            [trade(0), trade(0.5)],
            (AT + timedelta(seconds=2)).isoformat(),
            window_seconds=2,
        )
        self.assertEqual(out["matched_trades"], 1)
        self.assertEqual(out["features"]["signed_volume_ratio_proxy"], 1)
        self.assertAlmostEqual(out["features"]["effective_spread_bps"], 200)

    def test_missing_trade_flow_is_not_zero(self):
        out = summarize(
            [quote(0), quote(1)],
            [],
            (AT + timedelta(seconds=2)).isoformat(),
            window_seconds=2,
        )
        self.assertIsNone(out["features"]["signed_volume_ratio_proxy"])

    def test_future_markout_is_an_outcome_only(self):
        qs = [quote(0), quote(1, 100, 102), quote(2, 101, 103)]
        labels = markouts(qs, [trade(1)], horizon_seconds=1)
        self.assertEqual(labels[0]["use"], "OUTCOME_ONLY_NOT_FEATURE")
        self.assertGreater(labels[0]["signed_markout_bps"], 0)

    def test_additional_cost_cannot_increase_profit(self):
        c = candidate()
        returns = np.array([-0.1, 0, 0.1])
        base = pnl_lot(c, returns, Config())
        fund = instrument(c, Config())[0]
        c["extra_slippage_bps_per_side"] = 5
        self.assertTrue(np.all(pnl_lot(c, returns, Config()) < base))
        self.assertGreater(instrument(c, Config())[0], fund)
        c["extra_slippage_bps_per_side"] = -1
        with self.assertRaises(ValueError):
            pnl_lot(c, returns, Config())

    def test_live_guard_requires_warmup(self):
        cfg = {
            "stockFeed": "sip",
            "quant": {"microstructure": {"enabled": True, "required": True}},
        }
        with self.assertRaisesRegex(ValueError, "WARMUP"):
            guard("A", "equity", {}, cfg, AT.isoformat(), 24)

    def test_live_guard_measures_but_does_not_invent_support_model(self):
        qs = [quote(i - 300, 100, 100.02) for i in range(301)]
        cfg = {
            "stockFeed": "sip",
            "quant": {"microstructure": {"enabled": True, "required": True}},
        }
        market = {
            "micro_data": {
                "A": {
                    "feed": "sip",
                    "quotes": qs,
                    "trades": [],
                    "sampling_schema": "ALPACA_L1_LAST_PER_SECOND",
                }
            }
        }
        out = guard("A", "equity", market, cfg, AT.isoformat(), 24)
        self.assertEqual(out["extra_slippage_bps_per_side"], 0)
        self.assertEqual(out["support_status"], "UNCALIBRATED_NO_SUPPORT_ADJUSTMENT")

    def test_feed_mismatch_blocks_guard(self):
        cfg = {"stockFeed": "sip", "quant": {"microstructure": {"enabled": True}}}
        with self.assertRaisesRegex(ValueError, "FEED"):
            guard(
                "A",
                "equity",
                {"micro_data": {"A": {"feed": "iex"}}},
                cfg,
                AT.isoformat(),
                24,
            )


class CurvesTests(unittest.TestCase):
    def test_surface_is_finite_and_psd(self):
        c = curve()
        validate_surface(c)
        self.assertEqual(len(c["vector"]), 6)
        self.assertGreater(
            np.linalg.eigvalsh(c["spectrum"]["correlation_shrunk_psd"]).min(), -1e-10
        )
        self.assertFalse(c["trade_authorization"])

    def test_future_bars_cannot_change_curve(self):
        p = panel()
        a = surface(p, AT.isoformat(), feed="sip", windows=(32,), lags=(0,))
        p["A"].append(
            {
                **p["A"][-1],
                "start": AT.isoformat(),
                "end": (AT + timedelta(minutes=5)).isoformat(),
                "close": 100000,
            }
        )
        b = surface(p, AT.isoformat(), feed="sip", windows=(32,), lags=(0,))
        self.assertEqual(a["vector"], b["vector"])

    def test_frequency_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "FREQUENCY"):
            surface(panel(), AT.isoformat(), feed="sip", bar_seconds=900)

    def test_missing_timestamps_are_not_forward_filled(self):
        p = panel(50)
        p["B"] = p["B"][::2]
        with self.assertRaisesRegex(ValueError, "WARMUP"):
            surface(p, AT.isoformat(), feed="sip", windows=(32,), lags=(0,))

    def test_clock_and_origin_schema_segregation(self):
        with tempfile.TemporaryDirectory() as d:
            db = CurveStore(Path(d) / "curves.db")
            c = curve()
            db.add(c, AT.isoformat())
            q = copy.deepcopy(c)
            q["asof"] = (AT + timedelta(days=2)).isoformat()
            self.assertEqual(len(db.nearest(q, q["asof"])["neighbors"]), 1)
            for field, value in [
                ("origin", "OBSERVED"),
                ("feed", "iex"),
                ("clock", "EVENT_TIME_REPLAY"),
            ]:
                other = copy.deepcopy(q)
                other[field] = value
                self.assertEqual(db.nearest(other, q["asof"])["neighbors"], [])
            db.close()

    def test_registry_persists_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "curves.db"
            db = CurveStore(p)
            c = curve()
            identity = db.add(c, AT.isoformat())
            self.assertEqual(identity, db.add(c, AT.isoformat()))
            db.close()
            db = CurveStore(p)
            self.assertEqual(db.get(identity)["curve"], c)
            db.close()

    def test_registry_integrity_detects_vector_corruption(self):
        with tempfile.TemporaryDirectory() as d:
            db = CurveStore(Path(d) / "curves.db")
            identity = db.add(curve(), AT.isoformat())
            db.db.execute(
                "UPDATE curves SET vector=? WHERE id=?",
                (np.zeros(6, dtype="<f8").tobytes(), identity),
            )
            db.db.commit()
            with self.assertRaisesRegex(ValueError, "INTEGRITY"):
                db.get(identity)
            db.close()

    def test_future_availability_and_embargo_block_analogs(self):
        with tempfile.TemporaryDirectory() as d:
            db = CurveStore(Path(d) / "curves.db")
            c = curve()
            later = (AT + timedelta(days=3)).isoformat()
            db.add(c, later)
            q = copy.deepcopy(c)
            q["asof"] = (AT + timedelta(days=2)).isoformat()
            self.assertEqual(db.nearest(q, q["asof"])["neighbors"], [])
            q["asof"] = (AT + timedelta(days=4)).isoformat()
            self.assertEqual(
                db.nearest(q, q["asof"], embargo_seconds=5 * 86400)["neighbors"], []
            )
            self.assertEqual(len(db.nearest(q, q["asof"])["neighbors"]), 1)
            db.close()

    def test_cell_tampering_rejected(self):
        c = curve()
        c["vector"][0] = 0.9
        with self.assertRaisesRegex(ValueError, "INTEGRITY"):
            validate_surface(c)

    def test_resampling_requires_three_closed_bars(self):
        rows = panel(9)["A"]
        out = resample_15min(rows, 5)
        self.assertEqual(len(out), 3)
        self.assertEqual(out[0]["volume"], 30)
        rows.pop(1)
        self.assertEqual(len(resample_15min(rows, 5)), 2)


class SupportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = cost_panel()
        cls.available = "2026-09-01T15:00:00+00:00"
        cls.model = fit_support(cls.data, cls.available)

    def test_purged_walkforward_and_holdout(self):
        self.assertEqual(len(self.model["walkforward_folds"]), 3)
        for fold in self.model["walkforward_folds"]:
            self.assertLess(fold["train_max_label_end"], fold["test_first_at"])
        self.assertLess(
            self.model["train_max_label_end"][:10], self.model["calibration_start"]
        )
        self.assertFalse(self.model["trade_authorization"])

    def test_safe_json_export_and_synthetic_not_operational(self):
        model = json.loads(json.dumps(self.model))
        result = evaluate_support(
            model,
            {"spread_tw_bps": 5, "imbalance_tw": 0},
            "2026-09-02T15:00:00+00:00",
            "sip",
            24,
        )
        self.assertFalse(result["operational"])
        self.assertGreaterEqual(result["cost_extra_roundtrip_bps"], 0)
        self.assertIn("anomaly_score", result)

    def test_future_model_and_feed_and_sampling_rejected(self):
        for at, feed, sampling in [
            ("2026-08-01T15:00:00+00:00", "sip", "FULL_EVENT_CAPTURE"),
            ("2026-09-02T15:00:00+00:00", "iex", "FULL_EVENT_CAPTURE"),
            ("2026-09-02T15:00:00+00:00", "sip", "ALPACA_L1_LAST_PER_SECOND"),
        ]:
            with self.assertRaisesRegex(ValueError, "AGE_FEED_HORIZON"):
                evaluate_support(
                    self.model,
                    {"spread_tw_bps": 5, "imbalance_tw": 0},
                    at,
                    feed,
                    24,
                    sampling,
                )

    def test_model_tampering_rejected(self):
        model = copy.deepcopy(self.model)
        model["svr"]["intercept"] += 1
        with self.assertRaisesRegex(ValueError, "INTEGRITY"):
            evaluate_support(model, {}, "2026-09-02T15:00:00+00:00", "sip", 24)

    def test_holdout_targets_do_not_change_fitted_vectors_or_scaler(self):
        data = copy.deepcopy(self.data)
        for r in data["rows"][-48:]:
            r["target_extra_bps"] += 100
        other = fit_support(data, self.available)
        self.assertEqual(other["svr"], self.model["svr"])
        self.assertEqual(other["scaler"], self.model["scaler"])

    def test_future_labels_are_rejected(self):
        data = copy.deepcopy(self.data)
        data["rows"][0]["label_known_at"] = "2027-01-01T00:00:00+00:00"
        with self.assertRaisesRegex(ValueError, "CLOCK"):
            fit_support(data, self.available)

    def test_out_of_distribution_is_detected(self):
        out = evaluate_support(
            self.model,
            {"spread_tw_bps": 500, "imbalance_tw": 0},
            "2026-09-02T15:00:00+00:00",
            "sip",
            24,
        )
        self.assertTrue(out["anomaly"])
        self.assertEqual(out["status"], "FEATURE_DRIFT")

    def test_entirely_missing_column_cannot_be_calibrated(self):
        with self.assertRaisesRegex(ValueError, "ENTIRELY_MISSING"):
            scaling(matrix([{"features": {"a": None}}], ["a"]))

    def test_kernel_dimensions_cannot_be_forged(self):
        with self.assertRaisesRegex(ValueError, "SCHEMA"):
            kernel_output(self.model["svr"], np.zeros((1, 3)))


class DataTests(unittest.TestCase):
    def test_pagination_reaches_all_symbols_and_preserves_receipt(self):
        calls = []

        def transport(path, params):
            calls.append((path, params))
            return (
                {"quotes": {"A": [quote(0)]}, "next_page_token": "p2"}
                if len(calls) == 1
                else {"quotes": {"B": [quote(1)]}, "next_page_token": None}
            )

        out = AlpacaData("FAKE", "FAKE", transport).collect(
            ["A", "B"],
            "quotes",
            AT.isoformat(),
            (AT + timedelta(minutes=1)).isoformat(),
            feed="sip",
        )
        self.assertEqual(out["pages"], 2)
        self.assertTrue(out["complete"])
        self.assertIn("known_at", out["quotes"]["B"][0])
        self.assertEqual(calls[1][1]["page_token"], "p2")

    def test_repeated_token_cannot_loop(self):
        api = AlpacaData(
            "FAKE", "FAKE", lambda p, q: {"quotes": {}, "next_page_token": "same"}
        )
        with self.assertRaisesRegex(ValueError, "REPEATED"):
            api.collect(
                ["A"],
                "quotes",
                AT.isoformat(),
                (AT + timedelta(minutes=1)).isoformat(),
                feed="sip",
            )

    def test_page_budget_is_explicitly_partial(self):
        api = AlpacaData(
            "FAKE", "FAKE", lambda p, q: {"quotes": {}, "next_page_token": "more"}
        )
        out = api.collect(
            ["A"],
            "quotes",
            AT.isoformat(),
            (AT + timedelta(minutes=1)).isoformat(),
            feed="sip",
            max_pages=1,
        )
        self.assertFalse(out["complete"])

    def test_data_adapter_never_accepts_trading_action_or_ambiguous_feed(self):
        api = AlpacaData("FAKE", "FAKE", lambda p, q: {})
        for kind, feed in [("orders", "sip"), ("quotes", "UNKNOWN")]:
            with self.assertRaises(ValueError):
                api.collect(
                    ["A"],
                    kind,
                    AT.isoformat(),
                    (AT + timedelta(minutes=1)).isoformat(),
                    feed=feed,
                )

    def test_missing_credentials_report_only_requirement(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "CREDENTIALS_REQUIRED"):
                AlpacaData()


class RegimeSupportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from harpoon_quant.regimes import fit_regime

        rng = np.random.default_rng(502)
        cls.data = {
            "origin": "SYNTHETIC_ENGINEERING_ONLY",
            "clock": "LIVE_RECEIPT",
            "feed": "sip",
            "surface_schema_hash": "SYNTHETIC_SCHEMA",
            "feature_names": ["mean_corr", "pc1"],
            "rows": [],
        }
        for i in range(180):
            at = (datetime(2026, 1, 1, 15, tzinfo=UTC) + timedelta(days=i)).isoformat()
            cls.data["rows"].append(
                {
                    "at": at,
                    "known_at": at,
                    "features": {
                        "mean_corr": float(rng.normal(0.4, 0.05)),
                        "pc1": float(rng.uniform(0.4, 0.8)),
                    },
                }
            )
        cls.model = fit_regime(cls.data, "2026-07-01T15:00:00+00:00")

    def row(self):
        return {
            **{
                k: self.data[k]
                for k in (
                    "origin",
                    "clock",
                    "feed",
                    "surface_schema_hash",
                    "feature_names",
                )
            },
            "at": "2026-07-02T15:00:00+00:00",
            "features": {"mean_corr": 0.4, "pc1": 0.6},
        }

    def test_compact_curve_features_are_finite(self):
        from harpoon_quant.regimes import regime_features

        r = regime_features(curve())
        self.assertLess(len(r["feature_names"]), 256)
        self.assertTrue(np.isfinite(list(r["features"].values())).all())

    def test_regime_svm_scores_without_authorizing_a_trade(self):
        from harpoon_quant.regimes import evaluate_regime

        result = evaluate_regime(self.model, self.row(), self.row()["at"])
        self.assertIn("novel", result)
        self.assertFalse(result["trade_authorization"])

    def test_regime_svm_detects_out_of_domain_curve_shape(self):
        from harpoon_quant.regimes import evaluate_regime

        r = self.row()
        r["features"]["mean_corr"] = -0.99
        self.assertTrue(evaluate_regime(self.model, r, r["at"])["novel"])

    def test_curve_universe_schema_is_bound_to_model(self):
        from harpoon_quant.regimes import evaluate_regime

        r = self.row()
        r["surface_schema_hash"] = "DIFFERENT_UNIVERSE"
        with self.assertRaisesRegex(ValueError, "DOMAIN"):
            evaluate_regime(self.model, r, r["at"])

    def test_historical_backfill_cannot_impersonate_live_arrival(self):
        from harpoon_quant.regimes import fit_regime

        d = copy.deepcopy(self.data)
        d["rows"][0]["known_at"] = "2026-06-30T00:00:00+00:00"
        with self.assertRaisesRegex(ValueError, "LATE_LIVE"):
            fit_regime(d, "2026-07-01T15:00:00+00:00")


class FreshnessTests(unittest.TestCase):
    def test_live_surface_rejects_stale_bars_while_replay_is_explicit(self):
        later = (AT + timedelta(hours=1)).isoformat()
        with self.assertRaisesRegex(ValueError, "STALE_LIVE"):
            surface(panel(), later, feed="sip", windows=(32,), lags=(0,))
        c = surface(
            panel(),
            later,
            feed="sip",
            clock="EVENT_TIME_REPLAY",
            windows=(32,),
            lags=(0,),
        )
        self.assertEqual(c["observations"]["A"]["age_seconds"], 3600)


class PanelAgeTests(unittest.TestCase):
    def test_refitting_an_old_cost_panel_does_not_refresh_its_data(self):
        with self.assertRaisesRegex(ValueError, "STALE_SUPPORT_PANEL"):
            fit_support(cost_panel(), "2026-12-01T00:00:00+00:00")

    def test_refitting_an_old_regime_panel_does_not_refresh_its_data(self):
        from harpoon_quant.regimes import fit_regime

        if not hasattr(RegimeSupportTests, "data"):
            RegimeSupportTests.setUpClass()
        with self.assertRaisesRegex(ValueError, "STALE_REGIME_PANEL"):
            fit_regime(RegimeSupportTests.data, "2026-12-01T00:00:00+00:00")


class ModelRoutingTests(unittest.TestCase):
    def test_unrelated_feed_does_not_apply_or_block_a_ready_domain(self):
        d = cost_panel()
        d.update(
            feed="us", book_scope="crypto", sampling_schema="ALPACA_L1_LAST_PER_SECOND"
        )
        model = fit_support(d, "2026-09-01T15:00:00+00:00")
        self._guard(model, "NO_CALIBRATED_MODEL_FOR_DOMAIN")

    def test_bundle_selects_exact_domain_and_keeps_synthetic_adjustment_off(self):
        d = cost_panel()
        d.update(book_scope="equity", sampling_schema="ALPACA_L1_LAST_PER_SECOND")
        model = fit_support(d, "2026-09-01T15:00:00+00:00")
        self._guard({"schema": "HARPOON_SUPPORT_BUNDLE_1", "models": [model]}, None)

    def _guard(self, model, status):
        at = datetime(2026, 9, 2, 15, tzinfo=UTC)
        qs = [
            {
                "t": (at - timedelta(seconds=300 - i)).isoformat(),
                "bp": 100,
                "ap": 100.02,
                "bs": 40,
                "as": 50,
            }
            for i in range(301)
        ]
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "model.json"
            p.write_text(json.dumps(model))
            cfg = {
                "stockFeed": "sip",
                "quant": {
                    "microstructure": {
                        "enabled": True,
                        "required": True,
                        "modelFile": str(p),
                    }
                },
            }
            market = {
                "micro_data": {
                    "A": {
                        "feed": "sip",
                        "quotes": qs,
                        "trades": [],
                        "sampling_schema": "ALPACA_L1_LAST_PER_SECOND",
                    }
                }
            }
            result = guard("A", "equity", market, cfg, at.isoformat(), 24)
            if status:
                self.assertEqual(result["support_status"], status)
            else:
                self.assertIn("support", result)
            self.assertEqual(result["extra_slippage_bps_per_side"], 0)
