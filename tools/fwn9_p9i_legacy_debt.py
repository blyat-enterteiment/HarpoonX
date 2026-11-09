"""FWN9 P9I-R2 read-only classification of archived manifest debts.
Never rewrites manifests, source trees, or substitutes a different history as if it
were a verified contemporaneous source snapshot.
"""
from __future__ import annotations
import hashlib
import json
import subprocess
from pathlib import Path
from fwn9_p9i_provenance import audit, git_reader, safe_path

MAX_REVISIONS_PER_FILE = 160


def inspect(root: Path) -> dict[str, object]:
    root = root.resolve()
    p = audit(root)
    old = json.loads((root / "research/reused_evidence/protocol.json").read_text())
    expected = old["bound_files"]
    debts: list[dict[str, object]] = []
    reader = git_reader(root, p.legacy_ref)
    for failure in p.archive_failures:
        path = failure.split(":", 1)[0]
        safe_path(path)
        wanted = expected[path]
        try:
            received = hashlib.sha256(reader(path)).hexdigest()
        except FileNotFoundError:
            received = None
        result = subprocess.run(
            ["git", "log", "--all", "--format=%H", "--", path],
            cwd=root, check=False, capture_output=True, text=True, timeout=35,
        )
        if result.returncode:
            raise RuntimeError("P9I_R2_GIT_HISTORY_UNREADABLE")
        revisions = result.stdout.splitlines()[:MAX_REVISIONS_PER_FILE]
        matches: list[str] = []
        for rev in revisions:
            try:
                actual = hashlib.sha256(git_reader(root, rev)(path)).hexdigest()
            except FileNotFoundError:
                continue
            if actual == wanted:
                matches.append(rev)
                break
        debts.append({
            "path": path, "archived_expected_sha256": wanted,
            "source_head_actual_sha256": received,
            "matching_immutable_ref": matches[0] if matches else None,
            "revisions_searched": len(revisions),
            "status": "SPLIT_HISTORICAL_LINEAGE" if matches else "UNRESOLVED_HISTORICAL_BYTES",
        })
    return {
        "schema": "FWN9_P9I_R2_ARCHIVE_DEBT_1",
        "original_source_head": p.legacy_ref,
        "archive_bound_paths": p.archive_files_checked,
        "archive_mismatch_count": len(p.archive_failures),
        "m9_frozen_source_mismatch_count": len(p.m9_failures),
        "legacy_profit8_anchor_verified": p.distinct_versions_verified,
        "debts": debts, "archive_snapshot_verified": p.archive_verified,
        "global_certification": "BLOCKED",
        "historical_manifest_modified": False, "economic_accounts": 0,
        "note": "Individual old refs, even if found, DO NOT retroactively prove one concurrent 108-file source snapshot.",
    }


if __name__ == "__main__":
    print(json.dumps(inspect(Path(__file__).resolve().parents[1]), indent=2, sort_keys=True))
