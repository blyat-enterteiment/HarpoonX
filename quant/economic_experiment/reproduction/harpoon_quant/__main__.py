from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .bridge import from_runtime
from .calibration import fit
from .context import context_from_runtime
from .core import Config, allocate
from .performance import report
from .recursive import runtime_tick


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=["fit", "allocate", "worker", "context", "metrics", "optimize"],
    )
    parser.add_argument("--input", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--available-at")
    args = parser.parse_args()
    try:
        cfg = Config(**json.loads(args.config.read_text())) if args.config else Config()
        data = (
            json.loads(args.input.read_text()) if args.input else json.load(sys.stdin)
        )
        if args.action == "metrics":
            result = {
                "status": "PERFORMANCE_REPORT",
                "performance": report(data),
                "selected": [],
                "execution_allowed": False,
            }
        elif args.action == "optimize":
            result = runtime_tick(data)
        elif args.action == "context":
            result = context_from_runtime(data)
        elif args.action == "fit":
            if not args.available_at:
                raise ValueError("AVAILABLE_AT_REQUIRED")
            result = fit(data, args.available_at, cfg)
        else:
            model = args.model or Path("quant_calibration.json")
            if not model.is_file():
                result = {
                    "status": "BLOCKED",
                    "execution_allowed": False,
                    "selected": [],
                    "reason": "CALIBRATION_FILE_REQUIRED",
                    "liveApproved": False,
                }
            else:
                result = (
                    from_runtime(data, json.loads(model.read_text()))
                    if data.get("runtime_snapshot") is True
                    else allocate(data, json.loads(model.read_text()), cfg)
                )
        text = json.dumps(result, allow_nan=False, sort_keys=True)
        if args.output:
            args.output.write_text(text + "\n")
        else:
            print(text)
    except (ValueError, KeyError, TypeError, ArithmeticError, OSError) as exc:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "execution_allowed": False,
                    "selected": [],
                    "reason": str(exc),
                    "liveApproved": False,
                }
            )
        )
        sys.exit(2)


if __name__ == "__main__":
    main()
