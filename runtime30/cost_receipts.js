"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.LocalCostReceiptSource = exports.CostReceiptError = void 0;
exports.validateCostReceipt = validateCostReceipt;
exports.verifyBrokerAccrualCoverage = verifyBrokerAccrualCoverage;
exports.writeCostReceiptFile = writeCostReceiptFile;
const node_crypto_1 = require("node:crypto");
const node_fs_1 = require("node:fs");
const node_path_1 = __importDefault(require("node:path"));
const CATEGORIES = ["DATA", "INFRASTRUCTURE", "INFERENCE", "OTHER"];
class CostReceiptError extends Error {
    code;
    constructor(code) {
        super(code);
        this.code = code;
    }
}
exports.CostReceiptError = CostReceiptError;
function fail(code) { throw new CostReceiptError(code); }
function object(value) {
    if (!value || typeof value !== "object" || Array.isArray(value))
        fail("COST_RECEIPT_OBJECT_REQUIRED");
    return value;
}
function keys(row, allowed) {
    if (Object.keys(row).some(k => !allowed.includes(k)))
        fail("COST_RECEIPT_UNKNOWN_FIELD");
}
function text(value, code, maximum = 1000) {
    if (typeof value !== "string" || !value.trim() || value.length > maximum || /[\x00-\x1f\x7f]/.test(value))
        fail(code);
    return value;
}
function time(value) {
    if (typeof value === "string") {
        const date = value.slice(0, 10), day = Date.parse(date);
        if (!/^\d{4}-\d{2}-\d{2}T/.test(value) || !Number.isFinite(day) || new Date(day).toISOString().slice(0, 10) !== date)
            fail("COST_RECEIPT_TIME_INVALID");
    }
    const n = typeof value === "number" ? value : typeof value === "string" && /T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? Date.parse(value) : NaN;
    if (!Number.isSafeInteger(n) || n <= 0)
        fail("COST_RECEIPT_TIME_INVALID");
    return n;
}
/** JSON.parse silently accepts duplicate keys. This bounded scanner rejects
 * duplicates at every object level before the native parser is used. */
