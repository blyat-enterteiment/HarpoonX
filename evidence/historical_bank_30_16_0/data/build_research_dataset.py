#!/usr/bin/env python3
"""Rebuild a historical bar dataset from retained receipts. No financial trials."""
import collections
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
AUDIT = ROOT.parent / 'data_audit'
NY = ZoneInfo('America/New_York')
UTC = dt.timezone.utc
START = '2022-01-01'
END = '2024-08-31'
SYMBOLS = ['AAPL', 'MSFT', 'SPY', 'XLK']
MODELED_AVAILABILITY_DELAY_MS = 1000

def read(p):
    return json.loads(p.read_text())

def write(name, value, compact=False):
    p = ROOT / name
    p.write_text(json.dumps(value, ensure_ascii=False, indent=None if compact else 2,
                            separators=(',', ':') if compact else None, allow_nan=False) + '\n')
    return p

def reference(p):
    body = p.read_bytes()
    return {'name': str(p.relative_to(ROOT)), 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}

def parse_time(text, tz=UTC):
    value = dt.datetime.fromisoformat(text.replace('Z', '+00:00'))
    if value.tzinfo is None:
        value = value.replace(tzinfo=tz)
    return round(value.timestamp() * 1000)

def unwrap(receipt):
    response = receipt['response']
    if response.get('isError'):
        raise ValueError('PROVIDER_ERROR: ' + str(receipt.get('request')))
    body = response.get('structuredContent')
    if body is None:
        body = json.loads(next(x['text'] for x in response['content'] if x.get('type') == 'text'))
    if isinstance(body, dict) and isinstance(body.get('result'), str):
        return json.loads(body['result'])
    return body

def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

plan = read(ROOT / 'request_plan.json')
assert plan['universe'] == SYMBOLS
assert plan['request_count'] == 128 and len(plan['requests']) == 128
calendar_source = AUDIT / 'raw/calendar_2022_2024.json'
calendar_target = ROOT / 'raw/calendar_2022-01_2024-09-06.json'
if calendar_target.exists():
    assert calendar_target.read_bytes() == calendar_source.read_bytes(), 'CALENDAR_SOURCE_CHANGED'
else:
    calendar_target.write_bytes(calendar_source.read_bytes())
calendar_body = unwrap(read(calendar_target))
sessions = [{'date': x['date'], 'open': parse_time(x['open'], NY), 'close': parse_time(x['close'], NY)}
            for x in calendar_body['calendar']]
assert len({x['date'] for x in sessions}) == len(sessions)
assert all(s['open'] < s['close'] for s in sessions)
assert all(a['close'] < b['open'] for a, b in zip(sessions, sessions[1:]))
session_by_date = {s['date']: s for s in sessions}
study_sessions = [s for s in sessions if START <= s['date'] <= END]
deadline_sessions = [s for s in sessions if s['date'] > END]
expected = {t for s in study_sessions for t in range(s['open'], s['close'], 300000)}
expected_by_month = collections.defaultdict(set)
for s in study_sessions:
    expected_by_month[s['date'][:7]].update(range(s['open'], s['close'], 300000))
assert len(study_sessions) == 669 and len(expected) == 52038

