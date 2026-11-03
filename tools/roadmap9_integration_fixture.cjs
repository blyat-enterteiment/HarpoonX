'use strict';
// Declared synthetic engineering inputs; no market, account or strategy result.
function fixture(base = Date.now(), crypto = false) {
  const symbol = crypto ? 'BTC/USD' : 'AAPL';
  const init = {kind:'INIT', command_id:'init', assets:[{symbol, book:crypto?'crypto':'equity', factor:'SYNTHETIC',
    lot_qty:crypto?'0.00000001':'1', max_new_lots:2, schedule:Array(72).fill(true),
    schedule_known_at_ms:base-60000, schedule_source_hash:'a'.repeat(64)}],
    profiles:{[symbol]:{profile_id:'synthetic-fee-v1', base_asset:crypto?'BTC':'AAPL', quote_asset:'USD',
      maker_bps:crypto?'25':'0', taker_bps:crypto?'25':'0', origin:'SYNTHETIC_ENGINEERING_ONLY',
      source:'declared-offline-engineering-fixture', charge_mode:crypto?'CREDITED_ASSET_BPS':'QUOTE_PER_UNIT',
      quote_fee_per_unit:crypto?'0':'0.005', quote_fixed_per_order:crypto?'0':'0.20'}}};
  if (crypto) init.opening_events = [
    {kind:'INTENT',event_id:'opening-intent',client_order_id:'opening-buy',campaign_id:'opening-campaign',
      symbol,side:'buy',qty:'1',opened_at:base-3600000,deadline_at:base+71*3600000,at:base-4000},
    {kind:'SUBMITTED',event_id:'opening-submit',client_order_id:'opening-buy',at:base-3000},
    {kind:'ACK',event_id:'opening-ack',client_order_id:'opening-buy',broker_order_id:'SIMULATED-OPENING',at:base-2000},
    {kind:'FILL',event_id:'opening-fill',client_order_id:'opening-buy',execution_id:'opening-execution',
      qty:'1',price:'100',liquidity_role:'taker',executed_at:base-1500,at:base-1000}];
  return {symbol, init,
    market:{kind:'MARKET',command_id:'market',quotes:[{symbol,bid:'100',ask:'100',event_at_ms:base}]},
    predictor:{kind:'PREDICTOR',command_id:'predictor',ready:true,model_trained_at_ms:base-3000,latest_label_at_ms:base-60000},
    forecast:{schema:'HARPOON_ROADMAP9_PORTFOLIO_FORECAST_1',symbols:[symbol],units:'SIMPLE_RETURN_FRACTION',
      covariance_units:'RETURN_FRACTION_SQUARED',origin:'SYNTHETIC_ENGINEERING_ONLY',horizon_hours:24,
      known_at:new Date(base-2000).toISOString(),model_asof:new Date(base-3000).toISOString(),
      latest_label_at:new Date(base-60000).toISOString(),mean:[0.10],signal_age_hours:[0],alpha_half_life_hours:[24],
      return_covariance:[[0.0001]],mean_error_covariance:[[0]],scenario_returns:Array.from({length:20},(_,i)=>[i%2?0.02:-0.01]),
      scenario_weights:Array(20).fill(0.05),stress_returns:[[-0.05]]}};
}
module.exports = {fixture};
