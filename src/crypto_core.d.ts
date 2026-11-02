declare namespace HC19 {
    const VERSION = "19.0.0", DAY = 86400000, SYMBOLS: readonly ["BTC/USD", "ETH/USD"];
    type SymbolName = typeof SYMBOLS[number];
    interface Bar {
        t: number;
        o: number;
        h: number;
        l: number;
        c: number;
        v: number;
    }
    interface Config {
        entry_days: number;
        exit_days: number;
        atr_days: number;
        atr_multiple: number;
        risk_fraction: number;
        asset_cap: number;
        total_cap: number;
        fee_bps: number;
        slippage_bps: number;
        max_spread_bps: number;
        capital: number;
        capital_limit: number;
        hold_hours: number;
        drawdown_limit: number;
    }
    const defaults: Config;
    interface Signal {
        at: number;
        available_at: number;
        close: number;
        upper: number;
        lower: number;
        atr: number;
        volatility: number;
        enter: boolean;
        exit: boolean;
        stop: number;
    }
    interface Metrics {
        net: number;
        return_pct: number;
        cagr: number;
        sharpe: number | null;
        sortino: number | null;
        drawdown: number;
        trades: number;
        win_rate: number | null;
        profit_factor: number | null;
        fees: number;
        turnover: number;
        days: number;
    }
    interface Trade {
        symbol: string;
        opened: number;
        closed: number;
        entry: number;
        exit: number;
        qty: number;
        net: number;
        reason: string;
    }
    interface Replay {
        metrics: Metrics;
        returns: number[];
        nav: number[];
        days: number[];
        trades: Trade[];
        config: Config;
        basis: string;
    }
    type Bars = Record<SymbolName, Bar[]>;
    function validate(c: Config): Config;
    function normalize(raw: unknown, cutoff?: number): Bar[];
    function dataset(input: unknown, cutoff?: number): Bars;
    function signal(b: Bar[], c: Config, index?: number): Signal;
    function floorQty(q: number, step: number): number;
    function quantity(equity: number, cash: number, used: number, price: number, atr: number, c: Config, step: number): number;
    function metrics(returns: number[], trades: Trade[], initial: number, fees?: number, turnover?: number): Metrics;
    function replay(data: Bars, cfg: Config, start?: number, end?: number, costMultiplier?: number, passive?: boolean): Replay;
    function variants(base: Config): {
        name: string;
        config: Config;
    }[];
    function walkForward(data: Bars, base: Config): {
        schema: string;
        version: string;
        metric_series23: {
            dates: string[];
            candidate: number[];
            baseline: number[];
            benchmark: number[];
            annualization: number;
            boundary: string;
            costs_confirmed: boolean;
            capital: number;
            external_candidate_usd: number;
            external_baseline_usd: number;
            cost_basis: string;
            risk_hash: string;
            policy_before: string;
            policy_after: string;
        };
        source: string;
        status: string;
        gates: {
            oos_positive: boolean;
            holdout_positive: boolean;
            cost_stress: boolean;
            drawdown: boolean;
            trade_count: boolean;
            sharpe_vs_passive: boolean;
            fold_stability: boolean;
        };
        selected: string;
        config: Config;
        attempts: number;
        folds: {
            start: number;
            end: number;
            selected: string;
            training: Metrics;
            test: Metrics;
        }[];
        oos: Metrics;
        stress: Metrics;
        benchmark: Metrics;
        holdout: Metrics;
        holdout_stress: Metrics;
        holdout_benchmark: Metrics;
        holdout_start: number;
        through: number;
        changes_orders: boolean;
        protocol: {
            train_days: number;
            test_days: number;
            gap_days: number;
            final_days: number;
            warmup_days: number;
            flat_boundaries: boolean;
            annualization: number;
        };
        basis: string;
    };
}