sources = [reference(calendar_target)]
series_rows = {s: [] for s in SYMBOLS}
quality = []
issues = []
source_record_total = 0
for request in plan['requests']:
    source = ROOT / 'raw' / (request['id'] + '.json')
    receipt = read(source)
    assert receipt['request'] == request, 'CAPTURE_REQUEST_MISMATCH: ' + request['id']
    body = unwrap(receipt)
    symbol = request['args']['symbol']
    assert set(body['bars']) == {symbol}, 'WRONG_RESPONSE_UNIVERSE'
    provider_request = body['request']
    assert provider_request['symbols'] == [symbol], 'WRONG_PROVIDER_SYMBOL'
    for key in ['timeframe', 'start', 'end', 'limit', 'feed', 'sort', 'currency', 'asof', 'tz']:
        assert provider_request[key] == request['args'][key], 'WRONG_PROVIDER_PARAMETER: ' + key
    rows = body['bars'][symbol]
    assert body['counts']['records'] == len(rows)
    source_record_total += len(rows)
    stamps = []
    good = []
    invalid = []
    month = request['id'].split('_', 1)[1]
    month_expected = expected_by_month[month]
    for row in rows:
        assert row['symbol'] == symbol
        t = parse_time(row['timestamp'])
        stamps.append(t)
        if t not in month_expected:
            continue
        values = [row[k] for k in ['open', 'high', 'low', 'close', 'volume']]
        o, h, l, c, v = values
        if (not all(finite(x) for x in values) or min(o, h, l, c) <= 0 or v < 0
                or l > min(o, c) + 1e-10 or h + 1e-10 < max(o, c) or l > h):
            invalid.append(t)
            continue
        bar = {'t': t, 'end': t + 300000, 'availableAt': t + 300000 + MODELED_AVAILABILITY_DELAY_MS,
               'o': o, 'h': h, 'l': l, 'c': c, 'v': v}
        if row.get('vwap') is not None:
            assert finite(row['vwap']), 'INVALID_VWAP'
            bar['vw'] = row['vwap']
        good.append(bar)
    counter = collections.Counter(stamps)
    missing = sorted(month_expected - set(stamps))
    duplicate = [t for t, n in counter.items() if n > 1 and t in month_expected]
    zero_volume = sum(x['v'] == 0 for x in good)
    item = {'id': request['id'], 'source': reference(source), 'raw_records': len(rows),
            'expected_regular_bars': len(month_expected), 'valid_regular_bars': len(good),
            'outside_regular_grid_records': sum(t not in month_expected for t in stamps),
            'missing_regular_bars': len(missing), 'missing_timestamps_ms': missing,
            'duplicate_regular_timestamps': duplicate, 'invalid_regular_timestamps': invalid,
            'zero_volume_regular_bars': zero_volume, 'page_limit_reached': len(rows) >= request['args']['limit'],
            'api_next_page_token_exposed': False,
            'coverage_basis': 'Exact fixed calendar timestamp grid, not row count below limit.'}
    quality.append(item)
    if missing or duplicate or invalid:
        issues.append({'id': request['id'], 'causes': {k: item[k] for k in ['missing_regular_bars', 'duplicate_regular_timestamps', 'invalid_regular_timestamps']}})
    sources.append(item['source'])
    series_rows[symbol].extend(good)

ca_source = ROOT / 'raw/corporate_actions_2021-12_2024-10.json'
ca_body = unwrap(read(ca_source))
sources.append(reference(ca_source))
action_inventory = ca_body['announcements']
dividends, splits, exclusions, action_issues = [], [], [], []
for kind, events in action_inventory.items():
    for event in events:
        if kind == 'cash_dividends':
            symbol, ex_date = event['symbol'], event.get('ex_date')
            if symbol not in SYMBOLS:
                action_issues.append({'id': event.get('id'), 'reason': 'UNEXPECTED_DIVIDEND_SYMBOL'})
                continue
            if ex_date is None:
                action_issues.append({'id': event.get('id'), 'reason': 'MISSING_EX_DATE'})
                continue
            if not START <= ex_date <= END:
                exclusions.append({'id': event['id'], 'kind': kind, 'symbol': symbol, 'ex_date': ex_date,
                    'reason': 'EX_DATE_OUTSIDE_STUDY; original receipt retained. Initial account positions are not supplied by this dataset.'})
                continue
            if ex_date not in session_by_date:
                action_issues.append({'id': event['id'], 'reason': 'EX_DATE_NOT_IN_SESSION_CALENDAR'})
                continue
            amount = event.get('rate')
            if not finite(amount) or amount < 0:
                action_issues.append({'id': event['id'], 'reason': 'MISSING_OR_INVALID_CASH_RATE'})
                continue
            ex_at = session_by_date[ex_date]['open']
            payable_date = event.get('payable_date')
            payable_at = parse_time(payable_date + 'T16:00:00', NY) if payable_date is not None else None
            if payable_at is not None and payable_at < ex_at:
                action_issues.append({'id': event['id'], 'reason': 'PAYABLE_BEFORE_EX_DATE'})
                continue
            if event.get('due_bill_on_date') is not None or event.get('due_bill_off_date') is not None:
                action_issues.append({'id': event['id'], 'reason': 'DUE_BILL_RULE_NOT_IMPLEMENTED'})
                continue
            dividends.append({'id': event['id'], 'symbol': symbol, 'exAt': ex_at,
                              'payableAt': payable_at, 'amountPerShare': amount})
        elif kind in ('forward_splits', 'reverse_splits'):
            symbol, ex_date = event.get('symbol'), event.get('ex_date')
            if symbol not in SYMBOLS or ex_date not in session_by_date:
                action_issues.append({'id': event.get('id'), 'reason': 'UNRESOLVED_SPLIT_IDENTITY_OR_EFFECTIVE_DATE'})
                continue
            if not START <= ex_date <= END:
                exclusions.append({'id': event.get('id'), 'kind': kind, 'symbol': symbol,
                                   'ex_date': ex_date, 'reason': 'EX_DATE_OUTSIDE_STUDY'})
                continue
            new, old = event.get('new_rate'), event.get('old_rate')
            if not finite(new) or not finite(old) or new <= 0 or old <= 0:
                action_issues.append({'id': event.get('id'), 'reason': 'INVALID_SPLIT_RATIO'})
                continue
            splits.append({'symbol': symbol, 'at': session_by_date[ex_date]['open'], 'ratio': new / old})
        elif kind == 'cash_mergers' and event.get('acquirer_symbol') in SYMBOLS and event.get('acquiree_symbol') not in SYMBOLS:
            exclusions.append({'id': event.get('id'), 'kind': kind, 'acquirer_symbol': event['acquirer_symbol'],
                'acquiree_symbol': event['acquiree_symbol'], 'effective_date': event.get('effective_date'),
                'reason': 'Cash consideration is per acquiree share. The observed event does not convert units of the acquirer held in this universe.'})
        else:
            action_issues.append({'id': event.get('id'), 'kind': kind, 'reason': 'UNSUPPORTED_OBSERVED_ACTION'})

