#!/usr/bin/env python3
"""Independent Decimal-50 cash and shadow audit for FWN9 C10 engineering data."""
import json
import sys
from decimal import Decimal, getcontext

getcontext().prec = 50
D = lambda x: Decimal(str(x))

def verify(d: dict) -> None:
    assert d["schema"] == "FWN9_C10_NATIVE_WEALTH_ENVELOPE_1"
    assert d["scope"] == "EX_POST_PATHWISE_CONDITIONAL_NONNEGATIVE_CASH_LONG_ONLY"
    bands = {k: (D(v["min"]), D(v["max"])) for k, v in d["bands"].items()}
    ratio = max([Decimal(1)] + [hi / lo for lo, hi in bands.values()])
    assert abs(ratio-D(d["range"])) < D("1e-10")
    cash = Decimal(20000)
    inventory: dict[str, int] = {}
    sold = 0
    charged_days = 0
    events = d["events"]
    first_day = min(x["at"] for x in events) // 86400000 if events else 0
    # C10 native fixture starts on the same UTC date as its earliest executed fill.
    daily = D(d["calendarCostUsd"]) / D(d["chargedDays"])
    def shadow() -> Decimal:
        return cash + sum(Decimal(q)*bands[k.split("|")[0]][0]
                          for k, q in inventory.items())
    for e in events:
        assert e["knownAt"] >= e["at"]
        due = e["at"] // 86400000 - first_day + 1
        if due > charged_days:
            cash -= Decimal(due-charged_days)*daily
            charged_days = due
            assert cash >= -D("1e-7")
        old = shadow()
        key = e["symbol"]+"|"+e["tradeId"]
        q = e["quantityDelta"]
        fee = D(e["feeUsd"])
        assert abs(fee - D(abs(q))*D(d["feePerShare"])) < D("1e-8")
        assert fee >= 0 and D(e["filledPrice"])>0
        inventory[key] = inventory.get(key, 0)+q
        assert inventory[key]>=0
        cash -= D(q)*D(e["filledPrice"])+fee
        assert cash >= -D("1e-7")
        now = shadow()
        if q > 0:
            assert now <= old+D("1e-6")
        else:
            sold += 1
            assert now <= old*ratio+D("1e-6")
    remaining_days = d["chargedDays"]-charged_days
    assert remaining_days >= 0
    cash -= Decimal(remaining_days)*daily
    assert all(q==0 for q in inventory.values())
    assert sold == d["sales"]
    assert abs(cash-D(d["physicalCashUsd"])) < D("1e-6")
    assert abs(cash-D(d["physicalTerminalUsd"])) < D("1e-6")
    upper = D(20000).ln()+D(sold+1)*ratio.ln()
    assert D(d["physicalTerminalUsd"]).ln() <= upper+D("1e-7")
    assert d["newEconomicAccounts"] == d["alphaSpent"] == d["finalM10Opened"] == 0
    assert not d["N9SAccepted"] and not d["fullM9WealthMomentIntegrationProven"]
    print("C10_DECIMAL50_INDEPENDENT_PASS",len(events),"receipts",sold,"exits")

if __name__ == "__main__":
    verify(json.load(sys.stdin))
