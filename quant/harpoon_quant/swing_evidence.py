"""Pure Decimal reconciliation for the native, modeled USD swing account."""

from __future__ import annotations

from decimal import Context, Decimal, localcontext
from typing import Any

from .multiasset import stamp

TOL = Decimal("0.000001")


def _need(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def _decimal(value: Any) -> Decimal:
    _need(type(value) in (int, float, str), "LEDGER_NUMBER_TYPE")
    result = Decimal(str(value))
    _need(result.is_finite(), "NONFINITE_LEDGER")
    return result


def verify_account(a: dict[str, Any]) -> dict[str, Any]:
    """Use an isolated precision, independent of callers and worker processes."""
    with localcontext(Context(prec=50)):
        return _reconcile(a)


def _reconcile(a: dict[str, Any]) -> dict[str, Any]:
    """Rebuild every daily cash, inventory and entitlement frame from events.

    This validates supplied modeled records. It does not authenticate the data
    provider or establish executable prices. No files or services are accessed.
    """
    _need(a.get("schema") == "HARPOON_SWING_ACCOUNT_1", "NATIVE_SWING_SCHEMA")
    _need(type(a["stress"]) is bool, "SCENARIO_TYPE")
    _need(_decimal(a["initial_usd"]) == 20000, "REGISTERED_CAPITAL")
    _need(bool(a["curve"]), "EMPTY_LEDGER")
    _need(len(a["curve"]) <= 7300 and len(a["events"]) <= 100000, "LEDGER_BUDGET")
    cash = Decimal(20000)
    qty: dict[str, Decimal] = {}
    claims: dict[str, Decimal] = {}
    receipts: set[str] = set()
    cursor = 0
    maxerror = Decimal(0)
    for row in a["curve"]:
        stop = row["event_count"]
        _need(type(stop) is int and cursor <= stop <= len(a["events"]), "EVENT_CURSOR")
        for e in a["events"][cursor:stop]:
            k, symbol = e["kind"], e.get("symbol")
            n, px, fee = (
                _decimal(e.get(field, 0)) for field in ("qty", "price", "fee")
            )
            _need(fee >= 0, "NEGATIVE_FEE")
            if k == "BUY":
                _need(isinstance(symbol, str) and bool(symbol), "LEDGER_SYMBOL")
                _need(
                    n > 0 and px > 0 and symbol not in qty, "OVERLAPPING_OR_EMPTY_BUY"
                )
                _need("/" in symbol or n == n.to_integral(), "WHOLE_EQUITY_LOT")
                debit = n * px + fee
                _need(abs(-debit - _decimal(e["cash_delta"])) < TOL, "BUY_CASH")
                _need(cash >= debit, "UNFUNDED_ENTRY")
                cash -= debit
                qty[symbol] = n
            elif k == "SELL":
                _need(
                    symbol in qty
                    and abs(qty[symbol] - n) < Decimal("1e-10")
                    and px > 0,
                    "NAKED_OR_PARTIAL_EXIT",
                )
                credit = n * px - fee
                _need(abs(credit - _decimal(e["cash_delta"])) < TOL, "SELL_CASH")
                cash += credit
                del qty[symbol]
            elif k == "FIXED":
                delta = _decimal(e["cash_delta"])
                _need(delta == (-2 if a["stress"] else -1), "FIXED_COST")
                cash += delta
            elif k == "SPLIT":
                ratio = _decimal(e["ratio"])
                _need(symbol in qty and ratio > 0, "SPLIT_WITHOUT_POSITION")
                qty[symbol] *= ratio
            elif k == "DIV_EX":
                receipt = e["receipt"]
                _need(
                    isinstance(receipt, str)
                    and bool(receipt)
                    and receipt not in receipts,
                    "DIVIDEND_DUPLICATED",
                )
                amount = _decimal(e["amount"])
                _need(amount > 0, "DIVIDEND_AMOUNT")
                receipts.add(receipt)
                claims[receipt] = amount
            elif k == "DIV_PAY":
                receipt = e["receipt"]
                _need(
                    receipt in claims
                    and abs(claims[receipt] - _decimal(e["cash_delta"])) < TOL,
                    "DIVIDEND_PAYMENT",
                )
                cash += claims.pop(receipt)
            else:
                raise ValueError("UNKNOWN_EVENT")
        cursor = stop
        holdings = {p["symbol"]: p for p in row["positions"]}
        _need(
            len(holdings) == len(row["positions"]) and set(holdings) == set(qty),
            "INVENTORY_FRAME",
        )
        for symbol, n in qty.items():
            _need(
                abs(n - _decimal(holdings[symbol]["qty"])) < Decimal("1e-10"),
                "INVENTORY_QUANTITY",
            )
            _need(_decimal(holdings[symbol]["mark"]) > 0, "NONPOSITIVE_MARK")
        receivables = sum(claims.values(), Decimal(0))
        eq = (
            cash
            + receivables
            + sum((qty[s] * _decimal(holdings[s]["mark"]) for s in qty), Decimal(0))
        )
        error = abs(eq - _decimal(row["equity"]))
        maxerror = max(maxerror, error)
        _need(
            eq > 0 and error < TOL and abs(cash - _decimal(row["cash"])) < TOL,
            "DAILY_LEDGER",
        )
        _need(abs(receivables - _decimal(row["receivables"])) < TOL, "RECEIVABLE_FRAME")
    _need(cursor == len(a["events"]) and not qty, "UNRECONCILED_TERMINAL_EVENTS")
    _need(
        abs(cash + sum(claims.values(), Decimal(0)) - _decimal(a["terminal_usd"]))
        < TOL,
        "TERMINAL_VALUE",
    )
    _need(
        abs(_decimal(a["net_usd"]) - (_decimal(a["terminal_usd"]) - 20000)) < TOL,
        "NET_VALUE",
    )
    for t in a["trades"]:
        entered, exited, planned = map(
            stamp, (t["entry_at"], t["exit_at"], t["planned_exit"])
        )
        _need(
            stamp(t["signal_known_at"]) < entered <= exited <= planned,
            "CAUSALITY_OR_EXIT_AFTER_PLAN",
        )
        _need(
            24 <= (planned - entered).total_seconds() / 3600 <= 72,
            "PLANNED_SWING_HORIZON",
        )
        _need((exited - entered).total_seconds() / 3600 <= 72, "HARD_HOLD_LIMIT")
        _need(t["fill_nature"] == "MODELED", "FALSE_REAL_FILL")
        if t["exit_reason"] == "STOP":
            _need(
                _decimal(t["exit_price"]) <= _decimal(t["stop_at_entry"]), "STOP_PRICE"
            )
    _need(
        a["execution_allowed"] is False and a["level8_accredited"] is False, "AUTHORITY"
    )
    return {
        "trades": len(a["trades"]),
        "days": len(a["curve"]),
        "max_decimal_error_usd": float(maxerror),
    }
