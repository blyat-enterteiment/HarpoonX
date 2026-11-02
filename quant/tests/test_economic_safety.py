"""Adversarial fixtures for exposure, cash events and intraday risk measurement."""

import copy
import unittest
from datetime import datetime

import numpy as np

from harpoon_quant.economic_lab import Policy, replay
from harpoon_quant.ledger import reconcile_events

LIMITS = dict(
    capital=20000,
    risk_fraction=0.0025,
    open_risk_fraction=0.015,
    gross_fraction=0.5,
    asset_fraction=0.12,
    factor_fraction=0.5,
    max_positions=8,
    daily_loss=0.02,
    max_drawdown=0.08,
)


class TinyWorld:
    """Synthetic known-at-mark values; no market or broker observations."""

    def __init__(self, *, jump=False, valley=False, assets=1):
        self.marks = [
            datetime.fromisoformat(t)
            for t in [
                "2026-07-01T13:45:00+00:00",
                "2026-07-01T14:00:00+00:00",
                "2026-07-01T19:45:00+00:00",
                "2026-07-02T13:45:00+00:00",
            ]
        ]
        self.seed = 771
        self.returns = np.full((125, 24), 0.01)
        self.spot = np.full((125, 24), 20.0)
        self.ages = np.zeros((4, 24))
        self.depth = np.full((4, 24), 5)
        self.jump = jump
        self.valley = valley
        self.assets = assets

    def day(self, mark):
        return 121 + (mark == 3)

    def candidate(self, mark, asset, call, flags):
        return dict(
            asset=asset, call=call, entry=mark, exit=3, strike=22.0,
            dte=21, funding=42.65, risk=43.3,
            edge=10.0 if mark == 0 and call and asset < self.assets else -1.0,
            spread=0.1, exposure=1000.0, kind="option", fee=0.65,
            stock_expected=20.0, initial_mid=0.4,
            delta=0.5, gamma=0.01, vega=0.1,
        )

    def value(self, position, mark, stress, scenario="base"):
        unit = [40.0, 36.0, 44.0, 44.0][mark] if self.valley else 40.0
        spot = 120.0 if self.jump and mark > 0 else 20.0
        delta = 1.0 if self.jump and mark > 0 else 0.5
        return unit, dict(delta=delta, gamma=0.01, vega=0.1, mid_cash=unit + 0.65), spot


def run(world, flags="", **limits):
    return replay(world, Policy(flags), "2026-07-01", "2026-07-02", LIMITS | limits)


class EconomicSafetyTests(unittest.TestCase):
    def test_delta_jump_is_handled_at_first_observable_mark(self):
        world = TinyWorld(jump=True)
        result = run(world)
        self.assertEqual(result["trades"][0]["exit_at"], world.marks[1].isoformat())
        self.assertEqual(result["trades"][0]["reason"], "marked_exposure_limit")
        self.assertGreater(len(result["risk_breaches"]), 0)
        event = result["risk_breaches"][0]
        self.assertGreater(event["gross_exposure_usd"], event["limits_usd"]["gross"])

    def test_F_never_raises_configured_position_limit(self):
        result = run(TinyWorld(assets=5), "F", max_positions=1)
        self.assertLessEqual(max(e["open_positions"] for e in result["ledger"] if e["kind"] == "NAV"), 1)

    def test_F_never_raises_configured_factor_limit(self):
        self.assertEqual(run(TinyWorld(assets=5), "F", factor_fraction=0.025)["trades"], [])

    def test_F_never_raises_configured_open_risk_limit(self):
        self.assertEqual(run(TinyWorld(assets=5), "F", open_risk_fraction=0.001)["trades"], [])

    def test_every_cash_flow_can_be_reduced_without_trades_summary(self):
        result = run(TinyWorld())
        events = result["ledger"]
        self.assertEqual(sum(e["kind"] == "ENTRY" for e in events), 1)
        self.assertEqual(sum(e["kind"] == "EXIT" for e in events), 1)
        reduced = reconcile_events(events, 20000)
        self.assertEqual(reduced["open_inventory"], {})
        self.assertAlmostEqual(reduced["final_cash"], events[-1]["cash"])
        self.assertAlmostEqual(reduced["realized_net_pnl"], sum(t["net_pnl_usd"] for t in result["trades"]))

    def test_intraday_drawdown_is_not_erased_by_recovery(self):
        result = run(TinyWorld(valley=True))
        self.assertAlmostEqual(result["metrics"]["max_drawdown"], 0.0)
        self.assertGreater(result["risk_metrics"]["max_drawdown_all_observed_marks"], 0.0003)
        self.assertTrue(any(e["kind"] == "PRE_NAV" for e in result["ledger"]))

    def test_reducer_rejects_missing_exit_and_changed_cash(self):
        events = run(TinyWorld())["ledger"]
        with self.assertRaises(ValueError):
            reconcile_events([e for e in events if e["kind"] != "EXIT"], 20000)
        altered = copy.deepcopy(events)
        next(e for e in altered if e["kind"] == "NAV")["cash"] += 1
        with self.assertRaisesRegex(ValueError, "CASH_MISMATCH"):
            reconcile_events(altered, 20000)

    def test_partial_exit_fees_are_counted_exactly_once(self):
        events = [
            dict(kind="ENTRY", position_id="P", lots=2, cash_change=-102.0, gross_cash_change=-100.0, fees_usd=2.0),
            dict(kind="EXIT", position_id="P", lots=1, cash_change=59.0, gross_cash_change=60.0, fees_usd=1.0),
            dict(kind="NAV", cash=157.0, nav=217.0, positions=[dict(position_id="P", lots=1, liquidation_value_per_lot=60.0)]),
            dict(kind="EXIT", position_id="P", lots=1, cash_change=39.0, gross_cash_change=40.0, fees_usd=1.0),
        ]
        for i, event in enumerate(events):
            event["at"] = f"2026-07-01T13:{45+i:02}:00+00:00"
        reduced = reconcile_events(events, 200.0)
        self.assertEqual(reduced["final_cash"], 196.0)
        self.assertEqual(reduced["realized_net_pnl"], -4.0)
        self.assertEqual(reduced["fees_usd"], 4.0)
        self.assertEqual(reduced["open_inventory"], {})

    def test_position_limit_must_be_integer(self):
        with self.assertRaises(ValueError):
            run(TinyWorld(), max_positions=1.5)

    def test_caps_use_equity_after_fill_costs(self):
        result = run(TinyWorld(), gross_fraction=0.05)
        self.assertEqual(result["trades"], [])
        self.assertGreater(result["blocks"].get("post_fill_equity_limit", 0), 0)
        self.assertEqual(result["risk_breaches"], [])

    def test_reducer_rejects_time_reversal_and_excess_holding(self):
        events = run(TinyWorld())["ledger"]
        next(e for e in events if e["kind"] == "EXIT")["at"] = "2026-06-01T13:45:00+00:00"
        with self.assertRaisesRegex(ValueError, "EVENT_TIME_ORDER"):
            reconcile_events(events, 20000)
        events = [e for e in run(TinyWorld())["ledger"] if e["kind"] in {"ENTRY", "EXIT"}]
        events[-1]["at"] = "2026-07-05T13:45:00+00:00"
        with self.assertRaisesRegex(ValueError, "HOLDING_EXCEEDS_72H"):
            reconcile_events(events, 20000)


if __name__ == "__main__":
    unittest.main()
