"""Synthetic regressions for causal Ridge fitting and funded lot sizing.

These cases validate contracts, not observed returns or order authorization.
"""

import copy
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import numpy as np
from test_quant import calibration, candidate, request

from harpoon_quant import calibration as calibration_module
from harpoon_quant.core import Config, allocate, instrument, pnl_lot, timestamp


def synthetic_panel():
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
            }
        )
    return {"origin": "SYNTHETIC_ENGINEERING_ONLY", "rows": rows}


class RidgeAvailabilityTests(unittest.TestCase):
    def fit_audited(self, data):
        calls = []
        original = calibration_module.ridge

        def audited_fit(rows, penalty):
            calls.append(copy.deepcopy(rows))
            return original(rows, penalty)

        with patch.object(calibration_module, "ridge", audited_fit):
            result = calibration_module.fit(data, "2026-06-01T00:00:00+00:00", Config())
        return result, calls

    def test_label_unavailable_at_both_boundaries_is_never_fitted(self):
        data = synthetic_panel()
        late = data["rows"][10]
        late["label_known_at"] = data["rows"][100]["at"]
        model, calls = self.fit_audited(data)
        self.assertEqual(len(calls), 4)
        for rows in calls:
            self.assertNotIn(late["at"], {r["at"] for r in rows})
        final = model["models"]["A"]
        self.assertLess(
            timestamp(final["selection_train_max_label_known_at"]),
            timestamp(model["validation_start"] + "T00:00:00+00:00"),
        )
        self.assertLess(
            timestamp(final["train_max_label_known_at"]),
            timestamp(model["test_start"] + "T00:00:00+00:00"),
        )

    def test_validation_label_unavailable_at_test_boundary_is_not_refitted(self):
        data = synthetic_panel()
        late = data["rows"][80]
        late["label_known_at"] = data["rows"][100]["at"]
        _, calls = self.fit_audited(data)
        self.assertEqual(len(calls), 4)
        self.assertNotIn(late["at"], {r["at"] for r in calls[-1]})
        self.assertEqual(len(calls[-1]), 93)

    def test_exact_boundary_is_excluded_and_one_microsecond_before_is_allowed(self):
        data = synthetic_panel()
        rows = data["rows"]
        for exact, before, boundary_index in ((10, 11, 72), (80, 81, 96)):
            boundary = timestamp(rows[boundary_index]["at"]).replace(hour=0)
            rows[exact]["label_known_at"] = boundary.isoformat()
            rows[before]["label_known_at"] = (
                boundary - timedelta(microseconds=1)
            ).isoformat()
        _, calls = self.fit_audited(data)
        for fit_rows in calls[:3]:
            used = {r["at"] for r in fit_rows}
            self.assertNotIn(rows[10]["at"], used)
            self.assertIn(rows[11]["at"], used)
        used = {r["at"] for r in calls[-1]}
        self.assertNotIn(rows[80]["at"], used)
        self.assertIn(rows[81]["at"], used)

    def test_availability_uses_instant_and_not_local_calendar_date(self):
        data = synthetic_panel()
        data["rows"][10]["label_known_at"] = "2026-03-13T19:00:01-05:00"
        _, calls = self.fit_audited(data)
        for rows in calls:
            self.assertNotIn(data["rows"][10]["at"], {r["at"] for r in rows})

    def test_purge_can_make_calibration_insufficient_without_relabeling_data(self):
        data = synthetic_panel()
        for row in data["rows"][:40]:
            row["label_known_at"] = data["rows"][100]["at"]
        model, calls = self.fit_audited(data)
        self.assertEqual(calls, [])
        result = model["models"]["A"]
        self.assertFalse(result["accepted"])
        self.assertEqual(result["reason"], "INSUFFICIENT_PURGED_DATE_COUNTS")
        self.assertEqual(result["date_counts"], [31, 23, 24])

    def test_on_time_labels_preserve_fit_counts_and_input_bytes(self):
        data = synthetic_panel()
        before = copy.deepcopy(data)
        model, calls = self.fit_audited(data)
        self.assertEqual(data, before)
        self.assertEqual([len(rows) for rows in calls], [71, 71, 71, 94])
        self.assertTrue(model["models"]["A"]["accepted"])
        self.assertFalse(model["liveApproved"])


class FundingConsistencyTests(unittest.TestCase):
    def test_entry_hint_below_ask_cannot_buy_more_than_cash_funds(self):
        c = candidate()
        c["entry"] = 1
        r = request([c])
        r["account"].update(cash=250, buying_power=250)
        out = allocate(r, calibration(), Config())
        self.assertEqual(out["selected"][0]["quantity"], 2)
        self.assertAlmostEqual(out["cash_committed_usd"], 200.3001)
        self.assertLessEqual(out["cash_committed_usd"], 250)
        self.assertFalse(out["execution_allowed"])

    def test_funding_and_zero_return_pnl_use_identical_entry_slippage(self):
        cfg = Config(slippage_bps=10)
        for entry in (1, 100.05, 101):
            for book in ("equity", "etf", "crypto"):
                with self.subTest(entry=entry, book=book):
                    c = candidate(book)
                    c.update(
                        entry=entry, fee_per_side_usd=0.2, extra_slippage_bps_per_side=5
                    )
                    reserved, _ = instrument(c, cfg)
                    qty, multiplier = c["lot_qty"], c["multiplier"]
                    friction = (c["ask"] - c["bid"]) / 2 + c["bid"] * 15 / 10000
                    exit_mark = max(0, c["spot"] - friction)
                    self.assertAlmostEqual(
                        pnl_lot(c, np.array([0.0]), cfg)[0],
                        qty * multiplier * exit_mark - reserved,
                    )

    def test_option_funding_respects_contract_multiplier_and_fees(self):
        c = candidate("options")
        c.update(entry=1, lot_qty=2, fee_per_side_usd=0.65)
        cash, exposure = instrument(c, Config())
        self.assertAlmostEqual(cash, 2 * 100 * (5.02 + 5.02 * 0.001) + 2 * 2 * 0.65)
        self.assertEqual(exposure, 10000)

    def test_margin_funding_retains_verified_futures_contract(self):
        c = candidate("futures")
        c.update(entry=1, lot_qty=2, fee_per_side_usd=0.1)
        self.assertAlmostEqual(instrument(c, Config())[0], 50.4)

    def test_invalid_entry_fee_and_quote_fail_before_optimization(self):
        for change, reason in (
            ({"entry": 0}, "INVALID_ENTRY"),
            ({"entry": -1}, "INVALID_ENTRY"),
            ({"entry": True}, "INVALID_ENTRY"),
            ({"fee_per_side_usd": -0.01}, "NEGATIVE_FEES"),
            ({"bid": 101}, "CROSSED_QUOTE"),
        ):
            with self.subTest(change=change):
                c = candidate()
                c.update(change)
                with self.assertRaisesRegex(ValueError, reason):
                    instrument(c, Config())
                result = allocate(request([c]), calibration(), Config())
                self.assertEqual(result["selected"], [])
                self.assertIn(reason, result["rejected"][c["id"]])

    def test_overflowing_monetary_units_are_rejected(self):
        c = candidate("crypto")
        c.update(multiplier=1e308)
        with self.assertRaisesRegex(ValueError, "NONFINITE_INSTRUMENT_AMOUNT"):
            instrument(c, Config())


if __name__ == "__main__":
    unittest.main()
