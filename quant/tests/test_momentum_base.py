import unittest
from datetime import UTC, datetime, timedelta

from harpoon_quant.framework import evaluate


def fixture():
    start = datetime(2026, 1, 1, 21, tzinfo=UTC)
    daily = []
    for i in range(60):
        c = 70 + i * 0.6 if i < 50 else 101 + (i - 50) * 0.02
        width = 1 if i < 55 else 0.3
        daily.append(
            dict(
                available_at=(start + timedelta(days=i)).isoformat(),
                o=c,
                h=c + width,
                l=c - width,
                c=c,
                v=100000,
            )
        )
    return dict(
        schema="HARPOON_QUANT_FRAMEWORK_1",
        operation="MOMENTUM_BASE",
        payload=dict(
            symbol="TEST",
            asof="2026-03-03T14:36:00+00:00",
            daily=daily,
            capital=20000,
            reserved_risk=0,
            reserved_gross=0,
            quote=dict(
                at="2026-03-03T14:36:00+00:00",
                session_open="2026-03-03T14:30:00+00:00",
                opening_complete_at="2026-03-03T14:35:00+00:00",
                bid=102.2,
                ask=102.21,
                day_low=101,
                opening_high=102.1,
            ),
        ),
    )


class MomentumTests(unittest.TestCase):
    def test_candidate(self):
        p = fixture()
        # 30-session impulse ending before the base.
        for i, b in enumerate(p["payload"]["daily"][:50]):
            c = 50 + i
            b.update(o=c, h=c + 1, l=c - 1, c=c)
        r = evaluate(p)
        self.assertEqual(r["result"]["status"], "RESEARCH_CANDIDATE", r)
        self.assertFalse(r["execution_allowed"])
        self.assertLessEqual(r["result"]["research_plan"]["qty"] * 102.21, 2400)

    def test_budget_blocks(self):
        p = fixture()
        p["payload"]["reserved_risk"] = 50
        self.assertFalse(evaluate(p)["result"]["checks"]["shared_budget"])

    def test_no_breakout(self):
        p = fixture()
        p["payload"]["quote"].update(bid=101, ask=101.01)
        self.assertFalse(evaluate(p)["result"]["checks"]["breakout"])

    def test_stale_future_and_nan(self):
        for mode in ["stale", "future", "nan", "duplicate"]:
            p = fixture()
            v = p["payload"]
            if mode == "stale":
                v["quote"]["at"] = "2026-03-03T14:35:00+00:00"
            if mode == "future":
                v["daily"][-1]["available_at"] = v["asof"]
            if mode == "nan":
                v["daily"][0]["c"] = float("nan")
            if mode == "duplicate":
                v["daily"][1]["available_at"] = v["daily"][0]["available_at"]
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                evaluate(p)
