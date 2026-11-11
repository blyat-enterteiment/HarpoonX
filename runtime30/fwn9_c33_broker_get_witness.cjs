"use strict";
/**
 * C33 immutable local GET evidence for *real* C25 readOnlyTransport.
 * A callback wraps the supplied HTTPS fetch transport and records exact
 * HTTP response bytes BEFORE C25 may process them. No order method, API key,
 * account ID, response body or query token is persisted in the witness.
 * Valid TLS transport + local SHA is NOT third-party broker attestation.
 */
const assert=require("node:assert/strict");
const crypto=require("node:crypto");
const C27=require("./fwn9_c27_prebar_state.cjs");
const SCHEMA="HARPOON_FWN9_C33_ALPACA_GET_LOCAL_WITNESS_1";
const ORIGINS=new Set(["https://paper-api.alpaca.markets",
 "https://api.alpaca.markets"]);
function need(x,k){assert.ok(x,"C33GET_"+k);}
function sha(s){return crypto.createHash("sha256").update(s).digest("hex");}
function acceptWitness(row){
 need(row&&row.schema===SCHEMA&&
  Number.isSafeInteger(row.sequence)&&row.sequence>0&&
  row.method==="GET"&&ORIGINS.has(row.origin)&&
  row.endpointPath.startsWith("/v2/")&&
  /^[0-9a-f]{64}$/.test(row.requestQuerySha256)&&
  /^[0-9a-f]{64}$/.test(row.responseBodySha256)&&
  Number.isSafeInteger(row.httpStatus)&&row.httpStatus>=200&&row.httpStatus<=599&&
  Number.isSafeInteger(row.startedAt)&&Number.isSafeInteger(row.completedAt)&&
  row.completedAt>=row.startedAt&&
  Number.isSafeInteger(row.responseBodyBytes)&&row.responseBodyBytes<10*1024*1024&&
  row.transportReceiptsIndependentlyBrokerSigned===false&&
  row.localWallClockIndependentlyNotarized===false&&
  row.paperOrLiveOrdersPermitted===false&&row.N9S==="NO_GO",
  "WITNESS_SCHEMA");
 return true;
}
function wrapTransport({transport=fetch,sink,mode="PAPER",
 now=Date.now,maxBytes=10*1024*1024}={}){
 need(typeof transport==="function"&&typeof sink==="function"&&
  typeof now==="function"&&mode==="PAPER"&&
  Number.isSafeInteger(maxBytes)&&maxBytes>0&&maxBytes<=10*1024*1024,
  "PAPER_GET_ONLY_NO_LIVE_CAPTURE");
 let sequence=0;
 return async function watchedGet(url,init){
  const parsed=new URL(url);
  need(parsed.origin==="https://paper-api.alpaca.markets"&&
   ORIGINS.has(parsed.origin)&&
   parsed.protocol==="https:"&&
   ["GET"].includes(init?.method)&&init?.redirect==="error"&&
   init?.body===undefined&&
   parsed.username===""&&parsed.password===""&&
   /^\/v2\/(?:account|positions|orders|assets\/)/.test(parsed.pathname),
   "STRICT_PAPER_ALPACA_GET_ORIGIN_AND_METHOD");
  need(init.headers&&
   typeof init.headers["APCA-API-KEY-ID"]==="string"&&
   typeof init.headers["APCA-API-SECRET-KEY"]==="string",
   "C25_TRADING_API_AUTH_REQUIRED");
  const startedAt=now();
  const reply=await transport(url,init);
  need(reply&&typeof reply.text==="function"&&
   Number.isSafeInteger(reply.status)&&
   typeof reply.ok==="boolean","RAW_HTTP_RESPONSE_REQUIRED");
  const raw=await reply.text();
  need(typeof raw==="string"&&
   Buffer.byteLength(raw,"utf8")<maxBytes,
   "RAW_RESPONSE_SIZE_BOUND");
  const completedAt=now();
  need(Number.isSafeInteger(startedAt)&&
   Number.isSafeInteger(completedAt)&&completedAt>=startedAt,
   "LOCAL_RECEIPT_CLOCK");
  const row=Object.freeze({
   schema:SCHEMA,sequence:++sequence,
   method:"GET",origin:parsed.origin,endpointPath:parsed.pathname,
   requestQuerySha256:sha(parsed.searchParams.toString()),
   httpStatus:reply.status,responseBodySha256:sha(raw),
   responseBodyBytes:Buffer.byteLength(raw,"utf8"),
   startedAt,completedAt,
   responseDateHeaderClaimSha256:typeof reply.headers?.get==="function"?
    sha(reply.headers.get("date")??""):sha(""),
   httpTransportSource:"C25_LOCAL_HTTPS_GET_NOT_INDEPENDENT_BROKER_ATTESTATION",
   transportReceiptsIndependentlyBrokerSigned:false,
   localWallClockIndependentlyNotarized:false,
   paperOrLiveOrdersPermitted:false,N9S:"NO_GO"
  });
  acceptWitness(row);
  sink(row); // If persistence fails, C25 never sees the response.
  return {ok:reply.ok,async text(){return raw;}};
 };
}
function verifyCoverage({witnesses,mode="PAPER",offlineBundle=null}={}){
 need(mode==="PAPER"&&Array.isArray(witnesses)&&
  witnesses.length>0,"PAPER_WITNESSES_REQUIRED");
 let last=0;const seen=new Set(),byPath=new Map();
 for(const [i,row] of witnesses.entries()){
  acceptWitness(row);
  need(row.sequence===i+1&&row.startedAt>=last&&
   row.origin==="https://paper-api.alpaca.markets",
   "GET_SEQUENCE_AND_ORIGIN");
  last=row.completedAt;
  seen.add(row.sequence);
  byPath.set(row.endpointPath,(byPath.get(row.endpointPath)??0)+1);
 }
 const required=["/v2/account","/v2/positions","/v2/orders",
  "/v2/account/activities"];
 const missing=required.filter(p=>!byPath.has(p));
 const statuses=witnesses.every(r=>r.httpStatus>=200&&r.httpStatus<300);
 const bundleCheck=offlineBundle===null?null:{
  schema:offlineBundle.schema,
  mode:offlineBundle.mode,
  sourceAccountOriginNotBrokerSigned:
   offlineBundle.independent_broker_source_authentication===false,
  originalSourceBundleHash:C27.digest(offlineBundle)
 };
 if(bundleCheck!==null)need(
  bundleCheck.schema==="HARPOON_FWN9_C25_ALPACA_OFFLINE_BUNDLE_1"&&
  bundleCheck.mode==="PAPER"&&
  bundleCheck.sourceAccountOriginNotBrokerSigned===true,
  "PAPER_C25_SOURCE_BINDING");
 return {
  schema:"HARPOON_FWN9_C33_GET_TRANSPORT_DIAGNOSTIC_1",
  witnessedGetResponses:witnesses.length,
  witnessedEndpoints:[...byPath.keys()].sort(),
  missingRequiredEndpoints:missing,
  allHttpResponsesSuccessful:statuses,
  allRequiredEndpointKindsWitnessed:missing.length===0,
  rawResponseHashesLocallyVerified:true,
  offlineAccountBundleDigest:bundleCheck?.originalSourceBundleHash??null,
  brokerSourceIndependentlyAuthenticated:false,
  completeAccountAndOrderHistoryCertified:false,
  sourceWasCapturedProspectivelyInActualRuntime:false,
  independentTimeAnchorVerified:false,
  financedReturnVsCashCertified:false,financialGO:false,N9S:"NO_GO"
 };
}
module.exports={SCHEMA,acceptWitness,wrapTransport,verifyCoverage};
