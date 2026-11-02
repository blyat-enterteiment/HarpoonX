"""Seeded synthetic 48-option experiment. No market/provider observations."""
from __future__ import annotations
import json, math, sys, time
from pathlib import Path
from datetime import datetime, timedelta, UTC
import numpy as np
from scipy.special import ndtr
sys.path.insert(0,str(Path(__file__).resolve().parent))
from harpoon_quant.optimization import Policy, replay, validate_window, subwindow
from harpoon_quant.recursive import tick
from harpoon_quant.performance import report

OUT=Path(__file__).resolve().parent
SEED=20261030
ORIGIN='SYNTHETIC_ENGINEERING_ONLY'
LIMITS=dict(initial_equity=20000,risk_fraction=.0025,open_risk_fraction=.015,gross_fraction=.5,asset_fraction=.12,factor_fraction=.5,max_positions=8,max_drawdown=.08)

def bs(s,k,t,v,call):
    d1=(np.log(s/k)+(.04+.5*v*v)*t)/(v*np.sqrt(t));d2=d1-v*np.sqrt(t)
    c=s*ndtr(d1)-k*np.exp(-.04*t)*ndtr(d2)
    return np.maximum(0,c if call else c-s+k*np.exp(-.04*t))

def generate():
    rng=np.random.default_rng(SEED); n=420; assets=24
    spot=np.zeros((n+1,assets));spot[0]=rng.uniform(20,65,assets)
    ret=np.zeros((n+1,assets));rv=rng.uniform(.45,.95,assets)
    iv=np.zeros_like(spot);iv[0]=rv*1.15
    for d in range(1,n+1):
        # Forward generator: no outcomes used in the forecast rule.
        regime=1.0 if d<240 else (1.6 if d<300 else .8)
        persist=.18 if d<240 else (-.12 if d<300 else .08)
        market=rng.normal();shock=rng.standard_t(6,size=assets)*math.sqrt(4/6)
        jump=np.where(rng.random(assets)<.008,rng.normal(0,.10,assets),0)
        ret[d]=np.clip(persist*ret[d-1]+rv/math.sqrt(365)*regime*(.4*market+math.sqrt(.84)*shock)+jump,-.3,.3)
        spot[d]=spot[d-1]*np.exp(ret[d])
        iv[d]=np.clip(.94*iv[d-1]+.06*rv*regime*1.15+rng.normal(0,.015,assets),.2,2)
    days=[(datetime(2025,7,1,tzinfo=UTC)+timedelta(days=i)).date().isoformat() for i in range(n)]
    ops=[]
    for d in range(20,n-3):
        for a in range(assets):
            s=spot[d,a];v=iv[d,a];t=21/365;vol=max(.25,float(np.std(ret[d-19:d+1,a]))*math.sqrt(365))
            # Past-only momentum, fixed ex ante; not re-estimated on holdout.
            forecast=float(np.clip(.12*ret[d,a]+.04*ret[d-2:d+1,a].mean(),-.012,.012))
            for call in (True,False):
                k=s*math.exp((1 if call else -1)*1.7*v*math.sqrt(t))
                mid=float(bs(s,k,t,v,call));spread=float(np.clip(.08+.04*(v>.9),.08,.16))
                funding=mid*(1+spread/2)*100+.65
                if funding<=0:raise AssertionError('funding')
                expected=float(bs(s*math.exp(3*forecast),k,18/365,v,call))*(1-spread/2)*100-.65
                edge=expected-funding-.02*funding
                # Entry delta notional; maximum loss remains the full paid premium.
                d1=(math.log(s/k)+(.04+.5*v*v)*t)/(v*math.sqrt(t))
                delta=float(ndtr(d1)) if call else float(ndtr(d1))-1
                at=datetime.fromisoformat(days[d]).replace(tzinfo=UTC,hour=12);end=at+timedelta(days=3)
                wealth={}
                for j in range(4):
                    futuremid=float(bs(spot[d+j,a],k,(21-j)/365,iv[d+j,a],call))
                    wealth[days[d+j]]=max(0,futuremid*(1-spread/2)*100-.65)
                ops.append(dict(id=f'{d}-{a}-{call}',symbol=f'SYNTH{a:02}',book='options',factor=f'GROUP{a//6}',at=at.isoformat(),known_at=at.isoformat(),label_end=end.isoformat(),label_known_at=(end+timedelta(minutes=1)).isoformat(),funding_per_lot=funding,risk_per_lot=funding,exposure_per_lot=abs(delta)*s*100,max_lots=5,robust_edge_per_lot=edge,roundtrip_cost_per_lot=mid*spread*100+1.30,wealth_by_day=wealth))
    return dict(days=days,opportunities=ops)

