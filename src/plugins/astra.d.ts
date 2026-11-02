/** ASTRA 6: pure strategy. No credentials, network, order authority or model calls. */
declare namespace HAstra {
    const VERSION = "1.0.0";
    const FAMILY = "astra_second_wave";
    interface Params {
        impulseMinutes: number;
        pauseMinutes: number;
        minHistoryDays: number;
        impulseZ: number;
        minRvol: number;
        minRetained: number;
        minRelativeBps: number;
        minFlowImbalance: number;
        minClassifiedFraction: number;
        minFlowTrades: number;
        maxSpreadBps: number;
        maxChaseAtr: number;
        costMultiple: number;
        tpR: number;
        partialFraction: number;
        trailAtr: number;
        lockFraction: number;
        stagnationMinutes: number;
        holdHours: number;
        optionsRequired: boolean;
        maxIvRatio: number;
        maxPutSkew: number;
    }
    const defaults: Params;
    function validate(raw: unknown): Params;
    interface Bar {
        t: number;
        available: number;
        day: string;
        minute: number;
        o: number;
        h: number;
        l: number;
        c: number;
        v: number;
    }
    interface Flow {
        minute: number;
        buy: number;
        sell: number;
        unknown: number;
        trades: number;
        covered: boolean;
    }
    interface Quote {
        at: number;
        received: number;
        bid: number;
        ask: number;
    }
    interface Options {
        valid?: boolean;
        underlying?: string;
        feed?: string;
        asof?: number;
        quote_at?: number | null;
        proxy?: boolean;
        iv_atm?: number | null;
        iv_rv?: number | null;
        skew25?: number | null;
        term_slope?: number | null;
        expected_range?: number | null;
        expiry_at?: number | null;
    }
    interface Snapshot {
        symbol: string;
        at: number;
        source: 'ALPACA_OBSERVED' | 'RECORDED' | 'SYNTHETIC';
        feed: string;
        sessionOpen: number;
        bars: Bar[];
        market: Bar[];
        sector: Bar[];
        sectorSymbol: string | null;
        quote: Quote;
        flows: Flow[];
        slippageBps: number;
        options: Options | null;
    }
    interface Signal {
        version: string;
        asof: number;
        source: Snapshot['source'];
        ready: boolean;
        reasons: string[];
        metrics: Record<string, number | null>;
        impulseId: string;
        trigger: number | null;
        stop: number | null;
        options: Options | null;
    }
    function validQuote(q: Quote, now: number): boolean;
    function evaluate(snapshot: Snapshot, p: Params): Signal;
    function levels(row: {
        ask: number;
        bid: number;
        astra?: Signal;
    }, slippage: number, p: Params): {
        trigger: number;
        limit: number;
        stop: number;
        risk_unit: number;
        tp1: number;
        tp2: number;
        trail_distance: number;
    };
    function entryReasons(row: {
        ask: number;
        bid: number;
        astra?: Signal;
    }, now: number, p: Params): string[];
    interface ExitState {
        entry: number;
        peak: number;
        peakAt: number;
        virtual_stop: number;
        risk_unit: number;
        atr: number;
        tp1_filled: boolean;
        exit_cost_bps: number;
        stagnationMs?: number;
        closing?: string;
        astraState?: {
            minute: number;
            weak: number;
        };
        astraLatest?: Signal;
    }
    function exit(c: ExitState, bid: number, now: number, p: Params): void;
    function profile(p: Params): {
        name: string;
        hypothesis: string;
        family: string;
        min_rvol: number;
        momentum_bps: number;
        tp1_r: number;
        tp2_r: number;
        trail_atr: number;
        lock_fraction: number;
        tp1_fraction: number;
        tp2_fraction: number;
        hold_hours: number;
        reentry: boolean;
        stagnation_minutes: number;
        progress_r: number;
        selection_filter: string;
        trailing_mode: string;
        exit_layout: string;
        selective: boolean;
        prediction_floor: number;
        astra: Params;
    };
    function manifests(): {
        api: string;
        id: string;
        version: string;
        name: string;
        book: "equity" | "etf";
        family: string;
        binding: "fixed";
        params: {
            optionsRequired: boolean;
            impulseMinutes: number;
            pauseMinutes: number;
            minHistoryDays: number;
            impulseZ: number;
            minRvol: number;
            minRetained: number;
            minRelativeBps: number;
            minFlowImbalance: number;
            minClassifiedFraction: number;
            minFlowTrades: number;
            maxSpreadBps: number;
            maxChaseAtr: number;
            costMultiple: number;
            tpR: number;
            partialFraction: number;
            trailAtr: number;
            lockFraction: number;
            stagnationMinutes: number;
            holdHours: number;
            maxIvRatio: number;
            maxPutSkew: number;
        };
    }[];
    /** Bounded quote/trade classifier. Only observed stream data; no reconstructed buyer identity. */
    class Tape {
        quotes: Map<string, Quote[]>;
        buckets: Map<string, Map<number, Flow>>;
        seen: Map<string, number>;
        started: Map<string, number>;
        reset(): void;
        quote(symbol: string, q: Quote): void;
        trade(r: {
            S: string;
            t: string;
            p: number;
            s: number;
            i?: number | string;
            x?: string;
            c?: string[];
        }, received: number): void;
        flow(symbol: string): {
            minute: number;
            buy: number;
            sell: number;
            unknown: number;
            trades: number;
            covered: boolean;
        }[];
    }
}
