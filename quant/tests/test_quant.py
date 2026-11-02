import copy
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import numpy as np

from harpoon_quant.calibration import block_lower, fit
from harpoon_quant.core import (
    FEATURES,
    Config,
    allocate,
    covariance,
    expected_shortfall,
    features,
    instrument,
    option_price,
    pnl_lot,
)

NOW = "2026-10-29T14:00:00+00:00"


def calibration(mu=0.03):
    dates = [f"2026-09-{i:02}" for i in range(1, 29)]
    models = {
        s: {
            "accepted": True,
            "mean": [0] * 8,
            "scale": [1] * 8,
            "beta": [mu] + [0] * 8,
            "residuals": {d: (i % 5 - 2) * 0.002 for i, d in enumerate(dates)},
            "iv_residuals": {d: (i % 3 - 1) * 0.02 for i, d in enumerate(dates)},
        }
        for s in "ABCDE"
    }
    return {
        "origin": "SYNTHETIC_ENGINEERING_ONLY",
        "available_at": "2026-10-28T14:00:00+00:00",
        "horizon_hours": 24,
        "feature_names": list(FEATURES),
        "models": models,
    }


def candidate(book="equity", name="A"):
    c = {
        "id": name + "-" + book,
        "symbol": name,
        "underlying": name,
        "book": book,
        "factor": name,
        "spot": 100,
        "bid": 99.95,
        "ask": 100.05,
        "lot_qty": 1,
        "multiplier": 1,
        "step": 1,
        "quote_at": NOW,
        "known_at": NOW,
        "asof": NOW,
        "features": [0] * 8,
        "max_qty": 100,
    }
    if book == "options":
        c.update(
            bid=5,
            ask=5.02,
            multiplier=100,
            delta=0.5,
            iv=0.30,
            rate=0.03,
            dividend_yield=0,
            strike=100,
            right="call",
            style="american",
            expiry_at="2026-12-18T21:00:00+00:00",
            lifecycle_reviewed=True,
            fee_per_side_usd=0.10,
        )
    if book == "crypto":
        c.update(lot_qty=0.1, step=0.0001, fee_per_side_usd=0.25)
    if book == "futures":
        c.update(
            initial_margin_usd=25,
            margin_verified=True,
            roll_reviewed=True,
            fee_per_side_usd=0.10,
        )
    return c


def request(cs):
    return {
        "asof": NOW,
        "account": {
            "equity": 20000,
            "cash": 20000,
            "buying_power": 20000,
            "pending_cash": 0,
            "daily_pnl": 0,
            "drawdown_fraction": 0,
        },
        "candidates": cs,
        "holdings": [],
    }


