"""Read-only integrity and release lineage checks; no trading or financial test."""
from __future__ import annotations

import difflib
import hashlib
import json
import stat
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo

WORK = Path('/workspace/scratch/4ecb05fdc50d')
APP = WORK / 'level5_work/HARPOON_XXXUltimate_30_12_0'
ZIP = WORK / 'level5_delivery/HARPOON_XXXUltimate_30_12_0_Integral.zip'
OUT = WORK / 'consolidation_evidence/integrity'
OUT.mkdir(parents=True, exist_ok=True)
ROOT_NAME = 'HARPOON_XXXUltimate_30_12_0'
PREFIX = ROOT_NAME + '/'


def sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def read(p: Path):
    return json.loads(p.read_text())


def write(name: str, payload):
    (OUT / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')


errors = []
with zipfile.ZipFile(ZIP) as z:
    members = z.infolist()
    bad_crc = z.testzip()
    if bad_crc:
        errors.append({'crc': bad_crc})
    duplicates = [name for name, count in Counter(i.filename for i in members).items() if count > 1]
    unsafe = []
    symlinks = []
    for item in members:
        p = PurePosixPath(item.filename)
        if (p.is_absolute() or '..' in p.parts or '\\' in item.filename or
                not item.filename.startswith(PREFIX) or '\x00' in item.filename or ':' in p.parts[0]):
            unsafe.append(item.filename)
        if stat.S_ISLNK(item.external_attr >> 16):
            symlinks.append(item.filename)
    if duplicates or unsafe or symlinks:
        errors.append({'duplicates': duplicates, 'unsafe': unsafe, 'symlinks': symlinks})
    blobs = {i.filename[len(PREFIX):]: z.read(i) for i in members if not i.is_dir() and i.filename.startswith(PREFIX)}

    active_manifests = []
    for name in ['MANIFEST_XXXUltimate.json', 'quant/MANIFEST_QUANT.json']:
        manifest = json.loads(blobs[name])
        base = PurePosixPath(name).parent
        checked = []
        invalid = []
        for row in manifest['files']:
            relative = str(base / row['path'])
            safe = not PurePosixPath(row['path']).is_absolute() and '..' not in PurePosixPath(row['path']).parts
            content = blobs.get(relative)
            ok = safe and content is not None and sha(content) == row['sha256'] and len(content) == row['bytes']
            checked.append(relative)
            if not ok:
                invalid.append(relative)
        active_manifests.append({'path': name, 'version': manifest['version'], 'files_verified': len(checked), 'mismatches': invalid})
        if invalid:
            errors.append({'manifest': name, 'mismatches': invalid})
    active_sha_files = []
    for name in ['MANIFEST.sha256', 'quant/MANIFEST.sha256']:
        base = PurePosixPath(name).parent
        invalid = []
        rows = blobs[name].decode().splitlines()
        for row in rows:
            digest, relative = row.split('  ', 1)
            full = str(base / relative)
            if full not in blobs or sha(blobs[full]) != digest:
                invalid.append(full)
        active_sha_files.append({'path': name, 'files_verified': len(rows), 'mismatches': invalid})
        if invalid:
            errors.append({'sha_file': name, 'mismatches': invalid})
    manifest = json.loads(blobs['MANIFEST_XXXUltimate.json'])
    listed = {row['path'] for row in manifest['files']} | {'MANIFEST_XXXUltimate.json'}
    inventory_difference = {'unlisted_zip_files': sorted(set(blobs) - listed), 'declared_missing_files': sorted(listed - set(blobs))}
    if any(inventory_difference.values()):
        errors.append(inventory_difference)
    mismatch_source = [rel for rel, content in blobs.items() if not (APP / rel).is_file() or sha((APP / rel).read_bytes()) != sha(content)]
    if mismatch_source:
        errors.append({'source_mismatch': mismatch_source})
    freeze = json.loads(blobs['evidence/level5_30_12_0/frozen_source_hashes.json'])
    freeze_mismatch = [rel for rel, digest in freeze['files'].items() if rel not in blobs or sha(blobs[rel]) != digest]
    if freeze_mismatch:
        errors.append({'frozen_source_mismatch': freeze_mismatch})
    before = json.loads(blobs['evidence/level5_30_12_0/frozen_source_hashes_before_static_fix.json'])
    modified_after_full_run = [rel for rel in freeze['files'] if freeze['files'][rel] != before['files'][rel]]
    if modified_after_full_run != ['quant/harpoon_quant/causal_panel.py']:
        errors.append({'unexpected_post_full_run_source_changes': modified_after_full_run})

    qa_path = 'evidence/level5_30_12_0/final_regression/'
    qa = json.loads(blobs[qa_path + 'all_summary.json'])
    original_qa = json.loads(blobs[qa_path + 'initial_all_summary.json'])
    post_qa = json.loads(blobs[qa_path + 'post_fix_summary.json'])
    bad_logs = []
    checked_logs = []
    for title, report in [('initial', original_qa), ('final', qa), ('targeted', post_qa)]:
        for check in report['checks']:
            name = qa_path + check['log']
            checked_logs.append(name)
            if name not in blobs or sha(blobs[name]) != check['log_sha256']:
                bad_logs.append({'report': title, 'log': name})
    if bad_logs:
        errors.append({'evidence_log_mismatches': bad_logs})
    assert qa['tests'] == 902 and qa['passed'] and all(c['passed'] for c in qa['checks'])
    assert all(c['passed'] for c in post_qa['checks'])
    assert {c['name'] for c in original_qa['checks'] if not c['passed']} == {'ruff', 'mypy'}
    repeated = sum(c.get('tests') or 0 for c in post_qa['checks'])
    assert repeated == 28
    static_diff = []
    for relative in ['quant/harpoon_quant/causal_panel.py', 'quant/tests/test_observation_stream.py']:
        a = blobs[qa_path + 'before_static_fix/' + relative].decode().splitlines(keepends=True)
        b = blobs[relative].decode().splitlines(keepends=True)
        static_diff.extend(difflib.unified_diff(a, b, fromfile='before/' + relative, tofile='after/' + relative))
    assert ''.join(static_diff) == blobs[qa_path + 'static_fix.patch'].decode()

    required = [
        'package.json', 'package-lock.json', 'tsconfig.xxx.json', 'install.sh', 'status.sh', 'stop.sh',
        'deploy/ultimate_install.py', 'deploy/Dockerfile.xxx', 'deploy/entry30.py', 'deploy/dashboard30.html',
        'HARPOON_XXXUltimate.html', 'runtime/quant_bridge.cjs', 'runtime/discovery.cjs',
        'runtime30/server.js', 'runtime30/coordinator.js', 'xxx/server.ts', 'xxx/coordinator.ts', 'xxx/version.ts',
        'tools/coordinator_replay.cjs', 'tools/observation_replay_input.cjs', 'tools/funded_comparison.cjs',
        'tools/fixed_predictor_worker.cjs', 'tools/measurement_registration.py', 'tools/build_causal_panel.py',
        'tools/level4_readiness.cjs', 'tools/level5_readiness.cjs', 'tools/export_observation_snapshot.cjs',
        'tools/verify_remediation.py', 'tools/LEVEL5_READINESS_CONTRACT.txt', 'tools/OBSERVATION_SNAPSHOT_CONTRACT.txt',
        'quant/harpoon_quant/economic_gate.py', 'quant/harpoon_quant/economic_gate_v2.py',
        'quant/harpoon_quant/scalar_svr.py', 'quant/harpoon_quant/causal_panel.py', 'quant/harpoon_quant/fixed_predictor.py',
        'quant/requirements-tested.txt', 'quant/pyproject.toml', 'quant/README_ES.md',
        'LEEME_INTEGRAL_30_10_1.txt', 'LEEME_NIVEL5_30_12_0.txt',
        'EVALUACION_ECONOMICA_HARPOONX_30_12_0.yaml', 'evidence/level5_30_12_0/reproduce_level5.py',
    ]
    absent_required = [p for p in required if p not in blobs]
    if absent_required:
        errors.append({'required_files_missing': absent_required})
    assert blobs['HARPOON_XXXUltimate.html'] == blobs['deploy/dashboard30.html']
    package = json.loads(blobs['package.json'])
    package_lock = json.loads(blobs['package-lock.json'])
    assert package['version'] == package_lock['version'] == '30.12.0'

    hashes = defaultdict(list)
    for rel, content in blobs.items():
        hashes[sha(content)].append(rel)

EXCLUDED = {'node_modules', '__pycache__', '.ruff_cache', '.mypy_cache', '.pytest_cache', '.git', '.venv'}
PRODUCTION_PREFIXES = ('src/', 'runtime/', 'runtime30/', 'xxx/', 'service/', 'config/', 'deploy/', 'quant/harpoon_quant/', 'research/')
ROOT_FILES = {'package.json', 'package-lock.json', 'tsconfig.xxx.json', 'install.sh', 'status.sh', 'stop.sh',
              'install.ps1', 'status.ps1', 'stop.ps1', 'install.cmd', 'status.cmd', 'stop.cmd', 'HARPOON_XXXUltimate.html'}


def classify(rel):
    if rel.startswith(PRODUCTION_PREFIXES) or rel in ROOT_FILES:
        return 'production_or_research_implementation'
    if rel.startswith(('tools/', 'quant/tests/')):
        return 'tests_or_verification_tools'
    if rel in {'quant/requirements-tested.txt', 'quant/pyproject.toml'}:
        return 'dependency_contract'
    return None


lineage_paths = [
    ('30.7.0', 'baseline/fullapp/HARPOON_XXXUltimate_30_7_0'),
    ('30.8.0', 'svr_work/HARPOON_XXXUltimate_30_8_0'),
    ('30.9.0', 'remediation_work/HARPOON_XXXUltimate_30_9_0'),
    ('30.10.0', 'autonomy_work/HARPOON_XXXUltimate_30_10_0'),
    ('30.10.1', 'integral_work/HARPOON_XXXUltimate_30_10_1'),
    ('30.11.0', 'level4_work/HARPOON_XXXUltimate_30_11_0'),
    ('30.12.0', 'level5_work/HARPOON_XXXUltimate_30_12_0'),
]
lineage = []
for version, relative_root in lineage_paths:
    base = WORK / relative_root
    selected = [(str(p.relative_to(base)), p) for p in sorted(base.rglob('*'))
                if p.is_file() and not p.is_symlink() and not any(x in EXCLUDED for x in p.relative_to(base).parts)
                and p.suffix not in {'.pyc', '.pyo'} and classify(str(p.relative_to(base)))]
    equal = []
    changed = []
    absent = []
    for relative, p in selected:
        old_digest = sha(p.read_bytes())
        if relative not in blobs:
            absent.append({'path': relative, 'old_sha256': old_digest, 'same_bytes_elsewhere_in_archive': hashes.get(old_digest, [])})
        elif sha(blobs[relative]) == old_digest:
            equal.append(relative)
        else:
            changed.append(relative)
    lineage.append({'version': version, 'source': relative_root, 'implementation_and_verification_files': len(selected),
                    'same_path_and_bytes': len(equal), 'same_path_updated': len(changed), 'missing_at_same_path': absent,
                    'changed_paths': changed, 'class_counts': dict(Counter(classify(rel) for rel, _ in selected))})
write('lineage.json', lineage)
for row in lineage:
    if row['missing_at_same_path']:
        errors.append({'lineage_omissions_need_review': row['version'], 'items': row['missing_at_same_path']})

checksum_manifest = read(WORK / 'level5_delivery/HARPOONX_30_12_0_SHA256.json')
outer = next(a for a in checksum_manifest['artifacts'] if a['name'] == ZIP.name)
assert outer['sha256'] == sha(ZIP.read_bytes()) and outer['bytes'] == ZIP.stat().st_size
historical_manifest_names = [name for name in blobs if (name.endswith('MANIFEST_XXXUltimate.json') or name.endswith('MANIFEST_QUANT.json'))
                             and name not in {'MANIFEST_XXXUltimate.json', 'quant/MANIFEST_QUANT.json'}]
report = {
    'schema': 'HARPOON_INTEGRAL_READONLY_PACKAGE_AUDIT_1',
    'checked_at_mexico_city': datetime.now(ZoneInfo('America/Mexico_City')).isoformat(),
    'candidate': str(ZIP), 'application': '30.12.0', 'quant': '1.8.0',
    'status': 'PASS' if not errors else 'FINDINGS_REQUIRE_REVIEW', 'errors': errors,
    'scope': 'Delivered 30.12 archive, active manifests, retained logs and source snapshots, 30.7 through 30.12 release lineage file coverage. No new functional or financial test.',
    'additional_project_branches_not_inspected': ['31.0 through 31.4', 'Profit Framework 1.7', 'TP Neto', 'Options/Swing/Canasta48', 'Framework Aplicado 1.2'],
    'zip': {'sha256': outer['sha256'], 'bytes': outer['bytes'], 'files': len(blobs), 'bad_crc': bad_crc,
            'duplicate_names': duplicates, 'unsafe_paths': unsafe, 'symlinks': symlinks, 'inventory_difference': inventory_difference},
    'current_manifests': active_manifests, 'current_checksum_lists': active_sha_files,
    'archive_matches_working_files': not mismatch_source, 'required_distribution_files_checked': len(required),
    'required_distribution_files_missing': absent_required,
    'frozen_source_files_checked': len(freeze['files']), 'frozen_source_mismatches': freeze_mismatch,
    'preserved_test_evidence': {'unique_functional_cases': qa['tests'], 'passed': qa['passed'],
        'unique_log_files_hash_verified': len(set(checked_logs)), 'log_mismatches': bad_logs,
        'initial_static_failures_retained': ['ruff', 'mypy'], 'targeted_rechecks_not_added_to_count': repeated,
        'post_full_run_production_changes': modified_after_full_run, 'exact_two_file_static_patch_verified': True},
    'lineage': [{k: v for k, v in row.items() if k != 'changed_paths'} for row in lineage],
    'historical_manifests': {'count': len(historical_manifest_names), 'paths': historical_manifest_names,
        'treatment': 'Their bytes are verified by the current root manifest. They describe earlier snapshots; their old relative file tables are not claimed to describe the current tree.'},
    'dependency_scope': 'Complete application source/runtime/configuration/tests/evidence; external Node/Python packages are declared and installed by the installer, not vendored. No air-gapped installation or Docker build is claimed.',
    'deployment': 'NOT_PERFORMED', 'new_financial_trials': 0, 'financial_verdict': 'VENTAJA_NO_DEMOSTRADA', 'economic_score': 3,
    'external_independent_audit': False,
}
write('integral_audit.json', report)
print(json.dumps({k: report[k] for k in ['status', 'errors', 'zip', 'current_manifests', 'required_distribution_files_checked',
      'frozen_source_files_checked', 'preserved_test_evidence', 'lineage', 'economic_score']}, ensure_ascii=False, indent=2))
