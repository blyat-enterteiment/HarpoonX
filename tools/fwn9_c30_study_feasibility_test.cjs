"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const C30=require("../runtime30/fwn9_c30_study_feasibility.cjs");
const C29=require("../runtime30/fwn9_c29_frozen_assignments.cjs");
function freeze(){
 const registeredAt=Date.parse("2027-01-01T00:00:00.000Z");
 return C29.freeze({studyId:"C30_TEST_ONLY",registeredAt,
  startAt:registeredAt+72*3600000,cycles:4,
  assignmentNonce:"C30_SOURCE_ONLY_FIXED_TEST_NONCE_00001"});
}
test("unfrozen study fails closed without broker or trading",async()=>{
 const p=await C30.audit();
 assert.equal(p.candidateArms,6);
 assert.equal(p.controlArms,2);
 assert.equal(p.frozenPlanValidated,false);
 assert.equal(p.fullEightArmBrokerExperimentExecutable,false);
 assert.equal(p.mayStartFinancialValidation,false);
 assert.equal(p.maySendPaperOrLiveOrders,false);
 assert.ok(p.structuralBlockers.includes("NO_FROZEN_PROSPECTIVE_PLAN_SUPPLIED"));
});
test("valid frozen hash does not grant executable policy",async()=>{
 const plan=freeze(),p=await C30.audit({plan});
 assert.equal(p.frozenPlanValidated,true);
 assert.equal(p.frozenPlanDigest,plan.planDigest);
 assert.equal(p.originalC22RankExecutionAllowed,false);
 assert.equal(p.N9S,"NO_GO");
 assert.equal(p.M10FinalAccountsSealed,3200);
});
test("two option arms have no certified executable size",async()=>{
 const p=await C30.audit({plan:freeze()});
 assert.equal(p.optionResearchArms.length,2);
 assert.equal(p.originalC22OptionSizeCertified,false);
 assert.ok(p.structuralBlockers.includes("OPTIONS_C22_QUANTITY_EXECUTOR_UNCERTIFIED"));
});
test("C25 currently rejects option-contract accounting",async()=>{
 const p=await C30.audit({plan:freeze()});
 assert.equal(p.originalC25OptionInstrumentAccountingAvailable,false);
 assert.ok(p.structuralBlockers.includes("C25_BROKER_EXPORT_CANNOT_ACCOUNT_FOR_OPTIONS"));
});
test("caller flags never authenticate registration or broker",async()=>{
 const p=await C30.audit({plan:freeze(),
  independentBrokerAndRegistrarAttested:true,canTrade:true});
 assert.equal(p.independentBrokerAndRegistrarAttested,false);
 assert.ok(p.structuralBlockers.includes("INDEPENDENT_PREOUTCOME_REGISTRATION_NOT_VERIFIED"));
 assert.ok(p.structuralBlockers.includes("BROKER_PRIVATE_GET_RECEIPTS_NOT_AUTHENTICATED"));
});
test("tampered plan is rejected before source examination",async()=>{
 const plan=freeze();
 plan.eightArms[0]="FAKE_EXECUTABLE";
 await assert.rejects(C30.audit({plan}),/C29R_PLAN_TAMPERED/);
});
