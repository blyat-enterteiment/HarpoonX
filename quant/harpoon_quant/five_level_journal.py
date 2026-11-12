"""Append-only local C38 risk-veto state, fail-closed across restarts.

No external attestation, broker receipt or trading action. A forced shutdown
leaves an exclusive lock requiring human review; it never clears a sell-exit
intent, a purchase veto or outstanding order reservations automatically.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from harpoon_quant.five_level_guard import Grid, Latch, empty_latch, validate_grid

_SCHEMA = "HARPOON_FWN9_C38_PERSISTED_BUY_VETO_1"
_ROW = "HARPOON_FWN9_C38_BUY_VETO_STATE_ROW_1"


def _hash(x: object) -> str:
    return hashlib.sha256(json.dumps(
        x, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()).hexdigest()


def _safe_dir(directory: Path) -> None:
    if (not directory.is_dir() or directory.is_symlink()
            or directory.stat().st_mode & 0o077):
        raise ValueError("C38J_PRIVATE_DIRECTORY_REQUIRED")


def _safe_file(file: Path) -> None:
    if (not file.is_file() or file.is_symlink()
            or file.stat().st_mode & 0o777 != 0o600
            or file.stat().st_size > 4_000_000):
        raise ValueError("C38J_PRIVATE_FILE_0600_REQUIRED")


def _write_new(path: Path, contents: bytes) -> None:
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=False) as writer:
            writer.write(contents)
            writer.flush()
            os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_dir(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _row(index: int, previous: str, manifest_hash: str,
         state: Latch) -> dict[str, Any]:
    r: dict[str, Any] = {
        "schema": _ROW,
        "index": index, "previous": previous,
        "manifest_sha256": manifest_hash,
        "state": asdict(state),
    }
    return {**r, "chain_sha256": _hash(r)}


def create(directory: Path, grid: Grid) -> dict[str, object]:
    validate_grid(grid)
    if directory.exists() or "holdout" in directory.parts or "M10_final" in directory.parts:
        raise ValueError("C38J_NEW_NONHOLDOUT_DIRECTORY")
    directory.mkdir(mode=0o700, parents=False, exist_ok=False)
    manifest = {
        "schema": _SCHEMA,
        "source_grid_generation": grid.generation,
        "source_grid_sha256": _hash(asdict(grid)),
        "external_market_or_broker_attestation": False,
        "cancelled_order_assumed_confirmed": False,
        "paper_or_live_orders_allowed": False,
        "N9S": "NO_GO",
    }
    sha = _hash(manifest)
    _write_new(directory / "manifest.json", (
        json.dumps({**manifest, "manifest_sha256": sha}) + "\n"
    ).encode())
    genesis = _row(1, "GENESIS", sha, empty_latch(grid))
    _write_new(directory / "latch.ndjson",
               (json.dumps(genesis) + "\n").encode())
    _fsync_dir(directory)
    return verify(directory, grid)


def verify(directory: Path, grid: Grid) -> dict[str, Any]:
    validate_grid(grid)
    _safe_dir(directory)
    names = set(x.name for x in directory.iterdir())
    if not names.issubset({"manifest.json", "latch.ndjson", ".writer.lock"}):
        raise ValueError("C38J_UNEXPECTED_FILE")
    mf, log = directory / "manifest.json", directory / "latch.ndjson"
    _safe_file(mf)
    _safe_file(log)
    m = json.loads(mf.read_text())
    clean = dict(m)
    claimed = clean.pop("manifest_sha256", None)
    if (
        m.get("schema") != _SCHEMA
        or m.get("source_grid_generation") != grid.generation
        or m.get("source_grid_sha256") != _hash(asdict(grid))
        or m.get("external_market_or_broker_attestation") is not False
        or m.get("cancelled_order_assumed_confirmed") is not False
        or m.get("paper_or_live_orders_allowed") is not False
        or m.get("N9S") != "NO_GO"
        or claimed != _hash(clean)
    ):
        raise ValueError("C38J_MANIFEST_MISMATCH")
    raw = log.read_text()
    if not raw.endswith("\n"):
        raise ValueError("C38J_TRUNCATED_STATE_LOG")
    lines = raw.splitlines()
    head = "GENESIS"
    state: Latch | None = None
    for index, line in enumerate(lines, start=1):
        if len(line) > 12_000:
            raise ValueError("C38J_OVERSIZED_ENTRY")
        record = json.loads(line)
        digest = record.get("chain_sha256")
        clean = dict(record)
        clean.pop("chain_sha256", None)
        if (record.get("schema") != _ROW
                or record.get("index") != index
                or record.get("previous") != head
                or record.get("manifest_sha256") != claimed
                or digest != _hash(clean)):
            raise ValueError("C38J_CHAIN_OR_SEQUENCE_TAMPER")
        data = record.get("state")
        if not isinstance(data, dict):
            raise ValueError("C38J_INVALID_STATE")
        candidate = Latch(**data)
        if (candidate.generation != grid.generation
                or type(candidate.veto_latched) is not bool
                or type(candidate.exit_pending_unconfirmed) is not bool
                or not isinstance(candidate.last_known_at_ms, int)
                or candidate.last_known_at_ms < 0):
            raise ValueError("C38J_INVALID_STATE")
        if state is not None and (
            candidate.last_known_at_ms < state.last_known_at_ms
            or state.veto_latched and not candidate.veto_latched
            or state.exit_pending_unconfirmed and not candidate.exit_pending_unconfirmed
        ):
            raise ValueError("C38J_UNAUTHORIZED_STATE_RESET")
        if index == 1 and candidate != empty_latch(grid):
            raise ValueError("C38J_INVALID_GENESIS")
        state, head = candidate, str(digest)
    if state is None:
        raise ValueError("C38J_MISSING_GENESIS")
    return {
        "schema": "HARPOON_FWN9_C38_DURABLE_BUY_VETO_RESTART_AUDIT_1",
        "entries": len(lines), "head": head, "state": state,
        "local_integrity_verified": True,
        "broker_source_independently_authenticated": False,
        "state_reset_without_independent_rearm": False,
        "paper_or_live_orders_allowed": False,
        "N9S": "NO_GO",
    }


class Writer:
    def __init__(self, directory: Path, grid: Grid) -> None:
        current = verify(directory, grid)
        lock = directory / ".writer.lock"
        try:
            self._lock = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise ValueError("C38J_STALE_LOCK_REQUIRES_REVIEW") from exc
        os.close(self._lock)
        self._directory = directory
        self._grid = grid
        self._head = str(current["head"])
        self._index = int(current["entries"])
        self._state = current["state"]
        self._manifest = json.loads((directory / "manifest.json").read_text())
        self._closed = False
        self._fd = os.open(directory / "latch.ndjson", os.O_WRONLY | os.O_APPEND)

    def append(self, state: Latch) -> dict[str, Any]:
        if self._closed:
            raise ValueError("C38J_WRITER_CLOSED")
        if (state.generation != self._grid.generation
                or state.last_known_at_ms < self._state.last_known_at_ms
                or self._state.veto_latched and not state.veto_latched
                or self._state.exit_pending_unconfirmed
                and not state.exit_pending_unconfirmed):
            raise ValueError("C38J_UNAUTHORIZED_STATE_RESET")
        row = _row(self._index + 1, self._head,
                   self._manifest["manifest_sha256"], state)
        body = (json.dumps(row) + "\n").encode()
        if len(body) > 12_000:
            raise ValueError("C38J_OVERSIZED_ENTRY")
        if os.write(self._fd, body) != len(body):
            raise OSError("C38J_PARTIAL_WRITE")
        os.fsync(self._fd)
        self._head = str(row["chain_sha256"])
        self._index += 1
        self._state = state
        return row

    def close(self) -> dict[str, Any]:
        if self._closed:
            raise ValueError("C38J_WRITER_CLOSED")
        os.fsync(self._fd)
        os.close(self._fd)
        self._closed = True
        (self._directory / ".writer.lock").unlink()
        _fsync_dir(self._directory)
        return verify(self._directory, self._grid)
