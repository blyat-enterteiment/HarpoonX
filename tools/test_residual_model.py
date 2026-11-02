"""Synthetic contracts only. No files, historical prices, financial fits or ledger."""
import copy
import math
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import fmean, stdev

sys.path.insert(0, str(Path(__file__).resolve().parent))
import residual_model as rm


def fixture():
    protocol = {"recipe": dict(rm.FIXED_RECIPE), "periods": {
        "train_start": "2024-09-03", "train_end": "2025-03-05",
        "evaluation_start": "2025-03-11", "evaluation_end": "2026-10-16"},
        "scenarios": {"NOMINAL": {"spread_bps": 2, "slippage_bps": 2,
            "commission_usd_per_share_per_side": .005, "external_cost_usd_per_session": 1},
            "STRESS": {"spread_bps": 4, "slippage_bps": 4,
            "commission_usd_per_share_per_side": .01, "external_cost_usd_per_session": 2}}}
    days = []
    d = date(2024, 9, 3)
    # Fixture calendar only; holidays are supplied, not inferred by model.
    omitted = {"2024-11-28", "2024-12-25", "2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17"}
    while d <= date(2025, 3, 5):
        if d.weekday() < 5 and d.isoformat() not in omitted:
            days.append(d)
        d += timedelta(days=1)
    assert len(days) == 126
    days += [date(2025, 3, 11) + timedelta(days=i) for i in range(3)]
    sessions, series = [], {s: {"symbol": s, "root": s, "pointValue": 1, "tick": .01, "bars": []}
                            for s in (*rm.STOCKS, rm.BENCHMARK)}
    for n, day in enumerate(days):
        opening = int(datetime.combine(day, datetime.min.time(), timezone.utc).timestamp() * 1000) + (14 * 60 + 30) * 60000
        sessions.append({"date": day.isoformat(), "open": opening, "close": opening + 78 * rm.BAR_MS})
        x = .005 * math.sin(n * .2) + .002 * math.cos(n * .13)
        shocks = {"XLK": x, "AAPL": .8 * x + .0003 + .002 * math.cos(n * .41),
                  "MSFT": 1.2 * x - .0001 + .0015 * math.sin(n * .47)}
        if n >= 126:
            shocks = {"XLK": 0, "AAPL": -.008, "MSFT": -.003}
        for symbol, shock in shocks.items():
            for k in range(78):
                o = 100 * math.exp(shock * min(k, 12) / 12)
                c = 100 * math.exp(shock * min(k + 1, 12) / 12)
                t = opening + k * rm.BAR_MS
                series[symbol]["bars"].append({"t": t, "end": t + rm.BAR_MS,
                    "availableAt": t + rm.BAR_MS + 1000, "o": o, "h": max(o, c) + .3,
                    "l": min(o, c) - .3, "c": c, "v": 1000})
    data = {"schema": "HARPOON-ULTIMATE-DATA-1", "kind": "ALPACA_PROXY",
            "provenance": {"source": "SYNTHETIC_CONTRACT_ONLY", "feed": "NONE", "files": [], "execution": "MODELED_OHLCV"},
            "sessions": sessions, "splitEvents": [], "cashDividends": [], "series": list(series.values())}
    return data, protocol


def bars(data, symbol):
    return next(s["bars"] for s in data["series"] if s["symbol"] == symbol)


class ResidualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.protocol = fixture()
        cls.models = rm.fit_models(cls.data, cls.protocol)

    def changed(self):
        return copy.deepcopy(self.data), copy.deepcopy(self.protocol)

    def test_fixed_same_scale_ols_intercept_and_ddof_one(self):
        xs, ys = [], []
        for i in range(126):
            x, y = bars(self.data, "XLK")[78*i:78*i+12], bars(self.data, "AAPL")[78*i:78*i+12]
            xs.append(math.log(x[-1]["c"] / x[0]["o"]))
            ys.append(math.log(y[-1]["c"] / y[0]["o"]))
        xm, ym = fmean(xs), fmean(ys)
        beta = sum((x-xm)*(y-ym) for x, y in zip(xs, ys))/sum((x-xm)**2 for x in xs)
        residuals = [y-beta*x for x, y in zip(xs, ys)]
        model = self.models["models"]["AAPL"]
        self.assertTrue(model["available"])
        self.assertAlmostEqual(model["beta"], beta)
        self.assertAlmostEqual(model["mu"], ym-beta*xm)
        self.assertAlmostEqual(model["sigma"], stdev(residuals))
        self.assertEqual(model["n"], 126)
        self.assertEqual(self.models["counts"]["fit_invocations"], 2)

    def test_future_evaluation_values_do_not_affect_training(self):
        data, p = self.changed()
        for s in data["series"]:
            for b in s["bars"][126*78:]:
                for k in ["o", "h", "l", "c"]:
                    b[k] *= 30
        self.assertEqual(rm.fit_models(data, p), self.models)

    def test_current_future_close_not_read_and_planned_next_open(self):
        original = rm.generate_signals(self.data, self.models, self.protocol)
        data, p = self.changed()
        for s in data["series"]:
            for b in s["bars"][126*78+12:127*78]:
                for k in ["o", "h", "l", "c"]:
                    b[k] *= 30
        changed = rm.generate_signals(data, self.models, p)
        self.assertEqual(original["daily_decisions"][0], changed["daily_decisions"][0])
        signal = original["signals"]["NOMINAL"]["RESIDUAL_LONG"][0]
        session = self.data["sessions"][126]
        self.assertEqual(signal["at"], session["open"] + 60*60000 + 1000)
        self.assertEqual(signal["plannedEntryAt"], session["open"] + 65*60000)
        self.assertEqual(signal["hypothesis"], "CLOSED_CHANNEL")
        self.assertEqual(signal["metadata"]["execution_template"], "CLOSED_CHANNEL:BASELINE")
        self.assertFalse(signal["metadata"]["score_is_expected_return"])

    def test_cost_formula_and_same_event_sector_control(self):
        result = rm.generate_signals(self.data, self.models, self.protocol)
        decision = result["daily_decisions"][0]
        stock = decision["candidates"][decision["selected_symbol"]]
        self.assertAlmostEqual(decision["scenarios"]["NOMINAL"]["roundtrip_friction_fraction"], .0006+.01/stock["price"])
        self.assertAlmostEqual(decision["scenarios"]["STRESS"]["roundtrip_friction_fraction"], 2*(.0006+.01/stock["price"]))
        for scenario in result["signals"].values():
            self.assertEqual([s["at"] for s in scenario["RESIDUAL_LONG"]], [s["at"] for s in scenario["SECTOR_TIMING_CONTROL"]])
            self.assertTrue(all(s["symbol"] == "XLK" for s in scenario["SECTOR_TIMING_CONTROL"]))
            self.assertLessEqual(len(scenario["RESIDUAL_LONG"]), 3)

    def test_missing_benchmark_bar_refuses_all_policies_without_imputation(self):
        data, p = self.changed()
        del bars(data, "XLK")[126*78+5]
        r = rm.generate_signals(data, self.models, p)
        self.assertEqual(r["daily_decisions"][0]["reason"], "NO_ADMISSIBLE_STOCK")
        self.assertEqual(r["daily_decisions"][0]["candidates"]["AAPL"]["reason"], "BENCHMARK_MISSING_BAR")
        for scenario in r["signals"].values():
            self.assertTrue(all(len(signals) == 2 for signals in scenario.values()))

    def test_unavailable_last_shock_bar_refuses_only_affected_candidate(self):
        data, p = self.changed()
        bars(data, "AAPL")[126*78+11]["availableAt"] += 1
        r = rm.generate_signals(data, self.models, p)
        self.assertEqual(r["daily_decisions"][0]["candidates"]["AAPL"]["reason"], "BAR_NOT_AVAILABLE")
        self.assertEqual(r["daily_decisions"][0]["selected_symbol"], "MSFT")

    def test_drift_refusal_common_to_threshold_off(self):
        data, p = self.changed()
        for symbol in rm.STOCKS:
            for b in bars(data, symbol)[126*78:126*78+12]:
                b["c"] *= .8
                b["l"] = min(b["l"], b["c"]-.1)
        r = rm.generate_signals(data, self.models, p)
        self.assertEqual(r["daily_decisions"][0]["reason"], "NO_ADMISSIBLE_STOCK")
        self.assertEqual(r["daily_decisions"][0]["candidates"]["AAPL"]["reason"], "ABSOLUTE_Z_DRIFT_REFUSAL")

    def test_threshold_off_keeps_stock_selection_but_drops_z_and_hurdle(self):
        data, p = self.changed()
        for symbol in rm.STOCKS:
            for b in bars(data, symbol)[126*78:126*78+12]:
                b.update(o=100, h=100.3, l=99.7, c=100)
        r = rm.generate_signals(data, self.models, p)
        day = r["daily_decisions"][0]
        self.assertFalse(day["scenarios"]["NOMINAL"]["residual_proposed"])
        self.assertTrue(day["scenarios"]["NOMINAL"]["stock_threshold_off_proposed"])
        off = r["signals"]["NOMINAL"]["STOCK_THRESHOLD_OFF"][0]
        self.assertEqual(off["symbol"], day["selected_symbol"])

    def test_missing_training_sessions_fail_instead_of_extending_window(self):
        data, p = self.changed()
        del data["sessions"][0]
        with self.assertRaisesRegex(ValueError, "TRAIN_CALENDAR_REQUIRES_126"):
            rm.fit_models(data, p)

    def test_minimum_100_observations_and_record_rejections(self):
        for missing, available in [(26, True), (27, False)]:
            data, p = self.changed()
            for i in reversed(range(missing)):
                del bars(data, "AAPL")[i*78+4]
            model = rm.fit_models(data, p)["models"]["AAPL"]
            self.assertEqual(model["n"], 126-missing)
            self.assertEqual(model["available"], available)

    def test_zero_sigma_is_not_floored_into_a_fake_model(self):
        data, p = self.changed()
        src, dest = bars(data, "XLK"), bars(data, "AAPL")
        for i in range(126*78):
            dest[i].update({k: src[i][k] for k in ("o", "h", "l", "c")})
        model = rm.fit_models(data, p)["models"]["AAPL"]
        self.assertFalse(model["available"])
        self.assertEqual(model["reason"], "RESIDUAL_SIGMA_AT_OR_BELOW_FLOOR")

    def test_beta_not_clipped_to_admissible_range(self):
        data, p = self.changed()
        for i in range(126):
            source = bars(data, "XLK")[i*78:i*78+12]
            dest = bars(data, "AAPL")[i*78:i*78+12]
            for a, b in zip(source, dest):
                b["o"] = 100*(a["o"]/100)**3
                b["c"] = 100*(a["c"]/100)**3
                b["h"], b["l"] = max(b["o"], b["c"])+.3, min(b["o"], b["c"])-.3
        model = rm.fit_models(data, p)["models"]["AAPL"]
        self.assertFalse(model["available"])
        self.assertGreater(model["beta"], 2)
        self.assertEqual(model["reason"], "BETA_OUTSIDE_FROZEN_RANGE")

    def test_atr_uses_15_prior_completed_sessions_and_14_true_ranges(self):
        panel = rm._Panel(self.data)
        session = self.data["sessions"][126]
        result, reason = panel.atr("AAPL", session, session["open"]+3601000, 14)
        self.assertIsNone(reason)
        self.assertEqual(len(result["history_dates"]), 15)
        self.assertEqual(result["history_dates"][-1], "2025-03-05")
        daily = []
        for i in range(111, 126):
            bs = bars(self.data, "AAPL")[i*78:(i+1)*78]
            daily.append((max(b["h"] for b in bs), min(b["l"] for b in bs), bs[-1]["c"]))
        expected = fmean(max(b[0]-b[1], abs(b[0]-a[2]), abs(b[1]-a[2])) for a, b in zip(daily, daily[1:]))
        self.assertAlmostEqual(result["value"], expected)

    def test_causal_split_adjustment_and_no_future_split_adjustment(self):
        data, p = self.changed()
        s = data["sessions"][126]
        base = rm._Panel(data).atr("AAPL", s, s["open"]+3601000, 14)[0]["value"]
        data["splitEvents"] = [{"symbol": "AAPL", "at": s["open"], "knownAt": s["open"], "ratio": 2}]
        split = rm._Panel(data).atr("AAPL", s, s["open"]+3601000, 14)[0]["value"]
        self.assertAlmostEqual(split, base/2)
        data["splitEvents"][0]["at"] = data["sessions"][127]["open"]
        future = rm._Panel(data).atr("AAPL", s, s["open"]+3601000, 14)[0]["value"]
        self.assertAlmostEqual(future, base)

    def test_ambiguous_or_future_split_knowledge_fails_closed(self):
        for known, reason in [(None, "SPLIT_KNOWLEDGE_AMBIGUOUS"), (9999999999999, "SPLIT_NOT_KNOWN_AT_DECISION")]:
            data, p = self.changed()
            s = data["sessions"][126]
            e = {"symbol": "AAPL", "at": s["open"], "ratio": 2}
            if known is not None:
                e["knownAt"] = known
            data["splitEvents"] = [e]
            r = rm.generate_signals(data, self.models, p)
            self.assertEqual(r["daily_decisions"][0]["candidates"]["AAPL"]["reason"], reason)

    def test_intraday_split_is_not_silently_normalized(self):
        data, p = self.changed()
        t = data["sessions"][126]["open"]+300000
        data["splitEvents"] = [{"symbol": "AAPL", "at": t, "knownAt": t, "ratio": 2}]
        with self.assertRaisesRegex(ValueError, "SPLIT_EFFECTIVE_AT_SESSION_OPEN_REQUIRED"):
            rm.generate_signals(data, self.models, p)

    def test_midnight_split_requires_data_admission_normalization(self):
        data, p = self.changed()
        opening = data["sessions"][126]["open"]
        midnight = opening - (14*60+30)*60000
        data["splitEvents"] = [{"symbol": "AAPL", "at": midnight, "knownAt": midnight, "ratio": 2}]
        with self.assertRaisesRegex(ValueError, "SPLIT_EFFECTIVE_AT_SESSION_OPEN_REQUIRED"):
            rm.generate_signals(data, self.models, p)

    def test_duplicate_split_events_fail_instead_of_double_adjustment(self):
        data, p = self.changed()
        t = data["sessions"][126]["open"]
        e = {"symbol": "AAPL", "at": t, "knownAt": t, "ratio": 2}
        data["splitEvents"] = [e, dict(e)]
        with self.assertRaisesRegex(ValueError, "DUPLICATE_SPLIT_EFFECTIVE_EVENT"):
            rm.generate_signals(data, self.models, p)

    def test_sector_atr_refusal_is_explicit_not_false_event_matching(self):
        data, p = self.changed()
        for i in reversed(range(126)):
            del bars(data, "XLK")[i*78+77]
        result = rm.generate_signals(data, self.models, p)
        for scenario, pairing in result["counts"]["proposed_event_pairing"].items():
            self.assertEqual(pairing["residual_proposed_events"], 3)
            self.assertEqual(pairing["sector_proposed_events"], 0)
            self.assertEqual(pairing["unmatched_residual_events"], 3)
            self.assertFalse(pairing["pairing_is_execution_match"])
            self.assertEqual(result["daily_decisions"][0]["scenarios"][scenario]["sector_refusal"], "ATR_HISTORY_INSUFFICIENT")

    def test_alphabetical_tie_break(self):
        data, p = self.changed()
        src = next(s for s in data["series"] if s["symbol"] == "AAPL")
        dest = next(s for s in data["series"] if s["symbol"] == "MSFT")
        dest["bars"] = copy.deepcopy(src["bars"])
        model = rm.fit_models(data, p)
        result = rm.generate_signals(data, model, p)
        self.assertTrue(all(d["selected_symbol"] == "AAPL" for d in result["daily_decisions"]))

    def test_repeat_deterministic_and_does_not_mutate_input(self):
        before = rm._sha(self.data)
        one = rm.generate_signals(self.data, self.models, self.protocol)
        self.assertEqual(one, rm.generate_signals(self.data, self.models, self.protocol))
        self.assertEqual(before, rm._sha(self.data))
        ids = [s["id"] for ps in one["signals"].values() for signals in ps.values() for s in signals]
        self.assertEqual(len(ids), len(set(ids)))

    def test_protocol_and_model_mutations_rejected(self):
        p = copy.deepcopy(self.protocol)
        p["recipe"]["z_entry"] = -2
        with self.assertRaisesRegex(ValueError, "FROZEN_RECIPE_MISMATCH"):
            rm.fit_models(self.data, p)
        p = copy.deepcopy(self.protocol)
        p["scenarios"]["NOMINAL"]["spread_bps"] = 3
        with self.assertRaisesRegex(ValueError, "MODEL_PROTOCOL_BINDING"):
            rm.generate_signals(self.data, self.models, p)
        model = copy.deepcopy(self.models)
        model["models"]["AAPL"]["beta"] += .1
        with self.assertRaisesRegex(ValueError, "MODEL_PAYLOAD_BINDING"):
            rm.generate_signals(self.data, model, self.protocol)

    def test_period_overlap_and_alias_conflict_rejected(self):
        p = copy.deepcopy(self.protocol)
        p["periods"]["evaluation_start"] = p["periods"]["train_end"]
        with self.assertRaisesRegex(ValueError, "NONCAUSAL_PERIODS"):
            rm.fit_models(self.data, p)
        p = copy.deepcopy(self.protocol)
        p["periods"]["training_start"] = "2024-01-01"
        with self.assertRaisesRegex(ValueError, "CONFLICTING_PERIOD_ALIASES"):
            rm.fit_models(self.data, p)

    def test_invalid_ohlcv_and_duplicate_times_refused(self):
        data, p = self.changed()
        bars(data, "AAPL")[126*78+5]["c"] = float("nan")
        r = rm.generate_signals(data, self.models, p)
        self.assertEqual(r["daily_decisions"][0]["candidates"]["AAPL"]["reason"], "OHLCV_INVALID")
        data, p = self.changed()
        bars(data, "AAPL")[1]["t"] = bars(data, "AAPL")[0]["t"]
        with self.assertRaisesRegex(ValueError, "BAR_ORDER_DUPLICATES"):
            rm.fit_models(data, p)


if __name__ == "__main__":
    unittest.main()