def part(window,lo,hi):
    # Embargo within each OOS block and purge trades crossing boundaries.
    return subwindow(window,lo,hi,embargo_days=3)

def metrics(returns,days,trades):
    return report(dict(origin=ORIGIN,return_basis='NET_FLOW_ADJUSTED',initial_equity=20000,returns=returns,times=[d+'T23:59:59+00:00' for d in days],periods_per_year=365,sampling='DAILY_UTC_CALENDAR',trades=trades))

def main():
    started=time.perf_counter();w=generate();validate_window(w,'2026-10-30T00:00:00+00:00')
    # Numerical/clock validators, before scoring.
    s,k,t,v=50.,55.,.1,.6
    assert abs(float(bs(s,k,t,v,True)-bs(s,k,t,v,False))-(s-k*math.exp(-.04*t)))<1e-10
    assert len({o['symbol'] for o in w['opportunities']})==24
    assert all(o['known_at']<=o['at']<o['label_end']<=o['label_known_at'] for o in w['opportunities'])
    (OUT/'data.synthetic.json').write_text(json.dumps(w))
    binding=dict(account_id='SYNTH_48_OPTIONS',execution_hash='ENGINE_1_2_FROZEN',forecast_hash='FIXED_PAST_MOMENTUM_V1',risk_limits=LIMITS)
    settings=dict(LIMITS,origin=ORIGIN)
    config=dict(enabled=True,autoPaper=True,statePath=str(OUT/'optimizer.sqlite3'),lifetimeTrials=128,maxTrials=24,maxGenerations=3,cpuSeconds=5,minGainUsd=5,minHoldoutTrades=20,minSortinoPerPeriod=0)
    if Path(config['statePath']).exists():raise RuntimeError('Use fresh output directory; journal never silently reset')
    folds=[];combined={'baseline':[],'challenger':[],'stress':[]};alltrades={k:[] for k in combined};days=[]
    for f in range(3):
        lo=240+60*f;dev=part(w,lo-240,lo-1);hold=part(w,lo,lo+60)
        panel=dict(study_id=f'SYNTH48_FOLD{f}',origin=ORIGIN,binding=binding,net_costs_confirmed=True,cashflows_adjusted=True,complete_opportunity_universe=True,frozen_exit_replay_validated=True,development=dev,holdout_start=hold['days'][0],holdout_end=hold['days'][-1])
        # Register and freeze without supplying the holdout object.
        registered=(datetime.fromisoformat(hold['days'][0]).replace(tzinfo=UTC)-timedelta(seconds=1)).isoformat()
        transitions=[]
        for _ in range(8):
            result=tick(panel,config,binding,registered,paper=True);transitions.append(result['status'])
            if result['status'] in {'WAIT_HOLDOUT','REJECTED','EXHAUSTED'}:break
        if result['status']=='WAIT_HOLDOUT':
            panel['holdout']=hold
            result=tick(panel,config,binding,(datetime.fromisoformat(hold['days'][-1]).replace(tzinfo=UTC)+timedelta(days=2)).isoformat(),paper=True)
            transitions.append(result['status'])
        policy=Policy(**result.get('campaign',{}).get('best',{'risk_scale':1.,'quality_bps':0.}))
        runs=dict(baseline=replay(hold,Policy(),settings),challenger=replay(hold,policy,settings),stress=replay(hold,policy,settings,cashflow_stress=1.5))
        # Fold reset: each starts at $20k; compounded path is a normalized stitched diagnostic.
        for key,r in runs.items():combined[key]+=r['returns'];alltrades[key]+=r['trades']
        days+=hold['days']
        folds.append(dict(fold=f+1,development=[dev['days'][0],dev['days'][-1]],holdout=[hold['days'][0],hold['days'][-1]],registered_at=registered,transitions=transitions,status=result['status'],policy=policy.__dict__,active=result.get('active'),metrics={k:r['metrics'] for k,r in runs.items()},acceptance=result.get('result'),budget=result.get('budget')))
    aggregate={k:metrics(r,days,alltrades[k]) for k,r in combined.items()}
    # Terminal block bootstrap of fixed baseline/challenger series; descriptive, not a new selection stage.
    rng=np.random.default_rng(SEED+1);boot={}
    for key in ['baseline','challenger']:
        r=np.asarray(combined[key]);n=len(r);starts=rng.integers(0,n,size=(5000,(n+4)//5));idx=((starts[:,:,None]+np.arange(5))%n).reshape(5000,-1)[:,:n];rr=r[idx];nav=np.cumprod(1+rr,axis=1);peak=np.maximum.accumulate(np.column_stack([np.ones(5000),nav]),axis=1)[:,1:];dd=np.max(1-nav/peak,axis=1);ending=nav[:,-1]-1
        boot[key]=dict(terminal_return_p05_p50_p95=np.quantile(ending,[.05,.5,.95]).tolist(),resample_fraction_positive=float(np.mean(ending>0)),resample_fraction_drawdown_over_8pct=float(np.mean(dd>.08)),scope='Descriptive circular 5-day block bootstrap of this synthetic fixed-policy OOS path; not a real-world probability or selection gate.')
    result=dict(origin=ORIGIN,seed=SEED,capital_usd=20000,candidates_per_iteration=48,underlyings=24,holding_hours=72,model='European Black-Scholes synthetic marks; stochastic volatility, jumps, momentum and reversal regimes; no OPRA/Alpaca observations',daily_clock='UTC calendar 365; illustrative model also generates weekends',design='3 rolling folds: 239 development + 1 gap + 60 OOS days, 3-day embargo and purged crossing exits, persistent cumulative trial journal; separate fold capital resets',folds=folds,aggregate=aggregate,bootstrap=boot,series=dict(days=days,returns=combined),scope='Stitched 180-day normalized diagnostic; not a continuously funded live simulation. No synthetic profile activated.',limitations=['No historical option chain, OPRA, corporate actions, dividends, early exercise, assignments or actual fills','Constant relative spread 8%-12%, $0.65 fee per side assumption, no fee schedule claim; no depth or size-dependent market impact','Forecast rule and generative parameters are assumptions, not fitted empirical alpha','Funded selection replay does not reproduce production MILP, native exits or all account risk halts; DD gate is an end-window acceptance check','Exposure uses entry delta notional; intrahorizon gamma-driven exposure changes are not resimulated', 'Three folds only; overlapping development data and correlated option candidates; bootstrap does not validate the generator'],validation=dict(put_call_parity='PASS',calendar_schema='PASS',candidate_count='PASS',causal_timestamps='PASS',synthetic_no_activation=all(not f['active'] for f in folds)),seconds=time.perf_counter()-started)
    assert result['validation']['synthetic_no_activation']
    (OUT/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'folds':[(f['status'],f['policy']) for f in folds],'aggregate':{k:{m:v[m] for m in ['total_return','net_profit_usd_on_adjusted_initial_capital','max_drawdown','sortino_per_period','trade_count','profit_factor']} for k,v in aggregate.items()},'seconds':result['seconds']}))
if __name__=='__main__':main()
