import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from audit_research_budget import audit
from causal_campaign_state import CampaignState
from economic_verdict import archived_virtual_status
from test_forensic_features import fixture

COSTS = {"spread_bps": 2, "slippage_bps": 2, "commission_usd_per_share_per_side": .005}


def sample():
    data = fixture()
    start = data["sessions"][20]["open"] + 301_000
    end = start + 900_000
    trade = {"symbol": "AAPL", "riskUsd": 8, "holdingClockStartedAt": start,
             "holdingDeadlineAt": end, "dividendEntitlements": [],
             "marks": [{"at": start}, {"at": start + 300_000}, {"at": end}],
             "inventoryEvents": [{"knownAt": start, "quantityDelta": 4, "filledPrice": 101, "feeUsd": .02},
                                 {"knownAt": end, "quantityDelta": -4, "filledPrice": 104, "feeUsd": .02}]}
    return data, trade


class CausalIntegrityTests(unittest.TestCase):
    def test_future_prices_and_future_fill_cannot_change_prefix(self):
        data, trade = sample()
        original = CampaignState(data).trace(trade, COSTS)
        changed, future_trade = copy.deepcopy(data), copy.deepcopy(trade)
        for series in changed["series"]:
            for bar in series["bars"]:
                if bar["availableAt"] > trade["marks"][0]["at"]:
                    bar.update(o=999, h=1001, l=998, c=1000, vw=1000, v=99999)
        future_trade["inventoryEvents"][-1]["filledPrice"] = 8888
        altered = CampaignState(changed).trace(future_trade, COSTS)
        self.assertEqual(original[0], altered[0])

    def test_state_has_costs_and_closes_inventory_at_receipt(self):
        data, trade = sample()
        rows = CampaignState(data).trace(trade, COSTS)
        self.assertEqual(rows[0]["remaining_quantity_known"], 4)
        self.assertGreater(rows[0]["estimated_exit_cost_r"], 0)
        self.assertEqual(rows[-1]["remaining_quantity_known"], 0)
        self.assertAlmostEqual(rows[-1]["pnl_liquidation_estimated_r"], 11.96 / 8)
        self.assertTrue(all(r["price_available_at_ms"] <= r["at_ms"] for r in rows))
        self.assertTrue(all(r["observed_quote_spread"] is None for r in rows))

    def test_split_adjustment_is_effective_time_bounded(self):
        data, trade = sample()
        event_at = data["sessions"][20]["open"] + 300_000
        data["splitEvents"] = [{"symbol": "XLK", "at": event_at, "ratio": 2}]
        for bar in data["series"][2]["bars"]:
            if bar["t"] >= event_at:
                for k in ["o", "h", "l", "c", "vw"]:
                    bar[k] /= 2
        rows = CampaignState(data).trace(trade, COSTS)
        self.assertTrue(all(abs(r["relative_from_decision_known_close"]) < 1e-12 for r in rows))

    def test_registry_cannot_authorize_search_from_stale_119_snapshot(self):
        result = audit()
        self.assertFalse(result["new_measurements_allowed"])
        self.assertFalse(result["global_history_complete"])
        self.assertEqual(result["reserved_plus_unincorporated"], 151)
        self.assertEqual(result["estimate_even_if_unused_reservation_released"], 131)

    def test_economic_verdict_does_not_call_existing_variants_unimplemented(self):
        result = archived_virtual_status()
        self.assertTrue(result["policy_comparison_executed"])
        self.assertFalse(result["virtual_effect_identified"])
        self.assertEqual(len(result["virtual_comparison_accounts"]), 6)
        self.assertIn("NOT_RERUN", result["policy_comparison_execution_scope"])


if __name__ == "__main__":
    unittest.main()
