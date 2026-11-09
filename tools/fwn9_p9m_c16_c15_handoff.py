#!/usr/bin/env python3
"""C16 -> C15 handoff: verified pathwise native envelopes, no population promotion.

Requires independent Decimal-46 C16 evidence check. C15 requires EXPECTATIONS,
not one realized bounded trajectory. This functional adapter therefore reports
the pathwise measurements alongside *missing-input* original economic gates,
and refuses any attempt to substitute fixture values for expectation bounds.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from fwn9_p9m_c15_economic_gate import bound, verify_original_protocol
from fwn9_p9m_c16_decimal_accountant import audit


def handoff(
    evidence: dict[str, Any], original_protocol: Path
) -> dict[str, Any]:
    independent = audit(evidence)
    provenance = verify_original_protocol(original_protocol)
    if evidence["exactOrderedEightSubstepTapeAvailable"] is not False:
        raise ValueError("C16_C15_UNEXPECTED_NATIVE_SUBSTEP_TAPE")
    if evidence["pathwiseUpperOnly"] is not True:
        raise ValueError("C16_C15_REJECT_NON_PATHWISE_TAG")
    if evidence["populationExpectedAUpperCertified"] is not False:
        raise ValueError("C16_C15_UNAUTHORIZED_EXPECTATION_PROMOTION_A")
    if evidence["populationExpectedUUpperCertified"] is not False:
        raise ValueError("C16_C15_UNAUTHORIZED_EXPECTATION_PROMOTION_U")
    gates: dict[str, Any] = {}
    for scenario in ("NOMINAL", "STRESS"):
        screen = bound(scenario)
        if (screen["conditional_economic_screen"] !=
                "UNIDENTIFIED_MISSING_POPULATION_BOUNDS"):
            raise AssertionError("C16_C15_MUST_FAIL_CLOSED")
        gates[scenario] = {
            "scenario": scenario,
            "original_hurdle_increment_usd":
                screen["terminal_hurdle_increment_usd"],
            "fixed_calendar_cost_floor_usd":
                screen["fixed_calendar_cost_lower_usd"],
            "gamma_per_step": screen["gamma_per_step"],
            "expected_A_upper": None,
            "expected_U_upper": None,
            "math_exclusion_if_inputs_proved": None,
        }
    return {
        "schema": "HARPOON_M11_C16_VERIFIED_PATHWISE_TO_C15_NO_PROMOTION_1",
        "independent_recalculation": independent,
        "frozen_M9_protocol": provenance,
        "pathwise_only": {
            "A_lower_dollar_steps": evidence["AObservedPathLowerDollarSubsteps"],
            "A_upper_dollar_steps": evidence["AObservedPathUpperDollarSubsteps"],
            "U_upper_usd": evidence["UObservedPathPositiveCreditUpperUsd"],
            "session_count": len(evidence["sourceForIndependentAudit"]["sessions"]),
            "bars": evidence["barCount"],
        },
        "population_C15_screens": gates,
        "reason": "One deterministic replay fixture has no population expectation bound",
        "may_enable_recursive_search": False,
        "may_open_M10_final": False,
        "N9SAdmission": "NO_GO",
    }


def main() -> None:
    if len(sys.argv) != 3:
        raise ValueError(
            "USAGE: python tools/fwn9_p9m_c16_c15_handoff.py "
            "/tmp/c16_native.log research/modulation9/protocol.json"
        )
    rows = [
        row.split("=", 1)[1]
        for row in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
        if row.startswith("FWN9_C16_NATIVE_AU_EVIDENCE=")
    ]
    if len(rows) != 1:
        raise ValueError("C16_C15_EXACTLY_ONE_SOURCE_ROW")
    out = handoff(json.loads(rows[0]), Path(sys.argv[2]))
    print("FWN9_C16_C15_HANDOFF=" + json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
