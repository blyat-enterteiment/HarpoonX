"""Run from repo root with PYTHONPATH=quant:tools. Never authorizes trading."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from harpoon_quant.compound import BOOKS, paired_growth
from harpoon_quant.multiasset import calibrate_fills
from harpoon_quant.qualification import qualify_history
from harpoon_quant.remediation import economic_checks
from run_swing8 import response
from verify_swing8 import verify


def review(
    directory: Path,
    fills: Path | None = None,
    passive: Path | None = None,
    *,
    level8: bool = False,
) -> dict:
    audit = verify(directory)
    report = json.loads((directory / "report.json").read_bytes())
    expected = {
        scenario + "_" + book for scenario in ("NOMINAL", "STRESS") for book in BOOKS
    }
    if set(report["accounts"]) != expected:
        raise ValueError("EIGHT_FUNDED_ACCOUNTS_REQUIRED")
    # Older ledgers omitted the symbol in DIV_EX. Bind it to the already
    # hash-verified provider action receipt, never guess from an ex-date.
    root = Path(__file__).resolve().parents[1]
    action_path = "evidence/residual_30_18_0/data/raw/corporate_actions.json"
    if action_path not in report["input_sha256"]:
        raise ValueError("CORPORATE_ACTION_SOURCE_REQUIRED")
    dividends = response(root / action_path)["announcements"]["cash_dividends"]
    symbols = {}
    for action in dividends:
        receipt, symbol = action["id"], action["symbol"]
        if receipt in symbols:
            raise ValueError("DUPLICATE_DIVIDEND_SOURCE_RECEIPT")
        symbols[receipt] = symbol
    results = {}
    scenarios = {}
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
            **economic_checks(books["JOINT"], dividend_symbols=symbols),
            "paired_log_growth": totals,
        }
        scenarios[scenario] = books
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
    result = {
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
    if level8:
        result["qualification"] = qualify_history(scenarios, dividend_symbols=symbols)
        # Bind the review to the bytes actually consumed, including diagnostics.
        sources = [
            "quant/harpoon_quant/qualification.py",
            "quant/harpoon_quant/remediation.py",
            "quant/harpoon_quant/compound.py",
            "quant/harpoon_quant/multiasset.py",
            "quant/harpoon_quant/core.py",
            "quant/harpoon_quant/roadmap9/forward.py",
            "tools/review_compound_evidence.py",
            "tools/run_swing8.py",
            "tools/verify_swing8.py",
        ]
        result["source_sha256"] = {
            p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in sources
        }
        result["input_sha256"] = report["input_sha256"]
        result["account_sha256"] = {
            k: v["account_sha256"] for k, v in report["accounts"].items()
        }
        result["report_sha256"] = hashlib.sha256(
            (directory / "report.json").read_bytes()
        ).hexdigest()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--fills", type=Path)
    parser.add_argument("--passive", type=Path)
    parser.add_argument(
        "--level8", action="store_true", help="Recompute the eight research gates"
    )
    parser.add_argument(
        "--require-level8",
        action="store_true",
        help="Exit 2 if level 8 is not accredited",
    )
    args = parser.parse_args()
    result = review(
        args.directory,
        args.fills,
        args.passive,
        level8=args.level8 or args.require_level8,
    )
    print(json.dumps(result, indent=2, allow_nan=False))
    if args.require_level8 and not result["level8_accredited"]:
        raise SystemExit(2)