class QuantTests(unittest.TestCase):
    def test_fractional_tail_es(self):
        self.assertAlmostEqual(
            expected_shortfall(np.array([1, 2, 3, 4]), 0.625), (4 + 0.5 * 3) / 1.5
        )

    def test_es_worst_only(self):
        self.assertEqual(expected_shortfall(np.array([-2, 0, 10]), 0.95), 10)

    def test_covariance_psd(self):
        s = covariance(np.array([[1, 2, 3], [2, 4, 6], [3, 6, 9]], float))
        self.assertGreaterEqual(np.linalg.eigvalsh(s).min(), 0)
        np.testing.assert_allclose(s, s.T)

    def test_put_call_parity(self):
        s = np.array([80.0, 100.0, 120.0])
        v = np.full(3, 0.2)
        c = option_price(s, 100, 0.5, v, 0.03, 0.01, "call")
        p = option_price(s, 100, 0.5, v, 0.03, 0.01, "put")
        np.testing.assert_allclose(
            c - p, s * np.exp(-0.005) - 100 * np.exp(-0.015), atol=1e-10
        )

    def test_american_put_bounds(self):
        s = np.array([60.0, 90.0, 100.0])
        v = np.full(3, 0.3)
        a = option_price(s, 100, 0.5, v, 0.05, 0, "put", "american")
        e = option_price(s, 100, 0.5, v, 0.05, 0, "put")
        self.assertTrue(np.all(a >= np.maximum(100 - s, e) - 0.03))

    def test_expiry_payoff(self):
        np.testing.assert_equal(
            option_price(
                np.array([80.0, 120.0]), 100, 0, np.array([0.2, 0.2]), 0, 0, "call"
            ),
            [0, 20],
        )

    def test_multiplier_dimensions(self):
        c = candidate()
        r = np.array([0.02])
        one = pnl_lot(c, r, Config())
        c["multiplier"] = 10
        np.testing.assert_allclose(pnl_lot(c, r, Config()), 10 * one)

    def test_spread_monotonicity(self):
        c = candidate()
        r = np.array([0.02])
        p = pnl_lot(c, r, Config())
        c.update(bid=99, ask=101)
        self.assertLess(pnl_lot(c, r, Config())[0], p[0])

    def test_fee_dimensions(self):
        c = candidate()
        r = np.array([0.02])
        p = pnl_lot(c, r, Config())[0]
        c["fee_per_side_usd"] = 0.5
        self.assertAlmostEqual(p - pnl_lot(c, r, Config())[0], 1)

    def test_operable_lots(self):
        c = candidate("crypto")
        instrument(c, Config())
        c["book"] = "equity"
        with self.assertRaisesRegex(ValueError, "WHOLE"):
            instrument(c, Config())

    def test_five_asset_valuations_and_allocations(self):
        for book in ("equity", "etf", "crypto", "options", "futures"):
            with self.subTest(book=book):
                out = allocate(request([candidate(book)]), calibration(), Config())
                self.assertTrue(out["selected"], out)
                self.assertFalse(out["execution_allowed"])
                self.assertFalse(out["liveApproved"])

    def test_cash_integrality(self):
        r = request([candidate()])
        r["account"]["cash"] = 250
        out = allocate(r, calibration(), Config())
        q = out["selected"][0]["quantity"]
        self.assertEqual(q, int(q))
        self.assertLessEqual(out["cash_committed_usd"], 250)

    def test_tail_limits(self):
        out = allocate(
            request(
                [
                    candidate("equity", "A"),
                    candidate("etf", "B"),
                    candidate("crypto", "C"),
                    candidate("futures", "D"),
                ]
            ),
            calibration(),
            Config(),
        )
        self.assertLessEqual(out["cvar_usd"], 400 + 1e-5)
        self.assertLessEqual(out["stress_worst_loss_usd"], 1000 + 1e-5)
        self.assertLessEqual(out["partial_fill_cvar_upper_usd"], 400 + 1e-5)
        self.assertLessEqual(out["partial_fill_stress_upper_usd"], 1000 + 1e-5)

    def test_every_subset_of_new_fills_respects_tail_and_stress_limits(self):
        from itertools import combinations

        from harpoon_quant.core import scenarios

        cs = [candidate("equity", "A"), candidate("etf", "B"), candidate("crypto", "C")]
        cfg = Config(asset_fraction=0.25)
        cal = calibration()
        out = allocate(request(cs), cal, cfg)
        base, shock, _ = scenarios(cal, {c["underlying"]: 0.03 for c in cs}, cfg)
        self.assertTrue(out["selected"])
        selected = out["selected"]
        for count in range(len(selected) + 1):
            for subset in combinations(selected, count):
                values = np.zeros(cfg.scenarios)
                stresses = np.zeros(3)
                for item in subset:
                    c = next(c for c in cs if c["id"] == item["id"])
                    values += item["lots"] * pnl_lot(c, base[c["underlying"]], cfg)
                    stresses += item["lots"] * pnl_lot(
                        c, shock[c["underlying"]], cfg, stress=True
                    )
                self.assertLessEqual(
                    expected_shortfall(-values, cfg.cvar_alpha), 400 + 1e-5
                )
                self.assertLessEqual(-stresses.min(), 1000 + 1e-5)

    def test_cash_dominates_negative_edge(self):
        self.assertEqual(
            allocate(request([candidate()]), calibration(mu=-0.03), Config())[
                "selected"
            ],
            [],
        )

    def test_stale_quote(self):
        c = candidate()
        c["quote_at"] = "2026-10-29T13:00:00+00:00"
        self.assertEqual(
            allocate(request([c]), calibration(), Config())["selected"], []
        )

    def test_future_calibration(self):
        c = calibration()
        c["available_at"] = "2026-10-30T00:00:00+00:00"
        self.assertEqual(allocate(request([candidate()]), c, Config())["selected"], [])

    def test_unmodeled_holdings(self):
        r = request([candidate()])
        r["holdings"] = [candidate("equity", "UNKNOWN")]
        self.assertEqual(
            allocate(r, calibration(), Config())["reason"], "UNMODELED_OPEN_INVENTORY"
        )

    def test_futures_margin_gate(self):
        c = candidate("futures")
        c.pop("initial_margin_usd")
        self.assertEqual(
            allocate(request([c]), calibration(), Config())["selected"], []
        )

    def test_option_joint_iv_gate(self):
        cal = calibration()
        cal["models"]["A"].pop("iv_residuals")
        self.assertEqual(
            allocate(request([candidate("options")]), cal, Config())["selected"], []
        )

    def test_duplicate_underlying(self):
        self.assertLessEqual(
            len(
                allocate(
                    request([candidate(), candidate("etf")]), calibration(), Config()
                )["selected"]
            ),
            1,
        )

    def test_fixed_fees_cannot_manufacture_profit(self):
        c = candidate()
        self.assertTrue(allocate(request([c]), calibration(), Config())["selected"])
        c["fixed_fee_usd"] = 10000
        self.assertEqual(
            allocate(request([c]), calibration(), Config())["selected"], []
        )

    def test_selected_receipts_include_fixed_fees_and_reconcile_to_portfolio(self):
        c = candidate()
        c["fixed_fee_usd"] = 5
        out = allocate(request([c]), calibration(), Config())
        self.assertTrue(out["selected"])
        for field in ("expected_net_usd", "cash_committed_usd"):
            self.assertAlmostEqual(sum(s[field] for s in out["selected"]), out[field])
        self.assertAlmostEqual(
            sum(s["robust_net_usd"] for s in out["selected"]),
            out["robust_incremental_usd"],
        )

    def test_pending_reservations(self):
        r = request([candidate()])
        r["account"]["pending_cash"] = 20000
        self.assertEqual(allocate(r, calibration(), Config())["selected"], [])

    def test_loss_pause(self):
        r = request([candidate()])
        r["account"]["daily_pnl"] = -2000
        self.assertEqual(
            allocate(r, calibration(), Config())["reason"], "ACCOUNT_RISK_PAUSE"
        )

    def test_deterministic(self):
        r = request([candidate(), candidate("etf", "B")])
        self.assertEqual(
            allocate(r, calibration(), Config()), allocate(r, calibration(), Config())
        )

    def test_feature_drift(self):
        c = candidate()
        c["features"][0] = 100
        self.assertEqual(
            allocate(request([c]), calibration(), Config())["selected"], []
        )

    def test_features_ignore_future(self):
        at = datetime.fromisoformat(NOW)
        rows = []
        for i in range(40):
            end = at - timedelta(minutes=5 * (39 - i))
            rows.append(
                {
                    "start": (end - timedelta(minutes=5)).isoformat(),
                    "end": end.isoformat(),
                    "known_at": end.isoformat(),
                    "close": 100 + i * 0.1,
                    "volume": 1000 + i,
                    "vwap": 100 + i * 0.1,
                    "session": "2026-10-29",
                }
            )
        historical = []
        for day in range(1, 12):
            for row in rows:
                old = dict(row)
                for name in ("start", "end", "known_at"):
                    old[name] = (
                        datetime.fromisoformat(row[name]) - timedelta(days=day)
                    ).isoformat()
                old["session"] = datetime.fromisoformat(old["start"]).date().isoformat()
                historical.append(old)
        rows = historical + rows
        q = {"at": NOW, "known_at": NOW, "bid": 103.8, "ask": 104}
        a = features(rows, q, NOW)
        rows.append(
            {
                **rows[-1],
                "end": (at + timedelta(minutes=5)).isoformat(),
                "known_at": (at + timedelta(minutes=5)).isoformat(),
                "close": 1e9,
            }
        )
        self.assertEqual(a, features(rows, q, NOW))

    def test_negative_bootstrap_skill(self):
        self.assertLess(block_lower(np.full(30, -0.001)), 0)

    def test_fit_and_purging(self):
        rng = np.random.default_rng(42)
        rows = []
        for i in range(120):
            at = datetime(2026, 1, 1, 14, tzinfo=UTC) + timedelta(days=i)
            x = rng.normal(0, 1, 8)
            rows.append(
                {
                    "session": at.date().isoformat(),
                    "underlying": "A",
                    "at": at.isoformat(),
                    "features_known_at": at.isoformat(),
                    "label_end": (at + timedelta(hours=24)).isoformat(),
                    "label_known_at": (at + timedelta(hours=24, seconds=1)).isoformat(),
                    "features": x.tolist(),
                    "target_return": 0.02 + 0.002 * x[0],
                    "iv_change": 0.01 * x[1],
                }
            )
        data = {"origin": "SYNTHETIC_ENGINEERING_ONLY", "rows": rows}
        m = fit(data, "2026-06-01T00:00:00+00:00", Config())
        self.assertTrue(m["models"]["A"]["accepted"])
        self.assertFalse(m["liveApproved"])
        self.assertLess(
            m["models"]["A"]["train_max_label_end"], m["models"]["A"]["first_test_at"]
        )
        bad = copy.deepcopy(data)
        bad["rows"][0]["features_known_at"] = "2027-01-01T00:00:00+00:00"
        with self.assertRaisesRegex(ValueError, "CLOCK"):
            fit(bad, "2026-06-01T00:00:00+00:00", Config())


