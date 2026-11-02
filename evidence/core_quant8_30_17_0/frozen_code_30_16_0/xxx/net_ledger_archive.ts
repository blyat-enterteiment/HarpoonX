import { createHash } from "node:crypto";
import { Json, Store } from "./types";

/** Immutable accounting segments. The control record is committed by the ledger
 * only after an immutable segment and its durable quota reservation exist.
 * Reservations survive unsuccessful control commits; failed writes never buy
 * unlimited storage through retries. Bytes are serialized payload bytes, not
 * total SQLite/WAL/filesystem consumption. No segment is silently deleted. */
export class NetArchiveError extends Error {
  constructor(public readonly code: string, public readonly detail: Json = {}) { super(code); }
}
function fail(code: string, detail: Json = {}): never { throw new NetArchiveError(code, detail); }
function obj(value: unknown, code: string): Json {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail(code);
  return value as Json;
}
function integer(value: unknown, minimum: number, maximum: number): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < minimum || value > maximum) fail("LEDGER_ARCHIVE_CONFIG_INVALID");
  return value;
}
function idBloom(ids: string[], bytes?: number): string {
  const bits = Buffer.alloc(bytes ?? Math.max(32, Math.ceil(ids.length * 2)));
  for (const id of ids) {
    const hash = createHash("sha256").update(id).digest();
    for (let i = 0; i < 4; i++) {
      const bit = hash.readUInt32BE(i * 4) % (bits.length * 8);
      bits[Math.floor(bit / 8)]! |= 1 << (bit % 8);
    }
  }
  return bits.toString("base64");
}
function mightContain(bloom: string, id: string): boolean {
  const bits = Buffer.from(bloom, "base64"), selected = Buffer.from(idBloom([id], bits.length), "base64");
  return selected.every((value, i) => (value & bits[i]!) === value);
}

export class NetLedgerArchive {
  readonly enabled: boolean;
  readonly maxSegments: number;
  readonly maxStoredBytes: number;
  readonly activityOverlapMs: number;
  readonly policyHash: string;
  private budget: Json | null = null;
  private readonly cache = new Map<string, Json>();

  constructor(private readonly store: Store, private readonly key: string, private readonly accountId: string,
    private readonly digest: (value: unknown) => string, config: Json = {}) {
    if (config.enabled !== undefined && typeof config.enabled !== "boolean") fail("LEDGER_ARCHIVE_CONFIG_INVALID");
    this.enabled = config.enabled === true;
    this.maxSegments = integer(config.maxSegments ?? 16, 0, 256);
    this.maxStoredBytes = integer(config.maxStoredBytes ?? 512 * 1024 * 1024, 1024, 2 * 1024 * 1024 * 1024);
    this.activityOverlapMs = integer(config.activityOverlapMs ?? 60000, 1, 86400000);
    this.policyHash = digest({ enabled: this.enabled, maxSegments: this.maxSegments,
      maxStoredBytes: this.maxStoredBytes, activityOverlapMs: this.activityOverlapMs });
  }

  empty(): Json {
    return { schema: "HARPOON_NET_ARCHIVE_INDEX_1", accountId: this.accountId, policyHash: this.policyHash,
      head: "GENESIS", segments: [], observationCount: 0, activityCount: 0, costCount: 0, boundary: null };
  }

  private seal(row: Json): Json {
    const copy = { ...row }; delete copy.integrity;
    return { ...copy, integrity: this.digest(copy) };
  }

  private validHash(row: Json): boolean {
    return this.seal(row).integrity === row.integrity;
  }

