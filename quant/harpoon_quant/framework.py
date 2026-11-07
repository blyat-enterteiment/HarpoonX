"""Public quant-core entry for the technical multiasset research framework.

Input is an in-memory packet, not arbitrary filesystem paths or an acceptance
report. Every account is reconstructed before qualification is calculated.
"""

from __future__ import annotations

import json
from typing import Any

from .compound import BOOKS
from .qualification import qualify_history
from .remediation import order_costs, sector_decision, training_indices
from .roadmap9.forward import digest
from .swing_evidence import verify_account


def loads(raw: bytes) -> dict[str, Any]:
    """Reject ambiguous or nonfinite JSON before dispatch, up to the worker cap."""
    if len(raw) > 33554432:
        raise ValueError("FRAMEWORK_INPUT_LIMIT")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError("DUPLICATE_FRAMEWORK_JSON_KEY")
            out[key] = value
        return out

    def constant(value: str) -> None:
        raise ValueError("NONFINITE_FRAMEWORK_JSON:" + value)

    result = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    if not isinstance(result, dict):
        raise ValueError("FRAMEWORK_OBJECT_REQUIRED")
    return result


def evaluate(packet: dict[str, Any]) -> dict[str, Any]:
    """Run one explicitly named, bounded module without granting broker authority."""
    if (
        not isinstance(packet, dict)
        or packet.get("schema") != "HARPOON_QUANT_FRAMEWORK_1"
    ):
        raise ValueError("FRAMEWORK_SCHEMA")
    if set(packet) != {"schema", "operation", "payload"}:
        raise ValueError("FRAMEWORK_FIELDS")
    operation, payload = packet["operation"], packet["payload"]
    if not isinstance(payload, dict):
        raise ValueError("FRAMEWORK_PAYLOAD")
    result: dict[str, Any]
    audit: dict[str, Any] = {}
    if operation == "QUALIFY_HISTORY":
        if (
            set(payload) != {"origin", "accounts", "dividend_symbols"}
            or payload["origin"] != "HISTORICAL_MODELED"
        ):
            raise ValueError("MODELED_HISTORY_PACKET_REQUIRED")
        scenarios = payload["accounts"]
        if not isinstance(scenarios, dict) or set(scenarios) != {"NOMINAL", "STRESS"}:
            raise ValueError("BOTH_COST_SCENARIOS_REQUIRED")
        symbols = payload["dividend_symbols"]
        if not isinstance(symbols, dict) or not all(
            isinstance(k, str) and k and isinstance(v, str) and v
            for k, v in symbols.items()
        ):
            raise ValueError("DIVIDEND_SYMBOL_MAP_REQUIRED")
        for scenario, books in scenarios.items():
            if not isinstance(books, dict) or set(books) != set(BOOKS):
                raise ValueError("FOUR_FUNDED_ACCOUNTS_REQUIRED")
            for book, account in books.items():
                audit[scenario + "_" + book] = verify_account(account)
        result = qualify_history(
            scenarios, dividend_symbols=payload["dividend_symbols"]
        )
        status = result["decision"]
    elif operation == "MOMENTUM_BASE":
        from .momentum_base import analyze

        result = analyze(payload)
        status = "MOMENTUM_BASE_RESEARCH"
    elif operation == "INTRADAY_REPLAY":
        from .intraday import replay

        result = replay(payload)
        status = "INTRADAY_RESEARCH"
    elif operation == "SIMULATE_SESSION":
        from .roadmap9.integration import process

        result = process(payload)
        result["simulation_mode"] = "LOCAL_SYNTHETIC"
        result["broker_paper_connected"] = False
        status = "SIMULATION_SESSION"
    elif operation == "TECHNICAL_SWING":
        if set(payload) != {"dataset", "snapshots", "asof"}:
            raise ValueError("TECHNICAL_PACKET_FIELDS")
        result = sector_decision(
            payload["dataset"], payload["snapshots"], payload["asof"]
        )
        status = "RESEARCH_SIGNAL"
    elif operation == "PURGE_LABELS":
        if set(payload) != {"labels", "test_start"} or len(payload["labels"]) > 100000:
            raise ValueError("LABEL_PACKET_FIELDS_OR_BUDGET")
        result = {
            "training_indices": training_indices(
                payload["labels"], payload["test_start"]
            )
        }
        status = "TRAINING_INDICES"
    elif operation == "ORDER_COSTS":
        if (
            len(payload.get("orders", [])) > 100000
            or len(payload.get("fills", [])) > 100000
        ):
            raise ValueError("ORDER_PACKET_BUDGET")
        result = order_costs(payload)
        status = "COST_DIAGNOSTIC"
    else:
        raise ValueError("UNKNOWN_FRAMEWORK_OPERATION")
    def numeric_identity(value: Any) -> Any:
        # Node JSON.stringify writes 1.0 as 1. Preserve numeric equality across
        # the real bridge without collapsing distinct nonintegral numbers.
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, dict):
            return {k: numeric_identity(v) for k, v in value.items()}
        if isinstance(value, list):
            return [numeric_identity(v) for v in value]
        return value

    return {
        "schema": "HARPOON_QUANT_FRAMEWORK_RESULT_1",
        "operation": operation,
        "status": status,
        "result": result,
        "ledger_audit": audit,
        "input_canonical_sha256": digest(numeric_identity(packet)),
        "input_hash_serialization": "SORTED_JSON_INTEGRAL_FLOATS_AS_INTEGERS",
        "source_authenticity_verified": False,
        "selected": [],
        "execution_allowed": False,
        "liveApproved": False,
        "level8_accredited": False,
    }
