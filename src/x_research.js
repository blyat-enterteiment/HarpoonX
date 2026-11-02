'use strict';
/** Daily marked portfolio with overlap, cash reservation and fixed risk constraints.
 * Orders inside the observed shadows are approximations, not broker executions. */
function xDailyPolicy(rows,days,model,cfg){
 if(cfg.replay_policy===HXI.POLICY)return xiPortfolio(rows,days,model,cfg);
 const profile=model?.profile||{...cfg.profile,reentry:cfg.x.manual_reentry},pi=model?.profile_index??3,returns=[],market=[],equities=[];
 let cash=cfg.starting_budget,budget=cash,reserve=0,peakProfit=0,settled=0,realized=0,priorEquity=cash,peakEquity=cash,halted=false,count=0;
 const positions=[],closed=[],booksPnl={equity:0,etf:0},audit={max_gross:0,max_open_risk:0,max_positions:0,rejected:0};
 const pclose=(position,ret,at)=>{cash+=position.nominal*(1+ret);realized+=position.nominal*ret;booksPnl[position.row.feature.book]+=position.nominal*ret;closed.push({symbol:position.row.feature.symbol,created:Date.parse(position.row.at),closed_at:iso(at),peak:position.row.feature.ask+position.outcome.mfe_r*position.lv.risk_unit,entry:position.row.feature.ask,closed:true,risk_spent:position.risk*(position.outcome.risk_weight??1),day:ny(at).day});positions.splice(positions.indexOf(position),1);};
 const settle=at=>{for(const p of [...positions])if(p.outcome.exit_at<=at)pclose(p,p.outcome.return,p.outcome.exit_at);};
 for(const day of days){
   const session=cfg.research_sessions?.[day],start=session?.open??HX.nyTime(day,'09:30'),end=session?.close??HX.nyTime(day,'16:00');
   settle(start);const nextPeak=Math.max(peakProfit,realized),newReserve=(nextPeak-peakProfit)*cfg.reserve_pct;reserve+=newReserve;peakProfit=nextPeak;
   budget=Math.max(0,Math.min(cfg.capital_limit,budget*cfg.growth_cap,budget+realized-settled-newReserve,priorEquity-reserve));settled=realized;
   const dayCash=Math.max(0,cash-reserve);let spent=0;
   const pool=rows.filter(r=>r.day===day&&r.valid&&r.outcomes?.[pi]).sort((a,b)=>a.at.localeCompare(b.at)||(b.score??0)-(a.score??0)||a.feature.symbol.localeCompare(b.feature.symbol));
   for(const r of pool){
     const at=Date.parse(r.at);if(!HXI.entryWindow(at,{date:day,open:start,close:end},cfg.close_minutes)||halted)continue;settle(at);
     const f=r.feature,lv=localLevels(f,{...cfg,profile}),o=r.outcomes[pi],history=closed.filter(c=>c.symbol===f.symbol&&ny(c.created).day===day);
     const quality=HX.quality(f,profile,cfg.x.min_dollar_volume,cfg.x.max_cost_r,lv,cfg.slippage_bps);
     const admitted=model?.recipe?HLab.eligible(f,model.recipe,cfg.breakout_pct,cfg.chase_pct):f.perf5>0&&f.rvol>=profile.min_rvol&&f.momentum_bps>=profile.momentum_bps&&f.ask>=5&&f.ask>=lv.trigger&&f.ask<=lv.trigger*(1+cfg.chase_pct);
     const selected=r.selection_cohort?localSelected(r.selection_cohort,profile).has(f.symbol):f.book==='equity';if(!selected||!admitted||f.spread_bps>cfg.max_spread_bps||quality.reasons.length||HX.reentry(f,history,at,Boolean(profile.reentry)))continue;
     if(model&&!model.rule_only){const p=predict(model,f);if(p.drift||p.value<profile.prediction_floor)continue;}
     if(positions.some(p=>p.row.feature.symbol===f.symbol||(f.book==='etf'&&p.row.feature.book==='etf'&&p.row.feature.factor===f.factor))||positions.length>=cfg.max_symbols){audit.rejected++;continue;}
     const gross=sum(positions.map(p=>p.nominal)),risk=sum(positions.map(p=>p.risk)),book=sum(positions.filter(p=>p.row.feature.book===f.book).map(p=>p.nominal)),factor=sum(positions.filter(p=>p.row.feature.factor===f.factor).map(p=>p.nominal*p.row.feature.leverage)),unit=lv.risk_unit/lv.limit+2*cfg.slippage_bps/10000;
     const nominal=Math.max(0,Math.min(cash-reserve,dayCash-spent,budget*cfg.symbol_pct,budget*cfg.gross_pct-gross,(budget*cfg.factor_pct-factor)/f.leverage,budget*(f.book==='etf'?cfg.etf_book_pct:cfg.equity_book_pct)-book,Math.min(budget*cfg.risk_pct-sum(history.map(c=>c.risk_spent)),budget*cfg.open_risk_pct-risk)/unit));
     if(nominal/lv.limit<cfg.min_plan_qty){audit.rejected++;continue;}
     cash-=nominal;spent+=nominal;positions.push({row:r,outcome:o,nominal,risk:nominal*unit,lv});
     if(o.filled)count++;
     audit.max_gross=Math.max(audit.max_gross,(gross+nominal)/budget);audit.max_open_risk=Math.max(audit.max_open_risk,(risk+nominal*unit)/budget);audit.max_positions=Math.max(audit.max_positions,positions.length);
   }
   settle(end);
   const marked=p=>{if(!Object.hasOwn(p.outcome.marks,day))throw Error('Falta marca diaria: no se rellena una posición abierta');return p.outcome.marks[day];};
   let equity=cash+sum(positions.map(p=>p.nominal*(1+marked(p))));peakEquity=Math.max(peakEquity,equity);
   if(equity<=peakEquity*(1-cfg.max_drawdown_pct)||equity<=priorEquity*(1-cfg.daily_loss_pct)){
     halted=equity<=peakEquity*(1-cfg.max_drawdown_pct);for(const p of [...positions])pclose(p,marked(p),end);
     equity=cash;
   }
   returns.push(priorEquity>0?equity/priorEquity-1:0);market.push(session?.market_return??0);equities.push(equity);priorEquity=equity;
   if(cash<-.001||!Number.isFinite(equity))throw Error('Contabilidad de replay inválida');
 }
 return {returns,market,count,equities,books:booksPnl,audit};
}
function xEvaluate(rows,days,cfg,champion,usedEnd,attempts){
 const result=evaluate(rows,days,cfg,champion,usedEnd,attempts);
 result.report.schema='HARPOON-XI-1';if(result.report.gates){result.report.gates.integer_event_model=cfg.replay_policy===HXI.POLICY;if(!result.report.gates.integer_event_model){result.candidate=null;result.report.status='SOLO DIAGNÓSTICO: MODELO DE EJECUCIÓN LEGACY';}}result.report.risk_policy='Mismos límites; efectivo, posiciones solapadas, reserva y capital entre sesiones.';
 result.report.basis='Sombras prospectivas con marcas al cierre y capital reservado; ejecución modelada por cotizaciones; cantidades enteras bajo política XI. No son fills ni rentabilidad realizada. Alfa contra SPY, no atribución multifactor.';
 if(!result.report.oos)return result;
 const external=Number(cfg.xi?.data_cost_total||0)+Number(cfg.xi?.infra_cost_total||0);result.report.gates.external_costs_declared=cfg.xi?.external_costs_confirmed===true;result.report.economic_estimate_usd=cfg.starting_budget*result.report.oos.net_return-external;result.report.gates.net_economic_positive=result.report.economic_estimate_usd>0;if(!result.report.gates.external_costs_declared||!result.report.gates.net_economic_positive){result.candidate=null;result.report.status='MODELO CONSERVADO: COSTES ECONÓMICOS';}
 const hold=cfg.mode==='live'?63:20,dev=days.slice(0,-hold-1),fold=cfg.mode==='live'?84:20,oosDays=dev.slice(-3*fold);
 const trials=[];for(const p of [0,1,2]){const train=rows.filter(r=>dev.slice(0,60).includes(r.day)&&r.end_at<oosDays[0]+'T00:00:00Z');if(train.length<100)continue;const model=fit(train,p),r=xDailyPolicy(rows,oosDays,model,cfg).returns,m=mean(r),v=mean(r.map(v=>(v-m)**2));if(v>1e-20)trials.push(m/Math.sqrt(v));}
 // DSR is an additional diagnostic; block-bootstrap gates remain mandatory.
 const selected=result.candidate||fit(rows.filter(r=>dev.slice(-60).includes(r.day)&&r.end_at<days.slice(-hold)[0]+'T00:00:00Z'),Math.max(0,PROFILES.findIndex(p=>p.name===result.report.folds.at(-1).profile)));
 const diagnostics=xDailyPolicy(rows,days.slice(-hold),selected,cfg);
 result.report.portfolio_audit=diagnostics.audit;
 result.report.book_attribution=diagnostics.books;
 result.report.dsr=HX.dsr(diagnostics.returns,trials,3*(attempts+1));
 result.report.dsr_scope='Diagnóstico aproximado en holdout; 20 sesiones de paper no permiten DSR. Los gates por bloques y multiplicidad controlan la promoción.';
 if(cfg.mode==='live'){
   const gate=result.report.dsr.probability!==null&&result.report.dsr.probability>=.95;
   result.report.gates.dsr_holdout=gate;
   if(!gate){result.candidate=null;result.report.status='MODELO CONSERVADO';}
 }
 return result;
}
