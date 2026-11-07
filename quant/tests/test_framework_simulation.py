"""Order lifecycle via the public core; all receipts are synthetic."""

import unittest
from unittest.mock import patch

import test_roadmap9_integration as original

from harpoon_quant.framework import evaluate
from harpoon_quant.roadmap9.integration import process


class FrameworkSimulationTests(unittest.TestCase):
    def route(self, payload):
        result = evaluate(
            {
                "schema": "HARPOON_QUANT_FRAMEWORK_1",
                "operation": "SIMULATE_SESSION",
                "payload": payload,
            }
        )
        self.assertFalse(result["execution_allowed"])
        self.assertFalse(result["level8_accredited"])
        self.assertEqual(result["selected"], [])
        self.assertFalse(result["result"]["broker_paper_connected"])
        expected = process(payload)
        self.assertEqual(result["result"]["session"], expected["session"])
        return result["result"]

    def test_simulated_order_fill_and_fee(self):
        with patch.object(original, "process", side_effect=self.route):
            original.CompositeIntegrationTests().test_real_allocator_fill_fee_equity_and_no_authority()

    def test_partial_cancel_restart_and_late_fill(self):
        with patch.object(original, "process", side_effect=self.route):
            original.CompositeIntegrationTests().test_late_fill_after_cancel_restart_and_delayed_fees()
