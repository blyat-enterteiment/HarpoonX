from datetime import datetime, timedelta, timezone
import unittest
from dual_clock import Bar, ClockState, update

T = datetime(2026, 11, 16, 14, 30, tzinfo=timezone.utc)


def b(i: int, close: float, vol: float = 1000) -> Bar:
    return Bar(T + timedelta(minutes=5*i), close, close, close, close, vol)


class DualClockTests(unittest.TestCase):
    def test_early_without_rvol_or_late(self):
        x = update("XYZ", ClockState(), b(0, 105.1), official_prior_close=100,
                   session_open=100, historical_same_clock_expected_volume=None)
        self.assertTrue(x.early)
        self.assertFalse(x.late)
        self.assertTrue(x.admissible_now)

    def test_late_not_early_when_gap_from_open(self):
        x = update("XYZ", ClockState(), b(0, 111, 6000), official_prior_close=120,
                   session_open=100, historical_same_clock_expected_volume=1000)
        self.assertTrue(x.late)
        self.assertFalse(x.early)
        self.assertFalse(x.admissible_now)

    def test_both_signals_and_known_at(self):
        x = update("XYZ", ClockState(), b(0, 111, 6000), official_prior_close=100,
                   session_open=100, historical_same_clock_expected_volume=1000)
        self.assertTrue(x.early and x.late)
        self.assertEqual(x.known_at, T + timedelta(minutes=5))

    def test_missing_bar_halts(self):
        s = ClockState()
        update("XYZ", s, b(0, 100), official_prior_close=100,
               session_open=100, historical_same_clock_expected_volume=100)
        x = update("XYZ", s, b(2, 120), official_prior_close=100,
                   session_open=100, historical_same_clock_expected_volume=100)
        self.assertFalse(x.admissible_now)
        self.assertEqual(x.reason, "SOURCE_GAP_FAIL_CLOSED")

    def test_replayed_bar_rejected(self):
        s = ClockState()
        update("XYZ", s, b(0, 100), official_prior_close=100,
               session_open=100, historical_same_clock_expected_volume=100)
        with self.assertRaisesRegex(ValueError, "REPLAY"):
            update("XYZ", s, b(0, 105), official_prior_close=100,
                   session_open=100, historical_same_clock_expected_volume=100)

    def test_no_future_high_election(self):
        x = update("XYZ", ClockState(), Bar(T, 100, 115, 99, 100, 500),
                   official_prior_close=100, session_open=100,
                   historical_same_clock_expected_volume=10)
        self.assertFalse(x.early)

    def test_first_early_persists(self):
        s = ClockState()
        first = update("XYZ", s, b(0, 106), official_prior_close=100,
                       session_open=100, historical_same_clock_expected_volume=None)
        later = update("XYZ", s, b(1, 110, 6000), official_prior_close=100,
                       session_open=100, historical_same_clock_expected_volume=1000)
        self.assertEqual(first.known_at, later.early_first_at)
        self.assertEqual(later.late_first_at, later.known_at)

if __name__ == "__main__":
    unittest.main()
