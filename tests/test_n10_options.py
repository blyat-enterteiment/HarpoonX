"""Deterministic engineering fixtures only; no market backtest or broker."""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from quant.harpoon_quant.n10_options import (  # noqa: E402
    Candidate, Contract, Guard, Leg, Portfolio, Quote, Right, Scenario,
    _max_loss, _robust_mean, black_scholes, evaluate, select,
)

NOW = datetime(2026, 11, 13, 15, 0, tzinfo=timezone.utc)
EXIT = NOW + timedelta(hours=48)
EXPIRY = NOW + timedelta(days=10)
G = Guard()


def contract(kind: Right, strike: str) -> Contract:
    return Contract('XSP', kind, D(strike), EXPIRY)


def quote(kind: Right, strike: str, bid: str, ask: str, known_at: datetime = NOW) -> Quote:
    return Quote(contract(kind, strike), D(bid), D(ask), 10, 10, known_at)


def portfolio(**overrides: object) -> Portfolio:
    data = dict(equity=D('20000'), cash=D('20000'), session_open_equity=D('20000'),
                peak_equity=D('20000'), risk_reserved=D('0'), admission_reserved=D('0'), known_at=NOW)
    data.update(overrides)
    return Portfolio(**data)


def world(spot_high: float = 104.0) -> tuple[Scenario, ...]:
    return (Scenario(0.7, spot_high, 0.20, NOW), Scenario(0.3, 99.0, 0.25, NOW))


