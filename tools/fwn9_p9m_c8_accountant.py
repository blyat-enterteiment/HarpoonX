"""Independent Decimal-60 audit of the C8 native-JS engineering fixture.

Only consumes deterministic evidence on stdin. Does not call the trading core,
generate market paths, access a broker, or certify a population wealth bound.
"""
from __future__ import annotations

import hashlib
import json
import sys
from decimal import Decimal, localcontext
from typing import Any

D = Decimal
CAPITAL = D("20000")
FEE = D("0.005")
RISK = D("0.0025")
GROSS = D("0.12")


def close(actual: Any, expected: Decimal, label: str) -> None:
    delta = abs(D(str(actual)) - expected)
    if delta > D("0.0000001"):
        raise AssertionError(f"{label}: {actual} != {expected}, delta={delta}")


def check_fixture(f: dict[str, Any], tag: str) -> None:
    first_mark = D(str(f["firstMark"]))
    no_fill, partial = bool(f["noFill"]), bool(f["partial"])
    eq = CAPITAL + D(10) * (first_mark - D(200)) - D(10) * FEE
    base_reserved = D("2000.30")
    pending = D("100.03")
    raw = base_reserved + pending
    repriced = max(base_reserved, D(10) * first_mark) + pending
    exposure = D(10) * first_mark + (D(0) if no_fill else D(100))
    cash = CAPITAL - D(10) * (D(200) + FEE)
    if not no_fill:
        cash -= D(100) + FEE
    after_a = 10
    if partial:
        after_a -= 3
        cash += D(3) * (D("219.93") - FEE)
    wealth = cash + D(after_a) * first_mark + (D(0) if no_fill else D(100))
    for key, value in (
        ("equityAtDecision", eq), ("markedPrior", max(base_reserved, D(10) * first_mark)),
        ("rawAnchorUsd", raw), ("correctedAnchorUsd", repriced),
        ("exposureAtPrebarUsd", exposure), ("cashAfterEvents", cash),
        ("equityAfterEvents", wealth),
        ("rawSnapshotAfterUsd", base_reserved if no_fill else raw),
    ):
        close(f[key], value, f"{tag}.{key}")
    if bool(f["rawAnchorPasses"]) != (exposure <= raw):
        raise AssertionError(f"{tag}: raw anchor logical check")
    if bool(f["correctedAnchorPasses"]) != (exposure <= repriced):
        raise AssertionError(f"{tag}: repriced anchor logical check")
    if bool(f["correctedWithinGrossGate"]) != (repriced <= eq * GROSS):
        raise AssertionError(f"{tag}: gross gate")
    if bool(f["plannerAllowsB"]) != (pending <= eq * GROSS - max(base_reserved, D(10) * first_mark) and base_reserved > 0):
        # Risk check remains true in the fixed one-share, fixed-risk scenarios.
        raise AssertionError(f"{tag}: native planner condition")
    if f["nativeSecondReservationStatus"] != "RESERVED":
        raise AssertionError(f"{tag}: native book did not admit fixed reservation")
    if not (cash > 0 and wealth > 0):
        raise AssertionError(f"{tag}: self financing broken")


def moment(power: int, doob: int) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 60
        q = D(doob)
        cb = q * (q - 1) / 2
        sb = D("0.00085") * D("1.25") * D("1.20") * D("0.7").exp()
        sn = D("0.0035") * D("1.20") * D("0.7").exp()
        log_bar = (D("0.996") * (cb * sb * sb).exp()
                   + D("0.004") * (D(16) * cb * sb * sb).exp()).ln()
        log_night = cb * sn * sn
        log_jump = (D("0.994") + D("0.003") * D("0.97") ** doob
                    + D("0.003") * D("1.03") ** doob).ln()
        drift = D("0.000025") * D("1.10")
        log_mq = q * (q / (q - 1)).ln() + D(2).ln() + (
            D(312) * (q * drift + log_bar)
            + D(4) * (log_night + log_jump)
        )
        return ((D(power) / q) * log_mq).exp()


def verify(payload: dict[str, Any]) -> dict[str, Any]:
    if payload["schema"] != "HARPOON_FWN9_C8_STRUCTURAL_BOUND_PROBE_1":
        raise AssertionError("wrong evidence schema")
    for key in ("raw_counterexample", "no_fill", "partial", "planner_negative_control"):
        check_fixture(payload[key], key)
    rows = payload["finite_price_moments"]
    if len(rows) != 2:
        raise AssertionError("moment catalogue changed")
    for row, (power, doob) in zip(rows, ((2, 4), (4, 8)), strict=True):
        if row["targetPower"] != power or row["doobPower"] != doob:
            raise AssertionError("moment power changed")
        close(row["upper"], moment(power, doob), f"moment{power}")
    if payload["economic_accounts"] != 0 or payload["prospective_alpha_spent"] != 0:
        raise AssertionError("economic research prohibited for C8")
    if payload["unopened_M10_final_accounts"] != 3200:
        raise AssertionError("sealed final was opened")
    if payload["native_population_wealth_bound_certified"]:
        raise AssertionError("a fixture cannot certify N9-S")
    return {
        "schema": "FWN9_C8_INDEPENDENT_DECIMAL60_AUDIT_1",
        "cases": 4,
        "price_moment_cases": 2,
        "independent_decimal": "PASS",
        "population_certification": False,
    }


def main() -> None:
    raw = sys.stdin.buffer.read()
    if not raw:
        raise ValueError("expected JSON evidence on stdin")
    result = verify(json.loads(raw))
    result["evidence_sha256"] = hashlib.sha256(raw).hexdigest()
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
