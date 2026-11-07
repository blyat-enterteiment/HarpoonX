"""Reconcile retained account-count declarations without inventing a free budget."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def audit(root: Path = ROOT) -> dict[str, Any]:
    files = ["research/compound_swing/protocol.json", "research/profit8/protocol.json",
             "evidence/profit8/closure.json", "evidence/multiasset8/run_01/report.json",
             "evidence/swing8/run_01/report.json", "evidence/macd30/run_01/report.json",
             "evidence/virtual_ab/unpurged_report.json", "evidence/virtual_ab/purged_report.json"]
    data = {name: json.loads((root / name).read_bytes()) for name in files}
    latest = data[files[0]]["budget"]
    unused = data[files[1]]["budget"]["unused_recent_partition_reservation"]
    additional = {name: len(data[name]["accounts"]) for name in files[3:]}
    total_reserved = latest["reserved_after"] + sum(additional.values())
    return {
        "schema": "HARPOON_RESEARCH_BUDGET_RECONCILIATION_1",
        "unit": "policy_cost_account_including_controls_as_in_inherited_reservations",
        "last_declared_reserved": latest["reserved_after"], "ceiling": latest["limit"],
        "unincorporated_account_counts": additional,
        "reserved_plus_unincorporated": total_reserved,
        "documented_unused_profit8_reservation": unused,
        "estimate_even_if_unused_reservation_released": total_reserved - unused,
        "unused_reservation_actually_released": False,
        "global_history_complete": False,
        "deduplication_of_equivalent_cash_controls_certified": False,
        "new_measurements_allowed": False,
        "status": "BLOCKED_UNRECONCILED_GLOBAL_BUDGET",
        "reason": "The 119/128 snapshot omits 32 later/imported account measurements. Even releasing 20 unused slots gives 131, before global provenance or duplicate-control reconciliation. Do not change counting rules after seeing results to create capacity.",
        "exact_control_reproductions_and_measurement_bug_verification": "ALLOWED_NOT_NEW_POLICY_SEARCH",
        "sources_sha256": {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files},
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))
