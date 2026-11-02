"""Bounded multi-asset research. Model fills never establish live profitability."""
from __future__ import annotations

import hashlib
import math
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median, stdev
from typing import Any
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')
UTC = timezone.utc


def stamp(value: str) -> datetime:
    d = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if d.tzinfo is None:
        raise ValueError('TIMEZONE_REQUIRED')
    return d.astimezone(UTC)


def number(x: Any, *, positive: bool = False) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise ValueError('FINITE_NUMBER_REQUIRED')
    y = float(x)
    if not math.isfinite(y) or (positive and y <= 0):
        raise ValueError('FINITE_POSITIVE_NUMBER_REQUIRED')
    return y


def normalize(payloads: list[dict], symbols: list[str], start: datetime, end: datetime) -> tuple[dict, dict]:
    """Reject duplicate/unordered/invalid bars; do not silently impute timestamps."""
    panel: dict[str, list] = {s: [] for s in symbols}
    coverage: dict[str, dict] = {}
    for p in payloads:
        if not isinstance(p.get('bars'), dict):
            raise ValueError('BAR_RESPONSE_REQUIRED')
        for symbol, rows in p['bars'].items():
            if symbol not in panel:
                raise ValueError('UNREGISTERED_SYMBOL')
            last = None
            for r in rows:
                at = stamp(r['timestamp'])
                if last is not None and at <= last:
                    raise ValueError('DUPLICATE_OR_UNORDERED_BAR')
                last = at
                vals = {k: number(r[k], positive=True) for k in ('open', 'high', 'low', 'close')}
                volume = number(r['volume'])
                if volume < 0 or not vals['low'] <= min(vals['open'], vals['close']) <= max(vals['open'], vals['close']) <= vals['high']:
                    raise ValueError('INVALID_OHLCV')
                if start <= at < end:
                    panel[symbol].append(dict(vals, volume=volume, at=at,
                                              known=at + timedelta(hours=1, seconds=60)))
    for s, rows in panel.items():
        if not rows or any(a['at'] >= b['at'] for a, b in zip(rows, rows[1:])):
            raise ValueError('MISSING_OR_OVERLAPPING_SYMBOL')
        coverage[s] = {'bars': len(rows), 'first': rows[0]['at'].isoformat(),
                       'last': rows[-1]['at'].isoformat(), 'zero_volume_bars': sum(r['volume'] == 0 for r in rows),
                       'gaps_gt_1h': sum((b['at']-a['at']).total_seconds() > 3600 for a,b in zip(rows,rows[1:])),
                       'availability': 'ASSUMED_BAR_END_PLUS_60S_NOT_OBSERVED'}
    return panel, coverage


def signal(rows: list[dict], when: datetime) -> dict | None:
    known = [r for r in rows if r['known'] < when]
    if len(known) < 61 or when-known[-1]['known'] > timedelta(hours=96):
        return None
    trailing = known[-61:]
    ret = [math.log(b['close']/a['close']) for a,b in zip(trailing,trailing[1:])]
    vol = stdev(ret)
    if vol <= 1e-10 or max(map(abs,ret)) > .20:
        return None
    score = math.log(trailing[-1]['close']/trailing[-21]['close']) / (vol*math.sqrt(20))
    if score <= 0:
        return None
    return {'score': score, 'vol': vol, 'known': trailing[-1]['known'].isoformat(),
            'capacity_usd': .01*median(r['volume']*r['close'] for r in trailing[-20:])}


def allocation(candidates: list[dict], mode: str) -> dict[str, float]:
    """No cash redistribution after caps; same 20k bankroll in both policies."""
    ordered = sorted(candidates, key=lambda r: (-r['score'], r['symbol']))
    groups = [(ordered[:3], .6)] if mode == 'JOINT' else [
        ([r for r in ordered if r['book']=='equity'][:2], .4),
        ([r for r in ordered if r['book']=='crypto'][:1], .2)]
    out = {}
    for selected, budget in groups:
        total = sum(1/r['vol'] for r in selected)
        for r in selected:
            out[r['symbol']] = min(.2, budget/r['vol']/total)
    crypto = sum(out.get(r['symbol'], 0) for r in candidates if r['book']=='crypto')
    if crypto > .2:
        for r in candidates:
            if r['book']=='crypto' and r['symbol'] in out:
                out[r['symbol']] *= .2/crypto
    return out


