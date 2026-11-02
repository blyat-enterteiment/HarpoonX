"""Run the registered synthetic-only bank without network, broker or account access."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "quant"))
from harpoon_quant.synthetic9.experiment import build


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    summary = build(ROOT, args.output_dir, args.source_commit)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
