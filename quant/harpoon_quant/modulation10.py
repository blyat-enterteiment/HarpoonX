"""Second, separately registered search: persistent intraday drift and receipt ablation.

The generator, costs, capital and acceptance hurdles are inherited unchanged.
Signals use observable prefixes only. Daily momentum scores are ranking features,
not independent-return t statistics and not probabilities of a profitable trade.
"""

from __future__ import annotations

import copy
import math
from statistics import fmean, stdev
from typing import Any

from .modulation9 import SYMBOLS, market
from .modulation9 import make_protocol as previous_protocol
from .modulation9 import nominations as previous_nominations

MOMENTUM_RULES = {
    f"MOM{window}_{tag}": {"window": window, "threshold": threshold}
    for window in (3, 8) for tag, threshold in (("Z0", 0.), ("Z075", .75))
}
CONTROL_IDS = ["CURRENT", "SIMPLE", "CASH", "M9_BEST", "QUALITY_NATIVE72_R0625"]
EVALUATION_CONTROL_IDS = ["CURRENT", "SIMPLE", "CASH", "M9_BEST"]


def recipes() -> list[dict[str, Any]]:
    values = [
        {"id": f"{entry}_{exit_name}_R{round(risk * 1_000_000):04d}",
         "entry": entry, "exit": exit_name, "risk": risk, "role": "candidate"}
        for entry in MOMENTUM_RULES
        for exit_name in ("HOLD24", "HOLD72") for risk in (.00125, .0025)
    ]
    values += [
        {"id": "CONFIRMED_NATIVE_QUEUE72_R2500", "entry": "CONFIRMED",
         "exit": "NATIVE_QUEUE72", "risk": .0025, "role": "candidate"},
        {"id": "QUALITY_NATIVE_QUEUE72_R0625", "entry": "QUALITY",
         "exit": "NATIVE_QUEUE72", "risk": .000625, "role": "candidate"},
        {"id": "CURRENT", "entry": "CONFIRMED", "exit": "NATIVE72", "risk": .0025, "role": "control"},
        {"id": "SIMPLE", "entry": "SIMPLE", "exit": "NATIVE72", "risk": .0025, "role": "control"},
        {"id": "CASH", "entry": "CASH", "exit": "NATIVE72", "risk": .0025, "role": "control"},
        {"id": "M9_BEST", "entry": "QUALITY", "exit": "RUNNER72", "risk": .000625, "role": "control"},
        {"id": "QUALITY_NATIVE72_R0625", "entry": "QUALITY", "exit": "NATIVE72", "risk": .000625, "role": "control"},
    ]
    return values


