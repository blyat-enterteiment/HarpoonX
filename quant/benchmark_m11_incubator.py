#!/usr/bin/env python3
"""Repeatable *synthetic engineering* benchmark of C36, never a market trial."""

from __future__ import annotations

import hashlib
import json
import statistics
import time

from harpoon_quant.incubation_matrix import (
    Forecast,
    FundedBook,
    MarketFeatures,
    Opportunity,
    RoundTripCosts,
    evaluate_matrix,
)

EPOCH = 1_800_000_000_000
SCENARIO_IDS = tuple(f"s{i:03d}" for i in range(32))


def cohort() -> tuple[Opportunity, ...]:
    costs = RoundTripCosts(
        fee_entry_bps=25,
        fee_exit_bps=25,
        half_spread_entry_bps=3,
        half_spread_exit_bps=3,
        impact_entry_bps=2,
        impact_exit_bps=2,
        slippage_entry_bps=2,
        slippage_exit_bps=2,
    )
    features = MarketFeatures(
        relative_volume=2.0,
        volatility_momentum=0.2,
        momentum_bps=40,
        breakout_strength=1.5,
        reversal_strength=1.5,
        liquidity_usd=5_000_000,
        quote_age_ms=400,
    )
    rows = []
    for i in range(40):
        for j, family in enumerate(("breakout", "momentum", "reversal", "options_shadow")):
            book = "options" if family == "options_shadow" else (
                "crypto" if i % 2 == 0 else "equity"
            )
            fc = Forecast(
                expected_gross_bps=360 - 5 * j,
                standard_error_bps=5,
                n_effective=32,
                scenario_ids=SCENARIO_IDS,
                scenario_returns_bps=(450,) * 31 + (0,),
                known_at_ms=EPOCH - 500,
                provenance="SYNTHETIC_RESEARCH",
            )
            rows.append(
                Opportunity(
                    symbol=f"SYNTH_ASSET_{i:02d}",
                    native_strategy_id=f"synthetic_{family}",
                    book=book,
                    family=family,
                    factor_bucket=f"SYNTH_FACTOR_{i % 8}",
                    decision_at_ms=EPOCH,
                    quote_known_at_ms=EPOCH - 200,
                    horizon_hours=72,
                    native_prefilter_observed=True,  # synthetic fixture, NOT a native receipt
                    features=features,
                    costs=costs,
                    forecast=fc,
                    stop_loss_upper_bps=200,
                )
            )
    return tuple(rows)


def benchmark() -> dict[str, object]:
    rows = cohort()
    book = FundedBook(
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
    timings: list[float] = []
    outputs: set[str] = set()
    last = None
    for _ in range(20):
        start = time.perf_counter_ns()
        last = evaluate_matrix(rows, book)
        elapsed = (time.perf_counter_ns() - start) / 1_000_000
        timings.append(elapsed)
        outputs.add(hashlib.sha256(json.dumps(
            last, sort_keys=True, separators=(",", ":")
        ).encode()).hexdigest())
    assert last is not None
    assert len(outputs) == 1, "C36_NONDETERMINISTIC_RESEARCH_SOURCE"
    assert last["N9S"] == "NO_GO"
    assert last["paper_or_live_orders_allowed"] is False
    return {
        "schema": "HARPOON_FWN9_C36_SYNTHETIC_LOCAL_BENCHMARK_1",
        "assets": 40,
        "candidate_asset_strategy_pairs": len(rows),
        "common_scenarios": len(SCENARIO_IDS),
        "runs": len(timings),
        "mean_latency_ms": statistics.fmean(timings),
        "p50_latency_ms": statistics.median(timings),
        "p95_latency_ms": sorted(timings)[18],
        "result_sha256": next(iter(outputs)),
        "shortlisted_research_only": last["shortlisted_count"],
        "rejected_research_only": last["rejected_count"],
        "real_data_observed": False,
        "real_alpha_or_compound_verified": False,
        "paper_or_live_orders_authorized": False,
        "N9S": "NO_GO",
    }


if __name__ == "__main__":
    print(json.dumps(benchmark(), sort_keys=True))
