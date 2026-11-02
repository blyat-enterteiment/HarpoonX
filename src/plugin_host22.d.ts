/** Generic, bounded daily-allocation research host. No strategy identifiers or broker authority. */
declare namespace H22 {
    type Expr = number | string | Expr[];
    interface Events {
        source: string;
        from: string;
        to: string;
        known_at: string;
        dates: string[];
    }
    interface Rule {
        weekday: number;
        nth: number;
        holiday: 'previous_session';
        source: string;
    }
    interface Plugin {
        schema: string;
        id: string;
        version: string;
        name: string;
        symbol: string;
        book: string;
        description: string;
        orders_enabled: false;
        permissions: string[];
        source: Record<string, unknown>;
        source_canonical: string;
        parameters: Record<string, number>;
        program: {
            start: number;
            burn_in: number;
            state: Record<string, number>;
            nodes: {
                id: string;
                expr: Expr;
            }[];
            update: Record<string, string>;
            outputs: Record<string, string>;
        };
        calendar_rules: Record<string, Rule>;
        event_sets: Record<string, Events>;
        notes: string[];
        sha256: string;
    }
    interface Data {
        schema: string;
        symbol: string;
        kind: 'historical' | 'synthetic';
        source: string;
        adjustment: 'all';
        asof: string;
        calendar: {
            source: string;
            from: string;
            to: string;
            sessions: {
                date: string;
                open: number;
                close: number;
            }[];
        };
        bars: {
            date: string;
            open: number;
            close: number;
        }[];
        event_sets?: Record<string, Events>;
    }
    interface Point {
        date: string;
        next_session: string;
        values: Record<string, number>;
        ready: boolean;
    }
    interface Costs {
        capital: number;
        cost_bps: number;
        financing_apr: number;
        fee_apr: number;
        benchmark_weight: number;
    }
    const VERSION = "22.0.0";
    function stable(v: unknown): string;
    function digest(s: string): Promise<string>;
    function validate(p: Plugin): Plugin;
    function unpack(raw: unknown): Promise<Plugin>;
    function validateData(d: Data, p: Plugin): Data;
    function signals(p: Plugin, d: Data): Point[];
    function backtest(p: Plugin, d: Data, c: Costs): {
        schema: string;
        plugin: {
            id: string;
            version: string;
            sha256: string;
        };
        data: {
            symbol: string;
            kind: "historical" | "synthetic";
            source: string;
            asof: string;
            calendar: string;
        };
        costs: Costs;
        strategy: {
            returns: number[];
            dates: string[];
            total_costs: number;
            realized_net_sales: number;
            net_realized_after_carry: number;
            unrealized: number;
            remaining_exposure: number;
            trades: unknown[];
            sessions: number;
            net_return: number;
            nav: number | undefined;
            sharpe: number | null;
            sortino: number | null;
            max_drawdown: number;
        };
        benchmark: {
            returns: number[];
            dates: string[];
            total_costs: number;
            realized_net_sales: number;
            net_realized_after_carry: number;
            unrealized: number;
            remaining_exposure: number;
            trades: unknown[];
            sessions: number;
            net_return: number;
            nav: number | undefined;
            sharpe: number | null;
            sortino: number | null;
            max_drawdown: number;
        };
        beta: number | null;
        alpha_annual: number | null;
        last_signal: Point | undefined;
        status: string;
        evidence: string;
        orders_enabled: boolean;
        paid_tokens: number;
    };
}
