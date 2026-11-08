#!/usr/bin/env python3
"""Independent Decimal check for FWN9 P9B native portfolio book; fixtures only."""
import json
import sys
from decimal import Decimal, localcontext


def as_decimal(value: object) -> Decimal:
    return Decimal(str(value))


def verify(payload: dict[str, object]) -> dict[str, str]:
    checks = payload["checked"]
    book = payload["accounting"]
    native = payload["metadata"]
    assert isinstance(checks, dict) and isinstance(book, dict) and isinstance(native, dict)
    assert checks["nativeRiskClockParity"] is True
    assert checks["nativeMarkFormationIndependentlyVerified"] is False
    assert checks["stochasticWealthBoundCertified"] is False
    assert checks["realExecutionValidated"] is False
    with localcontext() as ctx:
        ctx.prec = 46
        start = Decimal("20000")
        trading = as_decimal(book["modeledTradingPnlUsd"])
        dividend = as_decimal(book["dividendAccruedUsd"])
        fixed = as_decimal(book["modeledExternalCostsUsd"])
        end = start + trading + dividend - fixed
        published = as_decimal(checks["terminalEquityUsd"])
        reported = as_decimal(book["netEconomicUsd"])
        assert abs(end - published) <= Decimal("0.0000001")
        assert abs(reported - (end - start)) <= Decimal("0.0000001")
        assert abs(as_decimal(checks["maximumObservedEventDrawdown"]) -
                   as_decimal(native["maximumObservedEventDrawdown"])) <= Decimal("0.000000001")
        assert int(checks["observedValuationEvents"]) == int(native["observedValuationEvents"])
        assert int(checks["acceptedCount"]) == len(payload["admittedCampaigns"])
        assert all(as_decimal(row["cashUsd"]) > 0 for row in checks["signalChecks"]
                   if "cashUsd" in row)
        return {"endUsd": str(end), "netUsd": str(end - start),
                "drawdown": str(native["maximumObservedEventDrawdown"])}


def main() -> None:
    with open(sys.argv[1], encoding="utf-8") as stream:
        lines = [line for line in stream if line.startswith("FWN9_P9B_AUDIT=")]
    assert len(lines) == 1, "AUDITOR_PAYLOAD_REQUIRED"
    payload = json.loads(lines[0].split("=", 1)[1])
    report = verify(payload)
    print("FWN9_P9B_DECIMAL_46_ACCOUNTING_PASS")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
