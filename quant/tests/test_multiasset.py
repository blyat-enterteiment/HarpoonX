"""Synthetic adversarial mechanism tests; not economic evidence."""
import copy
import importlib.util
import sys
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harpoon_quant.multiasset import allocation,calibrate_fills,normalize,number,replay,signal,stamp


def bundle(mode='LIVE'):
    return {'schema':'HARPOON_OBSERVED_FILLS_1','mode':mode,'available_at':'2025-02-01T00:00:00Z','fills':[
        {'fill_id':'f','order_id':'o','book':'equity','symbol':'SPY','side':'buy','qty':10,'price':101,
         'bid':99,'ask':101,'fee_usd':1,'fee_receipt_id':'explicit-fee','quote_at':'2025-01-01T14:59:59Z',
         'quote_received_at':'2025-01-01T14:59:59Z','decision_at':'2025-01-01T15:00:00Z',
         'filled_at':'2025-01-01T15:00:01Z'}]}


class MultiassetTests(unittest.TestCase):
    def test_time_and_numeric_domain(self):
        for v in ('2025-01-01T00:00:00',):
            with self.assertRaises(ValueError):stamp(v)
        for v in (True,float('nan'),float('inf'),'3'):
            with self.assertRaises(ValueError):number(v)

    def test_incomplete_universe_rejected(self):
        with self.assertRaisesRegex(ValueError,'MISSING'):
            normalize([{'bars':{}}],['SPY'],stamp('2025-01-01T00:00:00Z'),stamp('2026-01-01T00:00:00Z'))

    def test_duplicates_not_silently_deduped(self):
        bar={'timestamp':'2025-01-01T00:00:00Z','open':1,'high':2,'low':1,'close':2,'volume':5}
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):
            normalize([{'bars':{'SPY':[bar,bar]}}],['SPY'],stamp('2025-01-01T00:00:00Z'),stamp('2026-01-01T00:00:00Z'))

    def test_end_exclusive(self):
        bars=[{'timestamp':t,'open':1,'high':2,'low':1,'close':2,'volume':5}
              for t in ('2025-12-31T23:00:00Z','2026-01-01T00:00:00Z')]
        panel,_=normalize([{'bars':{'SPY':bars}}],['SPY'],stamp('2025-01-01T00:00:00Z'),stamp('2026-01-01T00:00:00Z'))
        self.assertEqual(len(panel['SPY']),1)

    def test_bad_ohlc(self):
        bar={'timestamp':'2025-01-01T00:00:00Z','open':3,'high':2,'low':1,'close':2,'volume':5}
        with self.assertRaisesRegex(ValueError,'OHLCV'):
            normalize([{'bars':{'SPY':[bar]}}],['SPY'],stamp('2025-01-01T00:00:00Z'),stamp('2026-01-01T00:00:00Z'))

    def test_capital_caps_even_both_crypto_selected(self):
        rows=[{'symbol':s,'score':4-i,'vol':.01,'book':'crypto' if '/' in s else 'equity'}
              for i,s in enumerate(['BTC/USD','ETH/USD','SPY'])]
        for policy in ('JOINT','SLEEVES'):
            weights=allocation(rows,policy)
            self.assertLessEqual(sum(weights.values()),.6+1e-12)
            self.assertLessEqual(weights.get('BTC/USD',0)+weights.get('ETH/USD',0),.2+1e-12)
            self.assertTrue(all(v<=.2 for v in weights.values()))

    def test_future_bars_do_not_change_signal(self):
        at=stamp('2025-01-01T00:00:00Z');rows=[]
        for i in range(65):
            p=100+i*.1+(i%2)*.02
            rows.append({'at':at+timedelta(hours=i),'known':at+timedelta(hours=i+1,seconds=60),'close':p,'volume':1000})
        when=at+timedelta(hours=63)
        a=signal(rows,when);mutated=copy.deepcopy(rows)
        for r in mutated:
            if r['known']>=when:r['close']*=1000
        self.assertEqual(a,signal(mutated,when));self.assertIsNotNone(a)

    def test_cash_no_reset_shared_cost_once(self):
        a=replay({},'CASH');b=replay({},'CASH',True)
        self.assertEqual(a['terminal_usd'],19635)
        self.assertEqual(b['terminal_usd'],19270)
        self.assertEqual(a['reconciliation_error_usd'],0)
        self.assertEqual(a['curve'][1]['equity'],19998)
        self.assertFalse(a['level8_accredited'])

    def test_shortfall_sign_and_no_double_spread_charge(self):
        b=bundle();r=calibrate_fills(b)['groups']['LIVE:equity:buy']
        self.assertAlmostEqual(r['weighted_shortfall_bps'],110)
        b['fills'][0].update(side='sell',price=99)
        self.assertAlmostEqual(calibrate_fills(b)['groups']['LIVE:equity:sell']['weighted_shortfall_bps'],110)

    def test_duplicate_partial_fills(self):
        b=bundle();b['fills']*=2
        with self.assertRaisesRegex(ValueError,'UNIQUE'):calibrate_fills(b)

    def test_missing_fees_not_zero(self):
        b=bundle();del b['fills'][0]['fee_usd']
        with self.assertRaises(KeyError):calibrate_fills(b)

    def test_post_decision_quote_rejected(self):
        b=bundle();b['fills'][0]['quote_received_at']='2025-01-01T15:00:01Z'
        with self.assertRaisesRegex(ValueError,'NONCAUSAL'):calibrate_fills(b)

    def test_stale_quote_rejected(self):
        b=bundle();b['fills'][0]['quote_at']='2025-01-01T14:59:54Z'
        with self.assertRaisesRegex(ValueError,'STALE'):calibrate_fills(b)

    def test_paper_never_live(self):
        b=bundle('PAPER');base=b['fills'][0];b['fills']=[]
        for i in range(30):
            row=dict(base,fill_id=str(i),order_id=str(i));day=1+i%15
            for key in ('quote_at','quote_received_at','decision_at','filled_at'):
                row[key]=base[key].replace('2025-01-01',f'2025-01-{day:02}')
            b['fills'].append(row)
        r=calibrate_fills(b)
        self.assertTrue(r['groups']['PAPER:equity:buy']['enough_observations'])
        self.assertFalse(r['groups']['PAPER:equity:buy']['live_cost_calibration_ready'])
        self.assertFalse(r['financial_acceptance_allowed'])

    def test_one_order_partial_fills_not_independent_sample(self):
        b=bundle();b['fills']=[dict(b['fills'][0],fill_id=str(i)) for i in range(100)]
        self.assertFalse(calibrate_fills(b)['groups']['LIVE:equity:buy']['enough_observations'])

    def test_calibration_cannot_know_future_fills(self):
        b=bundle();b['available_at']='2025-01-01T15:00:00Z'
        with self.assertRaisesRegex(ValueError,'BEFORE_FILL'):calibrate_fills(b)

    def test_mixed_paper_live_rejected(self):
        b=bundle();b['fills'][0]['mode']='PAPER'
        with self.assertRaisesRegex(ValueError,'MIXED'):calibrate_fills(b)

    def test_collector_readonly_and_pagination_bound(self):
        spec=importlib.util.spec_from_file_location('fills8',Path(__file__).resolve().parents[2]/'tools/observed_fills8.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        calls=[]
        def transport(route):
            calls.append(route)
            return [{'id':str(i),'activity_type':'FILL'} for i in range(100)] if len(calls)==1 else []
        r=module.collect('PAPER','2025-01-01T00:00:00Z','2025-02-01T00:00:00Z',transport)
        self.assertEqual(len(r['activities']),100)
        self.assertTrue(all(c.startswith('/v2/account/activities?') for c in calls))
        self.assertIn('page_token=99',calls[1])
        self.assertFalse(r['calibration_ready'])

    def test_collector_rejects_repeating_token(self):
        spec=importlib.util.spec_from_file_location('fills8b',Path(__file__).resolve().parents[2]/'tools/observed_fills8.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):
            module.collect('LIVE','2025-01-01T00:00:00Z','2025-02-01T00:00:00Z',lambda route:[{'id':str(i)} for i in range(100)])

if __name__=='__main__':unittest.main()