class OptionsPhase0Tests(unittest.TestCase):
    def test_put_call_parity(self) -> None:
        # zero carrying cost; European parity is C-P=S-K
        c = black_scholes(Right.CALL, 100, 100, 0.5, 0.2)
        p = black_scholes(Right.PUT, 100, 100, 0.5, 0.2)
        self.assertAlmostEqual(c-p, 0, places=11)

    def test_no_naked_short(self) -> None:
        with self.assertRaises(ValueError):
            Candidate('NAKED', (Leg(quote(Right.PUT, '100', '1', '1.1'), -1),))

    def test_crossed_quote_rejected(self) -> None:
        with self.assertRaises(ValueError):
            quote(Right.CALL, '100', '1.2', '1.1')

    def test_future_quote_rejected(self) -> None:
        cand = Candidate('CALL', (Leg(quote(Right.CALL, '110', '0.1', '0.2', NOW+timedelta(seconds=1)), 1),))
        with self.assertRaisesRegex(ValueError, 'future or stale'):
            evaluate(cand, world(), decision_at=NOW, exit_at=EXIT, guard=G, portfolio=portfolio())

    def test_future_forecast_rejected(self) -> None:
        cand = Candidate('CALL', (Leg(quote(Right.CALL, '110', '0.1', '0.2'), 1),))
        with self.assertRaisesRegex(ValueError, 'future-labelled'):
            evaluate(cand, (Scenario(1.0, 100, 0.2, NOW+timedelta(seconds=1)),),
                     decision_at=NOW, exit_at=EXIT, guard=G, portfolio=portfolio())

    def test_stale_quote_rejected(self) -> None:
        cand = Candidate('CALL', (Leg(quote(Right.CALL, '110', '0.1', '0.2', NOW-timedelta(minutes=5)), 1),))
        with self.assertRaisesRegex(ValueError, 'stale'):
            evaluate(cand, world(), decision_at=NOW, exit_at=EXIT, guard=G, portfolio=portfolio())

    def test_expiry_and_72h_rejected(self) -> None:
        cand = Candidate('CALL', (Leg(quote(Right.CALL, '110', '0.1', '0.2'), 1),))
        with self.assertRaises(ValueError):
            evaluate(cand, world(), decision_at=NOW, exit_at=NOW+timedelta(hours=73), guard=G, portfolio=portfolio())

    def test_debit_risk_cap(self) -> None:
        cand = Candidate('LONG_EXPENSIVE', (Leg(quote(Right.CALL, '100', '4', '4.1'), 1),))
        result = evaluate(cand, world(), decision_at=NOW, exit_at=EXIT, guard=G, portfolio=portfolio())
        self.assertFalse(result.admitted)
        self.assertGreater(result.max_loss_usd, 50)

    def test_credit_vertical_finite_risk(self) -> None:
        # Sell lower strike PUT, buy higher? For bull put: short upper strike put, long lower strike put.
        cand = Candidate('BULL_PUT', (
            Leg(quote(Right.PUT, '100', '0.30', '0.32'), -1),
            Leg(quote(Right.PUT, '99.75', '0.12', '0.14'), 1),
        ))
        self.assertLess(_max_loss(cand, G), D('50'))
        a = evaluate(cand, world(), decision_at=NOW, exit_at=EXIT, guard=G, portfolio=portfolio())
        self.assertTrue(a.admitted)

    def test_wider_credit_vertical_rejected(self) -> None:
        cand = Candidate('WIDE', (
            Leg(quote(Right.CALL, '100', '0.30', '0.32'), -1),
            Leg(quote(Right.CALL, '102', '0.10', '0.12'), 1),
        ))
        self.assertFalse(evaluate(cand, world(), decision_at=NOW, exit_at=EXIT,
                                  guard=G, portfolio=portfolio()).admitted)

    def test_cash_on_unpriced_edge(self) -> None:
        cand = Candidate('COSTLY', (Leg(quote(Right.CALL, '110', '0.20', '0.30'), 1),))
        scenarios = (Scenario(1.0, 100.0, 0.15, NOW),)
        selected, _ = select([cand], scenarios, decision_at=NOW, exit_at=EXIT, guard=G, portfolio=portfolio())
        self.assertEqual(selected, 'CASH')

    def test_winner_requires_forecast_after_costs(self) -> None:
        cand = Candidate('CHEAP_CALL', (Leg(quote(Right.CALL, '102', '0.10', '0.15'), 1),))
        selected, evidence = select([cand], world(), decision_at=NOW, exit_at=EXIT, guard=G, portfolio=portfolio())
        self.assertEqual(selected, 'CHEAP_CALL')
        self.assertGreater(evidence[0].worst_case_log_growth, 0)

    def test_shared_reservations_stop_new_trade(self) -> None:
        cand = Candidate('CALL', (Leg(quote(Right.CALL, '102', '0.10', '0.15'), 1),))
        p = portfolio(risk_reserved=D('49'))
        result = evaluate(cand, world(), decision_at=NOW, exit_at=EXIT, guard=G, portfolio=p)
        self.assertEqual(result.reason, 'SHARED_OPEN_RISK')

    def test_daily_loss_halts(self) -> None:
        cand = Candidate('CALL', (Leg(quote(Right.CALL, '102', '0.10', '0.15'), 1),))
        p = portfolio(equity=D('19600'), cash=D('19600'))
        self.assertEqual(evaluate(cand, world(), decision_at=NOW, exit_at=EXIT,
                                  guard=G, portfolio=p).reason, 'SESSION_HALT')

    def test_decimal_cash_and_risk_exact(self) -> None:
        cand = Candidate('CALL', (Leg(quote(Right.CALL, '102', '0.10', '0.15'), 1),))
        # Worst-case loss includes both fees, buy-side slippage, and close fee.
        self.assertEqual(_max_loss(cand, G), D('17.30'))

    def test_robust_mean_worse_than_nominal(self) -> None:
        self.assertAlmostEqual(_robust_mean((-2.0, 3.0), (0.2, 0.8), 0.1), 1.5, places=12)

    def test_future_portfolio_rejected(self) -> None:
        cand = Candidate('CALL', (Leg(quote(Right.CALL, '102', '0.1', '0.15'), 1),))
        with self.assertRaisesRegex(ValueError, 'future portfolio'):
            evaluate(cand, world(), decision_at=NOW, exit_at=EXIT, guard=G,
                     portfolio=portfolio(known_at=NOW+timedelta(seconds=1)))

    def test_engine_is_read_only(self) -> None:
        import inspect
        import quant.harpoon_quant.n10_options as module
        source = inspect.getsource(module).lower()
        for banned in ('alpaca', 'submit_order', 'requests.post', 'httpx', 'websocket', 'create_order'):
            self.assertNotIn(banned, source)


if __name__ == '__main__':
    unittest.main()
