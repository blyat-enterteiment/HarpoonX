"""Reproduce the fixed-entry engineering comparison; never calls a broker."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import platform
import tempfile
import time
from pathlib import Path
from typing import Any

from harpoon_quant.roadmap9.execution import HOUR_MS, ExecutionBook
from harpoon_quant.roadmap9.execution_replay import account_receipt, replay_account


def benchmark_reducer() -> dict[str, Any]:
    """Measure local event reduction separately from broker/network latency."""
    book = ExecutionBook({"AAPL": 250})
    samples = []
    for i in range(250):
        at = i * 1000
        cid = f"benchmark-{i}"
        events = [
            {
                "event_id": cid + "-intent",
                "kind": "INTENT",
                "at": at,
                "client_order_id": cid,
                "campaign_id": cid,
                "symbol": "AAPL",
                "side": "sell",
                "qty": "1",
                "opened_at": at,
                "deadline_at": at + 72 * HOUR_MS,
            },
            {
                "event_id": cid + "-sent",
                "kind": "SUBMITTED",
                "at": at + 1,
                "client_order_id": cid,
            },
            {
                "event_id": cid + "-ack",
                "kind": "ACK",
                "at": at + 2,
                "client_order_id": cid,
                "broker_order_id": cid + "-broker",
            },
            {
                "event_id": cid + "-fill",
                "kind": "FILL",
                "at": at + 3,
                "executed_at": at + 3,
                "client_order_id": cid,
                "execution_id": cid + "-execution",
                "qty": "1",
                "price": "100",
            },
        ]
        for e in events:
            started = time.perf_counter_ns()
            book.receive(e)
            elapsed = (time.perf_counter_ns() - started) / 1_000_000
            if i >= 20:
                samples.append(elapsed)
    ordered = sorted(samples)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "book.json"
        started = time.perf_counter_ns()
        book.save(path)
        persist_ms = (time.perf_counter_ns() - started) / 1_000_000
        started = time.perf_counter_ns()
        restored = ExecutionBook.load(path)
        restore_ms = (time.perf_counter_ns() - started) / 1_000_000
        equivalent = restored.snapshot() == book.snapshot()
    if not equivalent or book.inventory["AAPL"] != 0:
        raise ValueError("BENCHMARK_STATE_RECONSTRUCTION")
    return {
        "scope": "LOCAL_REDUCER_ONLY_NO_NETWORK_OR_BROKER_TIMING",
        "events": 1000,
        "warmup_events": 80,
        "timed_events": len(samples),
        "retained_orders": 250,
        "p50_ms": ordered[int((len(ordered) - 1) * 0.50)],
        "p95_ms": ordered[int((len(ordered) - 1) * 0.95)],
        "p99_ms": ordered[int((len(ordered) - 1) * 0.99)],
        "max_ms": ordered[-1],
        "persist_ms": persist_ms,
        "restore_ms": restore_ms,
        "restored_state_equal": equivalent,
        "latency_sla_certified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=Path("evidence/synthetic9/run_01/accounts")
    )
    parser.add_argument(
        "--protocol",
        type=Path,
        default=Path("research/roadmap9/execution_protocol.json"),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--raw-output", type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    protocol = json.loads(args.protocol.read_text())
    frozen_manifest_path = args.source.parent / "manifest.json"
    frozen_manifest = json.loads(frozen_manifest_path.read_text())
    if args.output.exists():
        raise SystemExit("Refusing to overwrite an existing engineering receipt")
    if args.raw_output:
        args.raw_output.mkdir(parents=True, exist_ok=False)
    receipts = []
    for path in sorted(args.source.glob("*.json.gz")):
        relative = str(path.relative_to(args.source.parent))
        if hashlib.sha256(path.read_bytes()).hexdigest() != frozen_manifest[
            "artifacts_sha256"
        ].get(relative):
            raise ValueError("FROZEN_ACCOUNT_HASH_MISMATCH:" + relative)
        with gzip.open(path, "rt") as stream:
            source = json.load(stream)
        replay = replay_account(source, protocol)
        receipts.append(account_receipt(source, replay, path))
        if args.raw_output:
            target = args.raw_output / path.name
            target.write_bytes(
                gzip.compress(
                    json.dumps(
                        replay, sort_keys=True, separators=(",", ":"), allow_nan=False
                    ).encode(),
                    mtime=0,
                )
            )
    if len(receipts) != 108:
        raise ValueError("EXPECTED_108_FROZEN_ACCOUNTS")
    if (
        len({(r["world"], r["seed"], r["scenario"], r["strategy"]) for r in receipts})
        != 108
    ):
        raise ValueError("DUPLICATE_FROZEN_ACCOUNT_RECIPE")
    totals = {}
    for strategy in sorted({r["strategy"] for r in receipts}):
        rows = [r for r in receipts if r["strategy"] == strategy]
        totals[strategy] = {
            "accounts": len(rows),
            "planned_deadline_breaches_before": sum(
                r["planned_deadline_breaches_before"] for r in rows
            ),
            "planned_deadline_breaches_after": sum(
                r["planned_deadline_breaches_after"] for r in rows
            ),
            "retry_orders": sum(r["retry_orders"] for r in rows),
        }
    checks = {
        "all_entries_preserved": all(r["entry_events_preserved"] for r in receipts),
        "separate_decimal_accounting_pass": all(
            r["decimal_audit"]["verified"] for r in receipts
        ),
        "no_planned_deadline_breaches_in_replay_conditions": all(
            r["planned_deadline_breaches_after"] == 0 for r in receipts
        ),
        "no_open_or_unresolved_inventory": all(
            r["open_positions"] == 0 and r["unresolved_orders"] == 0 for r in receipts
        ),
        "max_holding_le_72h": all(r["max_hold_after_hours"] <= 72 for r in receipts),
    }
    code_paths = [
        Path("quant/harpoon_quant/roadmap9/execution.py"),
        Path("quant/harpoon_quant/roadmap9/execution_replay.py"),
        Path("tools/run_roadmap9_execution.py"),
    ]
    report: dict[str, Any] = {
        "schema": "HARPOON_ROADMAP9_EVENT_REPLAY_RECEIPT_1",
        "origin": "SYNTHETIC_ENGINEERING_ONLY",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "protocol_sha256": hashlib.sha256(args.protocol.read_bytes()).hexdigest(),
        "baseline_manifest_sha256": hashlib.sha256(
            frozen_manifest_path.read_bytes()
        ).hexdigest(),
        "source_hashes": {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in code_paths
        },
        "checks": checks,
        "totals": totals,
        "accounts": receipts,
        "event_reducer_benchmark": benchmark_reducer(),
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "elapsed_seconds": time.perf_counter() - started,
        },
        "scope": "Fixed entries and first exit streams; historical decisions not reoptimized; synthetic fees unchanged; engineering attribution only",
        "account_specific_observed_fees_tested": False,
        "external_review_completed": False,
        "real_fills_present": False,
        "economic_improvement_accredited": False,
        "orders_allowed": False,
        "level9_accredited": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "checks": checks,
                "totals": totals,
                "elapsed_seconds": report["runtime"]["elapsed_seconds"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
