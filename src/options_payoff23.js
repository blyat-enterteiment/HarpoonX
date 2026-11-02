'use strict';
// Additive presentation/research module. No broker transport and no trading authority.
const H23Payoff = Object.freeze({
 validate(p){
  if(!p||p.schema!=='HARPOON-OPTION-PAYOFF-PLUGIN-1'||p.book!=='options'||p.orders_enabled!==false||p.evidence!=='UNVALIDATED'||!Array.isArray(p.legs)||p.legs.length<1||p.legs.length>2)throw Error('Contrato de sandbox inválido');
  if(Object.keys(p).sort().join(',')!=='book,description,evidence,id,legs,name,orders_enabled,parameters,schema,sha256,version')throw Error('Campos no permitidos');
  if(!/^[a-z][a-z0-9-]{2,70}$/.test(p.id)||p.version!=='1.0.0')throw Error('Identidad no válida');
  const a=p.parameters;if(Object.keys(a).sort().join(',')!=='max_dte,min_dte,spread_width_pct'||!Number.isInteger(a.min_dte)||!Number.isInteger(a.max_dte)||a.min_dte<1||a.max_dte<a.min_dte||a.max_dte>90||!Number.isFinite(a.spread_width_pct)||a.spread_width_pct<=0||a.spread_width_pct>.25)throw Error('Parámetros no válidos');
  for(const l of p.legs)if(Object.keys(l).sort().join(',')!=='kind,qty,strike'||!['call','put'].includes(l.kind)||![1,-1].includes(l.qty)||!['atm','upper'].includes(l.strike))throw Error('Pata no válida');
  if(p.legs.some(l=>l.qty<0)&&!(p.legs.length===2&&p.legs[0].kind==='call'&&p.legs[0].qty===1&&p.legs[0].strike==='atm'&&p.legs[1].kind==='call'&&p.legs[1].qty===-1&&p.legs[1].strike==='upper'))throw Error('Venta sin cobertura');
  return structuredClone(p);
 },
 evaluate(raw,input){
  const p=this.validate(raw),{spot,call,put,upper,cost}=input;
  if(![spot,call,put,upper,cost].every(Number.isFinite)||spot<=0||spot>1e6||[call,put,upper,cost].some(v=>v<0||v>1e6))throw Error('Precios/costes fuera de rango');
  const legs=p.legs.map(l=>({...l,k:spot*(l.strike==='upper'?1+p.parameters.spread_width_pct:1),premium:l.strike==='upper'?upper:l.kind==='put'?put:call}));
  const debit=legs.reduce((s,l)=>s+l.qty*l.premium,0)*100;
  if(debit<=0)throw Error('Se requiere débito positivo');
  if(legs.some(l=>l.qty<0)&&debit>=spot*p.parameters.spread_width_pct*100)throw Error('El débito debe ser menor que la anchura del spread');
  const scenarios=[-.2,-.1,-.05,0,.05,.1,.2].map(change=>{const price=spot*(1+change);const intrinsic=legs.reduce((s,l)=>s+l.qty*Math.max(l.kind==='call'?price-l.k:l.k-price,0)*100,0);return {spot_change:change,spot_at_expiry:price,net_pnl:intrinsic-debit-cost};});
  return {kind:'HYPOTHETICAL_EXPIRY_PAYOFF',plugin:p.id,contracts:1,multiplier_assumed:100,initial_debit:debit,estimated_all_costs:cost,worst_expiry_loss:debit+cost,scenarios,profitability_verified:false,orders_sent:0,paid_tokens:0,notice:'Escenarios al vencimiento, no backtest, distribución ni predicción. No modela ejercicio/asignación, dividendos, IV ni salida anticipada.'};
 }
});

const OPTIONS23_PRELOAD=[{"schema":"HARPOON-OPTION-PAYOFF-PLUGIN-1","id":"options-bull-call-spread","version":"1.0.0","name":"Spread alcista de débito","book":"options","description":"Prima y beneficio limitado por strike superior; plugin de payoff local, no ejecutor.","orders_enabled":false,"evidence":"UNVALIDATED","parameters":{"min_dte":7,"max_dte":45,"spread_width_pct":0.05},"legs":[{"kind":"call","qty":1,"strike":"atm"},{"kind":"call","qty":-1,"strike":"upper"}],"sha256":"f69343d55914002f55c7eb7e4ac78fce1078378496a2667d64b035fa47a8a59a"},{"schema":"HARPOON-OPTION-PAYOFF-PLUGIN-1","id":"options-long-call","version":"1.0.0","name":"Call comprada","book":"options","description":"Convexidad alcista; plugin de payoff local, sin adaptador de órdenes de contratos.","orders_enabled":false,"evidence":"UNVALIDATED","parameters":{"min_dte":7,"max_dte":45,"spread_width_pct":0.05},"legs":[{"kind":"call","qty":1,"strike":"atm"}],"sha256":"3e115a9c88d1cd72926080953921cddd1cd33ff97d9567ed3961ffc0686b3da3"},{"schema":"HARPOON-OPTION-PAYOFF-PLUGIN-1","id":"options-long-straddle","version":"1.0.0","name":"Straddle comprado","book":"options","description":"Movimiento amplio en cualquiera de las direcciones; exige superar ambas primas. Sandbox, no señal de beneficio probado.","orders_enabled":false,"evidence":"UNVALIDATED","parameters":{"min_dte":7,"max_dte":45,"spread_width_pct":0.05},"legs":[{"kind":"call","qty":1,"strike":"atm"},{"kind":"put","qty":1,"strike":"atm"}],"sha256":"91b908bd1a0d81230ce5aae6ef9a2f4cc975b3181d65aa4e094a39cbaf9cdac9"}];
