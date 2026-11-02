#!/usr/bin/env python3
"""Rebuild diagnostic derivations before replay; never reserve or authorize live."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / 'quant'))
sys.path.insert(0, str(APP / 'tools'))
import quant8_register
from harpoon_quant import historical_bank as h, quant8_models as q
from harpoon_quant.core import digest


def verify(protocol_path, manifest_path, registration_dir, artifacts=None):
    receipt = quant8_register.verify(registration_dir, protocol_path, manifest_path)
    if artifacts is None:
        return {'verified': True, 'registration_identity_hash': receipt['identity_hash'], 'financial_acceptance_allowed': False}
    study = h.read(protocol_path)
    base = h.read(APP / study['base_protocol'])
    dataset = h.read(APP / study['dataset'])
    signals, labels = h.read(artifacts / 'signals.json'), h.read(artifacts / 'training_labels.json')
    panel = h.feature_panel(dataset, signals['signals'], base)
    panel.pop('benchmark', None)
    checks = {'feature_panel.json': panel}
    legacy = h.fit_fixed(panel, labels, base)
    novel = q.fit_models(panel, labels, base, study)
    checks.update({'legacy_models.json': legacy, 'novel_models.json': novel,
                   'legacy_admissions.json': h.predict_fixed(panel, legacy, base),
                   'novel_admissions.json': q.predict(panel, novel, base, study)})
    for name, derived in checks.items():
        if digest(derived) != digest(h.read(artifacts / name)):
            raise ValueError('QUANT8_DERIVATION_MISMATCH:' + name)
    return {'schema': 'HARPOON_QUANT8_DERIVATION_VERIFICATION_1', 'verified': True,
            'hashes': {name: digest(value) for name, value in checks.items()},
            'model_fit_verification_invocations': legacy['fit_calls'] + novel['fit_calls'],
            'registration_identity_hash': receipt['identity_hash'], 'financial_acceptance_allowed': False,
            'scope': 'CJS also regenerates signals and labels from the registered dataset; all models and admissions rebuilt here'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--protocol', type=Path, required=True)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--registration-dir', type=Path, required=True)
    p.add_argument('--artifacts', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = verify(a.protocol, a.manifest, a.registration_dir, a.artifacts)
    h.write(a.output, result)
    print('REGISTERED_DERIVATION_VERIFIED')


if __name__ == '__main__':
    main()
