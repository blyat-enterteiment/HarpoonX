"""Registered synthetic OHLCV worlds and causal swing nominations.

Synthetic-only research. The strategy is never given a world, drift or latent
state. Native HARPOONX reservations, execution and account arithmetic live in
the Node bridge; this module creates inputs, not profitable trade labels.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Any

import numpy as np

from .technical_swing import BAR, TechnicalSwing

SYMBOLS = ("SYNA", "SYNB", "SYNM")
WORLDS = ("TREND", "WEAK", "FALSE", "NULL", "GAP")
ENTRIES = ("CONFIRMED", "QUALITY", "RETEST")
EXITS = ("NATIVE72", "PROTECT48", "RUNNER72", "FAST24")
RISKS = (0.000625, 0.00125, 0.0025)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def recipes() -> list[dict[str, Any]]:
    result = [
        {"id": f"{entry}_{exit_name}_R{int(round(risk * 1_000_000)):04d}",
         "entry": entry, "exit": exit_name, "risk": risk}
        for entry in ENTRIES for exit_name in EXITS for risk in RISKS
    ]
    result.extend([
        {"id": "CURRENT", "entry": "CONFIRMED", "exit": "NATIVE72", "risk": 0.0025},
        {"id": "SIMPLE", "entry": "SIMPLE", "exit": "NATIVE72", "risk": 0.0025},
        {"id": "CASH", "entry": "CASH", "exit": "NATIVE72", "risk": 0.0025},
    ])
    return result


def make_protocol() -> dict[str, Any]:
    """Fixed specification; call before generating any economic outputs."""
    return {
        "schema": "HARPOON_MODULATION9_PROTOCOL_1", "date": "2026-11-07",
        "source_head": "1ec647eb83062ed76c56f95ddd272c02bcfd0ece",
        "origin": "SYNTHETIC", "live_approved": False,
        "execution_allowed": False, "universe": list(SYMBOLS),
        "traded_universe": list(SYMBOLS[:2]), "benchmark": SYMBOLS[2],
        "limits": {"capitalUsd": 20000, "riskFraction": .0025,
                   "openRiskFraction": .0025, "grossFraction": .12,
                   "assetFraction": .12, "dailyLoss": .02, "maxDrawdown": .08},
        "risk_semantics": "12% gross/name and0.25% risk are admission/reservation caps; market appreciation, gaps and equity drift may create post-entry ratio excesses. Report these separately; no continuous rebalance is assumed.",
        "scenarios": {
            "NOMINAL": {"spread_bps": 2., "slippage_bps": 2.,
                        "commission_usd_per_share_per_side": .005,
                        "external_cost_usd_per_calendar_day": 1.},
            "STRESS": {"spread_bps": 4., "slippage_bps": 4.,
                       "commission_usd_per_share_per_side": .01,
                       "external_cost_usd_per_calendar_day": 2.},
        },
        "generator": {
            "worlds": list(WORLDS), "warmup_sessions": 50,
            "evaluation_sessions": 126, "buffer_sessions": 6,
            "first_date": "2024-01-08", "bars_per_session": 78,
            "calendar": "SYNTHETIC_WEEKDAYS_1430_2100_UTC_NO_HOLIDAYS_OR_DST",
            "bar_sigma": [.00075, .00085, .00050],
            "intrabar_substeps": 8,
            "overnight_sigma": [.0030, .0035, .0020],
            "trend_drift_per_bar": .000075, "weak_drift_per_bar": .000025,
            "false_first_hour_drift": .00013, "false_reversal_drift": -.00005,
            "gap_probability_per_session": .025, "gap_multiplier": .94,
            "correlation_loading": .45, "gap_correlation_loading": .85,
            "regime_refresh_probability": .08,
            "null_distribution": "conditionally compensated normal mixture; no trend or crash drift",
            "volume": "positive intraday U-shape, activity, contemporaneous absolute return and independent noise; never future prices",
            "volume_predicts_sign_in_null": False,
            "price_process_is_market_calibrated": False,
            "final_parameter_shift": {"sigma_multiplier_range": [.90, 1.20],
                                      "drift_multiplier_range": [.75, 1.10],
                                      "persistence_refresh_multiplier_range": [.80, 1.30]},
        },
        "entry_rules": {
            "CONFIRMED": "Exact TechnicalSwing: two closes above first30m range, relative return>0, same-slot RVOL20>1; decision60m+1s, next5m open.",
            "QUALITY": "CONFIRMED; RVOL<=3; close extension above range<=0.6*prior20d ATR; prior30d return>0 and prior daily MACD(12,26,9) histogram>0. EMA initialized on first of exactly50 previous daily closes. All daily values strictly prior session.",
            "RETEST": "At90m+1s: breakout during30-60m; last30m low revisits within0.15*prior20d ATR of range high without falling below range low; lasttwo closes above range; positive relative return; RVOL last10m in[0.8,3]; prior30d return>0. Next5m entry.",
        },
        "exit_rules": {
            "NATIVE72": "Exact native 25% at1.5R/25% at3R and causal trailing; max72h.",
            "PROTECT48": "Native targets; after completed close reaches1R, protect entry adjusted for exit friction and two commissions, retain75% of peak close profit, trailing distance1R. Pending-stop queue preserves received updates; max48h.",
            "RUNNER72": "25% integer shares at2R; remaining runner with2R trailing activated at2R; pending-stop queue preserves received updates; max72h.",
            "FAST24": "Native targets; after6 elapsedh with peak completed-close gain<0.5R and close<=entry, exit next open; max24h.",
        },
        "variants": recipes(),
        "stages": {
            "development": {"seeds": list(range(730101, 730109)), "all_variants": True},
            "final": {"seeds": list(range(940201, 940265)), "locked_candidates": 1,
                      "controls": ["CURRENT", "SIMPLE", "CASH"]},
        },
        "budget": {
            "authorization": "Current user explicitly requests iterations and multiple entry/exit/risk modulations.",
            "historical_reserved_plus_unincorporated": 151, "historical_cap": 128,
            "historical_debt_reconciled": False, "supplemental_candidates": 36,
            "development_policy_cost_world_seed_accounts": 3120,
            "final_policy_cost_world_seed_accounts": 2560,
            "supplemental_max_account_executions": 5680,
            "legacy_unit_new_policy_cost_accounts_including_controls": 78,
            "legacy_provisional_total_if_supplement_added": 229,
            "unit_note": "36 recipes+3 controls, times2costs =78. World/seed replication is also separately counted, not hidden.",
            "duplicate_control_recipe": "CONFIRMED_NATIVE72_R2500 exactly duplicates CURRENT; retained transparently, excluded from improvement selection.",
            "no_unregistered_parameter_edits_after_development": True,
        },
        "selection": {
            "only_stage": "development", "positive_edge_worlds": ["TREND", "WEAK"],
            "risk_filter": "max eventDD<=8%, worst session>=-2%, reconciled, maxholding<=72h",
            "score": "minimum across TREND/WEAK x nominal/stress of mean calendar-day log growth minus1.645 standard errors over independent seeds",
            "tie_break": "lower p95 drawdown, lower risk parameter, lexical id",
            "pareto": ["mean nominal log growth across TREND/WEAK", "p95 eventdrawdown across all stress worlds"],
            "pareto_scope": "risk-feasible candidates only",
            "final_if_no_positive_score": "Run one locked least-bad risk-feasible recipe diagnostically; negative development blocks promotion regardless of final.",
        },
        "statistics": {"unit": "independent full path; assets/costs/policies stay paired",
                       "bootstrap_replicates": 20000, "bootstrap_seed": 300710,
                       "one_sided_family_alpha": .05, "final_endpoints": 40,
                       "adjustment": "Bonferroni 5worlds*2costs*4 endpoints; paired cluster percentile bootstrap",
                       "daily_denominator": "inclusive calendar dates charged by native ledger",
                       "minimum_effect_daily_log": .0001,
                       "power_target": .8, "power_effect_daily_log": .0001},
        "gates": {
            "label": "N9S_1_INTERNAL_CONDITIONAL_ONLY", "industry_profitability_score": False,
            "nominal_edge_worlds_adjusted_lower": ">0.0001 daily net log",
            "stress_edge_worlds_adjusted_lower": ">0 daily net log",
            "paired_vs_current_simple_cash_edge_worlds_adjusted_lower": ">0",
            "development_score_positive": True,
            "final_paths_each_world": 64,
            "max_observed_event_drawdown": .08,
            "max_observed_session_loss": .02,
            "max_holding_elapsed_hours": 72,
            "tail_worlds_relative_to_same_cost_cash_mean_floor": -.005,
            "tail_floor_unit": "difference in mean terminal return fractions versus same-cost cash, separately by NULL/FALSE/GAP and cost",
            "null_positive_adjusted_lower_blocks": True,
            "null_positive_lower_scope": "absolute and relative to same-cost CASH; both already included in40 endpoints",
            "positive_aggregate_after_removing_best_campaign_each_path": True,
            "best_campaign_removal_scope": "TREND and WEAK separately in each cost case; descriptive fixed-account subtraction, not resimulation",
            "full_execution_fault_coverage_required_for_label": True,
            "no_real_profitability_accreditation": True,
            "economic_model_feasibility_reported_separately_from_missing_framework": True,
        },
        "limitations_locked_before_measurement": [
            "Synthetic equity-like symbols only; not observed AAPL/MSFT, not crypto/options.",
            "OHLCV next-bar IOC and native cash ledger; no empirically calibrated order queue, rejects, market impact or entry partial fills.",
            "Volume is tested in signals, not proof of executable market depth.",
            "No holiday/DST simulation; supplied calendar scheduling and weekend exits are testable.",
            "Native signal control, not the unintegrated virtual_net matrix coordinator.",
            "NATIVE72 and FAST24 preserve legacy pending-stop replacement semantics. PROTECT48/RUNNER72 also repair queued receipt handling, so changes do not isolate exit-parameter alpha from that repair.",
            "Independent seed holdout is conditional on this generator family, not market validation.",
            "NULL substep prices are exact martingales, but OHLC threshold-fill interpolation is an additional approximation; positive absolute or cash-relative lower bounds block inference.",
            "No automatic retraining, broker connection, deployment or trade authorization.",
        ],
    }


def _calendar(count: int, first: str) -> list[dict[str, Any]]:
    day = datetime.fromisoformat(first).replace(tzinfo=UTC)
    rows: list[dict[str, Any]] = []
    while len(rows) < count:
        if day.weekday() < 5:
            start = day.replace(hour=14, minute=30)
            rows.append({"date": day.date().isoformat(), "open": int(start.timestamp() * 1000),
                         "close": int((start + timedelta(hours=6, minutes=30)).timestamp() * 1000)})
        day += timedelta(days=1)
    return rows


def market(protocol: dict[str, Any], seed: int, world: str, stage: str) -> dict[str, Any]:
    """Generate prices from an explicit law; never adjust the law to a result."""
    if world not in WORLDS or stage not in ("development", "final", "fixture"):
        raise ValueError("WORLD_OR_STAGE")
    cfg = protocol["generator"]
    n = cfg["warmup_sessions"] + cfg["evaluation_sessions"] + cfg["buffer_sessions"]
    sessions = _calendar(n, cfg["first_date"])
    rng = np.random.default_rng(np.random.SeedSequence([seed, WORLDS.index(world), 90171]))
    shift = cfg["final_parameter_shift"]
    sigma_scale = float(rng.uniform(*shift["sigma_multiplier_range"])) if stage == "final" else 1.
    drift_scale = float(rng.uniform(*shift["drift_multiplier_range"])) if stage == "final" else 1.
    refresh_scale = float(rng.uniform(*shift["persistence_refresh_multiplier_range"])) if stage == "final" else 1.
    base_sigma = np.array(cfg["bar_sigma"]) * sigma_scale * (1.25 if world == "WEAK" else 1.)
    night_sigma = np.array(cfg["overnight_sigma"]) * sigma_scale
    loading = cfg["gap_correlation_loading"] if world == "GAP" else cfg["correlation_loading"]
    prices = np.array([100., 150., 120.])
    regime = rng.choice([-1., 0., 1.], size=3, p=[.4, .2, .4])
    series: list[list[dict[str, Any]]] = [[], [], []]
    log_activity = 0.
    for session in sessions:
        refresh = rng.random(3) < cfg["regime_refresh_probability"] * refresh_scale
        fresh = rng.choice([-1., 0., 1.], size=3, p=[.4, .2, .4])
        regime = np.where(refresh, fresh, regime)
        log_activity = float(.88 * log_activity + rng.normal(0, .15))
        activity = float(math.exp(max(-.7, min(.7, log_activity))))
        common = float(rng.normal())
        overnight = loading * common + math.sqrt(1 - loading**2) * rng.normal(size=3)
        ns = night_sigma * activity
        prices *= np.exp(ns * overnight - .5 * ns**2)
        # Symmetric positive multipliers have conditional expectation exactly1.
        # No uncompensated lognormal jump is permitted in the NULL world.
        tail_u = float(rng.random())
        if tail_u < .003:
            prices *= .97
        elif tail_u < .006:
            prices *= 1.03
        if world == "GAP" and rng.random() < cfg["gap_probability_per_session"]:
            prices *= cfg["gap_multiplier"]
        burst_sign = rng.choice([-1., 1.], size=3, p=[.4, .6])
        burst = rng.random(3) < .5
        substeps = cfg["intrabar_substeps"]
        common_z = rng.normal(size=(78, substeps, 1))
        z = loading * common_z + math.sqrt(1 - loading**2) * rng.normal(size=(78, substeps, 3))
        mixture = np.where(rng.random((78, 3)) < .004, 4., 1.)
        sigmas = base_sigma[None, :] * activity * mixture
        drifts = np.zeros((78, 3))
        if world in ("TREND", "WEAK", "GAP"):
            amplitude = cfg["weak_drift_per_bar"] if world == "WEAK" else cfg["trend_drift_per_bar"]
            drifts[:, :2] = amplitude * drift_scale * regime[:2]
            drifts[:, 2] = .00001 * drift_scale * regime[2]
        elif world == "FALSE":
            drifts[:12] = cfg["false_first_hour_drift"] * burst_sign * burst
            drifts[12:] = (cfg["false_reversal_drift"] * burst_sign * burst
                           * np.exp(-np.arange(66)[:, None] / 24.))
        logs = ((drifts[:, None, :] - .5 * sigmas[:, None, :]**2) / substeps
                + sigmas[:, None, :] / math.sqrt(substeps) * z)
        intrabar = prices[None, :] * np.exp(np.cumsum(logs.reshape(-1, 3), axis=0))
        intrabar = intrabar.reshape(78, substeps, 3)
        closes = intrabar[:, -1, :]
        opens = np.vstack((prices[None, :], closes[:-1]))
        # Extremes come from the same compensated price path. The replay still
        # uses conservative OHLC ordering, not hindsight over substep order.
        highs = np.maximum(opens, np.max(intrabar, axis=1))
        lows = np.minimum(opens, np.min(intrabar, axis=1))
        slots = np.arange(78)
        seasonal = 1. + .8 * np.exp(-slots / 12.) + .6 * np.exp(-(77 - slots) / 12.)
        volumes = (25000 * seasonal[:, None] * activity
                   * np.exp(.25 * np.abs(np.sum(z, axis=1) / math.sqrt(substeps))
                            + rng.normal(0, .30, (78, 3))))
        if world == "FALSE":
            volumes[6:18] *= (1. + 1.5 * burst)
        for j in range(3):
            series[j].extend({
                "t": session["open"] + k * BAR,
                "end": session["open"] + (k + 1) * BAR,
                "availableAt": session["open"] + (k + 1) * BAR + 1000,
                "o": float(opens[k, j]), "h": float(highs[k, j]),
                "l": float(lows[k, j]), "c": float(closes[k, j]),
                "v": float(volumes[k, j]),
            } for k in range(78))
        prices = closes[-1].copy()
    provenance_hash = digest({"generator": cfg, "seed": seed, "world": world, "stage": stage})
    return {"schema": "HARPOON-ULTIMATE-DATA-1", "kind": "ALPACA_PROXY",
            "origin": "SYNTHETIC", "sessions": sessions, "splitEvents": [], "cashDividends": [],
            "series": [{"symbol": s, "root": s, "tick": .01, "pointValue": 1,
                        "bars": series[j]} for j, s in enumerate(SYMBOLS)],
            "provenance": {"execution": "MODELED_OHLCV", "source": "HARPOON registered synthetic law; no market observations",
                           "feed": "SYNTHETIC", "files": [{"name": "generator_configuration", "sha256": provenance_hash}]}}


def _ema(x: list[float], span: int) -> list[float]:
    if not x:
        return []
    values = [x[0]]
    alpha = 2. / (span + 1)
    for value in x[1:]:
        values.append(alpha * value + (1 - alpha) * values[-1])
    return values


def nominations(dataset: dict[str, Any], protocol: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Price/volume prefixes only. No world identifier accepted by this API."""
    panel = TechnicalSwing(dataset, list(SYMBOLS[:2]), SYMBOLS[2])
    sessions = dataset["sessions"]
    cfg = protocol["generator"]
    start, stop = cfg["warmup_sessions"], cfg["warmup_sessions"] + cfg["evaluation_sessions"]
    daily: dict[str, list[dict[str, float]]] = {s: [] for s in SYMBOLS}
    for series in dataset["series"]:
        if len(series["bars"]) != len(sessions) * 78:
            raise ValueError("SYNTHETIC_DAILY_GRID_INCOMPLETE")
        for i in range(len(sessions)):
            bars = series["bars"][i * 78:(i + 1) * 78]
            if bars[0]["t"] != sessions[i]["open"] or bars[-1]["end"] != sessions[i]["close"]:
                raise ValueError("SYNTHETIC_DAILY_GRID_MISALIGNED")
            daily[series["symbol"]].append({"c": bars[-1]["c"], "h": max(b["h"] for b in bars),
                                            "l": min(b["l"] for b in bars), "o": bars[0]["o"],
                                            "available_at": max(b["availableAt"] for b in bars)})
    result: dict[str, list[dict[str, Any]]] = {name: [] for name in (*ENTRIES, "SIMPLE")}

    def add(entry: str, row: dict[str, Any], at: int, planned: int) -> None:
        result[entry].append({"id": f"{entry}:{row['symbol']}:{at}", "symbol": row["symbol"],
                              "hypothesis": "CLOSED_CHANNEL", "direction": 1, "index": 0,
                              "at": at, "plannedEntryAt": planned, "stopDistance": row["stop_distance"],
                              "regime": .4, "metadata": {"technicalRule": entry, "roadmapHorizonHours": 72}})

    for i in range(start, stop):
        session = sessions[i]
        at = session["open"] + 3_601_000
        decision = panel.decision(at)
        for name in ("CONFIRMED", "SIMPLE"):
            row = decision[name.lower()]
            if row is not None:
                add(name, row, at, decision["planned_entry_at"])
        features: dict[str, dict[str, float]] = {}
        for symbol in SYMBOLS[:2]:
            prior = daily[symbol][:i]  # excludes today's partially observed session
            if any(r["available_at"] > at for r in prior[-50:]):
                raise ValueError("DAILY_FEATURE_NOT_YET_AVAILABLE")
            closes = [r["c"] for r in prior[-50:]]
            fast, slow = _ema(closes, 12), _ema(closes, 26)
            macd = [a - b for a, b in zip(fast, slow, strict=True)]
            signal = _ema(macd, 9)
            tr = [max(prior[k]["h"] - prior[k]["l"], abs(prior[k]["h"] - prior[k-1]["c"]),
                      abs(prior[k]["l"] - prior[k-1]["c"])) for k in range(i - 20, i)]
            features[symbol] = {"atr": float(np.mean(tr)), "trend": math.log(closes[-1] / closes[-31]),
                                "histogram": macd[-1] - signal[-1]}
        candidates = [row for row in decision["ranked"] if row["confirmed"]
                      and row["rvol"] <= 3. and features[row["symbol"]]["trend"] > 0
                      and features[row["symbol"]]["histogram"] > 0
                      and row["price"] - row["level"] <= .6 * features[row["symbol"]]["atr"]]
        if candidates:
            add("QUALITY", candidates[0], at, decision["planned_entry_at"])
        retest: list[dict[str, Any]] = []
        retest_at = session["open"] + 5_401_000
        for symbol in SYMBOLS[:2]:
            stock = panel._window(symbol, session["open"], 0, 18, retest_at)
            bench = panel._window(SYMBOLS[2], session["open"], 0, 18, retest_at)
            level, floor = max(b["h"] for b in stock[:6]), min(b["l"] for b in stock[:6])
            price = stock[-1]["c"]
            base = median(sum(b["v"] for b in panel._window(symbol, s["open"], 16, 18, retest_at))
                          for s in sessions[i-20:i])
            rvol = sum(b["v"] for b in stock[-2:]) / base
            relative = math.log(price / stock[0]["o"]) - math.log(bench[-1]["c"] / bench[0]["o"])
            low = min(b["l"] for b in stock[12:])
            if (max(b["c"] for b in stock[6:12]) > level
                    and floor < low and abs(low - level) <= .15 * features[symbol]["atr"]
                    and min(b["c"] for b in stock[-2:]) > level
                    and relative > 0 and .8 <= rvol <= 3. and features[symbol]["trend"] > 0):
                retest.append({"symbol": symbol, "relative": relative, "stop_distance": price - floor})
        if retest:
            row = min(retest, key=lambda x: (-x["relative"], x["symbol"]))
            add("RETEST", row, retest_at, session["open"] + 19 * BAR)
    return result


def payload(protocol: dict[str, Any], seed: int, world: str, stage: str,
            variants: list[dict[str, Any]] | None = None, detailed: list[str] | None = None) -> dict[str, Any]:
    data = market(protocol, seed, world, stage)
    cfg = protocol["generator"]
    first, last = cfg["warmup_sessions"], cfg["warmup_sessions"] + cfg["evaluation_sessions"] - 1
    p = {**protocol, "periods": {"evaluation_start": data["sessions"][first]["date"],
                                 "evaluation_end": data["sessions"][last]["date"]}}
    return {"dataset": data, "protocol": p, "signals": nominations(data, protocol),
            "variants": variants if variants is not None else protocol["variants"],
            "scenario_names": ["NOMINAL", "STRESS"], "detailed": detailed or []}
