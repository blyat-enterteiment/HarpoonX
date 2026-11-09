"""M11 diagnostic-only, unmodified-law substep sidecar.

Observe the original M9 generator at its pre-existing intrabar-array boundary.
No RNG draw, patched source, changed signal, or interpolated market is allowed.
The sidecar must never be supplied to an entry/signal policy.
"""

from __future__ import annotations

import hashlib
import inspect
import sys
from pathlib import Path
from typing import Any

import numpy as np

from . import modulation9, modulation10

GENERATOR_SHA256 = "9d4afa402d2b70791f175e79219495f9bbbe25eb3cd0b7e9212cef6bccbd68ab"


def export_substeps(protocol: dict[str, Any], seed: int, world: str, stage: str) -> dict[str, Any]:
    """Return checksummed OHLCV, unaltered nominations and execution-only samples.

    A source hash and a second, uninstrumented generation must both agree.
    This requires the original deterministic generator and is not a new price law.
    """
    if stage not in ("development", "fixture"):
        raise ValueError("M11_FINAL_SEALED")
    if stage == "development" and seed not in protocol["stages"]["development"]["seeds"]:
        raise ValueError("M11_UNREGISTERED_DEVELOPMENT_SEED")
    source = Path(modulation9.__file__)
    if hashlib.sha256(source.read_bytes()).hexdigest() != GENERATOR_SHA256:
        raise RuntimeError("M11_FROZEN_GENERATOR_HASH_MISMATCH")
    if sys.gettrace() is not None:
        raise RuntimeError("M11_TRACE_IN_USE")
    if protocol["generator"]["intrabar_substeps"] != 8 or protocol["generator"]["bars_per_session"] != 78:
        raise ValueError("M11_GRID_CONTRACT_CHANGED")
    generator = modulation9.market
    lines, start = inspect.getsourcelines(generator)
    capture_lines = [start + index for index, line in enumerate(lines)
                     if line.strip() == "closes = intrabar[:, -1, :]"]
    if len(capture_lines) != 1:
        raise RuntimeError("M11_INTRABAR_CAPTURE_BOUNDARY_CHANGED")
    capture_at = capture_lines[0]
    samples: list[np.ndarray] = []

    def on_market(frame: Any, event: str, arg: Any) -> Any:
        del arg
        if event == "line" and frame.f_lineno == capture_at:
            values = frame.f_locals.get("intrabar")
            if not isinstance(values, np.ndarray) or values.shape != (78, 8, 3):
                raise RuntimeError("M11_INTRABAR_SHAPE_MISMATCH")
            if not bool(np.isfinite(values).all()) or not bool((values > 0).all()):
                raise RuntimeError("M11_NONFINITE_SUBSTEP")
            samples.append(values.copy())
        return on_market

    def on_call(frame: Any, event: str, arg: Any) -> Any:
        del arg
        return on_market if event == "call" and frame.f_code is generator.__code__ else None

    try:
        sys.settrace(on_call)
        dataset = generator(protocol, seed, world, stage)
    finally:
        sys.settrace(None)
    # A second call is intentionally outside tracing; this is a deterministic
    # identity check, not an independent sample or a selectable economic trial.
    plain = generator(protocol, seed, world, stage)
    if modulation9.digest(dataset) != modulation9.digest(plain):
        raise RuntimeError("M11_OHLCV_IDENTITY_FAILURE")
    if len(samples) != len(dataset["sessions"]):
        raise RuntimeError("M11_SESSION_CAPTURE_COUNT_MISMATCH")
    sidecar: list[dict[str, Any]] = []
    for index, session in enumerate(dataset["sessions"]):
        if session["close"] - session["open"] != 78 * 300000:
            raise RuntimeError("M11_UNEXPECTED_SESSION_INTERVAL")
        for j, series in enumerate(dataset["series"]):
            if series["symbol"] != modulation9.SYMBOLS[j]:
                raise RuntimeError("M11_SYMBOL_ORDER_CHANGED")
            for k in range(78):
                bar = series["bars"][index * 78 + k]
                sub = samples[index][k, :, j].tolist()
                if (bar["c"] != sub[-1] or bar["h"] != max(bar["o"], *sub)
                        or bar["l"] != min(bar["o"], *sub)
                        or bar["t"] != session["open"] + k * 300000
                        or bar["end"] != bar["t"] + 300000
                        or bar["availableAt"] != bar["end"] + 1000):
                    raise RuntimeError("M11_SUBSTEP_TO_OHLCV_MISMATCH")
                sidecar.append({"symbol": series["symbol"], "t": bar["t"],
                                "end": bar["end"], "availableAt": bar["availableAt"],
                                "prices": sub})
    signals = modulation10.nominations(dataset, protocol)
    if modulation9.digest(signals) != modulation9.digest(modulation10.nominations(plain, protocol)):
        raise RuntimeError("M11_SIGNAL_IDENTITY_FAILURE")
    return {"schema": "HARPOON_M11_SUBSTEP_SIDECAR_1", "stage": stage,
            "origin": "SYNTHETIC_DIAGNOSTIC_ONLY", "seed": seed, "world": world,
            "generator_sha256": GENERATOR_SHA256,
            "dataset_sha256": modulation9.digest(dataset),
            "signals_sha256": modulation9.digest(signals),
            "substeps_sha256": modulation9.digest(sidecar),
            "substep_count": len(sidecar) * 8,
            "disclosure": "Execution audit only; never provided to signals or entry decisions",
            "dataset": dataset, "signals": signals, "substeps": sidecar}
