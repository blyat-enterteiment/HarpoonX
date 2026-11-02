"use strict";
// Real local SQLite transport with synthetic values and deliberate process/ACK faults.
// No network, broker, model fit or financial experiment.
const test = require("node:test"), assert = require("node:assert/strict");
const fs = require("node:fs"), os = require("node:os"), path = require("node:path");
const { DurableStore } = require("../runtime/store30.cjs");
const temporary = () => fs.mkdtempSync(path.join(os.tmpdir(), "hx-store-deadline-"));
const posix = {skip: process.platform === "win32" ? "POSIX process suspension required" : false};

async function fixture(action) {
  const dir = temporary(), stores = [];
  const create = (options) => { const s = new DurableStore(path.join(dir, "state.sqlite"), options); stores.push(s); return s; };
  try { await action(create, dir); }
  finally {
    for (const store of stores.reverse()) await store.close();
    fs.rmSync(dir, {recursive: true, force: true});
  }
}

test("storage validates its RPC deadline bounds", () => {
  for (const timeoutMs of [0, 49, 5001, 100.5, NaN])
    assert.throws(() => new DurableStore("unused.sqlite", {timeoutMs}), /50\.\.5000ms/);
});

test("startup is not READY until the real SQLite ping is acknowledged; concurrent opens share one child", async () => {
  await fixture(async create => {
    const s = create();
    assert.equal(s.health().status, "NEW");
    await assert.rejects(s.get("before-open"), /not ready/);
    const first = s.open(), second = s.open();
    assert.equal(first, second);
    assert.equal(s.health().status, "OPENING");
    assert.equal(s.ready, false);
    assert.equal(await first, s);
    const pid = s.process.pid;
    assert.equal(s.health().status, "READY");
    assert(s.health().lastSuccess > 0);
    assert.equal(s.seq, 1, "Only startup ping was sent");
    assert.equal(await s.open(), s);
    assert.equal(s.process.pid, pid);
    assert.equal(s.seq, 1);
    assert.equal(await s.get("missing"), null);
  });
});

test("spawn failure rejects startup and remains failed without automatic reopen", async () => {
  await fixture(async (create, dir) => {
    const previous = process.env.PYTHON;
    const s = create();
    let opening;
    try {
      process.env.PYTHON = path.join(dir, "missing-interpreter");
      opening = s.open();
    } finally {
      if (previous === undefined) delete process.env.PYTHON;
      else process.env.PYTHON = previous;
    }
    await assert.rejects(opening, /Storage/);
    assert.equal(s.health().status, "FAILED");
    assert.equal(s.health().uncertainWrite, false);
    await assert.rejects(s.open(), /Storage/);
    assert.equal(s.pending.size, 0);
  });
});

test("a suspended SQLite child reaches a deadline, releases pending RPCs and never retries", posix, async () => {
  await fixture(async create => {
    const s = await create().open();
    // Shorten only this fault fixture after the real startup handshake.
    s.timeoutMs = 150;
    assert(s.process.kill("SIGSTOP"));
    const started = performance.now(), before = s.seq;
    await assert.rejects(s.put("unconfirmed", 1), /deadline/);
    assert(performance.now() - started < 2000);
    assert.equal(s.seq, before + 1);
    assert.equal(s.health().status, "FAILED");
    assert.equal(s.health().uncertainWrite, true);
    assert.equal(s.pending.size, 0);
    await assert.rejects(s.get("unconfirmed"), /deadline/);
    await assert.rejects(s.open(), /deadline/);
    assert.equal(s.seq, before + 1);
  });
});

