/** XXIII. Pure, daily, net-of-cost comparisons. No order or network authority. */
declare namespace HM23 {
    const VERSION = "23.0.0";
    type Source = 'SYNTHETIC' | 'HISTORICAL_REPLAY' | 'PAPER' | 'LIVE' | 'IMPORTED_UNVERIFIED';
    interface Trade {
        net: number;
        gross?: number;
        fees?: number;
        mfe?: number;
        captured?: number;
        hours?: number;
        slippage_bps?: number;
    }
    interface Series {
        source: Source;
        label: string;
        dates: string[];
        returns: number[];
        benchmark?: number[];
        annualization: 252 | 365;
        capital: number;
        risk_hash: string;
        cost_basis: string;
        external_costs_usd: number;
        costs_confirmed: boolean;
        rf_annual: number;
        mar_annual: number;
        trades?: Trade[];
        fees_usd?: number;
        turnover_usd?: number;
        policy_hash: string;
        basis: string;
        boundary: 'continuous' | 'reset_at_folds';
    }
    interface Metric {
        value: number | null;
        unit: 'ratio' | 'percent' | 'usd' | 'count' | 'hours' | 'bps';
        direction: 'higher' | 'lower' | 'neutral';
    }
    interface Summary {
        schema: string;
        source: Source;
        label: string;
        from: string;
        through: string;
        n: number;
        metrics: Record<string, Metric>;
        nav: number[];
        drawdowns: number[];
        warnings: string[];
        alpha_ci95: [number, number] | null;
    }
    function validate(s: Series): Series;
    function summarize(input: Series): Summary;
    function compare(baseline: Series, candidate: Series, attempts?: number, iterations?: number): {
        schema: string;
        baseline: Summary;
        candidate: Summary;
        delta: Record<string, {
            baseline: number | null;
            candidate: number | null;
            absolute: number | null;
            relative: number | null;
            improved: boolean | null;
            unit: string;
        }>;
        evidence: {
            method: string;
            block_days: number;
            replications: number;
            attempts: number;
            confidence: number;
            mean_daily_delta: number;
            lower_daily_delta: number | null;
            resolution_ok: boolean;
            positive: boolean;
        };
        policy_before: string;
        policy_after: string;
        profitability_verified: boolean;
        changes_orders: boolean;
    };
    function fromEquity(dates: string[], equity: number[], flows: number[], base: number): number[];
}
