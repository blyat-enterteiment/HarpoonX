'use strict';
/* Fixed, bounded experiment. No order API and no automatic promotion. */
function agentStudy25(data,base,baselinePlugin){
 const cfg=HC19.validate({...base}),n=data['BTC/USD']?.length||0;
 if(n<938)throw Error('Faltan 938 días completos comunes para validación walk-forward nativa');
 const report=HC19.walkForward(data,cfg),candidate={...baselinePlugin,id:baselinePlugin.id.slice(0,45)+'-a25-'+String(data['BTC/USD'].at(-1).t),version:'1.1.0',binding:'fixed',family:'trend_xix',name:'Ensayo agéntico · '+report.selected,params:{entryDays:report.config.entry_days,exitDays:report.config.exit_days,atrDays:report.config.atr_days,atrMultiple:report.config.atr_multiple,holdHours:report.config.hold_hours}};
 const validated=HXX.validate(candidate),baseline=HC19.replay(data,cfg,n-180,n),trial=HC19.replay(data,report.config,n-180,n),changes=Object.keys(report.config).filter(k=>report.config[k]!==cfg[k]).map(k=>({field:k,before:cfg[k],after:report.config[k]}));
 return {schema:'HARPOON-AGENT-STUDY-25-1',source:'HISTORICAL_REPLAY',status:report.status,through:data['BTC/USD'].at(-1).t,attempts:report.attempts,changes,candidate:validated,
  comparison:{baseline:baseline.metrics,candidate:trial.metrics,netDelta:trial.metrics.net-baseline.metrics.net,sharpeDelta:trial.metrics.sharpe!=null&&baseline.metrics.sharpe!=null?trial.metrics.sharpe-baseline.metrics.sharpe:null},report,
  acceptedForResearch:report.status==='CANDIDATA PARA PAPER',promoted:false,ordersEnabled:false,
  reason:'Prueba histórica nativa; requiere datos prospectivos independientes y autorización de despliegue. No cambia plugins activos.',costUsd:0,tokens:0};
}
