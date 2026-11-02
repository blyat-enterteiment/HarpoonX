"""Observable L1 statistics and explicit, causal microstructure approximations."""

from __future__ import annotations

import math
from bisect import bisect_left
from datetime import datetime
from typing import Any

import numpy as np

from .core import digest, finite, timestamp

FEATURE_NAMES = (
    "spread_tw_bps",
    "spread_p95_bps",
    "imbalance_tw",
    "weighted_mid_deviation_bps",
    "ofi_l1_norm",
    "quote_updates_per_second",
    "signed_volume_ratio_proxy",
    "effective_spread_bps",
    "mid_realized_vol_bps",
    "quote_coverage_fraction",
)


def seconds(value: Any) -> float:
    if isinstance(value, (int, float)):
        return finite(value, "TIMESTAMP") / 1000
    return timestamp(str(value)).timestamp()


def pick(row: dict[str, Any], *keys: str, default: Any = None) -> Any:
    return next((row[k] for k in keys if k in row), default)


def normalize(row: dict[str, Any], kind: str, book: str = "equity") -> dict[str, Any]:
    event = pick(row, "t", "timestamp", "event_at")
    at = seconds(event)
    received = pick(row, "known_at", "received", default=event)
    out: dict[str, Any] = {"at": at, "known": seconds(received), "kind": kind}
    conditions = pick(row, "c", "conditions", default=[])
    conditions = [conditions] if isinstance(conditions, str) else conditions
    if not isinstance(conditions, list):
        raise ValueError("CONDITION_SCHEMA")
    out["conditions"] = conditions
    if kind == "quote":
        for key, aliases in {
            "bid": ("bp", "bid_price", "bid"),
            "ask": ("ap", "ask_price", "ask"),
            "bs": ("bs", "bid_size"),
            "as": ("as", "ask_size"),
        }.items():
            out[key] = finite(pick(row, *aliases), key, True)
        if out["ask"] <= out["bid"]:
            raise ValueError("LOCKED_OR_CROSSED_BBO")
        if book in ("equity", "etf") and any(c != "R" for c in conditions):
            raise ValueError("NONREGULAR_OR_UNKNOWN_QUOTE_CONDITION")
        # Alpaca changed stock quote size units on 2025-11-03. Never apply to options.
        units = row.get("size_unit")
        if units is None:
            units = (
                "round_lots"
                if book in ("equity", "etf") and str(event)[:10] < "2025-11-03"
                else "native"
            )
        if units == "round_lots":
            if book not in ("equity", "etf"):
                raise ValueError("STOCK_LOT_UNIT_ON_OTHER_ASSET")
            out["bs"] *= 100
            out["as"] *= 100
        elif units not in ("native", "shares", "contracts", "base_units"):
            raise ValueError("UNKNOWN_SIZE_UNIT")
        out["bid_exchange"] = pick(row, "bx", "bid_exchange")
        out["ask_exchange"] = pick(row, "ax", "ask_exchange")
    elif kind == "trade":
        out["price"] = finite(pick(row, "p", "price"), "TRADE_PRICE", True)
        out["size"] = finite(pick(row, "s", "size"), "TRADE_SIZE", True)
        out["id"] = pick(row, "i", "id")
        out["exchange"] = pick(row, "x", "exchange")
        if book in ("equity", "etf") and any(
            c not in ("@", "I", "F") for c in conditions
        ):
            raise ValueError("NONREGULAR_OR_UNKNOWN_TRADE_CONDITION")
    else:
        raise ValueError("EVENT_KIND")
    return out


