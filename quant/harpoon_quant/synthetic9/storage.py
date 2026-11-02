"""Deterministic private artifacts and bounded decompression for reviewer packets."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from ..frontier.contracts import require

MAX_DECOMPRESSED = 64 * 1024 * 1024


def write_gzip(path: Path, value: Any) -> None:
    data = json.dumps(
        value, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode()
    require(len(data) <= MAX_DECOMPRESSED, "ARTIFACT_SIZE")
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as raw:
        with gzip.GzipFile(
            fileobj=raw, filename="", mode="wb", compresslevel=9, mtime=0
        ) as handle:
            handle.write(data)


def load_gzip(path: Path) -> Any:
    with gzip.open(path, "rb") as handle:
        data = handle.read(MAX_DECOMPRESSED + 1)
    require(len(data) <= MAX_DECOMPRESSED, "DECOMPRESSED_SIZE")

    def invalid(value: str) -> None:
        raise ValueError("NONFINITE_JSON:" + value)

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            require(key not in result, "DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    return json.loads(data, parse_constant=invalid, object_pairs_hook=unique)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes(root: Path) -> dict[str, str]:
    files = [
        *sorted((root / "quant/harpoon_quant/synthetic9").glob("*.py")),
        *sorted((root / "quant/harpoon_quant/frontier").glob("*.py")),
        *sorted((root / "quant/tests").glob("test_synthetic9*.py")),
        root / "quant/harpoon_quant/frontier_core.py",
        root / "quant/harpoon_quant/core.py",
        root / "quant/harpoon_quant/macd30.py",
        root / "tools/run_synthetic9.py",
        root / "tools/verify_synthetic9.py",
        root / "research/synthetic9/protocol.json",
        root / "quant/requirements-tested.txt",
        root / ".github/workflows/synthetic9.yml",
    ]
    return {str(p.relative_to(root)): sha256(p) for p in files}


def verify_manifest(directory: Path, root: Path, manifest: dict[str, Any]) -> None:
    for key, base in (("artifacts_sha256", directory), ("sources_sha256", root)):
        require(
            isinstance(manifest[key], dict) and bool(manifest[key]), "EMPTY_MANIFEST"
        )
        for name, expected in manifest[key].items():
            path = (base / name).resolve()
            require(
                path.is_relative_to(base.resolve()) and path.is_file(), "PACKET_PATH"
            )
            require(sha256(path) == expected, "PACKET_HASH:" + name)
