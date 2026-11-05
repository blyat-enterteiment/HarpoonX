"""Execute the preregistered shared-cash book ablation on frozen hourly data."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from harpoon_quant.compound import BOOKS, paired_growth
from harpoon_quant.swing import SwingLimits, replay
from residual_statistics import block_means
from run_swing8 import inputs
from verify_swing8 import verify

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "research/compound_swing/protocol.json"
SHA = "ed4c0c1bda06bbac03568cb6000dcf995535ca4c4190b6afc251b319cfa2db9f"


def write(file: Path, value: Any) -> None:
    file.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")


def run(output: Path) -> dict[str, Any]:
    if hashlib.sha256(PROTOCOL.read_bytes()).hexdigest() != SHA:
        raise ValueError("UNREGISTERED_PROTOCOL")
    p = json.loads(PROTOCOL.read_bytes())
    hourly, daily, sessions, actions, start, end, _, manifest = inputs()
    expected = json.loads((ROOT / p["data_manifest"]).read_bytes())
    if manifest != expected["input_sha256"] or set(hourly) != set(p["assets"]):
        raise ValueError("REGISTERED_SOURCE_MISMATCH")
    output.mkdir(parents=True, exist_ok=False)
    limits = SwingLimits(
        p["gross_fraction"],
        p["asset_fraction"],
        p["entry_risk_fraction"],
        p["open_risk_fraction"],
        p["drawdown_halt"],
    )
    summary: dict[str, Any] = {
        "schema": p["schema"],
        "input_sha256": manifest,
        "protocol_sha256": SHA,
        "accounts": {},
        "comparisons": {},
        "level8_accredited": False,
        "observed_live_fills": 0,
        "execution_allowed": False,
        "fresh_holdout": False,
    }
    economic = True
    positive_bounds = True
    for scenario in p["scenarios"]:
        stress = scenario == "STRESS"
        books = {}
        for name in BOOKS:
            symbols = sorted(
                s
                for s in hourly
                if name == "JOINT"
                or (name == "EQUITY_ETF" and "/" not in s)
                or (name == "CRYPTO" and "/" in s)
            )
            a = replay(
                {s: hourly[s] for s in symbols},
                {s: daily[s] for s in symbols},
                sessions,
                actions,
                "CASH" if name == "CASH" else "BREAKOUT",
                stress,
                start,
                end,
                limits=limits,
            )
            key = scenario + "_" + name
            raw = json.dumps(
                a, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
            (output / (key + ".json.gz")).write_bytes(gzip.compress(raw, mtime=0))
            trades = a["trades"]
            summary["accounts"][key] = {
                "net_usd": a["net_usd"],
                "terminal_usd": a["terminal_usd"],
                "fixed_usd": a["fixed_cost_usd"],
                "return_pct": 100 * (a["terminal_usd"] / a["initial_usd"] - 1),
                "drawdown": a["hour_grid_drawdown"],
                "trades": len(trades),
                "crypto_trades": sum(t["book"] == "crypto" for t in trades),
                "max_entry_gross": a["max_entry_gross_fraction"],
                "max_entry_open_risk": a["max_entry_stop_risk_fraction"],
                "max_hold_hours": max((t["holding_hours"] for t in trades), default=0),
                "account_sha256": hashlib.sha256(raw).hexdigest(),
            }
            books[name] = a
        totals, matrix = paired_growth(books)
        bounds = {}
        for block in (5, 20):
            draws = block_means(matrix, block, 20000, 319)
            lower = np.quantile(draws, 0.05 / 16, axis=0, method="lower")
            bounds[str(block)] = dict(zip(totals, lower.tolist(), strict=True))
            positive_bounds &= bool(np.all(lower > 0))
        joint = books["JOINT"]
        economic &= (
            joint["net_usd"] > 0 and joint["hour_grid_drawdown"] <= p["drawdown_halt"]
        )
        summary["comparisons"][scenario] = {
            "total_log_growth": totals,
            "lower_mean_daily_log_growth": bounds,
            "marginal_crypto_usd": joint["terminal_usd"]
            - books["EQUITY_ETF"]["terminal_usd"],
            "marginal_equity_usd": joint["terminal_usd"]
            - books["CRYPTO"]["terminal_usd"],
        }
    summary["decision"] = (
        "REJECT"
        if not economic
        else "FORWARD_REVIEW_ONLY"
        if positive_bounds
        else "INSUFFICIENT_EVIDENCE"
    )
    write(output / "report.json", summary)
    audit = verify(output)
    write(output / "audit.json", audit)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    print(run(parser.parse_args().output_dir.resolve())["decision"])