def summarize(
    quotes: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    asof: str,
    *,
    book: str = "equity",
    feed: str = "sip",
    window_seconds: float = 300,
    max_quote_age: float = 2,
    clock: str = "LIVE_RECEIPT",
    origin: str = "OBSERVED",
) -> dict[str, Any]:
    if clock not in ("LIVE_RECEIPT", "EVENT_TIME_REPLAY"):
        raise ValueError("CLOCK_MODE")
    if origin not in ("OBSERVED", "SYNTHETIC_ENGINEERING_ONLY"):
        raise ValueError("ORIGIN_REQUIRED")
    if not 0 < window_seconds <= 86400 or not 0 < max_quote_age <= window_seconds:
        raise ValueError("WINDOW_DOMAIN")
    if len(quotes) + len(trades) > 100000:
        raise ValueError("EVENT_COMPUTE_CAP")
    end = timestamp(asof).timestamp()
    start = end - window_seconds
    rejected: dict[str, int] = {}
    rows: dict[str, list[dict[str, Any]]] = {"quote": [], "trade": []}
    for kind, raw in (("quote", quotes), ("trade", trades)):
        seen = set()
        for item in raw:
            try:
                r = normalize(item, kind, book)
                if not start <= r["at"] <= end or (
                    clock == "LIVE_RECEIPT" and r["known"] > end
                ):
                    continue
                identity = digest({k: v for k, v in r.items() if k != "known"})
                if identity in seen:
                    rejected["DUPLICATE"] = rejected.get("DUPLICATE", 0) + 1
                    continue
                seen.add(identity)
                rows[kind].append(r)
            except (ValueError, TypeError, KeyError) as exc:
                reason = str(exc)
                rejected[reason] = rejected.get(reason, 0) + 1
        rows[kind].sort(key=lambda r: (r["at"], r["known"]))
    qs, ts = rows["quote"], rows["trade"]
    values: dict[str, float | None] = dict.fromkeys(FEATURE_NAMES)
    receipt: dict[str, Any] = {
        "schema": "HARPOON_MICRO_L1_1",
        "asof": asof,
        "book": book,
        "feed": feed,
        "origin": origin,
        "clock": clock,
        "quote_events": len(qs),
        "trade_events": len(ts),
        "window_seconds": window_seconds,
        "rejected": rejected,
        "features": values,
        "execution_data_eligible": clock == "LIVE_RECEIPT"
        and origin == "OBSERVED"
        and feed not in ("indicative", "delayed_sip"),
        "approximations": [
            "OFI from observed best-level updates, not a full order book",
            "Trade aggressor from preceding BBO/tick rule, not observed order intent",
            "Weighted midpoint is a static L1 proxy, not a trained microprice",
            "No hidden liquidity, queue rank, cancellations or venue-wide depth inferred",
        ],
        "input_hash": digest({"quotes": quotes, "trades": trades}),
    }
    if len(qs) < 2:
        return {**receipt, "status": "INSUFFICIENT_QUOTES", "coverage_seconds": 0}
    times = np.array([q["at"] for q in qs])
    bid = np.array([q["bid"] for q in qs])
    ask = np.array([q["ask"] for q in qs])
    bs = np.array([q["bs"] for q in qs])
    az = np.array([q["as"] for q in qs])
    mid = (bid + ask) / 2
    weights = np.minimum(np.maximum(0, np.r_[times[1:], end] - times), max_quote_age)
    covered = float(weights.sum())
    denom = window_seconds
    if covered <= 0:
        return {**receipt, "status": "NO_DURATION_COVERAGE", "coverage_seconds": 0}

    def avg(v: np.ndarray) -> float:
        return float(np.average(v, weights=weights))

    spread = 10000 * (ask - bid) / mid
    imbalance = (bs - az) / (bs + az)
    weighted_mid = (ask * bs + bid * az) / (bs + az)
    e = (bid[1:] >= bid[:-1]) * bs[1:] - (bid[1:] <= bid[:-1]) * bs[:-1]
    e -= (ask[1:] <= ask[:-1]) * az[1:] - (ask[1:] >= ask[:-1]) * az[:-1]
    contiguous = np.diff(times) <= max_quote_age
    returns = np.diff(np.log(mid))[contiguous]
    values.update(
        spread_tw_bps=avg(spread),
        spread_p95_bps=float(np.quantile(spread, 0.95)),
        imbalance_tw=avg(imbalance),
        weighted_mid_deviation_bps=avg(10000 * (weighted_mid - mid) / mid),
        ofi_l1_norm=float(
            e[contiguous].sum()
            / (avg((bs + az) / 2) * math.sqrt(max(1, int(contiguous.sum()))))
        ),
        quote_updates_per_second=float(len(qs) / max(1, times[-1] - times[0])),
        mid_realized_vol_bps=float(10000 * np.sqrt(np.sum(returns**2))),
        quote_coverage_fraction=min(1.0, covered / denom),
    )
    signed = 0.0
    signed_size = 0.0
    effect = []
    used_sizes = []
    matched = 0
    last_price = None
    last_tick = 0
    for tr in ts:
        ix = (
            bisect_left(times, tr["at"]) - 1
        )  # Strictly prior: equal timestamps have unknown ordering.
        while ix >= 0 and clock == "LIVE_RECEIPT" and qs[ix]["known"] > tr["known"]:
            ix -= 1
        sign = 0
        tick = 0 if last_price is None else int(np.sign(tr["price"] - last_price))
        if tick:
            last_tick = tick
        if ix >= 0 and tr["at"] - times[ix] <= max_quote_age:
            matched += 1
            difference = tr["price"] - mid[ix]
            sign = int(np.sign(difference)) if abs(difference) > 1e-10 else last_tick
            effect.append(20000 * abs(difference) / mid[ix])
            used_sizes.append(tr["size"])
        if sign:
            signed += sign * tr["size"]
            signed_size += tr["size"]
        last_price = tr["price"]
    if signed_size:
        values["signed_volume_ratio_proxy"] = signed / signed_size
    if effect:
        values["effective_spread_bps"] = float(np.average(effect, weights=used_sizes))
    return {
        **receipt,
        "status": "MEASURED_L1",
        "coverage_seconds": float(times[-1] - times[0]),
        "covered_quote_seconds": covered,
        "matched_trades": matched,
        "trade_quote_match_fraction": matched / len(ts) if ts else None,
        "latest_quote_age_seconds": end - times[-1],
        "size_unit": "shares"
        if book in ("equity", "etf")
        else "contracts"
        if book == "options"
        else "base_units",
    }


