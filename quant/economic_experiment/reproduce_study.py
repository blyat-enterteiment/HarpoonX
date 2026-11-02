"""Reproduce the frozen experiment without extending its original research budget."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from harpoon_quant.recursive import Journal  # noqa: E402
from harpoon_quant.study_integrity import load_verified_study  # noqa: E402


def main():
    # Verify the original before deriving any replica registration from its files.
    original = load_verified_study(ROOT)
    journal_before = hashlib.sha256(
        (ROOT / "study/optimizer.sqlite3").read_bytes()
    ).hexdigest()
    with tempfile.TemporaryDirectory(prefix="harpoon-frozen-replay-") as td:
        root = Path(td)
        (root / "study").mkdir()
        (root / "evidence").mkdir()
        (root / "work/HarpoonX_Motor_Quant").mkdir(parents=True)
        shutil.copytree(
            ROOT / "work/HarpoonX_Motor_Quant/harpoon_quant",
            root / "work/HarpoonX_Motor_Quant/harpoon_quant",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        for source, target in [
            ("study/protocol.json", "study/protocol.json"),
            ("study/initial_optimizer.sqlite3", "study/optimizer.sqlite3"),
            ("evidence/alpaca_calendar.json", "evidence/alpaca_calendar.json"),
            ("analysis_protocol.json", "analysis_protocol.json"),
        ]:
            shutil.copy2(ROOT / source, root / target)
        journal = Journal(root / "study/optimizer.sqlite3")
        try:
            with journal.transaction():
                now = datetime.now(UTC).isoformat()
                journal.put(
                    "economic:protocol",
                    dict(
                        hash=original.source_hashes["study/protocol.json"],
                        protocol=original.protocol,
                        engineering_replay_of_fixed_protocol=True,
                    ),
                    now,
                )
                journal.put(
                    "economic:analysis_protocol",
                    dict(
                        hash=original.source_hashes["analysis_protocol.json"],
                        after_holdout_generation=False,
                        registered_before_numeric_inspection=True,
                        engineering_replay_of_fixed_protocol=True,
                    ),
                    now,
                )
        finally:
            journal.close()
        env = dict(os.environ, PYTHONPATH=str(root / "work/HarpoonX_Motor_Quant"))
        for stage in ["develop", "holdout"]:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "harpoon_quant.economic_lab",
                    stage,
                    "--directory",
                    str(root / "study"),
                ],
                env=env,
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
        # Analyze through the current validator; leave the frozen simulator intact.
        subprocess.run(
            [sys.executable, str(ROOT / "analyze.py"), "--directory", str(root)],
            check=True,
            cwd=root,
            capture_output=True,
            text=True,
        )
        actual = json.loads((root / "study/decision.json").read_text())
        expected = json.loads((ROOT / "study/decision.json").read_text())
        # Integrity metadata may differ because the replica finalist has a new
        # registration timestamp. Every historical field must remain identical.
        metadata = {"integrity", "scenario_roles"}
        historical = {
            key: value for key, value in expected.items() if key not in metadata
        }
        assert {key: actual[key] for key in historical} == historical, (
            "Deterministic historical decision mismatch"
        )
        assert actual["integrity"]["research_budget"] == original.budget, (
            "Replica budget mismatch"
        )
        added_fields = sorted(set(actual) - set(historical))
    journal_after = hashlib.sha256(
        (ROOT / "study/optimizer.sqlite3").read_bytes()
    ).hexdigest()
    assert journal_before == journal_after, "Original journal changed"
    print(
        json.dumps(
            dict(
                deterministic_replay="PASS",
                original_research_journal="UNCHANGED",
                decision=expected["status"],
                compared_historical_fields=sorted(historical),
                separately_verified_metadata=added_fields,
            )
        )
    )


if __name__ == "__main__":
    main()