def make_protocol() -> dict[str, Any]:
    p = copy.deepcopy(previous_protocol())
    p.update({"schema": "HARPOON_MODULATION10_PROTOCOL_1", "round_id": "M10_R1",
              "source_head": "9cfa7418322bff6047b17be6e4b7df1936fe2329",
              "previous_economic_source": "d301fe53d1a57efe87b6fd91da5a599c6ba91d3d",
              "generator_law_changed": False, "costs_changed": False,
              "risk_caps_changed": False, "acceptance_hurdles_changed": False,
              "variants": recipes(), "control_ids": CONTROL_IDS,
              "evaluation_control_ids": EVALUATION_CONTROL_IDS,
              "momentum_rules": copy.deepcopy(MOMENTUM_RULES)})
    p["entry_schedules"] = {name: {"minutes": [60 if name != "RETEST" else 90],
                                         "lag_ms": 1000, "max_per_session": 1}
                            for name in ("CONFIRMED", "SIMPLE", "QUALITY", "RETEST")}
    for name, rule in MOMENTUM_RULES.items():
        p["entry_rules"][name] = (
            f"Use the last{rule['window']} COMPLETE prior sessions' log(close/open), excluding overnight. "
            f"Score=sample mean*sqrt(window)/sample SD, strictly above{rule['threshold']}; "
            "degenerate/nonfinite dispersion fails closed. Select highest score, lexical symbol tie. "
            "No market/world/regime labels. Initial stop distance=prior20-session mean true range. "
            "Decide at open+5minutes+1second; native IOC entry at open+10minutes. "
            "At most one nomination per rule per session. Score is a feature, not a significance test.")
        p["entry_schedules"][name] = {"minutes": [5], "lag_ms": 1000, "max_per_session": 1}
    p["exit_rules"].update({
        "NATIVE_QUEUE72": "Exact native targets, quantities, trailing function and72h; ONLY preserve pending received stop updates in a queue.",
        "HOLD24": "Initial protective stop and24h calendar deadline; no targets, partials or trailing.",
        "HOLD72": "Initial protective stop and72h calendar deadline; no targets, partials or trailing.",
    })
    p["ablations"] = [
        {"candidate": "CONFIRMED_NATIVE_QUEUE72_R2500", "control": "CURRENT", "changed_factor": "STOP_RECEIPT_QUEUE_ONLY"},
        {"candidate": "QUALITY_NATIVE_QUEUE72_R0625", "control": "QUALITY_NATIVE72_R0625", "changed_factor": "STOP_RECEIPT_QUEUE_ONLY"},
    ]
    p["stages"] = {
        "development": {"seeds": list(range(1206101, 1206109)), "all_variants": True},
        "final": {"seeds": list(range(1506201, 1506265)), "locked_candidates": 1,
                  "controls": EVALUATION_CONTROL_IDS, "open_only_if_development_eligible": True},
    }
    p["selection"] = {
        "only_stage": "development", "positive_edge_worlds": ["TREND", "WEAK"],
        "risk_filter": "max eventDD<=8%, worst session>=-2%, reconciled, signal-to-exit<=72h",
        "score": "minimum over TREND/WEAK and nominal/stress of mean daily log minus1.645SE minus scenario hurdle",
        "hurdles": {"NOMINAL": .0001, "STRESS": 0.},
        "score_is_confirmatory_interval": False,
        "tie_break": "lower p95 stress drawdown, lower risk, lexical id",
        "pareto": ["mean nominal daily log across TREND/WEAK", "p95 eventDD across all stress worlds"],
        "pareto_scope": "risk-feasible NEW candidates only",
        "final_if_no_positive_score": "DO NOT OPEN RESERVED FINAL. Preserve negative development; no promotion.",
    }
    p["statistics"].update({"bootstrap_replicates": 50000, "bootstrap_seed": 300711,
                            "one_sided_family_alpha": .025, "final_endpoints": 50,
                            "adjustment": "Bonferroni5worlds*2costs*5endpoints, paired trajectory bootstrap"})
    p["future_error_budget"] = {
        "scope": "Prospective validation program AFTER this checkpoint; no retroactive family confidence for historical trials.",
        "total_nominal_alpha": .05, "round_alpha": .025,
        "future_round_rule": "alpha_k=.05/2**k for prospective validation round k>=1; independent unviewed seeds",
        "prior_modulation9_family_alpha": .05, "historical_global_error_control_claimed": False,
        "no_repeated_final_until_success": True,
    }
    p["budget"] = {
        "historical_provisional_policy_cost_count": 151, "historical_ceiling": 128,
        "historical_debt_reconciled": False, "previous_supplement_policy_cost_count": 78,
        "previous_supplement_account_executions": 5680,
        "new_candidate_recipes": 18, "repeated_controls": 5,
        "supplemental_policy_cost_count": 46, "provisional_legacy_total_including_supplements": 275,
        "development_policy_cost_world_seed_accounts": 1840,
        "final_policy_cost_world_seed_accounts": 3200,
        "supplemental_max_account_executions": 5040,
        "user_authorized_continuation": True,
        "engineering_fixtures_are_not_statistical_market_trials": True,
    }
    p["gates"]["paired_vs_prior_best_edge_worlds_adjusted_lower"] = ">0 in addition to original controls"
    p["limitations_locked_before_measurement"] += [
        "Momentum's daily standardized score does not treat5minute bars or correlated days as independent inference units.",
        "A hard-continuous-exposure oracle bound is not a universal bound for the inherited admission-only cap or interpolated OHLC fills.",
        "Queue-only ablations isolate receipt for identical native entry/risk/target/trailing parameters; momentum comparisons do not.",
    ]
    return p