function parseStrict(raw) {
    let cursor = 0, nodes = 0;
    const space = () => { while (/\s/.test(raw[cursor] ?? "") && cursor < raw.length)
        cursor++; };
    const string = () => {
        const start = cursor++;
        while (cursor < raw.length) {
            const c = raw[cursor++];
            if (c === "\\") {
                cursor++;
                continue;
            }
            if (c === '"') {
                try {
                    return JSON.parse(raw.slice(start, cursor));
                }
                catch {
                    fail("COST_RECEIPT_JSON_INVALID");
                }
            }
        }
        fail("COST_RECEIPT_JSON_INVALID");
    };
    const value = (depth) => {
        if (depth > 12 || ++nodes > 400000)
            fail("COST_RECEIPT_JSON_BOUND");
        space();
        const c = raw[cursor];
        if (c === '"') {
            string();
            return;
        }
        if (c === "{") {
            cursor++;
            space();
            const seen = new Set();
            if (raw[cursor] === "}") {
                cursor++;
                return;
            }
            while (cursor < raw.length) {
                space();
                if (raw[cursor] !== '"')
                    fail("COST_RECEIPT_JSON_INVALID");
                const key = string();
                if (seen.has(key))
                    fail("COST_RECEIPT_DUPLICATE_JSON_KEY");
                seen.add(key);
                space();
                if (raw[cursor++] !== ":")
                    fail("COST_RECEIPT_JSON_INVALID");
                value(depth + 1);
                space();
                if (raw[cursor] === "}") {
                    cursor++;
                    return;
                }
                if (raw[cursor++] !== ",")
                    fail("COST_RECEIPT_JSON_INVALID");
            }
            fail("COST_RECEIPT_JSON_INVALID");
        }
        if (c === "[") {
            cursor++;
            space();
            if (raw[cursor] === "]") {
                cursor++;
                return;
            }
            while (cursor < raw.length) {
                value(depth + 1);
                space();
                if (raw[cursor] === "]") {
                    cursor++;
                    return;
                }
                if (raw[cursor++] !== ",")
                    fail("COST_RECEIPT_JSON_INVALID");
            }
            fail("COST_RECEIPT_JSON_INVALID");
        }
        const match = /^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/.exec(raw.slice(cursor));
        if (!match)
            fail("COST_RECEIPT_JSON_INVALID");
        cursor += match[0].length;
    };
    value(0);
    space();
    if (cursor !== raw.length)
        fail("COST_RECEIPT_JSON_INVALID");
    try {
        return JSON.parse(raw);
    }
    catch {
        fail("COST_RECEIPT_JSON_INVALID");
    }
}
function validateCostReceipt(input, accountId, now = Date.now()) {
    const row = object(input);
    keys(row, ["schema", "account_id", "currency", "receipt_id", "coverage_complete", "from", "through", "known_at", "reference", "categories", "entries", "broker_accrual_coverage"]);
    if (row.schema !== "HARPOON_COST_RECEIPT_1")
        fail("COST_RECEIPT_SCHEMA_INVALID");
    if (row.account_id !== accountId)
        fail("COST_RECEIPT_ACCOUNT_MISMATCH");
    if (row.currency !== "USD")
        fail("COST_RECEIPT_CURRENCY_UNKNOWN");
    if (row.coverage_complete !== true)
        fail("COST_RECEIPT_COVERAGE_NOT_DECLARED_COMPLETE");
    text(row.receipt_id, "COST_RECEIPT_ID_REQUIRED", 500);
    text(row.reference, "COST_RECEIPT_REFERENCE_REQUIRED");
    const from = time(row.from), through = time(row.through), known = time(row.known_at);
    if (from > through || through > known || known > now)
        fail("COST_RECEIPT_FUTURE_OR_REVERSED");
    if (!Array.isArray(row.categories) || row.categories.length !== 4 ||
        [...new Set(row.categories)].sort().join("|") !== [...CATEGORIES].sort().join("|"))
        fail("COST_RECEIPT_CATEGORIES_INCOMPLETE");
    if (!Array.isArray(row.entries) || row.entries.length > 20000)
        fail("COST_RECEIPT_ENTRIES_INVALID");
    const seen = new Set(), links = new Set();
    for (const inputEntry of row.entries) {
        const e = object(inputEntry);
        keys(e, ["id", "at", "known_at", "amount_usd", "reference", "category", "already_in_account", "activity_id"]);
        const id = text(e.id, "COST_RECEIPT_ENTRY_ID_REQUIRED", 500);
        if (seen.has(id))
            fail("COST_RECEIPT_DUPLICATE_ENTRY");
        seen.add(id);
        text(e.reference, "COST_RECEIPT_ENTRY_REFERENCE_REQUIRED");
        const at = time(e.at), knownAt = time(e.known_at);
        if (at < from || at > through || knownAt < at || knownAt > known)
            fail("COST_RECEIPT_ENTRY_TIME_INVALID");
        if (typeof e.amount_usd !== "number" || !Number.isFinite(e.amount_usd) || e.amount_usd < 0)
            fail("COST_RECEIPT_AMOUNT_UNKNOWN");
        if (!CATEGORIES.includes(e.category))
            fail("COST_RECEIPT_ENTRY_CATEGORY_INVALID");
        if (typeof e.already_in_account !== "boolean")
            fail("COST_RECEIPT_ACCOUNT_TREATMENT_UNKNOWN");
        if (e.already_in_account) {
            const link = text(e.activity_id, "COST_RECEIPT_ACTIVITY_LINK_REQUIRED", 500);
            if (links.has(link))
                fail("COST_RECEIPT_DUPLICATE_ACTIVITY_LINK");
            links.add(link);
        }
        else if (e.activity_id !== undefined && e.activity_id !== null)
            fail("COST_RECEIPT_EXTERNAL_LINK_AMBIGUOUS");
    }
    if (row.broker_accrual_coverage !== undefined && row.broker_accrual_coverage !== null) {
        if (time(object(row.broker_accrual_coverage).known_at) > known)
            fail("BROKER_ACCRUAL_KNOWLEDGE_AFTER_RECEIPT");
        verifyBrokerAccrualCoverage(row.broker_accrual_coverage, row.entries, accountId, now, from, through);
    }
    // An explicitly complete, empty report is a caller declaration of no listed
    // expenses in its interval. Missing fields/files are never such a declaration.
    return structuredClone(row);
}
const ACCRUAL_FIELDS = ["account_id", "currency", "from", "through", "known_at", "applicable_categories",
    "coverage_complete", "pending_total_usd", "explicit_zero"];
