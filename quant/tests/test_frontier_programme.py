from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harpoon_quant.core import digest
from harpoon_quant.frontier.market import market_clock
from harpoon_quant.frontier.programme import evidence_gate, validate_programme

ROOT = Path(__file__).resolve().parents[2]


class ProgrammeTests(unittest.TestCase):
    def setUp(self):
        self.programme = json.loads(
            (ROOT / "programme/frontier/programme.json").read_text()
        )

    def test_budget_exact_and_no_expenditure(self):
        r = validate_programme(self.programme)
        self.assertEqual(r["planning_budget_usd"], 5_000_000)
        self.assertEqual(r["reported_spent_usd"], 0)
        self.assertFalse(r["financial_authorization"])

    def test_budget_overrun_and_duplicate_packages_rejected(self):
        p = copy.deepcopy(self.programme)
        p["work_packages"][0]["budget_usd"] += 1
        with self.assertRaises(ValueError):
            validate_programme(p)
        p = copy.deepcopy(self.programme)
        p["work_packages"][1]["id"] = p["work_packages"][0]["id"]
        with self.assertRaises(ValueError):
            validate_programme(p)

    def test_hashes_do_not_authorize_spending_or_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = evidence_gate(self.programme, "G0", [], Path(tmp))
            self.assertFalse(r["spending_authorized"])
            self.assertFalse(r["promotion_authorized"])
            self.assertEqual(len(r["missing"]), 4)

    def test_gate_cycles_and_spend_domain(self):
        p = copy.deepcopy(self.programme)
        p["gates"][0]["depends_on"] = ["G5"]
        with self.assertRaises(ValueError):
            validate_programme(p)
        p = copy.deepcopy(self.programme)
        p["work_packages"][0]["spent_usd"] = 500_000
        with self.assertRaises(ValueError):
            validate_programme(p)

    def calendar(self):
        return {
            "venue": "NYSE",
            "known_at": "2025-11-27T00:00:00Z",
            "coverage_start": "2025-11-27",
            "coverage_end": "2025-12-03",
            "sessions": [
                {"open": "2025-11-28T14:30:00Z", "close": "2025-11-28T18:00:00Z"},
                {"open": "2025-12-01T14:30:00Z", "close": "2025-12-01T21:00:00Z"},
            ],
        }

    def test_early_close_normalized_without_weekday_guess(self):
        r = market_clock("2025-11-28T17:00:00Z", "equity", self.calendar(), [])
        self.assertTrue(r["tradable_now"])
        self.assertTrue(r["schedule"][0])
        self.assertFalse(r["schedule"][1])
        self.assertEqual(len(r["schedule_source_hash"]), len(digest({})))

    def test_unknown_halt_end_does_not_invent_resume(self):
        r = market_clock(
            "2025-11-28T17:00:00Z",
            "equity",
            self.calendar(),
            [
                {
                    "start_at": "2025-11-28T16:59:00Z",
                    "known_at": "2025-11-28T17:00:00Z",
                    "end_at": None,
                }
            ],
        )
        self.assertTrue(r["halted"])
        self.assertFalse(any(r["schedule"]))

    def test_derivatives_and_future_records_rejected(self):
        with self.assertRaises(ValueError):
            market_clock("2025-11-28T17:00:00Z", "options", self.calendar(), [])
        c = self.calendar()
        c["known_at"] = "2025-12-01T00:00:00Z"
        with self.assertRaises(ValueError):
            market_clock("2025-11-28T17:00:00Z", "equity", c, [])


if __name__ == "__main__":
    unittest.main()