def daily_panel(dataset: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    sessions = dataset["sessions"]
    result: dict[str, list[dict[str, Any]]] = {}
    for series in dataset["series"]:
        if series["symbol"] not in SYMBOLS:
            continue
        bars = series["bars"]
        if len(bars) != len(sessions) * 78:
            raise ValueError("MOD10_COMPLETE_SESSION_GRID_REQUIRED")
        values = []
        for i, session in enumerate(sessions):
            part = bars[i * 78:(i + 1) * 78]
            if part[0]["t"] != session["open"] or part[-1]["end"] != session["close"]:
                raise ValueError("MOD10_ALIGNED_GRID_REQUIRED")
            values.append({"o": part[0]["o"], "c": part[-1]["c"],
                           "h": max(b["h"] for b in part), "l": min(b["l"] for b in part),
                           "available_at": max(b["availableAt"] for b in part), "date": session["date"]})
        result[series["symbol"]] = values
    if set(result) != set(SYMBOLS):
        raise ValueError("MOD10_UNIVERSE_REQUIRED")
    return result


def momentum_feature(prior: list[dict[str, Any]], window: int, at: int) -> dict[str, Any] | None:
    if len(prior) < max(21, window) or any(r["available_at"] > at for r in prior[-max(21, window):]):
        raise ValueError("MOD10_PRIOR_FEATURE_HISTORY_OR_AVAILABILITY")
    r = [math.log(row["c"] / row["o"]) for row in prior[-window:]]
    sd, mean = stdev(r), fmean(r)
    if not math.isfinite(sd) or sd <= 1e-12 or not math.isfinite(mean):
        return None
    tr = [max(prior[j]["h"] - prior[j]["l"],
              abs(prior[j]["h"] - prior[j - 1]["c"]),
              abs(prior[j]["l"] - prior[j - 1]["c"])) for j in range(len(prior) - 20, len(prior))]
    atr = fmean(tr)
    score = mean * math.sqrt(window) / sd
    if not math.isfinite(atr) or atr <= 0 or not math.isfinite(score):
        return None
    return {"score": score, "mean_intraday_log_return": mean, "sample_daily_sd": sd,
            "stop_distance": atr, "source_available_at": max(row["available_at"] for row in prior[-max(21, window):]),
            "last_complete_session": prior[-1]["date"]}


def nominations(dataset: dict[str, Any], protocol: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result = previous_nominations(dataset, protocol)
    for signals in result.values():
        for signal in signals:
            signal["sourceAvailableAt"] = signal["at"]
    result.update({name: [] for name in MOMENTUM_RULES})
    panel = daily_panel(dataset)
    start = protocol["generator"]["warmup_sessions"]
    stop = start + protocol["generator"]["evaluation_sessions"]
    for i in range(start, stop):
        session = dataset["sessions"][i]
        at, planned = session["open"] + 301000, session["open"] + 600000
        for name, rule in MOMENTUM_RULES.items():
            qualified = []
            for symbol in SYMBOLS[:2]:
                feature = momentum_feature(panel[symbol][:i], int(rule["window"]), at)
                if feature is not None and feature["score"] > rule["threshold"]:
                    qualified.append({"symbol": symbol, **feature})
            if not qualified:
                continue
            chosen = min(qualified, key=lambda x: (-x["score"], x["symbol"]))
            result[name].append({
                "id": f"{name}:{chosen['symbol']}:{at}", "symbol": chosen["symbol"],
                "hypothesis": "CLOSED_CHANNEL", "direction": 1, "index": 0, "at": at,
                "plannedEntryAt": planned, "sourceAvailableAt": chosen["source_available_at"],
                "stopDistance": chosen["stop_distance"], "regime": .4,
                "metadata": {"technicalRule": name, "roadmapHorizonHours": 72,
                             "momentumFeature": {"window": rule["window"], "threshold": rule["threshold"],
                                                 **{k: v for k, v in chosen.items() if k != "symbol"}}},
            })
    return result


def payload(protocol: dict[str, Any], seed: int, world: str, stage: str,
            variants: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    data = market(protocol, seed, world, stage)
    cfg = protocol["generator"]
    first, last = cfg["warmup_sessions"], cfg["warmup_sessions"] + cfg["evaluation_sessions"] - 1
    p = {**protocol, "periods": {"evaluation_start": data["sessions"][first]["date"],
                                 "evaluation_end": data["sessions"][last]["date"]}}
    return {"dataset": data, "protocol": p, "signals": nominations(data, protocol),
            "variants": variants if variants is not None else p["variants"],
            "scenario_names": ["NOMINAL", "STRESS"], "detailed": []}
