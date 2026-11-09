"""P9I R4: run all quant regressions without testing historical sources on the wrong HEAD.

The archived test module runs separately in an explicitly reconstructed composite
of immutable old byte revisions; it does NOT claim one atomic historical snapshot.
No test is silently skipped: the archived split is asserted to contain 12 tests.
"""
from __future__ import annotations
import os
import subprocess
import sys
import tempfile
import unittest
import json
from pathlib import Path
from collections.abc import Iterator
from fwn9_p9i_composite_lineage import EXCEPTION_REF, EXPECTED_EXCEPTION_PATHS
from fwn9_p9i_provenance import audit, verify_expected, safe_path


def items(suite: unittest.TestSuite) -> Iterator[unittest.TestCase]:
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from items(test)
        elif isinstance(test, unittest.TestCase):
            yield test
        else:
            raise RuntimeError("P9I_R4_UNKNOWN_UNITTEST_SHAPE")


def current_suite(root: Path) -> int:
    sys.path[:0] = [str(root / "quant"), str(root / "tools")]
    all_tests = list(items(unittest.defaultTestLoader.discover(
        start_dir=str(root / "quant/tests"),
        top_level_dir=str(root / "quant/tests"))))
    archive = [t for t in all_tests if t.id().startswith("test_evidence_scope.")]
    current = [t for t in all_tests if not t.id().startswith("test_evidence_scope.")]
    if len(archive) != 12 or len(current) < 20 or len(current)+len(archive) != len(all_tests):
        raise RuntimeError("P9I_R4_TEST_PARTITION_NOT_CONSERVED")
    print("P9I_R4_CURRENT_CASES",len(current),"ARCHIVED_CASES",len(archive),flush=True)
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(unittest.TestSuite(current))
    if not result.wasSuccessful():
        raise RuntimeError("P9I_R4_CURRENT_QUANT_REGRESSIONS_FAILED")
    return len(current)


def archive_suite(root: Path) -> int:
    provenance = audit(root)
    if not provenance.distinct_versions_verified or provenance.m9_failures:
        raise RuntimeError("P9I_R4_PROVENANCE_PRECONDITION_FAILURE")
    if frozenset(x.split(":",1)[0] for x in provenance.archive_failures) != EXPECTED_EXCEPTION_PATHS:
        raise RuntimeError("P9I_R4_UNREGISTERED_ARCHIVE_DEVIATION")
    old = json.loads((root / "research/reused_evidence/protocol.json").read_text())
    with tempfile.TemporaryDirectory(prefix="p9i_archived_") as temp:
        dest = Path(temp) / "reconstructed-composite"
        proc = subprocess.run(["git", "worktree", "add", "--detach", str(dest), provenance.legacy_ref],
                              cwd=root,capture_output=True,text=True,timeout=120,check=False)
        if proc.returncode:
            raise RuntimeError("P9I_R4_WORKTREE_FAILED: " + proc.stderr[-1000:])
        try:
            for path in sorted(EXPECTED_EXCEPTION_PATHS):
                safe_path(path)
                content = subprocess.run(["git","show",f"{EXCEPTION_REF}:{path}"],
                                         cwd=root,capture_output=True,timeout=30,check=True).stdout
                target=dest/path
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(content)
            # The archived manifest is a classifier introduced after source_head.
            proto=dest/"research/reused_evidence/protocol.json"
            proto.parent.mkdir(parents=True,exist_ok=True)
            proto.write_bytes((root/"research/reused_evidence/protocol.json").read_bytes())
            n,miss=verify_expected(old["bound_files"],lambda name:(dest/name).read_bytes())
            if n != 108 or miss:
                raise RuntimeError("P9I_R4_RECONSTRUCTED_SOURCE_BYTES_MISMATCH")
            env={**os.environ,"PYTHONPATH":os.pathsep.join([str(dest/"quant"),str(dest/"tools")]),
                 "OPENBLAS_NUM_THREADS":"1"}
            p = subprocess.run([sys.executable,"-B","-m","unittest","discover",
                                "-s","quant/tests","-p","test_evidence_scope.py"],
                               cwd=dest,env=env,capture_output=True,text=True,
                               timeout=230,check=False)
            print(p.stdout,flush=True)
            print(p.stderr,flush=True)
            if p.returncode:
                raise RuntimeError("P9I_R4_RECONSTRUCTED_ARCHIVED_SUITE_FAILED")
            print("P9I_R4_ARCHIVED_HASHES",n,"COMPOSITE_REF",EXCEPTION_REF,flush=True)
            return 12
        finally:
            subprocess.run(["git","worktree","remove","--force",str(dest)],cwd=root,
                           capture_output=True,check=False,timeout=60)


if __name__ == "__main__":
    root=Path(__file__).resolve().parents[1]
    if len(sys.argv)!=2 or sys.argv[1] not in ("--current","--archive"):
        raise SystemExit("EXPECTED --current or --archive")
    n=current_suite(root) if sys.argv[1]=="--current" else archive_suite(root)
    print("P9I_R4_SUITE_PASS",sys.argv[1],n,flush=True)