test("a committed CAS with a lost ACK is uncertain and atomic never replays it", async () => {
  await fixture(async create => {
    const s = await create().open();
    s.timeoutMs = 250;
    const commands = new Map(), originalWrite = s.process.stdin.write.bind(s.process.stdin);
    s.process.stdin.write = (chunk, ...args) => {
      const command = JSON.parse(String(chunk));
      commands.set(command.id, command.op);
      return originalWrite(chunk, ...args);
    };
    const handlers = s.reader.listeners("line");
    s.reader.removeAllListeners("line");
    let acknowledgedCommitDropped = false;
    s.reader.on("line", line => {
      const response = JSON.parse(line);
      if (commands.get(response.id) === "cas") {
        assert.equal(response.result, true, "SQLite committed before its response was deliberately dropped");
        acknowledgedCommitDropped = true;
        return;
      }
      for (const handler of handlers) handler.call(s.reader, line);
    });
    await assert.rejects(s.atomic("counter", value => Number(value || 0) + 1), /deadline/);
    assert.equal(acknowledgedCommitDropped, true);
    assert.equal([...commands.values()].filter(op => op === "cas").length, 1);
    assert.equal(s.health().uncertainWrite, true);
    const sent = s.seq;
    await assert.rejects(s.get("counter"), /deadline/);
    assert.equal(s.seq, sent);
    await s.close();
    // A deliberately new connection reads the committed value for reconciliation.
    const observer = await create().open();
    assert.equal(await observer.get("counter"), 1);
    assert.equal([...commands.values()].filter(op => op === "cas").length, 1);
  });
});

test("incomplete, null, false and contradictory mutation ACKs cannot acknowledge a durable commit", async () => {
  for (const body of [{}, {result: null}, {result: false}, {error: ""}, {result: true, error: "contradictory"}]) {
    await fixture(async create => {
      const s = await create().open(), handlers = s.reader.listeners("line");
      s.reader.removeAllListeners("line");
      s.reader.on("line", line => {
        const response = JSON.parse(line);
        for (const handler of handlers) handler.call(s.reader, JSON.stringify({id: response.id, ...body}));
      });
      await assert.rejects(s.put("invalid-ack", 1), /response invalid/);
      assert.equal(s.health().status, "FAILED");
      assert.equal(s.health().uncertainWrite, true);
      assert.equal(s.pending.size, 0);
      await assert.rejects(s.open(), /response invalid/);
    });
  }
});

test("a valid ACK delivered after the monotonic deadline is rejected before the overdue timer can run", async () => {
  await fixture(async create => {
    const s = await create().open(), handlers = s.reader.listeners("line");
    s.timeoutMs = 250;
    s.reader.removeAllListeners("line");
    let ackProcessed = false, timerCallbackRan = false;
    const timerProbe = setTimeout(() => { timerCallbackRan = true; }, s.timeoutMs);
    s.reader.on("line", line => {
      const response = JSON.parse(line), pending = s.pending.get(response.id);
      assert(pending, "The actual SQLite ACK reached the event loop while its RPC was still pending");
      assert.equal(response.result, true);
      // Deliberately block this one callback past expiry: I/O runs before overdue timers.
      while (performance.now() < pending.deadlineAt + 10) { /* controlled fault injection */ }
      assert.equal(timerCallbackRan, false);
      for (const handler of handlers) handler.call(s.reader, line);
      assert.equal(s.health().status, "FAILED", "The ACK handler itself must enforce expiry");
      assert.equal(timerCallbackRan, false);
      ackProcessed = true;
    });
    try {
      await assert.rejects(s.put("late-ack", 1), /deadline/);
      assert.equal(ackProcessed, true);
      assert.equal(s.health().uncertainWrite, true);
      assert.equal(s.pending.size, 0);
    } finally { clearTimeout(timerProbe); }
  });
});

test("backpressure caps the pending RPC count and a read-only backlog does not invent uncertain writes", posix, async () => {
  await fixture(async create => {
    const s = await create().open();
    assert(s.process.kill("SIGSTOP"));
    const responses = [];
    for (let i = 0; i < s.health().maxPending; i++)
      responses.push(s.get("held-read").then(() => null, error => error.message));
    assert.equal(s.pending.size, 2048);
    await assert.rejects(s.get("overflow"), /backlog/);
    assert((await Promise.all(responses)).every(message => /backlog/.test(message)));
    assert.equal(s.pending.size, 0);
    assert.equal(s.health().status, "FAILED");
    assert.equal(s.health().uncertainWrite, false);
  });
});

