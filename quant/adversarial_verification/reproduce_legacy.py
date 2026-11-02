"""Reproduce the fixed legacy reference in a temporary, isolated directory."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> None:
    source = Path(__file__).resolve().parents[1] / "economic_experiment/reproduction"
    expected = json.loads((source / "results.json").read_text())
    with tempfile.TemporaryDirectory(prefix="harpoon-legacy-fixed-") as td:
        target = Path(td)
        shutil.copy2(source / "simulate.py", target / "simulate.py")
        shutil.copytree(source / "harpoon_quant", target / "harpoon_quant", ignore=shutil.ignore_patterns("__pycache__"))
        subprocess.run([sys.executable, "simulate.py"], cwd=target, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"), check=True, capture_output=True, text=True)
        actual = json.loads((target / "results.json").read_text())
        if actual["aggregate"] != expected["aggregate"]:
            raise ValueError("LEGACY_METRICS_CHANGED")
        observed_hash = hashlib.sha256((target / "data.synthetic.json").read_bytes()).hexdigest()
        if observed_hash != hashlib.sha256((source / "data.synthetic.json").read_bytes()).hexdigest():
            raise ValueError("LEGACY_DATA_CHANGED")
        print(json.dumps({"status": "PASS", "purpose": "Fixed synthetic reproduction, no new research", "aggregate": actual["aggregate"], "data_sha256": observed_hash, "original_journal_used_or_changed": False}, indent=2))


if __name__ == "__main__":
    main()
