"""Native fee accrual and calendar costs for offline account reconciliation.

No broker transport or tariff inference is provided. A caller supplies a versioned
profile and an observed liquidity role. Public tier rates can be explicit assumed
profiles, but that never authenticates the fee tier of an account.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

ZERO = Decimal(0)
BPS = Decimal(10000)


def decimal(value: Any, *, positive: bool = False) -> Decimal:
    """Accept exact decimal-compatible scalars, rejecting bool/nonfinite values."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise TypeError("INVALID_DECIMAL_TYPE")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("INVALID_DECIMAL") from exc
    if not result.is_finite() or (result <= 0 if positive else result < 0):
        raise ValueError("INVALID_DECIMAL_DOMAIN")
    return result


def _identity(body: Mapping[str, Any]) -> str:
    data = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(data.encode()).hexdigest()


@dataclass(frozen=True)
class FeeProfile:
    """Explicit credited-asset or quote-currency per-unit fee contract."""

    profile_id: str
    base_asset: str
    quote_asset: str
    maker_bps: Decimal
    taker_bps: Decimal
    origin: str
    source: str
    charge_mode: str = "CREDITED_ASSET_BPS"
    quote_fee_per_unit: Decimal = ZERO
    quote_fixed_per_order: Decimal = ZERO

    def __post_init__(self) -> None:
        if (
            not self.profile_id
            or not self.source
            or not self.base_asset
            or not self.quote_asset
            or self.base_asset == self.quote_asset
        ):
            raise ValueError("FEE_PROFILE_IDENTITY")
        if self.origin not in {
            "ASSUMED_PUBLIC_TARIFF",
            "OBSERVED_ACCOUNT",
            "SYNTHETIC_ENGINEERING_ONLY",
        }:
            raise ValueError("FEE_ORIGIN")
        for name in ("maker_bps", "taker_bps"):
            rate = decimal(getattr(self, name))
            if rate >= BPS:
                raise ValueError("FEE_RATE_DOMAIN")
            object.__setattr__(self, name, rate)
        if self.charge_mode not in {"CREDITED_ASSET_BPS", "QUOTE_PER_UNIT"}:
            raise ValueError("FEE_CHARGE_MODE")
        for name in ("quote_fee_per_unit", "quote_fixed_per_order"):
            object.__setattr__(self, name, decimal(getattr(self, name)))
        if self.charge_mode == "CREDITED_ASSET_BPS" and (
            self.quote_fee_per_unit != 0 or self.quote_fixed_per_order != 0
        ):
            raise ValueError("MIXED_FEE_UNITS")

    def fee(
        self,
        side: str,
        qty: Any,
        price: Any,
        liquidity_role: str,
        *,
        first_fill: bool = True,
    ) -> tuple[str, Decimal]:
        """Return fee currency and exact provision; unknown roles block entry."""
        if side not in {"buy", "sell"} or liquidity_role not in {"maker", "taker"}:
            raise ValueError("SIDE_OR_LIQUIDITY_UNKNOWN")
        q, p = decimal(qty, positive=True), decimal(price, positive=True)
        if self.charge_mode == "QUOTE_PER_UNIT":
            return self.quote_asset, q * self.quote_fee_per_unit + (
                self.quote_fixed_per_order if first_fill else ZERO
            )
        rate = self.maker_bps if liquidity_role == "maker" else self.taker_bps
        return (
            (self.base_asset, q * rate / BPS)
            if side == "buy"
            else (self.quote_asset, q * p * rate / BPS)
        )

    def fingerprint(self) -> str:
        """Bind all versioned tariff fields, including provenance, to every fill."""
        return _identity(
            {
                k: str(v) if isinstance(v, Decimal) else v
                for k, v in asdict(self).items()
            }
        )


def round_trip_break_even(entry_bps: Any, exit_bps: Any) -> Decimal:
    """Gross price return required for native-credited fees only; excludes spread."""
    a, b = decimal(entry_bps) / BPS, decimal(exit_bps) / BPS
    if a >= 1 or b >= 1:
        raise ValueError("FEE_RATE_DOMAIN")
    return 1 / ((1 - a) * (1 - b)) - 1


