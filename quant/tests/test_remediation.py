import unittest

from harpoon_quant.core import timestamp
from harpoon_quant.remediation import membership_at, order_costs, training_indices


class RemediationTests(unittest.TestCase):
    def test_universe_revision_and_expiry(self):
        snap = dict(
            received_at="2025-01-01T00:00Z",
            effective_at="2025-01-01T00:00Z",
            valid_until="2025-03-01T00:00Z",
            references={"A": "XLK", "B": "XLF"},
        )
        late = {
            **snap,
            "received_at": "2025-02-01T00:00Z",
            "references": {"A": "XLI", "B": "XLF"},
        }
        self.assertEqual(
            membership_at([late, snap], timestamp("2025-01-20T00:00Z"))[0],
            snap["references"],
        )
        for rows, at in (
            ([snap, snap], "2025-01-20T00:00Z"),
            ([snap], "2025-04-01T00:00Z"),
        ):
            with self.assertRaises(ValueError):
                membership_at(rows, timestamp(at))

    def test_purge_uses_label_receipt(self):
        row = dict(
            at="2025-01-01T00:00Z",
            label_end="2025-01-03T00:00Z",
            known_at="2025-01-03T00:00Z",
        )
        self.assertEqual(
            training_indices(
                [row, {**row, "known_at": "2025-01-08T00:00Z"}], "2025-01-10T00:00Z"
            ),
            [0],
        )

    def test_unfilled_order_retains_signed_cost(self):
        at = "2025-01-01T15:30Z"
        order = dict(
            order_id="O",
            symbol="AAPL",
            book="equity",
            side="buy",
            decision_at=at,
            quote_at=at,
            quote_received_at=at,
            terminal_at=at,
            valuation_at="2025-01-01T15:35Z",
            bid=99,
            ask=101,
            quantity=10,
            valuation_mid=102,
        )
        bundle = dict(
            schema="HARPOON_OBSERVED_FILLS_1",
            mode="PAPER",
            available_at=order["valuation_at"],
            orders=[order],
            fills=[],
        )
        self.assertEqual(order_costs(bundle)["orders"][0]["missed_opportunity_usd"], 20)
        fill = {
            **order,
            "filled_at": at,
            "fill_id": "F",
            "qty": 4,
            "price": 101,
            "fee_usd": 1,
            "fee_receipt_id": "receipt",
        }
        bundle["fills"] = [fill]
        self.assertEqual(
            order_costs(bundle)["orders"][0]["implementation_shortfall_usd"], 17
        )
        with self.assertRaises(ValueError):
            order_costs({**bundle, "orders": []})
