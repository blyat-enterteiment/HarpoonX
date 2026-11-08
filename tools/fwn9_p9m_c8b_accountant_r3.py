"""Independent Decimal-50 audit of C8B replay receipts and admission arithmetic."""

from __future__ import annotations

import json
import sys
from decimal import Decimal, getcontext
from typing import Any

getcontext().prec = 50


def d(value: object) -> Decimal:
    return Decimal(str(value))


def verify(report: dict[str, Any]) -> None:
    """Verify finite accounting identities, not model or population validity."""
    for label in ("appreciated", "noFillSecond", "noFillFirst"):
        evidence: Any = report[label]
        assert isinstance(evidence, dict)
        terminal: Any = evidence["terminal"]
        assert isinstance(terminal, dict)
        cash = d(terminal["physicalCashUsd"])
        net = d(evidence["netAfterAllCostsUsd"])
        assert abs(cash - Decimal(20000) - net) < Decimal("0.0000001"), label
        rows: Any = evidence["rows"]
        assert isinstance(rows, list)
        for row in rows:
            assert isinstance(row, dict)
            if row["admitted"]:
                assert d(row["correctedAfterUsd"]) <= (
                    d(row["grossAdmissionLimitUsd"]) + Decimal("0.0000001")
                )
            assert d(row["nativeCorrectedPriorUsd"]) >= d(
                row["nativeOriginalNotionalUsd"]
            )
        assert evidence["economicAccounts"] == 0
        assert evidence["finalM10Opened"] == 0
        assert evidence["wealthMomentsAndN9SInfeasibilityCertified"] is False
    print("PASS C8B INDEPENDENT_DECIMAL50", file=sys.stdout)


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as source:
        document: dict[str, Any] = json.load(source)
    verify(document)
