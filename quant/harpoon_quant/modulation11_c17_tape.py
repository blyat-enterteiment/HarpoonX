"""C17: deterministic recovery of frozen M9 WEAK ordered intrabar tape.

No market-law changes. Uses exactly one previously registered DEVELOPMENT seed.
There are no nominations, policy calls, native accounts or final seeds.
The tape is for execution auditing only; never supply to signal computation.
"""
from __future__ import annotations

import gzip
import hashlib
import inspect
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

from . import modulation9

ROOT = Path(__file__).resolve().parents[2]
GENERATOR_SHA256 = "9d4afa402d2b70791f175e79219495f9bbbe25eb3cd0b7e9212cef6bccbd68ab"
PROTOCOL_SHA256 = "de694919b0908fc0ecf474c9612ff7d54fe04db635a385e12ffa0f81abc7780d"
SEED = 730101
WORLD = "WEAK"
STAGE = "development"
SUBSTEPS = 8
BARS = 78
EVAL_SESSIONS = 126
ASSETS = ("SYNA", "SYNB")
SCHEMA = "HARPOON_M11_C17_REGISTERED_DEVELOPMENT_WEAK_8STEP_TAPE_1"
NUMERIC_TAPE_7DP_SHA256 = "a173af77533f7bbe2b0a3ae54485ee64bc4f33cc83a01b860efdb0702d102398"


def canonical_numeric_tape_digest(rows: list[dict[str, Any]]) -> str:
    """Cross-run seven-decimal *audit* fingerprint, never a trading price.

    The original exact float tape is preserved separately. This quantization
    is a provenance equality guard under observed CPU floating-point drift,
    not a replacement for native execution prices or bitwise source identity.
    """
    normalized = [
        {
            "symbol": row["symbol"], "t": row["t"], "end": row["end"],
            "open": f'{row["open"]:.7f}',
            "high": f'{row["high"]:.7f}',
            "low": f'{row["low"]:.7f}',
            "close": f'{row["close"]:.7f}',
            "prices": [f"{p:.7f}" for p in row["prices"]],
        }
        for row in rows
    ]
    return modulation9.digest(normalized)



def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _original_protocol() -> dict[str, Any]:
    p = ROOT / "research/modulation9/protocol.json"
    if _sha256(p) != PROTOCOL_SHA256:
        raise RuntimeError("C17_FROZEN_M9_PROTOCOL_HASH")
    if _sha256(Path(modulation9.__file__)) != GENERATOR_SHA256:
        raise RuntimeError("C17_FROZEN_M9_GENERATOR_HASH")
    out: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    g = out["generator"]
    if (g["intrabar_substeps"] != SUBSTEPS or
            g["bars_per_session"] != BARS or
            g["evaluation_sessions"] != EVAL_SESSIONS or
            SEED not in out["stages"][STAGE]["seeds"] or
            ASSETS != tuple(out["traded_universe"])):
        raise RuntimeError("C17_FROZEN_M9_PARAMETERS")
    return out


