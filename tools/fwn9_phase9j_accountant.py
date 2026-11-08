"""Independent P9J no-fill clock and cash check; engineering fixture only."""
from __future__ import annotations
import json
import sys
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any


def verify(path: Path) -> dict[str, Any]:
    proof = None
    for line in path.read_text().splitlines():
        if line.startswith("P9J_EVENT_PROOF="):
            if proof is not None:
                raise ValueError("P9J_DUPLICATE_PROOF")
            proof = json.loads(line.split("=", 1)[1])
    if proof is None:
        raise ValueError("P9J_PROOF_MISSING")
    rows = proof["noFillEvents"]
    assert len(rows) == 2 and proof["tradedCampaigns"] == 0
    assert all(not row["positionOpened"] for row in rows)
    assert all(row["decisionAt"] < row["plannedEntryAt"] == row["resolutionAt"]
               for row in rows)
    clocks = set(proof["sessions"]) | {row["plannedEntryAt"] for row in rows}
    expected = len(clocks)
    assert proof["sourceCount"] == proof["reconstructedCount"] == expected
    assert proof["releaseCount"] == 2
    assert proof["promotionAllowed"] is False
    day = 86400000
    days = proof["terminalAt"] // day - proof["sessionStart"] // day + 1
    with localcontext() as ctx:
        ctx.prec = 46
        expected_equity = Decimal(str(proof["capital"])) - (
            Decimal(days) * Decimal(str(proof["fixedCostPerDay"]))
        )
        assert Decimal(str(proof["nativeFinalEquity"])) == expected_equity
        assert Decimal(str(proof["bookFinalEquity"])) == expected_equity
    return {"schema":"FWN9_P9J_INDEPENDENT_NOFILL_CLOCK_1",
            "event_count":expected, "no_fill_receipts":len(rows),
            "calendar_cost_days":days,
            "terminal_equity_usd":str(expected_equity),
            "independent_decimal":"PASS_46",
            "stochastic_certificate":False, "economic_accounts":0}


if __name__=="__main__":
    if len(sys.argv)!=2:
        raise SystemExit("expected one audit output file")
    print(json.dumps(verify(Path(sys.argv[1])),indent=2,sort_keys=True))
