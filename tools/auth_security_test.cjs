'use strict';
// Synthetic credentials and local HTTP only. No provider or broker requests.
const assert = require('node:assert/strict');
const http = require('node:http');
const {once} = require('node:events');
const {edge, basicAuth, gatewayEnvironment} = require('../deploy/managed.cjs');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
 const password = 'SYNTHETIC-PANEL-PASSWORD-'.repeat(2);
 const encoded = Buffer.from('trader:' + password).toString('base64');
 const authorization = 'Basic ' + encoded;
 const results = [];
 const check = (name, fn) => { fn(); results.push(name); };
 check('Valid Basic header accepted', () => assert.equal(basicAuth(authorization, password), true));
 check('Case insensitive scheme accepted', () => assert.equal(basicAuth('basic ' + encoded, password), true));
 check('Missing Basic scheme rejected', () => assert.equal(basicAuth(encoded, password), false));
 check('Invalid base64 characters rejected', () => assert.equal(basicAuth('Basic %%%' + encoded, password), false));
 check('Wrong user rejected', () => assert.equal(basicAuth('Basic ' + Buffer.from('admin:' + password).toString('base64'), password), false));
 check('Wrong password rejected', () => assert.equal(basicAuth('Basic ' + Buffer.from('trader:wrong').toString('base64'), password), false));
 const inputEnv = {OPENAI_MODEL:'synthetic-model',OPENAI_API_KEY:'synthetic-provider',OPENAI_INPUT_USD_PER_MILLION:'1',OPENAI_OUTPUT_USD_PER_MILLION:'2',HARPOON_MONTHLY_CAP:'10',HARPOON_RUN_CAP:'1',OPENAI_CACHED_USD_PER_MILLION:'0.1',HARPOON_HOT_REASONING:'low',CRYPTO_APCA_KEY:'synthetic-broker',HARPOON_PANEL_PASSWORD:password};
 const childEnv = gatewayEnvironment(inputEnv,'/synthetic/data','synthetic-gateway',18083);
 check('Gateway child excludes broker and panel secrets', () => {assert.equal(childEnv.CRYPTO_APCA_KEY,undefined);assert.equal(childEnv.HARPOON_PANEL_PASSWORD,undefined);});
 check('Gateway listens on loopback in managed deployment', () => assert.equal(childEnv.BIND_HOST,'127.0.0.1'));
 check('Optional inference settings reach gateway', () => {assert.equal(childEnv.OPENAI_CACHED_USD_PER_MILLION,'0.1');assert.equal(childEnv.HARPOON_HOT_REASONING,'low');});
 check('Incomplete inference configuration fails before launch', () => assert.throws(()=>gatewayEnvironment({...inputEnv,OPENAI_MODEL:''},'/synthetic/data','synthetic-gateway',18083)));
 let hits = 0, last;
 const upstream = http.createServer(async (req, res) => {
  hits++;
  let body = '';
  for await (const part of req) body += part;
  last = {headers:req.headers, body, url:req.url};
  res.setHeader('Content-Type', 'application/json');
  res.end('{"fixture":true}');
 });
 upstream.listen(0, '127.0.0.1'); await once(upstream, 'listening');
 const port = upstream.address().port;
 const origin = 'https://panel.example.test';
 const server = edge({password,token:'synthetic-control',gptToken:'synthetic-gateway',
  workers:new Map([['crypto',{}],['gpt',{}]]),ports:{crypto:port,gpt:port},html:Buffer.from('Synthetic panel'),origin});
 server.listen(0, '127.0.0.1'); await once(server, 'listening');
 const base = 'http://127.0.0.1:' + server.address().port;
 async function requestStatus(name, url, options, expected, reachesUpstream=false) {
  const previous = hits;
  const response = await fetch(base + url, options);
  await response.text();
  check(name, () => { assert.equal(response.status, expected); assert.equal(hits, previous + Number(reachesUpstream)); });
 }
 const post = headers => ({method:'POST',headers:{Authorization:authorization,'X-Harpoon-Action':'1','Content-Type':'application/json',...headers},body:'{}'});
 try {
  await requestStatus('Header without scheme denied over HTTP','/crypto/v1/state',{headers:{Authorization:encoded}},401);
  await requestStatus('Missing action header denied','/crypto/v1/pause',post({'X-Harpoon-Action':''}),403);
  await requestStatus('Cross origin action denied before proxy','/crypto/v1/pause',post({Origin:'https://evil.invalid'}),403);
  await requestStatus('Null origin denied before proxy','/crypto/v1/pause',post({Origin:'null'}),403);
  await requestStatus('Cross site fetch denied before proxy','/crypto/v1/pause',post({'Sec-Fetch-Site':'cross-site'}),403);
  await requestStatus('Non JSON body denied before proxy','/crypto/v1/pause',post({'Content-Type':'text/plain'}),415);
  await requestStatus('Same origin action accepted','/crypto/v1/pause',post({Origin:origin}),200,true);
  check('Panel credentials replaced by internal token', () => assert.equal(last.headers.authorization, 'Bearer synthetic-control'));
  check('Panel password absent from upstream request', () => assert.equal(JSON.stringify(last).includes(password), false));
  await requestStatus('CLI action with no browser origin preserved','/crypto/v1/pause',post({}),200,true);
  await requestStatus('Oversized JSON rejected before proxy','/crypto/v1/pause',{...post({}),body:'x'.repeat(30001)},413);
  await requestStatus('Panel Basic cannot authenticate to GPT','/gpt/v1/health',{headers:{Authorization:authorization}},401);
  await requestStatus('Gateway bearer cannot control a book','/crypto/v1/state',{headers:{Authorization:'Bearer synthetic-gateway'}},401);
  await requestStatus('Gateway bearer reaches GPT only','/gpt/v1/health',{headers:{Authorization:'Bearer synthetic-gateway'}},200,true);
  check('Gateway token preserved for gateway', () => assert.equal(last.headers.authorization,'Bearer synthetic-gateway'));
  await requestStatus('Unconfigured book rejected','/equity/v1/state',{headers:{Authorization:authorization}},404);
  const report = {checks:results.length,passed:results.length,results,provider:'local synthetic fixtures',external_orders:0,paid_model_calls:0};
  fs.writeFileSync(path.join(__dirname,'../evidence/auth_security_tests.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report));
 } finally {
  server.closeAllConnections(); upstream.closeAllConnections(); server.close(); upstream.close();
 }
})().catch(error => { console.error(error); process.exitCode=1; });
