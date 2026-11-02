"""Fixed, causal opening-shock model. Pure offline functions; no data access or orders.

The recovery score is an unvalidated economic hypothesis, not an expected return.
Native CLOSED_CHANNEL is only an execution template: exits remain BASELINE.
Registration, source authenticity, cash accounting and replay are caller duties.
"""
from __future__ import annotations

import hashlib
import json
import math
from bisect import bisect_left
from collections import Counter
from datetime import date
from statistics import fmean, stdev

BAR_MS = 300_000
STOCKS = ("AAPL", "MSFT")
BENCHMARK = "XLK"
POLICIES = ("RESIDUAL_LONG", "STOCK_THRESHOLD_OFF", "SECTOR_TIMING_CONTROL")
FIXED_RECIPE = {
    "entry_minutes": 60, "entry_delay_ms": 1000, "z_entry": -1.5,
    "max_absolute_z": 8, "recovery_fraction": .5, "net_hurdle_bps": 5,
    "atr_sessions": 14, "beta_min": 0, "beta_max": 2,
    "minimum_training_sessions": 100, "required_training_sessions": 126,
}
SIGMA_FLOOR = 1e-6


def _need(ok, message):
    if not ok:
        raise ValueError(message)


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def _periods(protocol):
    p = protocol["periods"]
    def pick(short, long):
        a, b = p.get(short), p.get(long)
        _need(a is None or b is None or a == b, "CONFLICTING_PERIOD_ALIASES")
        value = a if a is not None else b
        _need(isinstance(value, str), "MISSING_PERIOD:" + short)
        date.fromisoformat(value)
        return value
    train_start, train_end = pick("train_start", "training_start"), pick("train_end", "training_end")
    start, end = pick("evaluation_start", "evaluation_start"), pick("evaluation_end", "evaluation_end")
    _need(train_start <= train_end < start <= end, "NONCAUSAL_PERIODS")
    return train_start, train_end, start, end


def _recipe(protocol):
    r = protocol["recipe"]
    _need(all(r.get(k) == v for k, v in FIXED_RECIPE.items()), "FROZEN_RECIPE_MISMATCH")
    _need(r.get("sigma_floor", SIGMA_FLOOR) == SIGMA_FLOOR, "SIGMA_FLOOR_MISMATCH")
    _periods(protocol)
    return r


