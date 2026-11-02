"""CLI for fitting, deciding and auditing frontier shadow research. No broker API."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .core import digest
from .frontier.contracts import Settings, require
from .frontier.controller import decide
from .frontier.evaluation import evaluate
from .frontier.journal import Journal
from .frontier.paths import fit
from .frontier.programme import evidence_gate, validate_programme

MAX_BYTES = 64 * 1024 * 1024


def read_json(path: Path) -> Any:
    require(path.stat().st_size <= MAX_BYTES, "JSON_INPUT_BYTES")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            require(key not in out, "DUPLICATE_JSON_KEY")
            out[key] = value
        return out

    def invalid(value: str) -> None:
        raise ValueError("NONFINITE_JSON:" + value)

    return json.loads(
        path.read_text(), object_pairs_hook=unique, parse_constant=invalid
    )


def write_json(path: Path, value: Any) -> None:
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(value, handle, allow_nan=False, sort_keys=True, indent=2)
        handle.write("\n")


def shadow(
    state: dict[str, Any],
    model: dict[str, Any],
    cfg: Settings | None = None,
    journal_path: Path | None = None,
) -> dict[str, Any]:
    cfg = cfg or Settings()
    receipt = decide(state, model, cfg)
    sources = [
        *sorted((Path(__file__).parent / "frontier").glob("*.py")),
        Path(__file__),
        Path(__file__).parent / "core.py",
    ]
    engine_hash = digest(
        {
            str(p.relative_to(Path(__file__).parent)): hashlib.sha256(
                p.read_bytes()
            ).hexdigest()
            for p in sources
        }
    )
    receipt["engine_source_hash"] = engine_hash
    receipt["receipt_hash"] = digest(
        {k: v for k, v in receipt.items() if k != "receipt_hash"}
    )
    if journal_path is not None:
        journal = Journal(journal_path)
        try:
            journal.verify()
            binding = digest(
                {
                    "state": state,
                    "model": model["model_hash"],
                    "settings": vars(cfg),
                    "engine_source_hash": engine_hash,
                }
            )
            receipt = journal.append(
                state["account_binding"], state["version"], binding, receipt
            )
        finally:
            journal.close()
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    train = commands.add_parser("fit")
    train.add_argument("--dataset", type=Path, required=True)
    train.add_argument("--available-at", required=True)
    train.add_argument("--output", type=Path, required=True)
    infer = commands.add_parser("decide")
    infer.add_argument("--state", type=Path, required=True)
    infer.add_argument("--model", type=Path, required=True)
    infer.add_argument("--journal", type=Path)
    infer.add_argument("--output", type=Path, required=True)
    audit = commands.add_parser("audit-journal")
    audit.add_argument("--journal", type=Path, required=True)
    audit.add_argument("--output", type=Path, required=True)
    evaluation = commands.add_parser("evaluate")
    evaluation.add_argument("--dataset", type=Path, required=True)
    evaluation.add_argument("--test-start", required=True)
    evaluation.add_argument("--test-end", required=True)
    evaluation.add_argument("--max-decisions", type=int, default=20)
    evaluation.add_argument("--output", type=Path, required=True)
    programme = commands.add_parser("validate-programme")
    programme.add_argument("--programme", type=Path, required=True)
    programme.add_argument("--output", type=Path, required=True)
    gate = commands.add_parser("audit-gate")
    gate.add_argument("--programme", type=Path, required=True)
    gate.add_argument("--gate", required=True)
    gate.add_argument("--artifacts", type=Path, required=True)
    gate.add_argument("--root", type=Path, required=True)
    gate.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cfg = Settings(**read_json(args.settings)) if args.settings else Settings()
    if args.command == "fit":
        value = fit(read_json(args.dataset), args.available_at, cfg)
    elif args.command == "decide":
        value = shadow(read_json(args.state), read_json(args.model), cfg, args.journal)
    elif args.command == "evaluate":
        value = evaluate(
            read_json(args.dataset),
            cfg,
            test_start=args.test_start,
            test_end=args.test_end,
            max_decisions=args.max_decisions,
        )
    elif args.command == "validate-programme":
        value = validate_programme(read_json(args.programme))
    elif args.command == "audit-gate":
        value = evidence_gate(
            read_json(args.programme), args.gate, read_json(args.artifacts), args.root
        )
    else:
        journal = Journal(args.journal)
        try:
            value = journal.verify()
        finally:
            journal.close()
    write_json(args.output, value)


if __name__ == "__main__":
    main()
