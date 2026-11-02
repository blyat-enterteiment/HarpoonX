"""Registered offline research: funded event replay, bounded hypotheses, no orders.

All generated prices are SYNTHETIC_ENGINEERING_ONLY. Calendar can be observed.
No runtime promotion, no account permission inference, no production model fitting.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
from scipy.special import ndtr

from .core import digest
from .ledger import reconcile_events
from .performance import report
from .recursive import Journal

ORIGIN = "SYNTHETIC_ENGINEERING_ONLY"
NY = ZoneInfo("America/New_York")


def bs(s: Any, k: Any, t: Any, v: Any, call: bool) -> Any:
    t = np.maximum(t, 1e-9)
    d1 = (np.log(s / k) + (0.04 + 0.5 * v * v) * t) / (v * np.sqrt(t))
    d2 = d1 - v * np.sqrt(t)
    c = s * ndtr(d1) - k * np.exp(-0.04 * t) * ndtr(d2)
    return np.maximum(0, c if call else c - s + k * np.exp(-0.04 * t))


def greeks(s: float, k: float, t: float, v: float, call: bool) -> dict[str, float]:
    d1 = (math.log(s / k) + (0.04 + 0.5 * v * v) * t) / (v * math.sqrt(t))
    density = math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi)
    return dict(
        delta=float(ndtr(d1)) - (0 if call else 1),
        gamma=density / (s * v * math.sqrt(t)),
        vega=s * density * math.sqrt(t),
    )


def quote(mid: float, relative_spread: float) -> tuple[float, float]:
    """Cent ticks, natural sides; never substitute midpoint for a fill."""
    return max(0.0, math.floor(mid * (1 - relative_spread / 2) * 100) / 100), math.ceil(
        mid * (1 + relative_spread / 2) * 100
    ) / 100


def timeline(calendar: dict[str, Any]) -> list[datetime]:
    marks = []
    for row in calendar["calendar"]:
        opening = datetime.fromisoformat(row["open"]).replace(tzinfo=NY)
        closing = datetime.fromisoformat(row["close"]).replace(tzinfo=NY)
        marks += [
            opening + timedelta(minutes=15),
            opening + timedelta(minutes=30),
            closing - timedelta(minutes=15),
        ]
    return sorted({m.astimezone(UTC) for m in marks})


def exit_index(marks: list[datetime], i: int) -> int:
    deadline = marks[i] + timedelta(hours=72)
    j = (
        int(
            np.searchsorted(
                [m.timestamp() for m in marks], deadline.timestamp(), side="right"
            )
        )
        - 1
    )
    return min(j, len(marks) - 1)


@dataclass(frozen=True)
class Policy:
    flags: str = ""

    def __post_init__(self) -> None:
        if any(c not in "ABCDEF" for c in self.flags) or len(set(self.flags)) != len(
            self.flags
        ):
            raise ValueError("UNKNOWN_ECONOMIC_POLICY")


class World:
    def __init__(self, calendar: dict[str, Any], seed: int):
        self.seed = seed
        self.marks = timeline(calendar)
        self._exits = np.minimum(
            np.searchsorted(
                np.array([m.timestamp() for m in self.marks]),
                np.array([m.timestamp() for m in self.marks]) + 72 * 3600,
                side="right",
            )
            - 1,
            len(self.marks) - 1,
        )
        self.start = self.marks[0].date()
        self.n = (self.marks[-1].date() - self.start).days + 1
        rng = np.random.default_rng(seed)
        self.spot = np.zeros((self.n, 24))
        self.spot[0] = rng.uniform(20, 65, 24)
        self.returns = np.zeros_like(self.spot)
        rv = rng.uniform(0.45, 0.95, 24)
        self.iv = np.zeros_like(self.spot)
        self.iv[0] = rv * 1.15
        for d in range(1, self.n):
            regime = 1.0 if d < 0.57 * self.n else 1.6 if d < 0.714 * self.n else 0.8
            persistence = (
                0.18 if d < 0.57 * self.n else -0.12 if d < 0.714 * self.n else 0.08
            )
            market = rng.normal()
            shocks = rng.standard_t(6, 24) * math.sqrt(4 / 6)
            jump = np.where(rng.random(24) < 0.008, rng.normal(0, 0.10, 24), 0)
            self.returns[d] = np.clip(
                persistence * self.returns[d - 1]
                + rv
                / math.sqrt(365)
                * regime
                * (0.4 * market + math.sqrt(0.84) * shocks)
                + jump,
                -0.3,
                0.3,
            )
            self.spot[d] = self.spot[d - 1] * np.exp(self.returns[d])
            self.iv[d] = np.clip(
                0.94 * self.iv[d - 1]
                + 0.06 * rv * regime * 1.15
                + rng.normal(0, 0.015, 24),
                0.2,
                2,
            )
        # Execution proxies are declared synthetic; shared for every policy.
        ex = np.random.default_rng(seed + 917)
        self.ages = ex.exponential(15, (len(self.marks), 24))
        self.depth = ex.integers(1, 8, (len(self.marks), 24))
        self.nodes, self.weights = np.polynomial.hermite.hermgauss(12)
        self.cache: dict[Any, Any] = {}

    def day(self, mark: int) -> int:
        return (self.marks[mark].date() - self.start).days

    def candidate(
        self, mark: int, asset: int, call: bool, flags: str
    ) -> dict[str, Any]:
        key = (mark, asset, call, "A" in flags, "C" in flags)
        if key in self.cache:
            return dict(self.cache[key])
        d = self.day(mark)
        end = int(self._exits[mark])
        h = (self.marks[end] - self.marks[mark]).total_seconds() / 86400
        s = float(self.spot[d, asset])
        v = float(self.iv[d, asset])
        days = 45 if "C" in flags else 21
        z = 1.0 if "C" in flags else 1.7
        t = days / 365
        k = s * math.exp((1 if call else -1) * z * v * math.sqrt(t))
        mid = float(bs(s, k, t, v, call))
        spread = 0.08 + 0.04 * (v > 0.9)
        _bid, ask = quote(mid, spread)
        past = self.returns[max(1, d - 120) : d + 1]
        if "A" in flags:
            xs, ys = past[:-1].ravel(), past[1:].ravel()
            beta = (
                float(np.clip(np.dot(xs, ys) / (np.dot(xs, xs) + 0.05), -0.5, 0.5))
                if len(xs)
                else 0
            )
            mu = float(
                np.clip(
                    sum(beta**k for k in range(1, max(1, math.ceil(h)) + 1))
                    * h
                    / max(1, math.ceil(h))
                    * self.returns[d, asset],
                    -0.05,
                    0.05,
                )
            )
            sigma = max(0.25, float(np.std(past[-20:, asset])) * math.sqrt(365))
            samples = s * np.exp(
                mu + math.sqrt(2 * sigma * sigma * h / 365) * self.nodes
            )
            expected_mid = float(
                np.dot(self.weights, bs(samples, k, t - h / 365, v, call))
                / math.sqrt(math.pi)
            )
            expected_stock = s * math.exp(mu + 0.5 * sigma * sigma * h / 365)
            reserve = 0.10
        else:
            mu = h * float(
                np.clip(
                    0.12 * self.returns[d, asset]
                    + 0.04 * self.returns[max(0, d - 2) : d + 1, asset].mean(),
                    -0.012,
                    0.012,
                )
            )
            expected_stock = s * math.exp(mu)
            expected_mid = float(bs(expected_stock, k, t - h / 365, v, call))
            reserve = 0.02
        funding = ask * 100 + 0.65
        expected = expected_mid * (1 - spread / 2) * 100 - 0.65
        g = greeks(s, k, t, v, call)
        row = dict(
            asset=asset,
            call=call,
            entry=mark,
            exit=end,
            strike=k,
            dte=days,
            funding=funding,
            risk=funding + 0.65,
            edge=expected - funding - reserve * funding,
            spread=spread,
            exposure=abs(g["delta"]) * s * 100,
            kind="option",
            fee=0.65,
            stock_expected=expected_stock,
            initial_mid=mid,
            **g,
        )
        self.cache[key] = dict(row)
        return row

    def stock(self, option: dict[str, Any]) -> dict[str, Any]:
        row = dict(option)
        s = float(self.spot[self.day(row["entry"]), row["asset"]])
        row.update(
            kind="stock",
            funding=s * 1.0005,
            risk=s * 1.0005,
            edge=row["stock_expected"] * 0.9995 - s * 1.0005,
            exposure=s,
            fee=0.0,
            delta=1.0,
            gamma=0.0,
            vega=0.0,
        )
        return row

    def value(
        self, position: dict[str, Any], mark: int, stress: float, scenario: str = "base"
    ) -> tuple[float, dict[str, float], float]:
        d = self.day(mark)
        a = position["asset"]
        s = float(self.spot[d, a])
        if position["kind"] == "stock":
            return (
                self.scenario_mark(s * (1 - 0.0005 * stress), position, scenario),
                dict(delta=1.0, gamma=0.0, vega=0.0, mid_cash=s),
                s,
            )
        elapsed = (
            self.marks[mark] - self.marks[position["entry"]]
        ).total_seconds() / 86400
        t = (position["dte"] - elapsed) / 365
        v = float(self.iv[d, a])
        mid = float(bs(s, position["strike"], t, v, position["call"]))
        spread = 0.08 + 0.04 * (v > 0.9)
        bid, _ = quote(mid, min(0.9, spread * stress))
        g = greeks(s, position["strike"], t, v, position["call"])
        g["mid_cash"] = mid * 100
        return (
            self.scenario_mark(
                bid * 100 - position["fee"] * stress, position, scenario
            ),
            g,
            s,
        )

    @staticmethod
    def scenario_mark(unit: float, position: dict[str, Any], scenario: str) -> float:
        if scenario == "gaps" and position["kind"] == "option":
            unit *= 0.9
        if scenario == "iv_crush" and position["kind"] == "option":
            unit *= 0.8
        if scenario == "liquidity":
            unit -= 0.05 * position["funding"]
        return unit


def replay(
    world: World,
    policy: Policy,
    start: str,
    end: str,
    limits: dict[str, Any],
    *,
    stress: float = 1.0,
    scenario: str = "base",
) -> dict[str, Any]:
    if not math.isfinite(stress) or stress < 1 or scenario not in {
        "base",
        "gaps",
        "iv_crush",
        "liquidity",
        "delay",
        "outage",
    }:
        raise ValueError("STRESS_DOMAIN")
    for key, upper in {
        "risk_fraction": 0.0025,
        "open_risk_fraction": 0.015,
        "gross_fraction": 0.5,
        "asset_fraction": 0.12,
        "factor_fraction": 0.5,
        "max_drawdown": 0.08,
        "daily_loss": 0.02,
    }.items():
        if not math.isfinite(limits[key]) or not 0 < limits[key] <= upper:
            raise ValueError("ORIGINAL_LIMIT_ENVELOPE:" + key)
    if (
        type(limits["max_positions"]) is not int
        or not 1 <= limits["max_positions"] <= 8
        or not 0 < limits.get("capital", 20000) <= 20000
    ):
        raise ValueError("CAPITAL_OR_POSITION_ENVELOPE")
    flags = policy.flags
    limits = dict(limits)
    if "F" in flags:
        # A restrictive policy must never relax an already tighter user limit.
        limits["max_positions"] = min(limits["max_positions"], 4)
        limits["factor_fraction"] = min(limits["factor_fraction"], 0.25)
        limits["open_risk_fraction"] = min(limits["open_risk_fraction"], 0.008)
    initial = float(limits.get("capital", 20000))
    cash = initial
    peak = initial
    positions: list[dict[str, Any]] = []
    trades = []
    ledger = []
    daily = {}
    blocks: dict[str, int] = {}
    previous = initial
    session_open = initial
    last_date = ""
    risk_paused = False
    day_paused = False
    exposure_paused = False
    risk_breaches: list[dict[str, Any]] = []

    def blocked(reason: str) -> None:
        blocks[reason] = blocks.get(reason, 0) + 1

    def snapshot(at: datetime, kind: str) -> dict[str, Any]:
        return dict(
            at=at.isoformat(),
            kind=kind,
            cash=cash,
            nav=cash + sum(p["lots"] * p["marked"] for p in positions),
            open_positions=len(positions),
            gross_exposure_usd=sum(p["lots"] * p["exposure"] for p in positions),
            positions=[
                dict(
                    position_id=p["position_id"],
                    lots=p["lots"],
                    liquidation_value_per_lot=p["marked"],
                    exposure_per_lot=p["exposure"],
                )
                for p in positions
            ],
            gamma=sum(p["lots"] * p["gamma"] * 100 for p in positions),
            vega=sum(p["lots"] * p["vega"] * 100 for p in positions),
        )

    for i, at in enumerate(world.marks):
        date = at.date().isoformat()
        if not start <= date <= end:
            continue
        if date != last_date:
            session_open = previous
            last_date = date
            day_paused = False
            exposure_paused = False
        keep = []
        for p in positions:
            unit, g, s = world.value(p, i, stress, scenario)
            p.update(
                marked=unit,
                exposure=abs(g["delta"]) * s * (100 if p["kind"] == "option" else 1),
                gamma=g["gamma"],
                vega=g["vega"],
            )
        pre = snapshot(at, "PRE_NAV")
        ledger.append(pre)
        pre_nav = pre["nav"]
        capital_at_mark = max(0.0, min(initial, pre_nav))
        by_asset: dict[int, float] = {}
        by_factor: dict[int, float] = {}
        for p in positions:
            exposure = p["lots"] * p["exposure"]
            by_asset[p["asset"]] = by_asset.get(p["asset"], 0.0) + exposure
            factor_id = p["asset"] // 6
            by_factor[factor_id] = by_factor.get(factor_id, 0.0) + exposure
        caps = {
            "gross": capital_at_mark * limits["gross_fraction"],
            "asset": capital_at_mark * limits["asset_fraction"],
            "factor": capital_at_mark * limits["factor_fraction"],
        }
        reasons = []
        if pre["gross_exposure_usd"] > caps["gross"] + 1e-8:
            reasons.append("gross")
        if any(v > caps["asset"] + 1e-8 for v in by_asset.values()):
            reasons.append("asset")
        if any(v > caps["factor"] + 1e-8 for v in by_factor.values()):
            reasons.append("factor")
        if reasons:
            breach = dict(
                at=at.isoformat(), kind="RISK_BREACH", reasons=reasons,
                gross_exposure_usd=pre["gross_exposure_usd"],
                asset_exposure_usd=by_asset, factor_exposure_usd=by_factor,
                limits_usd=caps,
                action="CLOSE_AT_OBSERVED_MARK_AND_BLOCK_SESSION_ENTRIES",
            )
            risk_breaches.append(breach)
            ledger.append(breach)
            exposure_paused = True
            day_paused = True
            blocked("marked_exposure_limit")
        peak = max(peak, pre_nav)
        risk_paused = risk_paused or 1 - pre_nav / peak >= limits["max_drawdown"]
        day_paused = day_paused or pre_nav / session_open - 1 <= -limits.get(
            "daily_loss", 0.02
        )
        for p in positions:
            unit, g, s = world.value(p, i, stress, scenario)
            ratio = (unit - p["funding"]) / p["funding"]
            invalidated = "E" in flags and (
                (world.returns[world.day(i), p["asset"]] < 0) == p["call"]
            )
            due = (
                i >= p["exit"]
                or risk_paused
                or day_paused
                or ("E" in flags and (ratio >= 0.35 or ratio <= -0.35 or invalidated))
            )
            partial = (
                "E" in flags
                and ratio >= 0.35
                and p["lots"] >= 2
                and i < p["exit"]
                and not risk_paused
                and not day_paused
            )
            quantity = max(1, p["lots"] // 2) if partial else p["lots"] if due else 0
            if quantity:
                cash += quantity * unit
                ledger.append(
                    dict(
                        at=at.isoformat(), kind="EXIT",
                        position_id=p["position_id"],
                        instrument=p["instrument"],
                        asset=p["asset"], lots=quantity,
                        gross_cash_change=quantity * (unit + p["fee"] * stress),
                        fees_usd=quantity * p["fee"] * stress,
                        cash_change=quantity * unit,
                        remaining_lots=p["lots"] - quantity,
                        partial=quantity < p["lots"],
                    )
                )
                trades.append(
                    dict(
                        position_id=p["position_id"],
                        asset=p["asset"],
                        kind=p["kind"],
                        entry_at=world.marks[p["entry"]].isoformat(),
                        exit_at=at.isoformat(),
                        lots=quantity,
                        net_pnl_usd=quantity * (unit - p["funding"]),
                        cost_usd=quantity
                        * (p["entry_cost"] + max(0.0, g["mid_cash"] - unit)),
                        reason="marked_exposure_limit"
                        if exposure_paused
                        else "partial"
                        if partial
                        else "deadline"
                        if i >= p["exit"]
                        else "signal_or_risk",
                    )
                )
                p["lots"] -= quantity
            if p["lots"]:
                p.update(
                    marked=unit,
                    exposure=abs(g["delta"])
                    * s
                    * (100 if p["kind"] == "option" else 1),
                    gamma=g["gamma"],
                    vega=g["vega"],
                )
                keep.append(p)
        positions = keep
        nav = cash + sum(p["lots"] * p["marked"] for p in positions)
        peak = max(peak, nav)
        risk_paused = risk_paused or 1 - nav / peak >= limits["max_drawdown"]
        day_paused = day_paused or nav / session_open - 1 <= -limits.get(
            "daily_loss", 0.02
        )
        candidates = []
        # Entry snapshots are known at 09:45, monitoring marks do not create new signals.
        if (
            at.astimezone(NY).time().hour == 9
            and at.astimezone(NY).time().minute == 45
            and world.day(i) >= 121
        ):
            for a in range(24):
                for call in (True, False):
                    o = world.candidate(i, a, call, flags)
                    if "B" in flags and call:
                        stock = world.stock(o)
                        if stock["edge"] / stock["risk"] > o["edge"] / o["risk"]:
                            o = stock
                    if (
                        o["exit"] <= i
                        or world.marks[o["exit"]].date().isoformat() > end
                    ):
                        blocked("purge_deadline")
                        continue
                    if scenario == "delay":
                        o["edge"] -= 0.05 * o["funding"]
                    if scenario == "outage" and world.day(i) % 11 == 0:
                        blocked("outage")
                        continue
                    if o["edge"] <= 0:
                        blocked("nonpositive_known_edge")
                        continue
                    if o["risk"] > min(initial, nav) * limits["risk_fraction"]:
                        blocked("integer_risk_funding")
                        continue
                    if world.ages[i, a] > 60 or (
                        "D" in flags and (world.ages[i, a] > 30 or o["spread"] > 0.10)
                    ):
                        blocked("quote_age_or_spread")
                        continue
                    candidates.append(o)
            for o in sorted(
                candidates,
                key=lambda x: (-x["edge"] / x["risk"], x["asset"], x["call"]),
            ):
                if risk_paused or day_paused:
                    blocked("risk_pause")
                    continue
                if len(positions) >= limits["max_positions"]:
                    blocked("position_cap")
                    continue
                if any(p["asset"] == o["asset"] for p in positions):
                    blocked("held_underlying")
                    continue
                if "D" in flags and world.depth[i, o["asset"]] < 2:
                    blocked("depth_FOK")
                    continue
                # Stress is charged in actual cash, not only in a reported metric.
                if o["kind"] == "option":
                    _, ask = quote(o["initial_mid"], min(0.9, o["spread"] * stress))
                    o["funding"] = ask * 100 + 0.65 * stress
                    o["risk"] = o["funding"] + 0.65 * stress
                    o["entry_cost"] = o["funding"] - o["initial_mid"] * 100
                    o["last_mid"] = o["initial_mid"] * 100
                else:
                    s = float(world.spot[world.day(i), o["asset"]])
                    o["funding"] = s * (1 + 0.0005 * stress)
                    o["risk"] = o["funding"]
                    o["entry_cost"] = o["funding"] - s
                    o["last_mid"] = s
                capital = min(initial, nav)
                gross = sum(p["lots"] * p["exposure"] for p in positions)
                factor = sum(
                    p["lots"] * p["exposure"]
                    for p in positions
                    if p["asset"] // 6 == o["asset"] // 6
                )
                risk = sum(p["lots"] * p["risk"] for p in positions)
                reserved = sum(p["lots"] * p["fee"] * stress for p in positions)
                lots = max(
                    0,
                    min(
                        5,
                        int(capital * limits["risk_fraction"] / o["risk"]),
                        int(max(0, cash - reserved) / o["risk"]),
                        int(
                            max(0, capital * limits["gross_fraction"] - gross)
                            / o["exposure"]
                        ),
                        int(capital * limits["asset_fraction"] / o["exposure"]),
                        int(
                            max(
                                0,
                                capital
                                * limits["factor_fraction"]
                                - factor,
                            )
                            / o["exposure"]
                        ),
                        int(
                            max(
                                0,
                                capital
                                * limits["open_risk_fraction"]
                                - risk,
                            )
                            / o["risk"]
                        ),
                        int(world.depth[i, o["asset"]]),
                    ),
                )
                if lots <= 0:
                    blocked("cash_exposure_or_openrisk")
                    continue
                unit, g, s = world.value(o, i, stress, scenario)
                current_exposure = abs(g["delta"]) * s * (
                    100 if o["kind"] == "option" else 1
                )
                # Admission uses post-fill equity, including immediate execution
                # costs. Recompute it after every fill, never reuse pre-order NAV.
                while lots > 0:
                    projected_nav = nav + lots * (unit - o["funding"])
                    projected_capital = max(0.0, min(initial, projected_nav))
                    admissible = (
                        projected_nav > 0
                        and cash - lots * o["funding"] + 1e-8
                        >= reserved + lots * o["fee"] * stress
                        and lots * o["risk"]
                        <= projected_capital * limits["risk_fraction"] + 1e-8
                        and risk + lots * o["risk"]
                        <= projected_capital * limits["open_risk_fraction"] + 1e-8
                        and gross + lots * current_exposure
                        <= projected_capital * limits["gross_fraction"] + 1e-8
                        and lots * current_exposure
                        <= projected_capital * limits["asset_fraction"] + 1e-8
                        and factor + lots * current_exposure
                        <= projected_capital * limits["factor_fraction"] + 1e-8
                    )
                    if admissible:
                        break
                    lots -= 1
                if lots == 0:
                    blocked("post_fill_equity_limit")
                    continue
                cash -= lots * o["funding"]
                nav = projected_nav
                o.update(
                    position_id=f"SYNTH-{world.seed}-{i}-{o['asset']}-{int(o['call'])}-{o['kind']}",
                    instrument=dict(
                        symbol=f"SYNTH{o['asset']:02}",
                        kind=o["kind"],
                        multiplier=100 if o["kind"] == "option" else 1,
                        strike=o["strike"] if o["kind"] == "option" else None,
                        call=o["call"] if o["kind"] == "option" else None,
                        dte=o["dte"] if o["kind"] == "option" else None,
                    ),
                    lots=lots,
                    marked=unit,
                    exposure=current_exposure,
                )
                positions.append(o)
                ledger.append(
                    dict(
                        at=at.isoformat(),
                        kind="ENTRY",
                        position_id=o["position_id"],
                        instrument=o["instrument"],
                        gross_cash_change=-lots * (o["funding"] - o["fee"] * stress),
                        fees_usd=lots * o["fee"] * stress,
                        cash_change=-lots * o["funding"],
                        lots=lots,
                        asset=o["asset"],
                        risk=lots * o["risk"],
                    )
                )
        nav = cash + sum(p["lots"] * p["marked"] for p in positions)
        previous = nav
        daily[date] = nav
        ledger.append(snapshot(at, "NAV"))
    if positions:
        raise ValueError("OPEN_POSITIONS_AT_EVALUATION_END")
    dates = []
    values = []
    d = datetime.fromisoformat(start).date()
    stop = datetime.fromisoformat(end).date()
    last = initial
    while d <= stop:
        day = d.isoformat()
        last = daily.get(day, last)
        dates.append(day)
        values.append(last)
        d += timedelta(days=1)
    returns = (np.array(values) / np.array([initial, *values[:-1]]) - 1).tolist()
    metrics = report(
        dict(
            origin=ORIGIN,
            return_basis="NET_FLOW_ADJUSTED",
            returns=returns,
            times=[d + "T23:59:59+00:00" for d in dates],
            initial_equity=initial,
            periods_per_year=365,
            sampling="DAILY_UTC_CALENDAR",
            trades=trades,
        )
    )
    reconciliation = reconcile_events(ledger, initial)
    if (
        abs(sum(t["net_pnl_usd"] for t in trades) - (values[-1] - initial)) >= 1e-7
        or abs(reconciliation["realized_net_pnl"] - (values[-1] - initial)) >= 1e-7
        or reconciliation["open_inventory"]
    ):
        raise ValueError("ECONOMIC_CASH_PNL_RECONCILIATION")
    observed_levels = np.array(
        [initial, *[e["nav"] for e in ledger if e["kind"] in {"PRE_NAV", "NAV"}]]
    )
    observed_dd = 1 - observed_levels / np.maximum.accumulate(observed_levels)
    return dict(
        metrics=metrics,
        mean_log_growth=float(np.log1p(returns).mean()),
        dates=dates,
        returns=returns,
        trades=trades,
        blocks=blocks,
        ledger=ledger,
        ledger_schema="HARPOON_CASH_EVENTS_1",
        reconciliation=reconciliation,
        risk_breaches=risk_breaches,
        risk_metrics=dict(
            max_drawdown_daily=metrics["max_drawdown"],
            max_drawdown_all_observed_marks=float(np.max(observed_dd)),
            observation_count=len(observed_levels) - 1,
            scope="Synthetic observed marks only; gaps can exceed caps before an exit",
        ),
        effective_limits=limits,
        policy=asdict(policy),
        risk_paused=risk_paused,
        origin=ORIGIN,
        execution_allowed=False,
    )


def run_stage(directory: Path, stage: str) -> None:
    protocol = json.loads((directory / "protocol.json").read_text())
    calendar = json.loads(
        (directory.parent / "evidence/alpaca_calendar.json").read_text()
    )
    j = Journal(directory / "optimizer.sqlite3")
    now = datetime.now(UTC).isoformat()
    try:
        seal = hashlib.sha256(
            b"".join(
                (Path(__file__).parent / n).read_bytes()
                for n in ["economic_lab.py", "performance.py", "recursive.py"]
            )
        ).hexdigest()
        if (
            hashlib.sha256((directory / "protocol.json").read_bytes()).hexdigest()
            != j.get("economic:protocol")["hash"]
        ):
            raise ValueError("REGISTERED_PROTOCOL_CHANGED")
        if (
            hashlib.sha256(
                (directory.parent / "evidence/alpaca_calendar.json").read_bytes()
            ).hexdigest()
            != protocol["calendar_file_sha256"]
        ):
            raise ValueError("REGISTERED_CALENDAR_CHANGED")
        with j.transaction():
            code = j.get("economic:implementation")
            if code and code["hash"] != seal:
                raise ValueError("REGISTERED_CODE_CHANGED")
            if not code:
                j.put("economic:implementation", dict(hash=seal), now)
        if stage == "develop":
            if j.get("economic:finalist"):
                raise ValueError("FINALIST_ALREADY_FROZEN")
            development = {}
            worlds = [World(calendar, seed) for seed in protocol["development_seeds"]]
            for name, flags in protocol["variants"].items():
                with j.transaction():
                    if j.get("economic:trial:" + name):
                        raise ValueError("TRIAL_ALREADY_USED")
                    budget = j.get("budget")
                    if budget["spent"] >= budget["limit"]:
                        raise ValueError("LIFETIME_BUDGET_EXHAUSTED")
                    budget["spent"] += 1
                    j.put("budget", budget, now)
                    j.put(
                        "economic:trial:" + name,
                        dict(stage="RESERVED", code_hash=seal),
                        now,
                    )
                runs = [
                    replay(
                        w,
                        Policy("".join(flags)),
                        "2024-07-01",
                        protocol["development_end"],
                        dict(protocol["limits"], capital=protocol["capital"]),
                    )
                    for w in worlds
                ]
                admissible = all(
                    r["metrics"]["max_drawdown"] <= protocol["limits"]["max_drawdown"]
                    and r["metrics"]["trade_count"] >= 20
                    for r in runs
                )
                score = min(r["mean_log_growth"] for r in runs) if admissible else -1e6
                row = dict(score=score, admissible=admissible, runs=runs)
                development[name] = row
                with j.transaction():
                    j.put(
                        "economic:trial:" + name,
                        dict(
                            stage="COMPLETE",
                            code_hash=seal,
                            score=score,
                            admissible=admissible,
                        ),
                        now,
                    )
            candidates = [
                k for k, v in development.items() if k != "BASE" and v["admissible"]
            ]
            chosen = (
                max(candidates, key=lambda k: development[k]["score"])
                if candidates
                else "BASE"
            )
            frozen = dict(
                name=chosen,
                flags=protocol["variants"][chosen],
                code_hash=seal,
                protocol_hash=hashlib.sha256(
                    (directory / "protocol.json").read_bytes()
                ).hexdigest(),
                at=now,
                admissible=bool(candidates),
                score=development[chosen]["score"],
            )
            (directory / "development.json").write_text(
                json.dumps(development, allow_nan=False)
            )
            (directory / "finalist.json").write_text(json.dumps(frozen, indent=2))
            with j.transaction():
                j.put("economic:finalist", frozen, now)
            print(json.dumps(dict(status="FROZEN", **frozen)))
        elif stage == "holdout":
            frozen = j.get("economic:finalist")
            if not frozen or frozen["code_hash"] != seal:
                raise ValueError("FROZEN_CODE_REQUIRED")
            with j.transaction():
                if j.get("economic:holdout"):
                    raise ValueError("HOLDOUT_ALREADY_SPENT")
                domain = digest({"account": "SYNTH_48_OPTIONS", "origin": ORIGIN})
                lo, hi = protocol["holdout_start"], protocol["holdout_end"]
                if j.db.execute(
                    "SELECT 1 FROM optimizer_holdouts WHERE domain=? AND NOT(hi<? OR lo>?)",
                    (domain, lo, hi),
                ).fetchone():
                    raise ValueError("HOLDOUT_INTERVAL_ALREADY_USED")
                j.db.execute(
                    "INSERT INTO optimizer_holdouts VALUES(?,?,?,?)",
                    (lo, hi, domain, protocol["study_id"]),
                )
                j.put("economic:holdout", dict(stage="RESERVED", finalist=frozen), now)
            results = []
            for seed in protocol["holdout_seeds"]:
                w = World(calendar, seed)
                hold_runs: dict[str, Any] = {}
                for name, policy, stress, scenario in [
                    ("baseline", Policy(), 1.0, "base"),
                    ("candidate", Policy("".join(frozen["flags"])), 1.0, "base"),
                    ("cash", Policy(), 1.0, "base"),
                    ("cost_1_5", Policy("".join(frozen["flags"])), 1.5, "base"),
                    ("cost_2", Policy("".join(frozen["flags"])), 2.0, "base"),
                ] + [
                    (s, Policy("".join(frozen["flags"])), 1.0, s)
                    for s in ["gaps", "iv_crush", "liquidity", "delay", "outage"]
                ]:
                    if name == "cash":
                        continue
                    hold_runs[name] = replay(
                        w,
                        policy,
                        protocol["holdout_start"],
                        protocol["holdout_end"],
                        dict(protocol["limits"], capital=protocol["capital"]),
                        stress=stress,
                        scenario=scenario,
                    )
                results.append(dict(seed=seed, runs=hold_runs))
            (directory / "holdout.json").write_text(
                json.dumps(dict(finalist=frozen, results=results), allow_nan=False)
            )
            with j.transaction():
                j.put(
                    "economic:holdout",
                    dict(
                        stage="COMPLETE",
                        result_hash=hashlib.sha256(
                            (directory / "holdout.json").read_bytes()
                        ).hexdigest(),
                        execution_allowed=False,
                    ),
                    datetime.now(UTC).isoformat(),
                )
            print(
                json.dumps(
                    dict(
                        status="HOLDOUT_COMPLETE",
                        paths=len(results),
                        execution_allowed=False,
                    )
                )
            )
    finally:
        j.close()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stage", choices=["develop", "holdout"])
    p.add_argument("--directory", type=Path, required=True)
    a = p.parse_args()
    run_stage(a.directory, a.stage)


if __name__ == "__main__":
    main()
