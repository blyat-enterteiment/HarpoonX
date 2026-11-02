"""Swing research with causal breakout/gap/retest signals and one funded account.

OHLC executions are deliberately modeled. No API writes or live promotion.
"""
from __future__ import annotations
import math
from bisect import bisect_left
from datetime import datetime,timedelta,timezone
from statistics import median
from zoneinfo import ZoneInfo
from typing import Any
from .multiasset import stamp,number

NY=ZoneInfo('America/New_York'); UTC=timezone.utc
TECH={'AAPL','MSFT','QQQ','XLK'}
RULES={'BREAKOUT','GAP','RETEST','CASH'}


def deadline(when:datetime,book:str,sessions:dict[str,dict],end:datetime)->datetime|None:
    if book=='crypto':
        out=when+timedelta(hours=48)
        return out if out<end else None
    choices=[]
    for i in range(1,5):
        day=(when.astimezone(NY)+timedelta(days=i)).date().isoformat()
        if day not in sessions:continue
        target=datetime.fromisoformat(day+'T12:00:00').replace(tzinfo=NY).astimezone(UTC)
        close=sessions[day]['close']
        hours=(target-when).total_seconds()/3600
        if 24<=hours<=72 and target<close and target<end:
            choices.append(target)
    return min(choices,key=lambda t:(abs((t-when).total_seconds()/3600-48),t)) if choices else None


def daily_features(prior:list[dict])->dict|None:
    if len(prior)<61:return None
    p=prior[-61:]
    if any(abs(math.log(b['close']/a['close']))>.20 for a,b in zip(p,p[1:])):return None
    tr=[max(b['high']-b['low'],abs(b['high']-a['close']),abs(b['low']-a['close'])) for a,b in zip(p,p[1:])]
    atr=sum(tr[-14:])/14
    if atr<=0:return None
    return {'atr':atr,'sma':sum(r['close'] for r in p[-50:])/50,
            'level':max(r['high'] for r in p[-21:-1]),'volmed':median(r['volume'] for r in p[-21:-1])}


def candidate(symbol:str,rule:str,when:datetime,daily:list[dict],hours:list[dict],entry:float,
              session_open:float|None,rate:float)->dict|None:
    prior=[r for r in daily if r['known']<when]
    known=[r for r in hours if r['known']<when]
    f=daily_features(prior)
    if f is None or len(known)<20:return None
    last,bar=prior[-1],known[-1]
    if when-bar['known']>timedelta(hours=30):return None
    # A current session's actually observed confirmation, not yesterday's last bar.
    if '/' not in symbol and bar['at'].astimezone(NY).date()!=when.astimezone(NY).date():return None
    if last['close']<=f['sma']:return None
    level=f['level'];atr=f['atr']
    def broke(rows):
        g=daily_features(rows)
        return bool(g and rows[-1]['close']>g['level'] and rows[-1]['volume']>=1.2*g['volmed'] and rows[-1]['close']>g['sma'])
    if rule=='BREAKOUT':
        if not broke(prior) or bar['close']<=level:return None
    elif rule=='GAP':
        if '/' in symbol or session_open is None:return None
        gap=(session_open-last['close'])/atr
        if not .5<=gap<=2 or bar['close']<=max(session_open,last['high']):return None
        level=session_open
    elif rule=='RETEST':
        setup=None
        for back in range(5):
            rows=prior[:len(prior)-back] if back else prior
            if broke(rows):setup=daily_features(rows);break
        if setup is None:return None
        level,atr=setup['level'],setup['atr']
        if bar['low']>level+.25*atr or bar['close']<=level:return None
    else:raise ValueError('REGISTERED_RULE_REQUIRED')
    if entry>bar['close']+.25*atr:return None
    if rule!='GAP' and entry>level+atr:return None
    if 2*atr/entry<3*(2*rate):return None
    return {'symbol':symbol,'atr':atr,'score':(last['close']-f['sma'])/atr,
            'stop':entry-2*atr,'target':entry+3*atr,'level':level,
            'signal_known_at':max(bar['known'],last['known']).isoformat(),
            'capacity':.01*median(r['close']*r['volume'] for r in known[-20:]),
            'book':'crypto' if '/' in symbol else 'equity'}


def normalize_daily(payloads:list[dict],sessions:dict)->dict:
    out={}
    for payload in payloads:
        for s,rows in payload['bars'].items():
            result=[]
            for row in rows:
                at=stamp(row['timestamp']);day=at.date().isoformat()
                if '/' in s:known=at+timedelta(days=1,seconds=60)
                else:
                    close=sessions.get(day,{}).get('close',datetime.fromisoformat(day+'T16:00:00').replace(tzinfo=NY).astimezone(UTC))
                    known=close+timedelta(seconds=60)
                vals={k:number(row[k],positive=True) for k in ('open','high','low','close')}
                if not vals['low']<=min(vals['open'],vals['close'])<=max(vals['open'],vals['close'])<=vals['high']:
                    raise ValueError('DAILY_OHLC')
                result.append(dict(vals,volume=number(row['volume']),at=at,known=known))
            if any(a['at']>=b['at'] for a,b in zip(result,result[1:])):raise ValueError('DAILY_ORDER')
            out[s]=result
    return out


