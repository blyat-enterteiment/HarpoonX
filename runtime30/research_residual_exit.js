"use strict";
/** Offline research only: decision uses bars received before the candidate open. */
function latest(bars, at) {
 let lo=0,hi=bars.length;
 while(lo<hi){const mid=(lo+hi)>>>1;if(bars[mid].availableAt<=at)lo=mid+1;else hi=mid;}
 return lo ? bars[lo-1] : null;
}
function residualZ(meta,data,at){
 const stock=data.series.find(s=>s.symbol===meta.stock),sector=data.series.find(s=>s.symbol==='XLK');
 if(!stock||!sector)throw Error('RESEARCH_EXIT_SERIES_REQUIRED');
 const a=latest(stock.bars,at),b=latest(sector.bars,at);
 if(!a||!b||a.t!==b.t||a.availableAt>at||b.availableAt>at)throw Error('RESEARCH_EXIT_ALIGNED_KNOWN_BARS_REQUIRED');
 if(at-a.availableAt>600000)throw Error('RESEARCH_EXIT_STALE_MARK');
 if(!(meta.stockOpen>0&&meta.sectorOpen>0&&meta.sigma>0&&Number.isFinite(meta.beta)&&Number.isFinite(meta.mu)))throw Error('RESEARCH_EXIT_MODEL_DOMAIN');
 const z=(Math.log(a.c/meta.stockOpen)-meta.beta*Math.log(b.c/meta.sectorOpen)-meta.mu)/meta.sigma;
 if(!Number.isFinite(z))throw Error('RESEARCH_EXIT_NONFINITE');
 return z;
}
function exitReason(signal,data,at){
 const m=signal.metadata.researchExit;
 if(at<=signal.plannedEntryAt)return null;
 if((data.splitEvents||[]).some(e=>e.symbol==='XLK'&&e.at>signal.at&&e.at<=at))throw Error('RESEARCH_BENCHMARK_SPLIT_WITH_OPEN_EXPOSURE');
 if(!['NORMALIZE','INVALIDATE'].includes(m.mode))throw Error('RESEARCH_EXIT_MODE');
 const z=residualZ(m,data,at);
 if(m.mode==='NORMALIZE'&&z>=-.25)return 'RESEARCH_NORMALIZE';
 if(m.mode==='INVALIDATE'&&z<=-3)return 'RESEARCH_INVALIDATE';
 return null;
}
module.exports={latest,residualZ,exitReason};
