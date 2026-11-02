#!/usr/bin/env python3
"""Portable historical-bank integrity/coverage audit. No model, orders or PnL.

The unsigned local manifests prove consistency of retained bytes, not independent
provider authenticity. A passing report permits only the stated conditional
historical replay; corporate-action completeness remains unknown.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import math
import re
from pathlib import Path
from zoneinfo import ZoneInfo

SYMBOLS = ('AAPL', 'MSFT', 'SPY', 'XLK')
START, END = '2022-01-01', '2024-08-31'
CALENDAR_NAME = 'raw/calendar_2022-01_2024-09-06.json'
ACTIONS_NAME = 'raw/corporate_actions_2021-12_2024-10.json'
NY, UTC = ZoneInfo('America/New_York'), dt.timezone.utc
HASH = re.compile(r'^[a-f0-9]{64}$')
BAR_MS, AVAILABILITY_DELAY_MS = 300000, 1000
PARTITION = {'train': ['2022-01-01', '2023-06-30'],
             'validation': ['2023-07-01', '2023-12-31'],
             'historical_reserved_test': ['2024-01-01', '2024-08-31']}


class AuditError(ValueError):
    def __init__(self, code: str, detail: str = '') -> None:
        self.code, self.detail = code, detail
        super().__init__(f'{code}: {detail}' if detail else code)


def require(condition: bool, code: str, detail: str = '') -> None:
    if not condition:
        raise AuditError(code, detail)


def canonical_bytes(value: object) -> bytes:
    # This is the retained builder's byte serialization, not a model hash scheme.
    return (json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def strict_pairs(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, 'DUPLICATE_JSON_KEY', key)
        result[key] = value
    return result


def load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=strict_pairs,
                          parse_constant=lambda x: (_ for _ in ()).throw(AuditError('NONFINITE_JSON', x)))
    except AuditError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuditError('UNREADABLE_JSON', path.name + ': ' + type(exc).__name__) from exc


def safe_path(root: Path, name: str) -> Path:
    require(isinstance(name, str) and bool(name) and '\\' not in name, 'UNSAFE_PATH')
    relative = Path(name)
    require(not relative.is_absolute() and '..' not in relative.parts, 'UNSAFE_PATH', name)
    target = (root / relative).resolve()
    require(target.is_relative_to(root.resolve()) and target != root.resolve(), 'UNSAFE_PATH', name)
    return target


def verify_manifest_files(root: Path, entries: list) -> dict:
    require(isinstance(entries, list) and bool(entries), 'EMPTY_MANIFEST')
    result = {}
    for entry in entries:
        require(isinstance(entry, dict), 'INVALID_MANIFEST_ENTRY')
        name = entry.get('name')
        path = safe_path(root, name)
        require(name not in result, 'DUPLICATE_MANIFEST_PATH', name)
        require(isinstance(entry.get('sha256'), str) and HASH.fullmatch(entry['sha256']) is not None,
                'INVALID_MANIFEST_HASH', name)
        require(path.is_file(), 'MISSING_FILE', name)
        content = path.read_bytes()
        actual = sha256(content)
        require(actual == entry['sha256'], 'HASH_MISMATCH', name)
        require(isinstance(entry.get('bytes'), int) and not isinstance(entry['bytes'], bool)
                and entry['bytes'] == len(content), 'BYTE_COUNT_MISMATCH', name)
        result[name] = {'name': name, 'bytes': len(content), 'sha256': actual}
    return result


def parse_time(text: str, default_timezone=None) -> int:
    require(isinstance(text, str), 'INVALID_TIMESTAMP')
    try:
        value = dt.datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError as exc:
        raise AuditError('INVALID_TIMESTAMP', text) from exc
    if value.tzinfo is None:
        require(default_timezone is not None, 'TIMEZONE_MISSING', text)
        value = value.replace(tzinfo=default_timezone)
    return round(value.timestamp() * 1000)


def unwrap(receipt: dict) -> dict:
    require(isinstance(receipt, dict) and isinstance(receipt.get('response'), dict), 'INVALID_RECEIPT')
    response = receipt['response']
    require(not response.get('isError'), 'PROVIDER_ERROR')
    body = response.get('structuredContent')
    if body is None:
        texts = [x['text'] for x in response.get('content', []) if x.get('type') == 'text']
        require(len(texts) == 1, 'AMBIGUOUS_PROVIDER_BODY')
        body = json.loads(texts[0], object_pairs_hook=strict_pairs)
    if isinstance(body, dict) and isinstance(body.get('result'), str):
        body = json.loads(body['result'], object_pairs_hook=strict_pairs)
    require(isinstance(body, dict), 'INVALID_PROVIDER_BODY')
    return body


def expected_requests() -> list:
    result = []
    for year in range(2022, 2025):
        for month in range(1, 13 if year < 2024 else 9):
            start = dt.datetime(year, month, 1, tzinfo=UTC)
            next_month = dt.datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=UTC)
            end = next_month - dt.timedelta(seconds=1)
            for symbol in SYMBOLS:
                result.append({'id': f'{symbol}_{year}-{month:02d}',
                    'tool': 'mcp__codex_apps__alpaca_get_stock_bars',
                    'args': {'symbol': symbol, 'timeframe': '5Min',
                             'start': start.strftime('%Y-%m-%dT%H:%M:%SZ'),
                             'end': end.strftime('%Y-%m-%dT%H:%M:%SZ'),
                             'limit': 10000, 'feed': 'sip', 'sort': 'asc', 'currency': 'USD',
                             'asof': '2024-08-31', 'tz': 'UTC'}})
    return result


def build_calendar(calendar: list) -> tuple:
    require(isinstance(calendar, list), 'INVALID_CALENDAR')
    sessions, dates, prior_close = [], set(), 0
    for row in calendar:
        date = row['date']
        opened, closed = parse_time(row['open'], NY), parse_time(row['close'], NY)
        local_open = dt.datetime.fromtimestamp(opened / 1000, NY)
        local_close = dt.datetime.fromtimestamp(closed / 1000, NY)
        require(date not in dates and opened > prior_close and opened < closed,
                'DUPLICATE_OR_UNORDERED_CALENDAR', date)
        require(local_open.date().isoformat() == date == local_close.date().isoformat()
                and local_open.weekday() < 5 and local_open.time() == dt.time(9, 30)
                and local_close.time() in (dt.time(13), dt.time(16)), 'CALENDAR_SESSION_UNITS', date)
        sessions.append({'date': date, 'open': opened, 'close': closed})
        dates.add(date)
        prior_close = closed
    study = [s for s in sessions if START <= s['date'] <= END]
    tail = [s for s in sessions if s['date'] > END]
    require(len(study) == 669 and len(sessions) == 673, 'SESSION_COUNT_MISMATCH')
    require(study[0]['date'] == '2022-01-03' and study[-1]['date'] == '2024-08-30', 'CALENDAR_BOUNDARY_MISMATCH')
    require([s['date'] for s in tail] == ['2024-09-03', '2024-09-04', '2024-09-05', '2024-09-06'],
            'DEADLINE_CALENDAR_MISMATCH')
    by_month = collections.defaultdict(set)
    for session in study:
        by_month[session['date'][:7]].update(range(session['open'], session['close'], BAR_MS))
    grid = set().union(*by_month.values())
    require(len(grid) == 52038, 'BAR_GRID_SIZE_MISMATCH')
    return sessions, study, tail, dict(by_month), grid


def normalize_rows(rows: list, symbol: str, grid: set[int]) -> tuple:
    require(isinstance(rows, list), 'INVALID_BAR_LIST')
    timestamps, normalized = [], []
    for row in rows:
        require(row.get('symbol') == symbol, 'WRONG_BAR_SYMBOL', symbol)
        t = parse_time(row['timestamp'])
        timestamps.append(t)
        if t not in grid:
            continue
        values = [row[k] for k in ('open', 'high', 'low', 'close', 'volume')]
        require(all(finite(v) for v in values), 'NONFINITE_OHLCV', symbol)
        o, h, l, c, v = values
        require(min(o, h, l, c) > 0 and v >= 0 and l <= min(o, c) + 1e-10
                and h + 1e-10 >= max(o, c) and l <= h, 'INVALID_OHLCV', symbol)
        bar = {'t': t, 'end': t + BAR_MS, 'availableAt': t + BAR_MS + AVAILABILITY_DELAY_MS,
               'o': o, 'h': h, 'l': l, 'c': c, 'v': v}
        if row.get('vwap') is not None:
            require(finite(row['vwap']), 'INVALID_VWAP', symbol)
            bar['vw'] = row['vwap']
        normalized.append(bar)
    counts = collections.Counter(timestamps)
    require(not any(counts[t] > 1 for t in grid), 'DUPLICATE_REGULAR_BAR', symbol)
    require(grid.issubset(counts), 'MISSING_REGULAR_BAR', symbol)
    summary = {'raw_records': len(rows), 'regular_bars': len(normalized),
               'outside_regular_grid_records': len(rows) - len(normalized),
               'zero_volume_regular_bars': sum(x['v'] == 0 for x in normalized)}
    return normalized, summary


def normalize_actions(announcements: dict, sessions: list) -> tuple:
    require(isinstance(announcements, dict), 'INVALID_ACTION_INVENTORY')
    session_dates = {s['date']: s for s in sessions}
    dividends, splits, not_applied, ids = [], [], [], set()
    for kind, events in announcements.items():
        require(isinstance(events, list), 'INVALID_ACTION_GROUP', kind)
        for event in events:
            event_id = event.get('id')
            require(isinstance(event_id, str) and event_id not in ids, 'DUPLICATE_OR_MISSING_ACTION_ID')
            ids.add(event_id)
            if kind == 'cash_dividends':
                symbol, ex_date = event.get('symbol'), event.get('ex_date')
                require(symbol in SYMBOLS and isinstance(ex_date, str), 'DIVIDEND_IDENTITY_OR_EX_DATE')
                if not START <= ex_date <= END:
                    not_applied.append({'id': event_id, 'kind': kind, 'reason': 'EX_DATE_OUTSIDE_STUDY'})
                    continue
                require(ex_date in session_dates, 'DIVIDEND_EX_DATE_NOT_SESSION')
                rate = event.get('rate')
                require(finite(rate) and rate >= 0, 'DIVIDEND_RATE_INVALID')
                require(event.get('due_bill_on_date') is None and event.get('due_bill_off_date') is None,
                        'UNSUPPORTED_DUE_BILL')
                ex_at = session_dates[ex_date]['open']
                pay_date = event.get('payable_date')
                payable_at = parse_time(pay_date + 'T16:00:00', NY) if pay_date is not None else None
                require(payable_at is None or payable_at >= ex_at, 'DIVIDEND_PAYABLE_BEFORE_EX')
                dividends.append({'id': event_id, 'symbol': symbol, 'exAt': ex_at,
                                  'payableAt': payable_at, 'amountPerShare': rate})
            elif kind in ('forward_splits', 'reverse_splits'):
                symbol, ex_date = event.get('symbol'), event.get('ex_date')
                require(symbol in SYMBOLS and isinstance(ex_date, str), 'SPLIT_IDENTITY_OR_EX_DATE')
                if not START <= ex_date <= END:
                    not_applied.append({'id': event_id, 'kind': kind, 'reason': 'EX_DATE_OUTSIDE_STUDY'})
                    continue
                require(ex_date in session_dates, 'SPLIT_EX_DATE_NOT_SESSION')
                new, old = event.get('new_rate'), event.get('old_rate')
                require(finite(new) and finite(old) and new > 0 and old > 0, 'SPLIT_RATIO_INVALID')
                splits.append({'symbol': symbol, 'at': session_dates[ex_date]['open'], 'ratio': new / old})
            elif (kind == 'cash_mergers' and event.get('acquirer_symbol') in SYMBOLS
                  and event.get('acquiree_symbol') not in SYMBOLS and isinstance(event.get('acquiree_symbol'), str)):
                not_applied.append({'id': event_id, 'kind': kind, 'reason': 'CASH_CONSIDERATION_PER_ACQUIREE_SHARE',
                                    'acquirer': event['acquirer_symbol'], 'acquiree': event['acquiree_symbol']})
            else:
                raise AuditError('UNSUPPORTED_OBSERVED_ACTION', kind)
    return (sorted(dividends, key=lambda x: (x['exAt'], x['symbol'], x['id'])),
            sorted(splits, key=lambda x: (x['at'], x['symbol'])), not_applied)


def compare_dataset(actual: dict, expected: dict) -> bytes:
    require(isinstance(actual, dict), 'INVALID_RESEARCH_DATASET')
    require(actual == expected, 'DATASET_RECONSTRUCTION_MISMATCH',
            'Raw bars, units, calendar, availability, action accounting or provenance differ.')
    return canonical_bytes(expected)


def validate_metadata(metadata: dict) -> None:
    require(metadata.get('universe') == list(SYMBOLS) and metadata.get('period') == [START, END]
            and metadata.get('partition') == PARTITION, 'METADATA_SCOPE_MISMATCH')
    require(metadata.get('nature') == 'HISTORICAL_RETROSPECTIVE_CONDITIONAL'
            and metadata.get('execution_nature') == 'MODELED_OHLCV', 'METADATA_NATURE_MISMATCH')
    require(metadata.get('entries_after_study_end_allowed') is False, 'POST_STUDY_ENTRY_AUTHORITY')
    actions = metadata.get('corporate_actions', {})
    require('completeness' in actions and actions['completeness'] is None,
            'CORPORATE_COMPLETENESS_NOT_UNKNOWN')
    require(actions.get('date_query_semantics') == 'process_date', 'ACTION_QUERY_SEMANTICS')
    require(actions.get('original_announcement_known_at') is None, 'UNSUPPORTED_ANNOUNCEMENT_KNOWN_AT')
    times = metadata.get('bar_time_semantics', {})
    require('observed_latency_ms' in times and times['observed_latency_ms'] is None
            and 'original_market_data_receipt_timestamp' in times
            and times['original_market_data_receipt_timestamp'] is None, 'UNSUPPORTED_OBSERVED_LATENCY')


def audit_data_dir(data_dir: Path) -> tuple[dict, bytes | None]:
    report = {'schema': 'HARPOON_HISTORICAL_BANK_AUDIT_1', 'status': 'BLOCKED',
              'scope': 'CONDITIONAL_HISTORICAL_DATA_ONLY', 'errors': [],
              'independent_provider_authenticity_verified': False,
              'corporate_action_completeness': None,
              'prospective_observations_verified': False,
              'financial_or_model_execution_performed': False,
              'profitability_grade_accredited': None}
    try:
        root = data_dir.resolve()
        manifest = load_json(root / 'manifest.json')
        require(manifest.get('algorithm') == 'SHA-256', 'MANIFEST_ALGORITHM')
        derived = verify_manifest_files(root, manifest['files'])
        required_derived = {'request_plan.json', 'capture_receipt.json', 'source_manifest.json',
                            'quality.json', 'metadata.json', 'build_research_dataset.py', 'research_dataset.json'}
        require(required_derived.issubset(derived), 'DERIVED_MANIFEST_COVERAGE')
        source_manifest = load_json(root / 'source_manifest.json')
        require(source_manifest.get('algorithm') == 'SHA-256', 'SOURCE_MANIFEST_ALGORITHM')
        sources = verify_manifest_files(root, source_manifest['files'])
        requests = expected_requests()
        required_sources = {f"raw/{r['id']}.json" for r in requests} | {CALENDAR_NAME, ACTIONS_NAME}
        require(set(sources) == required_sources and len(sources) == 130, 'RAW_MANIFEST_COVERAGE')
        require(source_manifest.get('raw_file_count') == 130 and source_manifest.get('raw_bytes')
                == sum(x['bytes'] for x in sources.values()), 'RAW_MANIFEST_TOTALS')
        require(source_manifest.get('upstream_authenticity_independently_certified') is False,
                'UNSUPPORTED_SOURCE_AUTHENTICITY_CLAIM')
        plan = load_json(root / 'request_plan.json')
        require(plan.get('universe') == list(SYMBOLS) and plan.get('requests') == requests
                and plan.get('request_count') == 128 and plan.get('partition') == PARTITION,
                'REQUEST_PLAN_SCOPE_MISMATCH')
        calendar_body = unwrap(load_json(root / CALENDAR_NAME))
        require(calendar_body.get('request') == {'start_date': '2022-01-01', 'end_date': '2024-09-06'},
                'CALENDAR_REQUEST_MISMATCH')
        sessions, study, tail, grids, full_grid = build_calendar(calendar_body['calendar'])
        by_symbol = {s: [] for s in SYMBOLS}
        chunks = []
        for request in requests:
            receipt = load_json(root / f"raw/{request['id']}.json")
            require(receipt.get('request') == request, 'CAPTURE_REQUEST_MISMATCH', request['id'])
            body = unwrap(receipt)
            symbol = request['args']['symbol']
            require(set(body['bars']) == {symbol}, 'RESPONSE_UNIVERSE_MISMATCH', request['id'])
            provider_request = body['request']
            require(provider_request.get('symbols') == [symbol], 'RESPONSE_SYMBOL_MISMATCH')
            for key in ('timeframe', 'start', 'end', 'limit', 'feed', 'sort', 'currency', 'asof', 'tz'):
                require(provider_request.get(key) == request['args'][key], 'RESPONSE_PARAMETER_MISMATCH', key)
            rows = body['bars'][symbol]
            require(body['counts']['records'] == len(rows) and len(rows) <= 10000, 'RAW_COUNT_MISMATCH')
            month = request['id'].split('_', 1)[1]
            bars, summary = normalize_rows(rows, symbol, grids[month])
            by_symbol[symbol].extend(bars)
            chunks.append({'id': request['id'], **summary})
        series = []
        for symbol in SYMBOLS:
            bars = sorted(by_symbol[symbol], key=lambda x: x['t'])
            require(len(bars) == 52038 and {b['t'] for b in bars} == full_grid,
                    'FINAL_SYMBOL_GRID_MISMATCH', symbol)
            series.append({'symbol': symbol, 'root': symbol, 'pointValue': 1, 'tick': 0.01, 'bars': bars})
        action_receipt = load_json(root / ACTIONS_NAME)
        require(action_receipt['request'] == {'tool': 'mcp__codex_apps__alpaca_get_corporate_actions',
            'args': {'symbols': list(SYMBOLS), 'start': '2021-12-01', 'end': '2024-10-31',
                     'limit': 1000, 'sort': 'asc'}}, 'ACTION_REQUEST_MISMATCH')
        actions = unwrap(action_receipt)['announcements']
        dividends, splits, not_applied = normalize_actions(actions, sessions)
        expected = {'schema': 'HARPOON-ULTIMATE-DATA-1', 'kind': 'ALPACA_PROXY',
            'provenance': {'source': 'ALPACA_TOOL_HISTORICAL_SIP_5MIN_RECONSTRUCTED_2022_2024',
                'feed': 'SIP', 'files': [{'name': x['name'], 'sha256': x['sha256']}
                    for x in sorted(sources.values(), key=lambda x: x['name'])], 'execution': 'MODELED_OHLCV'},
            'sessions': sessions, 'splitEvents': splits, 'cashDividends': dividends, 'series': series}
        actual = load_json(root / 'research_dataset.json')
        rebuilt = compare_dataset(actual, expected)
        require(sha256(rebuilt) == derived['research_dataset.json']['sha256'], 'REBUILT_BYTE_HASH_MISMATCH')
        metadata = load_json(root / 'metadata.json')
        validate_metadata(metadata)
        quality = load_json(root / 'quality.json')
        require(quality.get('grid_complete') is True and quality.get('bar_issues') == []
                and quality.get('action_issues') == []
                and quality.get('retained_regular_bars_total') == 208152,
                'STORED_QUALITY_REPORT_MISMATCH')
        raw_count = sum(c['raw_records'] for c in chunks)
        report.update({'status': 'PASS_CONDITIONAL_HISTORICAL_ONLY', 'conditional_replay_data_ready': True,
            'dataset': derived['research_dataset.json'],
            'manifest_hashes': {'manifest.json': sha256((root / 'manifest.json').read_bytes()),
                                'source_manifest.json': derived['source_manifest.json']['sha256']},
            'verified_raw_files': len(sources), 'verified_derived_files': len(derived),
            'raw_bytes': sum(x['bytes'] for x in sources.values()),
            'dataset_reconstructed_from_raw_and_byte_identical': True,
            'universe': list(SYMBOLS), 'period': [START, END],
            'sessions': {'study': len(study), 'deadline_only': len(tail),
                         'partition_counts': {role: sum(a <= s['date'] <= b for s in study)
                                              for role, (a, b) in PARTITION.items()}},
            'bars': {'raw': raw_count, 'regular': 208152, 'per_symbol': 52038,
                     'outside_regular_grid': raw_count - 208152, 'missing': 0, 'duplicates': 0,
                     'invalid_ohlcv': 0, 'zero_volume_regular': sum(c['zero_volume_regular_bars'] for c in chunks)},
            'corporate_actions': {'counts_observed_in_receipt': {k: len(v) for k, v in actions.items()},
                'cash_dividends_in_study': len(dividends), 'splits_observed_in_study': len(splits),
                'completeness': None, 'events_not_applied': not_applied,
                'ex_at': 'Calendar session open on observed ex_date; modeled accounting timestamp.',
                'payable_at': '16:00 America/New_York on supplied payable_date, otherwise null; no observed posting time.'},
            'technical_table': [
                {'variable': 'bar_resolution', 'unit': 'seconds', 'value': 300, 'nature': 'HISTORICAL_BAR_INTERVAL'},
                {'variable': 'regular_coverage', 'unit': 'bars', 'value': 208152, 'expected': 208152},
                {'variable': 'study_sessions', 'unit': 'sessions', 'value': 669},
                {'variable': 'deadline_only_sessions', 'unit': 'sessions', 'value': 4},
                {'variable': 'modeled_availability_after_bar_end', 'unit': 'milliseconds', 'value': 1000, 'nature': 'ASSUMPTION'},
                {'variable': 'original_receipt_latency', 'unit': 'milliseconds', 'value': None,
                 'reason': 'Historical capture has no original receipt timestamps.'},
                {'variable': 'decision_or_execution_latency', 'unit': 'milliseconds', 'value': None,
                 'reason': 'No historical decision, order or fill observations in this bank.'},
                {'variable': 'observed_executable_spread_or_fill_probability', 'unit': None, 'value': None,
                 'reason': 'OHLCV bars do not contain executable quotes or queue/fill observations.'}],
            'limitations': [
                'Hashes certify consistency of local retained bytes; manifests and tool responses are not independently signed provider attestations.',
                'The test period predates strategy design and remains retrospective historical evaluation, not real-account or prospective validation.',
                'Corporate-action completeness is unknown. The absence of returned split events is not certified absence of splits.',
                'The endpoint default is documented as raw; the connector has no explicit adjustment parameter or independent server-configuration attestation.',
                'Availability delay, execution, price tick and dividend intraday cash timing are replay assumptions, not observed latency or fill evidence.',
                'Calendar tail has no bars; it cannot create post-study fills. Receivables payable after the boundary must remain separately accounted for.']})
        return report, rebuilt
    except (AuditError, KeyError, TypeError, ValueError, AttributeError, OSError) as exc:
        if isinstance(exc, AuditError):
            error = {'code': exc.code, 'detail': exc.detail}
        else:
            error = {'code': 'MALFORMED_OR_MISSING_DATA', 'detail': type(exc).__name__}
        report['errors'].append(error)
        report['conditional_replay_data_ready'] = False
        return report, None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--report', type=Path, help='Write deterministic JSON here; otherwise stdout.')
    parser.add_argument('--rebuild-dataset', type=Path,
                        help='Write the verified byte-identical reconstruction to a new path. Existing different files are refused.')
    args = parser.parse_args(argv)
    report, rebuilt = audit_data_dir(args.data_dir)
    if rebuilt is not None and args.rebuild_dataset is not None:
        try:
            target = args.rebuild_dataset
            require(not target.exists() or target.read_bytes() == rebuilt, 'REBUILD_WOULD_OVERWRITE_DIFFERENT_FILE')
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_bytes(rebuilt)
        except (AuditError, OSError) as exc:
            report['status'] = 'BLOCKED'
            report['conditional_replay_data_ready'] = False
            report['errors'].append({'code': exc.code if isinstance(exc, AuditError) else 'REBUILD_WRITE_ERROR',
                                     'detail': exc.detail if isinstance(exc, AuditError) else type(exc).__name__})
    output = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output, encoding='utf-8')
    else:
        print(output, end='')
    return 0 if report['status'] == 'PASS_CONDITIONAL_HISTORICAL_ONLY' else 2


if __name__ == '__main__':
    raise SystemExit(main())
