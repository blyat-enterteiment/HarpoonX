"""Continuous-account synthetic prequential evaluation of the existing shadow core."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np

from ..core import digest, timestamp
from ..frontier.assurance import assure
from ..frontier.contracts import Settings, require
from ..frontier.paths import fit
from ..frontier.supervisor import expiry_step
from ..frontier_core import shadow
from . import ORIGIN
from .events import link
from .execution import event, simulate_order
from .ledger import EPS, Ledger
from .market import FEATURES, LOTS, SYMBOLS, WORLDS, available, ms, quotes, schedule

SCENARIOS = {
    "NOMINAL": (1.0, 0.0),
    "DOUBLE_COST": (2.0, 0.0),
    "DOUBLE_COST_GAP": (2.0, 0.005),
}


def iso(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, UTC).isoformat()


def state_for(
    ledger: Ledger,
    case: dict[str, Any],
    calibration: dict[str, Any],
    multiplier: float,
    version: int,
    binding: str,
) -> dict[str, Any]:
    now = ms(case["start_at"])
    bbo = quotes(case, 0, multiplier=multiplier)
    assets = []
    for j, symbol in enumerate(SYMBOLS):
        q = bbo[symbol]
        quantity = ledger.quantity(symbol)
        unit = LOTS[j]
        if quantity > EPS:
            unit = (
                math.gcd(round(quantity * 100_000_000), round(unit * 100_000_000))
                / 100_000_000
            )
        slippage = max(
            calibration["groups"][symbol + ":" + side]["q95_bps"]
            for side in ("buy", "sell")
        )
        asset = {
            "symbol": symbol,
            "book": "crypto" if j >= 2 else "equity",
            "factor": "CRYPTO" if j >= 2 else "TECH",
            "bid": q["bid"],
            "ask": q["ask"],
            "quote_at": iso(now),
            "quote_received_at": iso(now),
            "status_known_at": iso(now),
            "tradable_now": True,
            "halted": False,
            "quote_origin": "MODELED_FROM_BAR",
            "available_buy_qty": LOTS[j],
            "available_sell_qty": quantity,
            "lot_qty": unit,
            "current_lots": round(quantity / unit),
            "max_new_lots": 0 if quantity > EPS else 1,
            "fee_bps": 2 * multiplier,
            "slippage_bps": slippage * multiplier,
            "fixed_order_fee_usd": 0.01 * multiplier,
            "cost_origin": "ASSUMED",
            "schedule": schedule(j),
            "schedule_known_at": iso(now),
            "schedule_source_hash": digest({"synthetic_calendar": schedule(j)}),
        }
        if quantity > EPS:
            p = ledger.positions[symbol]
            asset.update(
                campaign_id=p["campaign_id"],
                opened_at=iso(p["opened_at"]),
                deadline=iso(p["deadline_at"]),
                stop_price=p["stop_price"],
                target_price=p["target_price"],
            )
        assets.append(asset)
    equity = ledger.cash + sum(ledger.quantity(s) * q["bid"] for s, q in bbo.items())
    peak = max([ledger.initial, equity] + [r["equity_usd"] for r in ledger.curve])
    return {
        "schema": "HARPOON_FRONTIER_STATE_1",
        "origin": ORIGIN,
        "asof": iso(now),
        "known_at": iso(now),
        "currency": "USD",
        "account_binding": binding,
        "version": version,
        "inventory_complete": True,
        "cash_usd": ledger.cash,
        "pending_cash_usd": ledger.reserved(),
        "receivables_usd": 0.0,
        "daily_pnl_usd": 0.0,
        "drawdown_fraction": max(0.0, 1 - equity / peak),
        "assets": assets,
        "features": case["features"],
        "feature_names": FEATURES,
        "features_known_at": case["features_known_at"],
        "evaluation_hours": 72,
    }


def metrics(report: dict[str, Any], initial: float) -> dict[str, Any]:
    curve = report["curve"]
    wealth = np.array([initial] + [r["equity_usd"] for r in curve])
    peak = np.maximum.accumulate(wealth)
    last = float(wealth[-1])
    return {
        "terminal_equity_usd": last,
        "net_pnl_usd": last - initial,
        "net_return": last / initial - 1,
        "terminal_log_growth": float(np.log(last / initial)) if last > 0 else None,
        "max_drawdown": float(np.max(1 - wealth / peak)),
        "fees_usd": report["fees_usd"],
        "overhead_usd": report["overhead_usd"],
        "fill_count": report["fill_count"],
        "filled_order_count": report["filled_order_count"],
        "deadline_breach_count": len(report["deadline_breaches"]),
        "max_hold_hours": report["max_hold_hours"],
        "unresolved_order_count": len(report["unresolved_orders"]),
        "open_position_count": len(report["positions"]),
        "terminal_mark_stale_if_inventory_remains": bool(report["positions"]),
        "account_resets": 0,
        "external_flows_usd": 0,
    }


def run_account(
    dataset: dict[str, Any],
    protocol: dict[str, Any],
    calibration: dict[str, Any],
    *,
    seed: int,
    world_name: str,
    scenario: str,
    strategy: str,
) -> dict[str, Any]:
    require(
        strategy in protocol["strategies"]
        and scenario in SCENARIOS
        and world_name in WORLDS,
        "ACCOUNT_RECIPE",
    )
    multiplier, gap = SCENARIOS[scenario]
    ledger = Ledger(protocol["initial_capital_usd"])
    deliveries: list[dict[str, Any]] = []
    receipts = []
    weekly = []
    blocked: dict[str, int] = {}
    warmup = protocol["warmup_weeks"]
    binding = f"SYN9-{world_name}-{seed}-{scenario}-{strategy}"
    cfg = Settings(overhead_usd_per_day=protocol["overhead_usd_per_day"] * multiplier)

    def record(body: dict[str, Any]) -> None:
        ledger.apply(body)
        deliveries.append(body)

    def execute_batch(orders: list[dict[str, Any]], hour: int, week: int) -> None:
        batch = []
        for order in orders:
            j = SYMBOLS.index(order["symbol"])
            # Policy-independent random numbers for the same world/hour/asset/side.
            rng_seed = int(
                np.random.SeedSequence(
                    [
                        seed,
                        WORLDS.index(world_name),
                        week,
                        hour,
                        j,
                        int(order["side"] == "sell"),
                    ]
                ).generate_state(1)[0]
            )
            batch.extend(
                simulate_order(
                    order,
                    rng_seed,
                    open_market=available(world_name, week, warmup, hour, j),
                    multiplier=multiplier,
                    gap=gap,
                )
            )
        for body in sorted(batch, key=lambda e: (e["at"], e["id"])):
            record(body)

    for week in range(warmup, warmup + protocol["evaluation_weeks"]):
        case = dataset["samples"][week]
        start = ms(case["start_at"])
        bbo = quotes(case, 0, multiplier=multiplier)
        record(event("MARK", binding + f"-{week}-initial", start, quotes=bbo))
        state = state_for(ledger, case, calibration, multiplier, week - warmup, binding)
        receipt = None
        if strategy == "CORE":
            # Current case never enters fitting. No current outcomes enter state_for.
            cutoff = timestamp(case["start_at"]) - timedelta(seconds=1)
            prior = [
                r
                for r in dataset["samples"][:week]
                if timestamp(r["known_at"]) < cutoff
            ][-40:]
            model = fit({**dataset, "samples": prior}, cutoff.isoformat(), cfg)
            receipt = shadow(state, model, cfg)
            if receipt["status"] == "SUPERVISED_RESEARCH_PROPOSAL":
                audit = assure(state, model, receipt, cfg)
                targets = receipt["supervisor"]["targets"]
                actions = receipt["supervisor"]["actions"]
            else:
                blocked[receipt["reason"]] = blocked.get(receipt["reason"], 0) + 1
                audit, targets, actions = (
                    None,
                    [a["current_lots"] for a in state["assets"]],
                    None,
                )
            receipts.append(
                {
                    "decision_at": case["start_at"],
                    "training_ids": [r["id"] for r in prior],
                    "maximum_training_known_at": max(r["known_at"] for r in prior),
                    "calibration_available_at": cutoff.isoformat(),
                    "model_hash": model["model_hash"],
                    "state": state,
                    "settings": vars(cfg),
                    "receipt": receipt,
                    "selected_action_check": audit,
                }
            )
        else:
            targets = [
                0 if strategy == "CASH" else max(a["current_lots"], 1)
                for a in state["assets"]
            ]
            actions = None
        decision_id = binding + f"-{week}-entry-decision"
        record(
            event(
                "DECISION",
                decision_id,
                start,
                decision_id=decision_id,
                quotes=bbo,
                core_receipt_hash=receipt["receipt_hash"] if receipt else None,
                state_hash=digest(state),
            )
        )
        orders = []
        for j, (asset, target) in enumerate(zip(state["assets"], targets, strict=True)):
            delta = target * asset["lot_qty"] - ledger.quantity(asset["symbol"])
            if abs(delta) <= EPS:
                continue
            side = "buy" if delta > 0 else "sell"
            symbol, q = asset["symbol"], bbo[asset["symbol"]]
            step = (
                actions[j]["expiry_step"]
                if actions and side == "buy"
                else expiry_step(asset, state["asof"], new=True)
            )
            mid = (q["bid"] + q["ask"]) / 2
            oid = decision_id + "-" + str(j)
            orders.append(
                event(
                    "SUBMIT",
                    oid,
                    start + 10 + j * 10,
                    order_id=oid,
                    decision_id=decision_id,
                    symbol=symbol,
                    book=asset["book"],
                    side=side,
                    qty=round(abs(delta), 8),
                    decision_bid=q["bid"],
                    decision_ask=q["ask"],
                    limit_price=q["ask"] * 1.05 if side == "buy" else None,
                    fee_bps=2 * multiplier,
                    fixed_fee_usd=0.01 * multiplier,
                    campaign_id=oid,
                    deadline_at=start + step * 3_600_000,
                    stop_price=mid * 0.98,
                    target_price=mid * 1.03,
                )
            )
        execute_batch(orders, 0, week)
        record(
            event("MARK", binding + f"-{week}-after-entry", start + 10_000, quotes=bbo)
        )
        for hour in range(1, 73):
            now = start + hour * 3_600_000
            bbo = quotes(case, hour, multiplier=multiplier)
            if any(ledger.quantity(s) > EPS for s in SYMBOLS) or hour % 24 == 0:
                record(
                    event("MARK", binding + f"-{week}-{hour}-before", now, quotes=bbo)
                )
            exit_orders = []
            did = binding + f"-{week}-{hour}-protective"
            for j, symbol in enumerate(SYMBOLS):
                if ledger.quantity(symbol) <= EPS or not available(
                    world_name, week, warmup, hour, j
                ):
                    continue
                p = ledger.positions[symbol]
                bar = [v * case["entry_prices"][j] for v in case["ohlc"][j][hour - 1]]
                q = bbo[symbol]
                reason = (
                    "STOP_OR_AMBIGUOUS"
                    if q["bid"] <= p["stop_price"] or bar[2] <= p["stop_price"]
                    else "TARGET_TRIGGER"
                    if q["bid"] >= p["target_price"] or bar[1] >= p["target_price"]
                    else "TIME_BUFFER_1H"
                    if now >= p["deadline_at"] - 3_600_000
                    else None
                )
                if reason is None:
                    continue
                oid = did + "-" + str(j)
                exit_orders.append(
                    event(
                        "SUBMIT",
                        oid,
                        now + 10 + j * 10,
                        order_id=oid,
                        decision_id=did,
                        symbol=symbol,
                        book="crypto" if j >= 2 else "equity",
                        side="sell",
                        qty=ledger.quantity(symbol),
                        decision_bid=q["bid"],
                        decision_ask=q["ask"],
                        limit_price=None,
                        fee_bps=2 * multiplier,
                        fixed_fee_usd=0.01 * multiplier,
                        campaign_id=p["campaign_id"],
                        deadline_at=p["deadline_at"],
                        reason=reason,
                    )
                )
            if exit_orders:
                record(
                    event(
                        "DECISION",
                        did,
                        now,
                        decision_id=did,
                        quotes=bbo,
                        core_receipt_hash=None,
                        state_hash=digest(ledger.report()),
                    )
                )
                execute_batch(exit_orders, hour, week)
            if hour % 24 == 0:
                record(
                    event(
                        "OVERHEAD",
                        binding + f"-{week}-{hour}-overhead",
                        now + 5000,
                        usd=cfg.overhead_usd_per_day,
                    )
                )
            if (
                exit_orders
                or any(ledger.quantity(s) > EPS for s in SYMBOLS)
                or hour % 24 == 0
            ):
                record(
                    event(
                        "MARK",
                        binding + f"-{week}-{hour}-after",
                        now + 10_000,
                        quotes=bbo,
                    )
                )
        # Four remaining calendar days accrue common expense; no invented trades/quotes.
        end = start + 7 * 24 * 3_600_000 - 1
        record(
            event(
                "OVERHEAD",
                binding + f"-{week}-outside-overhead",
                end - 1,
                usd=4 * cfg.overhead_usd_per_day,
            )
        )
        record(
            event(
                "MARK",
                binding + f"-{week}-week-end-carried",
                end,
                quotes=bbo,
                carried_from=start + 72 * 3_600_000,
            )
        )
        weekly.append(ledger.curve[-1])
    report = ledger.report()
    fill_stats = {}
    for symbol in SYMBOLS:
        rows = [r for r in ledger.fills if r["symbol"] == symbol]
        fill_stats[symbol] = {
            "fills": len(rows),
            "mean_total_shortfall_bps": float(
                np.mean([r["shortfall_including_fee_bps"] for r in rows])
            )
            if rows
            else None,
            "fraction_below_synthetic_training_q95": float(
                np.mean(
                    [
                        r["residual_slippage_bps"]
                        <= calibration["groups"][symbol + ":" + r["side"]]["q95_bps"]
                        for r in rows
                    ]
                )
            )
            if rows
            else None,
        }
    requested = sum(
        o["qty"] * (o["decision_bid"] + o["decision_ask"]) / 2
        for o in ledger.orders.values()
    )
    filled = sum(
        o["filled"] * (o["decision_bid"] + o["decision_ask"]) / 2
        for o in ledger.orders.values()
    )
    return {
        "schema": "HARPOON_SYNTHETIC_ACCOUNT_1",
        "origin": ORIGIN,
        "strategy": strategy,
        "world": world_name,
        "seed": seed,
        "cost_scenario": scenario,
        "initial_cash_usd": ledger.initial,
        "continuous_capital": True,
        "ledger": report,
        "weekly": weekly,
        "metrics": metrics(report, ledger.initial),
        "blocked_core_decisions": blocked,
        "core_receipts": receipts,
        "execution_diagnostics": {
            "per_asset": fill_stats,
            "requested_mid_notional_usd": requested,
            "filled_mid_notional_usd": filled,
            "notional_weighted_fill_ratio": filled / requested if requested else None,
            "quantity_aggregation": "NATIVE_QUANTITIES_NEVER_SUMMED_ACROSS_ASSETS",
        },
        "event_chain": link(deliveries),
        "real_fills_present": False,
        "real_prospective_validation": False,
        "external_review_completed": False,
        "execution_allowed": False,
        "level9_accredited": False,
    }