def replay(panel: dict, mode: str, stress: bool = False) -> dict:
    if mode not in ('JOINT','SLEEVES','CASH'):
        raise ValueError('POLICY_REQUIRED')
    cash = 20000.
    by_at = {s:{r['at']:r for r in rows} for s,rows in panel.items()}
    known_times = {s:[r['known'] for r in rows] for s,rows in panel.items()}
    trades, curve, missing = [], [], []
    peak, dd, max_gross, max_crypto = cash, 0., 0., 0.
    for i in range(365):
        day = datetime(2025,1,1,tzinfo=NY)+timedelta(days=i)
        when = day.replace(hour=10).astimezone(UTC)
        exit_at = day.replace(hour=12).astimezone(UTC)
        cash -= 2 if stress else 1
        if cash <= 0:
            raise ValueError('INSOLVENCY')
        candidates = []
        if mode != 'CASH':
            for s, rows in panel.items():
                # Equity only at the scheduled clock in an actual returned session.
                # Missing future exit data NEVER deletes an entry.
                if when not in by_at[s]:
                    continue
                cut = bisect_left(known_times[s],when)
                sig = signal(rows[max(0,cut-61):cut],when)
                if sig:
                    candidates.append(dict(sig,symbol=s,book='crypto' if '/' in s else 'equity'))
        weights = allocation(candidates, mode) if candidates else {}
        starting = cash
        positions = []
        for r in sorted(candidates,key=lambda r:r['symbol']):
            s,book=r['symbol'],r['book']
            px=by_at[s][when]['open']
            rate=(.0035 if book=='crypto' else .0005)*(2 if stress else 1)
            notional=min(starting*weights.get(s,0),r['capacity_usd'],cash/(1+rate))
            lot=1e-8 if book=='crypto' else 1.
            qty=math.floor(notional/px/lot)*lot
            if qty*px < 1:
                continue
            debit=qty*px*(1+rate)
            cash-=debit
            positions.append((r,qty,px,rate,debit))
        invested=sum(q*p for r,q,p,rate,debit in positions)
        crypto=sum(q*p for r,q,p,rate,debit in positions if r['book']=='crypto')
        max_gross=max(max_gross,invested/starting)
        max_crypto=max(max_crypto,crypto/starting)
        if cash < -1e-7 or invested > .6*starting+1e-7 or crypto > .2*starting+1e-7:
            raise ValueError('CAPITAL_LIMIT')
        for r,qty,entry,rate,debit in positions:
            s=r['symbol']
            if exit_at not in by_at[s]:
                missing.append({'symbol':s,'entry':when.isoformat(),'missing_exit':exit_at.isoformat()})
                continue
            exit_px=by_at[s][exit_at]['open']
            credit=qty*exit_px*(1-rate)
            cash+=credit
            trades.append({'symbol':s,'book':r['book'],'entry_at':when.isoformat(),'exit_at':exit_at.isoformat(),
                'signal_known_at':r['known'],'qty':qty,'entry_price':entry,'exit_price':exit_px,
                'debit_usd':debit,'credit_usd':credit,'net_usd':credit-debit,
                'modeled_cost_usd':qty*(entry+exit_px)*rate,'fill_nature':'MODELED',
                'observed_trailing_capacity_usd':r['capacity_usd']})
        if missing:
            raise ValueError('MISSING_EXIT_AFTER_ENTRY:'+str(missing))
        peak=max(peak,cash)
        dd=max(dd,1-cash/peak)
        curve.append({'day':day.date().isoformat(),'equity':cash,'cash':cash,'positions':0})
    fixed=365*(2 if stress else 1)
    residual=cash-20000-(sum(t['net_usd'] for t in trades)-fixed)
    if abs(residual)>1e-7:
        raise ValueError('CASH_RECONCILIATION')
    return {'mode':mode,'stress':stress,'initial_usd':20000,'terminal_usd':cash,'net_usd':cash-20000,
            'fixed_cost_usd':fixed,'modeled_variable_cost_usd':sum(t['modeled_cost_usd'] for t in trades),
            'trades':trades,'curve':curve,'reconciliation_error_usd':residual,
            'max_entry_gross_fraction':max_gross,'max_entry_crypto_fraction':max_crypto,
            'close_grid_drawdown':dd,'intrabar_drawdown_verified':False,
            'max_holding_hours':max([(stamp(t['exit_at'])-stamp(t['entry_at'])).total_seconds()/3600 for t in trades],default=0),
            'execution_allowed':False,'liveApproved':False,'level8_accredited':False}


