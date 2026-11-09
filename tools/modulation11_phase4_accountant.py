"""Independent decimal cash accountant for M11 phase4 fixture only.
No imported JS pricing, no market trials; checks an externally emitted JSON certificate.
"""
from __future__ import annotations

import json
import sys
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path

D = Decimal
TICK = D("0.01")
FEE_PER_SHARE = D("0.005")
FRICTION = D("0.0003")
QUANTITY = 8
ENTRY = D("100.03")
CAPITAL = D("20000")
MARK = D("100")
EPS = D("0.0000001")


def executable_price(raw: str) -> Decimal:
    return (D(raw) * (D("1") - FRICTION)).quantize(TICK, rounding=ROUND_FLOOR)


def ending_equity(sells: tuple[tuple[int, str], ...]) -> Decimal:
    remaining = QUANTITY
    cash = CAPITAL - D(QUANTITY) * ENTRY - D(QUANTITY) * FEE_PER_SHARE
    for qty, raw in sells:
        assert 0 <= qty <= remaining, "INVALID_INVENTORY"
        remaining -= qty
        cash += D(qty) * executable_price(raw) - D(qty) * FEE_PER_SHARE
    return cash + D(remaining) * MARK


def compare_certificate(cert: dict) -> dict:
    assert cert["schema"] == "HARPOON_M11_PHASE4_CAUSAL_FORK_WITNESS_1"
    cases = {
        "upNative": ((2, "101.53"),),
        "upFirstCross": ((2, "101.8"),),
        "downNative": ((8, "99.03"),),
        "downFirstCross": ((2, "101.8"), (6, "95.5")),
    }
    computed = {key: ending_equity(sells) for key, sells in cases.items()}
    for key, expected in computed.items():
        observed = D(str(cert["markedWealth"][key]["terminalEquityUsd"]))
        assert abs(observed - expected) < EPS, (key, expected, observed)
    up_gap = computed["upNative"] - computed["upFirstCross"]
    down_gap = computed["downNative"] - computed["downFirstCross"]
    assert abs(up_gap - D(str(cert["gapFromExecutionNativeUpUsd"]))) < EPS
    assert abs(down_gap - D(str(cert["gapFromExecutionNativeDownUsd"]))) < EPS
    assert up_gap < 0 < down_gap
    assert not cert["nativeN9SInfeasibilityCertified"]
    return {
        "schema": "HARPOON_M11_P4_INDEPENDENT_DECIMAL_ACCOUNTANT_1",
        "ending_equities": {k: str(v) for k, v in computed.items()},
        "up_gap_usd": str(up_gap),
        "down_gap_usd": str(down_gap),
        "same_law_costs_preserved": True,
        "economic_accounts": 0,
    }


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("USAGE: python tools/modulation11_phase4_accountant.py <json>")
    cert = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(json.dumps(compare_certificate(cert), sort_keys=True))


if __name__ == "__main__":
    main()