test("child death rejects a pending mutation and latches its uncertain status", async () => {
  await fixture(async create => {
    const s = await create().open();
    const outcome = s.put("possibly-committed", 1).then(() => null, error => error);
    assert(s.process.kill("SIGKILL"));
    assert.match((await outcome).message, /Storage/);
    assert.equal(s.health().status, "FAILED");
    assert.equal(s.health().uncertainWrite, true);
    assert.equal(s.pending.size, 0);
  });
});

test("close with an unacknowledged mutation preserves uncertainty and terminates a stopped child within its bound", posix, async () => {
  await fixture(async create => {
    const s = await create().open();
    s.timeoutMs = 150;
    assert(s.process.kill("SIGSTOP"));
    const outcome = s.put("closing-mutation", 1).then(() => null, error => error.message);
    const started = performance.now(), closing = s.close();
    assert.equal(s.close(), closing);
    assert.equal(s.health().uncertainWrite, true);
    assert.match(await outcome, /before acknowledgement/);
    await closing;
    assert(performance.now() - started < 2000);
    assert.equal(s.health().status, "CLOSED");
    assert.equal(s.health().uncertainWrite, true);
    assert.equal(s.pending.size, 0);
    await assert.rejects(s.open(), /closed/);
  });
});

test("closing an unopened or already closed store is safe and never advertises READY", async () => {
  await fixture(async create => {
    const s = create();
    await s.close();
    await s.close();
    assert.equal(s.health().status, "CLOSED");
    assert.equal(s.health().uncertainWrite, false);
    await assert.rejects(s.get("no-child"), /closed/);
    await assert.rejects(s.open(), /closed/);
  });
});

test("batch, get, paginated scan, scanAfter, CAS and cross-process leases retain their existing contracts", async () => {
  await fixture(async create => {
    const a = await create().open(), b = await create().open();
    const entries = Array.from({length: 601}, (_, i) => ["rows:" + String(i).padStart(12, "0"), {index: i, label: "señal"}]);
    assert.equal(await a.batch(entries), true);
    const all = await b.scan("rows:");
    assert.equal(all.length, 601);
    assert.deepEqual(all[600], {index: 600, label: "señal"});
    assert.deepEqual(await a.scanAfter("rows:", 598, row => row.index), [599, 600]);
    await assert.rejects(a.scan("rows:", 600), /scan limit/);
    assert.equal(a.health().status, "READY");
    assert.equal(await a.atomic("count", value => Number(value || 0) + 1), 1);
    assert.equal(await b.rpc({op: "cas", key: "count", expected: 0, value: 9}), false);
    assert.equal(await a.get("count"), 1);
    assert.equal(await a.lease("shared"), true);
    assert.equal(await b.lease("shared"), false);
    assert.equal(await a.lease("shared", true), true);
    assert.equal(await b.lease("shared"), true);
    assert.equal(await b.lease("shared", true), true);
  });
});

test("16 MiB values still round-trip; deadline hardening does not impose a smaller IPC byte limit", async () => {
  await fixture(async create => {
    const s = await create().open();
    const value = "a".repeat(16 * 1024 * 1024);
    assert.equal(await s.put("large-observation-metadata", value), true);
    assert.equal(await s.get("large-observation-metadata"), value);
    assert.equal(s.health().uncertainWrite, false);
  });
});

test("local serialization errors and acknowledged operation errors do not become uncertain transport writes", async () => {
  await fixture(async create => {
    const s = await create().open(), cyclic = {};
    cyclic.self = cyclic;
    await assert.rejects(s.put("invalid", cyclic), /circular/i);
    assert.equal(s.pending.size, 0);
    assert.equal(s.health().uncertainWrite, false);
    await assert.rejects(s.rpc({op: "unsupported"}), /Unsupported storage/);
    assert.equal(s.health().status, "READY");
    assert.equal(s.health().uncertainWrite, false);
    assert.equal(await s.get("invalid"), null);
  });
});
