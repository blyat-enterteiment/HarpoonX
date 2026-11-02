"""Fixed-trial purged walk-forward, paired block bootstrap and separate final holdout."""
import datetime as dt, hashlib, json, math, statistics
from pathlib import Path
import numpy as np
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'evidence/tp32'
NY=ZoneInfo('America/New_York');UTC=dt.timezone.utc
def day(t): return dt.datetime.fromtimestamp(t/1000,NY).date().isoformat()
def read(p): return json.loads(Path(p).read_text())
raw=read(OUT/'raw-results.json');p=raw['protocol'];capital=p['capitalUsd'];baseline='BASELINE_30_1';ids=p['candidates']
prepared=read(OUT/'prepared.json');sessions=sorted(x['date'] for x in prepared['calendar'] if p['historyFrom']<=x['date']<=p['historyThrough'])
cal={x['date']:x for x in prepared['calendar']};hold=sessions[-p['holdoutSessions']:];dev=sessions[:-p['holdoutSessions']];folds=[]
base=len(dev)-p['testFolds']*(p['testSessionsPerFold']+p['embargoSessions'])
if base<p['trainSessions']:raise ValueError('History too short for registered protocol')
for i in range(p['testFolds']):
    begin=base+i*(p['testSessionsPerFold']+p['embargoSessions'])+p['embargoSessions'];test=dev[begin:begin+p['testSessionsPerFold']];train=dev[begin-p['embargoSessions']-p['trainSessions']:begin-p['embargoSessions']]
    folds.append({'id':i+1,'train':train,'test':test,'purgeCutoff':cal[test[0]]['open']-p['purgeHours']*3600000})
def key(t):return (t['symbol'],t['signalAt'])
def comparable(variants,kind):
    maps={i:{key(t):t for t in variants[i][kind]} for i in ids};common=set.intersection(*(set(m) for m in maps.values()));return {i:[maps[i][k] for k in sorted(common)] for i in ids}
cohorts={kind:comparable(raw['variants'],kind) for kind in ['base','stress','delayed','partial']}
def window(trades,days,purge_end=True):
    start=cal[days[0]]['open'];end=cal[days[-1]]['close'];cut=end-p['maxHoldHours']*3600000 if purge_end else end
    return [t for t in trades if start<=t['opened']<=cut and t['closedAt']<=end]
def curve(trades,days):
    # Every open campaign contributes mark-to-market, including partial fills and estimated fees.
    dates=list(days);values=np.zeros(len(dates));ends=[cal[d]['close'] for d in dates]
    for t in trades:
        marks=t['marks'];j=0;last=0
        for k,end in enumerate(ends):
            if end<t['opened']:continue
            while j<len(marks) and marks[j]['at']<=end:last=marks[j]['pnl'];j+=1
            if t['closedAt']<=end:last=t['net']
            values[k]+=last
    return np.diff(np.r_[0,values])/capital
def metrics(trades,days):
    r=curve(trades,days);nav=capital*(1+np.cumsum(r));peaks=np.maximum.accumulate(np.r_[capital,nav])[1:];dd=np.max((peaks-nav)/peaks) if len(r) else 0
    mean=float(np.mean(r)) if len(r) else 0;z=r-mean;var=float(np.mean(z*z)) if len(r) else 0
    for lag in range(1,min(5,len(r)-1)+1):var+=2*(1-lag/6)*float(np.sum(z[lag:]*z[:-lag])/len(r))
    down=float(np.sqrt(np.mean(np.minimum(r,0)**2))) if len(r) else 0;gains=sum(max(t['net'],0) for t in trades);loss=-sum(min(t['net'],0) for t in trades);tail=sorted(r)[:max(1,math.ceil(len(r)*.05))]
    positive_peaks=[t for t in trades if t['peakPnl']>0];net=sum(t['net'] for t in trades)
    return {'trades':len(trades),'sessions':len(days),'netUsd':net,'netReturn':net/capital,'sharpeHac':mean/math.sqrt(var)*math.sqrt(252) if var>1e-20 else None,'sortino':mean/down*math.sqrt(252) if down>1e-15 else None,'maxDrawdownDaily':float(dd),'expectedShortfall95Daily':float(-np.mean(tail)) if len(tail) else None,'profitFactor':gains/loss if loss>0 else None,'winRate':sum(t['net']>0 for t in trades)/len(trades) if trades else None,'expectancyUsd':net/len(trades) if trades else None,'expectancyR':statistics.mean(t['net']/t['riskUsd'] for t in trades) if trades else None,'feesEstimatedUsd':sum(t['fees'] for t in trades),'observedBarMfeGivebackUsd':sum(t['giveback'] for t in trades),'captureOfPositivePeak':sum(t['net'] for t in positive_peaks)/sum(t['peakPnl'] for t in positive_peaks) if positive_peaks else None,'ambiguousStopTargetBars':sum(t['ambiguous'] for t in trades)}
