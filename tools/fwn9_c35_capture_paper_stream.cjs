#!/usr/bin/env node
"use strict";
/**
 * Explicit, finite-duration, user-invoked PAPER trade_updates observation.
 * Uses the documented Alpaca auth + listen WebSocket messages ONLY.
 * No order POST, submit, cancellation, deployment, or trade authority.
 * No keys in files or output. Never run in CI against Alpaca.
 */
const crypto=require("node:crypto");
const path=require("node:path");
const W=require("../runtime30/fwn9_c35_paper_trade_updates.cjs");
const J=require("../runtime30/fwn9_c35_paper_stream_journal.cjs");
function need(x,k){if(!x)throw Error("C35CLI_"+k);}
function argumentsOf(argv){
 need(Array.isArray(argv)&&argv.length===6&&
  argv[0]==="--mode"&&argv[1]==="PAPER"&&
  argv[2]==="--out"&&typeof argv[3]==="string"&&argv[3].length>0&&
  argv[4]==="--seconds"&&/^[1-9]\d*$/.test(argv[5]),
  "EXPLICIT_PAPER_CAPTURE_ARGUMENTS");
 const seconds=Number(argv[5]),out=path.resolve(argv[3]);
 need(Number.isSafeInteger(seconds)&&seconds>=1&&seconds<=3600&&
  !/(?:^|\/)(?:holdout|M10[_-]?final)(?:\/|$)/i.test(out),
  "FINITE_PRIVATE_CAPTURE_NOT_M10");
 return {out,seconds};
}
function localCapture(argv,{env=process.env,Socket=null}={}){
 const args=argumentsOf(argv);
 const key=env.APCA_API_KEY_ID,secret=env.APCA_API_SECRET_KEY;
 need(typeof key==="string"&&key.length>0&&
  typeof secret==="string"&&secret.length>0,
  "LOCAL_PAPER_ACCOUNT_CREDENTIALS_REQUIRED");
 const WS=Socket??require("ws");
 const runId="C35_"+crypto.randomBytes(16).toString("hex");
 J.create(args.out,{captureId:runId});
 const journal=J.openWriter(args.out),observer=W.session();
 return new Promise((resolve,reject)=>{
  let ready=false,graceful=false,finished=false;
  let activeTimer=null,authTimer=null;
  const socket=new WS("wss://paper-api.alpaca.markets/stream",{
   perMessageDeflate:false,handshakeTimeout:15000,
   maxPayload:1024*1024
  });
  const failed=()=>{
   if(finished)return;
   finished=true;clearTimeout(activeTimer);clearTimeout(authTimer);
   observer.close();
   try{socket.terminate();}catch{}
   // Preserve lock as an incident: a partial stream must not be silently
   // resumed or misrepresented as an exhaustive receipt history.
   reject(Error("C35CLI_STREAM_FAILED_OR_INTERRUPTED_NO_ORDER_ACTION"));
  };
  authTimer=setTimeout(failed,15000);
  socket.on("open",()=>{
   if(finished)return;
   socket.send(JSON.stringify({action:"auth",key,secret}));
  });
  socket.on("message",(raw)=>{
   if(finished)return;
   try{
    const at=Date.now(),result=observer.message(raw,at);
    if(result.type==="SEND_LISTEN"){
     journal.authorized(at);
     socket.send(JSON.stringify({
      action:"listen",data:{streams:["trade_updates"]}
     }));
    }else if(result.type==="READY"){
     journal.listening(at);clearTimeout(authTimer);ready=true;
     activeTimer=setTimeout(()=>{
      graceful=true;socket.close(1000,"C35_CAPTURE_END");
     },args.seconds*1000);
    }else if(result.type==="EVENT")journal.event(result.record);
    else throw Error("UNSUPPORTED_OBSERVER_STATE");
   }catch{failed();}
  });
  socket.on("error",failed);
  socket.on("close",()=>{
   if(finished)return;
   if(!ready||!graceful){failed();return;}
   try{
    const audit=journal.close(Date.now());
    observer.close();finished=true;clearTimeout(activeTimer);
    resolve({
     schema:"HARPOON_FWN9_C35_CAPTURE_PAPER_STATUS_1",
     eventsRecorded:audit.eventsRecorded,
     localJournalHead:audit.head,
     streamWasNeverProvenGapFree:true,
     accountKeysAndOrdersNotPrinted:true,
     noBrokerOrdersSubmitted:true,
     brokerOriginIndependentlyVerified:false,
     C26FillReceiptMatchingPerformed:false,
     financialGO:false,N9S:"NO_GO"
    });
   }catch{failed();}
  });
 });
}
if(require.main===module){
 process.umask(0o077);
 localCapture(process.argv.slice(2)).then(r=>{
  process.stdout.write(JSON.stringify(r)+"\n");
 },()=>{
  process.stderr.write("C35CLI_STREAM_CAPTURE_FAILED_LOCK_REQUIRES_REVIEW\n");
  process.exitCode=2;
 });
}
module.exports={argumentsOf,localCapture};
