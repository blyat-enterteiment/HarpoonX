"""Descriptive audit on existing archived results; no new strategy backtest."""
import gzip,json,sys,time,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'quant'))
from harpoon_quant.vector_gate import allocate

paths=sorted((ROOT/'evidence/macd30/run_01').glob('*.json.gz'))+sorted((ROOT/'evidence/swing8/run_01').glob('*.json.gz'))
columns={};scalars={};hashes={}
for p in paths:
    if 'CASH' in p.name:continue
    a=json.loads(gzip.decompress(p.read_bytes()));group='MACD_' if 'macd30' in str(p) else 'SWING_'
    key=group+p.stem.removesuffix('.json');hashes[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
    dates=[r['day'] for r in a['curve']];e=np.array([a['initial_usd']]+[r['equity'] for r in a['curve']]);columns[key]=(dates,np.diff(np.log(e)))
    pnl=np.array([t['net_usd'] for t in a['trades']]);win=pnl[pnl>0];loss=-pnl[pnl<0]
    n=len(pnl);w=float(win.mean()) if len(win) else 0;l=float(loss.mean()) if len(loss) else 0
    scalars[key]={'trades':n,'hit_rate':float((pnl>0).mean()) if n else None,'mean_winner_after_variables_usd':w,
        'mean_loser_after_variables_usd':l,'fixed_usd_per_closed_trade':a['fixed_cost_usd']/n if n else None,
        'breakeven_hit_rate_including_fixed':(l+a['fixed_cost_usd']/n)/(w+l) if n and w+l>0 else None,
        'required_mean_winner_at_current_hit_rate_usd':((1-float((pnl>0).mean()))*l+a['fixed_cost_usd']/n)/float((pnl>0).mean()) if n and (pnl>0).any() else None,
        'maximum_mean_loser_at_current_hit_rate_usd':(float((pnl>0).mean())*w-a['fixed_cost_usd']/n)/(1-float((pnl>0).mean())) if n and (pnl<=0).any() else None,
        'net_usd':a['net_usd'],'scope':'DESCRIPTIVE_EQUAL_TRADE_COUNT_WEIGHT_NOT_PREDICTIVE_CALIBRATION'}
names=sorted(k for k in columns if 'NOMINAL_' in k);days=columns[names[0]][0]
assert all(columns[k][0]==days for k in columns)
tensor=np.stack([np.column_stack([columns[k.replace('NOMINAL_','STRESS_') if scenario else k][1] for k in names]) for scenario in (0,1)],axis=2)
x=tensor[:,:,0];centered=x-x.mean(axis=0);s=np.linalg.svd(centered,compute_uv=False);v=s*s;prob=v/v.sum()
rank=int(np.sum(s>s[0]*1e-8));entropy_rank=float(np.exp(-np.sum(prob[prob>0]*np.log(prob[prob>0]))))
# Synthetic engineering contrast; not trained on archived trading results.
p=np.empty((40,2,1));p[:,0,0]=np.tile([-100,120],20);p[:,1,0]=np.tile([120,-100],20)
args=dict(funding=[100,100],variable=[[0],[0]],activation=[[0],[0]],shared=[0],max_lots=[1,1],equity=10000,cash=1000,risk_limit=500)
t=time.perf_counter();receipt=allocate(p,**args);wall=time.perf_counter()-t
report={'schema':'HARPOON_VECTOR_ADVERSARIAL_1','scalars':scalars,'tensor_shape':list(tensor.shape),
 'tensor_scope':'DEPENDENCE_DIAGNOSTIC_OF_SEPARATE_FUNDED_CURVES_NOT_INVESTABLE_LOT_PNL',
 'names':names,'nominal_matrix_rank':rank,'nominal_effective_spectral_rank':entropy_rank,
 'nominal_first_component_variance_fraction':float(prob[0]),'synthetic_engineering_only':receipt,
 'synthetic_exact_grid_wall_seconds':wall,'input_sha256':hashes,'level8_accredited':False,
 'economic_improvement_demonstrated':False,'new_strategy_trials':0,'new_market_data':0}
out=ROOT/'evidence/vector_core';(out/'audit.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
print(json.dumps({'tensor_shape':report['tensor_shape'],'rank':rank,'effective_rank':entropy_rank,'first_component':float(prob[0]),'synthetic_lots':receipt['lots']}))
for key in ('MACD_NOMINAL_EARLY','SWING_NOMINAL_GAP'):
    print(key,scalars[key])
