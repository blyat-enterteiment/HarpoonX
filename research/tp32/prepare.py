"""Prepare causal observed-bar features. No price path is interpolated or labelled as NBBO."""
import bisect, collections, datetime as dt, glob, hashlib, json, math
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'evidence/tp32/data'
OUT = ROOT / 'evidence/tp32'
NY = ZoneInfo('America/New_York')
UTC = dt.timezone.utc
def stamp(s): return int(dt.datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()*1000)
def local(t): return dt.datetime.fromtimestamp(t/1000,NY)
def read(p): return json.loads(Path(p).read_text())
def unwrap(d):
    while isinstance(d,dict) and isinstance(d.get('result'),str): d=json.loads(d['result'])
    return d
def raw_daily(s):
    bars=read(DATA/(s.replace('/','_')+'-1Day.json'))['bars']
    if isinstance(bars,dict): bars=bars[s]
    return [[stamp(b['timestamp']),b['open'],b['high'],b['low'],b['close'],b['volume'],b.get('vwap')] for b in bars]
cal={r['date']: {'date':r['date'], 'open':int(dt.datetime.fromisoformat(r['open']).replace(tzinfo=NY).timestamp()*1000),'close':int(dt.datetime.fromisoformat(r['close']).replace(tzinfo=NY).timestamp()*1000)} for r in read(DATA/'calendar.json')['calendar']}
actions=unwrap(read(DATA/'corporate-actions.json'))['announcements']
splits=[r for group in actions.values() for r in group]
def adjust(row,symbol,asof):
    # Rebase only corporate actions that are already effective at this observation.
    d=local(row[0]).date().isoformat()
    factor=math.prod(float(r['new_rate'])/float(r['old_rate']) for r in splits if r['symbol']==symbol and d<r['ex_date']<=asof)
    return [row[0],*[v/factor for v in row[1:5]],row[5]*factor,row[6]/factor if row[6] else None]

