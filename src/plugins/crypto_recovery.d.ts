declare namespace HPRecovery {
    const API: "harpoon.strategy/1";
    const MINUTE = 60000, DAY = 86400000, BPS = 10000;
    type SymbolName = 'BTC/USD' | 'ETH/USD';
    type Family = 'trend_xix' | 'shock_recovery';
    type Source = 'SYNTHETIC' | 'RECORDED';
    interface Bar {
        startMs: number;
        availableMs: number;
        open: number;
        high: number;
        low: number;
        close: number;
        volume: number;
        tradeVwap: number;
        buyVolume: number;
        sellVolume: number;
    }
    interface Quote {
        atMs: number;
        bid: number;
        ask: number;
    }
    interface Depth {
        atMs: number;
        askUsdWithin25bps: number;
    }
    interface Snapshot {
        asofMs: number;
        symbol: SymbolName;
        venue: 'alpaca-us';
        source: Source;
        daily: readonly Bar[];
        intraday: readonly Bar[];
        quote: Quote;
        depth?: Depth;
    }
    interface Manifest {
        api: typeof API;
        id: string;
        version: '1.0.0';
        family: Family;
        symbols: readonly SymbolName[];
        params: Readonly<Record<string, number>>;
    }
    interface Costs {
        feePerSideBps: number;
        slippagePerSideBps: number;
    }
    interface Proposal {
        pluginId: string;
        revision: string;
        family: Family;
        symbol: SymbolName;
        source: Source;
        signalMs: number;
        expiresMs: number;
        entryCeiling: number;
        stop: number;
        target: number | null;
        holdMs: number | null;
        costBps: number;
        diagnostics: Readonly<Record<string, number>>;
    }
    interface Evaluation {
        proposal: Proposal | null;
        reason: string;
        diagnostics: Readonly<Record<string, number>>;
    }
    interface ExitPolicy {
        stop: number;
        target: number | null;
        deadlineMs: number | null;
    }
    function demand(ok: boolean, why: string): asserts ok;
    function finite(n: number): boolean;
    function mean(a: readonly number[]): number;
    function stdev(a: readonly number[]): number;
    function median(a: readonly number[]): number;
    function quoteValid(q: Quote, now: number, ttl: number): boolean;
    function spreadBps(q: Quote): number;
    function costBps(q: Quote, c: Costs): number;
    function closedBars(raw: readonly Bar[], frame: number, asof: number): Bar[];
    function canonical(m: Manifest): string;
    function defaultManifest(family: 'trend_xix' | 'shock_recovery', id?: "trend_xix" | "shock_recovery"): Manifest;
    function validateManifest(raw: unknown): Manifest;
    function legacySignal(s: Snapshot, m: Manifest): HC19.Signal;
    function evaluate(m: Manifest, s: Snapshot, costs: Costs): Evaluation;
}