class _Panel:
    """Index bar timestamps only; compute prices strictly from admitted prefixes."""
    def __init__(self, data):
        _need(data.get("schema") == "HARPOON-ULTIMATE-DATA-1" and data.get("kind") == "ALPACA_PROXY",
              "DATASET_SCHEMA_KIND")
        self.data = data
        self.sessions = data["sessions"]
        last_close = -1
        dates = set()
        for s in self.sessions:
            date.fromisoformat(s["date"])
            _need(s["date"] not in dates and isinstance(s["open"], int) and isinstance(s["close"], int)
                  and s["open"] >= last_close and s["open"] < s["close"]
                  and (s["close"] - s["open"]) % BAR_MS == 0, "SESSION_CONTRACT")
            dates.add(s["date"])
            last_close = s["close"]
        self.series = {}
        self.times = {}
        for series in data["series"]:
            symbol = series["symbol"]
            _need(symbol not in self.series, "DUPLICATE_SERIES")
            if symbol not in (*STOCKS, BENCHMARK):
                continue
            _need(series.get("root") == symbol and series.get("pointValue") == 1
                  and _finite(series.get("tick")) and series["tick"] > 0, "SERIES_CONTRACT")
            times = [b["t"] for b in series["bars"]]
            _need(all(isinstance(t, int) for t in times) and
                  all(a < b for a, b in zip(times, times[1:])), "BAR_ORDER_DUPLICATES")
            self.series[symbol], self.times[symbol] = series, times
        _need(all(s in self.series for s in (*STOCKS, BENCHMARK)), "UNIVERSE_REQUIRED")
        self.splits = data.get("splitEvents")
        _need(isinstance(self.splits, list), "SPLIT_MANIFEST_REQUIRED")
        split_keys = set()
        session_opens = {s["open"] for s in self.sessions}
        for e in self.splits:
            _need(e.get("symbol") in self.series and isinstance(e.get("at"), int)
                  and _finite(e.get("ratio")) and e["ratio"] > 0, "SPLIT_EVENT_CONTRACT")
            _need(e["at"] in session_opens, "SPLIT_EFFECTIVE_AT_SESSION_OPEN_REQUIRED")
            key = (e["symbol"], e["at"])
            _need(key not in split_keys, "DUPLICATE_SPLIT_EFFECTIVE_EVENT")
            split_keys.add(key)

    def bars(self, symbol, start, end):
        times = self.times[symbol]
        return self.series[symbol]["bars"][bisect_left(times, start):bisect_left(times, end)]

    def split_error(self, symbol, at, since=None):
        for e in self.splits:
            if e["symbol"] != symbol or e["at"] > at or (since is not None and e["at"] <= since):
                continue
            # Absence is not an announcement-time assertion. The caller must
            # admit an explicit effective-time knowledge convention beforehand.
            known = e.get("knownAt")
            if known is None:
                return "SPLIT_KNOWLEDGE_AMBIGUOUS"
            if not isinstance(known, int) or known > at:
                return "SPLIT_NOT_KNOWN_AT_DECISION"
        return None

    def observed(self, symbol, start, end, at):
        bars = self.bars(symbol, start, end)
        expected = (end - start) // BAR_MS
        if len(bars) != expected:
            return None, "MISSING_BAR"
        for i, b in enumerate(bars):
            if b["t"] != start + i * BAR_MS or b.get("end") != b["t"] + BAR_MS:
                return None, "NONCONTIGUOUS_BAR"
            if not isinstance(b.get("availableAt"), int) or b["availableAt"] < b["end"]:
                return None, "BAR_AVAILABILITY_INVALID"
            if b["availableAt"] > at:
                return None, "BAR_NOT_AVAILABLE"
            if not all(_finite(b.get(k)) for k in ("o", "h", "l", "c", "v")) or not (
                0 < b["l"] <= min(b["o"], b["c"]) <= max(b["o"], b["c"]) <= b["h"] and b["v"] >= 0
            ):
                return None, "OHLCV_INVALID"
        return bars, None

    def shock(self, symbol, session, recipe):
        end = session["open"] + recipe["entry_minutes"] * 60_000
        at = end + recipe["entry_delay_ms"]
        if end >= session["close"]:
            return None, "SESSION_TOO_SHORT"
        split_error = self.split_error(symbol, at, session["open"] - 1)
        if split_error:
            return None, split_error
        if any(e["symbol"] == symbol and session["open"] < e["at"] <= end for e in self.splits):
            return None, "INTRADAY_SPLIT_UNMODELED"
        bars, reason = self.observed(symbol, session["open"], end, at)
        if reason:
            return None, reason
        return {"return": math.log(bars[-1]["c"] / bars[0]["o"]),
                "price": bars[-1]["c"], "known_at": max(b["availableAt"] for b in bars)}, None

    def atr(self, symbol, session, at, periods):
        prior = [s for s in self.sessions if s["close"] <= session["open"]]
        daily = []
        for s in reversed(prior):
            bars, reason = self.observed(symbol, s["open"], s["close"], at)
            if reason:
                continue  # Explicit completed-session history, not filled gaps.
            error = self.split_error(symbol, at, s["open"] - 1)
            if error:
                return None, error
            if any(e["symbol"] == symbol and s["open"] < e["at"] < s["close"] for e in self.splits):
                return None, "INTRADAY_SPLIT_UNMODELED"
            ratio = math.prod(e["ratio"] for e in self.splits
                              if e["symbol"] == symbol and s["close"] <= e["at"] <= at)
            daily.append({"date": s["date"], "h": max(b["h"] for b in bars) / ratio,
                          "l": min(b["l"] for b in bars) / ratio, "c": bars[-1]["c"] / ratio})
            if len(daily) == periods + 1:
                break
        if len(daily) != periods + 1:
            return None, "ATR_HISTORY_INSUFFICIENT"
        daily.reverse()
        ranges = [max(b["h"] - b["l"], abs(b["h"] - a["c"]), abs(b["l"] - a["c"]))
                  for a, b in zip(daily, daily[1:])]
        return {"value": max(2 * self.series[symbol]["tick"], fmean(ranges)),
                "history_dates": [b["date"] for b in daily]}, None


