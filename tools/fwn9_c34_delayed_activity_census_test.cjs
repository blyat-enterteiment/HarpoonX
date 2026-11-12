"use strict";
const test=require("node:test"),A=require("node:assert/strict");
const C=require("../runtime30/fwn9_c34_delayed_activity_census.cjs");
const B="2026-11-06T14:00:00Z",E="2026-11-06T17:00:00Z";
const T="2026-11-08T17:00:00Z",COLLECTED="2026-11-08T17:01:00Z";
const originalAccount={id:"SYNTHETIC_NOT_ALPACA",cash:"20000",equity:"20000",currency:"USD"};
function first(fee=null){
 const rows=fee?[fee]:[];
 const cash=fee?"19999":"20000";
 return {schema:"HARPOON_FWN9_C25_ALPACA_OFFLINE_BUNDLE_1",
  export_type:"OFFLINE_ALPACA_TRADING_API_READ_ONLY",
  mode:"PAPER",currency:"USD",account_id:originalAccount.id,
  from:B,through:E,collected_at:"2026-11-06T17:01:00Z",
  instruments:[],baseline_open_orders:[],
  baseline:{observed_at:B,account:originalAccount,positions:[]},
  terminal:{observed_at:E,
   account:{...originalAccount,cash,equity:cash},positions:[]},
  orders:{filter_status:"all",pagination_asserted_complete:true,rows:[]},
  activities:{filter:"all",order:"asc",page_size:100,pages:[
   {request_page_token:null,rows,complete:true}
  ]},
  external_cost_coverage:{currency:"USD",from:B,through:E,
   categories:["DATA","INFRASTRUCTURE","INFERENCE","OTHER"],
   coverage_declared_complete:true,rows:[]}
 };
}
const fee={id:"FEE_ORIGINAL",activity_type:"FEE",
 date:"2026-11-06",created_at:"2026-11-06T15:30:00Z",
 net_amount:"-1"};
const lateFee={id:"LATE_FEE",activity_type:"FEE",
 date:"2026-11-07",created_at:"2026-11-07T09:00:00Z",
 net_amount:"-0.5"};
function requery(base,rows){
 return {schema:C.SCHEMA,mode:"PAPER",account_id:base.account_id,
  from:base.from,through:T,collected_at:COLLECTED,
  capture_basis:"ALPACA_ACTIVITY_CREATED_AT_NOT_SETTLEMENT_DATE",
  activities:{filter:"all",order:"asc",page_size:100,pages:[
   {request_page_token:null,rows,complete:true}
  ]}
 };
}
test("C34 discovered late broker fee blocks final NAV promotion",()=>{
 const b=first(),r=C.inspect({initialBundle:b,requery:requery(b,[lateFee])});
 A.equal(r.startingActivityCount,0);
 A.equal(r.expandedActivityCount,1);
 A.equal(r.activitiesCreatedAfterOriginalClose,1);
 A.equal(r.requiresReconciliationRestatement,true);
 A.equal(r.originalC25NAVCannotBePromotedAsFinalFromThisCensus,true);
 A.equal(r.financialGO,false);
});
test("even no new activities cannot certify future settlement completeness",()=>{
 const b=first(),r=C.inspect({initialBundle:b,requery:requery(b,[])});
 A.equal(r.importedActivityHistoryExactSubsetVerified,true);
 A.equal(r.lateDiscoveredActivities.length,0);
 A.equal(r.singleAdditionalRequeryProvesNoFutureLateActivities,false);
 A.equal(r.financialGO,false);
});
test("C34 rejects account substitution before assessing late fees",()=>{
 const b=first(),x=requery(b,[]);
 x.account_id="OTHER";
 A.throws(()=>C.inspect({initialBundle:b,requery:x}),
 /C34L_SAME_INITIAL_ACCOUNT_AND_CREATION_WINDOW/);
});
test("C34 exact overlap rejects history gaps",()=>{
 const b=first(fee),x=requery(b,[]);
 A.throws(()=>C.inspect({initialBundle:b,requery:x}),
 /C34L_REQUERY_MISSING_PREVIOUS_ACTIVITY/);
});
test("C34 exact overlap rejects previously observed fee tampering",()=>{
 const b=first(fee),x=requery(b,[{...fee,net_amount:"-2"}]);
 A.throws(()=>C.inspect({initialBundle:b,requery:x}),
 /C34L_REQUERY_ALTERED_PRIOR_ACTIVITIES/);
});
test("C34 duplicate activity IDs reject source completeness",()=>{
 const b=first(),x=requery(b,[lateFee,lateFee]);
 A.throws(()=>C.inspect({initialBundle:b,requery:x}),
 /C25_DUPLICATE_ACTIVITY_ID/);
});
test("C34 rejects late activities without actual created_at",()=>{
 const b=first(),x=requery(b,[{...lateFee,created_at:undefined}]);
 A.throws(()=>C.inspect({initialBundle:b,requery:x}),
 /C34L_ISO_NEW_ACTIVITY_CREATED_AT/);
});
test("C34 rejects closed interval masquerading as extended collection",()=>{
 const b=first(),x=requery(b,[]);
 x.through=b.through;
 A.throws(()=>C.inspect({initialBundle:b,requery:x}),
 /C34L_EXPANDED_QUERY_MUST_OCCUR_AFTER_ORIGINAL/);
});