class JointDecisionTests(unittest.TestCase):
    def test_net_forecast_replaces_heuristic_rank(self):
        a = candidate("equity", "A")
        a["legacy_score"] = 9999
        b = candidate("equity", "B")
        b["legacy_score"] = 1
        cal = calibration()
        cal["models"]["A"]["beta"][0] = 0.02
        cal["models"]["B"]["beta"][0] = 0.05
        r = request([a, b])
        r["account"]["cash"] = 250
        result = allocate(r, cal, replace(Config(), max_positions=1))
        self.assertEqual(result["selected"][0]["symbol"], "B")

    def test_equivalent_feature_units_for_same_underlying(self):
        a = candidate()
        b = candidate("etf")
        b["features"][0] = 0.1
        result = allocate(request([a, b]), calibration(), Config())
        self.assertIn(
            "INCONSISTENT_UNDERLYING_FEATURES", result["rejected"].get(b["id"], "")
        )

    def test_bad_delta_cannot_lower_exposure_artificially(self):
        c = candidate("options")
        c["delta"] = 5
        self.assertEqual(
            allocate(request([c]), calibration(), Config())["selected"], []
        )


class ConvexityTests(unittest.TestCase):
    def test_put_can_benefit_from_negative_underlying_forecast(self):
        c = candidate("options")
        c.update(right="put", delta=-0.5)
        result = allocate(request([c]), calibration(mu=-0.03), Config())
        self.assertTrue(result["selected"], result)
        self.assertGreater(result["expected_net_usd"], 0)
        self.assertFalse(result["execution_allowed"])


