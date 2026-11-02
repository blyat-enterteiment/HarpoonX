"""Bounded offline inference of supplied JSON models through the real bridge.

This worker has no fitting, discovery, broker or promotion action. A receipt
binds exact request/model bytes to a reproduced calculation, not to valid model
training or market profitability. It is used only by the isolated replay tool.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

from .bridge import from_runtime, ms
from .core import FEATURES, ORIGINS, Config, predict, timestamp

PACKET_SCHEMA = "HARPOON_FIXED_PREDICTOR_PACKET_1"
RECEIPT_SCHEMA = "HARPOON_FIXED_PREDICTOR_RECEIPT_1"
MAX_PACKET_BYTES = 32 * 1024 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json(text: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    result = json.loads(text, object_pairs_hook=pairs)
    json.dumps(result, allow_nan=False)
    return result


def source_hashes() -> dict[str, str]:
    """All package sources, including the existing feature and inference code."""
    root = Path(__file__).resolve().parent
    return {
        "quant/harpoon_quant/" + p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.glob("*.py"))
    }


def validate_model(model: dict[str, Any], name: str, raw: dict[str, Any]) -> None:
    if name not in {"RIDGE", "SVR"} or not isinstance(model, dict):
        raise ValueError("FIXED_MODEL_REQUIRED")
    if model.get("origin") not in ORIGINS:
        raise ValueError("MODEL_ORIGIN_REQUIRED")
    inner = model.get("models")
    if not isinstance(inner, dict) or not 1 <= len(inner) <= 16:
        raise ValueError("MODEL_ASSET_BUDGET")
    if model.get("feature_names") != list(FEATURES):
        raise ValueError("MODEL_FEATURE_CONTRACT")
    cfg = Config(**raw["config"].get("quant", {}).get("config", {}))
    if model.get("horizon_hours") != cfg.horizon_hours:
        raise ValueError("MODEL_HORIZON_MISMATCH")
    available = timestamp(model["available_at"])
    if available >= timestamp(ms(raw["now"])):
        raise ValueError("MODEL_NOT_AVAILABLE_AT_DECISION")
    if name == "RIDGE":
        if model.get("schema") not in {None, "HARPOON_QUANT_CALIBRATION_1"}:
            raise ValueError("RIDGE_MODEL_SCHEMA")
        kinds: tuple[str | None, ...] = (None, "RIDGE")
    else:
        if model.get("schema") != "HARPOON_QUANT_CALIBRATION_2":
            raise ValueError("SVR_MODEL_SCHEMA")
        if model.get("research_only") is not True:
            raise ValueError("SVR_RESEARCH_ONLY_REQUIRED")
        kinds = ("SVR_RBF",)
    if model.get("model_kind") not in kinds or any(
        not isinstance(m, dict) or m.get("model_kind") not in kinds
        for m in inner.values()
    ):
        raise ValueError("PREDICTOR_ESTIMATOR_BINDING")
    # An inference receipt cannot repair future residuals or silently relabel
    # their unit. Detailed fitted-model checks remain in the existing predictor.
    for m in inner.values():
        residuals = m.get("residuals")
        if not isinstance(residuals, dict):
            raise ValueError("MODEL_RESIDUAL_PANEL_REQUIRED")
        for date, value in residuals.items():
            if timestamp(date + "T00:00:00+00:00") >= available:
                raise ValueError("FUTURE_MODEL_RESIDUAL")
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError("MODEL_RESIDUAL_DOMAIN")


def calculate(packet: dict[str, Any]) -> dict[str, Any]:
    if packet.get("schema") != PACKET_SCHEMA:
        raise ValueError("FIXED_PREDICTOR_PACKET_SCHEMA")
    for field in ("request", "model"):
        text = packet[field + "_json"]
        if not isinstance(text, str) or sha(text) != packet[field + "_hash"]:
            raise ValueError("FIXED_PREDICTOR_" + field.upper() + "_HASH")
    raw, model = _json(packet["request_json"]), _json(packet["model_json"])
    if not isinstance(raw, dict) or raw.get("runtime_snapshot") is not True:
        raise ValueError("REAL_RUNTIME_SNAPSHOT_REQUIRED")
    cfg = raw.get("config", {})
    quant = cfg.get("quant", {})
    if (
        cfg.get("mode") != "paper"
        or cfg.get("streaming") is not False
        or cfg.get("nativeProtection") != "stop"
        or not str(cfg.get("expected_account_id", "")).startswith("OFFLINE-")
        or quant.get("enabled") is not False
        or quant.get("optimizer", {}).get("enabled", False)
        or quant.get("microstructure", {}).get("enabled", False)
    ):
        raise ValueError("OFFLINE_FIXED_INFERENCE_CONFIGURATION")
    if not isinstance(raw.get("signals"), list) or len(raw["signals"]) > 96:
        raise ValueError("SIGNAL_COMPUTE_BUDGET")
    validate_model(model, packet["predictor"], raw)
    before = source_hashes()
    result = from_runtime(raw, model)
    forecast_checks = []
    # Re-evaluate the existing predictor on the exact normalized feature vectors
    # saved by the allocator. This records whether any numerical prediction was
    # actually possible, separately from merely reproducing a blocking branch.
    prediction_config = Config(**quant.get("config", {}))
    for candidate in result.get("decision_inputs", {}).get("candidates", []):
        check = {"id": candidate["id"], "underlying": candidate["underlying"]}
        try:
            value = predict(
                model,
                candidate["underlying"],
                candidate["features"],
                ms(raw["now"]),
                prediction_config,
            )
            check.update(status="COMPUTED", predicted_return=value)
        except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
            check.update(status="BLOCKED", predicted_return=None, reason=str(exc))
        forecast_checks.append(check)
    if before != source_hashes():
        raise ValueError("PREDICTOR_SOURCE_CHANGED_DURING_INFERENCE")
    # Preserve the actual engine output in an explicit, non-authorizing envelope.
    # In particular SVR remains SHADOW_RESEARCH_ONLY with execution_allowed=false.
    result_text = json.dumps(
        result, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    if len(result_text.encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise ValueError("FIXED_PREDICTOR_OUTPUT_LIMIT")
    return {
        "schema": RECEIPT_SCHEMA,
        "status": "COMPUTED",
        "predictor": packet["predictor"],
        "request_hash": packet["request_hash"],
        "model_hash": packet["model_hash"],
        "model_origin": model["origin"],
        "model_available_at": model["available_at"],
        "source_hashes": before,
        "result_json": result_text,
        "result_hash": sha(result_text),
        "forecast_checks": forecast_checks,
        "training_executed": False,
        "training_provenance_verified": False,
        "execution_allowed": False,
        "liveApproved": False,
        "financial_acceptance_allowed": False,
        "scope": "REEXECUTABLE_FIXED_JSON_INFERENCE_NOT_MODEL_TRAINING_OR_FINANCIAL_VALIDATION",
    }


def _deny_external_io() -> None:
    """Defense in depth for the fixed local worker, not a general code sandbox."""
    import os
    import socket
    import subprocess

    def deny(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("OFFLINE_FIXED_PREDICTOR_EXTERNAL_IO_DENIED")

    socket.socket.connect = deny  # type: ignore[assignment]
    socket.socket.connect_ex = deny  # type: ignore[assignment]
    socket.socket.sendto = deny  # type: ignore[assignment]
    socket.create_connection = deny
    subprocess.Popen = deny  # type: ignore[assignment,misc]
    os.system = deny
    os.popen = deny


def main() -> None:
    _deny_external_io()
    for _ in range(20000):
        line = sys.stdin.buffer.readline(MAX_PACKET_BYTES + 1)
        if not line:
            return
        try:
            if len(line) > MAX_PACKET_BYTES or not line.endswith(b"\n"):
                raise ValueError("FIXED_PREDICTOR_INPUT_LIMIT")
            result = calculate(_json(line.decode("utf-8")))
        except (
            ValueError,
            KeyError,
            TypeError,
            ArithmeticError,
            OSError,
            RuntimeError,
        ) as exc:
            result = {
                "schema": RECEIPT_SCHEMA,
                "status": "BLOCKED",
                "reason": str(exc),
                "execution_allowed": False,
                "liveApproved": False,
                "financial_acceptance_allowed": False,
            }
        sys.stdout.write(
            json.dumps(result, allow_nan=False, separators=(",", ":")) + "\n"
        )
        sys.stdout.flush()


if __name__ == "__main__":
    main()
