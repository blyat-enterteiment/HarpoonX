"""Tamper and accounting regressions using retained modeled report fixtures."""
import copy
import json
import math
import unittest
from pathlib import Path

from profitability_forensics import analyze_report, build, number

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'evidence/residual_30_18_0/run_completed'


class ForensicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads((REPORTS / 'NOMINAL_RESIDUAL_LONG.json').read_text())

    def reject_mutation(self, mutate, expected):
        report = copy.deepcopy(self.report)
        mutate(report)
        with self.assertRaisesRegex(ValueError, expected):
            analyze_report(report)

    def test_baseline_reconciles(self):
        result = analyze_report(self.report)
        self.assertAlmostEqual(result['net_modeled_usd'], -118.65)
        self.assertAlmostEqual(result['net_before_shared_fixed_usd'], 285.35)
        self.assertAlmostEqual(result['fixed_path_break_even_daily_budget_usd'], 285.35 / 404)
        self.assertEqual(result['campaigns'], 67)

    def test_complete_family_does_not_select_positive_control(self):
        result = build(REPORTS)
        self.assertEqual(len(result['accounts']), 8)
        self.assertIsNone(result['selected_policy'])
        self.assertFalse(result['level8_accredited'])
        self.assertGreater(result['accounts']['NOMINAL:STOCK_THRESHOLD_OFF']['net_modeled_usd'], 0)
        self.assertLess(result['accounts']['STRESS:STOCK_THRESHOLD_OFF']['net_modeled_usd'], 0)

    def test_cash_not_charged_per_campaign_or_asset(self):
        r = json.loads((REPORTS / 'NOMINAL_CASH.json').read_text())
        result = analyze_report(r)
        self.assertEqual(result['shared_fixed_costs_usd'], 404)
        self.assertEqual(result['fixed_path_break_even_daily_budget_usd'], 0)
        self.assertEqual(result['loss_campaigns_causing_at_least_80pct_losses'], 0)

    def test_nonfinite_and_boolean_rejected(self):
        for value in (True, None, '1', math.nan, math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                number(value)

    def test_cash_reset_rejected(self):
        self.reject_mutation(lambda r: r['curve'][1].update(equity_start_usd=20000), 'CONTINUITY')

    def test_hidden_cost_rejected(self):
        self.reject_mutation(lambda r: r['curve'][0].update(external_costs_usd=0), 'SESSION_PNL')

    def test_fee_rebate_rejected(self):
        self.reject_mutation(lambda r: r['curve'][0].update(modeled_trading_fees_usd=-1), 'NEGATIVE_COST')

    def test_duplicate_campaign_rejected(self):
        self.reject_mutation(lambda r: r['funded'].append(r['funded'][0]), 'IDENTITIES')

    def test_missing_session_rejected(self):
        self.reject_mutation(lambda r: r['curve'].pop(), 'SESSION_COUNT')

    def test_missing_dividend_rejected(self):
        self.reject_mutation(lambda r: r['accounting'].update(dividendAccruedUsd=0), 'dividendAccruedUsd')

    def test_terminal_inventory_rejected(self):
        self.reject_mutation(lambda r: r['summary']['CONTINUOUS'].update(positions_carried_out=1), 'CLOSED_ACCOUNT')

    def test_holding_deadline_rejected(self):
        self.reject_mutation(lambda r: r['funded'][0].update(closed=r['funded'][0]['holdingClockStartedAt'] + 73 * 3600000), '72H')

    def test_execution_authority_rejected(self):
        self.reject_mutation(lambda r: r.update(liveApproved=True), 'AUTHORITY')


if __name__ == '__main__':
    unittest.main()
