"""Run from repo root with PYTHONPATH=quant:tools. Never authorizes trading."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from harpoon_quant.compound import BOOKS, paired_growth
from harpoon_quant.multiasset import calibrate_fills
from harpoon_quant.remediation import economic_checks
from verify_swing8 import verify


def review(
    directory: Path, fills: Path | None = None, passive: Path | None = None
) -> dict:
    audit = verify(directory)
    report = json.loads((directory / "report.json").read_bytes())
    results = {}
    passive_accounts = json.loads(passive.read_bytes()) if passive else None
    for scenario in ("NOMINAL", "STRESS"):
        books = {}
        for book in BOOKS:
            key = scenario + "_" + book
            raw = gzip.decompress((directory / (key + ".json.gz")).read_bytes())
            if (
                hashlib.sha256(raw).hexdigest()
                != report["accounts"][key]["account_sha256"]
            ):
                raise ValueError("CHANGED_ACCOUNT:" + key)
            books[book] = json.loads(raw)
        totals, _ = paired_growth(books)
        results[scenario] = {
            **economic_checks(books["JOINT"]),
            "paired_log_growth": totals,
        }
        if passive_accounts is not None:
            # Use the same cash, daily marks and fixed-cost contract as the native books.
            control = passive_accounts[scenario]
            _, differences = paired_growth({**books, "EQUITY_ETF": control})
            results[scenario]["vs_passive_log_growth"] = float(differences[:, 1].sum())
            results[scenario]["checks"]["above_passive"] = (
                results[scenario]["vs_passive_log_growth"] > 0
            )
    costs = calibrate_fills(json.loads(fills.read_bytes())) if fills else None
    groups = costs["groups"] if costs else {}
    missing = [
        f"LIVE:{book}:{side}"
        for book in ("equity", "crypto")
        for side in ("buy", "sell")
        if not groups.get(f"LIVE:{book}:{side}", {}).get("live_cost_calibration_ready")
    ]
    passed = all(all(result["checks"].values()) for result in results.values())
    return {
        "economic_decision": "REQUIRES_FORWARD_REVIEW" if passed else "REJECT",
        "accounts": results,
        "ledger_verified": audit["verified"],
        "missing_cost_groups": missing,
        "outstanding": [
            "independently reconciled costs including unfilled orders",
            "risk-matched passive comparison",
            "untouched holdout and prospective decision receipts",
            "intrabar risk and concentration by sector",
        ],
        "level8_accredited": False,
        "execution_allowed": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--fills", type=Path)
    parser.add_argument("--passive", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            review(args.directory, args.fills, args.passive), indent=2, allow_nan=False
        )
    )
