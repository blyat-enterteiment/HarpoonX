"""File-based calibration and bounded recursive selection; no broker mutations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .curves import CurveStore, surface
from .data_client import AlpacaData
from .microstructure import summarize
from .performance import report
from .recursive import tick
from .regimes import evaluate_regime, fit_regime
from .support import evaluate_support, fit_support


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "action",
        choices=(
            "collect",
            "micro",
            "curves",
            "neighbors",
            "support-fit",
            "support-eval",
            "registry-get",
            "performance",
            "optimize",
            "regime-fit",
            "regime-eval",
        ),
    )
    p.add_argument("--input", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--model", type=Path)
    p.add_argument("--db", type=Path)
    p.add_argument("--available-at")
    p.add_argument("--known-at")
    p.add_argument("--symbols")
    p.add_argument("--kind", choices=("quotes", "trades", "bars"), default="quotes")
    p.add_argument("--book", default="equity")
    p.add_argument("--feed", default="sip")
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--id")
    p.add_argument("--max-pages", type=int, default=30)
    p.add_argument("--embargo-seconds", type=float, default=86400)
    a = p.parse_args()
    db = None
    try:
        data = json.loads(a.input.read_text()) if a.input else {}
        result: Any
        if a.action == "performance":
            result = report(data)
        elif a.action == "optimize":
            result = tick(
                data.get("panel"),
                data["config"],
                data["binding"],
                data["asof"],
                paper=data.get("paper", False),
            )
        elif a.action == "collect":
            if not a.symbols or not a.start or not a.end:
                raise ValueError("SYMBOLS_START_END_REQUIRED")
            result = AlpacaData().collect(
                a.symbols.split(","),
                a.kind,
                a.start,
                a.end,
                book=a.book,
                feed=a.feed,
                max_pages=a.max_pages,
            )
        elif a.action == "micro":
            result = summarize(**data)
        elif a.action == "curves":
            result = surface(**data)
            if a.db:
                if not a.known_at:
                    raise ValueError("KNOWN_AT_REQUIRED_FOR_REGISTRY")
                db = CurveStore(a.db)
                result["registry_id"] = db.add(result, a.known_at)
        elif a.action in ("neighbors", "registry-get"):
            if not a.db:
                raise ValueError("DB_REQUIRED")
            db = CurveStore(a.db)
            if a.action == "registry-get":
                if not a.id:
                    raise ValueError("REGISTRY_ID_REQUIRED")
                result = db.get(a.id)
            else:
                if not a.available_at:
                    raise ValueError("AVAILABLE_AT_REQUIRED")
                result = db.nearest(
                    data, a.available_at, embargo_seconds=a.embargo_seconds
                )
        elif a.action == "regime-fit":
            if not a.available_at:
                raise ValueError("AVAILABLE_AT_REQUIRED")
            result = fit_regime(data, a.available_at)
        elif a.action == "regime-eval":
            if not a.model or not a.available_at:
                raise ValueError("REGIME_MODEL_AND_AVAILABLE_AT_REQUIRED")
            result = evaluate_regime(
                json.loads(a.model.read_text()), data, a.available_at
            )
        elif a.action == "support-fit":
            if not a.available_at:
                raise ValueError("AVAILABLE_AT_REQUIRED")
            result = fit_support(data, a.available_at)
        else:
            if not a.model:
                raise ValueError("SUPPORT_MODEL_REQUIRED")
            result = evaluate_support(json.loads(a.model.read_text()), **data)
        output = json.dumps(result, allow_nan=False, sort_keys=True)
        if a.output:
            a.output.parent.mkdir(parents=True, exist_ok=True)
            a.output.write_text(output + "\n")
        else:
            print(output)
    except (ValueError, KeyError, TypeError, ArithmeticError, OSError) as exc:
        print(
            json.dumps(
                {"status": "ERROR", "reason": str(exc), "trade_authorization": False}
            )
        )
        raise SystemExit(2) from None
    finally:
        if db:
            db.close()


if __name__ == "__main__":
    main()
