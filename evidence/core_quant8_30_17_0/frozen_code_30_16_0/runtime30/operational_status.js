"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.entryOperationalFailures = entryOperationalFailures;
exports.operationalCapabilities = operationalCapabilities;
/** These checks narrow existing entry authority; they never create authority. */
function entryOperationalFailures(e, now = Date.now()) {
    if (!e.cfg.quant?.enabled)
        return [];
    const failures = [], rules = e.cfg.quant.operational || {};
    const ledger = e.netLedger.view(), observations = e.quantObservations.view(now);
    if (ledger.insolvency?.account || ledger.insolvency?.economic)
        failures.push("INSOLVENCY_OBSERVED_NO_CAPITAL_RESET");
    if (e.quantObservationError || observations.status === "ERROR")
        failures.push("OBSERVATION_PERSISTENCE_OR_CONTRACT");
    if (rules.requireObservationJournalForEntries &&
        (!observations.persisted || observations.status === "STALE"))
        failures.push("OBSERVATION_JOURNAL_NOT_CURRENT");
    if (rules.requireAccountLedgerForEntries && (!ledger.reconciled ||
        ["UNVERIFIED", "STALE", "BLOCKED", "ERROR"].includes(ledger.status) || e.netAccountingError))
        failures.push("ACCOUNT_LEDGER_NOT_RECONCILED");
    // Once an observed ledger has detected a mismatch, stop adding risk even
    // under a legacy config. Position protection remains a separate path.
    if (ledger.baseline && (!ledger.reconciled || ["BLOCKED", "ERROR", "STALE"].includes(ledger.status)))
        failures.push("OBSERVED_ACCOUNTING_DISCREPANCY");
    return [...new Set(failures)];
}
function operationalCapabilities(e, now = Date.now()) {
    const accountReady = !!e.syncAt && now >= e.syncAt && now - e.syncAt <= 15000 && !e.reconcileError;
    const storageReady = !e.storageError && !!e.validators.checks["journal-write"]?.lastSuccess;
    const coverage = e.exitCoverage(now), ledger = e.netLedger.view(), observations = e.quantObservations.view(now);
    const plan = e.quantLastPlan, planAge = typeof plan.completed_at === "number" ? now - plan.completed_at : null;
    const planningObserved = planAge !== null && planAge >= 0 && planAge <= 180000 &&
        plan.engine === "HARPOON_QUANT_1" && plan.origin === "OBSERVED" && plan.research_only !== true &&
        typeof plan.model_hash === "string" && /^[a-f0-9]{64}$/.test(plan.model_hash) &&
        ((plan.execution_allowed === true && plan.reason === "CONDITIONAL_MODEL_ALLOCATION") ||
            (plan.execution_allowed === false && plan.reason === "NO_VALUABLE_CANDIDATES"));
    const gate = e.quantEconomicGate;
    const candidateVerified = gate.recomputed_identically === true && gate.report_integrity_verified === true &&
        gate.runtime_binding_matches === true && Number.isFinite(gate.observed_at) &&
        now >= gate.observed_at && now - gate.observed_at <= 900000 &&
        gate.dictamen === "CANDIDATO_PARA_VALIDACION_FORWARD";
    const checks = [
        { id: "account_reconciliation", status: accountReady ? "PASS" : "BLOCKED",
            evidence: { sync_at: e.syncAt || null, error: e.reconcileError || null } },
        { id: "durable_state", status: storageReady ? "PASS" : "BLOCKED",
            evidence: { last_success: e.validators.checks["journal-write"]?.lastSuccess || null, error: e.storageError || null } },
        { id: "position_protection", status: coverage.entrySafe ? "PASS" : "BLOCKED", evidence: coverage },
        { id: "account_net_ledger", status: ledger.reconciled && !["STALE", "ERROR"].includes(ledger.status) ? "PASS" : "BLOCKED",
            evidence: { status: ledger.status, blockers: ledger.blockers, last_success: ledger.lastSuccess, error: e.netAccountingError || null } },
        { id: "economic_net_costs_and_returns", status: ledger.economicComplete && ledger.returnComplete &&
                !["STALE", "ERROR", "BLOCKED"].includes(ledger.status) ? "PASS" : "WAIT_DATA",
            evidence: { economic_complete: ledger.economicComplete, comparable_returns: ledger.returnComplete } },
        { id: "prospective_observations", status: observations.persisted && !["STALE", "ERROR"].includes(observations.status) &&
                !e.quantObservationError ? "PASS" : "WAIT_DATA", evidence: observations },
        { id: "quant_planning", status: !e.cfg.quant?.enabled ? "NOT_CONFIGURED" : planningObserved ? "PASS" : "WAIT_MODEL_OR_DECISION",
            evidence: { last_status: plan.status, reason: plan.reason || null, age_ms: planAge, model_hash: plan.model_hash || null } },
        { id: "net_economic_gate", status: candidateVerified ? "CANDIDATE_FOR_FORWARD_ONLY" : "NOT_PROVEN",
            evidence: gate },
    ];
    const failures = entryOperationalFailures(e, now);
    const operationalReady = e.entryReady() && !e.discoveryHold && accountReady && storageReady && coverage.entrySafe && !failures.length &&
        checks.filter(c => ["account_net_ledger", "prospective_observations"].includes(c.id)).every(c => c.status === "PASS") &&
        (!e.cfg.quant?.enabled || planningObserved);
    return { schema: "HARPOON_OPERATIONAL_CAPABILITIES_1", observed_at: now,
        state: e.stopping ? "STOPPING" : !accountReady ? "RECONCILING" : failures.length ? "HALT_NEW_RISK" :
            e.state.paused || e.state.halt ? "MANAGE_ONLY" : operationalReady ? "OPERATIONALLY_READY" : "COLLECTING_OR_VALIDATING",
        operational_ready: operationalReady, full_autonomous_economic_cycle_verified: false,
        automatic_model_training_and_promotion_verified: false,
        net_candidate_bound_to_runtime: candidateVerified,
        entry_additional_gate: { passes: failures.length === 0, failures, grants_order_authority: false },
        position_management_independent_of_research: true, financial_profitability_demonstrated: false,
        numerical_worker_budget: require("../runtime/quant_bridge.cjs").workerStatus(),
        checks, scope: "Local operational observations. HTTP liveness, model validity and economic evidence are distinct." };
}
