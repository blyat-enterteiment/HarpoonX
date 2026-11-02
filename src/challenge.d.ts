declare namespace HChallenge {
    interface Protocol {
        id: string;
        registered_at: number;
        start: string;
        end: string;
        capital: number;
        max_drawdown: number;
        trials: number;
        challenger: string;
        mandate: string;
    }
    interface Evidence {
        schema: string;
        protocol_id: string;
        source: 'LIVE' | 'PAPER' | 'SYNTHETIC';
        capital: number;
        days: string[];
        harpoon: number[];
        challenger: number[];
        benchmark?: number[];
        costs_reconciled: boolean;
        equal_risk: boolean;
        provenance: string;
    }
    function stats(a: number[], benchmark?: number[]): {
        net_return: number;
        cagr: number;
        max_drawdown: number;
        sharpe: number | null;
        sortino: number | null;
        beta: number | null;
        alpha_annual: number | null;
    };
    function validateProtocol(p: Protocol): Protocol;
    function evaluate(p: Protocol, e: Evidence): {
        schema: string;
        status: string;
        gates: {
            one_year: boolean;
            complete_period: boolean;
            live: boolean;
            costs: boolean;
            risk: boolean;
            within_drawdown: boolean;
            positive_net: boolean;
            larger_net: boolean;
            robust_difference: boolean;
        };
        harpoon: {
            net_return: number;
            cagr: number;
            max_drawdown: number;
            sharpe: number | null;
            sortino: number | null;
            beta: number | null;
            alpha_annual: number | null;
        };
        challenger: {
            net_return: number;
            cagr: number;
            max_drawdown: number;
            sharpe: number | null;
            sortino: number | null;
            beta: number | null;
            alpha_annual: number | null;
        };
        capital: number;
        ending_harpoon: number;
        ending_challenger: number;
        paired_block_bootstrap: {
            block: number;
            lower_daily: number;
        }[];
        observations: number;
        protocol: Protocol;
        provenance: string;
        source: "SYNTHETIC" | "LIVE" | "PAPER";
        limitation: string;
    };
}
