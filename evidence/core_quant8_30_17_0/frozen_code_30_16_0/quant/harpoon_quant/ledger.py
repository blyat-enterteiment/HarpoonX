"""Independent cash/inventory reduction for the economic replay event ledger.

Fees are a breakdown of cash_change, never a second debit. This verifies
internal consistency, not broker authenticity or market fill realism.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any


def reconcile_events(
    events: list[dict[str, Any]], initial_cash: float, tolerance: float = 1e-7
) -> dict[str, Any]:
    if not math.isfinite(initial_cash) or initial_cash <= 0:
        raise ValueError("LEDGER_INITIAL_CASH")
    cash = float(initial_cash)
    inventory: dict[str, int] = {}
    basis: dict[str, float] = {}
    entered_at: dict[str, datetime] = {}
    used_ids: set[str] = set()
    previous_at: datetime | None = None
    realized = 0.0
    fees = 0.0
    fills = 0

    def number(value: Any) -> float:
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("LEDGER_NONFINITE")
        return result

    def close(actual: float, expected: float, code: str) -> None:
        if abs(actual - expected) > tolerance:
            raise ValueError(code)

    for event in events:
        kind = event["kind"]
        at = datetime.fromisoformat(event["at"])
        if at.tzinfo is None or (previous_at is not None and at < previous_at):
            raise ValueError("LEDGER_EVENT_TIME_ORDER")
        previous_at = at
        if kind in {"ENTRY", "EXIT"}:
            position_id = str(event["position_id"])
            lots = event["lots"]
            if type(lots) is not int or lots <= 0:
                raise ValueError("LEDGER_LOT_DOMAIN")
            change = number(event["cash_change"])
            fee = number(event["fees_usd"])
            gross = number(event["gross_cash_change"])
            if fee < 0:
                raise ValueError("LEDGER_FEE_DOMAIN")
            close(change, gross - fee, "LEDGER_FEE_RECONCILIATION")
            if kind == "ENTRY":
                if position_id in used_ids or change >= 0:
                    raise ValueError("LEDGER_DUPLICATE_OR_INVALID_ENTRY")
                used_ids.add(position_id)
                inventory[position_id] = lots
                basis[position_id] = -change / lots
                entered_at[position_id] = at
            else:
                held = inventory.get(position_id, 0)
                if lots > held:
                    raise ValueError("LEDGER_EXIT_EXCEEDS_INVENTORY")
                if at - entered_at[position_id] > timedelta(hours=72):
                    raise ValueError("LEDGER_HOLDING_EXCEEDS_72H")
                realized += change - lots * basis[position_id]
                inventory[position_id] = held - lots
                if not inventory[position_id]:
                    del inventory[position_id]
                    del basis[position_id]
                    del entered_at[position_id]
            cash += change
            fees += fee
            fills += 1
        elif kind in {"PRE_NAV", "NAV"}:
            close(cash, number(event["cash"]), "LEDGER_CASH_MISMATCH")
            marks = event["positions"]
            seen: dict[str, int] = {}
            marked_value = 0.0
            for mark in marks:
                position_id = str(mark["position_id"])
                if position_id in seen:
                    raise ValueError("LEDGER_DUPLICATE_MARK")
                lots = mark["lots"]
                if type(lots) is not int or lots <= 0:
                    raise ValueError("LEDGER_LOT_DOMAIN")
                seen[position_id] = lots
                marked_value += lots * number(mark["liquidation_value_per_lot"])
            if seen != inventory:
                raise ValueError("LEDGER_INVENTORY_MISMATCH")
            close(cash + marked_value, number(event["nav"]), "LEDGER_NAV_MISMATCH")
        elif kind != "RISK_BREACH":
            raise ValueError("LEDGER_UNKNOWN_EVENT")
    return {
        "status": "RECONCILED",
        "final_cash": cash,
        "open_inventory": inventory,
        "realized_net_pnl": realized,
        "fees_usd": fees,
        "fill_events": fills,
        "scope": "Internal cash, inventory and event-time consistency; not verification of broker fills",
    }
