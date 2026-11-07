"""Export causal campaign states; quote liquidity remains explicitly unobserved."""
from __future__ import annotations

import argparse
import gzip
import json
import math
from bisect import bisect_right
from pathlib import Path
from statistics import median
from typing import Any

from harpoon_quant.forensic_features import ForensicPanel
from harpoon_quant.technical_swing import BAR


class CampaignState:
    def __init__(self, dataset: dict[str, Any]) -> None:
        self.panel = ForensicPanel(dataset)
        self.splits = dataset.get("splitEvents", [])
        self.bars = {s["symbol"]: s["bars"] for s in dataset["series"]}
        self.times = {s: [b["availableAt"] for b in bars] for s, bars in self.bars.items()}
        for times in self.times.values():
            if times != sorted(times):
                raise ValueError("AVAILABILITY_ORDER")

    def last(self, symbol: str, at: int) -> dict[str, Any] | None:
        i = bisect_right(self.times[symbol], at) - 1
        return self.bars[symbol][i] if i >= 0 else None

    def volume(self, symbol: str, at: int) -> dict[str, Any]:
        last = self.last(symbol, at)
        i = bisect_right(self.panel.opens, at) - 1
        if last is None or i < 0:
            return {"rvol10": None, "volume10": None, "median_prior20": None}
        opening = self.panel.opens[i]
        end = (last["t"] - opening) // BAR + 1
        rv = (self.panel.rvol(symbol, i, end - 2, end, at)
              if last["t"] >= opening and at - last["availableAt"] <= BAR else None)
        if rv is None:
            return {"rvol10": None, "volume10": None, "median_prior20": None}
        total = sum(b["v"] for b in self.panel.panel._window(symbol, opening, end - 2, end, at))
        prior = [sum(b["v"] for b in self.panel.panel._window(symbol, self.panel.opens[j], end - 2, end, at))
                 for j in range(i - 20, i)]
        return {"rvol10": rv, "volume10": total, "median_prior20": median(prior)}

    def trace(self, trade: dict[str, Any], costs: dict[str, Any]) -> list[dict[str, Any]]:
        symbol = trade["symbol"]
        decision = trade["holdingClockStartedAt"]
        initial_stock, initial_sector = self.last(symbol, decision), self.last("XLK", decision)
        if initial_stock is None or initial_sector is None:
            raise ValueError("DECISION_REFERENCE")
        friction = (costs["spread_bps"] / 2 + costs["slippage_bps"]) / 10_000
        fee = costs["commission_usd_per_share_per_side"]
        risk, peak = trade["riskUsd"], 0.0
        previous_rvol: float | None = None
        result = []
        for mark in trade["marks"]:
            at = mark["at"]
            known = [e for e in trade["inventoryEvents"] if e["knownAt"] <= at]
            quantity = sum(e["quantityDelta"] for e in known)
            if quantity < 0:
                raise ValueError("NEGATIVE_KNOWN_INVENTORY")
            cash = sum(-e["quantityDelta"] * e["filledPrice"] - e["feeUsd"] for e in known)
            stock, sector = self.last(symbol, at), self.last("XLK", at)
            if stock is None or sector is None:
                raise ValueError("CURRENT_REFERENCE")
            # The retained equity replay uses USD 0.01 ticks for these two stocks.
            liquidation_price = math.floor(stock["c"] * (1 - friction) / .01 + 1e-8) * .01
            exit_cost = quantity * (stock["c"] - liquidation_price + fee)
            dividends = sum(d["amountUsd"] for d in trade["dividendEntitlements"] if d["exAt"] <= at)
            pnl = cash + quantity * liquidation_price - quantity * fee + dividends
            peak = max(peak, pnl)
            volume = self.volume(symbol, at)
            rv = volume["rvol10"]
            delta = math.log1p(rv) - math.log1p(previous_rvol) if rv is not None and previous_rvol is not None else None
            stock_factor = math.prod(e["ratio"] for e in self.splits if e["symbol"] == symbol
                                     and initial_stock["t"] < e["at"] <= stock["t"])
            sector_factor = math.prod(e["ratio"] for e in self.splits if e["symbol"] == "XLK"
                                      and initial_sector["t"] < e["at"] <= sector["t"])
            relative = math.log(stock["c"] * stock_factor / initial_stock["c"]) - math.log(
                sector["c"] * sector_factor / initial_sector["c"])
            result.append({"at_ms": at, "pnl_liquidation_estimated_r": pnl / risk,
                           "running_peak_estimated_r": peak / risk, "giveback_so_far_r": (peak - pnl) / risk,
                           "delta_log1p_rvol10": delta, "relative_from_decision_known_close": relative,
                           "hours_to_frozen_deadline": max(0.0, (trade["holdingDeadlineAt"] - at) / 3_600_000),
                           "remaining_quantity_known": quantity, "estimated_exit_cost_r": exit_cost / risk,
                           "price_available_at_ms": stock["availableAt"], "price_age_seconds": (at - stock["availableAt"]) / 1000,
                           **volume, "observed_quote_spread": None, "quote_liquidity_observed": False,
                           "fixed_cost_allocated_to_campaign": False})
            previous_rvol = rv
        return result


def export(dataset: Path, protocol: Path, corrected: Path, output: Path) -> None:
    panel = CampaignState(json.loads(dataset.read_bytes()))
    p = json.loads(protocol.read_bytes())
    records = {}
    for scenario in ("NOMINAL", "STRESS"):
        key = scenario + "_CONFIRMED"
        a = json.loads(gzip.decompress((corrected / (key + ".json.gz")).read_bytes()))
        records[key] = [{"id": t["id"], "states": panel.trace(t, p["scenarios"][scenario])} for t in a["funded"]]
    result = {"schema": "HARPOON_CAUSAL_CAMPAIGN_STATE_1", "accounts": records,
              "origin": "REUSED_HISTORICAL_MODELED_NO_EXECUTABLE_QUOTES", "fitted_model": False,
              "risk_denominator": "initial planned trade risk; not a gap-loss cap", "execution_allowed": False}
    output.write_bytes(gzip.compress((json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n").encode(), mtime=0))
    print(json.dumps({"campaign_records": sum(map(len, records.values())),
                      "states": sum(len(r["states"]) for rows in records.values() for r in rows)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--corrected", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    export(root / "evidence/residual_30_18_0/data/research_dataset.json",
           root / "research/technical_swing/protocol.json", args.corrected, args.output)
