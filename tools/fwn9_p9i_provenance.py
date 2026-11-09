"""M11 P9I: version-scoped source lineage. Read-only; never rewrites archival hashes."""
from __future__ import annotations
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable, Mapping

ARCHIVED_PROTOCOL = "research/reused_evidence/protocol.json"
M9_REGISTRATION = "research/modulation9/registration.json"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class Provenance:
    legacy_ref: str
    archive_files_checked: int
    archive_failures: tuple[str, ...]
    m9_files_checked: int
    m9_failures: tuple[str, ...]
    legacy_profit8: str
    m9_profit8: str
    current_profit8: str
    distinct_versions_verified: bool
    archive_verified: bool
    all_sources_covered: bool


def safe_path(name: str) -> str:
    if not isinstance(name, str) or not name or name.startswith("/") or "\\" in name:
        raise ValueError("UNSAFE_PROVENANCE_PATH")
    if any(s in ("", ".", "..") for s in name.split("/")):
        raise ValueError("UNSAFE_PROVENANCE_PATH")
    if "\x00" in name:
        raise ValueError("UNSAFE_PROVENANCE_PATH")
    return name


def verify_expected(
    expected: Mapping[str, str], reader: Callable[[str], bytes],
) -> tuple[int, tuple[str, ...]]:
    if not expected:
        raise ValueError("EMPTY_PROVENANCE_MANIFEST")
    failures: list[str] = []
    for name, sha in sorted(expected.items()):
        safe_path(name)
        if not isinstance(sha, str) or SHA64.fullmatch(sha) is None:
            raise ValueError("INVALID_PROVENANCE_SHA256")
        try:
            actual = hashlib.sha256(reader(name)).hexdigest()
        except (FileNotFoundError, RuntimeError, OSError) as error:
            failures.append(f"{name}:UNAVAILABLE:{type(error).__name__}")
            continue
        if actual != sha:
            failures.append(f"{name}:SHA256_MISMATCH:{actual}")
    return len(expected), tuple(failures)


def git_reader(root: Path, ref: str) -> Callable[[str], bytes]:
    if not isinstance(ref, str) or SHA40.fullmatch(ref) is None:
        raise ValueError("NON_IMMUTABLE_SOURCE_REF")
    def read(name: str) -> bytes:
        safe_path(name)
        out = subprocess.run(["git", "show", f"{ref}:{name}"], cwd=root,
                             check=False, capture_output=True, timeout=30)
        if out.returncode:
            raise FileNotFoundError(name)
        return out.stdout
    return read


def audit(root: Path) -> Provenance:
    root = root.resolve()
    old = json.loads((root / ARCHIVED_PROTOCOL).read_text())
    reg = json.loads((root / M9_REGISTRATION).read_text())
    legacy_ref = old["source_head"]
    old_expected = old["bound_files"]
    current_expected = reg["sources_sha256"]
    older = git_reader(root, legacy_ref)
    old_count, old_failures = verify_expected(old_expected, older)
    def current(name: str) -> bytes:
        safe_path(name)
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            raise ValueError("UNSAFE_PROVENANCE_SYMLINK")
        if not path.is_file():
            raise FileNotFoundError(name)
        return path.read_bytes()
    m9_count, m9_failures = verify_expected(current_expected, current)
    p = "runtime30/profit8_replay.js"
    old_sha = old_expected[p]
    new_sha = current_expected[p]
    old_bytes = hashlib.sha256(older(p)).hexdigest()
    head_bytes = hashlib.sha256(current(p)).hexdigest()
    distinct = old_sha != new_sha and old_bytes == old_sha and head_bytes == new_sha
    return Provenance(legacy_ref, old_count, old_failures, m9_count, m9_failures,
                      old_sha, new_sha, head_bytes, distinct,
                      len(old_failures) == 0, len(m9_failures) == 0)


def promotion_gate(provenance: Provenance, state: dict[str, object]) -> dict[str, object]:
    """Require scoped source verification AND complete operational/economic coverage."""
    phase9h = state.get("m11_phase9h")
    assert isinstance(phase9h, dict), "P9I_PHASE9H_CLOSURE_MISSING"
    source_ok = provenance.distinct_versions_verified and provenance.archive_verified and provenance.all_sources_covered
    h_ok = phase9h.get("successful_ci") == 42444975973 and phase9h.get("source_native_ledger_identity_one_fixture") is True
    universal = phase9h.get("all_native_decisions_covered") is True
    execution = phase9h.get("native_infeasibility_certified") is True and phase9h.get("p9b_no_fill_valclock_closed") is True
    eligible = state.get("eligible_candidates")
    economic = state.get("goal_accepted") is True and type(eligible) is int and eligible > 0
    # No metadata toggles can certify omitted fills, multicell coverage or a population theorem.
    # This audit is only a provenance/fixture prerequisite, NEVER the final N9 authority.
    return {"status": "BLOCKED", "source_scopes_verified": source_ok,
            "phase9h_fixture_pass": h_ok, "all_native_decisions_covered": universal,
            "native_execution_complete": execution, "economic_admission_pass": economic,
            "archive_failures": len(provenance.archive_failures),
            "m9_failures": len(provenance.m9_failures),
            "reason": "GLOBAL_ECONOMIC_EXECUTION_ATTESTATIONS_NOT_IMPLEMENTED"}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    p = audit(root)
    state = json.loads((root / "research/continuous_n9/state.json").read_text())
    gate = promotion_gate(p, state)
    import dataclasses
    print(json.dumps({"schema": "FWN9_P9I_VERSIONED_PROVENANCE_1",
                      "provenance": dataclasses.asdict(p), "promotion": gate},
                     indent=2, sort_keys=True))
    if not p.distinct_versions_verified or p.m9_failures:
        raise SystemExit("P9I_FROZEN_M9_OR_LEGACY_ANCHOR_CORRUPTED")
    if gate["status"] != "BLOCKED":
        raise SystemExit("P9I_UNEXPECTED_PREMATURE_PROMOTION")


if __name__ == "__main__":
    main()