const ACCRUAL_CATEGORIES = ["COMMISSIONS", "EXCHANGE_CLEARING", "REGULATORY", "FINANCING", "BORROW", "OTHER"];
function pointer(document, value) {
    const p = text(value, "BROKER_ACCRUAL_DOCUMENT_POINTER_INVALID", 1000);
    if (!p.startsWith("/"))
        fail("BROKER_ACCRUAL_DOCUMENT_POINTER_INVALID");
    let current = document;
    for (const encoded of p.slice(1).split("/")) {
        if (/~(?:[^01]|$)/.test(encoded))
            fail("BROKER_ACCRUAL_DOCUMENT_POINTER_INVALID");
        const key = encoded.replace(/~1/g, "/").replace(/~0/g, "~");
        if (current === null || typeof current !== "object" || !Object.prototype.hasOwnProperty.call(current, key))
            fail("BROKER_ACCRUAL_DOCUMENT_FIELD_MISSING");
        current = current[key];
    }
    return current;
}
/** Optional documentary coverage. The original JSON bytes and explicit pointer
 * bindings must support the declaration. Linked pending charges are already in
 * external costs: this function never changes or subtracts monetary amounts. */
function verifyBrokerAccrualCoverage(raw, entries, accountId, now, requiredFrom, requiredThrough) {
    const scope = "DECLARED_DOCUMENT_BOUND_AND_COST_RECONCILED_NOT_EXTERNALLY_AUTHENTICATED";
    if (raw === undefined || raw === null)
        return { verified: false, amountUsd: null, from: null, through: null,
            reason: "BROKER_ACCRUAL_DOCUMENT_NOT_PROVIDED", scope, sourceAuthenticityVerified: false };
    const c = object(raw);
    keys(c, ["schema", ...ACCRUAL_FIELDS, "reference", "cost_ids", "document"]);
    if (c.schema !== "HARPOON_BROKER_ACCRUAL_COVERAGE_1")
        fail("BROKER_ACCRUAL_SCHEMA_INVALID");
    if (c.account_id !== accountId || c.currency !== "USD")
        fail("BROKER_ACCRUAL_ACCOUNT_OR_CURRENCY_MISMATCH");
    const from = time(c.from), through = time(c.through), known = time(c.known_at);
    if (from > through || through > known || known > now || c.coverage_complete !== true)
        fail("BROKER_ACCRUAL_COVERAGE_INVALID");
    if (!Array.isArray(c.applicable_categories) || !c.applicable_categories.length || c.applicable_categories.length > ACCRUAL_CATEGORIES.length ||
        new Set(c.applicable_categories).size !== c.applicable_categories.length || c.applicable_categories.some((v) => !ACCRUAL_CATEGORIES.includes(v)))
        fail("BROKER_ACCRUAL_APPLICABLE_CATEGORIES_REQUIRED");
    if (typeof c.pending_total_usd !== "number" || !Number.isFinite(c.pending_total_usd) || c.pending_total_usd < 0 ||
        typeof c.explicit_zero !== "boolean" || c.explicit_zero !== (c.pending_total_usd === 0))
        fail("BROKER_ACCRUAL_AMOUNT_OR_EXPLICIT_ZERO_INVALID");
    text(c.reference, "BROKER_ACCRUAL_REFERENCE_REQUIRED");
    if (!Array.isArray(c.cost_ids) || c.cost_ids.length > 20000 || new Set(c.cost_ids).size !== c.cost_ids.length)
        fail("BROKER_ACCRUAL_COST_LINKS_INVALID");
    const document = object(c.document);
    keys(document, ["reference", "content_type", "content", "sha256", "bindings"]);
    text(document.reference, "BROKER_ACCRUAL_ORIGINAL_REFERENCE_REQUIRED");
    if (document.content_type !== "application/json" || typeof document.content !== "string" ||
        Buffer.byteLength(document.content) > 262144 || !/^[0-9a-f]{64}$/.test(document.sha256 ?? "") ||
        (0, node_crypto_1.createHash)("sha256").update(document.content).digest("hex") !== document.sha256)
        fail("BROKER_ACCRUAL_ORIGINAL_DOCUMENT_HASH_INVALID");
    const original = parseStrict(document.content), bindings = object(document.bindings);
    keys(bindings, ACCRUAL_FIELDS);
    for (const field of ACCRUAL_FIELDS) {
        const value = pointer(original, bindings[field]);
        if (["from", "through", "known_at"].includes(field)) {
            if (time(value) !== time(c[field]))
                fail("BROKER_ACCRUAL_DOCUMENT_VALUE_MISMATCH");
        }
        else if (field === "pending_total_usd") {
            if ((typeof value !== "number" && (typeof value !== "string" || !value.trim())) || !Number.isFinite(Number(value)) || Number(value) !== c[field])
                fail("BROKER_ACCRUAL_DOCUMENT_VALUE_MISMATCH");
        }
        else if (field === "applicable_categories") {
            if (!Array.isArray(value) || value.length !== c[field].length || [...value].sort().join("|") !== [...c[field]].sort().join("|"))
                fail("BROKER_ACCRUAL_DOCUMENT_VALUE_MISMATCH");
        }
        else if (value !== c[field])
            fail("BROKER_ACCRUAL_DOCUMENT_VALUE_MISMATCH");
    }
    let linked = 0, allWithinComparedPeriod = true;
    const byId = new Map(entries.map(e => [e.id, e]));
    for (const id of c.cost_ids) {
        text(id, "BROKER_ACCRUAL_COST_ID_INVALID", 500);
        const e = byId.get(id);
        if (!e || e.already_in_account !== false || e.category !== "OTHER" ||
            (e.reference !== c.reference && e.reference !== document.reference) ||
            typeof e.amount_usd !== "number" || !Number.isFinite(e.amount_usd) || e.amount_usd <= 0 ||
            time(e.at) < from || time(e.at) > through)
            fail("BROKER_ACCRUAL_EXTERNAL_COST_LINK_INVALID");
        linked += e.amount_usd;
        if (time(e.at) <= requiredFrom || time(e.at) > requiredThrough)
            allWithinComparedPeriod = false;
    }
    if (Math.abs(linked - c.pending_total_usd) > 1e-8 || c.pending_total_usd === 0 && c.cost_ids.length !== 0)
        fail("BROKER_ACCRUAL_COST_SUM_MISMATCH");
    const complete = from <= requiredFrom && through >= requiredThrough && allWithinComparedPeriod;
    return { verified: complete, amountUsd: complete ? c.pending_total_usd : null, from, through, knownAt: known,
        comparedFrom: requiredFrom, comparedThrough: requiredThrough,
        reason: complete ? null : "BROKER_ACCRUAL_DOCUMENT_DOES_NOT_COVER_COMPARED_PERIOD",
        documentSha256: document.sha256, reference: c.reference, linkedCostIds: [...c.cost_ids],
        applicableCategories: [...c.applicable_categories], costsAlreadyIncludedInEconomicPnl: true,
        authorizesAdditionalCostSubtraction: false, scope, sourceAuthenticityVerified: false };
}
class LocalCostReceiptSource {
    filename;
    maxBytes;
    cache = null;
    constructor(filename, maxBytes = 8 * 1024 * 1024) {
        if (filename !== undefined && filename !== null && (typeof filename !== "string" || !filename.trim() || /[\x00-\x1f\x7f]/.test(filename)))
            fail("COST_RECEIPT_FILE_CONFIG_INVALID");
        this.filename = typeof filename === "string" ? node_path_1.default.resolve(filename) : null;
        if (typeof maxBytes !== "number" || !Number.isSafeInteger(maxBytes) || maxBytes < 1024 || maxBytes > 32 * 1024 * 1024)
            fail("COST_RECEIPT_FILE_BOUND_INVALID");
        this.maxBytes = maxBytes;
    }
    async read(accountId, now, previous) {
        const base = { type: "LOCAL_DECLARED_COST_RECEIPT", path: this.filename, receivedAt: now,
            sourceAuthenticityVerified: false, coverageIndependentlyVerified: false, maxBytes: this.maxBytes };
        if (this.filename === null)
            return { report: null, source: { ...base, status: "NOT_CONFIGURED", reason: "COST_RECEIPT_FILE_NOT_CONFIGURED" } };
        let handle;
        try {
            handle = await node_fs_1.promises.open(this.filename, node_fs_1.constants.O_RDONLY | node_fs_1.constants.O_NOFOLLOW);
            const before = await handle.stat({ bigint: true });
            if (!before.isFile() || before.size > BigInt(this.maxBytes))
                fail("COST_RECEIPT_FILE_NOT_REGULAR_OR_TOO_LARGE");
            const chunks = [];
            let count = 0;
            while (count <= this.maxBytes) {
                const buffer = Buffer.alloc(Math.min(65536, this.maxBytes + 1 - count));
                const result = await handle.read(buffer, 0, buffer.length, null);
                if (!result.bytesRead)
                    break;
                count += result.bytesRead;
                chunks.push(buffer.subarray(0, result.bytesRead));
            }
            if (count > this.maxBytes)
                fail("COST_RECEIPT_FILE_TOO_LARGE");
            const after = await handle.stat({ bigint: true });
            if (before.dev !== after.dev || before.ino !== after.ino || before.size !== after.size || before.mtimeNs !== after.mtimeNs ||
                BigInt(count) !== after.size)
                fail("COST_RECEIPT_CHANGED_DURING_READ");
            const bytes = Buffer.concat(chunks), hash = (0, node_crypto_1.createHash)("sha256").update(bytes).digest("hex");
            let report = this.cache?.hash === hash ? this.cache.report : validateCostReceipt(parseStrict(new TextDecoder("utf-8", { fatal: true }).decode(bytes)), accountId, now);
            if (report.account_id !== accountId)
                fail("COST_RECEIPT_ACCOUNT_MISMATCH");
            if (time(report.known_at) > now)
                fail("COST_RECEIPT_FUTURE_OR_REVERSED");
            const accepted = previous?.lastAccepted ?? (previous?.status === "READ" ? previous : null);
            if (accepted?.receiptId === report.receipt_id && accepted.fileSha256 !== hash)
                fail("COST_RECEIPT_ID_REUSED_WITH_CHANGED_BYTES");
            report = structuredClone(report);
            this.cache = { hash, report };
            const source = { ...base, status: "READ", receiptId: report.receipt_id, fileSha256: hash, bytes: count,
                firstReceivedAt: accepted?.fileSha256 === hash ? accepted.firstReceivedAt : now,
                producerKnownAt: time(report.known_at), coverageFrom: time(report.from), coverageThrough: time(report.through),
                interpretation: "LOCAL_DECLARATION_REQUIRES_LEDGER_RECONCILIATION; HASH_DOES_NOT_AUTHENTICATE_PROVIDER" };
            return { report, source };
        }
        catch (error) {
            const code = error instanceof CostReceiptError ? error.code : error?.code === "ENOENT" ? "COST_RECEIPT_FILE_MISSING" : "COST_RECEIPT_FILE_READ_OR_ENCODING_FAILED";
            return { report: null, source: { ...base, status: code === "COST_RECEIPT_FILE_MISSING" ? "MISSING" : "INVALID", reason: code,
                    lastAccepted: previous?.lastAccepted ?? (previous?.status === "READ" ? previous : null) } };
        }
        finally {
            await handle?.close();
        }
    }
}
exports.LocalCostReceiptSource = LocalCostReceiptSource;
/** Explicit local producer: receives every declaration from the caller, validates
 * it, and atomically replaces a receipt. No billing rate, charge or zero is
 * inferred, and no external provider is contacted. */