def main():
    cfg=read(ROOT/'config/examples/xxx.json'); symbols=cfg['universe']; series={}; daily={}; diagnostics={}; fingerprints=[]
    for metadata_file in sorted(DATA.glob('*.json')):
        if '-5Min-' not in metadata_file.name:
            fingerprints.append({'path':str(metadata_file.relative_to(ROOT)),'sha256':hashlib.sha256(metadata_file.read_bytes()).hexdigest()})
    for i in symbols+ [{'symbol':s,'book':'etf'} for s in ['XLK','SMH']]:
        s=i['symbol']; rows={}; duplicate=0; invalid=0; zero_volume=0
        for file in sorted(DATA.glob(s.replace('/','_')+'-5Min-*.json')):
            d=read(file); fingerprints.append({'path':str(file.relative_to(ROOT)),'sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
            for r in d['rows']:
                day=local(r[0]).date().isoformat(); session=cal.get(day)
                if i['book']!='crypto' and (not session or not session['open']<=r[0]<session['close']): continue
                if not all(isinstance(x,(int,float)) and math.isfinite(x) for x in r[:6]) or min(r[1:5])<=0 or r[5]<0 or r[2]<max(r[1],r[3],r[4]) or r[3]>min(r[1],r[2],r[4]):
                    invalid+=1;continue
                if r[5]==0: zero_volume+=1;continue
                if r[0] in rows:
                    if rows[r[0]]!=r: raise ValueError('Conflicting duplicate '+s)
                    duplicate+=1
                rows[r[0]]=r
        a=sorted(rows.values()); series[s]=a; daily[s]=raw_daily(s)
        expected=sum(int((x['close']-x['open'])/300000) for x in cal.values()) if i['book']!='crypto' else int((stamp('2026-10-17T00:00:00Z')-stamp('2024-09-01T00:00:00Z'))/300000)
        diagnostics[s]={'observedBars':len(a),'expectedBars':expected,'missingBarCount':expected-len(a),'quarantinedInvalidBars':invalid,'zeroVolumeBarsExcluded':zero_volume,'duplicateIdentical':duplicate,'first':a[0][0] if a else None,'last':a[-1][0] if a else None}
    by_time=collections.defaultdict(list); parity=[]; errors=collections.Counter()
    for instrument in symbols:
        if instrument['book']=='crypto': continue
        s=instrument['symbol']; a=series[s]; groups=collections.defaultdict(list)
        for r in a: groups[local(r[0]).date().isoformat()].append(r)
        days=sorted(groups)
        for day in days:
            if not '2024-10-01'<=day<='2026-10-16': continue
            prior_days=[d for d in days if d<day][-20:]
            history=[adjust(r,s,day) for d in prior_days for r in groups[d]]
            d=[adjust(r,s,day) for r in daily[s] if local(r[0]).date().isoformat()<day]
            if len(d)<21 or len(prior_days)<10: continue
            cumulative={}
            for pd in prior_days:
                total=0; times=[]; values=[]
                for r in groups[pd]:
                    r=adjust(r,s,day); t=local(r[0]); total+=r[5];times.append(t.hour*60+t.minute);values.append(total)
                cumulative[pd]=(times,values)
            current=[]; volume=0; dollars=0; vwap_num=0
            for r in groups[day]:
                current.append(r);volume+=r[5];dollars+=r[4]*r[5];vwap_num+=r[6]*r[5] if r[6] else 0
                if len(current)<4 or not all(b[6] and b[6]>0 for b in current): continue
                now=r[0]+303000
                if now>=cal[day]['close']-600000: continue
                n=local(r[0]);minute=n.hour*60+n.minute; totals=[]
                for times,values in cumulative.values():
                    j=bisect.bisect_right(times,minute)-1
                    if j>=0: totals.append(values[j])
                if len(totals)<10 or sum(totals)<=0: continue
                tail=(history+current)[-15:]
                tr=[max(b[2]-b[3],abs(b[2]-tail[j][4]),abs(b[3]-tail[j][4])) for j,b in enumerate(tail[1:])]; atr=sum(tr)/len(tr)
                diffs=[b[4]-tail[j][4] for j,b in enumerate(tail[1:])];up=sum(max(0,v) for v in diffs)/len(diffs);down=sum(max(0,-v) for v in diffs)/len(diffs)
                spread=5 if s in ['SPXL','SPXS'] else 2;bid=r[4]*(1-spread/20000);ask=r[4]*(1+spread/20000)
                f={'symbol':s,'book':instrument['book'],'factor':instrument['factor'],'leverage':instrument['leverage'],'asof':dt.datetime.fromtimestamp(now/1000,UTC).isoformat(),'bar_end':dt.datetime.fromtimestamp((r[0]+300000)/1000,UTC).isoformat(),'base':current[0][2],'atr':atr,'perf5':(ask/d[-5][4]-1)*100,'perf20':(ask/d[-20][4]-1)*100,'rvol':volume/(sum(totals)/len(totals)),'momentum_bps':(current[-1][4]/current[-4][4]-1)*10000,'rsi':100*up/(up+down) if up+down else 50,'atr_pct':atr/ask,'vwap_distance':ask/(vwap_num/volume)-1,'spread_bps':(ask/bid-1)*10000,'is_etf':int(s in ['SPXL','SPXS']),'ask':ask,'bid':bid,'dollar_volume':dollars,'at':now,'source':'OBSERVED_BARS_WITH_MODELED_SPREAD'}
                if s in ['SPXL','SPXS']: f['pair']='SPXL'
                by_time[now].append(f)
                if len(parity)<30 and minute==630 and day.endswith(('-01','-15')):
                    parity.append({'feature':f,'bars':history+current,'daily':d,'now':now})
        print('features',s,flush=True)
    candidates=[]
    for at,rows in sorted(by_time.items()):
        for f in rows:
            if f['perf5']>0 and f['rvol']>=2 and f['momentum_bps']>=20:
                candidates.append({'feature':f,'selectionRows':[{k:v for k,v in z.items() if k in ['symbol','book','pair','perf5','rvol','momentum_bps']} for z in rows]})
    output={'schema':'HARPOON-RESEARCH-BARS-32-1','source':'ALPACA_CONNECTED_MARKET_DATA','generatedAt':dt.datetime.now(UTC).isoformat(),'calendar':list(cal.values()),'series':series,'daily':daily,'splits':splits,'coverage':diagnostics,'fingerprints':fingerprints,'limitations':['Prices are historical OHLCV/VWAP; bid/ask and all fills are modeled, not observed NBBO.','Configured canonical entries only; 61 plugin variants are not 61 independently validated strategies.','No historical option quotes available through connected source; no option PnL simulated.','Missing bars are not interpolated; fills across data gaps excluded.','Universe chosen by existing release, not a point-in-time broad stock universe.']}
    (OUT/'prepared.json').write_text(json.dumps(output,separators=(',',':'))+'\n')
    (OUT/'candidates.json').write_text(json.dumps(candidates,separators=(',',':'))+'\n')
    (OUT/'feature-parity.json').write_text(json.dumps(parity,separators=(',',':'))+'\n')
    print(json.dumps({'coverage':diagnostics,'candidates':len(candidates),'paritySamples':len(parity)}),flush=True)
if __name__=='__main__': main()
