'use strict';
// Synthetic software checks of reserve funding; no external calls or replay.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const app=path.resolve(process.argv[2]||'/workspace/scratch/4ecb05fdc50d/level5_work/HARPOON_XXXUltimate_30_12_0');
const {validateRequest,SimulatedReplayBroker}=require(path.join(app,'tools/coordinator_replay.cjs'));
const {syntheticRequest}=require(path.join(app,'tools/fixtures/coordinator_replay_fixture.cjs'));
const input=syntheticRequest(),clone=x=>JSON.parse(JSON.stringify(x));
input.initial_cash_usd=1000;
input.execution_model.external_cost_usd=900;
input.execution_model.fees_bps_per_side=0;
input.execution_model.fee_per_fill_usd=1;
input.execution_model.operating_cash_reserve={method:'FIXED_INITIAL_CASH_RESERVE',amount_usd:900,known_at:input.start_at-1};
const tests=[];
function check(id,fn,predicate){try{const result=fn();tests.push({id,passed:!!predicate(result),result,error:null})}catch(e){tests.push({id,passed:false,error:e.message})}}
function errorOf(fn){try{fn();return null}catch(e){return e.message}}
check('CASH-RESERVE-VALID',()=>errorOf(()=>validateRequest(input)),x=>x===null);
const late=clone(input);late.execution_model.operating_cash_reserve.known_at=late.start_at;
check('CASH-RESERVE-KNOWN-STRICTLY-BEFORE',()=>errorOf(()=>validateRequest(late)),x=>x==='OPERATING_RESERVE_MUST_BE_FUNDED_AND_KNOWN_BEFORE_REPLAY');
const insufficient=clone(input);insufficient.execution_model.operating_cash_reserve.amount_usd=899;
check('CASH-RESERVE-COVERS-COST',()=>errorOf(()=>validateRequest(insufficient)),x=>x==='OPERATING_RESERVE_INSUFFICIENT_FOR_EXTERNAL_COSTS');
const clock={now:input.start_at+1},broker=new SimulatedReplayBroker(input,clock);
broker.engine={state:{intents:[]}};broker.quotes.set('AAPL',{bid:1,ask:1,at:clock.now});
check('CASH-RESERVE-NAV-NOT-DEDUCTED',()=>broker.account(),x=>+x.equity===1000&&+x.cash===1000&&+x.buying_power===100&&+x.non_marginable_buying_power===100);
const order=qty=>({side:'buy',symbol:'AAPL',qty:String(qty),filled_qty:'0',created_ms:input.start_at,client_order_id:'SYNTH-BUY-'+qty});
check('CASH-RESERVE-BUY-CANNOT-SPEND-FEE',()=>errorOf(()=>broker.fill(order(100),100,1,'TEST-TOO-LARGE',{market_at:clock.now})),x=>x==='MODELED_CAPITAL_OR_INVENTORY_EXCEEDED');
check('CASH-RESERVE-BUY-EXACT-AVAILABLE',()=>{broker.fill(order(99),99,1,'TEST-FUNDED',{market_at:clock.now});return broker.account()},x=>+x.cash===900&&+x.equity===999&&+x.buying_power===0);
check('CASH-RESERVE-PROTECTIVE-EXIT-SHOWS-DEFICIT',()=>{broker.fill({side:'sell',symbol:'AAPL',qty:'99',filled_qty:'0',created_ms:input.start_at,client_order_id:'SYNTH-EXIT'},99,.001,'TEST-EXIT',{market_at:clock.now});return broker.account()},x=>+x.cash<900&&+x.buying_power<0&&Math.abs(+x.buying_power-(+x.cash-900))<1e-12);
const result={scope:'Synthetic direct broker arithmetic and validator checks, not a financial experiment',source_sha256:crypto.createHash('sha256').update(fs.readFileSync(path.join(app,'tools/coordinator_replay.cjs'))).digest('hex'),passed:tests.filter(t=>t.passed).length,total:tests.length,tests,external_orders:0,production_edits:0,new_economic_experiments:0};
fs.writeFileSync(path.join(__dirname,'cash_reserve_checks.json'),JSON.stringify(result,null,2)+'\n');
process.stdout.write(JSON.stringify(result)+'\n');if(result.passed!==result.total)process.exitCode=1;
