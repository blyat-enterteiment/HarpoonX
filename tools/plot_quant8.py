#!/usr/bin/env python3
"""Plot sealed observed-historical/modelled-execution curves; no model evaluation."""
import json
import os
from datetime import datetime
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR','/tmp/harpoon_quant8_matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1];E=ROOT/'evidence/core_quant8_30_17_0'
reports=json.loads((E/'run_completed/reports.json').read_text())
fig,axs=plt.subplots(2,1,figsize=(12,8),sharex=True)
colors={'C0':'#9c3848','RIDGE':'#777777','SVR':'#bf8f3f','RIDGE_HURDLE':'#156f91','CASH':'#292b4b'}
for ax,scenario in zip(axs,['NOMINAL','STRESS']):
 for policy,color in colors.items():
  d=json.loads((E/'run_completed'/reports[scenario+':'+policy]).read_text());c=d['curve']
  x=[datetime.fromisoformat(r['session_id']) for r in c];y=[r['equity_end_usd']-20000 for r in c]
  ax.plot(x,y,label=policy if policy!='CASH' else 'CASH = Huber = Huber + régimen',color=color,linewidth=2 if policy in ['RIDGE_HURDLE','CASH'] else 1.2)
 ax.axhline(0,color='#555555',linestyle=':',label='Efectivo fuera del sistema (sin gasto/interés)')
 ax.set_title(scenario);ax.set_ylabel('PnL neto modelado (USD)');ax.grid(alpha=.15)
axs[0].legend(loc='lower left',fontsize=8,ncol=2)
fig.suptitle('HARPOON 30.17.0 · No se acredita ventaja neta\nCuenta continua de 20.000 USD · Datos históricos; ejecuciones y costes modelados',fontsize=13)
fig.tight_layout();fig.savefig(E/'analysis/curvas_quant8.png',dpi=150)
