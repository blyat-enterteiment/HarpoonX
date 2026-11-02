"""Local file adapter for observed causal panels and segregated archive diagnostics."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "quant"))
from harpoon_quant.causal_panel import build, verify
from harpoon_quant.study_integrity import _json as strict_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--verify", type=Path, help="Rebuild sources and compare an existing report; never train")
    args = parser.parse_args()
    request = strict_json(args.input.read_bytes())
    result = verify(strict_json(args.verify.read_bytes()), request, args.input.resolve().parent) if args.verify else \
        build(request, args.input.resolve().parent)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(args.output.resolve()), "schema": result["schema"],
                      "verified": result.get("verified"), "counts": result.get("counts"),
                      "training_executed": False, "execution_allowed": False}))
    if result.get("verified") is False:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
