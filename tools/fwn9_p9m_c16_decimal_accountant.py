#!/usr/bin/env python3
"""Independent Decimal-46 reconstruction of C16 native A/U pathwise envelopes.

Never accepts a C16 JSON arithmetic field as its own source of truth.
Consumes only original bars, fill events and native terminal from a replay
fixture. No RNG, market generation, strategies, external connections or
economic research accounts.
"""
from __future__ import annotations

import json
import sys
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any


def dec(x: Any) -> Decimal:
    return Decimal(str(x))


def audit(evidence: dict[str, Any]) -> dict[str, str | int | bool]:
    if evidence["schema"] != "HARPOON_M11_C16_NATIVE_AU_PATHWISE_ENVELOPE_1":
        raise AssertionError("C16_INDEPENDENT_SCHEMA")
    source: dict[str, Any] = evidence["sourceForIndependentAudit"]
    sessions: list[dict[str, Any]] = source["sessions"]
    rows: list[dict[str, Any]] = source["bars"]
    entries: list[dict[str, Any]] = source["events"]
    with localcontext() as ctx:
        ctx.prec = 46
        cash = Decimal("20000")
        shares: dict[str, int] = {"SYNA": 0, "SYNB": 0}
        fees = Decimal(0)
        lower = Decimal(0)
        upper = Decimal(0)
        positive_credit = Decimal(0)
        consumed: set[int] = set()
        pending: list[tuple[int, Decimal]] = []
        unit_day = 86400000
        first_day = int(sessions[0]["open"]) // unit_day
        charged = 0
        cost_per_day = (
            dec(evidence["calendarCostUsd"]) /
            Decimal(int(evidence["calendarDays"]))
        )
        if cost_per_day not in (Decimal(1), Decimal(2)):
            raise AssertionError("C16_INDEPENDENT_COST")
        if len(rows) != len(sessions) * 78:
            raise AssertionError("C16_INDEPENDENT_SESSION_GRID")
        if len(entries) != evidence["physicalFillEventCount"]:
            raise AssertionError("C16_INDEPENDENT_EVENT_COUNT")

        def charge(at: int) -> None:
            nonlocal cash, charged
            number = at // unit_day - first_day + 1
            if number < charged:
                raise AssertionError("C16_INDEPENDENT_CLOCK_BACKWARDS")
            cash -= Decimal(number - charged) * cost_per_day
            charged = number
            if cash < 0:
                raise AssertionError("C16_INDEPENDENT_NEGATIVE_COST_CASH")

        def physical_events(at: int, kind: str, bar: dict[str, Any]) -> None:
            nonlocal cash, fees, positive_credit
            for event in entries:
                if int(event["at"]) != at or event["kind"] != kind:
                    continue
                event_id = int(event["id"])
                if event_id in consumed:
                    raise AssertionError("C16_INDEPENDENT_DOUBLE_EVENT")
                consumed.add(event_id)
                symbol = str(event["symbol"])
                delta = int(event["quantityDelta"])
                quantity = abs(delta)
                if (symbol not in shares or
                        (kind == "ENTRY" and delta <= 0) or
                        (kind == "EXIT" and delta >= 0) or
                        int(event["knownAt"]) < at or quantity == 0):
                    raise AssertionError("C16_INDEPENDENT_INVALID_PHYSICAL_FILL")
                b = bar["assets"][symbol]
                px = dec(event["filledPrice"])
                fee = dec(event["feeUsd"])
                if kind == "ENTRY":
                    if px < dec(b["o"]):
                        raise AssertionError("C16_INDEPENDENT_BUY_BELOW_OPEN")
                    unconfirmed = sum(
                        (amount for known, amount in pending if known > at),
                        Decimal(0),
                    )
                    if cash - unconfirmed < Decimal(quantity) * px + fee:
                        raise AssertionError("C16_INDEPENDENT_UNKNOWN_RECEIPT_FINANCE")
                    credit = max(Decimal(0), dec(b["o"]) - px)
                else:
                    if shares[symbol] < quantity:
                        raise AssertionError("C16_INDEPENDENT_UNCOVERED_EXIT")
                    if px > dec(b["h"]) or px < 0:
                        raise AssertionError("C16_INDEPENDENT_SELL_ABOVE_HIGH")
                    credit = max(Decimal(0), px - dec(b["l"]))
                positive_credit += Decimal(quantity) * credit
                cash -= Decimal(delta) * px + fee
                shares[symbol] += delta
                fees += fee
                if kind == "EXIT":
                    payout = Decimal(quantity) * px - fee
                    if payout > 0 and int(event["knownAt"]) > at:
                        pending.append((int(event["knownAt"]), payout))
                if cash < 0 or shares[symbol] < 0:
                    raise AssertionError("C16_INDEPENDENT_UNFUNDED_LOT")

        previous_end = -1
        for row in rows:
            at, end = int(row["t"]), int(row["end"])
            if at < previous_end or at + 300000 != end:
                raise AssertionError("C16_INDEPENDENT_BAR_CLOCK")
            previous_end = end
            charge(at)
            physical_events(at, "ENTRY", row)
            for symbol in shares:
                b = row["assets"][symbol]
                if (dec(b["l"]) <= 0 or
                        dec(b["l"]) > min(dec(b["o"]), dec(b["c"])) or
                        dec(b["h"]) < max(dec(b["o"]), dec(b["c"]))):
                    raise AssertionError("C16_INDEPENDENT_OHLC_SUPPORT")
                lower += Decimal(8 * shares[symbol]) * dec(b["l"])
                upper += Decimal(8 * shares[symbol]) * dec(b["h"])
            physical_events(end, "EXIT", row)
        charge(int(sessions[-1]["close"]))
        if (len(consumed) != len(entries) or any(shares.values()) or
                upper < lower or charged != evidence["calendarDays"]):
            raise AssertionError("C16_INDEPENDENT_UNCONSUMED_INVENTORY")

        expected = {
            "AObservedPathLowerDollarSubsteps": lower,
            "AObservedPathUpperDollarSubsteps": upper,
            "UObservedPathPositiveCreditUpperUsd": positive_credit,
            "feesUsd": fees,
            "calendarCostUsd": Decimal(charged) * cost_per_day,
            "terminalCashUsd": cash,
            "nativeTerminalEquityUsd": dec(source["originalTerminalUsd"]),
        }
        for field, independently_derived in expected.items():
            observed = dec(evidence[field])
            if abs(observed - independently_derived) > Decimal("0.000001"):
                raise AssertionError("C16_INDEPENDENT_MISMATCH_" + field)
        if abs(cash - dec(source["originalTerminalUsd"])) > Decimal("0.000001"):
            raise AssertionError("C16_INDEPENDENT_NATIVE_TERMINAL_PARITY")
        if evidence["populationExpectedAUpperCertified"] is not False:
            raise AssertionError("C16_INDEPENDENT_ILLEGAL_A_PROMOTION")
        if evidence["populationExpectedUUpperCertified"] is not False:
            raise AssertionError("C16_INDEPENDENT_ILLEGAL_U_PROMOTION")
        if evidence["C15EconomicExclusionEvaluated"] is not False:
            raise AssertionError("C16_INDEPENDENT_ILLEGAL_C15_EVALUATION")
        if evidence["N9SAdmission"] != "NO_GO":
            raise AssertionError("C16_INDEPENDENT_ILLEGAL_GO")
        if evidence["budget"] != {
            "newStrategies": 0, "newEconomicAccounts": 0,
            "newMarketSeeds": 0, "finalM10Opened": 0, "prospectiveAlphaSpent": 0,
        }:
            raise AssertionError("C16_INDEPENDENT_BUDGET")
        return {
            "verifier": "INDEPENDENT_DECIMAL46_FULL_RECALCULATION",
            "source_events": len(entries),
            "session_bars": len(rows),
            "A_lower_dollar_steps": str(lower),
            "A_upper_dollar_steps": str(upper),
            "U_upper_usd": str(positive_credit),
            "terminal_cash_usd": str(cash),
            "matches_native_source": True,
            "population_certified": False,
        }


def main() -> None:
    path = Path(sys.argv[1])
    payloads = [
        line.split("=", 1)[1]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith("FWN9_C16_NATIVE_AU_EVIDENCE=")
    ]
    if len(payloads) != 1:
        raise ValueError("C16_EXACTLY_ONE_EVIDENCE_ROW")
    report = audit(json.loads(payloads[0]))
    print("FWN9_C16_INDEPENDENT_DECIMAL46_PATHWISE_AU_PASS")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
