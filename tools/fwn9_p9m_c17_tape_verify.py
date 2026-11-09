"""Independent C17 tape auditor against a fresh uninstrumented frozen M9 market.

No selection, nominations, risk policies or native accounts are invoked.
The recorded eight samples must exactly produce original OHLCV and entire
untraced dataset digest for already-opened M9 development seed 730101.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

from harpoon_quant import modulation9

SOURCE_SHA = "9d4afa402d2b70791f175e79219495f9bbbe25eb3cd0b7e9212cef6bccbd68ab"
PROTOCOL_SHA = "de694919b0908fc0ecf474c9612ff7d54fe04db635a385e12ffa0f81abc7780d"
SCHEMA = "HARPOON_M11_C17_REGISTERED_DEVELOPMENT_WEAK_8STEP_TAPE_1"


def verify_document(report: dict[str, Any], root: Path) -> dict[str, Any]:
    source = root / "quant/harpoon_quant/modulation9.py"
    protocol_file = root / "research/modulation9/protocol.json"
    if (hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_SHA or
            hashlib.sha256(protocol_file.read_bytes()).hexdigest() != PROTOCOL_SHA):
        raise AssertionError("C17_INDEPENDENT_FROZEN_SOURCE_HASH")
    if (
        report["schema"] != SCHEMA or report["stage"] != "development" or
        report["seed"] != 730101 or report["world"] != "WEAK" or
        report["signal_generation_calls"] != 0 or
        report["final_holdout_opened"] is not False or
        report["historic_archive_byte_match_verified"] is not False
    ):
        raise AssertionError("C17_INDEPENDENT_SEALED_SCOPE")
    original: dict[str, Any] = json.loads(protocol_file.read_text(encoding="utf-8"))
    untraced = modulation9.market(original, 730101, "WEAK", "development")
    if modulation9.digest(untraced) != report["dataset_sha256"]:
        raise AssertionError("C17_INDEPENDENT_ORIGINAL_MARKET_DIGEST")
    grid = untraced["sessions"]
    evaluation_start = original["generator"]["warmup_sessions"]
    evaluation_stop = evaluation_start + original["generator"]["evaluation_sessions"]
    row_index = {}
    for symbol, serie in ((s["symbol"], s) for s in untraced["series"]):
        if symbol not in original["traded_universe"]:
            continue
        for i in range(evaluation_start, evaluation_stop):
            for k in range(78):
                b = serie["bars"][i * 78 + k]
                row_index[symbol, b["t"]] = b
    checked = 0
    seen: set[tuple[str, int]] = set()
    rows: list[dict[str, Any]] = report["tape"]
    if len(rows) != 126 * 78 * 2 or report["bar_asset_count"] != len(rows):
        raise AssertionError("C17_INDEPENDENT_TAPE_CARDINALITY")
    for row in rows:
        symbol = str(row["symbol"])
        at = int(row["t"])
        key = symbol, at
        if key not in row_index or key in seen:
            raise AssertionError("C17_INDEPENDENT_NEW_OR_DUPLICATE_BAR")
        seen.add(key)
        b = row_index[key]
        prices = row["prices"]
        if (not isinstance(prices, list) or len(prices) != 8 or
                any(not isinstance(p, (float, int)) or p <= 0 for p in prices)):
            raise AssertionError("C17_INDEPENDENT_8STEP_POSITIVE_DOMAIN")
        if (b["o"] != row["open"] or b["h"] != row["high"] or
                b["l"] != row["low"] or b["c"] != row["close"] or
                b["end"] != row["end"] or prices[-1] != b["c"] or
                max([b["o"], *prices]) != b["h"] or
                min([b["o"], *prices]) != b["l"]):
            raise AssertionError("C17_INDEPENDENT_OHLCV_8STEP_MISMATCH")
        checked += 1
    if len(seen) != len(row_index):
        raise AssertionError("C17_INDEPENDENT_MISSING_BAR")
    if modulation9.digest(rows) != report["eightstep_sha256"]:
        raise AssertionError("C17_INDEPENDENT_TAPE_SHA256_MISMATCH")
    if (report["per_asset_substep_count"] != 126 * 78 * 8 or
            report["total_asset_substep_price_count"] != checked * 8 or
            grid[evaluation_start]["open"] != report["evaluation_start_at"] or
            grid[evaluation_stop-1]["close"] != report["evaluation_end_at"]):
        raise AssertionError("C17_INDEPENDENT_EVALUATION_WINDOW")
    return {
        "schema": "HARPOON_M11_C17_INDEPENDENT_8STEP_VERIFY_1",
        "checked_bar_asset_rows": checked,
        "checked_price_samples": checked * 8,
        "untraced_native_market_digest_identical": True,
        "generator_source_sha256": SOURCE_SHA,
        "original_archive_byte_identity": "UNVERIFIED_ARCHIVE_BYTES_UNAVAILABLE",
        "seeds_added": 0,
        "accounts_opened": 0,
        "final_opened": False,
    }


def verify_file(file: Path, root: Path) -> dict[str, Any]:
    with gzip.open(file, "rb") as stream:
        document = json.load(stream)
    if not isinstance(document, dict):
        raise ValueError("C17_EXPECT_OBJECT")
    return verify_document(document, root)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print("FWN9_C17_INDEPENDENT_TAPE=" +
          json.dumps(verify_file(args.file, args.root), sort_keys=True))


if __name__ == "__main__":
    main()
