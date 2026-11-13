"""C41 financial N9 gate adversarial tests; never enable trading."""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import n9_go_gate as G


class FixedHurdleGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out=G.audit()

    def test_result_is_economic_no_go_after_real_market_bars(self):
        self.assertFalse(self.out["financialGO"])
        self.assertEqual(self.out["N9S"],"NO_GO")
        self.assertLess(self.out["champion_modelled_net_pnl_usd"],0)

    def test_frozen_positive_log_growth_hurdle_rejected(self):
        self.assertLess(self.out["champion_modelled_daily_log_bps"],1)
        self.assertGreater(self.out["required_terminal_for_1bp_per_calendar_day_usd"],
                           20000)
        self.assertIn("MODELED_NET_LOG_GROWTH_NOT_ABOVE_FROZEN_1BP_PER_DAY",
                      self.out["unmet_acceptance_conditions"])

    def test_stress_and_single_trade_concentration_rejected(self):
        self.assertLess(self.out["cost_paired_stress_usd"],0)
        self.assertLess(self.out["cost_resized_stress_usd"],0)
        self.assertIn("FEWER_THAN_FIVE_MODELED_TRADES_NO_POPULATION_EVIDENCE",
                      self.out["unmet_acceptance_conditions"])

    def test_rvol_avoids_some_modelled_loss_without_proving_positive_alpha(self):
        self.assertGreater(self.out["modelled_loss_avoided_vs_no_RVOL_usd"],0)
        self.assertFalse(self.out["financialGO"])

    def test_source_manifest_sha_exactly_anchored(self):
        raw=(G.HERE/"artifacts"/"C41_CHAMPION1_OBSERVED_BARS_MODELED_FILLS.json").read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),self.out["report_sha256"])

    def test_report_modified_to_claim_go_fails_closed(self):
        with tempfile.TemporaryDirectory() as t:
            dest=Path(t)/"study"
            shutil.copytree(G.HERE,dest,ignore=shutil.ignore_patterns("__pycache__"))
            p=dest/"artifacts"/"C41_CHAMPION1_OBSERVED_BARS_MODELED_FILLS.json"
            obj=json.loads(p.read_text())
            obj["financialGO"]=True
            p.write_text(json.dumps(obj))
            with self.assertRaisesRegex(ValueError,"REPORT_SHA"):
                G.audit(dest)

    def test_no_real_broker_or_original_or_authenticated_future(self):
        self.assertEqual(self.out["actual_broker_fill_count"],0)
        self.assertIsNone(self.out["original_six_C22_reference_usd"])
        self.assertFalse(self.out["independently_timed_external_registration"])
        self.assertFalse(self.out["genuine_prospective_observation"])

    def test_automatic_orders_and_recursive_optimizer_remain_disabled(self):
        self.assertFalse(self.out["can_accept_production_orders"])
        self.assertFalse(self.out["can_restart_recursive_optimizer"])
        self.assertEqual(self.out["M10_final_sealed"],3200)

    def test_revalidation_replays_same_source_and_frozen_policy(self):
        a=G.audit()
        self.assertEqual(a,self.out)
        self.assertEqual(a["frozen_candidate_before_target_data_api_commit"],
                         "a8eb6029f026131d375f791f9fc439a4c2a4c44f")


if __name__=="__main__":
    unittest.main()