def markouts(
    quotes: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    *,
    horizon_seconds: float = 1,
    book: str = "equity",
) -> list[dict[str, Any]]:
    """Future markouts are labeled outcomes only and never enter summarize()."""
    if horizon_seconds <= 0:
        raise ValueError("POSITIVE_HORIZON_REQUIRED")
    qs = sorted((normalize(q, "quote", book) for q in quotes), key=lambda q: q["at"])
    times = [q["at"] for q in qs]
    out = []
    for raw in trades:
        tr = normalize(raw, "trade", book)
        before = bisect_left(times, tr["at"]) - 1
        after = bisect_left(times, tr["at"] + horizon_seconds)
        if (
            before < 0
            or after >= len(qs)
            or times[after] - tr["at"] - horizon_seconds > 0.25
        ):
            continue
        arrival = (qs[before]["bid"] + qs[before]["ask"]) / 2
        future = (qs[after]["bid"] + qs[after]["ask"]) / 2
        side = int(np.sign(tr["price"] - arrival))
        if side:
            out.append(
                {
                    "label_end": datetime.fromtimestamp(
                        times[after], timestamp("2000-01-01T00:00:00+00:00").tzinfo
                    ).isoformat(),
                    "label_known_at": datetime.fromtimestamp(
                        max(tr["known"], qs[after]["known"]),
                        timestamp("2000-01-01T00:00:00+00:00").tzinfo,
                    ).isoformat(),
                    "signed_markout_bps": 10000 * side * (future - arrival) / arrival,
                    "use": "OUTCOME_ONLY_NOT_FEATURE",
                }
            )
    return out
