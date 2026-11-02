import unittest,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harpoon_quant.vector_gate import allocate,hac_covariance
class VectorTests(unittest.TestCase):
    def call(self,p,**kw):
        n,s=p.shape[1:];args=dict(funding=[100]*n,variable=np.zeros((n,s)),activation=np.zeros((n,s)),shared=np.zeros(s),max_lots=[1]*n,equity=10000,cash=1000,risk_limit=500,z=3)
        args.update(kw);return allocate(p,**args)
    def test_negative_edges_do_not_become_profit(self):
        r=self.call(np.full((40,2,2),-1.));self.assertEqual(r['lots'],[0,0])
    def test_stress_veto(self):
        p=np.ones((40,1,2))*10;p[:,:,1]=-1
        self.assertEqual(self.call(p)['lots'],[0])
    def test_reopt_after_bad_leg(self):
        p=np.ones((40,2,1))*10;p[:,0,0]=np.tile([-100,120],20)
        self.assertEqual(self.call(p)['lots'],[0,1])
    def test_fixed_cost_once_not_per_lot(self):
        r=self.call(np.ones((40,1,1))*4,activation=[[5]],max_lots=[2]);self.assertEqual(r['lots'],[2]);self.assertAlmostEqual(r['certificate']['mean_net_usd'][0],3)
    def test_shared_cost_not_hidden(self):
        r=self.call(np.ones((40,1,1))*4,shared=[5]);self.assertEqual(r['lots'],[0])
    def test_funding_includes_fees(self):
        r=self.call(np.ones((40,1,1))*4,cash=100,activation=[[1]]);self.assertEqual(r['lots'],[0])
    def test_partial_hedges_cannot_fund_each_other(self):
        p=np.empty((40,2,1));p[:,0,0]=np.tile([-100,120],20);p[:,1,0]=np.tile([120,-100],20)
        self.assertEqual(self.call(p,risk_limit=50,z=0)['lots'],[0,0])
    def test_hac_psd_and_iid_floor(self):
        x=np.random.default_rng(1).normal(size=(80,3));c=hac_covariance(x)
        self.assertGreaterEqual(np.linalg.eigvalsh(c).min(),-1e-12)
        self.assertGreaterEqual(np.linalg.eigvalsh(c-np.cov(x,rowvar=False)/80).min(),-1e-12)
    def test_dimensions_and_budget(self):
        with self.assertRaises(ValueError):self.call(np.ones((40,2,1)),max_lots=[1000,1000])
        with self.assertRaises(ValueError):self.call(np.ones((40,1,1)),variable=[1])
    def test_work_budget(self):
        with self.assertRaisesRegex(ValueError,'WORK_BUDGET'):
            self.call(np.ones((2000,6,8)),max_lots=[3]*6)
    def test_linear_factor_limit(self):
        r=self.call(np.ones((40,2,1))*10,limits=([[100,100]],[100]));self.assertEqual(sum(r['lots']),1)
if __name__=='__main__':unittest.main()
