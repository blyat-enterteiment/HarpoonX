"""FWN9 P9L: independent Decimal-60 reconstruction of source receipt replay.

Engineering-modeled prices are input artifacts, not broker executions or alpha.
"""
from __future__ import annotations

import json
import sys
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any


def verify(path: Path) -> dict[str, Any]:
    raw = path.read_text()
    lines = [s for s in raw.splitlines() if s.startswith("P9L_AUDIT=")]
    if len(lines) != 1:
        raise ValueError("P9L_ONE_REPRODUCIBLE_AUDIT_REQUIRED")
    p: dict[str, Any] = json.loads(lines[0][len("P9L_AUDIT="):])
    if p.get("schema") != "HARPOON_FWN9_P9L_NATIVE_EVENT_BRIDGE_1" or (
        p.get("sourceNature") != "HISTORICAL_MODELED_OHLCV_NOT_BROKER_RECEIPTS"
        or p.get("optimizerEligible") is not False
        or p.get("nativePriceExecutability") is not False
        or p.get("noBroker") is not True
    ):
        raise ValueError("P9L_PROVENANCE_OR_PROMOTION_FALSE")
    events = p["receiptTape"]
    if not events or len(events) != p["events"]:
        raise ValueError("P9L_EVENT_COVERAGE_MISSING")
    ids = set()
    first_known: int | None = None
    previous = -1
    for e in events:
        if e["id"] in ids or e["knownAt"] < e["effectiveAt"]:
            raise ValueError("P9L_DUPLICATED_OR_FUTURE_EVENT")
        if e["knownAt"] < previous:
            raise ValueError("P9L_EVENT_ORDER_CHANGED")
        ids.add(e["id"])
        previous = e["knownAt"]
        if first_known is None:
            first_known = e["knownAt"]
    if first_known is None:
        raise ValueError("P9L_EMPTY_EVENTS")
    with localcontext() as context:
        context.prec = 60

        def dec(value: object) -> Decimal:
            return Decimal(str(value))

        capital = Decimal("20000")
        fee = Decimal("0.005")
        entry_cash = sum(
            (dec(e["quantity"]) * dec(e["price"]) for e in events
             if e["type"] == "ENTRY_FILL"), Decimal(0)
        )
        exit_cash = sum(
            (dec(e["quantity"]) * dec(e["price"]) for e in events
             if e["type"] == "EXIT_FILL"), Decimal(0)
        )
        fees = sum(
            (dec(e["quantity"]) * fee for e in events
             if e["type"] in {"ENTRY_FILL", "EXIT_FILL"}), Decimal(0)
        )
        last = p["finalSnapshot"]
        terminal = last["clock"]
        days = terminal // 86400000 - first_known // 86400000 + 1
        if days <= 0 or days > 176:
            raise ValueError("P9L_CALENDAR_RANGE")
        cash = capital - Decimal(days) - entry_cash + exit_cash - fees
        wealth = dec(p["shadowWealthUsd"])
        if abs(cash - wealth) >= Decimal("0.000001"):
            raise ValueError("P9L_INDEPENDENT_CASH_RECONCILIATION")
        if abs(wealth - dec(p["sourceWealthUsd"])) >= Decimal("0.000001"):
            raise ValueError("P9L_NATIVE_TERMINAL_DIFFERENCE")
        if last["positions"] != 0 or last["reservationCount"] != 0:
            raise ValueError("P9L_TERMINAL_INVENTORY_UNSETTLED")
        if abs(fees - dec(last["feesPaidUsd"])) >= Decimal("0.000001"):
            raise ValueError("P9L_SOURCE_FEE_MISMATCH")
    return {"schema": "FWN9_P9L_DECIMAL_60_SOURCE_BRIDGE_1",
            "status": "PASS_DECIMAL_60", "source_accepted": p["accepted"],
            "modeled_entries": p["funded"], "modeled_no_fills": p["nofill"],
            "source_events": len(events), "calendar_days": days,
            "independent_cash_usd": str(cash),
            "source_wealth_usd": str(wealth), "real_broker_fills": 0,
            "optimizer_promotion_allowed": False}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("expected one read-only source bridge audit")
    print(json.dumps(verify(Path(sys.argv[1])), indent=2, sort_keys=True))