series = []
for symbol in SYMBOLS:
    rows = sorted(series_rows[symbol], key=lambda b: b['t'])
    if len(rows) != len(expected) or {b['t'] for b in rows} != expected:
        issues.append({'symbol': symbol, 'reason': 'FINAL_REGULAR_GRID_NOT_EXACT'})
    series.append({'symbol': symbol, 'root': symbol, 'pointValue': 1, 'tick': 0.01, 'bars': rows})
dividends.sort(key=lambda x: (x['exAt'], x['symbol'], x['id']))
splits.sort(key=lambda x: (x['at'], x['symbol']))
assert len({x['id'] for x in dividends}) == len(dividends), 'DUPLICATE_DIVIDEND_ID'

source_manifest = {'schema': 'HARPOON_HISTORICAL_RAW_MANIFEST_1', 'algorithm': 'SHA-256',
    'files': sorted(sources, key=lambda x: x['name']), 'raw_file_count': len(sources),
    'raw_bytes': sum(x['bytes'] for x in sources),
    'source_serialization': plan['source_serialization'],
    'upstream_authenticity_independently_certified': False}
write('source_manifest.json', source_manifest)
quality_report = {'schema': 'HARPOON_HISTORICAL_COVERAGE_1', 'calendar_study_sessions': len(study_sessions),
    'deadline_only_sessions': deadline_sessions, 'expected_regular_bars_per_symbol': len(expected),
    'expected_regular_bars_total': len(expected) * len(SYMBOLS), 'raw_bar_records': source_record_total,
    'retained_regular_bars_total': sum(len(s['bars']) for s in series),
    'chunks': quality, 'bar_issues': issues, 'action_issues': action_issues,
    'grid_complete': not issues, 'zero_volume_regular_bars': sum(x['zero_volume_regular_bars'] for x in quality),
    'financial_calculation_executed': False}
