"use strict";
const {spawn}=require('node:child_process');
const child=spawn(process.execPath,[require('node:path').join(__dirname,'cloud.cjs')],{stdio:'inherit'});
let failures=0,checking=false,stopping=false;const started=Date.now();
const timer=setInterval(async()=>{if(checking||stopping||Date.now()-started<60000)return;checking=true;
 try{const r=await fetch('http://127.0.0.1:'+(process.env.PORT||8080)+'/healthz',{signal:AbortSignal.timeout(5000)});if(!r.ok)throw Error();const h=await r.json();if(h.boot!=='connected'&&Date.now()-started>600000)throw Error();failures=0;}
 catch{if(++failures>=3){console.error('{"event":"liveness_failure"}');child.kill('SIGTERM');setTimeout(()=>child.kill('SIGKILL'),30000).unref();}}
 finally{checking=false;}},15000);
child.once('exit',code=>{clearInterval(timer);process.exit(code??1);});
for(const signal of ['SIGTERM','SIGINT'])process.once(signal,()=>{stopping=true;child.kill(signal);});
