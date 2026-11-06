import copy
import unittest
from datetime import UTC, datetime, timedelta

from harpoon_quant.framework import evaluate
from harpoon_quant.intraday import replay


def fixture():
    start = datetime(2026, 11, 5, 14, 30, tzinfo=UTC)
    bars = []
    for i in range(60):
        price = 100 if i < 5 else 100.4
        bars.append(
            dict(
                t=(start + timedelta(minutes=i)).isoformat(),
                o=price,
                h=price + 0.2,
                l=price - 0.2,
                c=price + 0.1,
                v=1000,
            )
        )
    return dict(
        origin="SYNTHETIC",
        symbol="QQQ",
        strategy="ORB5",
        capital=20000,
        costs=dict(
            spread_bps=1, slippage_bps=1, fee_bps=1, borrow_bps=2, shortable=True
        ),
        sessions=[
            dict(
                open=start.isoformat(),
                close=(start + timedelta(minutes=60)).isoformat(),
                history_asof=(start - timedelta(days=1)).isoformat(),
                prior_opening_volumes=[3000] * 20,
                bars=bars,
            )
        ],
    )


class IntradayTests(unittest.TestCase):
    def test_next_bar_entry_and_close(self):
        p = fixture()
        r = replay(p)
        t = r["trades"][0]
        self.assertEqual(t["entry_time"], p["sessions"][0]["bars"][6]["t"])
        self.assertEqual(t["exit_bar_start"], p["sessions"][0]["bars"][55]["t"])
        self.assertLess(t["net_pnl"], 0)  # Flat path loses costs.
        self.assertAlmostEqual(r["net_pnl"], sum(t["net_pnl"] for t in r["trades"]))

    def test_gap_through_stop(self):
        p = fixture()
        b = p["sessions"][0]["bars"][7]
        b.update(o=95, h=96, l=94, c=95)
        t = replay(p)["trades"][0]
        self.assertLess(t["exit"], 95)
        self.assertEqual(t["exit_reason"], "STOP_OR_GAP")

    def test_short_direction(self):
        p = fixture()
        for b in p["sessions"][0]["bars"][5:]:
            b.update(o=99.6, h=99.8, l=99.4, c=99.5)
        self.assertEqual(replay(p)["trades"][0]["side"], -1)
        p["costs"]["shortable"] = False
        self.assertEqual(replay(p)["trades"], [])

    def test_reject_data_faults(self):
        for fault in ["nan", "gap", "lookahead", "overlap", "volume", "ohlc"]:
            p = fixture()
            s = p["sessions"][0]
            if fault == "nan":
                s["bars"][0]["c"] = float("nan")
            if fault == "gap":
                s["bars"].pop()
            if fault == "lookahead":
                s["history_asof"] = s["open"]
            if fault == "overlap":
                p["sessions"].append(copy.deepcopy(s))
            if fault == "volume":
                s["prior_opening_volumes"] = [0] * 20
            if fault == "ohlc":
                s["bars"][0]["l"] = 200
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                replay(p)

    def test_capital_not_reset(self):
        p = fixture()
        second = copy.deepcopy(p["sessions"][0])
        for k in ["open", "close", "history_asof"]:
            second[k] = (
                datetime.fromisoformat(second[k]) + timedelta(days=1)
            ).isoformat()
        for b in second["bars"]:
            b["t"] = (datetime.fromisoformat(b["t"]) + timedelta(days=1)).isoformat()
        p["sessions"].append(second)
        r = replay(p)
        self.assertEqual(len(r["trades"]), 2)
        self.assertAlmostEqual(
            r["final_equity"], 20000 + sum(t["net_pnl"] for t in r["trades"])
        )

    def test_costs_and_activity_reject(self):
        p = fixture()
        p["costs"]["spread_bps"] = 100
        self.assertEqual(replay(p)["trades"], [])
        p = fixture()
        p["sessions"][0]["prior_opening_volumes"] = [10000] * 20
        self.assertEqual(replay(p)["skipped"][0]["reason"], "ACTIVITY_OR_RANGE")

    def test_all_recipes_and_public_contract(self):
        for strategy in ["ORB5", "ORB15", "PULLBACK15"]:
            p = fixture()
            p["strategy"] = strategy
            r = evaluate(
                dict(
                    schema="HARPOON_QUANT_FRAMEWORK_1",
                    operation="INTRADAY_REPLAY",
                    payload=p,
                )
            )
            self.assertFalse(r["execution_allowed"])
            self.assertFalse(r["level8_accredited"])
            self.assertEqual(r["result"]["origin"], "SYNTHETIC")

    def test_future_suffix_cannot_change_entry(self):
        p = fixture()
        before = replay(p)["trades"][0]
        p["sessions"][0]["bars"][-1].update(o=500, h=501, l=499, c=500)
        after = replay(p)["trades"][0]
        self.assertEqual(before, after)

    def test_orb15_and_pullback_generate_distinct_entries(self):
        p = fixture()
        p["strategy"] = "ORB15"
        s = p["sessions"][0]
        s["prior_opening_volumes"] = [10000] * 20
        for b in s["bars"][:15]:
            b.update(o=100, h=100.2, l=99.8, c=100.1)
        self.assertEqual(replay(p)["trades"][0]["entry_time"], s["bars"][16]["t"])
        p["strategy"] = "PULLBACK15"
        s["bars"][16]["l"] = 100.3
        s["bars"][17].update(o=100.4, h=100.6, l=100.1, c=100.5)
        self.assertEqual(replay(p)["trades"][0]["entry_time"], s["bars"][18]["t"])
