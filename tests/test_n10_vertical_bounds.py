"""Deterministic non-economic contracts for N10 P4: European P-vs-Q guards."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

from quant.harpoon_quant.n10_vertical_bounds import (
    EuropeanQuote, Vertical, Side, PhysicalScenario, Funding,
    assert_parity, assert_convexity, quote_band, kl_lower, assess, choose,
)

NOW=datetime(2026,11,13,15,tzinfo=timezone.utc)
EX=NOW+timedelta(days=2)


def q(k:str,b:str,a:str,side:Side=Side.CALL, *, known_at:datetime=NOW,
      style:str='EUROPEAN_CASH',expiry:datetime=EX)->EuropeanQuote:
    return EuropeanQuote('XSP',side,D(k),D(b),D(a),expiry,known_at,exercise_style=style)


def book(**updates:object)->Funding:
    d=dict(equity=D(20000),cash=D(20000),risk_reserved=D(0),admission_reserved=D(0),known_at=NOW)
    d.update(updates)
    return Funding(**d)


def physical(p:float=.5,known_at:datetime=NOW)->tuple[PhysicalScenario,...]:
    return (PhysicalScenario(103,p,known_at),PhysicalScenario(100,1-p,known_at))


class VerticalBoundsTests(unittest.TestCase):
    def test_call_risk_neutral_band(self)->None:
        v=Vertical(q('101','.15','.18'),q('102','.10','.12'))
        b=quote_band(v,decision_at=NOW)
        self.assertAlmostEqual(b.low,.03,places=8)
        self.assertAlmostEqual(b.high,.08,places=8)
        self.assertEqual(b.ask_debit_usd,D('8.00'))
        self.assertIn('AVERAGED',b.interpretation)

    def test_put_risk_neutral_band(self)->None:
        v=Vertical(q('100','.20','.22',Side.PUT),q('101','.30','.34',Side.PUT))
        b=quote_band(v,decision_at=NOW)
        self.assertAlmostEqual(b.low,.08,places=9)
        self.assertAlmostEqual(b.high,.14,places=9)
        self.assertEqual(b.ask_debit_usd,D('14.00'))

    def test_intrinsic_call_put_complement(self)->None:
        c=Vertical(q('100','2.10','2.15'),q('101','1.70','1.75'))
        p=Vertical(q('100','1.40','1.45',Side.PUT),q('101','2.00','2.05',Side.PUT))
        ca,pu=assert_parity(c,p,decision_at=NOW)
        self.assertLessEqual(ca.low+pu.low,1)
        self.assertGreaterEqual(ca.high+pu.high,1)
        for s in (95,100,100.5,101,110):
            self.assertAlmostEqual(c.payoff_fraction(s)+p.payoff_fraction(s),1)

    def test_broken_put_call_parity(self)->None:
        c=Vertical(q('100','2.10','2.15'),q('101','1.70','1.75'))
        p=Vertical(q('100','.20','.25',Side.PUT),q('101','.30','.35',Side.PUT))
        with self.assertRaisesRegex(ValueError,'parity'):
            assert_parity(c,p,decision_at=NOW)

    def test_broken_convexity(self)->None:
        left=Vertical(q('100','2.00','2.02'),q('101','1.60','1.62'))
        right=Vertical(q('101','1.60','1.62'),q('102','.90','.92'))
        with self.assertRaisesRegex(ValueError,'convexity'):
            assert_convexity(left,right,decision_at=NOW)

    def test_crossed_vertical_arbitrage(self)->None:
        v=Vertical(q('100','1.00','1.05'),q('101','1.10','1.15'))
        with self.assertRaisesRegex(ValueError,'arbitrage'):
            quote_band(v,decision_at=NOW)

    def test_american_spy_rejected(self)->None:
        with self.assertRaisesRegex(ValueError,'European'):
            q('100','.2','.25',style='AMERICAN_PHYSICAL')

    def test_stale_and_future_rejected(self)->None:
        for ts in (NOW-timedelta(minutes=10),NOW+timedelta(seconds=1)):
            v=Vertical(q('101','.15','.18',known_at=ts),q('102','.10','.12',known_at=ts))
            with self.assertRaisesRegex(ValueError,'stale|future'):
                quote_band(v,decision_at=NOW)

    def test_outside_72h_rejected(self)->None:
        ex=NOW+timedelta(hours=73)
        v=Vertical(q('101','.15','.18',expiry=ex),q('102','.10','.12',expiry=ex))
        with self.assertRaisesRegex(ValueError,'72-hour'):
            quote_band(v,decision_at=NOW)

    def test_invalid_discount_rejected(self)->None:
        v=Vertical(q('101','.15','.18'),q('102','.10','.12'))
        with self.assertRaisesRegex(ValueError,'discount'):
            quote_band(v,decision_at=NOW,discount_factor=D('1.02'))

    def test_kl_lower_monotonic(self)->None:
        p=(.5,.5)
        v=(0.0,1.0)
        a=kl_lower(v,p,0)
        b=kl_lower(v,p,.02)
        c=kl_lower(v,p,.1)
        self.assertAlmostEqual(a,.5,places=10)
        self.assertGreater(a,b)
        self.assertGreater(b,c)
        self.assertGreater(c,0)
        self.assertAlmostEqual(kl_lower(v,p,1),0)

    def test_positive_call_with_robust_physical_tail(self)->None:
        v=Vertical(q('101','.15','.18'),q('102','.10','.12'))
        result=assess(v,physical(.7),decision_at=NOW,funding=book())
        self.assertTrue(result.admitted)
        self.assertEqual(result.reason,'RESEARCH_ELIGIBLE_ONLY')
        self.assertEqual(result.max_loss_usd,D('12.60'))
        self.assertEqual(choose((result,)),result.label)

    def test_positive_put_synthetic_forecast(self)->None:
        v=Vertical(q('100','.20','.22',Side.PUT),q('101','.30','.34',Side.PUT))
        p=(PhysicalScenario(98,.8,NOW),PhysicalScenario(103,.2,NOW))
        result=assess(v,p,decision_at=NOW,funding=book())
        self.assertTrue(result.admitted)
        self.assertEqual(result.max_loss_usd,D('18.60'))

    def test_cash_on_negative_edge(self)->None:
        v=Vertical(q('101','.15','.18'),q('102','.10','.12'))
        result=assess(v,physical(.01),decision_at=NOW,funding=book())
        self.assertFalse(result.admitted)
        self.assertEqual(choose((result,)),'CASH')

    def test_shared_risk_rejection(self)->None:
        v=Vertical(q('101','.15','.18'),q('102','.10','.12'))
        result=assess(v,physical(.8),decision_at=NOW,funding=book(risk_reserved=D('49')))
        self.assertFalse(result.admitted)
        self.assertEqual(result.reason,'SHARED_OPEN_RISK')

    def test_full_contractual_risk_rejection(self)->None:
        v=Vertical(q('101','.60','.80'),q('102','.10','.12'))
        result=assess(v,physical(.8),decision_at=NOW,funding=book())
        self.assertFalse(result.admitted)
        self.assertEqual(result.reason,'SHARED_OPEN_RISK')

    def test_future_forecast_or_portfolio_rejected(self)->None:
        v=Vertical(q('101','.15','.18'),q('102','.10','.12'))
        with self.assertRaisesRegex(ValueError,'future'):
            assess(v,physical(.5,NOW+timedelta(seconds=1)),decision_at=NOW,funding=book())
        with self.assertRaisesRegex(ValueError,'future'):
            assess(v,physical(.5),decision_at=NOW,funding=book(known_at=NOW+timedelta(seconds=1)))

    def test_invalid_probabilities_rejected(self)->None:
        v=Vertical(q('101','.15','.18'),q('102','.10','.12'))
        with self.assertRaisesRegex(ValueError,'sum'):
            assess(v,(PhysicalScenario(100,.1,NOW),PhysicalScenario(103,.1,NOW)),decision_at=NOW,funding=book())


if __name__=='__main__':
    unittest.main()
