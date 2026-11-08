"""FWN9/P9I-R3. Exact historical split-lineage verifier; NOT an atomic snapshot.

Verifies 105 archive files at the archived source_head and three documented
later files at an immutable commit. Retains original archive protocol unchanged.
This is a provenance classification, never an execution or profitability gate.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from dataclasses import dataclass
from fwn9_p9i_provenance import audit, git_reader, verify_expected

EXCEPTION_REF = "4325422cc104a8d75384ec852b8ae5cbde07f24e"
EXPECTED_EXCEPTION_PATHS = frozenset({
    "quant/harpoon_quant/evidence_scope.py",
    "quant/tests/test_evidence_scope.py",
    "tools/run_reused_evidence.py",
})


@dataclass(frozen=True)
class CompositeResult:
    legacy_source_head: str
    exception_ref: str
    legacy_paths: int
    exception_paths: int
    composite_mismatches: tuple[str, ...]
    true_atomic_snapshot_verified: bool
    composite_bytes_verified: bool
    original_manifest_modified: bool
    n9s_certified: bool


def verify_composite(root: Path) -> CompositeResult:
    root = root.resolve()
    proto = json.loads((root / "research/reused_evidence/protocol.json").read_text())
    previous = audit(root)
    expected = proto["bound_files"]
    old = git_reader(root, previous.legacy_ref)
    newer = git_reader(root, EXCEPTION_REF)
    failures = frozenset(x.split(":", 1)[0] for x in previous.archive_failures)
    if failures != EXPECTED_EXCEPTION_PATHS:
        raise RuntimeError("P9I_R3_UNDOCUMENTED_HISTORIC_MISMATCH")
    if len(expected) != 108:
        raise RuntimeError("P9I_R3_ARCHIVE_PATH_COUNT_CHANGED")
    if not previous.distinct_versions_verified or previous.m9_failures:
        raise RuntimeError("P9I_R3_ACTIVE_M9_OR_ARCHIVE_ANCHOR_CHANGED")

    def scoped_read(path: str) -> bytes:
        return (newer if path in EXPECTED_EXCEPTION_PATHS else old)(path)

    count, discrepancies = verify_expected(expected, scoped_read)
    if discrepancies:
        raise RuntimeError("P9I_R3_COMPOSITE_HASH_MISMATCH: " + discrepancies[0])
    # Cryptographic provenance is file-specific. These bytes are not claimed
    # to be a coherent, self-consistent 108-file executable checkout.
    return CompositeResult(
        legacy_source_head=previous.legacy_ref, exception_ref=EXCEPTION_REF,
        legacy_paths=count-len(EXPECTED_EXCEPTION_PATHS),
        exception_paths=len(EXPECTED_EXCEPTION_PATHS),
        composite_mismatches=discrepancies,
        true_atomic_snapshot_verified=False, composite_bytes_verified=True,
        original_manifest_modified=False, n9s_certified=False,
    )


def diagnostic(root: Path) -> dict[str, object]:
    result = verify_composite(root)
    archive = root / "research/reused_evidence/protocol.json"
    return {
        "schema":"FWN9_P9I_R3_COMPOSITE_LINEAGE_1",
        "legacy_ref":result.legacy_source_head,
        "exception_ref":result.exception_ref,
        "legacy_paths":result.legacy_paths,
        "exception_paths":result.exception_paths,
        "exception_files":sorted(EXPECTED_EXCEPTION_PATHS),
        "composite_bytes_verified":result.composite_bytes_verified,
        "atomic_snapshot_verified":result.true_atomic_snapshot_verified,
        "n9s_certified":result.n9s_certified,
        "archival_protocol_sha256":hashlib.sha256(archive.read_bytes()).hexdigest(),
        "source_modification_count":0,
        "classification":"SPLIT_LINEAGE_EXACT_BYTES_NOT_ATOMIC_SNAPSHOT",
    }


if __name__ == "__main__":
    print(json.dumps(diagnostic(Path(__file__).resolve().parents[1]),indent=2,sort_keys=True))
