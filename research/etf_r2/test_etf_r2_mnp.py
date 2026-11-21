"""ETF-R2 MNP synthetic engineering tests; not an economic backtest."""
import unittest
from dataclasses import replace
from research.etf_r2.etf_r2_mnp import (Observation,score,economic_gate,
                                       paired_growth,POLICIES,provenance)
def obs(**changes):
    base=Observation(symbol="TQQQ",at="2026-10-13T14:30:00Z",
        known_at="2026-10-13T14:30:01Z",macd_hist_delta=.4,
        macd_scale=.2,adverse_pressure_delta=-.2,adverse_scale=.1,
        signed_efficiency=.5,relative_activity=2.,spread_bps=8.,
        quote_age_ms=100.,verified_cross_etf=True)
    return replace(base,**changes)
class TestETFR2MNP(unittest.TestCase):
 def test_bounded_equal_weight_crp(self):
    r=score(obs(),"2026-10-13T14:30:02Z")
    self.assertEqual(r["status"],"FEATURE_ONLY_NOT_TRADE")
    self.assertTrue(-1<=r["crp"]<=1)
    self.assertAlmostEqual(sum(r["weights"]),1)
 def test_future_information_rejected(self):
    with self.assertRaises(ValueError):
        score(obs(known_at="2026-10-13T14:30:03Z"),"2026-10-13T14:30:02Z")
 def test_hcmt_without_verified_pair_abstains(self):
    r=score(obs(symbol="HCMT"),"2026-10-13T14:30:02Z")
    self.assertEqual(r["status"],"ABSTAIN_UNVERIFIED_CROSS_ETF")
 def test_uncalibrated_positive_score_cannot_promote(self):
    r=score(obs(),"2026-10-13T14:30:02Z")
    self.assertEqual(economic_gate(r)["status"],"NO_GO_UNCALIBRATED_OR_UNVERIFIED")
 def test_negative_net_edge_abstains(self):
    r=score(obs(),"2026-10-13T14:30:02Z")
    x=economic_gate(r,calibrated_expected_gross_bps=10,
       estimated_roundtrip_cost_bps=20,lower_bound_bps=1,
       preregistered=True,independent_oos=True,execution_quotes_verified=True)
    self.assertEqual(x["status"],"ABSTAIN_NO_NET_EDGE")
 def test_positive_edge_only_research_eligible(self):
    r=score(obs(),"2026-10-13T14:30:02Z")
    x=economic_gate(r,calibrated_expected_gross_bps=30,
       estimated_roundtrip_cost_bps=10,lower_bound_bps=1,
       preregistered=True,independent_oos=True,execution_quotes_verified=True)
    self.assertEqual(x["status"],"RESEARCH_ELIGIBLE")
    self.assertFalse(x["orders_enabled"])
 def test_paired_growth_includes_abstention(self):
    paths={p:[20000.,20000.,20000.] for p in POLICIES}
    paths["CRP5"]=[20000.,20000.,20100.]
    self.assertGreater(paired_growth(paths)["incremental_crp_vs_break5"],0)
 def test_missing_comparator_rejected(self):
    with self.assertRaises(ValueError):paired_growth({"CASH":[20000,20000]})
 def test_provenance_order_sensitive(self):
    self.assertNotEqual(provenance([1,2]),provenance([2,1]))
if __name__=="__main__":unittest.main()