def calibrate_fills(bundle: dict) -> dict:
    """Observed shortfall, not strategy alpha. Input provenance is declared, not authenticated.

    Explicit fees required. Do not combine paper/live, class, side or size domains.
    """
    if bundle.get('schema') != 'HARPOON_OBSERVED_FILLS_1' or bundle.get('mode') not in ('LIVE','PAPER'):
        raise ValueError('EXPLICIT_FILL_NATURE_REQUIRED')
    groups: dict[str,list] = defaultdict(list)
    seen=set()
    available=stamp(bundle['available_at'])
    for f in bundle['fills']:
        if not isinstance(f.get('fill_id'), str) or not f['fill_id'] or f['fill_id'] in seen:
            raise ValueError('UNIQUE_FILL_ID_REQUIRED')
        seen.add(f['fill_id'])
        if not f.get('order_id') or not f.get('fee_receipt_id') or f['side'] not in ('buy','sell') or f['book'] not in ('equity','crypto'):
            raise ValueError('FILL_IDENTITY_FEE_OR_SIDE')
        decision, quote, received, fill = (stamp(f[k]) for k in ('decision_at','quote_at','quote_received_at','filled_at'))
        if f.get('mode',bundle['mode']) != bundle['mode']:
            raise ValueError('MIXED_PAPER_LIVE_FILLS')
        if fill > available:
            raise ValueError('CALIBRATION_BEFORE_FILL')
        if not quote <= received <= decision <= fill or (decision-quote).total_seconds()>5:
            raise ValueError('NONCAUSAL_OR_STALE_DECISION_QUOTE')
        qty,price,bid,ask=(number(f[k],positive=True) for k in ('qty','price','bid','ask'))
        fee=number(f['fee_usd'])
        if ask < bid or fee < 0:
            raise ValueError('CROSSED_QUOTE_OR_FEE')
        mid=(bid+ask)/2
        direction=1 if f['side']=='buy' else -1
        notional=qty*mid
        shortfall=direction*(price-mid)*qty+fee
        group=bundle['mode']+':'+f['book']+':'+f['side']
        groups[group].append({'shortfall':shortfall,'notional':notional,'bps':10000*shortfall/notional,
                              'order':f['order_id'],'day':fill.date().isoformat(),
                              'latency_s':(fill-decision).total_seconds()})
    out={}
    for key,rows in sorted(groups.items()):
        values=sorted(r['bps'] for r in rows)
        # Empirical nearest-rank, not an upper confidence bound or IID claim.
        orders=len({r['order'] for r in rows}); days=len({r['day'] for r in rows})
        enough=len(rows)>=30 and orders>=20 and days>=10
        out[key]={'fills':len(rows),'distinct_orders':orders,'days':days,
          'weighted_shortfall_bps':10000*sum(r['shortfall'] for r in rows)/sum(r['notional'] for r in rows),
          'empirical_p95_bps':values[math.ceil(.95*len(values))-1],
          'conservative_bps_floor_zero':max(0,values[math.ceil(.95*len(values))-1]),
          'fill_notional_range_usd':[min(r['notional'] for r in rows),max(r['notional'] for r in rows)],
          'enough_observations':enough,'live_cost_calibration_ready':enough and bundle['mode']=='LIVE'}
    return {'schema':'HARPOON_FILL_CALIBRATION_1','groups':out,'mode':bundle['mode'],
            'source_independently_authenticated':False,'account_reconciled':False,
            'available_at':bundle['available_at'],
            'input_sha256':hashlib.sha256(__import__('json').dumps(bundle,sort_keys=True).encode()).hexdigest(),
            'financial_acceptance_allowed':False,'execution_allowed':False,
            'limitations':['NO_UNFILLED_ORDER_OPPORTUNITY_COST','NO_MARKOUT_WITHOUT_POST_FILL_QUOTES',
                           'EMPIRICAL_NOT_CONFIDENCE_BOUND','NO_EXTRAPOLATION_OUTSIDE_OBSERVED_SIZE_RANGE']}