def _provenance(protocol):
    return {"protocol_sha256": _sha(protocol), "origin": "HISTORICAL",
            "execution": "MODELED_OHLCV", "economic_hypothesis": "INTRADAY_SECTOR_RESIDUAL_RECOVERY",
            "execution_template": "CLOSED_CHANNEL:BASELINE", "maximum_holding_calendar_hours": 72,
            "beta_scale": "OPEN_TO_OPEN_PLUS_60_MINUTES_OLS_WITH_INTERCEPT",
            "recovery_score_is_expected_return": False, "financial_acceptance_allowed": False,
            "registration_and_authenticity_checked_by_this_module": False,
            "split_knowledge": "CANONICAL_SESSION_OPEN_EFFECTIVE_AT; EXPLICIT_KNOWN_AT_REQUIRED_WHEN_FEATURE_ADJUSTMENT_USES_SPLIT",
            "source_original_received_at_verified": False}


def fit_models(data, protocol):
    """Fit two frozen OLS recipes on TRAIN only; no evaluation labels are read."""
    r = _recipe(protocol)
    start, end, _, _ = _periods(protocol)
    panel = _Panel(data)
    sessions = [s for s in panel.sessions if start <= s["date"] <= end]
    _need(len(sessions) == r["required_training_sessions"], "TRAIN_CALENDAR_REQUIRES_126_SESSIONS")
    rows, decisions = {s: [] for s in STOCKS}, []
    for session in sessions:
        benchmark, benchmark_reason = panel.shock(BENCHMARK, session, r)
        for symbol in STOCKS:
            stock, reason = panel.shock(symbol, session, r)
            reason = ("BENCHMARK_" + benchmark_reason) if benchmark_reason else reason
            if reason:
                decisions.append({"date": session["date"], "symbol": symbol, "status": "REFUSED", "reason": reason})
                continue
            row = {"date": session["date"], "x": benchmark["return"], "y": stock["return"],
                   "known_at": max(benchmark["known_at"], stock["known_at"])}
            rows[symbol].append(row)
            decisions.append({"date": session["date"], "symbol": symbol, "status": "ADMITTED"})
    models = {}
    fits = 0
    for symbol in STOCKS:
        observations = rows[symbol]
        m = {"symbol": symbol, "benchmark": BENCHMARK, "available": False, "n": len(observations),
             "training_rows_sha256": _sha(observations), "beta": None, "mu": None, "sigma": None,
             "available_at": max((v["known_at"] for v in observations), default=None),
             "training_dates": [v["date"] for v in observations]}
        models[symbol] = m
        if m["n"] < r["minimum_training_sessions"]:
            m["reason"] = "INSUFFICIENT_ALIGNED_TRAINING_OBSERVATIONS"
            continue
        xs, ys = [v["x"] for v in observations], [v["y"] for v in observations]
        xm, ym = fmean(xs), fmean(ys)
        denominator = math.fsum((x - xm) ** 2 for x in xs)
        if denominator <= 0:
            m["reason"] = "BENCHMARK_VARIANCE_ZERO"
            continue
        beta = math.fsum((x - xm) * (y - ym) for x, y in zip(xs, ys)) / denominator
        residuals = [y - beta * x for x, y in zip(xs, ys)]
        mu, sigma = fmean(residuals), stdev(residuals)
        fits += 1
        m.update(beta=beta, mu=mu, sigma=sigma)
        if not r["beta_min"] <= beta <= r["beta_max"]:
            m["reason"] = "BETA_OUTSIDE_FROZEN_RANGE"
        elif sigma <= SIGMA_FLOOR:
            m["reason"] = "RESIDUAL_SIGMA_AT_OR_BELOW_FLOOR"
        else:
            m.update(available=True, reason=None)
    result = {"schema": "HARPOON_RESIDUAL_MODELS_1", "models": models,
              "training_decisions": decisions, "provenance": _provenance(protocol),
              "counts": {"training_calendar_sessions": len(sessions), "fit_invocations": fits,
                         "available_models": sum(m["available"] for m in models.values()),
                         "admitted_training_observations": {s: len(rows[s]) for s in STOCKS}}}
    result["model_payload_sha256"] = _sha(result)
    return result


