"""Bounded deterministic fixtures, without reading option market outcomes."""
from __future__ import annotations

import unittest
from datetime import date
import pandas as pd

from reverse_engineer import (_best_decision_candidate, _enter_and_exit,
                              _summarize_policy, options_at_d, policy_pick)

D=date(2025,1,6)
ENTRY=date(2025,1,7)
EXIT=date(2025,1,8)


def df(day:date, *, exit_bid:float|None=.4, entry:bool=False) -> pd.DataFrame:
    rows=[]
    for right,delta,ident in [('P',-.08,'P100'),('C',.08,'C100')]:
        bid=.10 if right=='P' else .12
        ask=.15 if right=='P' else .18
        if entry:
            ask+=.01
        if day==EXIT:
            bid=exit_bid
            if exit_bid is None:
                continue
            ask=(exit_bid+.03) if exit_bid is not None else .04
        rows.append(dict(date=day,contract_id=ident,expiration=date(2025,1,17),
                         type=right,strike=100.,bid=bid,ask=ask,bid_size=3,
                         ask_size=3,volume=10,open_interest=100,delta=delta,
                         implied_volatility=.20 if right=='P' else .24))
    if rows:
        return pd.DataFrame(rows)
    return pd.DataFrame(columns=['date','contract_id','expiration','type','strike',
                                 'bid','ask','bid_size','ask_size','volume',
                                 'open_interest','delta','implied_volatility'])


class TestN10Xray(unittest.TestCase):
    def setUp(self)->None:
        self.decision=options_at_d(df(D),EXIT)
        self.future=_enter_and_exit(self.decision,df(ENTRY,entry=True),df(EXIT),EXIT)

    def test_two_valid_candidates(self)->None:
        self.assertEqual(len(self.decision),2)

    def test_prognosis_has_no_future_dependence(self)->None:
        first=policy_pick('FOLLOW_3D_08',self.decision,{'r3':.02,'rv20':.2})
        changed_future=_enter_and_exit(self.decision,df(ENTRY,entry=True),df(EXIT,exit_bid=.01),EXIT)
        again=policy_pick('FOLLOW_3D_08',self.decision,{'r3':.02,'rv20':.2})
        self.assertEqual(first,again)
        self.assertNotEqual(self.future.pnl_usd.tolist(),changed_future.pnl_usd.tolist())

    def test_liquid_put_control(self)->None:
        self.assertEqual(policy_pick('PUT_08_P1_CONTROL',self.decision,{'r3':.03,'rv20':.3})['type'],'P')

    def test_trend_has_two_directions(self)->None:
        self.assertEqual(policy_pick('FOLLOW_3D_08',self.decision,{'r3':.03,'rv20':.3})['type'],'C')
        self.assertEqual(policy_pick('FOLLOW_3D_08',self.decision,{'r3':-.03,'rv20':.3})['type'],'P')

    def test_iv_discount_requires_strict_premium(self)->None:
        self.assertIsNone(policy_pick('IV_DISCOUNT_TREND',self.decision,{'r3':-.02,'rv20':.20}))
        self.assertEqual(policy_pick('IV_DISCOUNT_TREND',self.decision,{'r3':-.02,'rv20':.40})['type'],'P')

    def test_reversal_is_sparse(self)->None:
        self.assertIsNone(policy_pick('REVERSAL_ABS_2PCT',self.decision,{'r3':.01,'rv20':.3}))
        self.assertEqual(policy_pick('REVERSAL_ABS_2PCT',self.decision,{'r3':.03,'rv20':.3})['type'],'P')
        self.assertEqual(policy_pick('REVERSAL_ABS_2PCT',self.decision,{'r3':-.03,'rv20':.3})['type'],'C')

    def test_one_trade_cashflow(self)->None:
        p=self.future.set_index('contract_id').loc['P100']
        self.assertAlmostEqual(float(p.debit_usd),17.65)
        self.assertAlmostEqual(float(p.credit_usd),38.35)
        self.assertAlmostEqual(float(p.pnl_usd),20.70)

    def test_missing_exit_is_full_writeoff(self)->None:
        empty=df(EXIT,exit_bid=None)
        result=_enter_and_exit(self.decision,df(ENTRY,entry=True),empty,EXIT)
        p=result.set_index('contract_id').loc['P100']
        self.assertTrue(bool(p.feasible))
        self.assertFalse(bool(p.exit_quote_observed))
        self.assertAlmostEqual(float(p.pnl_usd),-17.65)

    def test_no_ioc_above_limit(self)->None:
        expensive=df(ENTRY,entry=True)
        expensive.loc[expensive.contract_id=='P100','ask']=.48
        result=_enter_and_exit(self.decision,expensive,df(EXIT),EXIT)
        self.assertFalse(bool(result.set_index('contract_id').loc['P100','feasible']))

    def test_portfolio_ledger_reconciliation(self)->None:
        p=self.future.set_index('contract_id').loc['P100']
        after={'id':'P100','type':'P','feasible':True,'debit_usd':float(p.debit_usd),
               'credit_usd':float(p.credit_usd),'entry_bid':float(p.entry_bid),
               'pnl_usd':float(p.pnl_usd),'exit_quote_observed':True}
        rec={'decision_date':str(D),'entry_date':str(ENTRY),'exit_date':str(EXIT),
             'picked':{'PUT_08_P1_CONTROL':_best_decision_candidate(self.decision,'P')},
             'outcomes':{'P100':after},'r3':-.01,'rv20':.3}
        summary,trades,ledger=_summarize_policy('PUT_08_P1_CONTROL',[rec])
        self.assertEqual(summary['trades'],1)
        self.assertAlmostEqual(summary['net_usd'],20.70-120,places=5)
        self.assertEqual(len(ledger),120)
        self.assertAlmostEqual(float(trades[0]['pnl_usd']),20.70)
        entry_ledger=next(x for x in ledger if x['date']==str(ENTRY))
        self.assertGreater(entry_ledger['equity_usd'],20000-120-17.65)

    def test_no_trade_costs_are_equal_cash(self)->None:
        result,_,ledger=_summarize_policy('CASH',[])
        self.assertEqual(result['net_usd'],-120.)
        self.assertEqual(ledger[-1]['equity_usd'],19880)

if __name__=='__main__':
    unittest.main()
