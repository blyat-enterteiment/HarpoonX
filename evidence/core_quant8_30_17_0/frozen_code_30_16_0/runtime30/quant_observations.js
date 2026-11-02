"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.QuantObservationJournal = void 0;
const node_crypto_1 = require("node:crypto");
const node_zlib_1 = require("node:zlib");
const ultimate_contracts_1 = require("./ultimate_contracts");
const sessions_1 = require("./sessions");
const hash = (value) => (0, node_crypto_1.createHash)("sha256").update(value).digest("hex");
const jsonBytes = (value) => Buffer.byteLength(JSON.stringify(value));
const boundedInt = (value, fallback, lo, hi, field) => {
    const n = value === undefined ? fallback : value;
    if (typeof n !== "number" || !Number.isInteger(n) || n < lo || n > hi)
        throw Error("OBSERVATION_CONFIG_" + field);
    return n;
};
/** Prospective evidence, not a claim that a sampled quote was executable.
 * Reserve bounded storage, retain immutable frame/segment objects, then commit
 * one index. Only that acknowledged commit advances the continuous cursor.
 * Orphans consume reserved capacity but never become observations silently.
 */
class QuantObservationJournal {
    store;
    key;
    accountId;
    index;
    status = "UNVERIFIED";
    error = null;
    lastAttempt = 0;
    loaded = false;
    writing = false;
    budget;
    exportRegistry = { schema: "HARPOON_OBSERVATION_SNAPSHOTS_1", snapshots: [] };
    exportRows = new Map();
    metadataTail = Promise.resolve();
    exportBytes = 0;
    maxFrames;
    maxArchives;
    maxStoredBytes;
    maxFrameBytes;
    maxAgeMs;
    maxSymbolsPerCapture;
    intervalMs;
    constructor(store, key, accountId, config = {}) {
        this.store = store;
        this.key = key;
        this.accountId = accountId;
        this.maxFrames = boundedInt(config.maxFrames, 10000, 2, 100000, "FRAMES");
        this.maxArchives = boundedInt(config.maxArchives, 16, 0, 256, "ARCHIVES");
        this.maxStoredBytes = boundedInt(config.maxStoredBytes, 536870912, 1024, 2147483648, "STORED_BYTES");
        this.maxFrameBytes = boundedInt(config.maxFrameBytes, 4194304, 1024, 16777216, "BYTES");
        this.intervalMs = boundedInt(config.intervalMs, 60000, 30000, 300000, "INTERVAL");
        this.maxAgeMs = boundedInt(config.maxAgeMs, this.intervalMs * 3, this.intervalMs, 900000, "AGE");
        this.maxSymbolsPerCapture = boundedInt(config.maxSymbolsPerCapture, 12, 1, 48, "SYMBOLS");
        this.index = { schema: "HARPOON_OBSERVATION_INDEX_1", account_id: accountId,
            configuration_hash: (0, ultimate_contracts_1.digest)(config), layout_version: 2, frames: [], archives: [], total_frames: 0,
            committed_bytes: 0, head: "GENESIS", last_summary: null };
        this.budget = { schema: "HARPOON_OBSERVATION_STORAGE_BUDGET_1", account_id: accountId,
            configuration_hash: (0, ultimate_contracts_1.digest)(config), charged_bytes: 0, last_batch: null, last_bytes: 0 };
    }
    async load() {
        this.loaded = false;
        try {
            const saved = await this.store.get(this.key);
            if (saved) {
                const { integrity_hash: seal, ...body } = saved;
                if (seal !== (0, ultimate_contracts_1.digest)(body) || body.schema !== this.index.schema || body.account_id !== this.accountId ||
                    body.configuration_hash !== this.index.configuration_hash || !Array.isArray(body.frames) || body.frames.length > this.maxFrames)
                    throw Error("OBSERVATION_INDEX_INTEGRITY_OR_BINDING");
                const rows = await this.validatedRows(body);
                let committed = (body.archives || []).reduce((n, r) => n + r.stored_bytes, 0);
                for (const row of rows) {
                    // The pre-segmentation layout did not record packed bytes. Measure
                    // those retained objects once on migration; do not rewrite their chain.
                    committed += row.stored_bytes ?? jsonBytes(await this.store.get(row.frame_key));
                }
                if (body.committed_bytes !== undefined && body.committed_bytes !== committed)
                    throw Error("OBSERVATION_COMMITTED_BYTES_INTEGRITY");
                this.index = { ...body, layout_version: 2, archives: body.archives || [], total_frames: rows.length, committed_bytes: committed };
                if (rows.length)
                    await this.readFrame(rows.at(-1));
            }
            const savedBudget = await this.store.get(this.key + "-storage-budget");
            if (savedBudget) {
                const { integrity_hash: seal, ...body } = savedBudget;
                if (seal !== (0, ultimate_contracts_1.digest)(body) || body.schema !== this.budget.schema || body.account_id !== this.accountId ||
                    body.configuration_hash !== this.budget.configuration_hash || !Number.isSafeInteger(body.charged_bytes) ||
                    body.charged_bytes < this.index.committed_bytes || body.charged_bytes > this.maxStoredBytes)
                    throw Error("OBSERVATION_STORAGE_BUDGET_INTEGRITY");
                this.budget = body;
            }
            else {
                this.budget.charged_bytes = this.index.committed_bytes;
                if (this.budget.charged_bytes > this.maxStoredBytes)
                    throw Error("OBSERVATION_STORAGE_BUDGET_EXHAUSTED");
                if (this.index.total_frames)
                    await this.store.put(this.key + "-storage-budget", { ...this.budget, integrity_hash: (0, ultimate_contracts_1.digest)(this.budget) });
            }
            const exports = await this.store.get(this.key + "-export-snapshots");
            if (exports) {
                const { integrity_hash, ...registry } = exports;
                if (integrity_hash !== (0, ultimate_contracts_1.digest)(registry) || registry.schema !== this.exportRegistry.schema ||
                    registry.account_id !== this.accountId || registry.configuration_hash !== this.index.configuration_hash ||
                    !Array.isArray(registry.snapshots) || registry.snapshots.length > 2 || jsonBytes(exports) > 16777216)
                    throw Error("OBSERVATION_SNAPSHOT_REGISTRY_INTEGRITY");
                const ids = new Set();
                for (const snapshot of registry.snapshots) {
                    this.checkSnapshot(snapshot);
                    if (ids.has(snapshot.snapshot_id))
                        throw Error("OBSERVATION_SNAPSHOT_DUPLICATE");
                    ids.add(snapshot.snapshot_id);
                    // Verify the retained immutable chain after restart, before any page is served.
                    this.exportRows.set(snapshot.snapshot_id, await this.validatedRows(snapshot.index));
                }
                this.exportRegistry = registry;
                this.exportBytes = jsonBytes(exports);
                if (this.budget.charged_bytes + this.exportBytes > this.maxStoredBytes)
                    throw Error("OBSERVATION_STORAGE_BUDGET_EXHAUSTED");
            }
            this.loaded = true;
            this.error = null;
            this.status = this.index.total_frames ? "RESTORED" : "WAIT_FIRST_CAPTURE";
        }
        catch (error) {
            this.fail(error);
            throw error;
        }
        return this.view();
    }
    fail(error) {
        this.status = "ERROR";
        this.error = String(error);
    }
    async readArchive(reference) {
        const saved = await this.store.get(reference.segment_key);
        if (!saved)
            throw Error("OBSERVATION_ARCHIVE_MISSING");
        const { integrity_hash: seal, ...body } = saved;
        if (seal !== (0, ultimate_contracts_1.digest)(body) || seal !== reference.segment_hash || body.schema !== "HARPOON_OBSERVATION_SEGMENT_1" ||
            body.account_id !== this.accountId || body.configuration_hash !== this.index.configuration_hash ||
            !Array.isArray(body.frames) || body.frames.length !== this.maxFrames ||
            reference.segment_key !== this.key + "-archive-" + seal || reference.stored_bytes !== jsonBytes(saved) ||
            reference.ordinal !== body.ordinal || reference.first_sequence !== body.frames[0]?.sequence ||
            reference.last_sequence !== body.frames.at(-1)?.sequence || reference.previous !== body.frames[0]?.previous ||
            reference.head !== body.frames.at(-1)?.chain_hash || reference.last_at !== body.frames.at(-1)?.at)
            throw Error("OBSERVATION_ARCHIVE_INTEGRITY");
        return body;
    }
    async validatedRows(body = this.index) {
        const archives = body.archives || [];
        if (!Array.isArray(archives) || archives.length > this.maxArchives ||
            !Array.isArray(body.frames) || body.frames.length > this.maxFrames ||
            (archives.length > 0 && body.frames.length === 0))
            throw Error("OBSERVATION_SEGMENT_BOUNDS");
        const rows = [];
        for (const [i, reference] of archives.entries()) {
            if (reference.ordinal !== i + 1 || reference.first_sequence !== rows.length + 1)
                throw Error("OBSERVATION_ARCHIVE_SEQUENCE");
            const segment = await this.readArchive(reference);
            rows.push(...segment.frames);
        }
        rows.push(...body.frames);
        let previous = "GENESIS", at = -Infinity;
        for (const [i, row] of rows.entries()) {
            const { chain_hash: chain, ...record } = row;
            if (row.sequence !== i + 1 || row.previous !== previous || chain !== (0, ultimate_contracts_1.digest)(record) ||
                !Number.isFinite(row.at) || row.at <= at || !/^[a-f0-9]{64}$/.test(row.frame_hash) ||
                row.frame_key !== this.key + "-frame-" + row.frame_hash ||
                (row.stored_bytes !== undefined && (!Number.isSafeInteger(row.stored_bytes) || row.stored_bytes <= 0)))
                throw Error("OBSERVATION_CHAIN_INTEGRITY");
            previous = chain;
            at = row.at;
            // A long export must let position-protection callbacks advance. The
            // caller holds a committed index value, so yielding cannot change scope.
            if ((i + 1) % 512 === 0)
                await new Promise(resolve => setImmediate(resolve));
        }
        if (body.head !== previous || (body.total_frames !== undefined && body.total_frames !== rows.length))
            throw Error("OBSERVATION_HEAD_INTEGRITY");
        return rows;
    }
    async reserve(parts) {
        if (!parts.length)
            return;
        return this.withMetadata(async () => {
            const batch = (0, ultimate_contracts_1.digest)(parts), bytes = parts.reduce((n, p) => n + p.bytes, 0);
            if (this.budget.last_batch === batch)
                return; // Retry of the same reserved write.
            if (this.budget.charged_bytes + bytes + this.exportBytes > this.maxStoredBytes)
                throw Error("OBSERVATION_STORAGE_BUDGET_EXHAUSTED");
            const next = { ...this.budget, charged_bytes: this.budget.charged_bytes + bytes, last_batch: batch, last_bytes: bytes };
            // Reserve before immutable writes. Failed writes/commits may conservatively
            // consume quota; they can never generate unbudgeted orphan payloads.
            await this.store.put(this.key + "-storage-budget", { ...next, integrity_hash: (0, ultimate_contracts_1.digest)(next) });
            this.budget = next;
        });
    }
    async withMetadata(run) {
        const prior = this.metadataTail;
        let release;
        this.metadataTail = new Promise(resolve => { release = resolve; });
        await prior;
        try {
            return await run();
        }
        finally {
            release();
        }
    }
    checkSnapshot(snapshot) {
        const h = snapshot?.descriptor, index = snapshot?.index;
        if (!h || !index || h.schema !== "HARPOON_OBSERVATION_SNAPSHOT_1" ||
            h.account_id !== this.accountId || h.configuration_hash !== this.index.configuration_hash ||
            snapshot.snapshot_id !== (0, ultimate_contracts_1.digest)(h) || h.index_hash !== (0, ultimate_contracts_1.digest)(index) ||
            h.head !== index.head || h.total_frames !== index.total_frames || h.account_id !== index.account_id ||
            h.configuration_hash !== index.configuration_hash || !Number.isSafeInteger(h.captured_at) ||
            h.execution_allowed !== false || h.liveApproved !== false)
            throw Error("OBSERVATION_SNAPSHOT_BINDING");
    }
    /** Pin a committed prefix. Two bounded metadata slots survive restart; frames remain immutable. */
    async snapshotExport() {
        if (!this.loaded)
            throw Error("OBSERVATION_LOAD_REQUIRED");
        // Capture never waits for an export scan: the index is copied before the first await.
        const index = structuredClone(this.index);
        const rows = await this.validatedRows(index);
        return this.withMetadata(async () => {
            const existing = this.exportRegistry.snapshots.find((s) => s.descriptor.index_hash === (0, ultimate_contracts_1.digest)(index));
            if (existing)
                return { snapshot_id: existing.snapshot_id, ...existing.descriptor };
            const descriptor = { schema: "HARPOON_OBSERVATION_SNAPSHOT_1", account_id: this.accountId,
                configuration_hash: index.configuration_hash, head: index.head, total_frames: index.total_frames,
                index_hash: (0, ultimate_contracts_1.digest)(index), captured_at: Date.now(), execution_allowed: false, liveApproved: false };
            const snapshot = { snapshot_id: (0, ultimate_contracts_1.digest)(descriptor), descriptor, index };
            const snapshots = [...this.exportRegistry.snapshots.slice(-1), snapshot];
            const body = { schema: this.exportRegistry.schema, account_id: this.accountId,
                configuration_hash: this.index.configuration_hash, snapshots };
            const saved = { ...body, integrity_hash: (0, ultimate_contracts_1.digest)(body) }, bytes = jsonBytes(saved);
            if (bytes > 16777216 || this.budget.charged_bytes + bytes > this.maxStoredBytes)
                throw Error("OBSERVATION_SNAPSHOT_METADATA_BUDGET");
            // A rejected store acknowledgement might still have committed the new
            // mutable registry. Keep the larger reservation until a later ACK/load.
            this.exportBytes = Math.max(this.exportBytes, bytes);
            await this.store.put(this.key + "-export-snapshots", saved);
            this.exportRegistry = body;
            this.exportBytes = bytes;
            const retained = new Set(snapshots.map((s) => s.snapshot_id));
            for (const id of this.exportRows.keys())
                if (!retained.has(id))
                    this.exportRows.delete(id);
            this.exportRows.set(snapshot.snapshot_id, rows);
            return { snapshot_id: snapshot.snapshot_id, ...descriptor };
        });
    }
    async exportSnapshot(snapshotId, offset = 0, limit = 100) {
        if (!this.loaded)
            throw Error("OBSERVATION_LOAD_REQUIRED");
        if (!/^[a-f0-9]{64}$/.test(snapshotId))
            throw Error("OBSERVATION_SNAPSHOT_ID");
        const snapshot = this.exportRegistry.snapshots.find((s) => s.snapshot_id === snapshotId);
        if (!snapshot)
            throw Error("OBSERVATION_SNAPSHOT_MISSING_OR_EVICTED");
        this.checkSnapshot(snapshot);
        boundedInt(offset, 0, 0, snapshot.descriptor.total_frames, "OFFSET");
        boundedInt(limit, 100, 1, 100, "EXPORT_LIMIT");
        let rows = this.exportRows.get(snapshotId);
        if (!rows) {
            rows = await this.validatedRows(snapshot.index);
            // Another export may evict this token while the archive read awaits.
            // The in-flight page remains pinned, but an evicted token is never cached again.
            if (this.exportRegistry.snapshots.some((s) => s.snapshot_id === snapshotId))
                this.exportRows.set(snapshotId, rows);
        }
        const frames = [], records = [];
        let bytes = 2048;
        for (const row of rows.slice(offset, offset + limit)) {
            const frame = { ...await this.readFrame(row), source_frame_sha256: row.frame_hash };
            const size = jsonBytes(frame) + jsonBytes(row) + 2;
            if (bytes + size > 33554432) {
                if (!frames.length)
                    throw Error("OBSERVATION_EXPORT_BYTES_BOUND");
                break;
            }
            bytes += size;
            frames.push(frame);
            records.push(row);
        }
        return { schema: "HARPOON_OBSERVATION_EXPORT_1", account_id: this.accountId,
            head: snapshot.descriptor.head, offset, next_offset: offset + frames.length,
            total_frames: snapshot.descriptor.total_frames, complete_export: offset === 0 && frames.length === rows.length,
            snapshot_id: snapshotId, snapshot_descriptor: snapshot.descriptor, chain_records: records,
            active_frames: snapshot.index.frames.length, archived_segments: snapshot.index.archives.length,
            stored_bytes: snapshot.index.committed_bytes, frames, liveApproved: false, execution_allowed: false,
            limitations: ["SAMPLED_QUOTES_ARE_NOT_EXECUTABLE_DEPTH", "OBSERVED_INPUTS_HAVE_NO_EXTERNAL_AUTHENTICATION",
                "NO_IMPUTED_LABELS_OR_FUNDED_WEALTH_PATHS", "SAMPLING_DOES_NOT_ESTABLISH_INTRABAR_ORDER"] };
    }
    async capture(input, observation) {
        if (!this.loaded)
            throw Error("OBSERVATION_LOAD_REQUIRED");
        if (this.writing)
            throw Error("OBSERVATION_CAPTURE_IN_PROGRESS");
        this.writing = true;
        this.lastAttempt = Date.now();
        try {
            if (!Number.isInteger(input.now) || input.now > Date.now() || input.config?.expected_account_id !== this.accountId ||
                observation.schema !== "HARPOON_RUNTIME_OBSERVATION_1" || Date.parse(observation.asof) !== input.now ||
                observation.execution_allowed !== false || observation.liveApproved !== false || observation.selected?.length !== 0 ||
                !Array.isArray(observation.observations) || !observation.rejected ||
                !["OBSERVATION_CAPTURED", "WAIT_FEATURE_DATA"].includes(observation.status))
                throw Error("OBSERVATION_CONTRACT");
            const requested = new Set((input.signals || []).map((s) => s.plugin + "|" + s.symbol));
            const covered = new Set();
            for (const row of observation.observations) {
                if (!requested.has(row.id) || covered.has(row.id) || !Array.isArray(row.features) || row.features.length !== 8 ||
                    !row.features.every((n) => typeof n === "number" && Number.isFinite(n)) ||
                    !Number.isFinite(Date.parse(row.known_at)) || Date.parse(row.known_at) > input.now || Date.parse(row.asof) !== input.now)
                    throw Error("OBSERVATION_FEATURE_CONTRACT");
                covered.add(row.id);
            }
            for (const id of Object.keys(observation.rejected)) {
                if (!requested.has(id) || covered.has(id) || typeof observation.rejected[id] !== "string")
                    throw Error("OBSERVATION_REJECTION_CONTRACT");
                covered.add(id);
            }
            if (requested.size !== (input.signals || []).length || covered.size !== requested.size)
                throw Error("OBSERVATION_COVERAGE_CONTRACT");
            const last = this.index.frames.at(-1);
            if (last && input.now <= last.at)
                throw Error("OBSERVATION_NON_INCREASING_CLOCK");
            const rotate = this.index.frames.length >= this.maxFrames;
            if (rotate && this.index.archives.length >= this.maxArchives)
                throw Error("OBSERVATION_ARCHIVE_REQUIRED:SEGMENT_BUDGET_EXHAUSTED");
            const payload = { schema: "HARPOON_PROSPECTIVE_FRAME_1", account_id: this.accountId,
                data_origin: "RUNTIME_OBSERVATION_UNVERIFIED", external_authenticity_verified: false,
                runtime_input: input, observation, session_context: (0, sessions_1.sessionContext)(input.now, input.market.calendar || []),
                sampled_execution_depth: null, policy_parity_verified: false, financial_acceptance_allowed: false };
            const bytes = Buffer.from(JSON.stringify(payload));
            if (bytes.length > this.maxFrameBytes)
                throw Error("OBSERVATION_FRAME_BYTES_BOUND");
            const frameHash = hash(bytes), frameKey = this.key + "-frame-" + frameHash;
            const packed = { schema: "HARPOON_COMPRESSED_FRAME_1", encoding: "gzip+base64", sha256: frameHash,
                uncompressed_bytes: bytes.length, data: (0, node_zlib_1.gzipSync)(bytes, { level: 6 }).toString("base64") };
            let packedBytes = jsonBytes(packed);
            const writes = [];
            let archives = [...this.index.archives], archiveBytes = 0;
            if (rotate) {
                const segment = { schema: "HARPOON_OBSERVATION_SEGMENT_1", account_id: this.accountId,
                    configuration_hash: this.index.configuration_hash, ordinal: archives.length + 1,
                    frames: this.index.frames };
                const seal = (0, ultimate_contracts_1.digest)(segment), value = { ...segment, integrity_hash: seal }, key = this.key + "-archive-" + seal;
                archiveBytes = jsonBytes(value);
                const reference = { ordinal: segment.ordinal, segment_key: key, segment_hash: seal,
                    first_sequence: this.index.frames[0].sequence, last_sequence: last.sequence,
                    previous: this.index.frames[0].previous, head: last.chain_hash, last_at: last.at,
                    stored_bytes: archiveBytes };
                const priorArchive = await this.store.get(key);
                if (priorArchive)
                    await this.readArchive(reference);
                else
                    writes.push({ key, value, bytes: archiveBytes });
                archives = [...archives, reference];
            }
            const prior = await this.store.get(frameKey);
            if (prior) {
                await this.readFrame({ frame_key: frameKey, frame_hash: frameHash, at: input.now });
                packedBytes = jsonBytes(prior);
            }
            else
                writes.push({ key: frameKey, value: packed, bytes: packedBytes });
            const reservations = writes.map(({ key, bytes }) => ({ key, bytes }));
            const expectedCommitted = this.index.committed_bytes + packedBytes + archiveBytes;
            const gap = expectedCommitted - this.budget.charged_bytes - reservations.reduce((n, p) => n + p.bytes, 0);
            if (gap > 0)
                reservations.push({ key: "ADOPT_RETAINED_BYTES:" + frameHash, bytes: gap });
            await this.reserve(reservations);
            if (expectedCommitted > this.budget.charged_bytes)
                throw Error("OBSERVATION_STORAGE_RESERVATION_INCOMPLETE");
            for (const write of writes)
                await this.store.put(write.key, write.value);
            const record = { sequence: this.index.total_frames + 1, at: input.now, frame_hash: frameHash,
                frame_key: frameKey, previous: this.index.head, stored_bytes: packedBytes };
            const linked = { ...record, chain_hash: (0, ultimate_contracts_1.digest)(record) };
            const summary = { at: input.now, accepted: observation.observations.length,
                rejected: observation.rejected, requested: requested.size, coverage: input.observation_coverage || null,
                phase: payload.session_context.phase, input_bytes: bytes.length, stored_bytes: Buffer.byteLength(packed.data) };
            const next = { ...this.index, frames: [...(rotate ? [] : this.index.frames), linked], archives,
                total_frames: this.index.total_frames + 1,
                committed_bytes: expectedCommitted,
                head: linked.chain_hash, last_summary: summary };
            await this.store.put(this.key, { ...next, integrity_hash: (0, ultimate_contracts_1.digest)(next) });
            this.index = next;
            this.error = null;
            this.status = observation.status;
            return this.view();
        }
        catch (error) {
            this.fail(error);
            throw error;
        }
        finally {
            this.writing = false;
        }
    }
    async readFrame(row) {
        const packed = await this.store.get(row.frame_key);
        if (!packed || packed.schema !== "HARPOON_COMPRESSED_FRAME_1" || packed.encoding !== "gzip+base64" ||
            packed.sha256 !== row.frame_hash || !Number.isInteger(packed.uncompressed_bytes) ||
            packed.uncompressed_bytes > this.maxFrameBytes || typeof packed.data !== "string" ||
            packed.data.length > this.maxFrameBytes * 2)
            throw Error("OBSERVATION_FRAME_INTEGRITY");
        if (row.stored_bytes !== undefined && row.stored_bytes !== jsonBytes(packed))
            throw Error("OBSERVATION_FRAME_STORED_BYTES_MISMATCH");
        const bytes = (0, node_zlib_1.gunzipSync)(Buffer.from(packed.data, "base64"), { maxOutputLength: this.maxFrameBytes });
        if (bytes.length !== packed.uncompressed_bytes || hash(bytes) !== row.frame_hash)
            throw Error("OBSERVATION_FRAME_HASH_MISMATCH");
        const payload = JSON.parse(bytes.toString("utf8"));
        if (payload.account_id !== this.accountId || payload.runtime_input?.now !== row.at ||
            payload.schema !== "HARPOON_PROSPECTIVE_FRAME_1")
            throw Error("OBSERVATION_FRAME_BINDING");
        return payload;
    }
    async exportFrames(offset = 0, limit = 100) {
        boundedInt(offset, 0, 0, this.maxFrames * (this.maxArchives + 1), "OFFSET");
        boundedInt(limit, 100, 1, 100, "EXPORT_LIMIT");
        const rows = await this.validatedRows(), chosen = rows.slice(offset, offset + limit), frames = [];
        let bytes = 0;
        for (const row of chosen) {
            const frame = await this.readFrame(row);
            bytes += Buffer.byteLength(JSON.stringify(frame));
            if (bytes > 33554432)
                throw Error("OBSERVATION_EXPORT_BYTES_BOUND");
            frames.push({ ...frame, source_frame_sha256: row.frame_hash });
        }
        return { schema: "HARPOON_OBSERVATION_EXPORT_1", account_id: this.accountId, head: this.index.head,
            offset, next_offset: offset + frames.length, total_frames: this.index.total_frames,
            active_frames: this.index.frames.length, archived_segments: this.index.archives.length,
            stored_bytes: this.budget.charged_bytes,
            complete_export: offset === 0 && frames.length === this.index.total_frames,
            frames, liveApproved: false, execution_allowed: false,
            limitations: ["SAMPLED_QUOTES_ARE_NOT_EXECUTABLE_DEPTH", "OBSERVED_INPUTS_HAVE_NO_EXTERNAL_AUTHENTICATION",
                "NO_IMPUTED_LABELS_OR_FUNDED_WEALTH_PATHS", "SAMPLING_DOES_NOT_ESTABLISH_INTRABAR_ORDER"] };
    }
    view(now = Date.now()) {
        const last = this.index.frames.at(-1), age = last ? now - last.at : null;
        return { schema: "HARPOON_OBSERVATION_STATUS_1", status: this.status === "ERROR" ? "ERROR" :
                age !== null && (age < 0 || age > this.maxAgeMs) ? "STALE" : this.status,
            persisted: !!last && this.status !== "ERROR", lastAttempt: this.lastAttempt,
            lastSuccess: last?.at || null, ageMs: age, error: this.error, frames: this.index.total_frames,
            active_frames: this.index.frames.length, archived_segments: this.index.archives.length,
            stored_bytes: this.budget.charged_bytes, committed_bytes: this.index.committed_bytes,
            export_snapshot_metadata_bytes: this.exportBytes, retained_export_snapshots: this.exportRegistry.snapshots.length,
            export_snapshot_metadata_basis: "CONSERVATIVE_RESERVED_BYTES_UNTIL_ACK_OR_VERIFIED_RELOAD",
            total_reserved_bytes: this.budget.charged_bytes + this.exportBytes,
            storage_budget_basis: "CONSERVATIVE_RESERVED_IMMUTABLE_JSON_BYTES_INCLUDING_ORPHANS;BOUNDED_MUTABLE_INDEX_AND_BUDGET_METADATA_EXCLUDED",
            head: this.index.head, maxFrames: this.maxFrames, maxArchives: this.maxArchives,
            maxStoredBytes: this.maxStoredBytes, intervalMs: this.intervalMs,
            cursor: this.index.total_frames * this.maxSymbolsPerCapture, latest: this.index.last_summary,
            complete_opportunity_paths: false, financial_acceptance_allowed: false };
    }
}
exports.QuantObservationJournal = QuantObservationJournal;
