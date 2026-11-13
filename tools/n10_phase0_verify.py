"""Independent Decimal checks and bounded microbenchmark for N10 Phase0."""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from pathlib import Path

from quant.harpoon_quant.n10_options import Candidate, Contract, Guard, Leg, Portfolio, Quote, Right, Scenario, evaluate, select

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / 'research/n10/phase0_protocol.json'


def check_hashes() -> dict[str, str]:
    protocol = json.loads(PROTOCOL.read_text())
    source = ROOT / 'quant/harpoon_quant/n10_options.py'
    tests = ROOT / 'tests/test_n10_options.py'
    hashes = {'code_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'test_sha256': hashlib.sha256(tests.read_bytes()).hexdigest()}
    assert hashes['code_sha256'] == protocol['source_code_sha256_preregistered']
    assert hashes['test_sha256'] == protocol['test_source_sha256_preregistered']
    return hashes


def check_arithmetic() -> dict[str, str]:
    # Independent arithmetic: $0.15 ask + $0.01 slippage; $0.65 fee on
    # each side, 100x multiplier => a maximum paid loss of $17.30.
    debit = (D('0.15') + D('0.01')) * 100 + D('0.65')
    call_loss = debit + D('0.65')
    assert call_loss == D('17.30')
    # Bull put credit: short strike 100 bid .30 less .01 slippage;
    # long strike 99.75 ask .14 plus .01 slippage.
    credit = (D('0.30') - D('0.01') - D('0.14') - D('0.01')) * 100 - D('1.30')
    vertical_loss = D('0.25') * 100 - credit + D('1.30')
    assert credit == D('12.70') and vertical_loss == D('13.60')
    return {'independent_call_max_loss_usd': str(call_loss),
            'independent_bull_put_max_loss_usd': str(vertical_loss)}


def benchmark() -> dict[str, object]:
    now = datetime(2026, 11, 13, 15, 0, tzinfo=timezone.utc)
    expiry = now + timedelta(days=10)
    exit_at = now + timedelta(hours=48)
    q = Quote(Contract('XSP', Right.CALL, D('102'), expiry), D('0.10'), D('0.15'), 10, 10, now)
    candidate = Candidate('SYNTHETIC_CALL_FIXTURE', (Leg(q, 1),))
    scenarios = (Scenario(0.7, 104.0, 0.2, now), Scenario(0.3, 99, 0.25, now))
    cash = Portfolio(D('20000'), D('20000'), D('20000'), D('20000'), D(0), D(0), now)
    start = time.perf_counter()
    count = 2000
    for _ in range(count):
        label, result = select([candidate], scenarios, decision_at=now, exit_at=exit_at, guard=Guard(), portfolio=cash)
        assert label == candidate.label and result[0].admitted
    millis = (time.perf_counter() - start) * 1000
    return {'number_of_pure_selections': count, 'elapsed_ms': round(millis, 3),
            'status': 'ENGINEERING_FIXTURE_NOT_PROFIT'}


if __name__ == '__main__':
    print(json.dumps({**check_hashes(), **check_arithmetic(), **benchmark()}, indent=2, sort_keys=True))
