"""Reproducible six-case engineering lab plus a separately labeled real probe.

Synthetic conditional laws are chosen deliberately. Their returns are not
estimates of attainable market returns, independent validation, or broker fills.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import tempfile
import time
from typing import Any

import numpy as np

from research.hf37.hf37_growth_gate import gate
from research.hf37.hf37_portfolio import (
    CheckpointStore,
    Costs,
    ModeledBook,
    Risk,
    canonical,
    digest,
    target_weights,
)
from research.hf37.hf37_predictor import (
    DAY_NS,
    Label,
    Quote,
    Trade,
    fit_return_model,
    pressure_features,
    shrunk_covariance,
)
from research.hf37.hf37_universe import SECTORS, manifest

CONFIG = Path(__file__).with_name("hf37_model_preregistered.json")
BASE_NS = 1_700_000_000_000_000_000  # Abstract synthetic clock, not exchange sessions.
POLICIES = ("CASH", "SECTOR", "WHALE_SECTOR")


def make_fixture(world: str, sessions: int = 180, seed: int = 3701) -> dict[str, Any]:
    if world not in ("PRESSURE_EDGE", "NULL", "REGIME_REVERSAL") or sessions < 4:
        raise ValueError("INVALID_SYNTHETIC_FIXTURE")
    rng = np.random.default_rng(seed)
    stocks = {s: sector for sector, (names, _) in SECTORS.items() for s in names}
    etfs = {etf: sector for sector, (_, etf) in SECTORS.items()}
    sectors = stocks | etfs
    symbols = sorted(sectors)
    alternative = {s: etf for names, etf in SECTORS.values() for s in names}
    mid = {s: 100.0 for s in symbols}
    rows, labels, returns = [], [], []
    for day in range(sessions):
        clock = BASE_NS + (day + 2) * DAY_NS
        sector_state = {sector: float(rng.uniform(-1, 1)) for sector in SECTORS}
        common = {sector: float(rng.normal(0, 0.005)) for sector in SECTORS}
        features, current, execution, future = {}, {}, {}, {}
        new_labels = []
        for s in symbols:
            m = mid[s]
            bid, ask = m * 0.9995, m * 1.0005
            latent = float(rng.uniform(-1, 1))
            baseline = [
                Trade(
                    clock - DAY_NS - j - 1,
                    clock - DAY_NS - j - 1,
                    m,
                    float(rng.uniform(5000, 90000)) / m,
                )
                for j in range(80)
            ]
            trades, quotes = [], []
            for j in range(30):
                stamp = clock - 60_000_000_000 + (j + 1) * 1_500_000_000
                q = Quote(
                    stamp - 1_000_000, stamp - 1_000_000, bid, ask, 100_000, 100_000
                )
                quotes.append(q)
                price = ask if rng.random() < (latent + 1) / 2 else bid
                trades.append(
                    Trade(stamp, stamp, price, float(rng.uniform(5000, 90000)) / price)
                )
            quotes.append(Quote(clock - 1, clock - 1, bid, ask, 100_000, 100_000))
            pressure = pressure_features(
                baseline, trades, quotes, clock - 60_000_000_000, clock
            )
            feature = pressure.feature if pressure.available and s in stocks else 0.0
            features[s] = {
                "sector": sector_state[sectors[s]],
                "pressure": feature,
                "pressure_available": pressure.available or s in etfs,
            }
            current[s] = quotes[-1]
            execution[s] = Quote(
                clock + 1_000_000_000, clock + 1_000_000_000, bid, ask, 100_000, 100_000
            )
            coefficient = 0.012 if world != "NULL" else 0.0
            if world == "REGIME_REVERSAL" and day >= sessions // 2:
                coefficient = -0.012
            r = math.expm1(
                0.003 * sector_state[sectors[s]]
                + coefficient * feature
                + common[sectors[s]]
                + float(rng.normal(0, 0.006 if s in stocks else 0.003))
            )
            future[s] = r
            new_labels.append(
                Label(
                    clock,
                    clock + DAY_NS,
                    clock + DAY_NS,
                    s,
                    sectors[s],
                    features[s]["sector"],
                    feature,
                    r,
                    s in etfs,
                )
            )
        rows.append(
            {
                "clock": clock,
                "features": features,
                "quotes": current,
                "execution": execution,
            }
        )
        labels.extend(new_labels)
        returns.append([future[s] for s in symbols])
        mid = {s: mid[s] * (1 + future[s]) for s in symbols}
    return {
        "rows": rows,
        "labels": labels,
        "returns": returns,
        "symbols": symbols,
        "sectors": sectors,
        "alternative": alternative,
        "world": world,
        "seed": seed,
    }


def run_case(
    fixture: dict[str, Any],
    cost_multiplier: int,
    checkpoint: Path,
    *,
    restart_at: int | None = None,
) -> dict[str, Any]:
    costs = Costs(fee_bps=float(cost_multiplier), impact_bps=float(2 * cost_multiplier))
    risk = Risk()
    config = json.loads(CONFIG.read_text())
    config_hash = digest(
        [
            config,
            fixture["world"],
            fixture["seed"],
            cost_multiplier,
            len(fixture["rows"]),
        ]
    )
    store = CheckpointStore(checkpoint, config_hash)
    books = {p: ModeledBook() for p in POLICIES}
    paths = {p: [20_000.0] for p in POLICIES}
    diagnostics = {
        p: {"retained": 0, "rejected_entries": 0, "halts": 0} for p in POLICIES
    }
    latency_ms = []
    resumed = False
    for day, row in enumerate(fixture["rows"]):
        clock, symbols = row["clock"], fixture["symbols"]
        available = [label for label in fixture["labels"] if label.known_ns <= clock]
        start = time.perf_counter()
        sector_model = fit_return_model(available, clock, whale=False)
        whale_model = fit_return_model(available, clock, whale=True)
        covariance = shrunk_covariance(
            fixture["returns"][max(0, day - 120) : day], len(symbols)
        )
        forecasts = {}
        for s in symbols:
            f = row["features"][s]
            model = whale_model if s in fixture["alternative"] else sector_model
            forecast = model.predict(f["sector"], f["pressure"], clock)
            if not f["pressure_available"]:
                forecast = replace(forecast, available=False)
            forecasts[s] = forecast
        for policy in POLICIES:
            book = books[policy]
            if policy == "CASH":
                weights = dict.fromkeys(symbols, 0.0)
                details = {
                    "retained_positions": 0,
                    "rejected_new_entries": len(symbols),
                    "risk_halt": False,
                }
            else:
                weights, details = target_weights(
                    symbols,
                    fixture["sectors"],
                    forecasts,
                    row["quotes"],
                    covariance,
                    book,
                    clock,
                    costs,
                    risk,
                    fixture["alternative"],
                    sector_only=policy == "SECTOR",
                )
            book.rebalance(
                f"session-{day}", clock, row["execution"], weights, costs, risk
            )
            value = book.wealth(row["execution"], costs, clock + 1_000_000_000)
            paths[policy].append(value)
            book.previous_close = value
            diagnostics[policy]["retained"] += details["retained_positions"]
            diagnostics[policy]["rejected_entries"] += details["rejected_new_entries"]
            diagnostics[policy]["halts"] += int(details["risk_halt"])
        latency_ms.append((time.perf_counter() - start) * 1000)
        state = {
            "books": {p: b.snapshot() for p, b in books.items()},
            "paths": paths,
            "diagnostics": diagnostics,
            "matured_labels": len(available),
        }
        store.save(
            "case", day, day - 1, {"clock": clock, "features": row["features"]}, state
        )
        if day == restart_at:
            loaded = CheckpointStore(checkpoint, config_hash).load("case")
            if loaded is None or loaded[0] != day:
                raise ValueError("RESTART_CHECKPOINT_MISSING")
            recovered = loaded[1]
            books = {p: ModeledBook.restore(v) for p, v in recovered["books"].items()}
            paths, diagnostics = recovered["paths"], recovered["diagnostics"]
            resumed = True
    last = fixture["rows"][-1]
    # Terminal liquidation uses an additional modeled quote, not a free exit.
    terminal_quotes = {
        s: replace(q, at_ns=q.at_ns + 1, known_ns=q.known_ns + 1)
        for s, q in last["execution"].items()
    }
    summaries = {}
    for policy, book in books.items():
        book.rebalance(
            "terminal-liquidation",
            last["clock"] + 1_000_000_000,
            terminal_quotes,
            dict.fromkeys(fixture["symbols"], 0.0),
            costs,
            risk,
        )
        final = book.wealth(terminal_quotes, costs, last["clock"] + 1_000_000_001)
        paths[policy][-1] = final
        peak, dd = 20_000.0, 0.0
        for value in paths[policy]:
            peak = max(peak, value)
            dd = max(dd, 1 - value / peak)
        signed_cash = 20_000.0 + sum(
            (1 if r["side"] == "SELL" else -1) * r["quantity"] * r["price"] - r["fee"]
            for r in book.receipts
        )
        if abs(signed_cash - book.cash) > 1e-6 or book.positions:
            raise ValueError("TERMINAL_LEDGER_RECONCILIATION")
        summaries[policy] = {
            "terminal_usd": final,
            "pnl_usd": final - 20_000,
            "geometric_per_session": math.expm1(
                math.log(final / 20_000) / len(fixture["rows"])
            ),
            "max_drawdown": dd,
            "fees_usd": book.fees,
            "turnover_multiple_initial": book.turnover / 20_000,
            "modeled_receipts": len(book.receipts),
            "holding_72h_breaches": book.hold_breaches,
            **diagnostics[policy],
        }
    return {
        "world": fixture["world"],
        "cost_multiplier": cost_multiplier,
        "config_sha256": config_hash,
        "summaries": summaries,
        "wealth_paths": paths,
        "restart_executed": resumed,
        "status": "SYNTHETIC_ENGINEERING_ONLY_NO_GO",
        "gate": gate(paths),
        "broker_receipts": 0,
        "orders_enabled": False,
        "benchmark_44_assets_ms": {
            "p50": float(np.median(latency_ms)),
            "p95": float(np.quantile(latency_ms, 0.95)),
        },
    }


def timestamp_ns(value: str) -> int:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("MISSING_UTC_OFFSET")
    epoch = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
    elapsed = parsed - epoch
    return (
        elapsed.days * 86400 + elapsed.seconds
    ) * 1_000_000_000 + parsed.microsecond * 1000


def real_probe(raw_dir: Path) -> dict[str, Any]:
    trade_path, quote_path = [
        raw_dir / f"aapl_20261015_{kind}.json" for kind in ("trades", "quotes")
    ]
    trade_raw, quote_raw = trade_path.read_bytes(), quote_path.read_bytes()
    ts, qs = json.loads(trade_raw), json.loads(quote_raw)
    start = timestamp_ns("2026-10-15T13:30:00Z")
    end = timestamp_ns("2026-10-15T13:31:00Z")
    latency = 100_000_000
    trades = [
        Trade(
            timestamp_ns(t["timestamp"]),
            timestamp_ns(t["timestamp"]) + latency,
            float(t["price"]),
            float(t["size"]),
        )
        for t in ts["trades"]["AAPL"]
    ]
    quotes, invalid = [], 0
    for q in qs["quotes"]["AAPL"]:
        item = Quote(
            timestamp_ns(q["timestamp"]),
            timestamp_ns(q["timestamp"]) + latency,
            float(q["bid_price"]),
            float(q["ask_price"]),
            float(q["bid_size"]),
            float(q["ask_size"]),
        )
        try:
            item.validate()
        except ValueError:
            invalid += 1
            continue
        quotes.append(item)
    middle = start + 30_000_000_000
    baseline = [t for t in trades if t.known_ns < middle]
    signal = [t for t in trades if t.at_ns >= middle and t.known_ns <= end + latency]
    features = pressure_features(baseline, signal, quotes, middle, end + latency)
    return {
        "status": "REAL_TAPE_PROCESSING_DIAGNOSTIC_NOT_ALPHA_VALIDATION",
        "symbol": "AAPL",
        "feed": "iex",
        "window": [ts["request"]["start"], ts["request"]["end"]],
        "trades": len(trades),
        "quotes": len(quotes),
        "invalid_quotes": invalid,
        "features": asdict(features),
        "combined_pressure_feature": features.feature,
        "trade_file_sha256": hashlib.sha256(trade_raw).hexdigest(),
        "quote_file_sha256": hashlib.sha256(quote_raw).hexdigest(),
        "receipt_clocks_observed": False,
        "assumed_latency_ms": 100,
        "timestamp_precision": "MICROSECONDS_FROM_CONNECTOR",
        "provider_pagination_exhausted_verified": False,
        "full_sip_coverage": False,
        "matured_forward_labels": 0,
        "forecast_calibrated": False,
        "modeled_portfolio_usd": 20000,
        "allocation": "CASH_INSUFFICIENT_CALIBRATION",
        "original_policy_available": False,
        "economic_gate": "NO_GO",
        "original_market_tape_drive_uploaded": False,
        "broker_receipts": 0,
        "holdout_november_2026_opened": False,
        "orders_enabled": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--real-raw", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    config = json.loads(CONFIG.read_text())
    result: dict[str, Any] = {
        "schema": "HF37_PORTFOLIO_MODEL_LAB_1",
        "config": config,
        "preregistered_config_sha256": digest(config),
        "universe": manifest(),
        "cases": [],
        "orders_enabled": False,
        "holdout_november_2026_opened": False,
        "economic_verdict": "NO_GO_NO_INDEPENDENT_REAL_PORTFOLIO_EVIDENCE",
    }
    with tempfile.TemporaryDirectory() as scratch:
        for world in config["synthetic_worlds"]:
            fixture = make_fixture(
                world, config["synthetic_sessions"], config["synthetic_seed"]
            )
            for multiplier in config["cost_multipliers"]:
                result["cases"].append(
                    run_case(
                        fixture,
                        multiplier,
                        Path(scratch) / f"{world}_{multiplier}.sqlite",
                        restart_at=89,
                    )
                )
    if args.real_raw:
        result["real_tape_probe"] = real_probe(args.real_raw)
    output = args.output / "hf37_portfolio_model_results.json"
    output.write_text(canonical(result) + "\n")
    print(
        canonical(
            {
                "result": str(output),
                "cases": len(result["cases"]),
                "config_sha256": result["preregistered_config_sha256"],
                "verdict": result["economic_verdict"],
            }
        )
    )


if __name__ == "__main__":
    main()
