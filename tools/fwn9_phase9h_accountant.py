"""P9H independent receipt-based cash accountant, no module imports from ledger."""
import json
import sys
from decimal import Decimal, localcontext
from pathlib import Path


def D(x: object) -> Decimal:
    return Decimal(str(x))


def verify(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    row = next(x for x in lines if x.startswith("P9H_AUDIT="))
    data = json.loads(row.split("=", 1)[1])
    check, raw = data["check"], data["raw"]
    with localcontext() as context:
        context.prec = 46
        cash = D(raw["capital"]) - D(check["calendarCosts"])
        for trade in raw["openTrades"]:
            q = D(trade["quantity"])
            events = trade["inventoryEvents"]
            ins = [e for e in events if e["kind"] == "ENTRY"]
            assert len(ins) == 1
            assert D(ins[0]["quantityDelta"]) == q
            cash -= D(trade["entry"]) * q + D(ins[0]["feeUsd"])
            for e in events:
                if e["kind"] != "EXIT" or e["knownAt"] > raw["observedAt"]:
                    continue
                assert e["at"] <= e["knownAt"]
                qty = -D(e["quantityDelta"])
                cash += qty * D(e["filledPrice"]) - D(e["feeUsd"])
        diff = abs(cash - D(check["physicalCashUsd"]))
        assert diff < Decimal("0.000001"), diff
        assert D(check["observedNativeEquityUsd"]) <= (
            cash + D(check["inventoryMarkUsd"]) + Decimal("0.000001")
        )
        assert D(check["currentStockPlusPendingUsd"]) <= (
            Decimal(".12") * D(check["observedNativeEquityUsd"]) +
            Decimal("0.000001")
        )
        assert check["sampleOnly"] and not check["fullM9Certificate"]
        return {"result": "P9H_INDEPENDENT_DECIMAL_46_PASS",
                "physicalCashUsd": str(cash), "auditDecisionId": check["decisionId"],
                "fullM9Certificate": "NO"}


if __name__ == "__main__":
    print(json.dumps(verify(Path(sys.argv[1])), indent=2))

