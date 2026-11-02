"""Focused synthetic counterexamples; no market strategy or PnL evaluation."""
import copy
import datetime as dt
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('historical_bank_data_audit', Path(__file__).with_name('historical_bank_data_audit.py'))
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class HistoricalDataAuditTests(unittest.TestCase):
    def row(self):
        return {'symbol': 'AAPL', 'timestamp': '2022-01-03T14:30:00+00:00',
                'open': 100.0, 'high': 102.0, 'low': 99.0, 'close': 101.0,
                'volume': 1234, 'vwap': 100.5}

    def grid(self):
        return {AUDIT.parse_time(self.row()['timestamp'])}

    def metadata(self):
        return {'universe': list(AUDIT.SYMBOLS), 'period': [AUDIT.START, AUDIT.END],
                'partition': AUDIT.PARTITION, 'nature': 'HISTORICAL_RETROSPECTIVE_CONDITIONAL',
                'execution_nature': 'MODELED_OHLCV', 'entries_after_study_end_allowed': False,
                'corporate_actions': {'completeness': None, 'date_query_semantics': 'process_date',
                                      'original_announcement_known_at': None},
                'bar_time_semantics': {'observed_latency_ms': None,
                                       'original_market_data_receipt_timestamp': None}}

    def dividend(self, **changes):
        event = {'id': 'test-dividend', 'symbol': 'AAPL', 'ex_date': '2022-02-04',
                 'payable_date': '2022-02-10', 'rate': 0.22,
                 'due_bill_on_date': None, 'due_bill_off_date': None}
        event.update(changes)
        return event

    def session(self):
        return [{'date': '2022-02-04', 'open': AUDIT.parse_time('2022-02-04T14:30:00Z'),
                 'close': AUDIT.parse_time('2022-02-04T21:00:00Z')}]

    def test_01_fixed_request_plan_128_and_leap_month(self):
        requests = AUDIT.expected_requests()
        self.assertEqual(len(requests), 128)
        self.assertEqual({r['args']['symbol'] for r in requests}, set(AUDIT.SYMBOLS))
        feb = next(r for r in requests if r['id'] == 'SPY_2024-02')
        self.assertEqual(feb['args']['end'], '2024-02-29T23:59:59Z')
        self.assertEqual(requests[-1]['id'], 'XLK_2024-08')

    def test_02_hash_verification_relocates_without_original_path(self):
        content = b'{"synthetic":true}\n'
        entry = {'name': 'raw/test.json', 'bytes': len(content), 'sha256': AUDIT.sha256(content)}
        outputs = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / 'raw').mkdir()
                (root / entry['name']).write_bytes(content)
                outputs.append(AUDIT.verify_manifest_files(root, [entry]))
        self.assertEqual(outputs[0], outputs[1])

    def test_03_missing_source_is_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(AUDIT.AuditError, 'MISSING_FILE'):
                AUDIT.verify_manifest_files(Path(directory), [{'name': 'missing.json', 'bytes': 1, 'sha256': 'a' * 64}])

    def test_04_changed_bytes_fail_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'x.json').write_bytes(b'changed')
            with self.assertRaisesRegex(AUDIT.AuditError, 'HASH_MISMATCH'):
                AUDIT.verify_manifest_files(root, [{'name': 'x.json', 'bytes': 7, 'sha256': AUDIT.sha256(b'correct')}])

    def test_05_traversal_absolute_and_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            for name in ('../outside.json', '/tmp/outside.json', 'raw\\outside.json'):
                with self.subTest(name=name), self.assertRaisesRegex(AUDIT.AuditError, 'UNSAFE_PATH'):
                    AUDIT.safe_path(root, name)
            (root / 'escape').symlink_to(Path(outside), target_is_directory=True)
            with self.assertRaisesRegex(AUDIT.AuditError, 'UNSAFE_PATH'):
                AUDIT.safe_path(root, 'escape/test.json')

    def test_06_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'duplicate.json'
            path.write_text('{"n":1,"n":2}')
            with self.assertRaisesRegex(AUDIT.AuditError, 'DUPLICATE_JSON_KEY'):
                AUDIT.load_json(path)

    def test_07_json_nonfinite_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'nan.json'
            path.write_text('{"n":NaN}')
            with self.assertRaisesRegex(AUDIT.AuditError, 'NONFINITE_JSON'):
                AUDIT.load_json(path)

    def test_08_regular_grid_has_only_modeled_end_plus_1000(self):
        bars, summary = AUDIT.normalize_rows([self.row()], 'AAPL', self.grid())
        self.assertEqual(bars[0]['end'] - bars[0]['t'], 300000)
        self.assertEqual(bars[0]['availableAt'] - bars[0]['end'], 1000)
        self.assertEqual(summary['regular_bars'], 1)

    def test_09_duplicate_bar_rejected(self):
        with self.assertRaisesRegex(AUDIT.AuditError, 'DUPLICATE_REGULAR_BAR'):
            AUDIT.normalize_rows([self.row(), self.row()], 'AAPL', self.grid())

    def test_10_missing_bar_rejected_without_interpolation(self):
        with self.assertRaisesRegex(AUDIT.AuditError, 'MISSING_REGULAR_BAR'):
            AUDIT.normalize_rows([], 'AAPL', self.grid())

    def test_11_ohlc_and_volume_units_validated(self):
        for field, value in [('high', 98), ('volume', -1), ('close', True)]:
            row = self.row()
            row[field] = value
            with self.subTest(field=field), self.assertRaises(AUDIT.AuditError):
                AUDIT.normalize_rows([row], 'AAPL', self.grid())

    def test_12_changed_availability_or_units_cannot_match_raw_reconstruction(self):
        bars, _ = AUDIT.normalize_rows([self.row()], 'AAPL', self.grid())
        expected = {'series': [{'pointValue': 1, 'bars': bars}]}
        for change in ('availability', 'units'):
            actual = copy.deepcopy(expected)
            if change == 'availability':
                actual['series'][0]['bars'][0]['availableAt'] -= 1000
            else:
                actual['series'][0]['pointValue'] = 100
            with self.subTest(change=change), self.assertRaisesRegex(AUDIT.AuditError, 'DATASET_RECONSTRUCTION_MISMATCH'):
                AUDIT.compare_dataset(actual, expected)

    def test_13_dividend_dates_use_ny_open_and_1600_or_null(self):
        events = {'cash_dividends': [self.dividend(), self.dividend(id='unpaid', payable_date=None)]}
        dividends, splits, _ = AUDIT.normalize_actions(events, self.session())
        self.assertEqual(splits, [])
        first = next(d for d in dividends if d['id'] == 'test-dividend')
        self.assertEqual(first['exAt'], AUDIT.parse_time('2022-02-04T14:30:00Z'))
        self.assertEqual(first['payableAt'], AUDIT.parse_time('2022-02-10T21:00:00Z'))
        self.assertIsNone(next(d for d in dividends if d['id'] == 'unpaid')['payableAt'])

    def test_14_payable_before_exdate_rejected(self):
        with self.assertRaisesRegex(AUDIT.AuditError, 'DIVIDEND_PAYABLE_BEFORE_EX'):
            AUDIT.normalize_actions({'cash_dividends': [self.dividend(payable_date='2022-02-03')]}, self.session())

    def test_15_cash_acquisition_does_not_convert_acquirer_units(self):
        announcements = {'cash_mergers': [{'id': 'synthetic-merger', 'acquirer_symbol': 'MSFT',
                                           'acquiree_symbol': 'NUAN', 'rate': 56}]}
        dividends, splits, excluded = AUDIT.normalize_actions(announcements, self.session())
        self.assertEqual(dividends, [])
        self.assertEqual(splits, [])
        self.assertEqual(excluded[0]['reason'], 'CASH_CONSIDERATION_PER_ACQUIREE_SHARE')

    def test_16_unknown_corporate_coverage_is_allowed_but_certification_is_rejected(self):
        metadata = self.metadata()
        AUDIT.validate_metadata(metadata)
        metadata['corporate_actions']['completeness'] = True
        with self.assertRaisesRegex(AUDIT.AuditError, 'CORPORATE_COMPLETENESS_NOT_UNKNOWN'):
            AUDIT.validate_metadata(metadata)

    def test_17_zero_is_not_a_substitute_for_unknown_latency(self):
        metadata = self.metadata()
        metadata['bar_time_semantics']['observed_latency_ms'] = 0
        with self.assertRaisesRegex(AUDIT.AuditError, 'UNSUPPORTED_OBSERVED_LATENCY'):
            AUDIT.validate_metadata(metadata)

    def test_18_missing_bank_cli_writes_failure_report_and_exit_two(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / 'report.json'
            status = AUDIT.main(['--data-dir', str(root / 'missing'), '--report', str(report)])
            self.assertEqual(status, 2)
            body = json.loads(report.read_text())
            self.assertEqual(body['status'], 'BLOCKED')
            self.assertFalse(body['conditional_replay_data_ready'])
            self.assertFalse(body['independent_provider_authenticity_verified'])

    def test_19_valid_json_with_invalid_manifest_shape_also_exits_two(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'manifest.json').write_text('null\n')
            report = root / 'report.json'
            self.assertEqual(AUDIT.main(['--data-dir', str(root), '--report', str(report)]), 2)
            body = json.loads(report.read_text())
            self.assertEqual(body['status'], 'BLOCKED')
            self.assertEqual(body['errors'][0]['code'], 'MALFORMED_OR_MISSING_DATA')


if __name__ == '__main__':
    unittest.main(verbosity=2)
