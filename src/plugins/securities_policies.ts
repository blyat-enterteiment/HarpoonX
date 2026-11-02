namespace HPPolicy {
 type Profile=HX.Profile;type Feature=HX.Feature;type Levels=HX.Levels;type ExitHistory=HX.ExitHistory;type Shadow=HX.Shadow;type Quote=HX.Quote;type Session=HX.Session;
 const finite=(x:number)=>Number.isFinite(x);
 const tradingMillis=(a:number,b:number,c:Session[])=>HX.tradingMillis(a,b,c);
 const finishShadow=(s:Shadow,q:Quote,r:string)=>HX.finishShadow(s,q,r);
 const marked=(s:Shadow,b:number)=>HX.marked(s,b);
export function parts(q: number, profile: Profile): number[] {
    if (!Number.isInteger(q)||q<4) throw Error('Tramo menor de cuatro títulos');
    if(profile.astra){const f=profile.astra.partialFraction;if(!(f>=0&&f<=.35))throw Error('ASTRA: fracción inválida');const a=f===0?0:Math.max(1,Math.floor(q*f));return [a,0,q-a];}
    const f=profile.tp1_fraction??.25,g=profile.tp2_fraction??.25;
    if (!(f>=HContract.min_partial&&g>=HContract.min_partial&&f+g<=HContract.partial_max)) throw Error('Reparto de parciales inválido');
    const a=Math.max(1,Math.floor(q*f)),b=profile.exit_layout==='single_target'?0:Math.max(1,Math.floor(q*g));
    return [a,b,q-a-b];
  }
export function reentry(f: Feature, history: ExitHistory[], now: number, enabled: boolean): string | null {
    if (!history.length) return null;
    if (history.some(c=>!c.closed)) return 'POSICIÓN ABIERTA';
    if (!enabled) return 'REENTRADA DESACTIVADA';
    if (history.length>=2) return 'MÁXIMO DOS CAMPAÑAS';
    const last=history[history.length-1],closed=Date.parse(last.closed_at??'');
    if (!finite(closed)||now-closed<1800000) return 'ESPERA 30 MINUTOS';
    if (!finite(f.volume_acceleration??NaN)||(f.volume_acceleration??0)<1.1) return 'VOLUMEN SIN RENOVACIÓN';
    if (!finite(f.consolidation_atr??NaN)||(f.consolidation_atr??99)>2.5) return 'SIN CONSOLIDACIÓN';
    if (f.ask<=(f.reentry_trigger??Infinity) || f.ask<=last.peak+.1*f.atr || Date.parse(f.bar_end??'')<=closed+900000) return 'SIN NUEVA RUPTURA';
    return null;
  }
export function quality(f: Feature, p: Profile, minDollarVolume: number, maxCostFraction: number, lv: Levels, costsBps: number): {score:number; reasons:string[]; cost_r:number} {
    const reasons:string[]=[];
    if (!(f.dollar_volume!==undefined&&finite(f.dollar_volume)&&f.dollar_volume>=minDollarVolume)) reasons.push('LIQUIDEZ INSUFICIENTE');
    const costR=(f.ask*(f.spread_bps+2*costsBps)/10000)/lv.risk_unit;
    if (!finite(costR)||costR>maxCostFraction) reasons.push('COSTE / R EXCESIVO');
    if (p.selective) {
      if (f.vwap_distance>3*f.atr_pct || f.vwap_distance<-.5*f.atr_pct) reasons.push('EXTENSIÓN VWAP');
      if ((f.relative_bps??-Infinity)<0) reasons.push('FUERZA RELATIVA DÉBIL');
      if ((f.volume_acceleration??0)<1) reasons.push('VOLUMEN DECRECIENTE');
    }
    const score=Math.log1p(Math.max(0,f.rvol))*20+Math.min(100,f.momentum_bps)/5+Math.max(-20,Math.min(20,(f.relative_bps??0)/10))-costR*30-Math.max(0,f.vwap_distance/Math.max(f.atr_pct,1e-9)-2)*8;
    return {score,reasons,cost_r:costR};
  }
export function newShadow(f: Feature, lv: Levels, p: Profile, until: number, costsBps: number, plannedQty?: number): Shadow {
    const at=Date.parse(f.asof);
    const first=plannedQty===undefined?.5:Math.floor(plannedQty*.5)/plannedQty;
    return {plannedQty,at,deadline:until,last:at,lastBid:f.bid,anchor:lv.limit,risk:lv.risk_unit,atr:f.atr,profile:{...p},costs:costsBps/10000,paid:0,proceeds:0,opened:0,riskSpent:0,riskBudget:lv.risk_unit+2*lv.limit*costsBps/10000,peak:lv.limit,stop:lv.stop,entry:lv.limit,levels:1,first:false,peakAt:at,lots:[],pending:{at,weight:first,levels:lv},marks:{},done:false,valid:true,reason:'OBSERVANDO',entryAt:null,mfe:0,mae:0,exitAt:until,tradingStagnation:0};
  }
export function stepShadow(s: Shadow, q: Quote, day: string, calendar: Session[], makeLevels:(ask:number,bid:number)=>Levels): void {
    if(s.done)return;
    const elapsed=tradingMillis(s.last,q.received,calendar);
    if(q.received<s.last || elapsed>60000 || q.received-q.at>15000) {s.valid=false;s.reason='HUECO DE COTIZACIÓN';}
    s.tradingStagnation+=elapsed;s.last=q.received;s.lastBid=q.bid;const vol=HXII.updateVol(s.vol,q.bid,q.received,s.atr);s.vol=vol.state;s.dynamicAtr=vol.atr;
    if(s.pending && q.received>s.pending.at) {
      if(q.received-s.pending.at>30000)s.pending=null;
      else if(q.ask<=s.pending.levels.limit) {
        const p=s.pending,l=p.levels;const sizes=s.plannedQty===undefined?null:parts(Math.round(p.weight*s.plannedQty),s.profile);s.paid+=p.weight*l.limit;s.opened+=p.weight;s.riskSpent+=p.weight*(l.risk_unit+2*l.limit*s.costs);
        s.lots.push({firstWeight:sizes?sizes[0]/(s.plannedQty as number):undefined,secondWeight:sizes?sizes[1]/(s.plannedQty as number):undefined,weight:p.weight,left:p.weight,entry:l.limit,stop:l.stop,tp1:l.tp1,tp2:l.tp2,first:false,second:false});s.entry=s.paid/s.opened;s.entryAt??=q.received;s.pending=null;
      }
    }
    if(!s.opened&&!s.pending){finishShadow(s,q,'SIN FILL');s.marks[day]=0;return;}
    if(s.opened){
      s.mfe=Math.max(s.mfe,(q.bid-s.entry)/s.risk);s.mae=Math.min(s.mae,(q.bid-s.entry)/s.risk);
      for(const l of s.lots){
        if(!l.left)continue;
        if(q.bid<=Math.max(l.stop,s.stop)){s.proceeds+=l.left*q.bid*(1-s.costs);l.left=0;continue;}
        for(const first of [true,false]) {if(!first&&s.profile.exit_layout==='single_target')continue;const hit=first?l.first:l.second,target=first?l.tp1:l.tp2,frac=first?(s.profile.tp1_fraction??.25):(s.profile.tp2_fraction??.25);
          if(!hit&&q.bid>=target){const sold=Math.min(l.left,(first?l.firstWeight:l.secondWeight)??l.weight*frac);s.proceeds+=sold*target*(1-s.costs);l.left-=sold;if(first){l.first=true;s.first=true;s.firstTargetAt??=q.received;}else l.second=true;}
        }
      }
      if(s.lots.every(l=>l.left<1e-12)){finishShadow(s,q,'STOP / OBJETIVOS');}
      else {
        if(q.bid>s.peak){s.peak=q.bid;s.peakAt=q.received;s.tradingStagnation=0;}
        s.stop=Math.max(s.stop,s.peak-s.profile.trail_atr*(s.profile.trailing_mode==='realized_vol'?(s.dynamicAtr??s.atr):s.atr));
        if(s.peak>=s.entry+2.5*s.risk)s.stop=Math.max(s.stop,s.entry+s.profile.lock_fraction*(s.peak-s.entry));
        if(s.first)s.stop=Math.max(s.stop,s.entry/(1-s.costs));
        if(q.bid<=s.stop)finishShadow(s,q,'TRAILING');
        else if(s.tradingStagnation>=(s.profile.stagnation_minutes??20)*60000&&q.bid*(1-s.costs)-s.entry<(s.profile.progress_r??1)*s.risk)finishShadow(s,q,'SIN CONTINUIDAD');
        else if(q.received>=s.deadline)finishShadow(s,q,'PLAZO');
        else if(!s.pending&&s.levels<3&&!s.first&&q.bid>=s.anchor+s.levels*.75*s.risk&&s.stop>=s.entry){
          const lv=makeLevels(q.ask,q.bid),unit=lv.risk_unit+2*lv.limit*s.costs;
          let weight=Math.max(0,Math.min(.25,Math.min(.25*s.riskBudget,s.riskBudget-s.riskSpent)/unit,(s.anchor-s.paid)/lv.limit));
          if(s.plannedQty!==undefined){const n=Math.floor(weight*s.plannedQty+1e-9);weight=n>=4?n/s.plannedQty:0;}
          if(weight>0){s.pending={at:q.received,weight,levels:lv};s.levels++;}
        }
      }
    }
    if(q.received>=s.deadline&&!s.done)finishShadow(s,q,'PLAZO');
    s.marks[day]=marked(s,q.bid);
  }
}