def _costs(protocol):
    scenarios = protocol["scenarios"]
    _need(set(scenarios) == {"NOMINAL", "STRESS"}, "TWO_FROZEN_SCENARIOS_REQUIRED")
    for name, c in scenarios.items():
        _need(all(_finite(c.get(k)) and c[k] >= 0 for k in (
            "spread_bps", "slippage_bps", "commission_usd_per_share_per_side")), "COST_CONTRACT:" + name)
    return scenarios


def generate_signals(data, models, protocol):
    """Create decision-time opportunities only. Does not inspect future fills/exits."""
    r, scenarios = _recipe(protocol), _costs(protocol)
    _, train_end, start, end = _periods(protocol)
    _need(models.get("schema") == "HARPOON_RESIDUAL_MODELS_1", "MODEL_SCHEMA")
    _need(models.get("provenance", {}).get("protocol_sha256") == _sha(protocol), "MODEL_PROTOCOL_BINDING")
    _need(models.get("model_payload_sha256") == _sha({k: v for k, v in models.items() if k != "model_payload_sha256"}),
          "MODEL_PAYLOAD_BINDING")
    _need(set(models["models"]) == set(STOCKS), "MODEL_UNIVERSE")
    panel = _Panel(data)
    signals = {name: {p: [] for p in POLICIES} for name in sorted(scenarios)}
    decisions = []
    refusal_counts = Counter()
    sessions = [s for s in panel.sessions if start <= s["date"] <= end]
    _need(sessions, "EMPTY_EVALUATION")
    for session in sessions:
        at = session["open"] + r["entry_minutes"] * 60_000 + r["entry_delay_ms"]
        entry = session["open"] + (r["entry_minutes"] + 5) * 60_000
        daily = {"date": session["date"], "at": at, "planned_entry_at": entry,
                 "candidates": {}, "selected_symbol": None, "scenarios": {}}
        decisions.append(daily)
        if entry >= session["close"] - BAR_MS:
            daily["reason"] = "NO_SCHEDULED_ENTRY_WITHIN_SESSION"
            refusal_counts[daily["reason"]] += 1
            continue
        benchmark, benchmark_reason = panel.shock(BENCHMARK, session, r)
        candidates = []
        for symbol in STOCKS:
            m = models["models"][symbol]
            candidate = {"symbol": symbol, "admissible": False}
            daily["candidates"][symbol] = candidate
            reason = None
            if not m["available"]:
                reason = "MODEL_UNAVAILABLE:" + str(m.get("reason"))
            elif not isinstance(m.get("available_at"), int) or m["available_at"] >= at or any(d > train_end for d in m["training_dates"]):
                reason = "MODEL_NOT_CAUSALLY_AVAILABLE"
            elif benchmark_reason:
                reason = "BENCHMARK_" + benchmark_reason
            else:
                stock, reason = panel.shock(symbol, session, r)
                if not reason:
                    e = stock["return"] - m["beta"] * benchmark["return"]
                    z = (e - m["mu"]) / m["sigma"]
                    score = r["recovery_fraction"] * (m["mu"] - e)
                    candidate.update(residual=e, z=z, score_hypothesis=score, price=stock["price"],
                                     beta=m["beta"], known_at=max(stock["known_at"], benchmark["known_at"]))
                    if abs(z) > r["max_absolute_z"]:
                        reason = "ABSOLUTE_Z_DRIFT_REFUSAL"
                    else:
                        atr, reason = panel.atr(symbol, session, at, r["atr_sessions"])
                        if not reason:
                            candidate.update(admissible=True, stop_distance=atr["value"], atr_history_dates=atr["history_dates"])
                            candidates.append(candidate)
            candidate["reason"] = reason
            if reason:
                refusal_counts[reason] += 1
        if not candidates:
            daily["reason"] = "NO_ADMISSIBLE_STOCK"
            continue
        selected = min(candidates, key=lambda v: (v["z"], v["symbol"]))
        daily["selected_symbol"] = selected["symbol"]
        daily["reason"] = None
        sector_atr, sector_reason = panel.atr(BENCHMARK, session, at, r["atr_sessions"])
        for name, costs in sorted(scenarios.items()):
            friction = ((costs["spread_bps"] + 2 * costs["slippage_bps"]) / 10_000
                        + 2 * costs["commission_usd_per_share_per_side"] / selected["price"])
            hurdle = friction + r["net_hurdle_bps"] / 10_000
            z_ok, hurdle_ok = selected["z"] <= r["z_entry"], selected["score_hypothesis"] > hurdle
            passes = z_ok and hurdle_ok
            action = {"z_gate": z_ok, "hurdle_gate": hurdle_ok, "roundtrip_friction_fraction": friction,
                      "hurdle_fraction": hurdle, "residual_proposed": passes,
                      "stock_threshold_off_proposed": True, "sector_proposed": passes and sector_reason is None,
                      "sector_refusal": sector_reason if passes else None}
            daily["scenarios"][name] = action
            for policy in POLICIES:
                if policy == "RESIDUAL_LONG" and not passes:
                    continue
                if policy == "SECTOR_TIMING_CONTROL" and (not passes or sector_reason):
                    continue
                sector = policy == "SECTOR_TIMING_CONTROL"
                symbol = BENCHMARK if sector else selected["symbol"]
                stop = sector_atr["value"] if sector else selected["stop_distance"]
                metadata = {"economicHypothesis": "INTRADAY_SECTOR_RESIDUAL_RECOVERY",
                            "execution_template": "CLOSED_CHANNEL:BASELINE", "policy": policy, "scenario": name,
                            "candidate_symbol": selected["symbol"], "candidate_z": selected["z"],
                            "score_hypothesis": selected["score_hypothesis"], "score_is_expected_return": False,
                            "roundtrip_friction_fraction": friction, "hurdle_fraction": hurdle,
                            "control_is_exactly_exposure_matched": False,
                            "atr_history_dates": sector_atr["history_dates"] if sector else selected["atr_history_dates"]}
                signals[name][policy].append({"id": f"RESIDUAL:{name}:{policy}:{session['date']}:{symbol}",
                    "symbol": symbol, "hypothesis": "CLOSED_CHANNEL", "direction": 1, "at": at,
                    "plannedEntryAt": entry, "index": 0, "stopDistance": stop, "regime": .4, "metadata": metadata})
    pairing = {}
    for scenario, by_policy in signals.items():
        stock_events = {s["at"] for s in by_policy["RESIDUAL_LONG"]}
        sector_events = {s["at"] for s in by_policy["SECTOR_TIMING_CONTROL"]}
        pairing[scenario] = {"residual_proposed_events": len(stock_events),
                             "sector_proposed_events": len(sector_events),
                             "unmatched_residual_events": len(stock_events - sector_events),
                             "pairing_is_execution_match": False}
    return {"schema": "HARPOON_RESIDUAL_SIGNALS_1", "signals": signals, "daily_decisions": decisions,
            "counts": {"evaluation_sessions": len(sessions), "refusal_reasons": dict(sorted(refusal_counts.items())),
                       "signals": {s: {p: len(v) for p, v in ps.items()} for s, ps in signals.items()},
                       "proposed_event_pairing": pairing},
            "provenance": {**_provenance(protocol), "model_payload_sha256": models["model_payload_sha256"],
                           "exit_and_terminal_entry_cutoff_enforced_by": "NATIVE_FUNDED_REPLAY",
                           "control": "THRESHOLD_OFF_RETAINS_SAME_LOWEST_Z_STOCK_AND_ALL_OTHER_GATES"}}
