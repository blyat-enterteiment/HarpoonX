'use strict';
/** Same calendar, tranche allocator, canonical selection and risk limits as execution.
 * Quote-touch fills remain a model: no queue priority, auction or broker latency claim. */
function xiPortfolio(rows,days,model,cfg){
 const profile=model?.profile||cfg.profile,calendar=Object.entries(cfg.research_sessions||{}).map(([date,s])=>({date,open:s.open,close:s.close})),events=[],quotes={},positions=[],closed=[],returns=[],market=[],equities=[],daily_evidence=[],priorBooks={equity:0,etf:0},priorCounts={equity:0,etf:0},books={equity:0,etf:0};
 const audit={max_gross:0,max_open_risk:0,max_positions:0,rejected:0,integer_quantities:true,intraday_risk:true,policy:HXI.POLICY,invalid_quotes:0,modeled_fills:true};
 let cash=cfg.starting_budget,budget=cash,reserve=0,realized=0,settled=0,peakProfit=0,priorEquity=cash,peakEquity=cash,count=0,halted=false,dayHalt=false,spent=0,dayCash=cash;
 const qmap=new Map();
 for(const row of rows){if(!days.includes(row.day)||!row.valid)continue;events.push({at:Date.parse(row.at),kind:'signal',row});for(const q of row.quote_path||[]){const key=row.feature.symbol+':'+q.received;qmap.set(key,{at:q.received,kind:'quote',symbol:row.feature.symbol,q});}}
 events.push(...qmap.values());events.sort((a,b)=>a.at-b.at||Number(a.kind==='signal')-Number(b.kind==='signal')||((b.row?.score||0)-(a.row?.score||0))||(a.symbol||a.row?.feature.symbol||'').localeCompare(b.symbol||b.row?.feature.symbol||''));let cursor=0;
 const marked=p=>p.nominal*(1+HX.marked(p.shadow,quotes[p.row.feature.symbol]?.bid??p.shadow.lastBid));
 const nav=()=>cash+sum(positions.map(marked));
 const close=p=>{const o=HX.outcome(p.shadow);cash+=p.nominal*(1+o.return);realized+=p.nominal*o.return;books[p.row.feature.book]+=p.nominal*o.return;if(o.filled)count++;closed.push({book:p.row.feature.book,symbol:p.row.feature.symbol,created:Date.parse(p.row.at),closed_at:iso(o.exit_at),peak:p.shadow.peak,entry:p.shadow.entry,closed:true,risk_spent:p.risk*o.risk_weight,day:p.row.day});positions.splice(positions.indexOf(p),1);};
 for(const day of days){
  const session=calendar.find(s=>s.date===day);if(!session)throw Error('Falta calendario para replay XI');
  const peak=Math.max(peakProfit,realized),addReserve=(peak-peakProfit)*cfg.reserve_pct;reserve+=addReserve;peakProfit=peak;budget=Math.max(0,Math.min(cfg.capital_limit,budget*cfg.growth_cap,budget+realized-settled-addReserve,priorEquity-reserve));settled=realized;dayCash=Math.max(0,cash-reserve);spent=0;dayHalt=false;
  while(cursor<events.length&&events[cursor].at<session.open)cursor++;
  while(cursor<events.length&&events[cursor].at<=session.close){
   const ev=events[cursor++];
   if(ev.kind==='quote'){
    const batch=[ev];while(cursor<events.length&&events[cursor].at===ev.at&&events[cursor].kind==='quote')batch.push(events[cursor++]);const updated=new Set();
    for(const event of batch){const q=event.q;if(!(q.bid>0&&q.ask>=q.bid&&q.received-q.at<=15000&&q.at<=q.received+2000)){audit.invalid_quotes++;continue;}quotes[event.symbol]=q;updated.add(event.symbol);}
    for(const p of [...positions])if(updated.has(p.row.feature.symbol)){const q=quotes[p.row.feature.symbol];HX.stepShadow(p.shadow,q,day,calendar,(ask,bid)=>localLevels({...p.row.feature,base:p.row.feature.ask,ask,bid},{...cfg,profile}));if(!p.shadow.valid)throw Error('Hueco de observación en cartera XI');if(p.shadow.done)close(p);}
    const value=nav();peakEquity=Math.max(peakEquity,value);
    if(value<=priorEquity*(1-cfg.daily_loss_pct)||value<=peakEquity*(1-cfg.max_drawdown_pct)){
     dayHalt=true;halted||=value<=peakEquity*(1-cfg.max_drawdown_pct);
     for(const p of [...positions]){const last=quotes[p.row.feature.symbol];if(!last||ev.at-last.at>15000)throw Error('No se puede simular cierre de riesgo con precio vencido');HX.finishShadow(p.shadow,{...last,received:ev.at},'LÍMITE DE RIESGO INTRADÍA');close(p);}
    }
    continue;
   }
   if(halted||dayHalt||!HXI.entryWindow(ev.at,session,cfg.close_minutes))continue;
   const r=ev.row,f=r.feature,lv=localLevels(f,{...cfg,profile}),history=closed.filter(c=>c.symbol===f.symbol&&c.day===day),selected=r.selection_cohort?localSelected(r.selection_cohort,profile).has(f.symbol):f.book==='equity';
   const eligible=model?.recipe?HLab.eligible(f,model.recipe,cfg.breakout_pct,cfg.chase_pct):f.perf5>0&&f.rvol>=profile.min_rvol&&f.momentum_bps>=profile.momentum_bps&&f.ask>=5&&f.ask>=lv.trigger&&f.ask<=lv.trigger*(1+cfg.chase_pct);
   if(!selected||!eligible||f.spread_bps>cfg.max_spread_bps||HX.quality(f,profile,cfg.x.min_dollar_volume,cfg.x.max_cost_r,lv,cfg.slippage_bps).reasons.length||HX.reentry(f,history,ev.at,Boolean(profile.reentry)))continue;
   if(profile.selection_filter==='ridge_lcb'&&!HXII.selection(f,model?.selection_model,ev.at).eligible)continue;
   if(model&&!model.rule_only){const p=predict(model,f);if(p.drift||p.value<profile.prediction_floor)continue;}
   if(positions.some(p=>p.row.feature.symbol===f.symbol||(f.book==='etf'&&p.row.feature.book==='etf'&&p.row.feature.factor===f.factor))||positions.length>=cfg.max_symbols){audit.rejected++;continue;}
   const gross=sum(positions.map(p=>p.nominal)),risk=sum(positions.map(p=>p.risk)),book=sum(positions.filter(p=>p.row.feature.book===f.book).map(p=>p.nominal)),factor=sum(positions.filter(p=>p.row.feature.factor===f.factor).map(p=>p.nominal*p.row.feature.leverage)),unit=lv.risk_unit+2*lv.limit*cfg.slippage_bps/10000;
   const cluster=cfg.xii?HXII.clusterRoom(f,positions.map(p=>({symbol:p.row.feature.symbol,factor:p.row.feature.factor,leverage:p.row.feature.leverage,nominal:p.nominal,risk:p.risk})),budget,cfg.xii.cluster_exposure_pct,cfg.xii.cluster_risk_pct):null;
   const qty=Math.floor(Math.max(0,Math.min(cluster?cluster.nominal/(f.leverage*lv.limit):Infinity,cluster?cluster.risk/unit:Infinity,(cash-reserve)/lv.limit,(dayCash-spent)/lv.limit,budget*cfg.symbol_pct/lv.limit,(budget*cfg.gross_pct-gross)/lv.limit,(budget*cfg.factor_pct-factor)/(f.leverage*lv.limit),(budget*(f.book==='etf'?cfg.etf_book_pct:cfg.equity_book_pct)-book)/lv.limit,Math.min(budget*cfg.risk_pct-sum(history.map(c=>c.risk_spent)),budget*cfg.open_risk_pct-risk)/unit))+1e-9);
   if(qty<cfg.min_plan_qty){audit.rejected++;continue;}
   const deadline=HX.deadline(ev.at,profile.hold_hours??cfg.x.hold_hours,calendar,cfg.close_minutes);
   if(deadline>calendar.at(-1).close)continue;
   const nominal=qty*lv.limit,shadow=HX.newShadow({...f,asof:r.at},lv,profile,deadline,cfg.slippage_bps,qty);cash-=nominal;spent+=nominal;positions.push({row:r,nominal,risk:qty*unit,shadow});quotes[f.symbol]??={bid:f.bid,ask:f.ask,at:ev.at,received:ev.at};
   audit.max_gross=Math.max(audit.max_gross,(gross+nominal)/Math.max(1,budget));audit.max_open_risk=Math.max(audit.max_open_risk,(risk+qty*unit)/Math.max(1,budget));audit.max_positions=Math.max(audit.max_positions,positions.length);
  }
  for(const p of positions){const q=quotes[p.row.feature.symbol];if(!q||q.received<session.close-30000)throw Error('Falta marca de cierre XI');}
  const equity=nav();if(!Number.isFinite(equity)||cash<-.001)throw Error('Contabilidad XI inválida');const bookPnl=key=>books[key]+sum(positions.filter(p=>p.row.feature.book===key).map(p=>marked(p)-p.nominal)),eq=bookPnl('equity'),et=bookPnl('etf'),ec=closed.filter(c=>c.book==='equity').length,tc=closed.filter(c=>c.book==='etf').length;daily_evidence.push({day,capital:priorEquity,equity:(eq-priorBooks.equity)/priorEquity,etf:(et-priorBooks.etf)/priorEquity,equity_closes:ec-priorCounts.equity,etf_closes:tc-priorCounts.etf});priorBooks.equity=eq;priorBooks.etf=et;priorCounts.equity=ec;priorCounts.etf=tc;returns.push(priorEquity>0?equity/priorEquity-1:0);market.push(cfg.research_sessions[day].market_return);equities.push(equity);priorEquity=equity;
 }
 if(positions.length)throw Error('La ventana invade etiquetas abiertas; aplica purga');
 return {returns,market,count,equities,books,audit,daily_evidence};
}

function xiAttachPaths(rows,events){
 const paths=new Map();for(const e of events){if(e.kind!=='COTIZACIONES')continue;const received=Date.parse(e.at);for(const [symbol,at,bid,ask]of e.data.quotes||[]){if(!paths.has(symbol))paths.set(symbol,[]);paths.get(symbol).push({at,bid,ask,received});}}
 for(const path of paths.values())path.sort((a,b)=>a.received-b.received);
 return rows.map(r=>{const path=paths.get(r.feature.symbol)||[],start=Date.parse(r.at),end=Date.parse(r.end_at);let lo=0,hi=path.length;while(lo<hi){const m=(lo+hi)>>1;if(path[m].received<start)lo=m+1;else hi=m;}const out=[];for(let i=lo;i<path.length&&path[i].received<=end+30000;i++)out.push(path[i]);return {...r,quote_path:out};});
}
