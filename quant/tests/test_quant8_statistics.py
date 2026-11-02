"""Synthetic statistics contracts only; these arrays are not financial evidence."""
import copy
import unittest
import numpy as np
from harpoon_quant.quant8_statistics import block_means, evaluate


class StatisticsContracts(unittest.TestCase):
    def fixture(self):
        policies = ['C0', 'RIDGE', 'SVR', 'RIDGE_HURDLE', 'HUBER_HURDLE', 'HUBER_REGIME_CAP']
        protocol = {'budget': {'policies': policies, 'scenarios': ['NOMINAL', 'STRESS']},
                    'statistics': {'block_lengths': [5, 20], 'bootstrap_replicates': 200, 'seed': 1701,
                                   'confidence': .95, 'simultaneous_endpoint_count': 60}}
        base = {'periods': {'test_start': '000', 'test_end': '999'}}
        reports = {s + ':' + p: {'portfolio': {'limits': {'maxDrawdown': .08, 'dailyLoss': .02}},
                   'metadata': {'maximumObservedEventDrawdown': .01},
                   'curve': [{'session_id': f'{i:03d}', 'portfolio_log_return': -.0001}
                   for i in range(100)]} for s in ['NOMINAL', 'STRESS'] for p in [*policies, 'CASH']}
        return reports, base, protocol

    def test_identical_policies_have_exactly_zero_paired_advantage(self):
        result = evaluate(*self.fixture())
        for block in result['by_block'].values():
            for pair in block['paired'].values():
                self.assertEqual(pair['lower_paired_log_return_family_adjusted'], 0)
        self.assertFalse(any(g['conditional_diagnostic_pass'] for g in result['gates'].values()))

    def test_all_positive_synthetic_results_never_grant_real_level8(self):
        reports, base, protocol = self.fixture()
        for key, report in reports.items():
            if 'HURDLE' in key or 'CAP' in key:
                for row in report['curve']:
                    row['portfolio_log_return'] = .001
        result = evaluate(reports, base, protocol)
        self.assertTrue(all(g['conditional_diagnostic_pass'] for g in result['gates'].values()))
        self.assertFalse(result['level8_accredited'])
        self.assertFalse(result['financial_acceptance_allowed'])

    def test_missing_cash_refused(self):
        args = list(self.fixture())
        del args[0]['NOMINAL:CASH']
        with self.assertRaisesRegex(ValueError, 'CASH_REQUIRED'):
            evaluate(*args)

    def test_profitable_path_does_not_override_observed_risk_breach(self):
        reports, base, protocol = self.fixture()
        for key, report in reports.items():
            if 'HURDLE' in key or 'CAP' in key:
                for row in report['curve']:
                    row['portfolio_log_return'] = .001
                report['metadata']['maximumObservedEventDrawdown'] = .09
        result = evaluate(reports, base, protocol)
        self.assertFalse(any(g['conditional_diagnostic_pass'] for g in result['gates'].values()))

    def test_session_mismatch_refused(self):
        args = list(self.fixture())
        args[0]['NOMINAL:CASH']['curve'][0]['session_id'] = '099'
        with self.assertRaisesRegex(ValueError, 'ALIGNMENT'):
            evaluate(*args)

    def test_multiplicity_cannot_be_reduced(self):
        args = list(self.fixture())
        args[2]['statistics']['simultaneous_endpoint_count'] = 30
        with self.assertRaisesRegex(ValueError, 'MULTIPLICITY'):
            evaluate(*args)

    def test_pairing_and_seed_deterministic(self):
        x = np.arange(200, dtype=float).reshape(100, 2)
        a = block_means(x, 5, 300, 9)
        self.assertTrue(np.array_equal(a, block_means(x, 5, 300, 9)))
        np.testing.assert_allclose(a[:, 1] - a[:, 0], 1)

    def test_nonfinite_and_short_refused(self):
        for x in (np.zeros((79, 2)), np.full((100, 2), np.nan)):
            with self.assertRaises(ValueError):
                block_means(x, 20, 100, 1)


if __name__ == '__main__':
    unittest.main()
