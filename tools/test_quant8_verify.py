"""Synthetic, mocked verifier boundaries; never runs the historical family."""
import json
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import quant8_verify as v
from run_quant8 import expected_limits


class VerifyTests(unittest.TestCase):
    def fixture(self, root):
        paths = {'study': {'base_protocol': 'base', 'dataset': 'data'}, 'base': {}, 'data': {},
                 'signals.json': {'signals': []}, 'training_labels.json': {},
                 'feature_panel.json': {'rows': [], 'synthetic_contract_only': True},
                 'legacy_models.json': {'fit_calls': 8}, 'novel_models.json': {'fit_calls': 8},
                 'legacy_admissions.json': {'admissions': {'test': False}},
                 'novel_admissions.json': {'admissions': {'test': False}}}
        stack = ExitStack()
        stack.enter_context(patch.object(v.quant8_register, 'verify', return_value={'identity_hash': 'synthetic'}))
        stack.enter_context(patch.object(v.h, 'read', side_effect=lambda p: paths[Path(p).name]))
        stack.enter_context(patch.object(v.h, 'feature_panel', return_value={'rows': [], 'synthetic_contract_only': True, 'benchmark': 1}))
        stack.enter_context(patch.object(v.h, 'fit_fixed', return_value={'fit_calls': 8}))
        stack.enter_context(patch.object(v.q, 'fit_models', return_value={'fit_calls': 8}))
        stack.enter_context(patch.object(v.h, 'predict_fixed', return_value={'admissions': {'test': False}}))
        stack.enter_context(patch.object(v.q, 'predict', return_value={'admissions': {'test': False}}))
        return paths, stack

    def test_rebuilds_and_records_all_fits_without_authority(self):
        paths, stack = self.fixture(Path('/synthetic'))
        with stack:
            result = v.verify(Path('study'), Path('manifest'), Path('registration'), Path('/synthetic'))
        self.assertTrue(result['verified'])
        self.assertEqual(result['model_fit_verification_invocations'], 16)
        self.assertFalse(result['financial_acceptance_allowed'])

    def test_every_derived_artifact_tamper_refused(self):
        for name in ['feature_panel.json', 'legacy_models.json', 'novel_models.json', 'legacy_admissions.json', 'novel_admissions.json']:
            with self.subTest(name=name):
                paths, stack = self.fixture(Path('/synthetic'))
                paths[name] = {'forged_synthetic_only': True}
                with stack, self.assertRaisesRegex(ValueError, 'DERIVATION_MISMATCH'):
                    v.verify(Path('study'), Path('manifest'), Path('registration'), Path('/synthetic'))

    def test_registration_failure_prevents_all_derivations(self):
        with patch.object(v.quant8_register, 'verify', side_effect=ValueError('NOT_REGISTERED')), patch.object(v.h, 'fit_fixed') as fit:
            with self.assertRaisesRegex(ValueError, 'NOT_REGISTERED'):
                v.verify(Path('study'), Path('manifest'), Path('registration'), Path('/synthetic'))
            fit.assert_not_called()

    def test_preflight_does_not_fit(self):
        with patch.object(v.quant8_register, 'verify', return_value={'identity_hash': 'synthetic'}), patch.object(v.h, 'fit_fixed') as fit:
            self.assertTrue(v.verify(Path('study'), Path('manifest'), Path('registration'))['verified'])
            fit.assert_not_called()

    def test_risk_caps_derived_not_taken_from_report(self):
        fields = ['riskFraction', 'openRiskFraction', 'grossFraction', 'assetFraction']
        base = {'limits': {**dict.fromkeys(fields, .1), 'capitalUsd': 20000, 'maxDrawdown': .08, 'dailyLoss': .02}}
        study = {'regime_cap': {'fields': fields, 'limit_multiplier': .5}}
        cap = expected_limits(base, study, 'HUBER_REGIME_CAP')
        for f in fields:
            self.assertEqual(cap[f], .05)
        for f in ['capitalUsd', 'maxDrawdown', 'dailyLoss']:
            self.assertEqual(cap[f], base['limits'][f])
        self.assertEqual(expected_limits(base, study, 'C0'), base['limits'])
        study['regime_cap']['limit_multiplier'] = 2
        with self.assertRaisesRegex(ValueError, 'HALF_CAP'):
            expected_limits(base, study, 'HUBER_REGIME_CAP')


if __name__ == '__main__':
    unittest.main()
