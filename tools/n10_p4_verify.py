"""No-market independent Decimal checks and reproducible pure-function benchmark."""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from pathlib import Path

from quant.harpoon_quant.n10_vertical_bounds import (
    EuropeanQuote, Funding, PhysicalScenario, Side, Vertical, assess, choose,
    quote_band,
)

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check() -> dict[str, object]:
    proto = json.loads((ROOT / 'research/n10/p4_protocol.json').read_text())
    hashes: dict[str, str] = {}
    for path, expected in proto['source_sha256'].items():
        current = sha256(ROOT / path)
        if current != expected:
            raise AssertionError(f'source integrity: {path}')
        hashes[path] = current
    now = datetime(2026, 11, 13, 15, 0, tzinfo=timezone.utc)
    expiry = now + timedelta(days=2)
    call = Vertical(
        EuropeanQuote('XSP', Side.CALL, D('101'), D('.15'), D('.18'), expiry, now),
        EuropeanQuote('XSP', Side.CALL, D('102'), D('.10'), D('.12'), expiry, now),
    )
    # Completely independent width/credit/debit check, without use of the engine.
    high = D('.18') - D('.10')
    low = D('.15') - D('.12')
    assert high == D('.08') and low == D('.03')
    gross_debit = high * D('100')
    friction = D('.01') * D('100') * 2
    fees = D('.65') * 4
    total_loss = gross_debit + friction + fees
    assert total_loss == D('12.60')
    b = quote_band(call, decision_at=now)
    assert abs(b.low - float(low)) < 1e-12
    assert abs(b.high - float(high)) < 1e-12
    funding = Funding(D('20000'), D('20000'), D('0'), D('0'), now)
    prediction = (
        PhysicalScenario(103, .70, now),
        PhysicalScenario(100, .30, now),
    )
    target = assess(call, prediction, decision_at=now, funding=funding)
    assert target.admitted and target.max_loss_usd == total_loss
    start = time.perf_counter()
    for _ in range(2000):
        selection = choose([assess(call, prediction, decision_at=now, funding=funding)])
        if selection != target.label:
            raise AssertionError('nondeterministic P-vs-Q choice')
    ms = (time.perf_counter() - start) * 1000
    return {
        'schema': 'HARPOONX_N10_P4_INDEPENDENT_ENGINEERING_AUDIT_1',
        'source_sha256': hashes,
        'independent_decimal_credit_spread_bid_usd': str(low * 100),
        'independent_decimal_debit_spread_ask_usd': str(gross_debit),
        'independent_decimal_maximum_contract_loss_usd': str(total_loss),
        'synthetic_positive_fixture_is_not_profit': True,
        'benchmark_assessments': 2000,
        'benchmark_elapsed_ms': round(ms, 3),
        'market_accounts': 0,
        'broker_orders': 0,
        'status': 'PASS_ENGINEERING_ONLY',
    }


if __name__ == '__main__':
    print(json.dumps(check(), indent=2, sort_keys=True))
