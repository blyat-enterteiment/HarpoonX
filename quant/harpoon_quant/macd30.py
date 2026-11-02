"""Causal daily MACD(12,30,9), Wilder RSI14 and stochastic14/3/3."""
import math
from statistics import median
from .swing import daily_features


def ema(values,span):
    if span<2 or len(values)<span:raise ValueError('EMA_WARMUP')
    out=[None]*(span-1);v=sum(values[:span])/span;out.append(v)
    for x in values[span:]:
        v+=2/(span+1)*(x-v);out.append(v)
    return out


def indicators(rows):
    if len(rows)<150:raise ValueError('150_COMPLETED_DAYS_REQUIRED')
    c=[r['close'] for r in rows]
    if not all(math.isfinite(x) and x>0 for x in c):raise ValueError('INVALID_CLOSE')
    fast,slow=ema(c,12),ema(c,30)
    m=[a-b for a,b in zip(fast[29:],slow[29:])];sig=ema(m,9)
    hist=[a-b for a,b in zip(m[8:],sig[8:])]
    changes=[b-a for a,b in zip(c,c[1:])];g=sum(max(x,0) for x in changes[:14])/14;l=sum(max(-x,0) for x in changes[:14])/14
    rsis=[]
    for i,x in enumerate(changes[13:]):
        if i:g=(13*g+max(x,0))/14;l=(13*l+max(-x,0))/14
        rsis.append(50 if g==l==0 else 100 if l==0 else 100-100/(1+g/l))
    k=[]
    for i in range(13,len(rows)):
        window=rows[i-13:i+1];lo=min(r['low'] for r in window);hi=max(r['high'] for r in window)
        k.append(50 if hi==lo else 100*(c[i]-lo)/(hi-lo))
    smooth=[sum(k[i-2:i+1])/3 for i in range(2,len(k))]
    d=[sum(smooth[i-2:i+1])/3 for i in range(2,len(smooth))]
    return {'hist':hist[-3:],'macd':m[-1],'rsi':rsis[-2:],'k':smooth[-1],'d':d[-1]}


def make_candidate(full_daily,variant):
    if variant not in ('CROSS','CONFIRMED','EARLY'):raise ValueError('VARIANT')
    def candidate(symbol,rule,when,daily,hours,entry,session_open,rate):
        prior=[r for r in full_daily[symbol] if r['known']<when]
        known=[r for r in hours if r['known']<when]
        if len(prior)<150 or len(known)<20:return None
        f=daily_features(prior);bar=known[-1]
        if not f or when-bar['known']>__import__('datetime').timedelta(hours=30):return None
        if '/' not in symbol and bar['at'].astimezone(__import__('zoneinfo').ZoneInfo('America/New_York')).date()!=when.astimezone(__import__('zoneinfo').ZoneInfo('America/New_York')).date():return None
        x=indicators(prior);h=x['hist'];cross=h[-2]<=0<h[-1]
        osc=45<=x['rsi'][-1]<=70 and x['rsi'][-1]>x['rsi'][-2] and x['k']>x['d'] and x['k']<85
        early=h[-3]<h[-2]<h[-1]<=0
        if not ((cross if variant=='CROSS' else cross and osc if variant=='CONFIRMED' else early and osc)):return None
        # Same price, trend, costs and capacity tests across all three arms.
        if prior[-1]['close']<=f['sma'] or prior[-1]['close']<f['level']-.5*f['atr']:return None
        if bar['close']<=prior[-1]['high'] or entry>bar['close']+.25*f['atr'] or entry>f['level']+f['atr']:return None
        if 2*f['atr']/entry<3*2*rate or entry<=2*f['atr']:return None
        return {'symbol':symbol,'atr':f['atr'],'score':(prior[-1]['close']-f['sma'])/f['atr'],
                'stop':entry-2*f['atr'],'target':entry+3*f['atr'],'level':f['level'],
                'signal_known_at':max(bar['known'],prior[-1]['known']).isoformat(),
                'capacity':.01*median(r['close']*r['volume'] for r in known[-20:]),
                'book':'crypto' if '/' in symbol else 'equity','indicator_receipt':x,'variant':variant}
    return candidate
