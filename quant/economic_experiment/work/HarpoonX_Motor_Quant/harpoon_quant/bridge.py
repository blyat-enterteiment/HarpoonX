"""Normalize the Node coordinator's actual snapshot for the shared numerical engine."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .core import Config, allocate, features

NY = ZoneInfo("America/New_York")


def ms(v: float) -> str:
    return datetime.fromtimestamp(v / 1000, UTC).isoformat()


def bars(
    raw: list[dict[str, Any]],
    book: str,
    known: str,
    calendar: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    minutes = 15 if book == "crypto" else 5
    sessions = {s["date"]: s for s in (calendar or [])}
    if book != "crypto" and not sessions:
        raise ValueError("EXCHANGE_CALENDAR_REQUIRED")
    out = []
    for b in raw:
        at = datetime.fromisoformat(b["t"]).astimezone(UTC)
        local = at if book == "crypto" else at.astimezone(NY)
        end = at + timedelta(minutes=minutes)
        if book != "crypto":
            session = sessions.get(local.date().isoformat())
            if not session:
                continue
            opening = datetime.fromtimestamp(float(session["open"]) / 1000, UTC)
            closing = datetime.fromtimestamp(float(session["close"]) / 1000, UTC)
            if not opening <= at < end <= closing:
                continue
        out.append(
            {
                "start": at.isoformat(),
                "end": end.isoformat(),
                "known_at": known,
                "session": local.date().isoformat(),
                "slot": end.astimezone(local.tzinfo).strftime("%H:%M"),
                "close": float(b["c"]),
                "volume": float(b["v"]),
                "vwap": float(b["vw"]),
            }
        )
    return out


def from_runtime(raw: dict[str, Any], calibration: dict[str, Any]) -> dict[str, Any]:
    at = ms(raw["now"])
    market = raw["market"]
    oldcfg = raw["config"]
    qcfg = oldcfg.get("quant", {}).get("config", {})
    # Original account/risk policy remains an upper bound on the shared allocator.
    cfg = Config(
        **{
            **qcfg,
            "max_positions": oldcfg["maxPositions"],
            "gross_fraction": oldcfg["totalExposure"],
            "asset_fraction": oldcfg["assetExposure"],
            "factor_fraction": oldcfg["factorExposure"],
            "daily_loss_fraction": oldcfg["dailyLoss"],
            "drawdown_fraction": oldcfg["maxDrawdown"],
            "slippage_bps": oldcfg["slippageBps"],
            "max_quote_age_seconds": oldcfg["quoteAgeMs"] / 1000,
        }
    )
    rejected = {}
    normalized = []
    overlay = None
    optimizer = oldcfg.get("quant", {}).get("optimizer", {})
    if optimizer.get("enabled") and optimizer.get("statePath"):
        from .recursive import active_policy

        overlay = active_policy(
            optimizer["statePath"], raw.get("optimizer_binding", {}), at
        )
        if overlay and oldcfg.get("mode") != "paper":
            return {
                "status": "BLOCKED",
                "reason": "OPTIMIZER_POLICY_PAPER_ONLY",
                "selected": [],
                "execution_allowed": False,
            }
        if overlay and overlay.get("pause_entries"):
            return {
                "status": "BLOCKED",
                "reason": overlay.get("reason"),
                "selected": [],
                "execution_allowed": False,
            }
        if overlay:
            cfg = replace(
                cfg,
                min_robust_return_bps=max(
                    cfg.min_robust_return_bps, overlay["policy"]["quality_bps"]
                ),
            )

    def convert(
        symbol: str,
        asset: dict[str, Any],
        cid: str,
        signal: dict[str, Any] | None = None,
        qty: float | None = None,
    ) -> dict[str, Any]:
        book = asset["book"]
        underlying = asset.get("underlying", symbol) if book == "options" else symbol
        quote = market["quotes"][symbol]
        uq = market["quotes"][underlying]
        source_book = "crypto" if book == "crypto" else "equity"
        calendar = market.get("calendar")
        hist = bars(market["bars"].get(underlying, []), source_book, at, calendar)
        q = {
            "bid": uq["bid"],
            "ask": uq["ask"],
            "at": ms(uq["at"]),
            "known_at": ms(uq.get("received", uq["at"])),
        }
        benchmark = None
        if book in ("equity", "etf", "options"):
            benchmark = bars(market["bars"].get("SPY", []), "equity", at, calendar)
            if not benchmark:
                raise ValueError("SPY_BENCHMARK_REQUIRED")
        vector = features(hist, q, at, benchmark)
        lot = 1.0
        if book == "crypto":
            step = float(asset["step"])
            lot = max(
                float(asset["minQty"]),
                int((250 / max(quote["ask"], 1e-12)) / step) * step,
            )
        c = {
            "id": cid,
            "symbol": symbol,
            "underlying": underlying,
            "book": book,
            "factor": asset.get("factor", underlying),
            "currency": "USD",
            "side": "long",
            "asof": at,
            "known_at": at,
            "quote_at": ms(quote["at"]),
            "bid": float(quote["bid"]),
            "ask": float(quote["ask"]),
            "spot": float((uq["bid"] + uq["ask"]) / 2),
            "multiplier": float(asset.get("multiplier", 1)),
            "step": float(asset["step"]),
            "lot_qty": qty if qty is not None else lot,
            "features": vector,
            "entry": float(signal["entry"]) if signal else quote["bid"],
            "fee_per_side_usd": float(oldcfg["optionsFeePerContract"])
            if book == "options"
            else float(quote["ask"]) * float(oldcfg["cryptoFeeBps"]) / 10000
            if book == "crypto"
            else float(asset.get("fee_per_share_usd", 0)),
        }
        from .context import guard

        micro = guard(symbol, book, market, oldcfg, at, cfg.horizon_hours)
        c["microstructure"] = micro
        c["extra_slippage_bps_per_side"] = micro["extra_slippage_bps_per_side"]
        if signal:
            c["max_qty"] = float(signal["max_qty"]) * (
                overlay["policy"]["risk_scale"] if overlay else 1
            )
        if book == "options":
            snap = market.get("snapshots", {}).get(symbol, {})
            # No funding/lifecycle approval is inferred from a quote or model.
            c.update(
                iv=snap.get("impliedVolatility"),
                delta=snap.get("greeks", {}).get("delta"),
                rate=asset.get("rate"),
                dividend_yield=asset.get("dividend_yield"),
                strike=asset.get("strike"),
                right=asset.get("right"),
                style=asset.get("style", "american"),
                expiry_at=asset.get("expiry_at"),
                lifecycle_reviewed=asset.get("quant_lifecycle_reviewed", False),
            )
        return c

    for signal in raw["signals"]:
        cid = signal["plugin"] + "|" + signal["symbol"]
        try:
            normalized.append(
                convert(
                    signal["symbol"], market["assets"][signal["symbol"]], cid, signal
                )
            )
        except (KeyError, ValueError, TypeError) as exc:
            rejected[cid] = str(exc)
    holdings = []
    for p in raw.get("positions", []):
        symbol = next(
            (
                s
                for s in market["assets"]
                if s.replace("/", "") == p["symbol"].replace("/", "")
            ),
            p["symbol"],
        )
        try:
            q = float(p["qty"])
            if q <= 0:
                raise ValueError("SHORT_OR_NONPOSITIVE_POSITION")
            holdings.append(
                convert(symbol, market["assets"][symbol], "held|" + symbol, qty=q)
            )
        except (KeyError, ValueError, TypeError) as exc:
            return {
                "status": "BLOCKED",
                "selected": [],
                "execution_allowed": False,
                "reason": "UNMODELED_OPEN_INVENTORY:" + str(exc),
                "rejected": rejected,
                "liveApproved": False,
            }
    account = raw["account"]
    pending = sum(
        float(i["payload"]["qty"])
        * float(i["payload"].get("limit_price", 0))
        * float(market["assets"].get(i["symbol"], {}).get("multiplier", 1))
        for i in raw.get("pending", [])
        if i["kind"] == "entry"
    )
    eq = float(account["equity"])
    request = {
        "asof": at,
        "candidates": normalized,
        "holdings": holdings,
        "account": {
            "equity": eq,
            "cash": float(account["cash"]),
            "buying_power": float(account["buying_power"]),
            "pending_cash": pending,
            "daily_pnl": float(raw.get("daily_pnl", 0)),
            "drawdown_fraction": float(raw.get("drawdown_fraction", 0)),
        },
    }
    if not normalized:
        return {
            "status": "BLOCKED",
            "selected": [],
            "execution_allowed": False,
            "reason": "NO_CALIBRATED_RUNTIME_CANDIDATES",
            "rejected": rejected,
            "liveApproved": False,
        }
    result = allocate(request, calibration, cfg)
    result["rejected"].update(rejected)
    result["microstructure"] = {c["id"]: c["microstructure"] for c in normalized}
    result["optimizer_policy"] = overlay
    return result