def lower(a):
    if len(a)<20:return None
    rng=np.random.default_rng(3201);samples=[];a=np.asarray(a)
    for _ in range(4000):
        ix=[]
        while len(ix)<len(a):start=int(rng.integers(len(a)));ix.extend((start+j)%len(a) for j in range(5))
        samples.append(float(np.mean(a[ix[:len(a)]])))
    return float(np.quantile(samples,(1-p['confidence'])/2))
def metric_window(alltrades,days):return metrics(window(alltrades,days),days)
def select(train):
    m={i:metric_window(cohorts['base'][i],train) for i in ids};b=m[baseline];eligible=[]
    for i in ids[1:]:
        a=m[i]
        if a['trades']>=30 and a['netUsd']>max(0,b['netUsd']) and a['maxDrawdownDaily']<=b['maxDrawdownDaily'] and a['expectedShortfall95Daily']<=b['expectedShortfall95Daily']:eligible.append(i)
    return max(eligible,key=lambda i:m[i]['netUsd']) if eligible else baseline
oos_days=[d for f in folds for d in f['test']];tables={i:{} for i in ids};fold_reports=[];selected_trades=[]
for f in folds:
    chosen=select(f['train']);tr=window(cohorts['base'][chosen],f['test']);selected_trades.extend(tr)
    fold_reports.append({'id':f['id'],'trainFrom':f['train'][0],'trainThrough':f['train'][-1],'testFrom':f['test'][0],'testThrough':f['test'][-1],'purgeCutoff':f['purgeCutoff'],'selectedUsingTrainingOnly':chosen,'metrics':{i:metric_window(cohorts['base'][i],f['test']) for i in ids}})
def fold_trades(i,kind='base'):return [t for f in folds for t in window(cohorts[kind][i],f['test'])]
final_train=dev[-p['trainSessions']-p['embargoSessions']:-p['embargoSessions']];locked=select(final_train)
for i in ids:
    tables[i]['oos']=metrics(fold_trades(i),oos_days);tables[i]['holdout']=metric_window(cohorts['base'][i],hold)
    for kind in ['stress','delayed','partial']:
        tables[i][kind+'Oos']=metrics(fold_trades(i,kind),oos_days);tables[i][kind+'Holdout']=metric_window(cohorts[kind][i],hold)
    tables[i]['oosByBook']={book:metrics([t for t in fold_trades(i) if t['book']==book],oos_days) for book in ['equity','etf','crypto']}
gates={}
for i in ids[1:]:
    a=tables[i];b=tables[baseline];paired=curve(fold_trades(i),oos_days)-curve(fold_trades(baseline),oos_days);h=curve(window(cohorts['base'][i],hold),hold)-curve(window(cohorts['base'][baseline],hold),hold)
    lo=lower(paired);hi=lower(h);stresslo=lower(curve(fold_trades(i,'stress'),oos_days)-curve(fold_trades(baseline,'stress'),oos_days))
    g={'oosSample':a['oos']['trades']>=100,'holdoutSample':a['holdout']['trades']>=30,'oosPositive':a['oos']['netUsd']>0,'holdoutPositive':a['holdout']['netUsd']>0,'pairedOosLowerPositive':lo is not None and lo>0,'pairedHoldoutLowerPositive':hi is not None and hi>0,'oosDrawdownNoWorse':a['oos']['maxDrawdownDaily']<=b['oos']['maxDrawdownDaily'],'holdoutDrawdownNoWorse':a['holdout']['maxDrawdownDaily']<=b['holdout']['maxDrawdownDaily'],'tailNoWorse':a['oos']['expectedShortfall95Daily']<=b['oos']['expectedShortfall95Daily'],'doubleCostsPositive':a['stressOos']['netUsd']>0 and a['stressHoldout']['netUsd']>0,'doubleCostsPairedLowerPositive':stresslo is not None and stresslo>0,'improvedFoldFraction':sum(f['metrics'][i]['netUsd']>f['metrics'][baseline]['netUsd'] for f in fold_reports)/len(fold_reports)>=.6}
    gates[i]={'gates':g,'passed':all(g.values()),'pairedDailyExcessLower':lo,'holdoutPairedDailyExcessLower':hi,'doubleCostsDailyExcessLower':stresslo}
