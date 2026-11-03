"""Fixed-entry counterfactual replay of archived synthetic execution episodes.

The original first exit streams and all entry events remain unchanged. Residual
inventory after a terminal report is retried by event, subject to a frozen budget
and the causal quote TTL. Later baseline hourly exit streams are replaced. This
isolates the execution intervention; it is not a fresh alpha strategy evaluation.
"""

from __future__ import annotations

import copy
import hashlib
import heapq
import itertools
from pathlib import Path
from typing import Any

from ..core import digest
from ..synthetic9.bank import metrics
from ..synthetic9.events import link, unlink
from ..synthetic9.execution import event, simulate_order
from ..synthetic9.ledger import EPS, Ledger
from ..synthetic9.review import audit_account
from .execution import RetryBudget


def replay_account(account: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    """Rebuild one account and separately verify its Decimal cash/inventory ledger."""
    audit_account(account)
    budget = RetryBudget(
        max_attempts=protocol["max_exit_attempts_per_campaign"],
        backoff_ms=protocol["retry_backoff_ms"],
        execution_budget_ms=protocol["execution_latency_budget_ms"],
        max_quote_age_ms=protocol["max_quote_age_ms"],
    )
    source = unlink(account["event_chain"])
    baseline_orders = {e["order_id"]: e for e in source if e["kind"] == "SUBMIT"}
    first_exits: dict[str, dict[str, Any]] = {}
    for e in source:
        if e["kind"] == "SUBMIT" and e["side"] == "sell":
            first_exits.setdefault(e["campaign_id"], e)
    retained_sells = {e["order_id"] for e in first_exits.values()}
    omitted_sells = {
        k
        for k, e in baseline_orders.items()
        if e["side"] == "sell" and k not in retained_sells
    }
    ledger = Ledger(account["initial_cash_usd"])
    deliveries: list[dict[str, Any]] = []
    causal_quotes: dict[str, Any] = {}
    attempts = {campaign: 1 for campaign in first_exits}
    pending_retry: set[str] = set()
    declined: list[dict[str, Any]] = []
    retry_sends: list[dict[str, Any]] = []
    queue: list[tuple[int, int, dict[str, Any]]] = []
    sequence = itertools.count()
    original_entries = [
        e
        for e in source
        if e.get("order_id") in baseline_orders
        and baseline_orders[e["order_id"]]["side"] == "buy"
    ]

    def enqueue(body: dict[str, Any]) -> None:
        heapq.heappush(queue, (body["at"], next(sequence), body))

    for e in source:
        if e.get("order_id") in omitted_sells:
            continue
        enqueue(copy.deepcopy(e))
    multiplier = 1.0 if account["cost_scenario"] == "NOMINAL" else 2.0
    gap = 0.005 if account["cost_scenario"] == "DOUBLE_COST_GAP" else 0.0

    while queue:
        _, _, body = heapq.heappop(queue)
        kind = body["kind"]
        if kind == "DECISION":
            if body.get("core_receipt_hash"):
                # The entry schedule is fixed from a prior account, not reoptimized
                # for changed cash. Do not attach an old core certificate to it.
                body["archived_core_receipt_hash"] = body["core_receipt_hash"]
                body["core_receipt_hash"] = None
            body["state_hash"] = digest(ledger.report())
        if "quotes" in body:
            for symbol, q in body["quotes"].items():
                if q["received_at"] <= body["at"]:
                    causal_quotes[symbol] = q
        if kind == "SUBMIT" and body.get("reason") == "EVENT_RESIDUAL_RETRY":
            pending_retry.discard(body["campaign_id"])
        ledger.apply(body)
        deliveries.append(body)
        if kind not in {"REJECT", "CANCEL_ACK", "FILL"}:
            continue
        order = ledger.orders[body["order_id"]]
        if order["side"] != "sell":
            continue
        campaign, symbol = order["campaign_id"], order["symbol"]
        quantity = ledger.quantity(symbol)
        if quantity <= EPS or campaign in pending_retry:
            continue
        unresolved = sum(
            Ledger.remaining(o)
            for o in ledger.orders.values()
            if o["symbol"] == symbol and o["side"] == "sell"
        )
        if unresolved > EPS:
            continue
        quote = causal_quotes[symbol]
        first = first_exits[campaign]
        at = budget.next_at(
            now=body["at"],
            deadline=first["deadline_at"],
            quote_at=quote["quote_at"],
            attempts=attempts[campaign],
            order_reconciled=True,
            market_available=True,
        )
        if at is None:
            declined.append(
                {
                    "campaign_id": campaign,
                    "at": body["at"],
                    "quantity": quantity,
                    "attempts": attempts[campaign],
                    "reason": "REGISTERED_BUDGET_OR_CAUSAL_QUOTE_EXHAUSTED",
                }
            )
            continue
        attempts[campaign] += 1
        number = attempts[campaign]
        oid = first["order_id"] + f"-event-retry-{number}"
        did = oid + "-decision"
        enqueue(
            event(
                "DECISION",
                did,
                at - 1,
                decision_id=did,
                quotes={symbol: copy.deepcopy(quote)},
                core_receipt_hash=None,
                state_hash=digest(ledger.report()),
            )
        )
        retry = event(
            "SUBMIT",
            oid,
            at,
            order_id=oid,
            decision_id=did,
            symbol=symbol,
            book=first["book"],
            side="sell",
            qty=round(quantity, 8),
            decision_bid=quote["bid"],
            decision_ask=quote["ask"],
            limit_price=None,
            fee_bps=first["fee_bps"],
            fixed_fee_usd=first["fixed_fee_usd"],
            campaign_id=campaign,
            deadline_at=first["deadline_at"],
            reason="EVENT_RESIDUAL_RETRY",
        )
        seed_material = f"{account['seed']}|{campaign}|{number}".encode()
        seed = int.from_bytes(hashlib.sha256(seed_material).digest()[:4], "big")
        for generated in simulate_order(retry, seed, multiplier=multiplier, gap=gap):
            enqueue(generated)
        pending_retry.add(campaign)
        retry_sends.append(
            {
                "order_id": oid,
                "campaign_id": campaign,
                "at": at,
                "attempt": number,
                "quote_age_ms": at - quote["quote_at"],
                "original_deadline": first["deadline_at"],
            }
        )

    report = ledger.report()
    reproduced_entries = [
        e
        for e in deliveries
        if e.get("order_id") in baseline_orders
        and baseline_orders[e["order_id"]]["side"] == "buy"
    ]
    if reproduced_entries != original_entries:
        raise ValueError("FIXED_ENTRY_EVENTS_CHANGED")
    packet = {
        "schema": account["schema"],
        "origin": account["origin"],
        "strategy": account["strategy"],
        "world": account["world"],
        "seed": account["seed"],
        "cost_scenario": account["cost_scenario"],
        "initial_cash_usd": ledger.initial,
        "continuous_capital": True,
        "ledger": report,
        "metrics": metrics(report, ledger.initial),
        "core_receipts": [],
        "event_chain": link(deliveries),
        "counterfactual_variant": "REGISTERED_EVENT_RETRY_FIXED_ENTRIES",
        "entry_policy_recomputed": False,
        "entry_source_receipts_hash": digest(account["core_receipts"]),
        "source_event_chain_head": account["event_chain"][-1]["hash"],
        "entry_events_preserved": True,
        "entry_events_hash": digest(original_entries),
        "retry_sends": retry_sends,
        "declined_retries": declined,
        "real_fills_present": False,
        "real_prospective_validation": False,
        "external_review_completed": False,
        "execution_allowed": False,
        "level9_accredited": False,
    }
    packet["separate_decimal_audit"] = audit_account(packet)
    return packet


def account_receipt(
    source: dict[str, Any], replay: dict[str, Any], path: Path
) -> dict[str, Any]:
    """Compact, reproducible proof index; raw packets may be saved by the runner."""
    before, after = source["metrics"], replay["metrics"]
    return {
        "source_file": str(path),
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "world": source["world"],
        "seed": source["seed"],
        "scenario": source["cost_scenario"],
        "strategy": source["strategy"],
        "planned_deadline_breaches_before": before["deadline_breach_count"],
        "planned_deadline_breaches_after": after["deadline_breach_count"],
        "original_breached_campaign_ids": sorted(source["ledger"]["deadline_breaches"]),
        "remaining_breached_campaign_ids": sorted(
            replay["ledger"]["deadline_breaches"]
        ),
        "net_pnl_before_usd": before["net_pnl_usd"],
        "net_pnl_after_usd": after["net_pnl_usd"],
        "max_hold_after_hours": after["max_hold_hours"],
        "retry_orders": len(replay["retry_sends"]),
        "declined_retries": replay["declined_retries"],
        "open_positions": after["open_position_count"],
        "unresolved_orders": after["unresolved_order_count"],
        "entry_events_preserved": replay["entry_events_preserved"],
        "event_chain_head": replay["event_chain"][-1]["hash"],
        "entry_events_hash": replay["entry_events_hash"],
        "decimal_audit": replay["separate_decimal_audit"],
        "financial_acceptance_allowed": False,
    }
