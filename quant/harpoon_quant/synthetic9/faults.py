"""Executable fault injections and known-answer controls, never profitability claims."""

from __future__ import annotations

import copy
from typing import Any

from ..frontier.contracts import require
from . import ORIGIN
from .events import link
from .execution import event, simulate_order
from .ledger import Ledger
from .review import audit_account

T0 = 1_700_000_000_000


def fixture_order(
    *, qty: float = 2.0, symbol: str = "AAPL", book: str = "equity"
) -> tuple[dict[str, Any], dict[str, Any]]:
    q = {"bid": 99.99, "ask": 100.01, "quote_at": T0, "received_at": T0}
    decision = event("DECISION", "D", T0, decision_id="D", quotes={symbol: q})
    order = event(
        "SUBMIT",
        "O",
        T0 + 10,
        order_id="O",
        decision_id="D",
        symbol=symbol,
        book=book,
        side="buy",
        qty=qty,
        decision_bid=q["bid"],
        decision_ask=q["ask"],
        limit_price=105.0,
        fee_bps=2.0,
        fixed_fee_usd=0.01,
        campaign_id="CAMPAIGN",
        deadline_at=T0 + 72 * 3_600_000,
        stop_price=98.0,
        target_price=103.0,
    )
    return decision, order


def account_from(ledger: Ledger, events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": "HARPOON_SYNTHETIC_ACCOUNT_1",
        "origin": ORIGIN,
        "initial_cash_usd": ledger.initial,
        "ledger": ledger.report(),
        "event_chain": link(events),
        "real_fills_present": False,
        "real_prospective_validation": False,
        "external_review_completed": False,
        "execution_allowed": False,
        "level9_accredited": False,
    }


def fault_matrix() -> dict[str, Any]:
    rows = []
    for name, force, opened in [
        ("FULL_FILL", "FULL", True),
        ("PARTIAL_CANCEL", "PARTIAL_CANCEL", True),
        ("CANCEL_LATE_FILL", "LATE_FILL", True),
        ("REJECT", "REJECT", True),
        ("HALT_NO_FILL", "FULL", False),
        ("NONMARKETABLE_LIMIT_NO_FILL", "FULL", True),
        ("DUPLICATE_DELIVERY", "FULL", True),
        ("EXPLICIT_FEE_CORRECTION", "FULL", True),
        ("DEADLINE_HALT_UNRESOLVED", "FULL", True),
    ]:
        ledger = Ledger()
        decision, order = fixture_order()
        if name == "NONMARKETABLE_LIMIT_NO_FILL":
            order["limit_price"] = 99.0
        bodies = [decision, *simulate_order(order, 73, force=force, open_market=opened)]
        if name == "DUPLICATE_DELIVERY":
            bodies.append(copy.deepcopy(bodies[-1]))
        if name == "EXPLICIT_FEE_CORRECTION":
            bodies.append(
                event(
                    "FEE_CORRECTION",
                    "fee-correction",
                    T0 + 3000,
                    order_id="O",
                    fee_usd=0.25,
                )
            )
        final = T0 + (73 * 3_600_000 if name == "DEADLINE_HALT_UNRESOLVED" else 10000)
        bodies.append(
            event("MARK", "mark", final, quotes={"AAPL": {"bid": 101.0, "ask": 101.02}})
        )
        for body in bodies:
            ledger.apply(body)
        audit = audit_account(account_from(ledger, bodies))
        if name == "DEADLINE_HALT_UNRESOLVED":
            require(
                bool(ledger.breaches) and ledger.quantity("AAPL") == 2,
                "HALT_NOT_FAKE_LIQUIDATED",
            )
        elif name in {"REJECT", "HALT_NO_FILL", "NONMARKETABLE_LIMIT_NO_FILL"}:
            require(ledger.quantity("AAPL") == 0, "UNEXPECTED_FILL")
        elif name == "PARTIAL_CANCEL":
            require(ledger.quantity("AAPL") == 1, "PARTIAL_QTY")
        else:
            require(ledger.quantity("AAPL") == 2, "FULL_QTY")
        rows.append(
            {
                "case": name,
                "result": "EXPECTED_BEHAVIOR",
                "fill_count": len(ledger.fills),
                "remaining_qty": ledger.quantity("AAPL"),
                "deadline_breach_count": len(ledger.breaches),
                "separate_decimal_verified": audit["verified"],
            }
        )
    bad_cases = [
        "STALE_QUOTE",
        "FUTURE_QUOTE",
        "OVERFILL",
        "MISSING_ACK",
        "FILL_DURING_HALT",
        "LIQUIDITY_OVERCLAIM",
        "CONFLICTING_DUPLICATE",
        "UNCONFIRMED_SALE_FUNDING",
        "POST_CANCEL_FILL",
    ]
    for name in bad_cases:
        decision, order = fixture_order()
        bodies = [decision, *simulate_order(order, 73, force="FULL")]
        valid_ledger = Ledger()
        valid_bodies = copy.deepcopy(bodies)
        mark = event(
            "MARK", "final", T0 + 10000, quotes={"AAPL": {"bid": 101.0, "ask": 101.02}}
        )
        valid_bodies.append(mark)
        for body in valid_bodies:
            valid_ledger.apply(body)
        if name == "STALE_QUOTE":
            decision["quotes"]["AAPL"]["quote_at"] -= 15001
        elif name == "FUTURE_QUOTE":
            decision["quotes"]["AAPL"]["received_at"] += 1
        elif name == "OVERFILL":
            bodies[-1]["qty"] = 3.0
            bodies[-1]["available_qty"] = 3.0
        elif name == "MISSING_ACK":
            bodies = [b for b in bodies if b["kind"] != "ACK"]
        elif name == "FILL_DURING_HALT":
            bodies[-1]["halted"] = True
        elif name == "LIQUIDITY_OVERCLAIM":
            bodies[-1]["available_qty"] = 1.0
        elif name == "CONFLICTING_DUPLICATE":
            duplicate = copy.deepcopy(bodies[-1])
            duplicate["price"] += 1
            bodies.append(duplicate)
        elif name == "UNCONFIRMED_SALE_FUNDING":
            order["qty"] = 1000.0
        elif name == "POST_CANCEL_FILL":
            bodies = [decision, *simulate_order(order, 73, force="LATE_FILL")]
            bodies[-1]["occurred_at"] = bodies[-2]["occurred_at"] + 1
        ledger = Ledger()
        reason = None
        try:
            for body in bodies:
                ledger.apply(body)
        except ValueError as exc:
            reason = str(exc)
        require(reason is not None, "FAULT_NOT_REJECTED:" + name)
        invalid_packet = account_from(valid_ledger, [*bodies, mark])
        independent_reason = None
        try:
            audit_account(invalid_packet)
        except ValueError as exc:
            independent_reason = str(exc)
        require(
            independent_reason is not None
            and independent_reason != "AUDIT_CURVE_LENGTH",
            "INDEPENDENT_FAULT_NOT_REJECTED:" + name,
        )
        rows.append(
            {
                "case": name,
                "result": "EXPECTED_REJECTION",
                "reason": reason,
                "separate_decimal_rejection": independent_reason,
            }
        )
    return {
        "origin": ORIGIN,
        "cases": rows,
        "passed": len(rows),
        "total": len(rows),
        "all_expected_behaviors": True,
        "scope": "ENGINEERING_FAULT_COVERAGE_NOT_MARKET_AUTHENTICATION",
        "external_review_completed": False,
        "level9_accredited": False,
    }
