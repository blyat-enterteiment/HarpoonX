"""One-command, offline reproduction of the measurement repair and its verdict."""
from __future__ import annotations

import argparse
import subprocess
import time
from pathlib import Path

from causal_campaign_state import export
from verify_causal_integrity import ROOT, run, sha, write


def reproduce(output: Path) -> None:
    started = time.perf_counter()
    output.mkdir(parents=True, exist_ok=False)
    modes = {}
    for mode in ("control", "corrected"):
        begin = time.perf_counter()
        subprocess.run(["node", "tools/causal_integrity_replay.cjs", mode, str(output / mode)],
                       cwd=ROOT, check=True, timeout=180)
        modes[mode] = time.perf_counter() - begin
    evidence = output / "evidence"
    run(output / "control", output / "corrected", evidence)
    export(ROOT / "evidence/residual_30_18_0/data/research_dataset.json",
           ROOT / "research/technical_swing/protocol.json", output / "corrected",
           evidence / "causal_states.json.gz")
    hashes = {str(p.relative_to(evidence)): sha(p) for p in sorted(evidence.rglob("*"))
              if p.is_file() and p.name != "sha256.json"}
    write(evidence / "sha256.json", hashes)
    write(output / "benchmark.json", {"elapsed_seconds": time.perf_counter() - started,
          "replay_seconds": modes, "scope": "one offline control/corrected comparison plus audits, bootstrap and state export; not live latency"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    reproduce(parser.parse_args().output_dir.resolve())