portfolio={i:{kind:metric_window(raw['portfolios'][i][kind]['trades'],hold) for kind in ['base','stress']} for i in ids}
winners=[i for i,g in gates.items() if g['passed']];recommendation=max(winners,key=lambda i:tables[i]['oos']['netUsd']) if winners else baseline
report={'schema':'HARPOON-WF-REPORT-32-1','generatedAt':dt.datetime.now(UTC).isoformat(),'source':raw['source'],'baselineArchiveSha256':p['baselineArchiveSha256'],'protocolSha256':raw['protocolSha256'],'trialCount':3,'confidence':p['confidence'],'nativeFeatureParitySamples':raw['nativeFeatureParitySamples'],'cohorts':raw['cohortCount'],'windows':{'oosFrom':oos_days[0],'oosThrough':oos_days[-1],'holdoutFrom':hold[0],'holdoutThrough':hold[-1],'trainSessions':126,'testSessionsPerFold':21,'folds':12,'purgeHours':72,'embargoSessions':3},'tables':tables,'folds':fold_reports,'walkForwardSelection':{'finalLockedProfileBeforeHoldout':locked,'oos':metrics(selected_trades,oos_days),'holdout':tables[locked]['holdout']},'gates':gates,'researchRecommendation':recommendation,'productionDefault':baseline,'promotion':'NONE_BAR_MODEL_REQUIRES_PROSPECTIVE_EXECUTION_VALIDATION','fundedPortfolioHoldout':portfolio,'coverage':raw['coverage'],'excluded':{i:raw['variants'][i]['excluded'] for i in ids},'limitations':raw['limitations']+['Daily HAC Sharpe, Sortino and tail risk use exchange sessions; weekend crypto marks accumulate into the next exchange close.','Fixed entry cohort comparison is an opportunity study with overlapping positions; funded portfolio is reported separately.','Purged window ends exclude opportunities whose complete maximum-hold label would cross the boundary.','Bar MFE capture is relative to observed close marks; it is not intrabar omniscient maximum or guaranteed attainable profit.','No account-level real returns, no championship-equivalent futures/forex adapter or contest registration.','Historical stock/ETF feed is SIP; runtime default is IEX. Matching-feed prospective validation and feed permissions remain required.']}
(OUT/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
lines=['HARPOON XXX 30.2 — TAKE PROFIT / WALK-FORWARD','Fecha: '+report['generatedAt'],'','RESULTADO: '+recommendation,'Activación automática: NO. Las ejecuciones se modelaron sobre barras reales, no son fills ni rendimientos reales.','','MÉTODO','Tres políticas registradas antes del cálculo. 12 ventanas de prueba de 21 sesiones, entrenamiento previo de 126 sesiones, purga de 72 horas y embargo de 3 sesiones. Holdout final separado de 63 sesiones.','OOS: '+oos_days[0]+' a '+oos_days[-1]+'. Holdout: '+hold[0]+' a '+hold[-1]+'.','Intervalos bootstrap por bloques de 5 sesiones; 4,000 remuestreos; confianza ajustada por 3 ensayos: '+str(p['confidence']), '','COMPARACIÓN A ENTRADAS Y RIESGO FIJOS (NO ES RENTABILIDAD DE UNA CUENTA)']
for i in ids:
    lines+=['',i]
    for label in ['oos','holdout','stressOos','stressHoldout','delayedOos','partialOos']:
        m=tables[i][label];lines+=[f"{label}: {m['trades']} operaciones; neto estimado USD {m['netUsd']:.2f}; retorno sobre unidad de capital {m['netReturn']:.2%}; DD diario {m['maxDrawdownDaily']:.2%}; Sharpe HAC {m['sharpeHac']}; Sortino {m['sortino']}; PF {m['profitFactor']}; esperanza R {m['expectancyR']}."]
    if i!=baseline: lines+=['Criterios: '+json.dumps(gates[i],ensure_ascii=False)]
lines+=['','CARTERA CON RESTRICCIONES DE CAPITAL / HOLDOUT',json.dumps(portfolio,ensure_ascii=False,indent=2),'','COBERTURA',json.dumps(report['coverage'],indent=2),'','EXCLUSIONES',json.dumps(report['excluded'],indent=2),'','LIMITACIONES']+['- '+x for x in report['limitations']]+['','LECTURA CORRECTA','No se promete una mejora drástica. Si ningún candidato supera todos los criterios se conserva la referencia. Los arreglos de cancelación, stop y reconciliación se validan con pruebas de fallos, no se les atribuye PnL que estas barras no permiten medir.','El 11,376% de Larry Williams corresponde a 1987 según la organización. La competición es de futuros/forex; Alpaca acciones/ETF/cripto/opciones no equivale a esas divisiones.','https://www.worldcupchampionships.com/','https://docs.alpaca.markets/us/docs/orders-at-alpaca','https://docs.alpaca.markets/us/docs/websocket-streaming']
(OUT/'WALKFORWARD_XXX_30_2.txt').write_text('\n'.join(lines)+'\n')
print(json.dumps({'researchRecommendation':recommendation,'productionDefault':baseline,'tables':{i:{k:tables[i][k] for k in ['oos','holdout']} for i in ids},'gates':gates},indent=2))
