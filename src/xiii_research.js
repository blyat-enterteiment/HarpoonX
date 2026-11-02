'use strict';
function xiiiCompare(input){
 const report=xiiCompare(input);report.xiii_schema=HXIII.POLICY;
 if(!report.candidate)return report;
 const evidence=report.engine_contributions?.daily_candidate;
 report.gates.contribution_accounting=Boolean(evidence?.rows.length===252&&evidence.rows.every(d=>Number.isFinite(d.equity+d.etf)));
 report.gates.material_change=HXI.recipeKey(HLab.validate(input.trial.recipe))!==HXI.recipeKey(HLab.validate(input.trial.reference));
 report.status=Object.values(report.gates).every(Boolean)?'ACEPTADA':'RECHAZADA';
 report.reason=report.status==='ACEPTADA'?'Superó validación anual, prospectiva y contabilidad por motor.':Object.entries(report.gates).filter(([,v])=>!v).map(([k])=>k).join(' · ');
 report.allocation_basis='Comparación a igual riesgo de referencia. La asignación operativa XIII se reduce según evidencia observada; este replay no certifica su rendimiento adaptativo.';
 return report;
}

/** Completed adjacent sessions only. A missing day is never treated as zero return. */
function xiiiDaily(epoch,source,costsConfirmed,now=Date.now()){
 const rows=[],calendar=[...(epoch?.calendar||[])].filter(s=>s.close<now).sort((a,b)=>a.open-b.open),marks=epoch?.marks||{};
 const valid=(m,s)=>Boolean(m&&m.first<=s.open+600000&&m.last>=s.close-30000&&m.gap<=60000&&m.valid!==false&&Number.isFinite(m.nav)&&m.nav>0&&['equity','etf'].every(k=>Number.isFinite(m.pnl[k])&&Number.isInteger(m.closed[k])));
 let consecutive=[];
 for(let i=1;i<calendar.length;i++){
  const session=calendar[i],prior=calendar[i-1],m=marks[session.date],p=marks[prior.date];
  if(!valid(m,session)||!valid(p,prior)){consecutive=[];continue;}
  const d={day:session.date,capital:p.nav,equity:(m.pnl.equity-p.pnl.equity)/p.nav,etf:(m.pnl.etf-p.pnl.etf)/p.nav,equity_closes:m.closed.equity-p.closed.equity,etf_closes:m.closed.etf-p.closed.etf};
  if(d.equity_closes<0||d.etf_closes<0){consecutive=[];continue;}consecutive.push(d);
 }
 rows.push(...consecutive);
 return {schema:'HARPOON-XIII-DAILY-1',source,policy_id:epoch?.id||'sin-politica',rows,costs_confirmed:Boolean(costsConfirmed),through:rows.at(-1)?.day||'',basis:'Último tramo continuo de sesiones completas de una política. Fills y NAV bid con provisión de ejecución, incluidos días sin operaciones. No incluye impuestos ni asigna facturas externas a motores.'};
}
