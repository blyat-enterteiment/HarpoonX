from pathlib import Path
import sys,json,importlib.util,inspect
import numpy as np
from scipy.special import ndtr
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reproduction'))
import harpoon_quant.optimization as op
s=importlib.util.spec_from_file_location('legacy',ROOT/'reproduction/simulate.py');legacy=importlib.util.module_from_spec(s);s.loader.exec_module(legacy)
source=inspect.getsource(legacy.generate).replace('def generate():','def state():').replace('return dict(days=days,opportunities=ops)','return dict(days=days,opportunities=ops),spot,iv,ret')
ns=vars(legacy).copy();exec(source,ns);w,spot,iv,ret=ns['state']()
source=inspect.getsource(op.replay).replace('"net_pnl_usd": lots','"lots": lots, "opportunity_id":o["id"], "net_pnl_usd": lots')
ns=vars(op).copy();exec(source,ns);trace=ns['replay'];byid={o['id']:o for o in w['opportunities']};trades=[];settings=dict(legacy.LIMITS,origin=legacy.ORIGIN)
for f in range(3):
 lo=240+f*60;run=trace(legacy.part(w,lo,lo+60),op.Policy(),settings)
 for trade in run['trades']:
  o=byid[trade['opportunity_id']];d,a,call=o['id'].split('-');d,a=int(d),int(a);call=call=='True';s=spot[d,a];v=iv[d,a];t=21/365;k=s*np.exp((1 if call else -1)*1.7*v*np.sqrt(t));s1=spot[d+3,a];v1=iv[d+3,a];n=trade['lots'];p0=float(legacy.bs(s,k,t,v,call));p1=float(legacy.bs(s1,k,18/365,v1,call));d1=(np.log(s/k)+(.04+.5*v*v)*t)/(v*np.sqrt(t));delta=float(ndtr(d1))-(0 if call else 1);density=np.exp(-d1*d1/2)/np.sqrt(2*np.pi);gamma=density/(s*v*np.sqrt(t));vega=s*density*np.sqrt(t);eps=1e-5;theta=(float(legacy.bs(s,k,t-eps,v,call))-float(legacy.bs(s,k,t+eps,v,call)))/(2*eps)/365
  attrib={'delta_usd':delta*(s1-s)*100*n,'gamma_usd':.5*gamma*(s1-s)**2*100*n,'vega_usd':vega*(v1-v)*100*n,'theta_usd':theta*3*100*n};midpnl=(p1-p0)*100*n;attrib['residual_usd']=midpnl-sum(attrib.values());cost=midpnl-trade['net_pnl_usd'];spread=.08+.04*(v>.9)
  path_pnl=[n*(value-o['funding_per_lot']) for value in o['wealth_by_day'].values()]
  trades.append(dict(MFE_daily_curve_usd=max(0,max(path_pnl)),MAE_daily_curve_usd=min(0,min(path_pnl)),hindsight_exit_gap_usd=max(0,max(path_pnl)-trade['net_pnl_usd']),**trade,entry_at=o['at'],exit_at=o['label_end'],underlying=f'SYNTH{a:02}',call=call,entry_delta=delta,entry_mid=p0,exit_mid=p1,funding_per_lot=o['funding_per_lot'],edge_at_decision=o['robust_edge_per_lot'],break_even_option_mid_at_exit=(o['funding_per_lot']+.65)/(100*(1-spread/2)),gross_mid_pnl_usd=midpnl,actual_modeled_friction_usd=cost,attribution=attrib))
positive=[o for o in w['opportunities'] if o['robust_edge_per_lot']>0]
summary=dict(origin=legacy.ORIGIN,trades=trades,total_net=sum(t['net_pnl_usd'] for t in trades),gross_mid=sum(t['gross_mid_pnl_usd'] for t in trades),modeled_friction=sum(t['actual_modeled_friction_usd'] for t in trades),attribution={k:sum(t['attribution'][k] for t in trades) for k in trades[0]['attribution']},universe=dict(candidates=len(w['opportunities']),positive_edge=len(positive),positive_edge_premium_within_50=sum(o['funding_per_lot']<=50 for o in positive)),scope='15 historical synthetic exits with independent fold capital resets; sums are dollar P&L across folds, not normalized compounded index P&L.')
summary['exit_diagnostic']=dict(sum_positive_MFE_usd=sum(t['MFE_daily_curve_usd'] for t in trades),sum_hindsight_exit_gap_usd=sum(t['hindsight_exit_gap_usd'] for t in trades),scope='Ex-post daily synthetic liquidation marks, includes weekends in legacy generator; not executable gains or a usable exit rule.')
losses=sorted([t for t in trades if t['net_pnl_usd']<0],key=lambda t:t['net_pnl_usd']);top=losses[:max(1,int(np.ceil(.2*len(trades))))]
summary['pareto_losses']=dict(top_ids=[t['opportunity_id'] for t in top],top_loss_usd=-sum(t['net_pnl_usd'] for t in top),share_of_gross_losses=-sum(t['net_pnl_usd'] for t in top)/(-sum(t['net_pnl_usd'] for t in losses)))
assert abs(summary['gross_mid']-summary['modeled_friction']-summary['total_net'])<1e-9
assert abs(sum(summary['attribution'].values())-summary['gross_mid'])<1e-9
(ROOT/'evidence/legacy_forensic.json').write_text(json.dumps(summary,indent=2))
print(json.dumps({k:v for k,v in summary.items() if k!='trades'}))
