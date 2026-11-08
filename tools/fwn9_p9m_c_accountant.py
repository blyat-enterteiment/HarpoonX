"""Independent Decimal-46 accountant for the immutable P9M-C1 witness JSON."""
import json
import sys
from decimal import Decimal, getcontext
getcontext().prec = 46
M=Decimal
raw=sys.stdin.read()
line=next((x for x in raw.splitlines() if x.startswith("P9MC1_EVIDENCE=")),None)
if line is None:
    raise SystemExit("MISSING_WITNESS")
w=json.loads(line.split("=",1)[1])
assert w["sourceNature"]=="DETERMINISTIC_SYNTHETIC_ENGINEERING_NO_OBSERVED_FILLS"
assert w["sourcePair"]["sameOHLC"] and w["sourcePair"]["sameSubstepMultiset"]
assert w["budget"]=={"economicAccounts":0,"marketSeedsOpened":0,"finalSeedsOpened":0,
                      "prospectiveAlphaSpent":0,"newCandidates":0}
def audit(book):
    entry_fee=M(".005")
    q=book["quantity"]
    assert q==8
    assert book["closed"]
    # The independent native-vs-causal check uses a closed-campaign
    # net and price levels; buy prices are fixed by the original IOC.
    first_buy=M("100.03")
    cash=M("20000")-M(q)*(first_buy+entry_fee)
    inventory=q
    for receipt in book["fills"]:
        n=receipt["shares"]
        assert 0<n<=inventory
        inventory-=n
        cash+=M(str(receipt["priceUsd"]))*n-entry_fee*n
    assert inventory==0
    assert abs((cash-M("20000"))-M(str(book["netTradingUsd"])))<=M(".000001")
    assert abs((cash-M("8"))-M(str(book["terminalAfterCalendarUsd"])))<=M(".000001")
    assert M(str(book["feesUsd"]))==M(".08")
for branch in ["targetFirst","stopFirst"]:
    for mode in ["native","discrete"]:
        audit(w[branch][mode])
assert w["targetFirst"]["native"]["netTradingUsd"]==w["stopFirst"]["native"]["netTradingUsd"]
assert w["targetFirst"]["discrete"]["netTradingUsd"]!=w["stopFirst"]["discrete"]["netTradingUsd"]
print("P9MC1_DECIMAL46_ACCOUNTANT_PASS")
