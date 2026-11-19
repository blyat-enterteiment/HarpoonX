"""Funded long-only research portfolio. All executions here are modeled IOC.

This module has no broker adapter, authenticated fill flag, or order endpoint.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from contextlib import closing
import copy
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from typing import Any

import numpy as np
from scipy.optimize import minimize

from research.hf37.hf37_predictor import Array, DAY_NS, Forecast, Quote


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


@dataclass(frozen=True)
class Costs:
    fee_bps: float = 1.0
    impact_bps: float = 2.0
    gap_buffer_bps: float = 5.0

    def validate(self) -> None:
        if not all(math.isfinite(v) and 0 <= v < 1000 for v in asdict(self).values()):
            raise ValueError("INVALID_COSTS")

    def sale(self, quote: Quote) -> float:
        return quote.bid * (1 - self.impact_bps / 10_000) * (1 - self.fee_bps / 10_000)

    def roundtrip(self, quote: Quote) -> float:
        entry = quote.ask * (1 + self.impact_bps / 10_000) * (1 + self.fee_bps / 10_000)
        return entry / self.sale(quote) - 1 + self.gap_buffer_bps / 10_000


@dataclass(frozen=True)
class Risk:
    max_asset: float = 0.12
    max_sector: float = 0.25
    max_gross: float = 0.60
    daily_loss_halt: float = 0.02
    drawdown_halt: float = 0.10
    risk_aversion: float = 10.0
    max_hold_ns: int = 3 * DAY_NS
    quote_participation: float = 0.10
    max_quote_age_ns: int = 2_000_000_000

    def validate(self) -> None:
        if not all(math.isfinite(v) for v in asdict(self).values()):
            raise ValueError("NONFINITE_RISK_CONFIGURATION")
        if self.max_quote_age_ns <= 0:
            raise ValueError("INVALID_QUOTE_AGE_LIMIT")
        if not (0 < self.max_asset <= self.max_sector <= self.max_gross < 1):
            raise ValueError("INVALID_EXPOSURE_LIMITS")
        if not (0 < self.daily_loss_halt <= self.drawdown_halt < 1):
            raise ValueError("INVALID_HALT_LIMITS")
        if not 0 < self.max_hold_ns <= 3 * DAY_NS or self.risk_aversion <= 0:
            raise ValueError("INVALID_HORIZON_OR_RISK_AVERSION")
        if not 0 < self.quote_participation <= 1:
            raise ValueError("INVALID_PARTICIPATION")


@dataclass
class Position:
    quantity: int
    opened_ns: int
    high_bid: float


@dataclass
class ModeledBook:
    cash: float = 20_000.0
    positions: dict[str, Position] = field(default_factory=dict)
    peak: float = 20_000.0
    previous_close: float = 20_000.0
    permanently_halted: bool = False
    fees: float = 0.0
    turnover: float = 0.0
    receipts: list[dict[str, Any]] = field(default_factory=list)
    applied: dict[str, str] = field(default_factory=dict)
    hold_breaches: int = 0

    def wealth(self, quotes: dict[str, Quote], costs: Costs, clock_ns: int) -> float:
        costs.validate()
        total = self.cash
        for symbol, p in self.positions.items():
            q = quotes[symbol]
            q.validate()
            if q.known_ns > clock_ns:
                raise ValueError("FUTURE_LIQUIDATION_MARK")
            total += p.quantity * costs.sale(q)
        if not math.isfinite(total) or total <= 0:
            raise ValueError("NONPOSITIVE_WEALTH")
        return total

    def snapshot(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def restore(cls, state: dict[str, Any]) -> ModeledBook:
        obj = copy.deepcopy(state)
        obj["positions"] = {s: Position(**p) for s, p in obj["positions"].items()}
        book = cls(**obj)
        if (
            not math.isfinite(book.cash)
            or book.cash < 0
            or any(p.quantity <= 0 or p.opened_ns <= 0 for p in book.positions.values())
        ):
            raise ValueError("INVALID_PERSISTED_BOOK")
        return book

    def rebalance(
        self,
        event_id: str,
        decision_ns: int,
        execution_quotes: dict[str, Quote],
        targets: dict[str, float],
        costs: Costs,
        risk: Risk,
    ) -> None:
        """Model one IOC per symbol at a strictly post-decision quote.

        Remainders are canceled in this explicit model; they are never broker
        receipts. Failed validation leaves every account field unchanged.
        """
        costs.validate()
        risk.validate()
        payload_hash = digest(
            [
                decision_ns,
                {s: asdict(q) for s, q in execution_quotes.items()},
                targets,
                asdict(costs),
                asdict(risk),
            ]
        )
        if event_id in self.applied:
            if self.applied[event_id] != payload_hash:
                raise ValueError("CONFLICTING_REPLAY")
            return
        for symbol, q in execution_quotes.items():
            q.validate()
            if q.at_ns <= decision_ns or q.known_ns < q.at_ns:
                raise ValueError("EXECUTION_NOT_AFTER_DECISION")
        if (
            any(
                not math.isfinite(w) or not 0 <= w <= risk.max_asset + 1e-8
                for w in targets.values()
            )
            or sum(targets.values()) > risk.max_gross + 1e-7
        ):
            raise ValueError("INVALID_TARGET_WEIGHTS")
        if (set(targets) | set(self.positions)) - set(execution_quotes):
            raise ValueError("MISSING_EXECUTION_QUOTE")
        draft = copy.deepcopy(self)
        stamp = max(
            (q.known_ns for q in execution_quotes.values()), default=decision_ns
        )
        wealth = draft.wealth(execution_quotes, costs, stamp)
        desired = {
            s: int(targets.get(s, 0) * wealth / costs.sale(q) + 1e-9)
            for s, q in execution_quotes.items()
        }
        breached = {
            s
            for s, p in draft.positions.items()
            if execution_quotes[s].at_ns - p.opened_ns > risk.max_hold_ns
        }
        # Sell before buying; new buys use only cash actually left by modeled IOC.
        for side in ("SELL", "BUY"):
            if side == "BUY":
                breached.update(
                    s
                    for s, p in draft.positions.items()
                    if execution_quotes[s].at_ns - p.opened_ns >= risk.max_hold_ns
                )
                draft.permanently_halted |= bool(breached)
                if draft.permanently_halted:
                    continue
            for symbol in sorted(desired):
                q = execution_quotes[symbol]
                previous = draft.positions.get(symbol)
                owned = previous.quantity if previous else 0
                gap = desired[symbol] - owned
                requested = -gap if side == "SELL" else gap
                if requested <= 0:
                    continue
                depth = q.bid_size if side == "SELL" else q.ask_size
                qty = min(requested, math.floor(depth * risk.quote_participation))
                price = (
                    q.bid * (1 - costs.impact_bps / 10_000)
                    if side == "SELL"
                    else q.ask * (1 + costs.impact_bps / 10_000)
                )
                if side == "BUY":
                    spendable = max(0.0, draft.cash - wealth * (1 - risk.max_gross))
                    qty = min(
                        qty, int(spendable / (price * (1 + costs.fee_bps / 10_000)))
                    )
                if qty <= 0:
                    continue
                fee = qty * price * costs.fee_bps / 10_000
                if side == "SELL":
                    assert previous is not None
                    draft.cash += qty * price - fee
                    previous.quantity -= qty
                    if not previous.quantity:
                        del draft.positions[symbol]
                else:
                    draft.cash -= qty * price + fee
                    if previous:
                        previous.quantity += qty  # Oldest clock remains unchanged.
                    else:
                        draft.positions[symbol] = Position(qty, q.at_ns, q.bid)
                draft.fees += fee
                draft.turnover += qty * price
                draft.receipts.append(
                    {
                        "event_id": event_id,
                        "symbol": symbol,
                        "side": side,
                        "quantity": qty,
                        "price": price,
                        "fee": fee,
                        "at_ns": q.at_ns,
                        "kind": "MODELED_IOC_NOT_BROKER_FILL",
                        "requested": requested,
                    }
                )
        if draft.cash < -1e-8 or not math.isfinite(draft.cash):
            raise ValueError("CASH_INVARIANT")
        breached.update(
            s
            for s, p in draft.positions.items()
            if execution_quotes[s].at_ns - p.opened_ns >= risk.max_hold_ns
        )
        draft.hold_breaches += len(breached)
        draft.permanently_halted |= bool(breached)
        draft.applied[event_id] = payload_hash
        self.__dict__.update(draft.__dict__)


def target_weights(
    symbols: list[str],
    sectors: dict[str, str],
    forecasts: dict[str, Forecast],
    quotes: dict[str, Quote],
    covariance: Array,
    book: ModeledBook,
    decision_ns: int,
    costs: Costs,
    risk: Risk,
    stock_etf: dict[str, str],
    *,
    sector_only: bool = False,
) -> tuple[dict[str, float], dict[str, Any]]:
    risk.validate()
    costs.validate()
    if len(set(symbols)) != len(symbols) or covariance.shape != (
        len(symbols),
        len(symbols),
    ):
        raise ValueError("INVALID_PORTFOLIO_DIMENSIONS")
    if not np.isfinite(covariance).all() or not np.allclose(covariance, covariance.T):
        raise ValueError("INVALID_COVARIANCE")
    if float(np.linalg.eigvalsh(covariance).min()) < -1e-10:
        raise ValueError("NON_PSD_COVARIANCE")
    for q in quotes.values():
        q.validate()
        if q.known_ns > decision_ns:
            raise ValueError("NONCAUSAL_ALLOCATION_QUOTE")
        if decision_ns - q.at_ns > risk.max_quote_age_ns:
            raise ValueError("STALE_ALLOCATION_QUOTE")
    wealth = book.wealth(quotes, costs, decision_ns)
    book.peak = max(book.peak, wealth)
    dd = 1 - wealth / book.peak
    day_loss = 1 - wealth / book.previous_close
    book.permanently_halted |= dd >= risk.drawdown_halt
    halt = book.permanently_halted or day_loss >= risk.daily_loss_halt
    lower = np.zeros(len(symbols))
    upper = np.zeros(len(symbols))
    utility = np.zeros(len(symbols))
    rejected = retained = 0
    for i, symbol in enumerate(symbols):
        f, q = forecasts[symbol], quotes[symbol]
        p = book.positions.get(symbol)
        if p:
            p.high_bid = max(p.high_bid, q.bid)
        trailing = p is not None and q.bid < p.high_bid * (
            1 - max(0.02, min(0.10, 2 * math.sqrt(f.variance)))
        )
        expired = (
            p is not None
            and decision_ns + 1_000_000_000 - p.opened_ns >= risk.max_hold_ns
        )
        forced = halt or trailing or expired or not f.available
        net = f.lower - costs.roundtrip(q)
        # Compare a stock's complete-cost hurdle against its cheaper sector ETF.
        alternative = 0.0
        if symbol in stock_etf:
            etf = stock_etf[symbol]
            ef = forecasts[etf]
            alternative = (
                max(0.0, ef.upper - costs.roundtrip(quotes[etf])) if ef.available else 0
            )
        entry = (
            not forced
            and net > alternative
            and (not sector_only or symbol not in stock_etf)
        )
        continuation = p is not None and not forced and f.lower > alternative
        if continuation and p:
            lower[i] = min(risk.max_asset, p.quantity * costs.sale(q) / wealth)
            retained += 1
        upper[i] = risk.max_asset if entry else lower[i]
        utility[i] = net if entry else f.lower if continuation else 0
        rejected += int(not entry)
    # Existing drift or concentration is trimmed; no constraint is silently relaxed.
    if lower.sum() > risk.max_gross:
        lower *= risk.max_gross / lower.sum()
    for sector in sorted(set(sectors.values())):
        indices = [i for i, s in enumerate(symbols) if sectors[s] == sector]
        if lower[indices].sum() > risk.max_sector:
            lower[indices] *= risk.max_sector / lower[indices].sum()
    upper = np.maximum(upper, lower)
    constraints: list[dict[str, Any]] = [
        {"type": "ineq", "fun": lambda w: risk.max_gross - float(np.sum(w))}
    ]
    for sector in sorted(set(sectors.values())):
        indices = np.array([i for i, s in enumerate(symbols) if sectors[s] == sector])
        constraints.append(
            {
                "type": "ineq",
                "fun": lambda w, ix=indices: risk.max_sector - float(w[ix].sum()),
            }
        )

    def objective(w: Array) -> float:
        return float(0.5 * risk.risk_aversion * (w @ covariance @ w) - utility @ w)

    def gradient(w: Array) -> Array:
        return risk.risk_aversion * covariance @ w - utility

    if not upper.any():
        weights, success = lower, True
    else:
        solution = minimize(
            objective,
            lower,
            jac=gradient,
            method="SLSQP",
            bounds=list(zip(lower, upper)),
            constraints=constraints,
            options={"ftol": 1e-11, "maxiter": 200},
        )
        weights, success = (solution.x, True) if solution.success else (lower, False)
    if (weights < -1e-8).any() or weights.sum() > risk.max_gross + 1e-7:
        raise ValueError("OPTIMIZER_EXPOSURE_INVARIANT")
    for sector in set(sectors.values()):
        if (
            sum(weights[i] for i, s in enumerate(symbols) if sectors[s] == sector)
            > risk.max_sector + 1e-7
        ):
            raise ValueError("OPTIMIZER_SECTOR_INVARIANT")
    return {s: max(0.0, float(weights[i])) for i, s in enumerate(symbols)}, {
        "optimizer_converged": success,
        "rejected_new_entries": rejected,
        "retained_positions": retained,
        "drawdown": dd,
        "daily_loss": day_loss,
        "risk_halt": halt,
        "gross_target": float(weights.sum()),
    }


class CheckpointStore:
    """Transactional CAS checkpoints and a hash chain; no credentials in state."""

    def __init__(self, path: Path, config_hash: str) -> None:
        self.path, self.config_hash = path, config_hash
        with closing(sqlite3.connect(path)) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS checkpoint (run TEXT PRIMARY KEY, step INTEGER, config TEXT, payload TEXT, hash TEXT)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS journal (run TEXT, step INTEGER, input_hash TEXT, state_hash TEXT, previous_hash TEXT, chain_hash TEXT, PRIMARY KEY(run,step))"
            )

    def load(self, run: str) -> tuple[int, dict[str, Any]] | None:
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute(
                "SELECT step,config,payload,hash FROM checkpoint WHERE run=?", (run,)
            ).fetchone()
            journal = db.execute(
                "SELECT step,input_hash,state_hash,previous_hash,chain_hash FROM journal WHERE run=? ORDER BY step",
                (run,),
            ).fetchall()
        if row is None:
            return None
        if (
            row[1] != self.config_hash
            or hashlib.sha256(row[2].encode()).hexdigest() != row[3]
        ):
            raise ValueError("CHECKPOINT_CONFIG_OR_HASH_MISMATCH")
        previous_hash = "0" * 64
        for step, item in enumerate(journal):
            if (
                item[0] != step
                or item[3] != previous_hash
                or item[4] != digest([previous_hash, item[1], item[2]])
            ):
                raise ValueError("CHECKPOINT_JOURNAL_HASH_MISMATCH")
            previous_hash = item[4]
        if not journal or journal[-1][0] != row[0] or journal[-1][2] != row[3]:
            raise ValueError("CHECKPOINT_JOURNAL_HEAD_MISMATCH")
        return int(row[0]), json.loads(row[2])

    def save(
        self,
        run: str,
        step: int,
        expected_previous: int,
        inputs: Any,
        state: dict[str, Any],
    ) -> None:
        payload, ih = canonical(state), digest(inputs)
        sh = hashlib.sha256(payload.encode()).hexdigest()
        with closing(sqlite3.connect(self.path, isolation_level=None)) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT step,config,hash FROM checkpoint WHERE run=?", (run,)
            ).fetchone()
            if row is not None and row[1] != self.config_hash:
                raise ValueError("CHECKPOINT_CONFIGURATION_CONFLICT")
            if row is not None and row[0] == step:
                prior = db.execute(
                    "SELECT input_hash,state_hash FROM journal WHERE run=? AND step=?",
                    (run, step),
                ).fetchone()
                if prior != (ih, sh):
                    raise ValueError("CHECKPOINT_REPLAY_CONFLICT")
                db.commit()
                return
            previous = row[0] if row is not None else -1
            if previous != expected_previous or step != previous + 1:
                raise ValueError("CHECKPOINT_LEASE_CONFLICT")
            previous_event = db.execute(
                "SELECT chain_hash FROM journal WHERE run=? ORDER BY step DESC LIMIT 1",
                (run,),
            ).fetchone()
            previous_hash = previous_event[0] if previous_event else "0" * 64
            chain_hash = digest([previous_hash, ih, sh])
            db.execute(
                "INSERT INTO journal VALUES (?,?,?,?,?,?)",
                (run, step, ih, sh, previous_hash, chain_hash),
            )
            db.execute(
                "INSERT INTO checkpoint VALUES (?,?,?,?,?) ON CONFLICT(run) DO UPDATE SET step=excluded.step,config=excluded.config,payload=excluded.payload,hash=excluded.hash",
                (run, step, self.config_hash, payload, sh),
            )
            db.commit()