  async load(index: Json | undefined, expectedLedgerPolicy?: string, expectedBaselineHash?: string): Promise<void> {
    if (!this.enabled) {
      if (index?.segments?.length) fail("LEDGER_ARCHIVE_CONFIGURATION_REQUIRED");
      return;
    }
    const saved: unknown = await this.store.get(this.key + "-archive-budget");
    if (saved !== null && saved !== undefined) {
      const b = obj(saved, "LEDGER_ARCHIVE_BUDGET_INVALID");
      if (b.schema !== "HARPOON_NET_ARCHIVE_BUDGET_1" || b.accountId !== this.accountId ||
          b.policyHash !== this.policyHash || !this.validHash(b) || !Array.isArray(b.reservations)) fail("LEDGER_ARCHIVE_BUDGET_INTEGRITY");
      let bytes = 0; const keys = new Set<string>();
      for (const r of b.reservations) {
        if (typeof r.key !== "string" || !r.key.startsWith(this.key + "-archive-") || keys.has(r.key) ||
            !Number.isSafeInteger(r.bytes) || r.bytes <= 0 || !/^[0-9a-f]{64}$/.test(r.hash)) fail("LEDGER_ARCHIVE_BUDGET_INTEGRITY");
        bytes += r.bytes; keys.add(r.key);
      }
      if (bytes !== b.reservedBytes || bytes > this.maxStoredBytes || keys.size > this.maxSegments) fail("LEDGER_ARCHIVE_BUDGET_INTEGRITY");
      this.budget = structuredClone(b);
    } else this.budget = this.seal({ schema: "HARPOON_NET_ARCHIVE_BUDGET_1", accountId: this.accountId,
      policyHash: this.policyHash, reservedBytes: 0, reservations: [] });
    if (index === undefined) return;
    this.validateIndex(index);
    let previous = "GENESIS", count = 0, activityCount = 0, costCount = 0;
    let boundary: Json | null = null;
    for (let i = 0; i < index.segments.length; i++) {
      const ref = index.segments[i], segment = await this.read(ref);
      if (expectedLedgerPolicy !== undefined && segment.ledgerPolicyHash !== expectedLedgerPolicy ||
          expectedBaselineHash !== undefined && segment.originalBaselineHash !== expectedBaselineHash) fail("LEDGER_ARCHIVE_LEDGER_BINDING_MISMATCH");
      if (segment.sequence !== i + 1 || segment.previous !== previous ||
          (boundary && (segment.observations[0].at !== boundary.anchor.at ||
            segment.observations[0].sourceHash !== boundary.anchor.sourceHash))) fail("LEDGER_ARCHIVE_CHAIN_MISMATCH");
      count += segment.observations.length; activityCount += segment.activities.length;
      costCount += segment.externalCosts.length; previous = ref.hash; boundary = segment.boundary;
    }
    if (index.head !== previous || index.observationCount !== count || index.activityCount !== activityCount ||
        index.costCount !== costCount || this.digest(index.boundary) !== this.digest(boundary)) fail("LEDGER_ARCHIVE_INDEX_TOTAL_MISMATCH");
  }

  private validateIndex(index: Json): void {
    if (index.schema !== "HARPOON_NET_ARCHIVE_INDEX_1" || index.accountId !== this.accountId ||
        index.policyHash !== this.policyHash || !Array.isArray(index.segments) || index.segments.length > this.maxSegments) fail("LEDGER_ARCHIVE_INDEX_INVALID");
  }

  async read(ref: Json): Promise<Json> {
    const value: unknown = await this.store.get(ref.key);
    if (value === null || value === undefined) fail("LEDGER_ARCHIVE_SEGMENT_MISSING");
    const row = obj(value, "LEDGER_ARCHIVE_SEGMENT_INVALID");
    const bytes = Buffer.byteLength(JSON.stringify(row));
    const reservation = this.budget?.reservations.find((r: Json) => r.key === ref.key);
    if (row.schema !== "HARPOON_NET_ARCHIVE_SEGMENT_1" || row.accountId !== this.accountId ||
        row.archivePolicyHash !== this.policyHash || !this.validHash(row) || row.integrity !== ref.hash ||
        bytes !== ref.bytes || !reservation || reservation.bytes !== bytes || reservation.hash !== ref.hash ||
        !Array.isArray(row.observations) || !row.observations.length || !Array.isArray(row.activities) || !Array.isArray(row.externalCosts) ||
        !row.boundary?.anchor || row.observations.length !== ref.observations || row.activities.length !== ref.activities ||
        row.externalCosts.length !== ref.costs || row.observations[0].at !== ref.from ||
        row.observations.at(-1).at !== ref.through || row.boundary.anchor.at !== ref.anchorAt ||
        idBloom(row.activities.map((a: Json) => a.id)) !== ref.activityBloom) fail("LEDGER_ARCHIVE_SEGMENT_INTEGRITY");
    let at = -Infinity;
    for (const o of row.observations) {
      if (!Number.isFinite(o.at) || o.at <= at || o.at >= row.boundary.anchor.at) fail("LEDGER_ARCHIVE_OBSERVATION_ORDER");
      at = o.at;
    }
    return row;
  }

