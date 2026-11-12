"""C36 incubator: synthetic engineering tests, NEVER observed performance."""

from __future__ import annotations

import math
import unittest
from dataclasses import replace

from harpoon_quant.incubation_matrix import (
    Forecast,
    FundedBook,
    MarketFeatures,
    Opportunity,
    ResearchPolicy,
    RoundTripCosts,
    compound_one_book,
    evaluate_matrix,
)

NOW = 1_800_000_000_000
SCENARIOS = tuple(f"path_{i:03d}" for i in range(8))


def costs(fee: float = 25) -> RoundTripCosts:
    return RoundTripCosts(
        fee_entry_bps=fee,
        fee_exit_bps=fee,
        half_spread_entry_bps=3,
        half_spread_exit_bps=3,
        impact_entry_bps=2,
        impact_exit_bps=2,
        slippage_entry_bps=2,
        slippage_exit_bps=2,
    )


def funded(**override: object) -> FundedBook:
    source = FundedBook(
        equity_usd=20_000,
        settled_cash_usd=20_000,
        committed_cash_usd=0,
        unsettled_cash_usd=0,
        outstanding_gross_usd=0,
        outstanding_risk_usd=0,
        reconciled=True,
        receipts_complete=True,
        risk_halt=False,
    )
    return replace(source, **override)


def candidate(
    symbol: str = "BTC/USD",
    strategy: str = "native-breakout",
    book: str = "crypto",
    factor: str = "crypto-beta",
    family: str = "breakout",
    gross: float = 360,
    fee: float = 25,
    losses: float = 200,
) -> Opportunity:
    features = MarketFeatures(
        relative_volume=2,
        volatility_momentum=0.2,
        momentum_bps=40,
        breakout_strength=1.5,
        reversal_strength=1.5,
        liquidity_usd=2_000_000,
        quote_age_ms=500,
    )
    forecast = Forecast(
        expected_gross_bps=gross,
        standard_error_bps=5,
        n_effective=8,
        scenario_ids=SCENARIOS,
        scenario_returns_bps=(450, 450, 450, 450, 450, 450, 450, 0),
        known_at_ms=NOW - 1_000,
        provenance="SYNTHETIC_RESEARCH",
    )
    return Opportunity(
        symbol=symbol,
        native_strategy_id=strategy,
        book=book,
        family=family,
        factor_bucket=factor,
        decision_at_ms=NOW,
        quote_known_at_ms=NOW - 100,
        horizon_hours=72,
        native_prefilter_observed=True,
        features=features,
        costs=costs(fee),
        forecast=forecast,
        stop_loss_upper_bps=losses,
    )