def replay(hourly:dict,daily:dict,sessions:dict,actions:list[dict],rule:str,stress:bool,start:datetime,end:datetime)->dict:
    if rule not in RULES:raise ValueError('REGISTERED_RULE_REQUIRED')
    if set(hourly)!=set(daily):raise ValueError('JOINT_UNIVERSE_MISMATCH')
    lookup={s:{r['at']:r for r in rows} for s,rows in hourly.items()}
    dates={s:[r['known'] for r in rows] for s,rows in hourly.items()}
    daily_dates={s:[r['known'] for r in rows] for s,rows in daily.items()}
    daily_by_date={s:{r['at'].date().isoformat():r for r in rows} for s,rows in daily.items()}
    cash=20000.;positions={};receivables=[];marks={};events=[];trades=[];curve=[];signals=[]
    peak=20000.;drawdown=0.;day_start=20000.;current_day=None;action_days=set();max_gross=0.;max_crypto=0.;max_stop=0.
    rate=lambda s:(.0035 if '/' in s else .0005)*(2 if stress else 1)
    def equity():return cash+sum(p['qty']*marks[s] for s,p in positions.items())+sum(x['amount'] for x in receivables)
    def emit(kind,when,**kw):events.append(dict(kind=kind,at=when.isoformat(),**kw))
    def sell(s,px,at,reason):
        nonlocal cash
        p=positions.pop(s);credit=p['qty']*px*(1-rate(s));cash+=credit
        emit('SELL',at,symbol=s,qty=p['qty'],price=px,fee=p['qty']*px*rate(s),cash_delta=credit)
        trades.append(dict(symbol=s,book=p['book'],qty=p['qty'],entry_at=p['entry_at'],exit_at=at.isoformat(),
            entry_price=p['entry'],exit_price=px,stop_at_entry=p['original_stop'],target_at_entry=p['original_target'],
            planned_exit=p['deadline'].isoformat(),signal_known_at=p['signal_known_at'],
            net_usd=credit-p['debit'],variable_cost_usd=p['entry_fee']+p['qty']*px*rate(s),
            exit_reason=reason,fill_nature='MODELED',holding_hours=(at-stamp(p['entry_at'])).total_seconds()/3600))
    when=start
    while when<end:
        utc_day=when.date().isoformat();local=when.astimezone(NY)
        if utc_day!=current_day:
            current_day=utc_day;day_start=equity();fee=2. if stress else 1.;cash-=fee
            emit('FIXED',when,cash_delta=-fee)
        # Apply actual entitlements only when effective, never use future actions to select entries.
        local_day=local.date().isoformat()
        if local_day not in action_days:
            action_days.add(local_day)
            for a in actions:
                s=a['symbol']
                if a['kind']=='split' and a['date']==local_day and s in positions:
                    p=positions[s];ratio=a['ratio'];p['qty']*=ratio
                    for k in ('entry','stop','target'):p[k]/=ratio
                    marks[s]/=ratio;emit('SPLIT',when,symbol=s,ratio=ratio)
                if a['kind']=='dividend' and a['date']==local_day and s in positions:
                    value=positions[s]['qty']*a['rate'];receivables.append({'id':a['id'],'amount':value,'pay':a['pay']})
                    emit('DIV_EX',when,receipt=a['id'],amount=value)
            for item in list(receivables):
                if item['pay']<=local_day:
                    cash+=item['amount'];receivables.remove(item)
                    emit('DIV_PAY',when,receipt=item['id'],cash_delta=item['amount'])
        bars={s:by[when] for s,by in lookup.items() if when in by}
        # Price observations at opening precede any new entries at that opening.
        for s,r in bars.items():marks[s]=r['open']
        for s,p in list(positions.items()):
            if when>=p['deadline']:
                if s not in bars:raise ValueError('MISSING_DEADLINE_BAR:'+s+':'+when.isoformat())
                sell(s,bars[s]['open'],when,'TIME')
            elif s in bars and bars[s]['open']<=p['stop']:
                effective=max(when,sessions.get(local_day,{}).get('open',when)) if '/' not in s else when
                sell(s,bars[s]['open'],effective,'GAP_STOP')
        if rule!='CASH' and local.hour==12 and equity()>=day_start*.98:
            candidates=[]
            for s,r in bars.items():
                if s in positions:continue
                if '/' not in s and (local_day not in sessions or when>=sessions[local_day]['close']):continue
                until=deadline(when,'crypto' if '/' in s else 'equity',sessions,end)
                if until is None:continue
                cut=bisect_left(dates[s],when);dcut=bisect_left(daily_dates[s],when)
                session_open=daily_by_date[s].get(local_day,{}).get('open') if '/' not in s else None
                c=candidate(s,rule,when,daily[s][max(0,dcut-66):dcut],hourly[s][max(0,cut-50):cut],r['open'],session_open,rate(s))
                if c and c['stop']>0:candidates.append(dict(c,deadline=until,entry=r['open']))
            for c in sorted(candidates,key=lambda c:(-c['score'],c['symbol'])):
                if len(positions)>=3:break
                s=c['symbol'];px=c['entry'];eq=equity()
                gross=sum(p['qty']*marks[k] for k,p in positions.items())
                crypto=sum(p['qty']*marks[k] for k,p in positions.items() if p['book']=='crypto')
                tech=sum(p['qty']*marks[k] for k,p in positions.items() if k in TECH)
                risk=sum(max(0,marks[k]-p['stop'])*p['qty'] for k,p in positions.items())
                r=rate(s);distance=(px-c['stop'])/px
                budget=min(.2*eq/(1+.2*r),(.6*eq-gross)/(1+.6*r),c['capacity'],max(0,cash-100)/(1+r),
                           .0035*eq/(distance+.0035*r),max(0,.01*eq-risk)/(distance+.01*r))
                if c['book']=='crypto':budget=min(budget,(.2*eq-crypto)/(1+.2*r))
                if s in TECH:budget=min(budget,(.3*eq-tech)/(1+.3*r))
                lot=1e-8 if c['book']=='crypto' else 1.
                qty=math.floor(max(0,budget)/px/lot)*lot
                if qty*px<1:continue
                fee=qty*px*rate(s);debit=qty*px+fee;cash-=debit
                p=dict(c,qty=qty,debit=debit,entry_fee=fee,entry_at=when.isoformat(),original_stop=c['stop'],original_target=c['target'])
                positions[s]=p;emit('BUY',when,symbol=s,qty=qty,price=px,fee=fee,cash_delta=-debit)
                signals.append({k:(v.isoformat() if isinstance(v,datetime) else v) for k,v in c.items()})
                # Limits are certificates at entry. Overnight gaps can exceed these levels later.
                after=equity();g=sum(p['qty']*marks[k] for k,p in positions.items())/after
                cr=sum(p['qty']*marks[k] for k,p in positions.items() if p['book']=='crypto')/after
                risk_after=sum(max(0,marks[k]-p['stop'])*p['qty'] for k,p in positions.items())/after
                max_gross=max(max_gross,g);max_crypto=max(max_crypto,cr);max_stop=max(max_stop,risk_after)
                # Prospective sizing includes the fee's reduction of account equity.
                if cash<0 or g>.6+1e-10 or cr>.2+1e-10 or risk_after>.01+1e-10:raise ValueError('ENTRY_CAPITAL_OR_RISK')
        # Current bar high/low are consumed only after entries, never for their selection.
        for s,p in list(positions.items()):
            if s not in bars:continue
            r=bars[s];at=when+timedelta(hours=1)-timedelta(seconds=1)
            if r['low']<=p['stop']:sell(s,min(r['open'],p['stop']),at,'STOP')
            elif r['high']>=p['target']:sell(s,p['target'],at,'TARGET')
        for s,r in bars.items():marks[s]=r['close']
        eq=equity();peak=max(peak,eq);drawdown=max(drawdown,1-eq/peak)
        if eq<=0:raise ValueError('INSOLVENCY')
        if when.hour==23:
            curve.append({'day':utc_day,'equity':eq,'cash':cash,'receivables':sum(x['amount'] for x in receivables),
                          'positions':[{ 'symbol':s,'qty':p['qty'],'mark':marks[s]} for s,p in sorted(positions.items())],
                          'event_count':len(events)})
        when+=timedelta(hours=1)
    if positions:raise ValueError('UNLIQUIDATED_TERMINAL_INVENTORY')
    terminal=equity();fixed=sum(-e['cash_delta'] for e in events if e['kind']=='FIXED')
    dividends=sum(e['amount'] for e in events if e['kind']=='DIV_EX')
    error=terminal-20000-(sum(t['net_usd'] for t in trades)+dividends-fixed)
    if abs(error)>1e-6:raise ValueError('TERMINAL_RECONCILIATION')
    return {'schema':'HARPOON_SWING_ACCOUNT_1','rule':rule,'stress':stress,'initial_usd':20000,
        'terminal_usd':terminal,'net_usd':terminal-20000,'fixed_cost_usd':fixed,'dividend_entitlement_usd':dividends,
        'variable_cost_usd':sum(t['variable_cost_usd'] for t in trades),'reconciliation_error_usd':error,
        'max_entry_gross_fraction':max_gross,'max_entry_crypto_fraction':max_crypto,'max_entry_stop_risk_fraction':max_stop,
        'hour_grid_drawdown':drawdown,'intrabar_drawdown_verified':False,'events':events,'trades':trades,'curve':curve,'signals':signals,
        'execution_allowed':False,'liveApproved':False,'level8_accredited':False}
