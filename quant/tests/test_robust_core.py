"""Synthetic engineering fixtures: certificates, not trading-performance evidence."""
import copy
import unittest
from unittest.mock import patch

import numpy as np
from test_quant import calibration, candidate, request

from harpoon_quant import core, robust_core


class RobustCoreTests(unittest.TestCase):
    def test_feasible_proposal_is_verified_without_order_authority(self):
        result = robust_core.allocate(request([candidate()]), calibration())
        self.assertEqual(result['status'], 'VERIFIED_RESEARCH_PROPOSAL', result)
        self.assertTrue(result['selected'])
        self.assertTrue(result['certificate']['verified'])
        self.assertEqual(result['certificate']['incremental_mean_uncertainty']['original_rows'], 28)
        self.assertFalse(result['execution_allowed'])
        self.assertFalse(result['level8_accredited'])

    def test_future_residual_is_rejected_before_solver(self):
        cal = calibration()
        cal['models']['A']['residuals']['2026-11-01'] = .1
        # Reproduce the legacy function's missing chronology check.
        self.assertEqual(core.scenarios(cal, {'A': .03}, core.Config())[2], 29)
        with patch.object(core, 'allocate') as solver:
            result = robust_core.allocate(request([candidate()]), cal)
        self.assertIn('RESIDUAL_AFTER_CALIBRATION', result['reason'])
        solver.assert_not_called()

    def test_negative_expected_edge_abstains(self):
        result = robust_core.allocate(request([candidate()]), calibration(mu=-.03))
        self.assertEqual(result['selected'], [])
        self.assertFalse(result['execution_allowed'])

    def test_original_rows_not_resampled_count_drive_uncertainty(self):
        r = request([candidate()])
        a = robust_core.allocate(r, calibration(), core.Config(scenarios=128))
        b = robust_core.allocate(r, calibration(), core.Config(scenarios=512))
        # Compare per-lot SE even if legacy scenario constraints change sizing.
        se_a = a['certificate']['incremental_mean_uncertainty']['standard_error'] / a['selected'][0]['lots']
        se_b = b['certificate']['incremental_mean_uncertainty']['standard_error'] / b['selected'][0]['lots']
        self.assertAlmostEqual(se_a, se_b)

    def test_positive_serial_dependence_raises_se(self):
        values = np.repeat(np.array([-1., 1.] * 10), 10)
        hac = robust_core.mean_uncertainty(values, 5)
        iid = robust_core.mean_uncertainty(values, 0)
        self.assertGreater(hac['standard_error'], iid['standard_error'])

    def test_anticorrelation_never_reduces_below_iid_floor(self):
        values = np.array([-1., 1.] * 20)
        hac = robust_core.mean_uncertainty(values, 5)
        iid = robust_core.mean_uncertainty(values, 0)
        self.assertGreaterEqual(hac['standard_error'], iid['standard_error'])

    def test_bad_uncertainty_inputs_rejected(self):
        for x in (np.arange(19), np.ones((20, 2)), np.full(20, np.nan)):
            with self.assertRaises(ValueError):
                robust_core.mean_uncertainty(x)

    def test_tampered_quantities_fail_independent_certificate(self):
        r, cal, cfg = request([candidate()]), calibration(), core.Config()
        proposal = core.allocate(r, cal, cfg)
        proposal['selected'][0]['quantity'] += .5
        with self.assertRaisesRegex(ValueError, 'QUANTITY_MISMATCH'):
            robust_core.certify(r, cal, cfg, proposal)

    def test_fractional_lots_cannot_pass_as_integer_solution(self):
        r, cal, cfg = request([candidate()]), calibration(), core.Config()
        proposal = core.allocate(r, cal, cfg)
        proposal['selected'][0]['lots'] += .000001
        with self.assertRaisesRegex(ValueError, 'INTEGER_SELECTED_LOTS'):
            robust_core.certify(r, cal, cfg, proposal)

    def test_overfunded_or_overrisk_solution_cannot_pass(self):
        r, cal, cfg = request([candidate()]), calibration(), core.Config()
        proposal = core.allocate(r, cal, cfg)
        proposal['selected'][0].update(lots=10000, quantity=10000)
        r['candidates'][0]['max_qty'] = 10000
        with self.assertRaisesRegex(ValueError, 'CERTIFICATE_FAILED'):
            robust_core.certify(r, cal, cfg, proposal)

    def test_duplicate_holdings_cannot_double_spend_inventory(self):
        c = candidate()
        r = request([c])
        r['holdings'] = [copy.deepcopy(c)]
        result = robust_core.allocate(r, calibration())
        self.assertEqual(result['selected'], [])
        self.assertIn('DUPLICATE_INPUT_ID', result['reason'])

    def test_input_and_calibration_unchanged(self):
        r, cal = request([candidate()]), calibration()
        before = copy.deepcopy((r, cal))
        robust_core.allocate(r, cal)
        self.assertEqual(before, (r, cal))

    def test_sparse_common_panel_blocked(self):
        cal = calibration()
        cal['models']['A']['residuals'] = dict(list(cal['models']['A']['residuals'].items())[:19])
        self.assertIn('ORIGINAL_RESIDUAL_ROWS', robust_core.allocate(request([candidate()]), cal)['reason'])

    def test_original_panel_can_veto_an_optimistic_proposal(self):
        r, cal, cfg = request([candidate()]), calibration(mu=-.03), core.Config()
        fake = {'selected': [{'id': 'A-equity', 'lots': 1, 'quantity': 1}]}
        with self.assertRaisesRegex(ValueError, 'ORIGINAL_PANEL_EDGE_NOT_ROBUST'):
            robust_core.certify(r, cal, cfg, fake)

    def test_partial_fill_tail_is_checked_without_other_legs_gains(self):
        r, cal = request([candidate(), candidate(name='B')]), calibration()
        cfg = core.Config(stress_fraction=.0001)
        fake = {'selected': [{'id': 'A-equity', 'lots': 1, 'quantity': 1},
                             {'id': 'B-equity', 'lots': 1, 'quantity': 1}]}
        with self.assertRaisesRegex(ValueError, 'partial_fill_stress'):
            robust_core.certify(r, cal, cfg, fake)


if __name__ == '__main__':
    unittest.main()