def recover_registered_tape(
    seed: int = SEED, world: str = WORLD, stage: str = STAGE
) -> dict[str, Any]:
    """Recover the same already-opened M9 development market path, not new data.

    The original market() code runs with an observer restricted to one source
    line, exactly as existing M11 modulation11_substeps.py. A second untraced
    invocation of the SAME seed proves internal deterministic equivalence.
    This does not claim byte identity with the historic gz archive unless
    that original archive is available for an additional hash check.
    """
    if stage != STAGE or world != WORLD or seed != SEED:
        raise ValueError("C17_ONLY_REGISTERED_M9_WEAK_DEVELOPMENT_SEED_730101")
    if sys.gettrace() is not None:
        raise RuntimeError("C17_TRACE_ALREADY_IN_USE")
    protocol = _original_protocol()
    original = modulation9.market
    lines, start = inspect.getsourcelines(original)
    boundary = [
        start + i for i, line in enumerate(lines)
        if line.strip() == "closes = intrabar[:, -1, :]"
    ]
    if len(boundary) != 1:
        raise RuntimeError("C17_ORIGINAL_INTRABAR_OBSERVER_BOUNDARY_CHANGED")
    captured: list[np.ndarray[Any, Any]] = []

    def trace_market(frame: Any, event: str, arg: Any) -> Any:
        del arg
        if event == "line" and frame.f_lineno == boundary[0]:
            matrix = frame.f_locals.get("intrabar")
            if not isinstance(matrix, np.ndarray) or matrix.shape != (78, 8, 3):
                raise RuntimeError("C17_ORIGINAL_INTRABAR_SHAPE_CHANGED")
            if not bool(np.isfinite(matrix).all()) or not bool((matrix > 0).all()):
                raise RuntimeError("C17_NONPOSITIVE_OR_NONFINITE_PRICE")
            captured.append(matrix.copy())
        return trace_market

    def call_trace(frame: Any, event: str, arg: Any) -> Any:
        del arg
        return trace_market if event == "call" and frame.f_code is original.__code__ else None

    try:
        sys.settrace(call_trace)
        traced = original(protocol, seed, world, stage)
    finally:
        sys.settrace(None)
    plain = original(protocol, seed, world, stage)
    dataset_hash = modulation9.digest(traced)
    if dataset_hash != modulation9.digest(plain):
        raise RuntimeError("C17_TRACE_HAS_CHANGED_OHLCV")
    sessions = traced["sessions"]
    if len(captured) != len(sessions):
        raise RuntimeError("C17_TRACE_SESSION_COUNT_MISMATCH")
    evaluation_start = int(protocol["generator"]["warmup_sessions"])
    evaluation_end = evaluation_start + EVAL_SESSIONS
    if evaluation_end > len(sessions):
        raise RuntimeError("C17_EVALUATION_OUTSIDE_RECORDED_SESSIONS")
    tape: list[dict[str, Any]] = []
    evaluated_bars = 0
    for i, session in enumerate(sessions):
        for index, source in enumerate(traced["series"]):
            symbol = str(source["symbol"])
            if symbol != modulation9.SYMBOLS[index]:
                raise RuntimeError("C17_M9_SYMBOL_ORDER_CHANGED")
            for k in range(BARS):
                bar = source["bars"][i * BARS + k]
                values = captured[i][k, :, index].tolist()
                original_open = float(bar["o"])
                if (
                    bar["t"] != session["open"] + k * 300000 or
                    bar["end"] != bar["t"] + 300000 or
                    bar["availableAt"] != bar["end"] + 1000 or
                    float(bar["c"]) != values[-1] or
                    float(bar["h"]) != max([original_open, *values]) or
                    float(bar["l"]) != min([original_open, *values])
                ):
                    raise RuntimeError("C17_TRACED_8STEP_NOT_IDENTICAL_TO_M9_OHLCV")
                if (evaluation_start <= i < evaluation_end and symbol in ASSETS):
                    tape.append({
                        "symbol": symbol,
                        "t": int(bar["t"]),
                        "end": int(bar["end"]),
                        "open": original_open,
                        "low": float(bar["l"]),
                        "high": float(bar["h"]),
                        "close": float(bar["c"]),
                        "prices": values,
                    })
        if evaluation_start <= i < evaluation_end:
            evaluated_bars += BARS
    if len(tape) != EVAL_SESSIONS * BARS * len(ASSETS):
        raise RuntimeError("C17_TAPE_EVALUATION_CARDINALITY")
    if evaluated_bars != 9828:
        raise RuntimeError("C17_UNEXPECTED_EVALUATION_GRID")
    tape_digest = modulation9.digest(tape)
    numeric_digest = canonical_numeric_tape_digest(tape)
    if numeric_digest != NUMERIC_TAPE_7DP_SHA256:
        raise RuntimeError("C17_CROSS_RUN_7DP_NUMERIC_IDENTITY_MISMATCH")
    return {
        "schema": SCHEMA,
        "stage": stage,
        "world": world,
        "seed": seed,
        "origin": "REPLAYED_EXISTING_REGISTERED_DEVELOPMENT_SEED",
        "source_sha256": GENERATOR_SHA256,
        "protocol_sha256": PROTOCOL_SHA256,
        "dataset_sha256": dataset_hash,
        "eightstep_sha256": tape_digest,
        "seven_decimal_numeric_tape_sha256": numeric_digest,
        "numeric_7dp_equivalence_is_not_bitwise_identity": True,
        "evaluation_start_at": sessions[evaluation_start]["open"],
        "evaluation_end_at": sessions[evaluation_end - 1]["close"],
        "evaluation_sessions": EVAL_SESSIONS,
        "bars_per_session": BARS,
        "asset_count": len(ASSETS),
        "bar_asset_count": len(tape),
        "per_asset_substep_count": evaluated_bars * SUBSTEPS,
        "total_asset_substep_price_count": len(tape) * SUBSTEPS,
        "signal_generation_calls": 0,
        "economic_account_executions": 0,
        "new_seeds": 0,
        "final_holdout_opened": False,
        "historic_archive_byte_match_verified": False,
        "execution_audit_only": True,
        "tape": tape,
    }


def save_registered_tape(filename: Path, report: dict[str, Any]) -> dict[str, Any]:
    """Write a reproducible artifact; no historical archive is overwritten."""
    if report.get("schema") != SCHEMA or report.get("seed") != SEED:
        raise ValueError("C17_UNREGISTERED_REPORT")
    raw = modulation9.canonical(report)
    filename.parent.mkdir(parents=True, exist_ok=True)
    with filename.open("wb") as target:
        with gzip.GzipFile(filename="", mode="wb", fileobj=target, mtime=0) as gz:
            gz.write(raw)
    return {
        "artifact_sha256": hashlib.sha256(filename.read_bytes()).hexdigest(),
        "artifact_bytes": filename.stat().st_size,
        "dataset_sha256": report["dataset_sha256"],
        "tape_sha256": report["eightstep_sha256"],
        "seven_decimal_numeric_tape_sha256": report["seven_decimal_numeric_tape_sha256"],
        "substep_prices": report["total_asset_substep_price_count"],
        "archive_original_identity_proved": False,
    }


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--world", default=WORLD)
    parser.add_argument("--stage", default=STAGE)
    args = parser.parse_args()
    report = recover_registered_tape(args.seed, args.world, args.stage)
    output = save_registered_tape(args.out, report)
    print("FWN9_C17_REPRODUCED_TAPE=" + json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
