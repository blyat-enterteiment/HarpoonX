import { performance } from "node:perf_hooks";
export interface Lane {
  name: string;
  interval: number;
  run: () => Promise<void>;
  running: boolean;
  lastStart: number;
  lastEnd: number;
  runs: number;
  failures: number;
  error: string;
  lastSuccess: number;
  durationMs: number | null;
  consecutiveFailures: number;
  reason: string;
  timer?: NodeJS.Timeout;
  job?: Promise<void>;
}
/** Independent fixed-delay lanes: one slow research request cannot queue or block another lane. */
export class Scheduler {
  lanes: Lane[] = [];
  stopping = false;
  add(name: string, interval: number, run: () => Promise<void>) {
    this.lanes.push({
      name,
      interval,
      run,
      running: false,
      lastStart: 0,
      lastEnd: 0,
      runs: 0,
      failures: 0,
      error: "",
      lastSuccess: 0,
      durationMs: null,
      consecutiveFailures: 0,
      reason: "Aún no ejecutado",
    });
  }
  async once(l: Lane) {
    if (this.stopping || l.running) return;
    const monotonicStart = performance.now();
    l.running = true;
    l.lastStart = Date.now();
    try {
      await l.run();
      l.runs++;
      l.lastSuccess = Date.now();
      l.consecutiveFailures = 0;
      l.reason = "Ejecución completada";
      l.error = "";
    } catch (e) {
      l.failures++;
      l.consecutiveFailures++;
      l.error = e instanceof Error ? e.message : String(e);
    } finally {
      l.lastEnd = Date.now();
      l.durationMs = performance.now() - monotonicStart;
      l.running = false;
    }
  }
  start() {
    for (const l of this.lanes) {
      const next = () => {
        if (this.stopping) return;
        l.job = this.once(l).finally(() => {
          if (!this.stopping) l.timer = setTimeout(next, l.interval);
        });
      };
      next();
    }
  }
  async stop() {
    this.stopping = true;
    for (const l of this.lanes) clearTimeout(l.timer);
    await Promise.allSettled(this.lanes.map((l) => l.job));
  }
  view() {
    const now = Date.now();
    return this.lanes.map((l) => ({
      ...Object.fromEntries(
        Object.entries(l).filter(
          ([key]) => !["run", "timer", "job"].includes(key),
        ),
      ),
      name: l.name,
      interval: l.interval,
      running: l.running,
      lastStart: l.lastStart,
      lastEnd: l.lastEnd,
      lastSuccess: l.lastSuccess,
      durationMs: l.durationMs,
      runs: l.runs,
      failures: l.failures,
      error: l.error,
      reason: l.reason,
      health:
        l.running && now - l.lastStart > Math.max(3000, l.interval * 3)
          ? "STALLED"
          : l.error
            ? "ERROR"
            : !l.lastSuccess
              ? "STARTING"
              : now - l.lastSuccess > Math.max(3000, l.interval * 3)
                ? "STALE"
                : l.running
                  ? "RUNNING"
                  : "ALIVE",
    }));
  }
}
/** Serialize broker authority; queued exits/reconciliation precede fresh entries. */
export class PriorityMutex {
  private busy = false;
  private queue: {
    priority: number;
    run: () => Promise<unknown>;
    resolve: (v: any) => void;
    reject: (e: unknown) => void;
  }[] = [];
  run<T>(priority: number, run: () => Promise<T>): Promise<T> {
    return new Promise((resolve, reject) => {
      this.queue.push({ priority, run, resolve, reject });
      this.queue.sort((a, b) => a.priority - b.priority);
      this.drain();
    });
  }
  private drain() {
    if (this.busy) return;
    const task = this.queue.shift();
    if (!task) return;
    this.busy = true;
    task
      .run()
      .then(task.resolve, task.reject)
      .finally(() => {
        this.busy = false;
        this.drain();
      });
  }
}
