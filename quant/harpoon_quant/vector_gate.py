"""Exact bounded research allocation on aligned original PnL tensors, not a broker.

Input T x N x S is gross USD per integer lot, same horizon and original dates.
No bootstrap replication, leveraged full-account curves or mixed units permitted.
"""
from itertools import product
import math
import numpy as np
from .core import expected_shortfall,digest


def hac_covariance(x,lag=5):
    x=np.asarray(x,dtype=float)
    if x.ndim!=2 or len(x)<20 or not np.isfinite(x).all():raise ValueError('ORIGINAL_FINITE_T_BY_N_REQUIRED')
    if type(lag) is not int or not 0<=lag<len(x):raise ValueError('HAC_LAG')
    n=len(x);z=x-x.mean(axis=0);iid=z.T@z/(n-1)
    long=z.T@z/n
    for k in range(1,lag+1):
        gamma=z[k:].T@z[:-k]/n;long+=(1-k/(lag+1))*(gamma+gamma.T)
    # PSD floor in Loewner order: V >= IID and V >= raw HAC, unlike elementwise clipping.
    values,vectors=np.linalg.eigh((long-iid+long.T-iid.T)/2)
    cov=iid+(vectors*np.maximum(values,0))@vectors.T
    return (cov+cov.T)/(2*n)


def allocate(panel,*,funding,variable,activation,shared,max_lots,equity,cash,
             risk_limit,max_positions=3,z=3.,lag=5,budget=50000,limits=None):
    p=np.asarray(panel,dtype=float);fund=np.asarray(funding,dtype=float)
    var=np.asarray(variable,dtype=float);fixed=np.asarray(activation,dtype=float);over=np.asarray(shared,dtype=float)
    caps=np.asarray(max_lots)
    if p.ndim!=3 or not 20<=p.shape[0]<=2000 or not 1<=p.shape[1]<=6 or not 1<=p.shape[2]<=8:raise ValueError('TENSOR_DOMAIN')
    t,n,s=p.shape
    if fund.shape!=(n,) or var.shape!=(n,s) or fixed.shape!=(n,s) or over.shape!=(s,) or caps.shape!=(n,):raise ValueError('DIMENSION_OR_UNITS')
    if not all(np.isfinite(a).all() for a in (p,fund,var,fixed,over,caps)):raise ValueError('NONFINITE')
    if (fund<=0).any() or (var<0).any() or (fixed<0).any() or (over<0).any() or (caps<0).any() or (caps!=np.floor(caps)).any() or caps.dtype.kind=='b':raise ValueError('COST_OR_LOT_DOMAIN')
    if any(isinstance(a,(bool,np.bool_)) for a in (equity,cash,risk_limit,z)) or not all(math.isfinite(a) for a in (equity,cash,risk_limit,z)) or equity<=0 or cash<0 or not 0<risk_limit<equity or z<0:raise ValueError('ACCOUNT_DOMAIN')
    if type(max_positions) is not int or not 1<=max_positions<=6 or type(budget) is not int or not 1<=budget<=50000:raise ValueError('COMPUTE_BUDGET')
    count=math.prod(int(x)+1 for x in caps)
    if count>budget:raise ValueError('ENUMERATION_BUDGET_EXCEEDED')
    if count*t*n*s>20000000:raise ValueError('TENSOR_ENUMERATION_WORK_BUDGET')
    A,b=(np.zeros((0,n)),np.zeros(0)) if limits is None else map(lambda v:np.asarray(v,dtype=float),limits)
    if A.ndim!=2 or A.shape[1]!=n or b.shape!=(len(A),) or not np.isfinite(A).all() or not np.isfinite(b).all() or (b<0).any():raise ValueError('LINEAR_LIMIT_DOMAIN')
    cov=np.stack([hac_covariance(p[:,:,j],lag) for j in range(s)])
    def evaluate(q):
        active=q>0
        if active.sum()>max_positions or np.any(A@q>b+1e-9):return None
        # Reserve worst scenario's variable and activation costs, including exit provision.
        reserve=float(np.max(var.T@q+fixed.T@active))
        if fund@q+reserve+over.max()>cash+1e-9:return None
        costs=var.T@q+fixed.T@active+over
        pnl=np.einsum('tns,n->ts',p,q)-costs
        if (equity+pnl<=0).any():return None
        # Every partial-fill subset is bounded by dropping each unfilled leg's gains.
        partial=np.einsum('tns,n->ts',np.minimum(p-var[None,:,:],0),q)-fixed.T@active-over
        tail=max(expected_shortfall(-partial[:,j],.95) for j in range(s))
        if tail>risk_limit+1e-9:return None
        se=np.sqrt(np.maximum(np.einsum('i,sij,j->s',q,cov,q),0))
        lower=pnl.mean(axis=0)-z*se
        score=float(np.min(np.log1p(pnl/equity).mean(axis=0)-z*se/equity))
        return {'score':score,'lower_net_usd':lower.tolist(),'mean_net_usd':pnl.mean(axis=0).tolist(),
                'partial_fill_cvar_usd':float(tail),'reserved_funding_usd':float(fund@q+reserve+over.max())}
    zero=np.zeros(n,dtype=int);baseline=evaluate(zero)
    if baseline is None:raise ValueError('CASH_REFERENCE_INFEASIBLE')
    best=baseline;chosen=zero;feasible=0
    for values in product(*(range(int(v)+1) for v in caps)):
        q=np.asarray(values,dtype=int);result=evaluate(q)
        if result is None:continue
        feasible+=1
        # An improvement relative to loss-making CASH alone is insufficient.
        if min(result['lower_net_usd'])<=0:continue
        if result['score']>best['score']+1e-14:best=result;chosen=q
    recheck=evaluate(chosen)
    if recheck!=best:raise ArithmeticError('REPRICING_MISMATCH')
    return {'schema':'HARPOON_VECTOR_GATE_1','lots':chosen.tolist(),'certificate':best,
            'cash_reference':baseline,'enumerated':count,'feasible':feasible,
            'optimality_scope':'EXACT_FINITE_REGISTERED_GRID_WITH_POSITIVE_LOWER_NET_GATE',
            'mean_covariance':cov.tolist(),'input_sha256':digest({'panel':p.tolist(),'funding':fund.tolist(),
                'variable':var.tolist(),'activation':fixed.tolist(),'shared':over.tolist(),'caps':caps.tolist(),
                'equity':equity,'cash':cash,'risk_limit':risk_limit,'z':z,'lag':lag,'A':A.tolist(),'b':b.tolist()}),
            'execution_allowed':False,'liveApproved':False,'level8_accredited':False,
            'limitations':['CONDITIONAL_INPUT_DISTRIBUTION','NOT_GLOBAL_STRATEGY_SEARCH_CORRECTION',
                           'NO_HOLDINGS_ADOPTION','NO_AUTHENTICATION_OF_INPUT_ORIGINALITY']}
