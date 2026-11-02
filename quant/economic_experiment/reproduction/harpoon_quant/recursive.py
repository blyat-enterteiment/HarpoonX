"""Persistent, budgeted recursive selection with a once-only terminal holdout."""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np

from .core import digest, timestamp
from .optimization import Policy, development_score, replay, validate_window


class Journal:
    def __init__(self, path: str | Path):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(p, timeout=2)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS optimizer_state(k TEXT PRIMARY KEY,v TEXT NOT NULL,h TEXT NOT NULL)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS optimizer_audit(seq INTEGER PRIMARY KEY,payload TEXT NOT NULL,previous TEXT NOT NULL,h TEXT NOT NULL)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS optimizer_holdouts(lo TEXT,hi TEXT,domain TEXT,campaign TEXT,PRIMARY KEY(lo,hi,domain))"
        )
        self.db.commit()
        with self.transaction():
            self.verify()

    def close(self) -> None:
        self.db.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def verify(self) -> None:
        previous = "GENESIS"
        latest = {}
        for payload, prior, h in self.db.execute(
            "SELECT payload,previous,h FROM optimizer_audit ORDER BY seq"
        ):
            event = json.loads(payload)
            if previous != prior or h != digest({"event": event, "previous": prior}):
                raise ValueError("OPTIMIZER_AUDIT_INTEGRITY")
            previous = h
            latest[event["key"]] = event["value_hash"]
        for key, value, h in self.db.execute("SELECT k,v,h FROM optimizer_state"):
            if digest(json.loads(value)) != h or latest.get(key) != h:
                raise ValueError("OPTIMIZER_STATE_INTEGRITY")

    def get(self, key: str) -> Any:
        row = self.db.execute(
            "SELECT v,h FROM optimizer_state WHERE k=?", (key,)
        ).fetchone()
        if row is None:
            return None
        data = json.loads(row[0])
        if digest(data) != row[1]:
            raise ValueError("OPTIMIZER_STATE_INTEGRITY")
        return data

    def put(self, key: str, value: Any, now: str) -> None:
        h = digest(value)
        prior = self.db.execute(
            "SELECT h FROM optimizer_audit ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        previous = prior[0] if prior else "GENESIS"
        event = {"key": key, "value_hash": h, "at": now}
        self.db.execute(
            "INSERT INTO optimizer_audit(payload,previous,h) VALUES(?,?,?)",
            (
                json.dumps(event, sort_keys=True),
                previous,
                digest({"event": event, "previous": previous}),
            ),
        )
        self.db.execute(
            "INSERT OR REPLACE INTO optimizer_state VALUES(?,?,?)",
            (key, json.dumps(value, allow_nan=False, sort_keys=True), h),
        )


def active_policy(
    path: str, binding: dict[str, Any], asof: str
) -> dict[str, Any] | None:
    if not Path(path).is_file():
        return None
    j = Journal(path)
    try:
        active = j.get("active")
        if not active:
            return None
        if active.get("pause_entries"):
            return active
        if active["binding"] != binding or timestamp(asof) > timestamp(
            active["valid_until"]
        ):
            return {
                "pause_entries": True,
                "reason": "OPTIMIZER_BINDING_CHANGED_OR_EXPIRED",
            }
        if active["origin"] != "OBSERVED" or active["status"] != "PAPER_ACCEPTED":
            raise ValueError("INVALID_ACTIVE_OPTIMIZER_POLICY")
        Policy(**active["policy"])
        return active
    finally:
        j.close()


def tick(
    panel: dict[str, Any] | None,
    config: dict[str, Any],
    binding: dict[str, Any],
    now: str,
    *,
    paper: bool = True,
    live_drawdown: float = 0.0,
) -> dict[str, Any]:
    base = {
        "schema": "HARPOON_RECURSIVE_1",
        "execution_allowed": False,
        "selected": [],
        "trade_authorization": False,
    }
    if not config.get("enabled", False):
        return {**base, "status": "DISABLED"}
    path = config["statePath"]
    j = Journal(path)
    try:
        if not panel:
            return {
                **base,
                "status": "WAIT_DATA",
                "reason": "OPPORTUNITY_PANEL_REQUIRED",
                "active": active_policy(path, binding, now),
            }
        if (
            panel.get("origin") not in ("OBSERVED", "SYNTHETIC_ENGINEERING_ONLY")
            or panel.get("binding") != binding
        ):
            raise ValueError("OPTIMIZER_ORIGIN_OR_BINDING")
        for k in (
            "net_costs_confirmed",
            "cashflows_adjusted",
            "complete_opportunity_universe",
            "frozen_exit_replay_validated",
        ):
            if panel.get(k) is not True:
                raise ValueError("OPTIMIZER_EVIDENCE_REQUIRED:" + k)
        for field in ("account_id", "execution_hash", "forecast_hash", "risk_limits"):
            if field not in binding:
                raise ValueError("OPTIMIZER_BINDING_FIELD:" + field)
        settings = {
            **binding["risk_limits"],
            "origin": panel["origin"],
            "min_development_trades": 20,
        }
        validate_window(panel["development"], now)
        if len(panel["development"]["days"]) < 180:
            raise ValueError("DEVELOPMENT_180_DAYS_REQUIRED")
        lo, hi = panel["holdout_start"], panel["holdout_end"]
        if lo <= panel["development"]["days"][-1] or lo > hi:
            raise ValueError("HOLDOUT_AFTER_DEVELOPMENT")
        budget_limit = config.get("lifetimeTrials", 128)
        max_trials = config.get("maxTrials", 24)
        max_generations = config.get("maxGenerations", 3)
        if (
            not 8 <= budget_limit <= 200
            or not 3 <= max_trials <= 32
            or not 1 <= max_generations <= 8
        ):
            raise ValueError("OPTIMIZER_BUDGET_BOUNDS")
        seal = digest(
            {
                "development": panel["development"],
                "origin": panel["origin"],
                "settings": settings,
                "binding": binding,
                "holdout_start": lo,
                "holdout_end": hi,
                "protocol": "FROZEN_EXIT_POLICY_SELECTION_1",
            }
        )
        campaign = digest({"study": panel["study_id"], "seal": seal})
        key = "campaign:" + panel["study_id"]
        with j.transaction():
            budget = j.get("budget") or {"limit": budget_limit, "spent": 0}
            if budget["limit"] != budget_limit:
                raise ValueError("CUMULATIVE_BUDGET_IS_FROZEN")
            if not j.get("budget"):
                j.put("budget", budget, now)
            state = j.get(key)
            if state and state["seal"] != seal:
                raise ValueError("DEVELOPMENT_OR_PROTOCOL_MUTATED")
            if not state:
                state = {
                    "id": campaign,
                    "seal": seal,
                    "registered_at": now,
                    "stage": "SEARCH",
                    "generation": 0,
                    "spent": 0,
                    "best": asdict(Policy()),
                    "best_score": -1e6,
                    "seen": [],
                    "plateau": 0,
                    "max_trials": max_trials,
                    "max_generations": max_generations,
                    "settings_hash": digest(config),
                }
                j.put(key, state, now)
            if state["settings_hash"] != digest(config):
                raise ValueError("OPTIMIZER_CONFIG_MUTATED")
            active = j.get("active")
            if active and live_drawdown >= settings.get("max_drawdown", 0.08):
                active = {
                    **active,
                    "pause_entries": True,
                    "reason": "OPTIMIZER_OBSERVED_RISK_PAUSE",
                }
                j.put("active", active, now)
                return {**base, "status": "RISK_PAUSED", "active": active}
            if state["stage"] in (
                "PAPER_ACCEPTED",
                "RESEARCH_ACCEPTED",
                "REJECTED",
                "EXHAUSTED",
                "HOLDOUT_INTERRUPTED",
            ):
                return {
                    **base,
                    "status": state["stage"],
                    "campaign": state,
                    "budget": budget,
                    "active": active,
                }
            if state.get("running"):
                if timestamp(now) <= timestamp(state["lease_until"]):
                    return {**base, "status": "BUSY", "campaign_id": campaign}
                if state["stage"] == "HOLDOUT_RUNNING":
                    state.update(stage="HOLDOUT_INTERRUPTED", running=False)
                    j.put(key, state, now)
                    return {**base, "status": state["stage"]}
                state["running"] = False
                state["interrupted_attempts"] = state.get("interrupted_attempts", 0) + 1
                j.put(key, state, now)
            if state["stage"] == "SEARCH":
                incumbent = Policy(**state["best"])
                policies = (
                    [incumbent] if state["generation"] == 0 else []
                ) + incumbent.neighbors()
                policies = [
                    p for p in policies if digest(asdict(p)) not in state["seen"]
                ]
                remaining = min(
                    max_trials - state["spent"], budget["limit"] - budget["spent"]
                )
                policies = policies[: max(0, remaining)]
                if not policies:
                    state["stage"] = (
                        "LOCKED" if state["best_score"] > -1e6 else "EXHAUSTED"
                    )
                    j.put(key, state, now)
                    return {
                        **base,
                        "status": state["stage"],
                        "campaign": state,
                        "budget": budget,
                    }
                state.update(
                    running=True,
                    lease_until=(timestamp(now) + timedelta(seconds=90)).isoformat(),
                )
                for p in policies:
                    state["seen"].append(digest(asdict(p)))
                state["spent"] += len(policies)
                budget["spent"] += len(policies)
                j.put("budget", budget, now)
                j.put(key, state, now)
            else:
                policies = []
        if policies:
            results = []
            started = time.perf_counter()
            for p in policies:
                try:
                    if time.perf_counter() - started > config.get("cpuSeconds", 5):
                        raise ValueError("CPU_BUDGET_CONSUMED")
                    result = development_score(panel["development"], p, settings)
                except (ValueError, ArithmeticError, KeyError) as exc:
                    result = {"score": -1e6, "admissible": False, "error": str(exc)}
                results.append((p, result))
                with j.transaction():
                    j.put(
                        "trial:" + campaign + ":" + digest(asdict(p)),
                        {
                            "policy": asdict(p),
                            "result": result,
                            "origin": panel["origin"],
                        },
                        now,
                    )
            best_p, best_result = max(results, key=lambda x: x[1]["score"])
            with j.transaction():
                state = j.get(key)
                if best_result["score"] > state["best_score"] + 1e-12:
                    state.update(
                        best=asdict(best_p), best_score=best_result["score"], plateau=0
                    )
                else:
                    state["plateau"] += 1
                state.update(generation=state["generation"] + 1, running=False)
                if (
                    state["generation"] >= max_generations
                    or state["plateau"] >= 2
                    or state["spent"] >= max_trials
                ):
                    state["stage"] = (
                        "LOCKED" if state["best_score"] > -1e6 else "REJECTED"
                    )
                j.put(key, state, now)
            return {
                **base,
                "status": state["stage"],
                "campaign": state,
                "budget": budget,
                "trial_results": [
                    {"policy": asdict(p), "result": r} for p, r in results
                ],
            }
        # The terminal holdout is never read before a finalist has been frozen.
        holdout = panel.get("holdout")
        if not holdout:
            return {**base, "status": "WAIT_HOLDOUT", "campaign": state}
        if timestamp(now) < timestamp(hi + "T00:00:00+00:00") + timedelta(days=1):
            return {**base, "status": "WAIT_HOLDOUT", "campaign": state}
        validate_window(holdout, now)
        if (
            holdout["days"][0] != lo
            or holdout["days"][-1] != hi
            or len(holdout["days"]) < 60
        ):
            raise ValueError("FROZEN_HOLDOUT_60_DAYS_REQUIRED")
        domain = digest(
            {"account": binding.get("account_id"), "origin": panel["origin"]}
        )
        with j.transaction():
            if j.db.execute(
                "SELECT 1 FROM optimizer_holdouts WHERE domain=? AND NOT(hi<? OR lo>?)",
                (domain, lo, hi),
            ).fetchone():
                raise ValueError("HOLDOUT_ALREADY_CONSUMED")
            j.db.execute(
                "INSERT INTO optimizer_holdouts VALUES(?,?,?,?)",
                (lo, hi, domain, campaign),
            )
            state.update(
                stage="HOLDOUT_RUNNING",
                running=True,
                lease_until=(timestamp(now) + timedelta(seconds=90)).isoformat(),
            )
            j.put(key, state, now)
        selected = Policy(**state["best"])
        baseline = replay(holdout, Policy(), settings)
        challenger = replay(holdout, selected, settings)
        stressed = replay(holdout, selected, settings, cashflow_stress=1.5)
        difference = np.asarray(challenger["returns"]) - np.asarray(baseline["returns"])
        lower = paired_lower(difference, budget["limit"])
        m, bm = challenger["metrics"], baseline["metrics"]
        passed = (
            lower > 0
            and m["net_profit_usd_on_adjusted_initial_capital"]
            > bm["net_profit_usd_on_adjusted_initial_capital"]
            + config.get("minGainUsd", 5)
            and m["max_drawdown"]
            <= min(settings.get("max_drawdown", 0.08), bm["max_drawdown"] + 1e-12)
            and m["sortino_per_period"] is not None
            and m["sortino_per_period"] >= config.get("minSortinoPerPeriod", 0)
            and m["trade_count"] >= config.get("minHoldoutTrades", 20)
            and stressed["metrics"]["total_return"] > 0
        )
        prospective = timestamp(state["registered_at"]) < timestamp(
            lo + "T00:00:00+00:00"
        )
        status = (
            "PAPER_ACCEPTED"
            if passed
            and prospective
            and paper
            and config.get("autoPaper", False)
            and panel["origin"] == "OBSERVED"
            else "RESEARCH_ACCEPTED"
            if passed
            else "REJECTED"
        )
        receipt = {
            "passed": bool(passed),
            "paired_mean_improvement_lower": lower,
            "family_budget": budget["limit"],
            "holdout_hash": digest(holdout),
            "baseline": bm,
            "challenger": m,
            "cost_stress_1_5": stressed["metrics"],
            "prospectively_registered": prospective,
            "scope": "Bootstrap estimate under five-day blocks and full registered budget; no guaranteed future improvement.",
        }
        with j.transaction():
            state.update(stage=status, running=False, result=receipt, completed_at=now)
            j.put(key, state, now)
            if status == "PAPER_ACCEPTED":
                active = {
                    "status": status,
                    "policy": state["best"],
                    "origin": panel["origin"],
                    "binding": binding,
                    "campaign_id": campaign,
                    "valid_until": min(
                        timestamp(now) + timedelta(days=30),
                        timestamp(hi + "T23:59:59+00:00") + timedelta(days=30),
                    ).isoformat(),
                    "receipt_hash": digest(receipt),
                    "pause_entries": False,
                }
                j.put("active", active, now)
        return {
            **base,
            "status": status,
            "campaign": state,
            "result": receipt,
            "active": j.get("active"),
        }
    finally:
        j.close()


def runtime_tick(raw: dict[str, Any]) -> dict[str, Any]:
    config = raw["config"].get("quant", {}).get("optimizer", {})
    if raw.get("research_paused"):
        return {"status": "PAUSED", "selected": [], "execution_allowed": False}
    panel_path = config.get("panelFile")
    if (
        panel_path
        and Path(panel_path).is_file()
        and Path(panel_path).stat().st_size > 32 * 1024 * 1024
    ):
        raise ValueError("OPPORTUNITY_PANEL_FILE_BOUND")
    panel = (
        json.loads(Path(panel_path).read_text())
        if panel_path and Path(panel_path).is_file()
        else None
    )
    return tick(
        panel,
        config,
        raw.get("optimizer_binding", {}),
        raw["optimizer_asof"],
        paper=raw["config"].get("mode") == "paper",
        live_drawdown=raw.get("drawdown_fraction", 0),
    )


def paired_lower(values: np.ndarray, family: int, seed: int = 1701) -> float:
    """Five-day circular blocks, family-adjusted tail, bounded temporary arrays."""
    if len(values) < 60 or not np.isfinite(values).all() or not 1 <= family <= 200:
        raise ValueError("PAIRED_BOOTSTRAP_DOMAIN")
    runs = max(2000, 400 * family)
    rng = np.random.default_rng(seed)
    means = []
    n = len(values)
    for offset in range(0, runs, 256):
        count = min(256, runs - offset)
        starts = rng.integers(0, n, size=(count, (n + 4) // 5))
        indexes = (starts[:, :, None] + np.arange(5)) % n
        means.extend(values[indexes.reshape(count, -1)[:, :n]].mean(axis=1).tolist())
    return float(np.quantile(means, 0.05 / family, method="lower"))
