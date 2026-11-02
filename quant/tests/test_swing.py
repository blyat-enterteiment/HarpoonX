"""Synthetic mechanism and adversarial tests. No economic performance claims."""
import copy,sys,unittest
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harpoon_quant.swing import NY,UTC,candidate,daily_features,deadline,replay
from harpoon_quant.multiasset import stamp


def sessions(days):
    return {d:{k:datetime.fromisoformat(d+'T'+t).replace(tzinfo=NY).astimezone(UTC) for k,t in [('open','09:30'),('close','16:00')]}for d in days}


def fixture():
    when=stamp('2025-01-06T17:00:00Z');ds=[];hs=[]
    for i in range(65):
        at=when-timedelta(days=66-i)
        ds.append(dict(at=at,known=at+timedelta(hours=8),open=100,high=101,low=99,close=100,volume=100))
    ds[-1].update(close=102,high=103,volume=200)
    for i in range(30):
        at=when-timedelta(hours=32-i)
        hs.append(dict(at=at,known=at+timedelta(hours=1,seconds=60),open=102,high=102.2,low=101.2,close=102,volume=100000))
    # most recent confirmed bar from today's session, low tests previous high.
    hs[-1].update(at=when-timedelta(hours=2),known=when-timedelta(minutes=59),low=101.1)
    return when,ds,hs


