#!/usr/bin/env python3
"""One exact reproduction of frozen roadmap recipes; zero additional trials.

This verifier adds no policy, thresholds, selection or market observations. It
preserves the retained registry incident and never rewrites registered results.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "quant"), str(ROOT / "tools")]
import run_roadmap9_research as research
from harpoon_quant.roadmap9.registry import verify_registry


def reproduce(directory: Path) -> dict:
    os.chdir(ROOT)
    directory = directory.resolve()
    p = research.read(ROOT / 'research/roadmap9/protocol.json')
    bindings = research.read(directory / 'source_bindings.json')
    research.require(research.source_bindings(p) == bindings, 'SOURCE_BINDING_CHANGED')
    before = verify_registry(directory / 'registry.jsonl')
    research.require(before['completed_measurements'] == 12, 'TWELVE_BOUND_RESULTS_REQUIRED')
    started = time.perf_counter()
    data = research.read(ROOT / p['dataset'])
    panel = research.ClockPanel(data)
    rows = panel.rows()
    forecasts = research.forecast_panel(panel, p['periods']['evaluation_start'], p['periods']['evaluation_end'], rows)
    base = research.continuation_base(rows, p)
    bundle = research.make_signals(base['signals'], forecasts, p)
    _, _, archived = research.research9_prepare.prepare()
    for scenario in research.SCENARIOS:
        bundle['signals'][scenario]['ARCHIVED_CONTINUATION'] = archived[scenario]['CONTINUATION']
    bundle['comparators'] = p['controls']
    research.require(bundle == research.read(directory / 'signals.json'), 'EXACT_SIGNAL_REPRODUCTION')
    research.require({'forecast': forecasts['models'], 'entry': base['models']} == research.read(directory / 'models.json.gz'), 'EXACT_MODEL_REPRODUCTION')
    reports, checks = {}, {}
    with tempfile.TemporaryDirectory(prefix='roadmap9_exact_reproduction_') as temporary:
        target = Path(temporary)
        (target / 'signals.json').write_text(json.dumps(bundle, allow_nan=False))
        for scenario in research.SCENARIOS:
            for rid in (*p['controls'], *research.RECIPE_IDS):
                result = subprocess.run(['node', 'tools/roadmap9_replay.cjs', str(target), rid, scenario],
                    cwd=ROOT, check=False, text=True, capture_output=True, timeout=600)
                research.require(result.returncode == 0, 'REPLAY_REPRODUCTION_FAILED:' + result.stderr)
                report = research.read(target / f'{scenario}_{rid}.json')
                key = scenario + ':' + rid
                reports[key] = report
                raw = (json.dumps(report, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()
                repeated_hash = hashlib.sha256(gzip.compress(raw, compresslevel=9, mtime=0)).hexdigest()
                expected_hash = research.sha(directory / f'{scenario}_{rid}.json.gz')
                research.require(repeated_hash == expected_hash, 'EXACT_ACCOUNT_REPRODUCTION:' + key)
                audit = research.audit_report(report, p, data, key)
                checks[key] = {'identical_gzip_sha256': repeated_hash, 'independent_ledger_reconciliation': audit['verified']}
        findings = research.statistics(reports, p, panel)
        findings['paired_exits'] = {s + ':' + r: research.read(target / (s + '_' + r + '.paired.json'))
            for s in research.SCENARIOS for r in research.RECIPE_IDS if r.startswith('H3_')}
        research.require(findings == research.read(directory / 'results.json'), 'EXACT_STATISTICS_AND_PAIRS_REPRODUCTION')
    after = verify_registry(directory / 'registry.jsonl')
    research.require(after == before, 'VERIFIER_CHANGED_REGISTRY')
    research.require(research.source_bindings(p) == bindings, 'SOURCES_CHANGED_DURING_REPRODUCTION')
    return {'schema': 'HARPOON_ROADMAP9_EXACT_REPRODUCTION_1', 'verified': True,
        'accounts': checks, 'model_and_signal_derivation_identical': True,
        'statistics_and_h3_pairs_identical': True, 'registry_head_unchanged': after['head'],
        'completed_candidate_measurements': after['completed_measurements'],
        'new_recipe_slots': 0, 'new_policy_measurements': 0, 'new_original_observations': 0,
        'registry_incident_preserved': 'evidence/roadmap9/research_registry_incident/incident.json',
        'runtime_seconds': time.perf_counter() - started,
        'financial_acceptance_allowed': False, 'source_origin': 'HISTORICAL_MODELED',
        'scope': 'Exact rerun from retained source/data bindings. Independent Python reconciles ledger quantities, fees, reservations and cash, not original observed fill prices.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = reproduce(args.directory)
    research.write(args.output, result)
    print(json.dumps({'verified': result['verified'], 'accounts': len(result['accounts']),
        'new_policy_measurements': 0, 'completed_candidate_measurements': result['completed_candidate_measurements']}))
