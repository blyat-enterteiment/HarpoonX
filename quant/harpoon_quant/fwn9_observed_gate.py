"""FWN9 P9M-A: read-only intake of prospectively observed execution receipts.

This module is a financial/clock preflight, not a provenance authenticator
or an optimizer. It never reads or opens a final holdout, creates orders,
changes M9 limits, or invokes recursive.tick.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .recursive import Journal

SCHEMA = "HARPOON_FWN9_P9M_A_RECEIPT_TAPE_1"
SHA = re.compile(r"^[0-9a-f]{64}$")
CASH = Decimal("20000")
MAX_EVENTS = 4096


def _need(ok: bool, label: str) -> None:
    if not ok:
        raise ValueError("P9M_" + label)


def _utc(s: Any) -> datetime:
    _need(isinstance(s, str) and s.endswith("Z"), "UTC_ISO_REQUIRED")
    try:
        t = datetime.fromisoformat(s[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("P9M_UTC_ISO_REQUIRED") from exc
    _need(t.tzinfo is not None and t.utcoffset() == timedelta(0), "UTC_ONLY")
    return t.astimezone(UTC)


def _money(v: Any, *, positive: bool = False) -> Decimal:
    _need(isinstance(v, str) and bool(re.fullmatch(r"\d{1,12}(?:\.\d{1,8})?", v)),
          "DECIMAL_STRING_REQUIRED")
    try:
        n = Decimal(v)
    except InvalidOperation as exc:
        raise ValueError("P9M_DECIMAL_STRING_REQUIRED") from exc
    _need(n.is_finite() and (n > 0 if positive else n >= 0), "NONNEGATIVE_MONEY")
    return n


def receipt_sha256(events: list[dict[str, Any]]) -> str:
    """Canonical receipt digest; a checksum alone is NOT source authentication."""
    raw = json.dumps(events, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def audit_receipt_tape(
    tape: dict[str, Any],
    *,
    native_checkpoint_sha256: str,
    externally_pinned_receipt_sha256: str | None,
    now: str,
) -> dict[str, Any]:
    """Validate finite inventory, causal labels and an unopened future split.

    A caller's pinned hash does not prove independence or authenticity.
    Passing this function never grants optimizer or trade authorization.
    """
    _need(isinstance(tape, dict) and tape.get("schema") == SCHEMA, "SCHEMA")
    _need(tape.get("source_nature") == "PROSPECTIVE_OBSERVED_EXECUTION_RECEIPTS",
          "SOURCE_IS_NOT_PROSPECTIVE_OBSERVED")
    _need(isinstance(tape.get("batch_id"), str) and
          bool(re.fullmatch(r"[A-Za-z0-9_-]{3,80}", tape["batch_id"])),
          "BATCH_ID")
    _need(bool(SHA.fullmatch(native_checkpoint_sha256)) and
          tape.get("native_checkpoint_sha256") == native_checkpoint_sha256,
          "NATIVE_CHECKPOINT_BINDING")
    end = _utc(now)
    days = tape.get("development_days")
    _need(isinstance(days, list) and 180 <= len(days) <= 2000, "DEVELOPMENT_180D")
    assert isinstance(days, list)  # narrows after the fail-closed validator
    try:
        dd = [date.fromisoformat(x) for x in days]
        hold_start = date.fromisoformat(tape["holdout_start"])
        hold_end = date.fromisoformat(tape["holdout_end"])
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError("P9M_DATE_PARSE") from exc
    _need(all(x.isoformat() == y for x, y in zip(dd, days, strict=True)),
          "CANONICAL_DEVELOPMENT_DATES")
    _need(all(b - a == timedelta(days=1) for a, b in zip(dd, dd[1:])),
          "CONTIGUOUS_DEVELOPMENT")
    _need(dd[-1] + timedelta(days=1) <= end.date(), "DEVELOPMENT_NOT_COMPLETE")
    _need(hold_start >= dd[-1] + timedelta(days=4) and
          hold_end - hold_start >= timedelta(days=59),
          "SEALED_HOLDOUT_DISJOINT_EMBARGO")
    _need(tape.get("holdout_payload") is None, "HOLDOUT_PAYLOAD_FORBIDDEN")
    events = tape.get("events")
    labels = tape.get("labels")
    _need(isinstance(events, list) and 1 <= len(events) <= MAX_EVENTS and
          isinstance(labels, list) and len(labels) <= MAX_EVENTS,
          "EVENT_BUDGET")
    assert isinstance(events, list) and isinstance(labels, list)
    _need(all(isinstance(e, dict) for e in events) and
          all(isinstance(e, dict) for e in labels), "EVENT_SHAPES")
    actual_digest = receipt_sha256(events)
    _need(externally_pinned_receipt_sha256 is not None and
          bool(SHA.fullmatch(externally_pinned_receipt_sha256)) and
          externally_pinned_receipt_sha256 == actual_digest, "EXTERNAL_ROOT_REQUIRED")
    seen: set[str] = set()
    records: dict[str, dict[str, Any]] = {}
    prior_known: datetime | None = None
    cash = CASH
    events_validated = 0
    for event in events:
        event_id = event.get("id")
        order = event.get("order_id")
        kind = event.get("type")
        _need(isinstance(event_id, str) and
              bool(re.fullmatch(r"[A-Za-z0-9_:.-]{1,120}", event_id)) and
              event_id not in seen, "UNIQUE_EVENT_ID")
        seen.add(event_id)
        _need(isinstance(order, str) and
              bool(re.fullmatch(r"[A-Za-z0-9_:.-]{1,120}", order)),
              "ORDER_ID")
        _need(kind in {"SIGNAL", "ENTRY_FILL", "EXIT_FILL", "ENTRY_NO_FILL"},
              "RECEIPT_KIND")
        at, known = _utc(event.get("effective_at")), _utc(event.get("known_at"))
        _need(at <= known <= end, "NO_FUTURE_INFORMATION")
        _need(dd[0] <= at.date() <= dd[-1], "RECEIPT_DEVELOPMENT_ONLY")
        _need(prior_known is None or known >= prior_known, "KNOWN_AT_SORT_ORDER")
        prior_known = known
        p = records.setdefault(order, {"signal": None, "entry": None,
                                       "exits": [], "no_fill": None})
        if kind == "SIGNAL":
            _need(p["signal"] is None and event.get("symbol") in {"SYNA", "SYNB"},
                  "DUPLICATE_OR_FOREIGN_SIGNAL")
            _need(known == at and event.get("forecast_hash") and
                  bool(SHA.fullmatch(event["forecast_hash"])), "FROZEN_SIGNAL")
            p["signal"] = event
        else:
            _need(p["signal"] is not None, "RECEIPT_BEFORE_CAUSAL_SIGNAL")
            _need(at >= _utc(p["signal"]["effective_at"]), "ENTRY_PRECEDES_SIGNAL")
            if kind == "ENTRY_NO_FILL":
                _need(p["entry"] is None and p["no_fill"] is None, "NO_FILL_CONFLICT")
                p["no_fill"] = event
            else:
                q = event.get("quantity")
                _need(type(q) is int and 1 <= q <= 1_000_000, "INTEGER_FILLED_QUANTITY")
                price = _money(event.get("price"), positive=True)
                fee = _money(event.get("fee_usd"))
                delta = Decimal(q) * price
                if kind == "ENTRY_FILL":
                    _need(p["entry"] is None and p["no_fill"] is None and
                          not p["exits"], "MULTIPLE_OR_LATE_ENTRY")
                    _need(at - _utc(p["signal"]["effective_at"]) <= timedelta(days=3),
                          "ENTRY_AFTER_SIGNAL_HORIZON")
                    cash -= delta + fee
                    _need(cash >= 0, "UNFUNDED_ENTRY")
                    p["entry"] = event
                else:
                    _need(p["entry"] is not None and p["no_fill"] is None,
                          "EXIT_WITHOUT_INVENTORY")
                    _need(at >= _utc(p["entry"]["effective_at"]) and
                          at - _utc(p["entry"]["effective_at"]) <= timedelta(hours=72),
                          "MAX_HOLD_72H")
                    _need(sum(int(v["quantity"]) for v in p["exits"]) + q <=
                          int(p["entry"]["quantity"]), "OVERSELL")
                    cash += delta - fee
                    p["exits"].append(event)
                    _need(cash >= 0, "NEGATIVE_CASH")
        events_validated += 1
    _need(len(labels) == len(records), "COMPLETE_LABEL_COVERAGE")
    labels_seen: set[str] = set()
    net = Decimal("0")
    filled = 0
    no_fills = 0
    for label in labels:
        oid = label.get("order_id")
        _need(isinstance(oid, str) and oid in records and oid not in labels_seen,
              "UNIQUE_COMPLETE_LABEL")
        labels_seen.add(oid)
        p = records[oid]
        _need(p["signal"] is not None, "UNSIGNALLED_OUTCOME")
        late = _utc(label.get("label_known_at"))
        _need(late <= end, "FUTURE_LABEL")
        if p["no_fill"] is not None:
            _need(p["entry"] is None and not p["exits"] and
                  late >= _utc(p["no_fill"]["known_at"]) and
                  _money(label.get("net_usd")) == 0, "NO_FILL_LABEL")
            no_fills += 1
            continue
        entry = p["entry"]
        xs = p["exits"]
        _need(entry is not None and bool(xs) and
              sum(int(v["quantity"]) for v in xs) == int(entry["quantity"]),
              "OPEN_OR_PARTIAL_INVENTORY")
        _need(late >= max(_utc(v["known_at"]) for v in [entry, *xs]) and
              late <= datetime.combine(dd[-1] + timedelta(days=1),
                                       datetime.min.time(), tzinfo=UTC),
              "LABEL_KNOWN_AFTER_DEVELOPMENT")
        bought = Decimal(int(entry["quantity"])) * _money(entry["price"]) + \
            _money(entry["fee_usd"])
        sold = sum((Decimal(int(x["quantity"])) * _money(x["price"]) -
                    _money(x["fee_usd"]) for x in xs), Decimal(0))
        pnl = sold - bought
        _need(pnl == Decimal(str(label.get("net_usd"))), "INDEPENDENT_NET_RECONCILIATION")
        net += pnl
        filled += 1
    _need(len(labels_seen) == len(records), "MISSING_LABEL")
    return {
        "schema": "HARPOON_FWN9_P9M_A_PREFLIGHT_1",
        "batch_id": tape["batch_id"],
        "native_checkpoint_sha256": native_checkpoint_sha256,
        "source_receipt_sha256": actual_digest,
        "events_checked": events_validated,
        "filled_campaigns": filled,
        "ioc_no_fills": no_fills,
        "net_receipts_usd": str(net),
        "physical_cash_end_usd": str(cash),
        "development_days": len(days),
        "holdout_days_declared_not_opened": (hold_end - hold_start).days + 1,
        "integrity": "RECEIPTS_STRUCTURALLY_RECONCILED",
        "independent_source_authentication": False,
        "daily_mtm_and_complete_universe_verified": False,
        "native_M9_risk_parity": False,
        "optimizer_eligible": False,
        "execution_allowed": False,
        "n9s_certified": False,
        "status": "WAIT_INDEPENDENT_SOURCE_ATTESTATION_AND_DAILY_MTM",
    }


def journal_preflight(path: str | Path, audit: dict[str, Any], now: str) -> str:
    """Append-only read/write audit state; conflicting restarts fail closed."""
    _need(audit.get("schema") == "HARPOON_FWN9_P9M_A_PREFLIGHT_1" and
          audit.get("optimizer_eligible") is False and
          audit.get("execution_allowed") is False, "PRECHECK_BEFORE_JOURNAL")
    key = "fwn9:p9m:receipt:" + audit["batch_id"]
    j = Journal(path)
    try:
        with j.transaction():
            previous = j.get(key)
            if previous is not None:
                _need(previous == audit, "RESTART_EVIDENCE_CONFLICT")
                return "UNCHANGED"
            j.put(key, audit, now)
        j.verify()
        return "COMMITTED"
    finally:
        j.close()