def _utc(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("AWARE_TIME_REQUIRED")
    return value.astimezone(UTC)


def calendar_overhead(start: datetime, end: datetime, usd_per_day: Any) -> Decimal:
    """Elapsed calendar-time accrual, including weekends, without business-day resets."""
    elapsed = _utc(end) - _utc(start)
    if elapsed.total_seconds() < 0:
        raise ValueError("OVERHEAD_TIME_ORDER")
    micros = (elapsed.days * 86400 + elapsed.seconds) * 1_000_000 + elapsed.microseconds
    return decimal(usd_per_day) * Decimal(micros) / Decimal(86_400_000_000)


class NativeFeeLedger:
    """Gross settled assets minus explicit pending native-fee liabilities.

    apply_fill changes cash/inventory once and accrues a conservative fee.
    post_fee reconciles CFEE/FEE once; a correction changes only its difference.
    Fees already included in a broker balance must not be posted again: initialize
    before the observed fills, or use reconcile_balances as an external equality
    check. This ledger does not claim historical-source authentication.
    """

    def __init__(self, balances: Mapping[str, Any]) -> None:
        self.balances = {asset: decimal(value) for asset, value in balances.items()}
        self.fills: dict[str, dict[str, Any]] = {}
        self.order_contracts: dict[str, tuple[str, str]] = {}
        self.activities: dict[str, str] = {}
        self.overhead_periods: dict[str, tuple[datetime, datetime, Decimal]] = {}

    def pending(self, asset: str) -> Decimal:
        return sum(
            (
                row["provision"]
                for row in self.fills.values()
                if row["fee_asset"] == asset and row["posted_fee"] is None
            ),
            ZERO,
        )

    def available(self, asset: str) -> Decimal:
        return self.balances.get(asset, ZERO) - self.pending(asset)

    def apply_fill(
        self,
        *,
        fill_id: str,
        order_id: str,
        side: str,
        qty: Any,
        price: Any,
        liquidity_role: str,
        profile: FeeProfile,
    ) -> bool:
        q, p = decimal(qty, positive=True), decimal(price, positive=True)
        profile_fingerprint = profile.fingerprint()
        contract = (side, profile_fingerprint)
        if (
            order_id in self.order_contracts
            and self.order_contracts[order_id] != contract
        ):
            raise ValueError("ORDER_FEE_CONTRACT_CHANGED")
        first_fill = not any(row["order_id"] == order_id for row in self.fills.values())
        # An identical delivered fill retains its first-fill treatment on replay.
        if fill_id in self.fills:
            first_fill = self.fills[fill_id]["first_fill"]
        fee_asset, provision = profile.fee(
            side, q, p, liquidity_role, first_fill=first_fill
        )
        if not fill_id or not order_id:
            raise ValueError("FILL_IDENTITY")
        payload = {
            "fill_id": fill_id,
            "order_id": order_id,
            "side": side,
            "qty": str(q),
            "price": str(p),
            "liquidity_role": liquidity_role,
            "profile_id": profile.profile_id,
            "profile_fingerprint": profile_fingerprint,
            "fee_asset": fee_asset,
            "base_asset": profile.base_asset,
            "quote_asset": profile.quote_asset,
            "provision": str(provision),
            "first_fill": first_fill,
        }
        identity = _identity(payload)
        if fill_id in self.fills:
            if self.fills[fill_id]["identity"] != identity:
                raise ValueError("CONFLICTING_FILL")
            return False
        debit_asset = profile.quote_asset if side == "buy" else profile.base_asset
        debit = q * p if side == "buy" else q
        if self.available(debit_asset) < debit + (
            provision if fee_asset == debit_asset else ZERO
        ):
            raise ValueError("INSUFFICIENT_SETTLED_ASSETS")
        credit_asset = profile.base_asset if side == "buy" else profile.quote_asset
        credit = q if side == "buy" else q * p
        self.balances[debit_asset] = self.balances.get(debit_asset, ZERO) - debit
        self.balances[credit_asset] = self.balances.get(credit_asset, ZERO) + credit
        self.fills[fill_id] = {
            **payload,
            "identity": identity,
            "provision": provision,
            "posted_fee": None,
            "fee_asset": fee_asset,
        }
        self.order_contracts[order_id] = contract
        return True

    def post_fee(
        self,
        *,
        activity_id: str,
        fill_id: str,
        fee_asset: str,
        total_fee: Any,
        corrects_activity_id: str | None = None,
    ) -> bool:
        """Reconcile a fill's total fee, with explicit correction lineage."""
        amount = decimal(total_fee)
        if not activity_id or fill_id not in self.fills:
            raise ValueError("FEE_ACTIVITY_IDENTITY")
        row = self.fills[fill_id]
        payload = {
            "activity_id": activity_id,
            "fill_id": fill_id,
            "fee_asset": fee_asset,
            "total_fee": str(amount),
            "corrects_activity_id": corrects_activity_id,
        }
        identity = _identity(payload)
        if activity_id in self.activities:
            if self.activities[activity_id] != identity:
                raise ValueError("CONFLICTING_FEE_ACTIVITY")
            return False
        if fee_asset != row["fee_asset"]:
            raise ValueError("FEE_CURRENCY_MISMATCH")
        previous = row["posted_fee"]
        if previous is not None and corrects_activity_id != row.get("activity_id"):
            raise ValueError("FEE_CORRECTION_LINEAGE_REQUIRED")
        if previous is None and corrects_activity_id is not None:
            raise ValueError("FEE_CORRECTION_WITHOUT_ORIGINAL")
        delta = amount - (previous if previous is not None else ZERO)
        # Negative balances remain visible if the actual fee exceeds the accrual.
        # Dropping an authentic fee to preserve a risk limit would falsify accounting.
        self.balances[fee_asset] = self.balances.get(fee_asset, ZERO) - delta
        row["posted_fee"], row["activity_id"] = amount, activity_id
        self.activities[activity_id] = identity
        return True

    def accrue_overhead(
        self,
        *,
        accrual_id: str,
        start: datetime,
        end: datetime,
        usd_per_day: Any,
        quote_asset: str = "USD",
    ) -> bool:
        a, b = _utc(start), _utc(end)
        value = calendar_overhead(a, b, usd_per_day)
        if not accrual_id:
            raise ValueError("OVERHEAD_IDENTITY")
        if accrual_id in self.overhead_periods:
            if self.overhead_periods[accrual_id] != (a, b, value):
                raise ValueError("CONFLICTING_OVERHEAD")
            return False
        if any(
            a < old_b and b > old_a
            for old_a, old_b, _ in self.overhead_periods.values()
        ):
            raise ValueError("OVERLAPPING_COMMON_OVERHEAD")
        self.balances[quote_asset] = self.balances.get(quote_asset, ZERO) - value
        self.overhead_periods[accrual_id] = (a, b, value)
        return True

    def equity(self, usd_marks: Mapping[str, Any]) -> Decimal:
        """Net asset value at supplied marks; no presumed mark for missing assets."""
        total = ZERO
        for asset in self.balances:
            quantity = self.available(asset)
            if quantity == ZERO:
                continue
            if asset not in usd_marks:
                raise ValueError("MISSING_ASSET_MARK:" + asset)
            total += quantity * decimal(usd_marks[asset], positive=True)
        return total

    def reconcile_balances(
        self, observed: Mapping[str, Any], tolerance: Any = "0"
    ) -> bool:
        tol = decimal(tolerance)
        if set(observed) != set(self.balances):
            return False
        return all(
            abs(self.balances[a] - decimal(v)) <= tol for a, v in observed.items()
        )

    def report(self) -> dict[str, Any]:
        return {
            "schema": "HARPOON_NATIVE_FEE_LEDGER_1",
            "balances": {k: str(v) for k, v in sorted(self.balances.items())},
            "pending_native_fees": {
                k: str(self.pending(k)) for k in sorted(self.balances)
            },
            "available": {k: str(self.available(k)) for k in sorted(self.balances)},
            "pending_fee_count": sum(
                r["posted_fee"] is None for r in self.fills.values()
            ),
            "negative_available_assets": [
                k for k in self.balances if self.available(k) < 0
            ],
            "observed_source_authenticated": False,
            "orders_allowed": False,
        }
