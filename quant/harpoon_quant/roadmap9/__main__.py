"""Local inspection CLI. No broker credentials or network transport are used."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .forward import assess_forward
from .gates import close_plan, render_markdown
from .operations import evaluate_health


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    forward = commands.add_parser("admit-forward", help="Validate original normalized account records")
    forward.add_argument("--packet", type=Path)
    forward.add_argument("--protocol", type=Path)
    forward.add_argument("--trust-store", type=Path)
    forward.add_argument("--now-ms", type=int, required=True)
    health = commands.add_parser("health", help="Derive health from receipt and source ages")
    health.add_argument("--state", type=Path, required=True)
    health.add_argument("--now-ms", type=int, required=True)
    close = commands.add_parser("close", help="Validate 49 evidence-bound work-cycle verdicts")
    close.add_argument("--root", type=Path, default=Path.cwd())
    close.add_argument("--plan", type=Path, required=True)
    close.add_argument("--claims", type=Path, required=True)
    close.add_argument("--source-manifest", type=Path, required=True)
    close.add_argument("--source-commit", required=True)
    close.add_argument("--markdown", type=Path)
    for sub in (forward, health, close):
        sub.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    def read(path: Path | None):
        return json.loads(path.read_text()) if path else None
    if args.command == "admit-forward":
        result = assess_forward(read(args.packet), read(args.protocol), read(args.trust_store), now_ms=args.now_ms)
    elif args.command == "health":
        result = evaluate_health(read(args.state), args.now_ms)
    else:
        result = close_plan(read(args.plan), read(args.claims), args.root,
                            source_commit=args.source_commit, source_manifest=read(args.source_manifest))
        if args.markdown:
            args.markdown.parent.mkdir(parents=True, exist_ok=True)
            args.markdown.write_text(render_markdown(result))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(args.output), "status": result.get("status", result.get("result_counts")),
                      "execution_allowed": result["execution_allowed"]}))


if __name__ == "__main__":
    main()
