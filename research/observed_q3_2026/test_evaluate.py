"""C37 tests: observed market bars, modeled fills ONLY, no network or orders."""

from __future__ import annotations

import copy
import math
import shutil
import tempfile
import unittest
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import evaluate


class ObservedQ3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.market, cls.audit = evaluate.load_data()
        cls.report = evaluate.evaluate()

    def test_exact_five_assets_376_observed_bars(self) -> None:
        self.assertEqual(set(self.market), {
            "SPY", "QQQ", "NVDA", "BTC/USD", "ETH/USD"
        })
        self.assertEqual(self.audit["rows"], 376)
        self.assertEqual(
            sorted(len(v) for v in self.market.values()),
            [64, 64, 64, 92, 92],
        )

    def test_source_git_blobs_checked_and_not_exchange_signed(self) -> None:
        self.assertTrue(all(x["git_blob_sha1_verified"]
                            for x in self.audit["feeds"]))
        self.assertFalse(self.audit["independent_exchange_signature_verified"])
        self.assertFalse(self.audit["SIP_NBBO_available"])

    def test_crypto_calendar_has_all_92_days(self) -> None:
        for symbol in ("BTC/USD", "ETH/USD"):
            rows = self.market[symbol]
            self.assertEqual(rows[0].day, date(2026, 7, 1))
            self.assertEqual(rows[-1].day, date(2026, 9, 30))
            self.assertEqual(len(set(r.day for r in rows)), 92)

    def test_tamper_byte_refuses_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shutil.copytree(
                evaluate.ROOT / "research/observed_q3_2026",
                root / "research/observed_q3_2026",
            )
            path = root / "research/observed_q3_2026/raw/BTCUSD_us_1day.csv"
            data = path.read_bytes()
            path.write_bytes(data.replace(b"BTC", b"BTX", 1))
            with patch.object(evaluate, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "SOURCE_GIT_BLOB_CHANGED"):
                    evaluate.load_data(
                        root / "research/observed_q3_2026/source_manifest.json"
                    )

    def test_no_same_day_close_to_same_day_open_entry(self) -> None:
        rows = self.market["BTC/USD"]
        events = evaluate.proposals_for("BTC/USD", rows)
        self.assertGreater(len(events), 0)
        by_day = {r.day: i for i, r in enumerate(rows)}
        for event in events:
            i = by_day[event.decision_day]
            self.assertEqual(event.entry_at.date(), rows[i + 2].day)
            self.assertEqual(event.exit_at.date(), rows[i + 3].day)
            self.assertGreater(event.entry_at, evaluate.market_open(
                event.decision_day, "crypto"
            ))

    def test_every_modelled_holding_is_leq_72_wall_clock_hours(self) -> None:
        for symbol, rows in self.market.items():
            for event in evaluate.proposals_for(symbol, rows):
                elapsed = (event.exit_at - event.entry_at).total_seconds()
                self.assertGreater(elapsed, 0)
                self.assertLessEqual(elapsed, 72 * 3600)

    def test_no_retrospective_validation_outcome_in_training(self) -> None:
        rows = [e for symbol, bars in self.market.items()
                for e in evaluate.proposals_for(symbol, bars)]
        original = evaluate.calibrated(rows)
        altered = [replace(x, net_bps=x.net_bps + 1_000_000)
                   if x.decision_day >= date(2026, 9, 1) else x
                   for x in rows]
        self.assertEqual(original, evaluate.calibrated(altered))

    def test_end_of_august_trade_exiting_september_not_used_in_train(self) -> None:
        c = evaluate.Candidate(
            symbol="SPY", strategy="momentum5", factor="US_INDEX",
            book="equity", decision_day=date(2026, 8, 31),
            entry_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
            exit_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
            entry_open=100, exit_open=101, cost_bps=13,
            stop_stress_bps=300, raw_gross_bps=100, net_bps=87,
        )
        self.assertEqual(evaluate.calibrated([c]), {})

    def test_alpha_heuristic_has_no_familywise_population_proof(self) -> None:
        self.assertFalse(self.report["economic_conclusions"][
            "real_prospective_N9_alpha_proven"])
        self.assertFalse(self.report["economic_conclusions"][
            "calibration_split_pre_registered_before_2026_Q3"])

    def test_crypto_taker_fees_and_stress_not_substituted_with_maker(self) -> None:
        self.assertEqual(evaluate.assumption_cost("BTC/USD"), 100)
        self.assertEqual(evaluate.assumption_cost("ETH/USD", stress=True), 170)
        self.assertEqual(evaluate.assumption_cost("SPY"), 13)
        self.assertEqual(evaluate.assumption_cost("SPY", stress=True), 26)
        self.assertEqual(self.report["cost_assumptions_bps"][
            "crypto_real_published_taker_fee_each_side"], 25)

    def test_replay_is_deterministic_given_same_bar_bytes(self) -> None:
        one = self.report
        other = evaluate.evaluate()
        self.assertEqual(one, other)

    def test_all_modeled_positions_require_common_one_book(self) -> None:
        for model in self.report["modelled_wealth"].values():
            if "trades" not in model:
                continue
            self.assertEqual(model["wealth_initial_usd"], 20_000)
            self.assertEqual(model["actual_alpaca_fills"], 0)
            self.assertEqual(model["N9S"], "NO_GO")
            self.assertAlmostEqual(
                model["wealth_initial_usd"] + model["modeled_net_pnl_usd"],
                model["wealth_terminal_usd"], delta=0.0001,
            )
            self.assertTrue(all(0 < trade["hold_hours"] <= 72
                                for trade in model["trades"]))

    def test_no_trade_branch_is_exactly_cash(self) -> None:
        x = evaluate.simulate_one_book([], {})
        self.assertEqual(x["wealth_terminal_usd"], 20_000)
        self.assertEqual(x["closed_modeled_trades"], 0)
        self.assertEqual(x["modeled_net_pnl_usd"], 0)

    def test_degenerate_fee_only_price_flat_causes_negative_not_profit(self) -> None:
        t = datetime(2026, 9, 10, 9, tzinfo=timezone.utc)
        c = evaluate.Candidate(
            symbol="BTC/USD", strategy="momentum5", factor="CRYPTO_BETA",
            book="crypto", decision_day=date(2026, 9, 8),
            entry_at=t, exit_at=t + evaluate.timedelta(days=1),
            entry_open=100, exit_open=100,
            cost_bps=100, stop_stress_bps=200, raw_gross_bps=0,
            net_bps=-100,
        )
        x = evaluate.simulate_one_book([c], {})
        self.assertEqual(x["closed_modeled_trades"], 1)
        self.assertLess(x["modeled_net_pnl_usd"], 0)

    def test_unsupported_original_policy_never_substituted_with_naive(self) -> None:
        self.assertIn("naive_momentum_reference_NOT_ORIGINAL",
                      self.report["modelled_wealth"])
        self.assertFalse(self.report["economic_conclusions"][
            "original_C22_policy_comparison_available"])

    def test_no_live_prospective_evidence_is_claimed(self) -> None:
        self.assertEqual(self.report["economic_conclusions"][
            "actual_broker_entry_exit_orders_fills"], 0)
        self.assertFalse(self.report["economic_conclusions"][
            "broker_costs_actually_reconciled"])
        self.assertEqual(self.report["economic_conclusions"][
            "firm_level_growth_target_N9"], "NO_GO")

    def test_capital_never_resets_between_modelled_trades(self) -> None:
        model = self.report["modelled_wealth"][
            "naive_momentum_reference_NOT_ORIGINAL"
        ]
        for t in model["trades"]:
            self.assertLessEqual(t["position_usd"], 800.00001)
            self.assertLessEqual(t["risk_reservation_usd"], 50.000001)
            self.assertFalse(t["actual_broker_fill"])
        self.assertTrue(math.isfinite(model["wealth_terminal_usd"]))

    def test_stress_cost_never_lower_than_base(self) -> None:
        for symbol in self.market:
            self.assertGreaterEqual(
                evaluate.assumption_cost(symbol, stress=True),
                evaluate.assumption_cost(symbol),
            )

    def test_unknown_data_asset_cannot_become_a_study_strategy(self) -> None:
        with self.assertRaises(KeyError):
            evaluate.group_for("FANTOM_SYNTH")

    def test_source_no_concatenation_of_crypto_midpoint_and_stock_NBBO(self) -> None:
        self.assertFalse(self.audit["price_fill_reachability_verified"])
        self.assertFalse(self.audit["ipo_dividend_split_adjustment_complete"])


if __name__ == "__main__":
    unittest.main()