class RuntimeNormalizationTests(unittest.TestCase):
    def test_exchange_calendar_handles_early_close_and_closed_days(self):
        from harpoon_quant.bridge import bars as normalize_bars

        start = datetime.fromisoformat("2026-11-27T17:55:00+00:00")
        calendar = [
            {
                "date": "2026-11-27",
                "open": (start - timedelta(hours=3, minutes=25)).timestamp() * 1000,
                "close": (start + timedelta(minutes=5)).timestamp() * 1000,
            }
        ]
        raw = [
            {"t": at.isoformat(), "c": 100, "v": 1, "vw": 100}
            for at in [
                start,
                start + timedelta(minutes=3),
                start + timedelta(minutes=5),
                start + timedelta(days=1),
            ]
        ]
        out = normalize_bars(raw, "equity", "2026-11-28T20:00:00+00:00", calendar)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["end"], "2026-11-27T18:00:00+00:00")

    def test_equity_calendar_cannot_be_inferred_from_wall_clock(self):
        from harpoon_quant.bridge import bars as normalize_bars

        with self.assertRaisesRegex(ValueError, "EXCHANGE_CALENDAR_REQUIRED"):
            normalize_bars([], "equity", NOW)

    def test_stock_runtime_snapshot_reaches_shared_allocator(self):
        from harpoon_quant.bridge import bars as normalize_bars
        from harpoon_quant.bridge import from_runtime

        at = datetime.fromisoformat(NOW)
        history = []
        for day in range(12, -1, -1):
            for j in range(18):
                start = at - timedelta(days=day, minutes=5 * (18 - j))
                price = 100 + j * 0.02
                history.append(
                    {
                        "t": start.isoformat(),
                        "o": price - 0.01,
                        "h": price + 0.01,
                        "l": price - 0.02,
                        "c": price,
                        "v": 10000 + j,
                        "vw": price - 0.005,
                    }
                )
        calendar = []
        for day in range(12, -1, -1):
            opening = (at - timedelta(days=day)).replace(hour=13, minute=30)
            calendar.append(
                {
                    "date": opening.date().isoformat(),
                    "open": opening.timestamp() * 1000,
                    "close": (opening + timedelta(hours=6, minutes=30)).timestamp()
                    * 1000,
                }
            )
        # Explicit fabricated calendar: numerical fixture, not exchange evidence.
        market = {
            "assets": {
                "A": {
                    "book": "equity",
                    "factor": "tech",
                    "multiplier": 1,
                    "step": 1,
                    "minQty": 1,
                }
            },
            "quotes": {
                "A": {
                    "bid": 100.34,
                    "ask": 100.36,
                    "at": at.timestamp() * 1000,
                    "received": at.timestamp() * 1000,
                }
            },
            "bars": {"A": history, "SPY": history},
            "snapshots": {},
            "calendar": calendar,
        }
        raw = {
            "now": at.timestamp() * 1000,
            "config": {
                "maxPositions": 4,
                "totalExposure": 1,
                "assetExposure": 0.35,
                "factorExposure": 0.6,
                "dailyLoss": 0.05,
                "maxDrawdown": 0.1,
                "slippageBps": 10,
                "quoteAgeMs": 15000,
                "optionsFeePerContract": 0.1,
                "cryptoFeeBps": 25,
            },
            "market": market,
            "signals": [{"plugin": "qa", "symbol": "A", "entry": 100.36, "max_qty": 5}],
            "positions": [],
            "pending": [],
            "account": {"equity": 20000, "cash": 20000, "buying_power": 20000},
        }
        cal = calibration()
        x = features(
            normalize_bars(history, "equity", NOW, calendar),
            {"bid": 100.34, "ask": 100.36, "at": NOW, "known_at": NOW},
            NOW,
            normalize_bars(history, "equity", NOW, calendar),
        )
        cal["models"]["A"]["mean"] = x
        out = from_runtime(raw, cal)
        self.assertTrue(out["selected"], out)
        self.assertFalse(out["execution_allowed"])
        self.assertLessEqual(out["selected"][0]["quantity"], 5)
