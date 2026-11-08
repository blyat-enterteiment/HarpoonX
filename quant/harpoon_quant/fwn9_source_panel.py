"""P9M-B: signed offline evidence, complete daily marks and opportunity grid.
Engineering fixtures never establish genuinely observed broker provenance.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, cast

from .fwn9_observed_gate import (
    CASH, _money, _need, _utc, audit_receipt_tape, receipt_sha256,
)
from .recursive import Journal

SCHEMA = "HARPOON_FWN9_P9M_B_PANEL_1"
SYMBOLS = ("SYNA", "SYNB")


def digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def signing_bytes(panel: dict[str, Any]) -> bytes:
    body = {key: value for key, value in panel.items() if key != "signature_b64"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def audit_panel(tape: dict[str, Any], panel: dict[str, Any],
                *, trusted_public_keys: Mapping[str, bytes],
                native_checkpoint_sha256: str, now: str) -> dict[str, Any]:
    _need(isinstance(panel, dict) and panel.get("schema") == SCHEMA, "B_SCHEMA")
    _need("public_key" not in panel, "B_UNTRUSTED_PAYLOAD_KEY")
    signer = cast(str, panel.get("attestor_id"))
    _need(isinstance(signer, str) and signer in trusted_public_keys,
          "B_TRUST_ROOT_MISSING")
    key = trusted_public_keys[signer]
    _need(isinstance(key, bytes) and len(key) == 32, "B_TRUST_KEY_LENGTH")
    signature = cast(str, panel.get("signature_b64"))
    _need(isinstance(signature, str), "B_SIGNATURE_MISSING")
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        sig = base64.b64decode(signature, validate=True)
        _need(len(sig) == 64, "B_SIGNATURE_LENGTH")
        Ed25519PublicKey.from_public_bytes(key).verify(sig, signing_bytes(panel))
    except (ValueError, binascii.Error, InvalidSignature) as exc:
        raise ValueError("P9M_B_INVALID_SIGNATURE") from exc
    except ImportError as exc:
        raise ValueError("P9M_B_CRYPTOGRAPHY_REQUIRED") from exc
    _need(panel.get("batch_id") == tape.get("batch_id") and
          panel.get("native_checkpoint_sha256") == native_checkpoint_sha256 and
          panel.get("tape_sha256") == digest(tape) and
          panel.get("receipt_sha256") == receipt_sha256(tape["events"]) and
          panel.get("label_sha256") == receipt_sha256(tape["labels"]),
          "B_SIGNED_TAPE_BINDING")
    proof = audit_receipt_tape(
        tape, native_checkpoint_sha256=native_checkpoint_sha256,
        externally_pinned_receipt_sha256=panel["receipt_sha256"], now=now)
    days: list[str] = tape["development_days"]
    marks = cast(list[dict[str, Any]], panel.get("marks"))
    opps = cast(list[dict[str, Any]], panel.get("opportunities"))
    _need(isinstance(marks, list) and len(marks) == 2 * len(days),
          "B_MARK_COVERAGE")
    weekdays = [d for d in days if date.fromisoformat(d).weekday() < 5]
    _need(isinstance(opps, list) and len(opps) == 2 * len(weekdays),
          "B_UNIVERSE_COVERAGE")
    prices: dict[tuple[str, str], Decimal] = {}
    previous: dict[str, Decimal] = {}
    for day in days:
        subset = [m for m in marks if isinstance(m, dict) and m.get("day") == day]
        _need(len(subset) == 2, "B_DAY_MARK_COUNT")
        for row in subset:
            sym = row.get("symbol")
            _need(sym in SYMBOLS and (day, sym) not in prices,
                  "B_UNIQUE_MARK")
            assert isinstance(sym, str)
            known = _utc(row.get("known_at"))
            as_of = _utc(row.get("as_of"))
            _need(as_of <= known <= _utc(day + "T23:59:59Z") <= _utc(now),
                  "B_CAUSAL_MARK")
            p = _money(row.get("price"), positive=True)
            if date.fromisoformat(day).weekday() < 5:
                _need(row.get("kind") == "OBSERVED_QUOTE" and
                      as_of.date().isoformat() == day, "B_SESSION_MARK")
            else:
                _need(row.get("kind") == "CARRY_FORWARD" and
                      as_of.date().isoformat() < day and
                      sym in previous and p == previous[sym],
                      "B_WEEKEND_CARRY")
            previous[sym] = p
            prices[day, sym] = p
    orders: dict[tuple[str, str], list[str]] = defaultdict(list)
    symbols: dict[str, str] = {}
    for e in tape["events"]:
        if e["type"] == "SIGNAL":
            day = _utc(e["effective_at"]).date().isoformat()
            orders[day, e["symbol"]].append(e["order_id"])
            symbols[e["order_id"]] = e["symbol"]
    _need(all(d in weekdays for d, _ in orders), "B_UNCOVERED_CLOSED_DAY_SIGNAL")
    opportunities: set[tuple[str, str]] = set()
    for row in opps:
        _need(isinstance(row, dict), "B_OPPORTUNITY_SHAPE")
        d, s = cast(str, row.get("day")), row.get("symbol")
        _need(isinstance(d, str) and d in weekdays and s in SYMBOLS and
              (d, s) not in opportunities, "B_OPPORTUNITY_DUP_OR_FOREIGN")
        assert isinstance(s, str)
        _need(_utc(d + "T21:00:00Z") <= _utc(row.get("known_at")) <=
              _utc(d + "T23:59:59Z") <= _utc(now), "B_OPPORTUNITY_CLOCK")
        ids = sorted(orders.get((d, s), []))
        _need(row.get("signal_order_ids") == ids and
              row.get("status") == ("SIGNALS" if ids else "NO_SIGNAL"),
              "B_OPPORTUNITY_SIGNAL_MISMATCH")
        opportunities.add((d, s))
    _need(all((d, s) in opportunities for d in weekdays for s in SYMBOLS),
          "B_MISSING_OPPORTUNITY")
    events = tape["events"]
    qty: dict[str, int] = defaultdict(int)
    cash = CASH
    high = CASH
    dd = Decimal(0)
    previous_equity = CASH
    worst: Decimal | None = None
    equity_rows = []
    cursor = 0
    for day in days:
        clock = _utc(day + "T23:59:59Z")
        while cursor < len(events) and _utc(events[cursor]["known_at"]) <= clock:
            e = events[cursor]
            if e["type"] in ("ENTRY_FILL", "EXIT_FILL"):
                s = symbols[e["order_id"]]
                n = e["quantity"]
                value = Decimal(n) * _money(e["price"])
                fee = _money(e["fee_usd"])
                if e["type"] == "ENTRY_FILL":
                    cash -= value + fee
                    qty[s] += n
                else:
                    cash += value - fee
                    qty[s] -= n
                _need(qty[s] >= 0 and cash >= 0, "B_UNFUNDED_INVENTORY")
            cursor += 1
        cash -= Decimal(1)  # M9 nominal fixed cost every calendar date
        _need(cash >= 0, "B_UNFUNDED_FIXED_COST")
        equity = cash + sum((Decimal(qty[s]) * prices[day, s]
                             for s in SYMBOLS), Decimal(0))
        high = max(high, equity)
        dd = max(dd, (high - equity) / high)
        if day in weekdays:
            change = equity - previous_equity
            worst = change if worst is None else min(worst, change)
        equity_rows.append({"date": day, "equity_usd": str(equity)})
        previous_equity = equity
    _need(cursor == len(events) and all(n == 0 for n in qty.values()),
          "B_UNCLOSED_INVENTORY")
    gains = [max(Decimal(str(x["net_usd"])), Decimal(0))
             for x in tape["labels"]]
    total_positive = sum(gains, Decimal(0))
    return {
        "schema": "HARPOON_FWN9_P9M_B_AUDIT_1",
        "batch_id": tape["batch_id"],
        "signed_panel_sha256": digest(panel),
        "signature_cryptographically_verified": True,
        "independent_source_attested": False,
        "issuer_opportunity_completeness_verified": True,
        "independent_universe_verified": False,
        "marks_checked": len(marks),
        "opportunities_checked": len(opps),
        "events_checked": proof["events_checked"],
        "end_equity_usd": str(previous_equity),
        "cash_benchmark_usd": str(CASH - len(days)),
        "net_after_fixed_and_receipt_cost_usd": str(previous_equity - CASH),
        "fixed_calendar_costs_usd": str(len(days)),
        "max_daily_drawdown": str(dd),
        "worst_weekday_usd": str(worst),
        "best_campaign_positive_share": (
            str(max(gains) / total_positive) if total_positive else None),
        "daily_equity_sha256": digest(equity_rows),
        "native_m9_causal_equivalence": False,
        "paired_prior_candidate": False,
        "world_stability": False,
        "optimizer_eligible": False,
        "execution_allowed": False,
        "n9s_certified": False,
    }


def journal_panel(path: str | Path, report: dict[str, Any], now: str) -> str:
    _need(report.get("schema") == "HARPOON_FWN9_P9M_B_AUDIT_1" and
          report.get("optimizer_eligible") is False, "B_JOURNAL_GUARD")
    j = Journal(path)
    try:
        key = "fwn9:p9mb:" + report["batch_id"]
        with j.transaction():
            old = j.get(key)
            if old is not None:
                _need(old == report, "B_RESTART_CONFLICT")
                return "UNCHANGED"
            j.put(key, report, now)
        j.verify()
        return "COMMITTED"
    finally:
        j.close()
