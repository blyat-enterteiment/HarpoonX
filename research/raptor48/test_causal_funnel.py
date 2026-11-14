"""C48: pure causal-clock tests on synthetic fixtures, never financial alpha."""
from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta

import causal_funnel as F


@dataclass(frozen=True)
class Bar:
    at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 100.0


def make_session(date: str, closes: list[float], *,
                 start: str = "14:30") -> list[Bar]:
    origin = datetime.fromisoformat(f"{date}T{start}:00+00:00")
    return [Bar(origin + timedelta(minutes=i * 5), close, close + 0.01,
                close - 0.01, close) for i, close in enumerate(closes)]


class C48FunnelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.prev = make_session("2026-11-12", [100] * 6)

    def test_no_high_touch_no_stages(self) -> None:
        d = F.audit_path(self.prev, make_session("2026-11-13", [100] * 6), .03)
        self.assertFalse(d["historical_high_touch"])
        self.assertFalse(d["priced_next_open"])

    def test_touch_without_two_closes_is_not_fill(self) -> None:
        bars = make_session("2026-11-13", [100, 100, 100, 100])
        bars[1] = Bar(bars[1].at, 100, 106, 99, 100)
        d = F.audit_path(self.prev, bars, .04)
        self.assertTrue(d["historical_high_touch"])
        self.assertFalse(d["two_completed_closes"])
        self.assertFalse(d["historical_high_was_a_fill"])

    def test_two_closes_and_priced_next_open(self) -> None:
        d = F.audit_path(self.prev, make_session("2026-11-13",
                         [100, 103.1, 103.2, 103.3, 104]), .03)
        self.assertTrue(d["two_completed_closes"])
        self.assertTrue(d["contiguous_next_open"])
        self.assertTrue(d["priced_next_open"])
        self.assertEqual(d["first_ideal_decision_at"],
                         "2026-11-13T14:45:00+00:00")

    def test_price_pursuit_rejects_next_open(self) -> None:
        d = F.audit_path(self.prev,
                         make_session("2026-11-13", [100, 104, 104, 105, 110]),
                         .03)
        self.assertTrue(d["two_completed_closes"])
        self.assertTrue(d["contiguous_next_open"])
        self.assertFalse(d["priced_next_open"])

    def test_missing_intermediate_bar_rejects(self) -> None:
        t = make_session("2026-11-13", [100, 104, 104, 103.2])
        t[2] = Bar(t[2].at + timedelta(minutes=10), 104, 104.01, 103.99, 104)
        t[3] = Bar(t[3].at + timedelta(minutes=10), 103.2, 103.21, 103.19, 103.2)
        d = F.audit_path(self.prev, t, .03)
        self.assertFalse(d["contiguous_next_open"])

    def test_beyond_cutoff_not_allowed(self) -> None:
        d = F.audit_path(self.prev,
                         make_session("2026-11-13", [100, 103.1, 103.2, 103.3],
                                      start="20:00"), .03)
        self.assertFalse(d["two_completed_closes"])

    def test_reject_unfrozen_threshold(self) -> None:
        with self.assertRaisesRegex(ValueError, "FROZEN"):
            F.audit_path(self.prev, make_session("2026-11-13", [100] * 4), .05)

    def test_reject_nonmonotonic_and_naive_clock(self) -> None:
        rows = make_session("2026-11-13", [100] * 4)
        with self.assertRaisesRegex(ValueError, "MONOTONIC"):
            F.audit_path(self.prev, [rows[0], rows[0], *rows[2:]], .03)
        rows[0] = Bar(datetime(2026, 11, 13), 100, 101, 99, 100)
        with self.assertRaisesRegex(ValueError, "NAIVE"):
            F.audit_path(self.prev, rows, .03)

    def test_inadequate_history_rejected(self) -> None:
        d = F.audit_path(self.prev[:5],
                         make_session("2026-11-13", [103] * 4), .03)
        self.assertFalse(d["eligible_history"])
        self.assertFalse(d["priced_next_open"])

    def test_exact_source_provenance_pin_and_no_autotrade(self) -> None:
        self.assertEqual(len(F.EXPECTED_SOURCE_SHA256), 64)
        self.assertTrue(F.EXPECTED_SOURCE_SHA256.startswith("74a1230b"))
        self.assertFalse(F.audit_path(
            self.prev, make_session("2026-11-13", [100] * 4),
            .03)["historical_high_was_a_fill"])


if __name__ == "__main__":
    unittest.main()
