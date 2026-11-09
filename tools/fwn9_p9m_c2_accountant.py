"""P9M-C2 independent Decimal ledger: offline native receipt export only."""
from __future__ import annotations
import json
import sys
from decimal import Decimal, getcontext
from pathlib import Path

getcontext().prec = 46

def dec(x: object) -> Decimal:
    return Decimal(str(x))

def validate(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema"] == "P9MC2_DECIMAL_INPUT_1"
    assert len(data["audits"]) == 2
    for row in data["audits"]:
        assert row["budget"] == {"marketAccounts": 0, "finalM10Opened": 0,
            "alphaSpent": 0, "newCandidates": 0}
        cash = dec(row["capitalUsd"])
        shares = 0
        fees = Decimal("0")
        prior_known = -1
        for e in row["filled"]["events"]:
            q = int(e["quantityDelta"])
            price = dec(e["filledPrice"])
            fee = dec(e["feeUsd"])
            assert e["knownAt"] >= e["at"] and e["knownAt"] >= prior_known
            assert fee == abs(q) * dec(row["feePerShareSideUsd"])
            if e["kind"] == "ENTRY":
                assert q > 0 and shares == 0
                shares += q
                cash -= q * price + fee
            else:
                assert e["kind"] == "EXIT" and q < 0 and shares + q >= 0
                shares += q
                cash += (-q) * price - fee
            fees += fee
            prior_known = e["knownAt"]
        assert shares == 0
        assert abs(fees-dec(row["filled"]["totalFeesUsd"])) < Decimal("0.00000001")
        assert abs(cash-dec(row["account"]["tradingCashBeforeFixedUsd"])) < Decimal("0.00000001")
        final = cash - dec(row["account"]["totalFixedCalendarUsd"])
        assert abs(final-dec(row["account"]["terminalPhysicalCashUsd"])) < Decimal("0.00000001")
        assert abs(final-dec(row["account"]["nativeTerminalEquityUsd"])) < Decimal("0.00000001")
        assert row["noFill"]["phantomInventory"] is False
        assert row["noFillReservationAfterReceipt"] is False
        assert row["gates"]["n9sEligible"] is False
    print("P9MC2_DECIMAL46_INDEPENDENT_PASS 2 dual-asset cases")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("expected a JSON filename")
    validate(Path(sys.argv[1]))
