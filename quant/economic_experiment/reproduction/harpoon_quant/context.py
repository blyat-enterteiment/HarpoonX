"""Live L1 entry guard and a separately scheduled calibration registry cycle."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .bridge import bars
from .core import digest, timestamp
from .curves import CurveStore, surface
from .microstructure import summarize
from .regimes import evaluate_regime, regime_features
from .support import evaluate_support


def guard(
    symbol: str,
    book: str,
    market: dict[str, Any],
    cfg: dict[str, Any],
    asof: str,
    horizon: float,
) -> dict[str, Any]:
    options = cfg.get("quant", {}).get("microstructure", {})
    if not options.get("enabled"):
        return {"status": "DISABLED", "extra_slippage_bps_per_side": 0.0}
    data = market.get("micro_data", {}).get(symbol, {})
    feed = (
        "us" if book == "crypto" else "opra" if book == "options" else cfg["stockFeed"]
    )
    if data and data.get("feed") != feed:
        raise ValueError("MICRO_FEED_MISMATCH")
    result = summarize(
        data.get("quotes", []),
        data.get("trades", []),
        asof,
        book=book,
        feed=feed,
        window_seconds=options.get("windowSeconds", 300),
        max_quote_age=options.get("maxQuoteAgeSeconds", 5),
    )
    result["sampling_schema"] = data.get("sampling_schema", "UNKNOWN")
    result["omitted_events"] = data.get("omitted_events", 0)
    result["extra_slippage_bps_per_side"] = 0.0
    ready = (
        result["status"] == "MEASURED_L1"
        and result["quote_events"] >= options.get("minQuoteEvents", 20)
        and result["coverage_seconds"] >= options.get("minCoverageSeconds", 60)
        and result["features"]["quote_coverage_fraction"]
        >= options.get("minWindowCoverageFraction", 0.5)
        and result["latest_quote_age_seconds"] <= options.get("maxQuoteAgeSeconds", 5)
    )
    if not ready:
        if options.get("required", True):
            raise ValueError("MICRO_WARMUP_OR_COVERAGE:" + symbol)
        return {**result, "support_status": "WARMUP_SHADOW_ONLY"}
    model_path = options.get("modelFile")
    if not model_path or not Path(model_path).is_file():
        return {**result, "support_status": "UNCALIBRATED_NO_SUPPORT_ADJUSTMENT"}
    model = json.loads(Path(model_path).read_text())
    models = (
        model.get("models", [])
        if model.get("schema") == "HARPOON_SUPPORT_BUNDLE_1"
        else [model]
    )
    if not isinstance(models, list) or len(models) > 128:
        raise ValueError("SUPPORT_BUNDLE_SCHEMA")
    matches = []
    for item in models:
        if item.get("schema") != "HARPOON_SUPPORT_1" or item.get(
            "artifact_hash"
        ) != digest({k: v for k, v in item.items() if k != "artifact_hash"}):
            raise ValueError("SUPPORT_ARTIFACT_INTEGRITY")
        if (
            item["feed"] == feed
            and item["book_scope"] == book
            and item["sampling_schema"] == result["sampling_schema"]
            and (not item["symbol_scope"] or symbol in item["symbol_scope"])
        ):
            matches.append(item)
    if not matches:
        return {**result, "support_status": "NO_CALIBRATED_MODEL_FOR_DOMAIN"}
    if len(matches) != 1:
        raise ValueError("AMBIGUOUS_SUPPORT_MODELS_FOR_DOMAIN")
    model = matches[0]
    scored = evaluate_support(
        model,
        result["features"],
        asof,
        feed,
        horizon,
        result["sampling_schema"],
        book,
        symbol,
    )
    result["support"] = scored
    if scored["operational"] and model["anomaly_validated"] and scored["anomaly"]:
        raise ValueError("MICRO_SUPPORT_OUT_OF_DISTRIBUTION:" + symbol)
    if scored["operational"]:
        result["extra_slippage_bps_per_side"] = scored["cost_extra_roundtrip_bps"] / 2
    return result


def resample_15min(
    rows: list[dict[str, Any]], native_minutes: int
) -> list[dict[str, Any]]:
    if native_minutes == 15:
        return rows
    if native_minutes != 5:
        raise ValueError("UNSUPPORTED_NATIVE_BAR_SIZE")
    buckets = defaultdict(list)
    for b in rows:
        start = timestamp(b["start"])
        bucket = int(start.timestamp()) // 900 * 900
        buckets[(b["session"], bucket)].append(b)
    out = []
    for (session, bucket), group in sorted(buckets.items()):
        group.sort(key=lambda b: timestamp(b["start"]))
        if len(group) != 3 or [timestamp(b["start"]).timestamp() for b in group] != [
            bucket,
            bucket + 300,
            bucket + 600,
        ]:
            continue
        out.append(
            {
                "start": datetime.fromtimestamp(bucket, UTC).isoformat(),
                "end": group[-1]["end"],
                "known_at": max(timestamp(b["known_at"]) for b in group).isoformat(),
                "session": session,
                "close": group[-1]["close"],
                "volume": sum(b["volume"] for b in group),
            }
        )
    return out


def context_from_runtime(raw: dict[str, Any]) -> dict[str, Any]:
    at = datetime.fromtimestamp(raw["now"] / 1000, UTC).isoformat()
    cfg, market = raw["config"], raw["market"]
    options = cfg.get("quant", {}).get("microstructure", {})
    output: dict[str, Any] = {
        "status": "CALIBRATION_CONTEXT",
        "asof": at,
        "microstructure": {},
        "trade_authorization": False,
        "execution_allowed": False,
        "selected": [],
    }
    for symbol, asset in market["assets"].items():
        try:
            output["microstructure"][symbol] = guard(
                symbol,
                asset["book"],
                market,
                cfg,
                at,
                cfg.get("quant", {}).get("config", {}).get("horizon_hours", 24),
            )
        except (ValueError, KeyError, TypeError, OSError) as exc:
            output["microstructure"][symbol] = {
                "status": "NOT_READY",
                "reason": str(exc),
            }
    maximum = min(48, max(2, int(options.get("curveMaxSymbols", 12))))
    held = [p["symbol"] for p in raw.get("positions", [])]
    eligible = [
        s
        for s, a in market["assets"].items()
        if a["book"] in ("equity", "etf", "crypto")
    ]
    # Never mix IEX equity returns into a curve labeled as SIP.
    feed = "equity:" + cfg.get("stockFeed", "UNKNOWN") + ";crypto:us;bars:15Min"
    priority = list(
        dict.fromkeys([s for s in ["SPY", *held, *sorted(eligible)] if s in eligible])
    )
    selected = priority[:maximum]
    panel = {}
    for symbol in selected:
        try:
            book = market["assets"][symbol]["book"]
            normalized = bars(
                market["bars"].get(symbol, []), book, at, market.get("calendar")
            )
            if len(normalized) >= 96:
                panel[symbol] = resample_15min(
                    normalized, 15 if book == "crypto" else 5
                )
        except (ValueError, KeyError, TypeError) as exc:
            output.setdefault("curve_rejected", {})[symbol] = str(exc)
    output["curve_scope"] = {
        "requested": selected,
        "excluded_by_budget": priority[maximum:],
        "normalized_symbols": sorted(panel),
    }
    try:
        curve = surface(
            panel,
            at,
            feed=feed,
            windows=(32, 64),
            lags=(-3, -1, 0, 1, 3),
            bar_seconds=900,
        )
        db_path = options.get("registryPath")
        if not db_path:
            raise ValueError("CURVE_REGISTRY_PATH_REQUIRED")
        store = CurveStore(db_path)
        try:
            neighbors = store.nearest(
                curve, at, embargo_seconds=options.get("curveEmbargoSeconds", 86400)
            )
            identity = store.add(curve, at)
        finally:
            store.close()
        output["curve"] = {
            "status": "STORED",
            "id": identity,
            "schema_hash": curve["schema_hash"],
            "dimension": len(curve["vector"]),
            "spectrum": curve["spectrum"],
            "neighbors": neighbors,
            "diagnostics": curve["diagnostics"],
        }
        shape = regime_features(curve)
        output["curve"]["regime_features"] = shape
        regime_path = options.get("regimeModelFile")
        if regime_path and Path(regime_path).is_file():
            try:
                output["curve"]["regime_support"] = evaluate_regime(
                    json.loads(Path(regime_path).read_text()), shape, at
                )
            except (ValueError, KeyError, TypeError, OSError) as exc:
                output["curve"]["regime_support"] = {
                    "status": "NOT_READY",
                    "reason": str(exc),
                }
        else:
            output["curve"]["regime_support"] = {"status": "UNCALIBRATED"}
    except (ValueError, KeyError, TypeError, OSError) as exc:
        output["curve"] = {"status": "NOT_READY", "reason": str(exc)}
    return output