class MultilayerIncubatorTests(unittest.TestCase):
    def test_no_candidates_is_cash_only(self):
        result = evaluate_matrix((), funded())
        self.assertEqual(result["shortlisted_count"], 0)
        self.assertEqual(result["baseline"], "CASH")
        self.assertEqual(result["N9S"], "NO_GO")

    def test_eligible_synthetic_candidate_is_never_an_order(self):
        row = evaluate_matrix((candidate(),), funded())
        self.assertEqual(row["shortlisted_count"], 1)
        self.assertFalse(row["paper_or_live_orders_allowed"])
        self.assertTrue(row["scenario_data_not_empirically_authenticated"])
        self.assertEqual(row["comparison_with_original"], "UNOBSERVED")
        self.assertEqual(row["research_shortlist"][0]["selection"],
                         "OFFLINE_RESEARCH_SHORTLIST_NOT_ORDER")

    def test_original_natively_unobserved_candidate_fails_closed(self):
        c = replace(candidate(), native_prefilter_observed=False)
        row = evaluate_matrix((c,), funded())
        self.assertEqual(row["shortlisted_count"], 0)
        self.assertEqual(row["no_trade_diagnostics"][0]["reason"],
                         "NO_ORIGINAL_NATIVE_PREFILTER_WITNESS")

    def test_options_stays_shadow_even_with_positive_forecast(self):
        c = replace(candidate(book="options", family="options_shadow"),
                    native_strategy_id="options-call-raw")
        row = evaluate_matrix((c,), funded())
        self.assertEqual(row["shortlisted_count"], 0)
        self.assertEqual(row["no_trade_diagnostics"][0]["reason"],
                         "OPTIONS_EXECUTION_AND_ACCOUNTING_UNCERTIFIED")

    def test_stale_market_quote_rejected(self):
        c = candidate()
        c = replace(c, features=replace(c.features, quote_age_ms=60001))
        self.assertEqual(evaluate_matrix((c,), funded())[
            "no_trade_diagnostics"][0]["reason"], "STALE_SOURCE_QUOTE")

    def test_future_quote_time_rejected(self):
        c = replace(candidate(), quote_known_at_ms=NOW + 1)
        with self.assertRaisesRegex(ValueError, "FUTURE_INFORMATION"):
            evaluate_matrix((c,), funded())

    def test_future_forecast_time_rejected(self):
        c = candidate()
        c = replace(c, forecast=replace(c.forecast, known_at_ms=NOW + 1))
        with self.assertRaisesRegex(ValueError, "FUTURE_INFORMATION"):
            evaluate_matrix((c,), funded())

    def test_negative_fee_is_rejected_not_savings(self):
        c = candidate()
        c = replace(c, costs=replace(c.costs, fee_exit_bps=-25))
        with self.assertRaisesRegex(ValueError, "INVALID_OR_MISSING_COST"):
            evaluate_matrix((c,), funded())

    def test_fee_round_trip_is_counted_each_side_once(self):
        self.assertEqual(costs().total_bps(), 64)
        self.assertEqual(costs(15).total_bps(), 44)

    def test_maker_cost_hypothesis_is_not_a_fill_guarantee(self):
        taker = evaluate_matrix((candidate(fee=25),), funded())
        maker = evaluate_matrix((candidate(fee=15),), funded())
        a = taker["research_shortlist"][0]["analysis"]
        b = maker["research_shortlist"][0]["analysis"]
        self.assertAlmostEqual(
            b["net_forecast_lower_bps"] - a["net_forecast_lower_bps"], 20
        )
        self.assertEqual(maker["N9S"], "NO_GO")

    def test_cost_eats_small_alpha_in_no_trade_zone(self):
        c = candidate(gross=110)
        row = evaluate_matrix((c,), funded())
        self.assertEqual(row["shortlisted_count"], 0)
        self.assertEqual(row["no_trade_diagnostics"][0]["reason"],
                         "NO_TRADE_REGION_AFTER_COST_AND_HURDLE")

    def test_higher_uncertainty_rejects_unchanged_forecast(self):
        c = candidate()
        x = replace(c.forecast, standard_error_bps=150)
        row = evaluate_matrix((replace(c, forecast=x),), funded())
        self.assertEqual(row["shortlisted_count"], 0)
        self.assertEqual(row["no_trade_diagnostics"][0]["reason"],
                         "NO_POSITIVE_PESSIMISTIC_NET_EDGE")

    def test_one_native_strategy_per_asset_competes_for_capital(self):
        a = candidate(strategy="plugin-a")
        b = candidate(strategy="plugin-b", gross=120)
        row = evaluate_matrix((a, b), funded())
        self.assertEqual(row["shortlisted_count"], 1)
        self.assertEqual(row["research_shortlist"][0]["strategy"], "plugin-a")
        self.assertEqual(len(row["no_trade_diagnostics"]), 1)

    def test_correlated_asset_bucket_suppresses_second_entry(self):
        a = candidate()
        b = candidate(symbol="ETH/USD", strategy="eth-breakout")
        row = evaluate_matrix((a, b), funded())
        self.assertEqual(row["shortlisted_count"], 1)
        self.assertEqual(row["no_trade_diagnostics"][0]["reason"],
                         "FACTOR_CLUSTER_EXPOSURE_DUPLICATED")

    def test_shared_admission_cap_is_never_two_times_twelve_percent(self):
        a = candidate(symbol="BTC/USD", factor="bitcoin")
        b = candidate(symbol="SPY", strategy="equity-momentum",
                      family="momentum", book="equity", factor="equity")
        row = evaluate_matrix((a, b), funded())
        total = sum(x["research_notional_usd"] for x in
                    row["research_shortlist"])
        self.assertLessEqual(total, 2400 + 1e-9)
        self.assertEqual(row["shortlisted_count"], 2)

    def test_very_large_loss_assumption_shrinks_funded_capacity(self):
        c = candidate(losses=6000)
        row = evaluate_matrix((c,), funded())
        self.assertEqual(row["shortlisted_count"], 0)
        self.assertNotEqual(row["no_trade_diagnostics"][0]["reason"],
                            "NO_FUNDED_ADMISSION_CAPACITY")

    def test_no_settled_cash_blocks_selection(self):
        row = evaluate_matrix((candidate(),), funded(settled_cash_usd=0))
        self.assertEqual(row["shortlisted_count"], 0)
        self.assertEqual(row["no_trade_diagnostics"][0]["reason"],
                         "NO_FUNDED_ADMISSION_CAPACITY")

    def test_pending_cash_reservations_reduce_real_capacity(self):
        row = evaluate_matrix((candidate(),), funded(committed_cash_usd=20_000))
        self.assertEqual(row["shortlisted_count"], 0)

    def test_risk_halt_is_absolute(self):
        row = evaluate_matrix((candidate(),), funded(risk_halt=True))
        self.assertEqual(row["shortlisted_count"], 0)
        self.assertEqual(row["no_trade_diagnostics"][0]["reason"],
                         "FUNDED_BOOK_NOT_RECONCILED")

    def test_no_source_reconciliation_is_absolute(self):
        row = evaluate_matrix((candidate(),), funded(receipts_complete=False))
        self.assertEqual(row["shortlisted_count"], 0)

    def test_original_held_symbol_not_reopened_to_collect_more_fees(self):
        row = evaluate_matrix((candidate(),),
                              funded(held_symbols=("BTC/USD",)))
        self.assertEqual(row["shortlisted_count"], 0)
        self.assertEqual(row["no_trade_diagnostics"][0]["reason"],
                         "ALREADY_HELD_DO_NOT_CHURN")

    def test_joint_scenario_alignment_must_be_identical(self):
        a = candidate()
        b = candidate(symbol="SPY", strategy="native-spy",
                      factor="equity", family="momentum", book="equity")
        ids = tuple(reversed(b.forecast.scenario_ids))
        b = replace(b, forecast=replace(b.forecast, scenario_ids=ids))
        with self.assertRaisesRegex(ValueError, "SCENARIO_ALIGNMENT"):
            evaluate_matrix((a, b), funded())

    def test_duplicate_asset_strategy_blocks_cohort(self):
        c = candidate()
        with self.assertRaisesRegex(ValueError, "DUPLICATE_ASSET_STRATEGY"):
            evaluate_matrix((c, c), funded())

    def test_more_than_72h_rejected(self):
        with self.assertRaisesRegex(ValueError, "INVALID_ASSET_STRATEGY"):
            evaluate_matrix((replace(candidate(), horizon_hours=73),), funded())

    def test_nonpositive_stop_risk_is_not_accepted(self):
        with self.assertRaisesRegex(ValueError, "INVALID_LOSS_OR_FEATURE"):
            evaluate_matrix((replace(candidate(), stop_loss_upper_bps=0),),
                            funded())

    def test_bankruptcy_scenario_blocks_log_score(self):
        c = candidate()
        x = replace(c.forecast, scenario_returns_bps=(-300_000,) * 8)
        with self.assertRaisesRegex(ValueError, "SCENARIO_RUIN"):
            evaluate_matrix((replace(c, forecast=x),), funded())

    def test_wealth_growth_keeps_one_continuous_financed_book(self):
        result = compound_one_book(20_000, (100, -30, 50))
        self.assertEqual(result, (20_000, 20_100, 20_070, 20_120))
        self.assertAlmostEqual(math.prod(
            result[i + 1] / result[i] for i in range(len(result) - 1)
        ), result[-1] / result[0])

    def test_compounded_profit_never_relaxes_original_20000_cap(self):
        x = evaluate_matrix((candidate(),),
                            funded(equity_usd=25_000, settled_cash_usd=25_000))
        self.assertEqual(x["original_hard_capital_base_usd"], 20_000)
        self.assertLessEqual(x["research_shortlist"][0]["research_notional_usd"],
                             2_400)

    def test_negative_ending_equity_is_not_compound_return(self):
        with self.assertRaisesRegex(ValueError, "COMPOUND_INVALID"):
            compound_one_book(20_000, (-20_001,))

    def test_cannot_relax_frozen_funding_or_risk_caps(self):
        for p in (
            replace(ResearchPolicy(), max_admission_gross_fraction=0.15),
            replace(ResearchPolicy(), max_admission_risk_fraction=0.01),
            replace(ResearchPolicy(), hard_capital_usd=25_000),
            replace(ResearchPolicy(), max_horizon_hours=144),
            replace(ResearchPolicy(), hurdle_bps_per_day=0),
        ):
            with self.subTest(p=p), self.assertRaisesRegex(
                    ValueError, "FROZEN_FINANCIAL_CONTRACT"):
                evaluate_matrix((candidate(),), funded(), p)

    def test_rejection_produces_no_broker_quantity_or_market_order(self):
        c = candidate(gross=0)
        row = evaluate_matrix((c,), funded())
        self.assertEqual(row["shortlisted_count"], 0)
        self.assertEqual(row["paper_or_live_orders_allowed"], False)
        self.assertEqual(row["N9S"], "NO_GO")

    def test_loss_cvar_stress_floor_is_not_claimed_as_population_bound(self):
        row = evaluate_matrix((candidate(),), funded())
        analysis = row["research_shortlist"][0]["analysis"]
        self.assertGreaterEqual(analysis["tail_penalty_basis"],
                                analysis["scenario_loss_cvar95"])
        self.assertGreaterEqual(analysis["tail_penalty_basis"],
                                analysis["modeled_stop_stress_fraction"])
        self.assertTrue(row["shortlist_requires_independent_prospective_validation"])


    def test_no_mixed_decision_clocks_in_joint_matrix(self):
        a = candidate()
        b = candidate(symbol="ETH/USD", strategy="native-eth", factor="eth",
                      )
        b = replace(b, decision_at_ms=NOW + 10)
        with self.assertRaisesRegex(ValueError, "NONATOMIC_PORTFOLIO"):
            evaluate_matrix((a, b), funded())

    def test_no_mixed_forecast_horizons_in_joint_scenario_distribution(self):
        a = candidate()
        b = replace(candidate(symbol="ETH/USD", strategy="eth", factor="eth"),
                    horizon_hours=24)
        with self.assertRaisesRegex(ValueError, "NONATOMIC_PORTFOLIO"):
            evaluate_matrix((a, b), funded())

    def test_caller_cannot_claim_zero_quote_age_with_stale_receipt(self):
        c = replace(candidate(), quote_known_at_ms=NOW - 100_000)
        with self.assertRaisesRegex(ValueError, "FUTURE_INFORMATION_OR_CLOCK"):
            evaluate_matrix((c,), funded())

    def test_policy_and_cohort_sha256_are_stable_and_content_addressed(self):
        x = evaluate_matrix((candidate(),), funded())
        y = evaluate_matrix((candidate(),), funded())
        self.assertEqual(x["research_policy_sha256"], y["research_policy_sha256"])
        self.assertEqual(x["research_input_cohort_sha256"],
                         y["research_input_cohort_sha256"])
        z = evaluate_matrix((candidate(gross=361),), funded())
        self.assertNotEqual(x["research_input_cohort_sha256"],
                            z["research_input_cohort_sha256"])
        self.assertEqual(len(x["research_policy_sha256"]), 64)
        self.assertFalse(x["portfolio_financial_go"])

    def test_three_assets_can_share_capital_without_three_12pct_trades(self):
        rows = tuple(
            candidate(symbol=f"ASSET_{i}", strategy="native-breakout",
                      factor=f"FACTOR_{i}") for i in range(3)
        )
        result = evaluate_matrix(rows, funded())
        self.assertEqual(result["shortlisted_count"], 3)
        self.assertAlmostEqual(sum(
            x["research_notional_usd"] for x in result["research_shortlist"]
        ), 2_400.0)
        self.assertLessEqual(sum(
            x["research_loss_budget_usd"] for x in result["research_shortlist"]
        ), 50.0)
        self.assertGreater(result["joint_aligned_scenario_log_score"], 0)
        self.assertEqual(result["N9S"], "NO_GO")

    def test_factor_bucket_research_limit_can_be_relaxed_only_without_trade_authority(self):
        rows = (
            candidate(symbol="BTC/USD", strategy="btc"),
            candidate(symbol="ETH/USD", strategy="eth"),
        )
        result = evaluate_matrix(rows, funded(), replace(
            ResearchPolicy(), max_per_factor_bucket=2,
        ))
        self.assertEqual(result["shortlisted_count"], 2)
        self.assertEqual(result["N9S"], "NO_GO")
        self.assertFalse(result["paper_or_live_orders_allowed"])

    def test_nonfinite_joint_return_does_not_result_in_profitable_signal(self):
        c = candidate()
        future = replace(c.forecast, scenario_returns_bps=(
            math.inf, 450, 450, 450, 450, 450, 450, 0
        ))
        with self.assertRaisesRegex(ValueError, "MISSING_OR_MISALIGNED_SCENARIOS"):
            evaluate_matrix((replace(c, forecast=future),), funded())


if __name__ == "__main__":
    unittest.main()