class SwingTests(unittest.TestCase):
    def test_weekend_plan_is_real_elapsed_time(self):
        cal=sessions(['2025-01-03','2025-01-06','2025-01-07'])
        w=stamp('2025-01-03T17:00:00Z');d=deadline(w,'equity',cal,stamp('2025-01-10T00:00:00Z'))
        self.assertEqual((d-w).total_seconds()/3600,72)

    def test_dst_73_hour_weekend_cannot_violate72(self):
        cal=sessions(['2025-10-31','2025-11-03'])
        self.assertIsNone(deadline(stamp('2025-10-31T16:00:00Z'),'equity',cal,stamp('2025-11-05T00:00:00Z')))

    def test_dst_spring71_hours_allowed(self):
        cal=sessions(['2025-03-07','2025-03-10'])
        w=stamp('2025-03-07T17:00:00Z');d=deadline(w,'equity',cal,stamp('2025-03-12T00:00:00Z'))
        self.assertEqual((d-w).total_seconds()/3600,71)

    def test_half_day_and_long_holiday_no_fake_session(self):
        cal=sessions(['2025-11-28','2025-12-02'])
        self.assertIsNone(deadline(stamp('2025-11-28T17:00:00Z'),'equity',cal,stamp('2025-12-04T00:00:00Z')))

    def test_crypto_48hours(self):
        w=stamp('2025-01-03T17:00:00Z');self.assertEqual(deadline(w,'crypto',{},w+timedelta(days=3))-w,timedelta(hours=48))

    def test_breakout_and_retest_are_distinct_signals(self):
        w,ds,hs=fixture()
        self.assertIsNotNone(candidate('SPY','BREAKOUT',w,ds,hs,102,None,.0005))
        self.assertIsNotNone(candidate('SPY','RETEST',w,ds,hs,102,None,.0005))
        h=copy.deepcopy(hs);h[-1]['low']=102
        self.assertIsNone(candidate('SPY','RETEST',w,ds,h,102,None,.0005))

    def test_gap_confirmation_and_crypto_exclusion(self):
        w,ds,hs=fixture();hs[-1].update(close=104,high=104.1)
        self.assertIsNotNone(candidate('SPY','GAP',w,ds,hs,104,103.1,.0005))
        self.assertIsNone(candidate('BTC/USD','GAP',w,ds,hs,104,103,.0035))
        hs[-1]['close']=102.9
        self.assertIsNone(candidate('SPY','GAP',w,ds,hs,103,103,.0005))

    def test_no_chasing_and_no_late_data(self):
        w,ds,hs=fixture()
        self.assertIsNone(candidate('SPY','BREAKOUT',w,ds,hs,110,None,.0005))
        a=candidate('SPY','BREAKOUT',w,ds,hs,102,None,.0005)
        future=dict(ds[-1],known=w+timedelta(hours=1),close=10000)
        futureh=dict(hs[-1],known=w+timedelta(hours=1),close=10000)
        self.assertEqual(a,candidate('SPY','BREAKOUT',w,ds+[future],hs+[futureh],102,None,.0005))

    def test_cost_hurdle_rejects_more_expensive_entry(self):
        w,ds,hs=fixture()
        self.assertIsNone(candidate('SPY','BREAKOUT',w,ds,hs,102,None,.05))

    def test_discontinuity_not_alpha(self):
        w,ds,hs=fixture();ds[-2]['close']=200
        self.assertIsNone(daily_features(ds))

    def account(self,collision=False,gap=False,dividend=False):
        start=stamp('2025-01-01T00:00:00Z');end=start+timedelta(days=8)
        rows=[]
        for i in range(8*24):
            at=start+timedelta(hours=i);o=100
            if gap and at>=stamp('2025-01-05T14:00:00Z'):o=80
            rows.append(dict(at=at,known=at+timedelta(hours=1,seconds=60),open=o,high=o+.1,low=o-.1,close=o,volume=100000))
        if collision:
            next(r for r in rows if r['at']==stamp('2025-01-04T17:00:00Z')).update(low=80,high=120)
        def setup(s,rule,w,ds,hs,entry,opening,rate):
            if w!=stamp('2025-01-04T17:00:00Z'):return None
            return dict(symbol=s,book='crypto',atr=5,score=1,stop=90,target=115,level=95,
                        signal_known_at=(w-timedelta(hours=1)).isoformat(),capacity=100000)
        actions=[dict(symbol='BTC/USD',kind='dividend',id='synthetic-div',date='2025-01-05',pay='2025-01-07',rate=1)] if dividend else []
        with patch('harpoon_quant.swing.candidate',side_effect=setup):
            return replay({'BTC/USD':rows},{'BTC/USD':rows}, {},actions,'BREAKOUT',False,start,end)

    def test_collision_stop_first(self):
        r=self.account(collision=True);t=r['trades'][0]
        self.assertEqual(t['exit_reason'],'STOP');self.assertEqual(t['exit_price'],90)
        self.assertLess(t['net_usd'],0)

    def test_gap_stop_worse_than_stop(self):
        r=self.account(gap=True);t=r['trades'][0]
        self.assertEqual(t['exit_reason'],'GAP_STOP');self.assertEqual(t['exit_price'],80)

    def test_funded_continuous_account_risk_and_holding(self):
        r=self.account();self.assertEqual(r['trades'][0]['holding_hours'],48)
        self.assertLessEqual(r['max_entry_gross_fraction'],.6+1e-10)
        self.assertLessEqual(r['max_entry_crypto_fraction'],.2+1e-10)
        self.assertLessEqual(r['max_entry_stop_risk_fraction'],.01+1e-10)
        self.assertAlmostEqual(r['terminal_usd'],20000+sum(t['net_usd'] for t in r['trades'])-8)

    def test_dividend_receivable_not_double_counted(self):
        r=self.account(dividend=True);ex=sum(e['amount'] for e in r['events'] if e['kind']=='DIV_EX')
        paid=sum(e['cash_delta'] for e in r['events'] if e['kind']=='DIV_PAY')
        self.assertEqual(ex,paid);self.assertGreater(ex,0)
        self.assertAlmostEqual(r['terminal_usd'],20000+sum(t['net_usd'] for t in r['trades'])+ex-8)

    def test_cash_pays_fixed_once_per_calendar_day(self):
        start=stamp('2025-01-01T00:00:00Z')
        r=replay({}, {}, {}, [],'CASH',True,start,start+timedelta(days=5))
        self.assertEqual(r['terminal_usd'],19990)
        self.assertEqual(len([e for e in r['events'] if e['kind']=='FIXED']),5)
        self.assertFalse(r['execution_allowed'])

if __name__=='__main__':unittest.main()
