import unittest
from datetime import UTC, datetime, timedelta

from harpoon_quant.virtual_ab import replay


def data():
    start = datetime(2025, 1, 1, tzinfo=UTC)
    daily = [
        dict(
            at=start - timedelta(days=110 - i),
            known=start - timedelta(days=109 - i) + timedelta(minutes=1),
            close=10 * 1.02**i,
        )
        for i in range(105)
    ]
    hourly = [
        dict(at=start + timedelta(hours=i), open=100, high=101, low=99, close=100)
        for i in range(240)
    ]
    return {"BTC/USD": hourly}, {"BTC/USD": daily}


class VirtualABTests(unittest.TestCase):
    def test_funded_reconciliation_all_policies(self):
        for policy in ["CURRENT", "A", "B"]:
            h, d = data()
            r = replay(h, d, policy)
            cash = 20000
            qty = 0
            for e in r["events"]:
                cash -= e["cost"]
                if e["side"] == "buy":
                    cash -= e["qty"] * e["price"]
                    qty += e["qty"]
                elif e["side"] == "sell":
                    cash += e["qty"] * e["price"]
                    qty -= e["qty"]
            with self.subTest(policy=policy):
                self.assertAlmostEqual(qty, 0)
                self.assertAlmostEqual(cash, r["final"])
                self.assertTrue(all(x["cash"] >= 0 for x in r["curve"]))
                self.assertGreater(
                    len([e for e in r["events"] if e["side"] == "buy"]), 0
                )
                self.assertFalse(r["execution_allowed"])

    def test_gradual_first_entry_smaller(self):
        h, d = data()
        a = replay(h, d, "A")
        b = replay(h, d, "B")

        def first(r):
            return next(e["qty"] for e in r["events"] if e["side"] == "buy")

        self.assertAlmostEqual(first(b), first(a) / 2)

    def test_future_daily_rows_do_not_change_decisions(self):
        h, d = data()
        a = replay(h, d, "CURRENT")
        d["BTC/USD"].append(
            dict(
                at=datetime(2026, 1, 1, tzinfo=UTC),
                known=datetime(2026, 1, 2, tzinfo=UTC),
                close=999999,
            )
        )
        self.assertEqual(a, replay(h, d, "CURRENT"))

    def test_gap_stop_is_adverse_open(self):
        h, d = data()
        h["BTC/USD"][13].update(open=90, low=89, close=90)
        r = replay(h, d, "CURRENT")
        sells = [e for e in r["events"] if e["side"] == "sell"]
        self.assertEqual(sells[0]["price"], 90)

    def test_campaign_not_extended_by_additions(self):
        h, d = data()
        r = replay(h, d, "B")
        deadline = None
        for e in r["events"]:
            if e["side"] == "sell":
                deadline = None
            if e["side"] == "buy":
                if deadline:
                    self.assertEqual(e["deadline"], deadline)
                deadline = e["deadline"]
                self.assertLessEqual(
                    (
                        datetime.fromisoformat(deadline)
                        - datetime.fromisoformat(e["at"])
                    ).total_seconds(),
                    72 * 3600,
                )

    def test_purged_labels_precede_fold_by_72_hours(self):
        h, d = data()
        r = replay(h, d, "CURRENT", purged=True)
        cutoff = datetime(2025, 1, 1, tzinfo=UTC) - timedelta(hours=72)
        seen = False
        for decision in r["decisions"]:
            if decision["max_label_available"]:
                seen = True
                self.assertLess(
                    datetime.fromisoformat(decision["max_label_available"]), cutoff
                )
        self.assertTrue(seen)
