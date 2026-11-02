'use strict';
const HPCryptoExits=Object.freeze({
 update(c,q,sig,now){const cfg=c.config;if(c.plugin?.manifest?.family==='shock_recovery'){if(q.bid>=c.target)c.closing='OBJETIVO DE RECUPERACIÓN';if(now>=c.deadline)c.closing='PLAZO RECUPERACIÓN';}
  else{if(sig&&sig.available_at>c.lastSignal){c.high=Math.max(c.high,sig.close);c.stop=Math.max(c.stop,c.high-cfg.atr_multiple*sig.atr);c.lastSignal=sig.available_at;}if(sig?.exit)c.closing='TENDENCIA';if(cfg.hold_hours>0&&now-c.opened>=cfg.hold_hours*3600000)c.closing='PLAZO';}
  if(q.bid<=c.stop)c.closing='STOP';
 }
});