write('quality.json', quality_report)
metadata = {'schema': 'HARPOON_HISTORICAL_RESEARCH_METADATA_1',
    'nature': 'HISTORICAL_RETROSPECTIVE_CONDITIONAL', 'execution_nature': 'MODELED_OHLCV',
    'universe': SYMBOLS, 'period': [START, END], 'partition': plan['partition'],
    'calendar_study_sessions': len(study_sessions), 'calendar_deadline_only_sessions': len(deadline_sessions),
    'entries_after_study_end_allowed': False,
    'bar_granularity_seconds': 300,
    'bar_time_semantics': {'t': 'Historical provider bar start', 'end': 't + 300000ms by timeframe',
        'availableAt': 'end + 1000ms, explicit MODEL assumption; not an observed receipt or original publication timestamp',
        'original_market_data_receipt_timestamp': None, 'observed_latency_ms': None},
    'price_adjustment': plan['adjustment'],
    'price_tick': {'value': 0.01, 'nature': 'Replay configuration inherited for these USD stocks/ETFs; not measured quote granularity'},
    'corporate_actions': {'source': reference(ca_source), 'date_query_semantics': 'process_date',
        'observed_counts_by_class': {k: len(v) for k, v in action_inventory.items()},
        'cash_dividends_in_study': len(dividends), 'split_events_in_study': len(splits),
        'observed_events_not_applied': exclusions, 'unresolved_observed_events': action_issues,
        'completeness': None,
        'completeness_reason': 'A bounded process-date response and connector without pagination/data_quality/ex_date controls do not certify all possible exceptional actions.',
        'empty_split_inventory_means': 'No applicable split returned in this request; not certified absence of all splits.',
        'ex_at_convention': 'Open of the calendar session on observed ex_date; accounting convention, not original announcement time.',
        'payable_at_convention': '16:00 America/New_York on observed payable_date; MODELED conservative intraday cash availability, not observed broker posting. null means no payment date supplied.',
        'cash_vs_receivable': 'Unpaid entitled dividends remain receivables; a payable date beyond study end must not erase a receivable or make it reinvestable early.',
        'original_announcement_known_at': None,
        'signal_use': 'These records support accounting only; current retrieval does not establish ex-ante signal availability.'},
    'limitations': [
        'Raw historical bars, calendar, and reported actions do not prove realized profitability, original receipt timing, executable bid/ask or actual fills.',
        'Reserved 2024 prices precede strategy design. This is a retrospective held-out evaluation within a fixed study, not live forward validation.',
        'The fixed four-asset scope is not a point-in-time whole-market or delisting-complete universe.',
        'Five-minute OHLCV cannot resolve an intrabar stop/target ordering; execution rules and stress costs remain model assumptions.',
        'Corporate action completeness remains unknown; a conditional replay must carry this limitation and cannot be promoted to a strict certified dataset.',
        'The final four calendar sessions supply deadlines only. They have no bars and cannot manufacture fills after the study boundary.',
    ],
    'status': 'READY_FOR_CONDITIONAL_HISTORICAL_REPLAY' if not issues and not action_issues else 'BLOCKED_DATA_ISSUES',
    'no_strategy_fit_or_pnl_executed': True,
}
write('metadata.json', metadata)
if issues or action_issues:
    raise SystemExit('Dataset not emitted: see quality.json for unhandled known data issues.')
dataset = {'schema': 'HARPOON-ULTIMATE-DATA-1', 'kind': 'ALPACA_PROXY',
    'provenance': {'source': 'ALPACA_TOOL_HISTORICAL_SIP_5MIN_RECONSTRUCTED_2022_2024', 'feed': 'SIP',
                   'files': [{'name': x['name'], 'sha256': x['sha256']} for x in source_manifest['files']],
                   'execution': 'MODELED_OHLCV'},
    'sessions': sessions, 'splitEvents': splits, 'cashDividends': dividends, 'series': series}
write('research_dataset.json', dataset, compact=True)
manifest = {'schema': 'HARPOON_HISTORICAL_DERIVED_MANIFEST_1', 'algorithm': 'SHA-256',
    'files': [reference(ROOT / name) for name in ['request_plan.json', 'capture_receipt.json',
        'source_manifest.json', 'quality.json', 'metadata.json', 'build_research_dataset.py', 'research_dataset.json']],
    'financial_calculation_executed': False}
write('manifest.json', manifest)
print(json.dumps({'status': metadata['status'], 'dataset': str(ROOT / 'research_dataset.json'),
    'dataset_sha256': reference(ROOT / 'research_dataset.json')['sha256'],
    'raw_files': len(sources), 'raw_records': source_record_total,
    'regular_bars': sum(len(s['bars']) for s in series), 'sessions': len(study_sessions),
    'deadline_sessions': len(deadline_sessions), 'cash_dividends': len(dividends),
    'split_events': len(splits), 'bar_issues': len(issues), 'action_issues': len(action_issues)}, indent=2))
