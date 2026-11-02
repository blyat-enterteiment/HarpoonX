"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.RuntimeProbe = exports.ObservedApi = void 0;
exports.systemHealth = systemHealth;
const node_perf_hooks_1 = require("node:perf_hooks");
const exits_1 = require("./exits");
class ObservedApi {
    inner;
    total = 0;
    errors = 0;
    inflight = 0;
    rows = {};
    timings = [];
    constructor(inner) {
        this.inner = inner;
    }
    get keys() {
        return this.inner.keys;
    }
    get mode() {
        return this.inner.mode;
    }
    async request(path, method = "GET", body, market = false) {
        const key = method + " " + path.split("?")[0], start = node_perf_hooks_1.performance.now();
        const r = (this.rows[key] ??= {
            attempts: 0,
            successes: 0,
            failures: 0,
            lastAttempt: 0,
            lastSuccess: 0,
            lastError: "",
            lastStatus: null,
            latencyMs: null,
        });
        r.attempts++;
        this.total++;
        this.inflight++;
        r.lastAttempt = Date.now();
        try {
            const value = await this.inner.request(path, method, body, market);
            r.successes++;
            r.lastSuccess = Date.now();
            r.lastError = "";
            r.lastStatus = "CONFIRMED_RESPONSE";
            return value;
        }
        catch (e) {
            r.failures++;
            this.errors++;
            r.lastError = e instanceof Error ? e.message : String(e);
            r.lastStatus = e?.status || "TRANSPORT_ERROR";
            throw e;
        }
        finally {
            this.inflight--;
            r.latencyMs = node_perf_hooks_1.performance.now() - start;
            this.timings.push(r.latencyMs);
            this.timings = this.timings.slice(-128);
        }
    }
    snapshot() {
        const times = [...this.timings].sort((a, b) => a - b);
        const queues = this.inner.transportQueues || {};
        return {
            requests: this.total,
            errors: this.errors,
            inflight: this.inflight,
            latencyP95Ms: times.length
                ? times[Math.floor((times.length - 1) * 0.95)]
                : null,
            endpoints: Object.entries(this.rows).map(([endpoint, r]) => ({
                endpoint,
                ...r,
            })),
            queues: Object.fromEntries(Object.entries(queues).map(([k, v]) => [
                k,
                {
                    pending: v.pending?.length || 0,
                    running: v.running || 0,
                },
            ])),
            rateLimits: structuredClone(this.inner.rateState || {}),
        };
    }
}
exports.ObservedApi = ObservedApi;
class RuntimeProbe {
    startedAt = Date.now();
    hist = (0, node_perf_hooks_1.monitorEventLoopDelay)({ resolution: 20 });
    enabled = false;
    priorCpu = process.cpuUsage();
    priorAt = node_perf_hooks_1.performance.now();
    priorUtil = node_perf_hooks_1.performance.eventLoopUtilization();
    start() {
        if (!this.enabled) {
            this.hist.enable();
            this.enabled = true;
        }
    }
    close() {
        this.hist.disable();
        this.enabled = false;
    }
    snapshot() {
        const now = node_perf_hooks_1.performance.now(), elapsed = now - this.priorAt, cpu = process.cpuUsage(this.priorCpu);
        const utilization = node_perf_hooks_1.performance.eventLoopUtilization(this.priorUtil);
        this.priorCpu = process.cpuUsage();
        this.priorAt = now;
        this.priorUtil = node_perf_hooks_1.performance.eventLoopUtilization();
        const memory = process.memoryUsage(), count = this.hist.count;
        const value = {
            pid: process.pid,
            node: process.version,
            startedAt: this.startedAt,
            uptimeSeconds: process.uptime(),
            rssBytes: memory.rss,
            heapUsedBytes: memory.heapUsed,
            heapTotalBytes: memory.heapTotal,
            cpuPercent: elapsed >= 100
                ? ((cpu.user + cpu.system) / (elapsed * 1000)) * 100
                : null,
            eventLoopUtilization: utilization.utilization,
            eventLoopP95Ms: count ? this.hist.percentile(95) / 1e6 : null,
            eventLoopMaxMs: count ? this.hist.max / 1e6 : null,
            samples: count,
            probeActive: this.enabled,
        };
        if (count)
            this.hist.reset();
        return value;
    }
}
exports.RuntimeProbe = RuntimeProbe;
function systemHealth(e) {
    const now = Date.now(), processMetrics = e.probe.snapshot(), lanes = e.scheduler.view(), broker = e.broker.snapshot();
    const components = [];
    components.push({
        id: "runtime",
        label: "Runtime Node",
        state: e.stopping
            ? "STOPPING"
            : processMetrics.probeActive
                ? "ALIVE"
                : "STARTING",
        lastSuccess: now,
        ageMs: 0,
        detail: processMetrics.probeActive
            ? "Respuesta HTTP y sonda del proceso medidas"
            : "Motor aún sin iniciar",
    });
    for (const lane of lanes)
        components.push({
            id: lane.name,
            label: lane.name,
            state: lane.health,
            lastAttempt: lane.lastStart,
            lastSuccess: lane.lastSuccess,
            ageMs: lane.lastSuccess ? now - lane.lastSuccess : null,
            latencyMs: lane.durationMs,
            runs: lane.runs,
            failures: lane.failures,
            detail: lane.error || lane.reason,
        });
    const operationalCoverage = e.exitCoverage(now);
    if (e.cfg.quant?.enabled) {
        const ledger = e.netLedger.view(), observations = e.quantObservations.view(now);
        components.push({ id: "net-account-data", label: "Contabilidad neta conciliada",
            state: ledger.reconciled && !["STALE", "ERROR", "BLOCKED"].includes(ledger.status) ? "READY" : ledger.status,
            lastSuccess: ledger.lastSuccess || null, ageMs: ledger.lastSuccess ? now - ledger.lastSuccess : null,
            economicComplete: ledger.economicComplete, detail: e.netAccountingError || ledger.blockers });
        components.push({ id: "quant-observation-data", label: "Observaciones prospectivas",
            state: e.quantObservationError ? "ERROR" : observations.status,
            lastSuccess: observations.lastSuccess, ageMs: observations.ageMs, frames: observations.frames,
            detail: e.quantObservationError || observations.error || observations.latest });
    }
    if (e.cfg.quant?.enabled && e.cfg.quant.discovery) {
        const d = e.quantDiscovery, age = Number.isFinite(d.at) ? Math.max(0, now - d.at) : null;
        components.push({
            id: "stock-etf-discovery-data", label: "Cobertura de acciones y ETF",
            state: d.health === "READY" && age !== null && age > 900000 ? "STALE" : d.health || "WAITING",
            lastAttempt: d.attempt_at || d.at || 0,
            lastSuccess: d.health === "READY" && d.persisted === true ? d.at : 0,
            ageMs: age, entryHold: e.discoveryHold,
            readySymbols: d.ready_symbols || [], pendingSymbols: d.pending_symbols || [],
            detail: d.reason || "Sin snapshot completo de descubrimiento",
        });
    }
    components.push({
        id: "exit-decisions",
        label: "Decisiones de salida por posición",
        state: operationalCoverage.state,
        lastAttempt: Math.max(0, ...operationalCoverage.positions.map((p) => p.lastAttempt || 0)),
        lastSuccess: operationalCoverage.lastCompletedAt || 0,
        ageMs: operationalCoverage.lastCompletedAt
            ? Math.max(0, now - operationalCoverage.lastCompletedAt)
            : null,
        total: operationalCoverage.total,
        completed: operationalCoverage.completed,
        fresh: operationalCoverage.fresh,
        deadlineMs: operationalCoverage.deadlineMs,
        entrySafe: operationalCoverage.entrySafe,
        detail: operationalCoverage.detail,
    });
    const storage = e.validators.checks["journal-write"];
    components.push({
        id: "storage",
        label: "SQLite durable",
        state: e.storageError
            ? "ERROR"
            : storage?.lastSuccess
                ? "ALIVE"
                : "WAITING",
        lastSuccess: storage?.lastSuccess || 0,
        ageMs: storage?.lastSuccess ? now - storage.lastSuccess : null,
        detail: e.storageError || "Última escritura confirmada por SQLite",
    });
    components.push({
        id: "broker-sync",
        label: "Cuenta y órdenes",
        state: e.reconcileError && e.reconcileError !== "STARTING"
            ? "ERROR"
            : !e.syncAt
                ? "WAITING"
                : now - e.syncAt > 15000
                    ? "STALE"
                    : "ALIVE",
        lastSuccess: e.syncAt || 0,
        ageMs: e.syncAt ? now - e.syncAt : null,
        detail: e.reconcileError || "Snapshot conciliado",
    });
    const books = e.healthBooks(now);
    for (const b of books)
        components.push({
            id: "data-" + b.book,
            label: "Datos " + b.book,
            state: b.dataState,
            lastSuccess: b.lastQuoteAt,
            ageMs: b.quoteAgeMs,
            detail: b.reason,
        });
    const actualHeld = e
        .active()
        .filter((c) => Number(e.position(c.symbol)?.qty || 0) > 0), protectedCount = actualHeld.filter((c) => e.confirmedProtection(c)).length, heldNativeCount = actualHeld.filter((c) => e.pending(c).some((i) => i.kind === "protect" && i.status === "held")).length;
    const protectionReconciled = Boolean(e.syncAt && !e.reconcileError && now >= e.syncAt && now - e.syncAt <= 10000);
    const aligned = actualHeld.filter((c) => (0, exits_1.protectionSnapshot)(c, e.state.intents, Number(e.position(c.symbol)?.qty || 0), now).aligned).length;
    components.push({
        id: "native-stop-alignment",
        label: "Stop calculado / broker",
        state: !actualHeld.length
            ? "IDLE"
            : !protectionReconciled
                ? "STALE"
                : aligned < actualHeld.length
                    ? "DEGRADED"
                    : heldNativeCount
                        ? "CONTINGENT"
                        : "ALIVE",
        lastSuccess: actualHeld.length ? e.syncAt : 0,
        ageMs: e.syncAt ? now - e.syncAt : null,
        detail: aligned +
            " / " +
            actualHeld.length +
            " posiciones con cantidad y piso observados; " +
            heldNativeCount +
            " con orden nativa held" +
            (protectionReconciled ? "" : " · conciliación sin vigencia"),
    });
    for (const s of e.streams.snapshot().channels) {
        const closed = s.name !== "orders" && s.name !== "crypto" && !e.session("equity");
        components.push({
            id: "stream-" + s.name,
            label: "Stream " + s.name,
            state: s.state === "RECONNECTING"
                ? "DEGRADED"
                : closed
                    ? "MARKET_CLOSED"
                    : s.state === "SUBSCRIBED"
                        ? s.name === "orders"
                            ? "CONNECTED_IDLE"
                            : s.lastEventAt && now - s.lastEventAt < 15000
                                ? "ALIVE"
                                : "WAITING"
                        : s.state,
            lastSuccess: s.lastEventAt || s.subscribedAt,
            ageMs: s.eventAgeMs,
            detail: s.error ||
                (s.name === "orders"
                    ? "Suscripción confirmada; inventario conciliado por REST"
                    : s.symbols + " símbolos · eventos recibidos y validados"),
        });
    }
    const fees = e.fees.view();
    components.push({
        id: "reported-fees",
        label: "Comisiones reportadas",
        state: fees.status === "ERROR"
            ? "ERROR"
            : fees.lastSuccess
                ? "ALIVE"
                : "WAITING",
        lastSuccess: fees.lastSuccess || 0,
        ageMs: fees.lastSuccess ? now - fees.lastSuccess : null,
        detail: fees.error ||
            "Actividades reales del broker; cobertura de costes se declara por separado",
    });
    const validatorErrors = e.validators
        .view()
        .filter((v) => v.status === "ERROR");
    const lab = e.ultimateLab.view(), futures = e.futures.view(now);
    components.push({
        id: "ultimate-registry",
        label: "Ultimate experimentos",
        state: lab.status === "ERROR"
            ? "ERROR"
            : lab.status === "RUNNING"
                ? "RUNNING"
                : lab.lastSuccess
                    ? "READY"
                    : "WAITING",
        lastSuccess: lab.lastSuccess,
        detail: lab.lastError ||
            `${lab.spent}/${lab.budget} ensayos registrados; no promoción automática`,
    });
    for (const [id, component] of [
        ["account", futures.account],
        ["market", futures.market],
    ])
        components.push({
            id: "ultimate-futures-" + id,
            label: "Futuros " + id,
            state: component.state,
            lastSuccess: component.lastSuccess,
            lastAttempt: component.lastAttempt,
            detail: component.error ||
                "Conector PAPER; estado derivado de respuestas del broker",
        });
    const critical = components.filter((c) => ["ERROR", "STALLED", "STALE", "DEGRADED"].includes(c.state));
    return {
        serverTime: now,
        sampledAt: now,
        sequence: e.healthSequence++,
        status: e.stopping
            ? "STOPPING"
            : critical.length ||
                validatorErrors.length ||
                protectedCount < actualHeld.length
                ? "DEGRADED"
                : !processMetrics.probeActive ||
                    !e.scheduler.lanes.some((l) => l.lastSuccess)
                    ? "STARTING"
                    : (operationalCoverage.total > 0 &&
                        operationalCoverage.state !== "ALIVE") ||
                        books.some((b) => b.dataState === "WAITING")
                        ? "WAIT_DATA"
                        : "ALIVE",
        source: "RUNTIME_OBSERVED",
        components,
        process: processMetrics,
        broker,
        books,
        operationalCoverage,
        validatorErrors: validatorErrors.length,
        protection: {
            positions: actualHeld.length,
            protected: protectedCount,
            pending: actualHeld.length - protectedCount,
            aligned,
            held: heldNativeCount,
            reconciled: protectionReconciled,
        },
        readiness: {
            entries: e.entryReady(),
            reason: e.state.halt ||
                e.storageError ||
                e.reconcileError ||
                (e.state.paused ? "PAUSED" : "DATA_AND_SIGNAL_GATES_APPLY"),
        },
        measuredHistory: e.metricHistory.slice(-120),
    };
}
