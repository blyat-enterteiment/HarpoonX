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
        choices=["fit", "allocate", "worker", "context", "metrics", "optimize", "observe", "verify-gate", "technical-swing"],
    )
    parser.add_argument("--input", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--available-at")
    parser.add_argument(
        "--estimator", choices=["ridge", "svr"],
        help="Return estimator for fit; the saved artifact controls inference",
    )
    args = parser.parse_args()
    try:
        if args.estimator is not None and args.action != "fit":
            raise ValueError("ESTIMATOR_ONLY_FOR_FIT")
        cfg = Config(**json.loads(args.config.read_text())) if args.config else Config()
        data = (
            json.loads(args.input.read_text()) if args.input else json.load(sys.stdin)
        )
        if args.action == "technical-swing":
            from .core import timestamp
            from .technical_swing import TechnicalSwing

            if not args.available_at:
                raise ValueError("TECHNICAL_DECISION_TIMESTAMP_REQUIRED")
            panel = TechnicalSwing(data["dataset"], data["symbols"], data["benchmark"])
            result = panel.decision(round(timestamp(args.available_at).timestamp() * 1000))
        elif args.action == "verify-gate":
            from .economic_gate import verify_gate_report

            result = verify_gate_report(
                data["report"], data["protocol"], data["evidence"],
                artifact_root=Path(data["artifact_root"]) if data.get("artifact_root") else None,
            )
            result.update(selected=[], execution_allowed=False, liveApproved=False)
        elif args.action == "observe":
            result = from_runtime(data, None, observation_only=True)
        elif args.action == "metrics":
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
            result = fit(data, args.available_at, cfg, estimator=args.estimator or "ridge")
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
