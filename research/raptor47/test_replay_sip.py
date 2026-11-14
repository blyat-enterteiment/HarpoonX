"""C47 fixed 3%/4% SIP-vs-IEX Raptor 5Min posthoc replication checks."""
from __future__ import annotations

import copy
import json
import math
import shutil
import tempfile
import unittest
from pathlib import Path

import replay_sip as S


class SIPReplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data,cls.source=S.load()
        cls.out=S.report()

    def test_original_consolidated_SIP_2540_sha_16_tickers(self):
        self.assertEqual(self.source["raw_returned_5min_bars"],2540)
        self.assertEqual(len(self.data),16)
        self.assertTrue(len(self.source["raw_source_sha256"])==64)
        self.assertEqual(self.out["source_feed"],"SIP")

    def test_excludes_premarket_and_afterhours(self):
        for bars in self.data.values():
            for b in bars:
                t=b.at.astimezone(S.NY).time()
                self.assertGreaterEqual((t.hour,t.minute),(9,30))
                self.assertLess((t.hour,t.minute),(16,0))

    def test_source_preflight_and_posthoc_flags_preserved(self):
        self.assertTrue(self.source[
            "four_symbol_SIP_coverage_preflight_was_observed"])
        self.assertTrue(self.source["posthoc_16_symbol_selection"])
        self.assertFalse(self.source["screener_RVOL_over5_historically_confirmed"])
        self.assertTrue(self.out[
            "post_selection_bias_disqualifies_prospective_inference"])

    def test_same_fixed_thresholds_nothing_retuned(self):
        self.assertEqual(set(self.out["scenarios"]),{"3","4"})
        self.assertEqual(self.out["frozen_pre_full_download_commit"],
                         "f37f5a1266e2026d3ecb5b17818bfacc8a7223ff")
        self.assertEqual(self.out["original_unmodified_state_machine"],
                         "research/raptor46/local_fishing_net.py")

    def test_all_model_entries_are_strictly_following_close_confirmations(self):
        for p in ("3","4"):
            for c in self.out["scenarios"][p][
                "strict_shadow_candidate_detail"]:
                self.assertTrue(c["entry_at"].startswith("2026-11-13"))
                self.assertFalse(c["broker_actual_fill"])
                self.assertGreater(float(c["entry_open_price"]),0)

    def test_actual_no_N9_proof_when_modeled_profits_positive(self):
        self.assertEqual(self.out["N9S"],"NO_GO")
        self.assertEqual(self.out["N10"],"NO_GO")
        self.assertFalse(self.out["FWER_0_025_alpha_proved"])
        self.assertEqual(self.out["orders_PAPER"],0)
        self.assertEqual(self.out["orders_LIVE"],0)

    def test_cash_and_book_budget_not_inflated_by_sip_feed(self):
        for p in ("3","4"):
            for risk in self.out["scenarios"][p][
                "cost_100_300_500_bps_onebook_sensitivity"].values():
                self.assertEqual(risk["modeled_initial_financed_equity"],20000)
                self.assertFalse(risk["account_true_profit_reconciled"])
                self.assertEqual(risk["broker_fills"],0)
                self.assertEqual(risk["N9S"],"NO_GO")

    def test_cost_sensitivity_monotonic_on_same_entries(self):
        for p in ("3","4"):
            variants=self.out["scenarios"][p][
                "cost_100_300_500_bps_onebook_sensitivity"]
            values=[variants[f"{v:.1f}"][
                "hypothetical_one_day_net_pnl_usd"]
                for v in (100.,300.,500.)]
            self.assertGreaterEqual(values[0],values[1])
            self.assertGreaterEqual(values[1],values[2])

    def test_known_source_bytes_are_exact_with_manifest_git_blob(self):
        root=S.HERE
        b=(root/S.INPUT.name).read_bytes()
        manifest=json.loads((root/"source_manifest.json").read_text())
        self.assertEqual(S.A.git_sha1(b),manifest["Git_blob_sha1"])

    def test_tamper_rejected_on_future_prices(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for file in ("SIP_FIVE_MIN_2026_11_12_13_16_VISIBLE.csv",
                         "source_manifest.json",
                         "FROZEN_BEFORE_FULL_SIP_DATA.json"):
                shutil.copy2(S.HERE/file,root/file)
            csv=root/S.INPUT.name
            data=csv.read_bytes()
            csv.write_bytes(data[:-2]+b"7"+data[-1:])
            with self.assertRaisesRegex(ValueError,"SIP_FILE_HASH"):
                S.load(root)

    def test_replay_exact_determinism_and_no_original_claim(self):
        self.assertEqual(self.out,S.report())
        self.assertTrue(self.out[
            "model_trade_fills_are_not_authenticated"])
        self.assertFalse(self.out[
            "original_C22_vs_CASH_prospective_comparison_done"])

    def test_only_one_day_of_post_entry_obs_not_72hours(self):
        self.assertTrue(self.out[
            "no_72_hour_swing_results_from_1_day_bars"])
        self.assertEqual(self.out["sealed_M10_accounts"],3200)


if __name__=="__main__":
    unittest.main()
