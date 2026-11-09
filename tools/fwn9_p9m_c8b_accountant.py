"""Independent Decimal-50 audit of native C8B receipts and arithmetic."""
from __future__ import annotations
import json
import sys
from decimal import Decimal, getcontext

getcontext().prec = 50
def d(v: object) -> Decimal:
    return Decimal(str(v))
def verify(report: dict[str, object]) -> None:
    for label in ("appreciated", "noFillSecond", "noFillFirst"):
        e = report[label]
        assert isinstance(e, dict)
        terminal = e["terminal"]
        assert isinstance(terminal, dict)
        cash = d(terminal["physicalCashUsd"])
        net = d(e["netAfterAllCostsUsd"])
        assert abs(cash - d("20000") - net) < d("0.0000001"), label
        rows = e["rows"]
        assert isinstance(rows, list)
        for row in rows:
            assert isinstance(row, dict)
            if row["admitted"]:
                assert d(row["correctedAfterUsd"]) <= d(row["grossAdmissionLimitUsd"]) + d("0.0000001")
            assert d(row["nativeCorrectedPriorUsd"]) >= d(row["nativeOriginalNotionalUsd"])
        assert e["economicAccounts"] == 0 and e["finalM10Opened"] == 0
        assert e["wealthMomentsAndN9SInfeasibilityCertified"] is False
    print("PASS C8B INDEPENDENT_DECIMAL50", file=sys.stdout)
if __name__ == "__main__":
    document = json.load(open(sys.argv[1], encoding="utf-8"))
    verify(document)