async function writeCostReceiptFile(filename, input, accountId, now = Date.now()) {
    const receipt = validateCostReceipt(input, accountId, now);
    const target = node_path_1.default.resolve(text(filename, "COST_RECEIPT_FILE_CONFIG_INVALID", 4096));
    const bytes = Buffer.from(JSON.stringify(receipt, null, 2) + "\n");
    if (bytes.length > 8 * 1024 * 1024)
        fail("COST_RECEIPT_FILE_TOO_LARGE");
    const temporary = target + ".pending-" + (0, node_crypto_1.randomUUID)();
    let handle;
    try {
        handle = await node_fs_1.promises.open(temporary, "wx", 0o600);
        await handle.writeFile(bytes);
        await handle.sync();
        await handle.close();
        handle = undefined;
        await node_fs_1.promises.rename(temporary, target);
        const directory = await node_fs_1.promises.open(node_path_1.default.dirname(target), "r");
        try {
            await directory.sync();
        }
        finally {
            await directory.close();
        }
        return { status: "LOCAL_RECEIPT_WRITTEN", receiptId: receipt.receipt_id,
            fileSha256: (0, node_crypto_1.createHash)("sha256").update(bytes).digest("hex"), bytes: bytes.length,
            sourceAuthenticityVerified: false, financialAuthorization: false };
    }
    finally {
        await handle?.close();
        try {
            await node_fs_1.promises.unlink(temporary);
        }
        catch (error) {
            if (error.code !== "ENOENT")
                throw error;
        }
    }
}