  async append(index: Json | undefined, body: Json): Promise<Json> {
    if (!this.enabled) fail("LEDGER_ARCHIVE_DISABLED");
    const current = index ?? this.empty(); this.validateIndex(current);
    if (current.segments.length >= this.maxSegments) fail("LEDGER_ARCHIVE_SEGMENT_BUDGET_EXHAUSTED");
    if (this.budget === null) await this.load(index);
    const segment = this.seal({ ...body, schema: "HARPOON_NET_ARCHIVE_SEGMENT_1", accountId: this.accountId,
      archivePolicyHash: this.policyHash, sequence: current.segments.length + 1, previous: current.head });
    const bytes = Buffer.byteLength(JSON.stringify(segment));
    const key = this.key + "-archive-" + segment.integrity;
    let reservation = this.budget!.reservations.find((r: Json) => r.key === key);
    if (!reservation) {
      if (this.budget!.reservations.length >= this.maxSegments) fail("LEDGER_ARCHIVE_RESERVED_SEGMENT_BUDGET_EXHAUSTED");
      if (this.budget!.reservedBytes + bytes > this.maxStoredBytes) fail("LEDGER_ARCHIVE_BYTE_BUDGET_EXHAUSTED");
      const next = this.seal({ ...this.budget, reservedBytes: this.budget!.reservedBytes + bytes,
        reservations: [...this.budget!.reservations, { key, bytes, hash: segment.integrity }] });
      if (await this.store.put(this.key + "-archive-budget", next) === false) fail("LEDGER_ARCHIVE_BUDGET_PERSISTENCE_REJECTED");
      this.budget = next; reservation = { key, bytes, hash: segment.integrity };
    }
    if (reservation.bytes !== bytes || reservation.hash !== segment.integrity) fail("LEDGER_ARCHIVE_RESERVATION_MISMATCH");
    const existing: unknown = await this.store.get(key);
    if (existing !== null && existing !== undefined) {
      if (this.digest(existing) !== this.digest(segment)) fail("LEDGER_ARCHIVE_IMMUTABLE_COLLISION");
    } else if (await this.store.put(key, segment) === false) fail("LEDGER_ARCHIVE_SEGMENT_PERSISTENCE_REJECTED");
    const ref = { key, hash: segment.integrity, bytes, observations: segment.observations.length,
      activities: segment.activities.length, costs: segment.externalCosts.length,
      from: segment.observations[0].at, through: segment.observations.at(-1).at, anchorAt: segment.boundary.anchor.at,
      activityBloom: idBloom(segment.activities.map((a: Json) => a.id)) };
    // Read-back before referencing the immutable segment in the control record.
    await this.read(ref);
    return { ...current, segments: [...current.segments, ref], head: ref.hash,
      observationCount: current.observationCount + ref.observations,
      activityCount: current.activityCount + ref.activities, costCount: current.costCount + ref.costs,
      boundary: segment.boundary };
  }

  async findActivity(index: Json | undefined, id: string): Promise<Json | null> {
    if (!index) return null;
    for (const ref of index.segments) {
      if (!mightContain(ref.activityBloom, id)) continue;
      let segment = this.cache.get(ref.hash);
      if (!segment) {
        segment = await this.read(ref);
        if (this.cache.size >= 1) this.cache.delete(this.cache.keys().next().value!);
        this.cache.set(ref.hash, segment);
      }
      const found = segment.activities.find((a: Json) => a.id === id);
      if (found) return structuredClone(found);
    }
    return null;
  }

  summary(index: Json | undefined): Json {
    return { enabled: this.enabled, segments: index?.segments.length ?? 0,
      archivedObservations: index?.observationCount ?? 0, archivedActivities: index?.activityCount ?? 0,
      archivedCosts: index?.costCount ?? 0, head: index?.head ?? "GENESIS",
      reservedBytes: this.budget?.reservedBytes ?? 0, reservedSegments: this.budget?.reservations.length ?? 0,
      maxSegments: this.maxSegments, maxStoredBytes: this.maxStoredBytes, activeCacheSegments: 1,
      storageBasis: "SERIALIZED_ARCHIVE_PAYLOADS_PLUS_DURABLE_RESERVATIONS; SQLITE_AND_WAL_OVERHEAD_EXCLUDED",
      retainedHistoryDeleted: false, indefiniteRetention: false,
      fullHistoricalPerformanceRequiresMaterialization: (index?.segments.length ?? 0) > 0,
      economicHistorySealedComplete: index?.boundary?.economicHistoryComplete ?? null };
  }
}
