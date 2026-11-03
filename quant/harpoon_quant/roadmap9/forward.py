"""Reconcile normalized spot-account evidence and verify scoped attestations.

No account is contacted. Original broker records must be normalized without
inventing timestamps. A mathematically consistent packet is not authenticated
by its own flags or hashes. Ed25519 trust roots are supplied by the operator,
never generated or installed by this module.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
from decimal import Decimal, InvalidOperation
from itertools import pairwise
from typing import Any

import numpy as np


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def need(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def amount(value: Any, *, positive: bool = False) -> Decimal:
    need(not isinstance(value, bool) and isinstance(value, (str, int, float, Decimal)),
         "AMOUNT_TYPE")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("AMOUNT_FORMAT") from exc
    need(result.is_finite() and (result > 0 if positive else result >= 0), "AMOUNT_DOMAIN")
    return result


def timestamp(value: Any) -> int:
    need(type(value) is int and value >= 0, "UTC_MILLISECONDS_REQUIRED")
    return value


def verify_attestation(attestation: dict[str, Any] | None,
                       trust_store: dict[str, Any], *, role: str,
                       expected: dict[str, Any], now_ms: int) -> dict[str, Any]:
    """Verify identity, expiry, scope and independent-review role of a signer.

    This verifies a signed assertion against explicitly trusted public keys; it
    cannot establish the truth of a dishonest signer's assertion. Test keys can
    exercise signature verification but are never accepted as production trust.
    """
    failure = {"verified": False, "reason": "ATTESTATION_REQUIRED"}
    if not attestation:
        return failure
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        return {"verified": False, "reason": "SIGNATURE_VERIFIER_UNAVAILABLE"}
    try:
        payload = attestation["payload"]
        key = trust_store[attestation["key_id"]]
        need(role in key["roles"] and payload["role"] == role, "ATTESTATION_ROLE")
        need(payload["signer_id"] == key["signer_id"], "ATTESTATION_IDENTITY")
        need(timestamp(payload["issued_at"]) <= timestamp(now_ms) <= timestamp(payload["expires_at"]),
             "ATTESTATION_EXPIRY")
        need(all(payload.get(k) == v for k, v in expected.items()), "ATTESTATION_SCOPE")
        public = Ed25519PublicKey.from_public_bytes(bytes.fromhex(key["public_key_hex"]))
        public.verify(base64.b64decode(attestation["signature"], validate=True), canonical(payload))
        need(key.get("test_only") is False, "TEST_KEY_NOT_PRODUCTION_EVIDENCE")
        if role == "EXTERNAL_REVIEW":
            need(payload.get("author_id") and payload["author_id"] != payload["signer_id"],
                 "REVIEWER_NOT_INDEPENDENT")
            need(key.get("independent_reviewer") is True, "REVIEWER_TRUST_SCOPE")
            need(payload.get("verdict") == "ACCEPT" and payload.get("critical_findings") == 0,
                 "REVIEW_NOT_ACCEPTED")
        return {"verified": True, "signer_id": payload["signer_id"], "role": role,
                "assertion_truth_requires_signer_diligence": True}
    except (KeyError, TypeError, ValueError, InvalidSignature) as exc:
        return {"verified": False, "reason": str(exc) or "INVALID_SIGNATURE"}


def reconcile_packet(packet: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    """Rebuild settled balances, pending fees and economic NAV from every event.

    Supported scope: one long-only USD spot account, no leverage or cash flows.
    FILL quantities are per execution, never cumulative order quantities. FEE
    posts retire a fill's provision and debit the actual native currency once.
    Snapshot balances are gross settled broker balances; economic NAV subtracts
    outstanding provisions. Unresolved fees block economic acceptance.
    """
    need(packet.get("schema") == "HARPOON_ROADMAP_FORWARD_PACKET_1", "PACKET_SCHEMA")
    need(packet.get("protocol_sha256") == digest(protocol), "PROTOCOL_BINDING")
    need(packet.get("origin") in {"OBSERVED_LIVE", "OBSERVED_PAPER", "SYNTHETIC_ENGINEERING_ONLY"},
         "EVIDENCE_ORIGIN")
    for key, maximum in (("max_quote_age_ms", 15_000), ("max_mark_age_ms", 15_000),
                         ("max_model_label_age_ms", 168 * 3_600_000)):
        limit = protocol[key]
        need(type(limit) is int and 0 < limit <= maximum, "PROTOCOL_FRESHNESS_LIMIT:" + key)
    start, end = timestamp(protocol["evaluation_start"]), timestamp(protocol["evaluation_end"])
    need(start < end and timestamp(protocol["registered_at"]) < start, "FORWARD_PERIOD")
    need(timestamp(protocol["calibration_end"]) < start, "CALIBRATION_VALIDATION_OVERLAP")
    need(packet.get("code_commit") == protocol["code_commit"], "CODE_BINDING")
    need(packet.get("recipe_hash") == protocol["recipe_hash"], "RECIPE_BINDING")
    need(packet.get("cost_profile_hash") == protocol["cost_profile_hash"], "COST_PROFILE_BINDING")
    need(bool(packet.get("account_ref")), "ACCOUNT_IDENTITY")
    initial = amount(protocol["initial_capital_usd"], positive=True)
    need(initial == Decimal(20000), "REGISTERED_CAPITAL")
    balances: dict[str, Decimal] = {"USD": initial}
    specs = protocol["instruments"]
    need(isinstance(specs, dict) and bool(specs), "INSTRUMENTS_REQUIRED")
    orders: dict[str, dict[str, Any]] = {}
    client_ids: set[str] = set()
    campaigns: dict[str, tuple[int, int, str]] = {}
    campaign_inventory: dict[str, Decimal] = {}
    for order in packet["orders"]:
        oid, cid = order["order_id"], order["client_order_id"]
        need(bool(oid) and bool(cid) and oid not in orders and cid not in client_ids, "ORDER_IDENTITY")
        need(order["symbol"] in specs and order["side"] in {"buy", "sell"}, "ORDER_INSTRUMENT")
        opened, deadline = timestamp(order["opened_at"]), timestamp(order["original_deadline"])
        need(0 < deadline - opened <= 72 * 3_600_000, "ORIGINAL_72H_DEADLINE")
        campaign_id = order["campaign_id"]
        need(bool(campaign_id), "CAMPAIGN_IDENTITY")
        if campaign_id in campaigns:
            need(campaigns[campaign_id] == (opened, deadline, order["symbol"]), "CAMPAIGN_DEADLINE_RESET")
        campaigns[campaign_id] = (opened, deadline, order["symbol"])
        campaign_inventory.setdefault(campaign_id, Decimal(0))
        need(opened <= timestamp(order["decision_at"]) <= timestamp(order["submitted_at"]), "ORDER_CLOCK")
        need(timestamp(order["quote_event_at"]) <= timestamp(order["quote_available_at"])
             <= order["decision_at"], "QUOTE_LOOKAHEAD")
        need(order["decision_at"] - order["quote_event_at"] <= protocol["max_quote_age_ms"],
             "STALE_DECISION_QUOTE")
        need(timestamp(order["latest_training_label_available_at"]) < order["decision_at"], "LABEL_LOOKAHEAD")
        need(order["latest_training_label_available_at"] <= timestamp(order["model_available_at"])
             <= order["decision_at"], "MODEL_AVAILABILITY_LOOKAHEAD")
        need(order["decision_at"] - order["latest_training_label_available_at"] <=
             protocol["max_model_label_age_ms"], "STALE_TRAINING_LABELS")
        amount(order["quantity"], positive=True)
        orders[oid] = order
        client_ids.add(cid)
    events = packet["events"]
    need(isinstance(events, list) and 2 <= len(events) <= 1_000_000, "EVENT_COUNT")
    need(all(timestamp(a["at"]) <= timestamp(b["at"]) for a, b in pairwise(events)), "EVENT_CHRONOLOGY")
    seen: dict[str, str] = {}
    fills: dict[str, dict[str, Any]] = {}
    quantities: dict[str, Decimal] = {}
    snapshots: list[dict[str, Any]] = []
    deadline_breaches: list[str] = []
    expired_residuals: dict[str, dict[str, Any]] = {}
    total_external_cost = Decimal(0)
    outside_account_cost = Decimal(0)
    cost_ids: set[str] = set()
    for event in events:
        event_id = event["event_id"]
        need(isinstance(event_id, str) and bool(event_id), "EVENT_IDENTITY")
        identity = digest(event)
        if event_id in seen:
            need(identity == seen[event_id], "CONFLICTING_EVENT")
            continue
        seen[event_id] = identity
        at = timestamp(event["at"])
        need(start <= at <= end and at <= timestamp(event["received_at"]), "EVENT_CLOCK")
        kind = event["kind"]
        if kind == "FILL":
            oid, fid = event["order_id"], event["fill_id"]
            need(oid in orders and fid not in fills, "FILL_IDENTITY")
            order = orders[oid]
            campaign_id = order["campaign_id"]
            symbol = order["symbol"]
            spec = specs[symbol]
            need(spec["quote"] == "USD", "UNSUPPORTED_FX_OR_MARGIN")
            q, price = amount(event["quantity"], positive=True), amount(event["price"], positive=True)
            need(q % amount(spec["quantity_increment"], positive=True) == 0, "NATIVE_QUANTITY_INCREMENT")
            quantities[oid] = quantities.get(oid, Decimal(0)) + q
            need(quantities[oid] <= amount(order["quantity"]), "CUMULATIVE_OVERFILL")
            need(order["submitted_at"] <= at, "FILL_BEFORE_SUBMISSION")
            base, side = spec["base"], order["side"]
            if side == "sell":
                campaign_provision = sum((f["provision"] for f in fills.values()
                    if not f["posted"] and f["campaign_id"] == campaign_id and f["currency"] == base), Decimal(0))
                need(campaign_inventory[campaign_id] - campaign_provision >= q,
                     "CROSS_CAMPAIGN_OR_UNFUNDED_SELL")
            campaign_inventory[campaign_id] += q if side == "buy" else -q
            debit_asset, debit = ("USD", q * price) if side == "buy" else (base, q)
            pending = sum((f["provision"] for f in fills.values()
                           if not f["posted"] and f["currency"] == debit_asset), Decimal(0))
            need(balances.get(debit_asset, Decimal(0)) - pending >= debit, "UNFUNDED_OR_SHORT_FILL")
            credit_asset, credit = (base, q) if side == "buy" else ("USD", q * price)
            balances[debit_asset] = balances.get(debit_asset, Decimal(0)) - debit
            balances[credit_asset] = balances.get(credit_asset, Decimal(0)) + credit
            currency = event["fee_provision_currency"]
            need(currency in {base, "USD"}, "FEE_CURRENCY")
            fills[fid] = {"currency": currency, "provision": amount(event["fee_provision"]),
                          "posted": False, "order_id": oid, "campaign_id": campaign_id, "base_asset": base}
            if at > order["original_deadline"]:
                deadline_breaches.append(fid)
        elif kind == "FEE":
            fid = event["fill_id"]
            need(fid in fills and not fills[fid]["posted"], "FEE_DUPLICATE_OR_UNKNOWN_FILL")
            currency, fee = event["currency"], amount(event["amount"])
            need(currency == fills[fid]["currency"], "FEE_CURRENCY_MISMATCH")
            need(balances.get(currency, Decimal(0)) >= fee, "UNFUNDED_FEE")
            balances[currency] -= fee
            if currency == fills[fid]["base_asset"]:
                campaign_id = fills[fid]["campaign_id"]
                need(campaign_inventory[campaign_id] >= fee, "CAMPAIGN_NATIVE_FEE_INVENTORY")
                campaign_inventory[campaign_id] -= fee
            fills[fid]["posted"] = True
        elif kind == "EXTERNAL_COST":
            cost = amount(event["amount_usd"])
            need(event["cost_id"] not in cost_ids, "DUPLICATE_SHARED_COST")
            cost_ids.add(event["cost_id"])
            need(type(event["debited_from_account"]) is bool, "COST_SETTLEMENT_UNKNOWN")
            if event["debited_from_account"]:
                need(balances["USD"] >= cost, "UNFUNDED_EXTERNAL_COST")
                balances["USD"] -= cost
            else:
                outside_account_cost += cost
            total_external_cost += cost
        elif kind == "SNAPSHOT":
            reported = {asset: amount(value) for asset, value in event["balances"].items()}
            need(all(reported.get(a, Decimal(0)) == balances.get(a, Decimal(0))
                     for a in reported.keys() | balances.keys()), "BROKER_BALANCE_MISMATCH")
            marks = {asset: amount(value, positive=True) for asset, value in event["usd_marks"].items()}
            need(marks.get("USD") == 1, "USD_MARK")
            required_assets = {a for a, v in balances.items() if v != 0}
            required_assets |= {f["currency"] for f in fills.values() if not f["posted"] and f["provision"]}
            need(required_assets <= marks.keys(), "MISSING_MARK")
            for asset in required_assets - {"USD"}:
                mark_clock = event["mark_timestamps"][asset]
                mark_at, available = timestamp(mark_clock["event_at"]), timestamp(mark_clock["available_at"])
                need(mark_at <= available <= event["received_at"] and mark_at <= at,
                     "MARK_TIMESTAMP_LOOKAHEAD")
                need(at - mark_at <= protocol["max_mark_age_ms"], "STALE_ACCOUNT_MARK")
                derived = sum((qty for cid, qty in campaign_inventory.items()
                               if specs[campaigns[cid][2]]["base"] == asset), Decimal(0))
                need(derived == balances.get(asset, Decimal(0)), "CAMPAIGN_ACCOUNT_RECONCILIATION")
            for campaign_id, quantity in campaign_inventory.items():
                if quantity > 0 and at >= campaigns[campaign_id][1]:
                    expired_residuals.setdefault(campaign_id, {"campaign_id": campaign_id,
                        "observed_at": at, "original_deadline": campaigns[campaign_id][1],
                        "remaining_native_quantity": str(quantity)})
            gross = sum((qty * marks.get(asset, Decimal(0)) for asset, qty in balances.items()), Decimal(0))
            pending_usd = sum((f["provision"] * marks[f["currency"]] for f in fills.values()
                               if not f["posted"] and f["provision"]), Decimal(0))
            equity = gross - pending_usd - outside_account_cost
            need(equity > 0, "ECONOMIC_INSOLVENCY")
            need(amount(event["economic_equity_usd"], positive=True) == equity, "ECONOMIC_NAV_MISMATCH")
            snapshots.append({"at": at, "equity": str(equity), "pending_fees_usd": str(pending_usd)})
        else:
            raise ValueError("UNSUPPORTED_EVENT_OR_EXTERNAL_FLOW:" + str(kind))
    need(len(snapshots) >= 2 and snapshots[0]["at"] == start and snapshots[-1]["at"] == end,
         "PERIOD_BOUNDARY_SNAPSHOTS")
    need([s["at"] for s in snapshots] == protocol["observation_times"], "REGISTERED_OBSERVATION_COVERAGE")
    need(Decimal(snapshots[0]["equity"]) == initial, "INITIAL_ECONOMIC_CAPITAL")
    max_gap = protocol["max_snapshot_gap_ms"]
    need(type(max_gap) is int and 0 < max_gap <= 86_400_000, "OBSERVATION_GAP_LIMIT")
    need(all(0 < b["at"] - a["at"] <= max_gap for a, b in pairwise(snapshots)), "SNAPSHOT_GAP")
    equity_values = [float(s["equity"]) for s in snapshots]
    peak, drawdown = equity_values[0], 0.0
    logs: list[float] = []
    for previous, value in pairwise(equity_values):
        logs.append(math.log(value / previous))
        peak = max(peak, value)
        drawdown = max(drawdown, 1 - value / peak)
    pending_ids = [fid for fid, f in fills.items() if not f["posted"]]
    return {"schema": "HARPOON_ROADMAP_ACCOUNT_RECONCILIATION_1", "verified": True,
            "origin": packet["origin"], "packet_sha256": digest(packet), "account_ref": packet["account_ref"],
            "fill_count": len(fills), "unique_event_count": len(seen), "pending_fee_fill_ids": pending_ids,
            "deadline_breaches": deadline_breaches, "balances": {k: str(v) for k, v in balances.items()},
            "expired_residual_inventory": list(expired_residuals.values()),
            "campaign_inventory": {k: str(v) for k, v in campaign_inventory.items()},
            "snapshots": snapshots, "log_returns": logs, "initial_equity_usd": str(initial),
            "final_equity_usd": snapshots[-1]["equity"],
            "net_pnl_usd": str(Decimal(snapshots[-1]["equity"]) - initial),
            "external_costs_usd": str(total_external_cost), "observed_drawdown_fraction": drawdown,
            "source_authenticity_verified": False, "risk_between_snapshots_verified": False,
            "execution_allowed": False}


def block_growth_test(log_returns: list[float], control_returns: dict[str, list[float]],
                      settings: dict[str, Any]) -> dict[str, Any]:
    """Paired circular block bootstrap; endpoints and multiplicity are preregistered.

    Returns a diagnostic when the global search history is incomplete. Draws
    and overlapping trade paths are never counted as independent observations.
    """
    values = np.asarray(log_returns, dtype=float)
    need(values.ndim == 1 and len(values) >= 2 and bool(np.isfinite(values).all()), "FINITE_LOG_RETURNS")
    need({"CASH", "BASELINE"} <= control_returns.keys(), "PAIRED_CONTROLS_REQUIRED")
    need(type(settings["minimum_observations"]) is int and settings["minimum_observations"] >= 20,
         "SUPPORT_THRESHOLD")
    blocks = settings["block_lengths"]
    need(isinstance(blocks, list) and bool(blocks) and all(type(b) is int and 1 < b <= len(values) for b in blocks),
         "BLOCK_LENGTHS")
    draws, endpoints = settings["draws"], settings["family_endpoints"]
    need(type(draws) is int and 1000 <= draws <= 120000, "BOOTSTRAP_BUDGET")
    need(type(endpoints) is int and endpoints >= 1 + len(control_returns), "MULTIPLICITY_ENDPOINTS")
    alpha = settings["alpha"]
    need(type(alpha) in (float, int) and 0 < alpha <= 0.05, "ALPHA_PREDECLARED")
    delta = settings["minimum_mean_log_edge"]
    need(type(delta) in (float, int) and math.isfinite(delta) and delta >= 0, "ECONOMIC_MATERIALITY")
    series = {"ABSOLUTE": values}
    for name, control in control_returns.items():
        array = np.asarray(control, dtype=float)
        need(array.shape == values.shape and bool(np.isfinite(array).all()), "ALIGNED_CONTROL")
        series["MINUS_" + name] = values - array
    bounds: dict[str, dict[str, float]] = {}
    rng = np.random.default_rng(settings["seed"])
    for block in blocks:
        lower: dict[str, float] = {}
        samples = {name: np.empty(draws) for name in series}
        for offset in range(0, draws, 256):
            count = min(256, draws - offset)
            starts = rng.integers(0, len(values), size=(count, math.ceil(len(values) / block)))
            indices = ((starts[:, :, None] + np.arange(block)) % len(values)).reshape(count, -1)[:, :len(values)]
            for name, array in series.items():
                samples[name][offset:offset + count] = array[indices].mean(axis=1)
        for name, sample in samples.items():
            lower[name] = float(np.quantile(sample, alpha / endpoints))
        bounds[str(block)] = lower
    supported = len(values) >= settings["minimum_observations"]
    passed = supported and all(v > (0 if k == "ABSOLUTE" else delta)
                               for row in bounds.values() for k, v in row.items())
    complete = settings.get("global_search_history_complete") is True
    return {"schema": "HARPOON_ROADMAP_PAIRED_GROWTH_1", "observations": len(values),
            "draws_are_not_observations": True, "lower_mean_log_return_bounds": bounds,
            "within_family_criterion_passed": passed, "support_sufficient": supported,
            "global_search_correction_certified": False,
            "search_history_declared_complete": complete,
            "selection_scope": "WITHIN_REGISTERED_FAMILY_ONLY;GLOBAL_PROVENANCE_NOT_ESTABLISHED_BY_A_FLAG",
            "decision": "RETAIN_FOR_FORWARD" if passed and complete else "NO_CONCLUSION",
            "financial_acceptance_allowed": False}


def assess_forward(packet: dict[str, Any] | None, protocol: dict[str, Any] | None,
                   trust_store: dict[str, Any] | None = None, *, now_ms: int = 0) -> dict[str, Any]:
    """Account-evidence admission; never grants strategy or execution authority."""
    reasons: list[str] = []
    report: dict[str, Any] | None = None
    source: dict[str, Any] = {"verified": False, "reason": "ATTESTATION_REQUIRED"}
    if not packet or not protocol:
        reasons.append("OBSERVED_PACKET_AND_FROZEN_PROTOCOL_REQUIRED")
    else:
        try:
            report = reconcile_packet(packet, protocol)
            need(packet["origin"] in {"OBSERVED_LIVE", "OBSERVED_PAPER"}, "SYNTHETIC_NOT_OBSERVED")
            need(report["fill_count"] > 0, "OBSERVED_FILLS_REQUIRED")
            need(not report["pending_fee_fill_ids"], "UNRECONCILED_FEE_ACTIVITIES")
            need(not report["deadline_breaches"], "OBSERVED_DEADLINE_BREACH")
            need(not report["expired_residual_inventory"], "EXPIRED_RESIDUAL_INVENTORY")
            need(timestamp(protocol["evaluation_end"]) <= timestamp(now_ms), "FUTURE_EVALUATION_NOT_OBSERVED")
            need(all(timestamp(e["received_at"]) <= now_ms for e in packet["events"]),
                 "FUTURE_RECEIPT_NOT_OBSERVED")
            unsigned = {k: v for k, v in packet.items() if k != "source_attestation"}
            source = verify_attestation(packet.get("source_attestation"), trust_store or {},
                role="BROKER_SOURCE", expected={"packet_sha256": digest(unsigned),
                "protocol_sha256": digest(protocol), "account_ref": packet["account_ref"]}, now_ms=now_ms)
            if not source["verified"]:
                reasons.append("SOURCE_AUTHENTICATION:" + source["reason"])
        except (KeyError, TypeError, ValueError) as exc:
            reasons.append(str(exc))
    return {"schema": "HARPOON_ROADMAP_FORWARD_ADMISSION_1", "status": "ADMITTED_FOR_ANALYSIS" if not reasons else "BLOCKED",
            "blocking_reasons": reasons, "reconciliation": report, "source_attestation": source,
            "paper_is_live": False, "financial_acceptance_allowed": False,
            "external_review_completed": False, "execution_allowed": False,
            "remaining_gates": ["REGISTERED_PAIRED_PROSPECTIVE_ECONOMICS", "NOMINAL_AND_STRESS",
                                "RISK_AND_CAPACITY", "INDEPENDENT_EXTERNAL_REVIEW", "SCOPED_AUTHORIZATION"]}
