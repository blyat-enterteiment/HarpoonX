/** XIII: paired daily evidence, bounded allocation and conditional survival research. */
declare namespace HXIII {
    const VERSION = "13.0.0";
    const POLICY = "XIII-EVIDENCE-1";
    type Source = 'PAPER' | 'LIVE' | 'REPLAY' | 'SYNTHETIC';
    interface Day {
        day: string;
        capital: number;
        equity: number;
        etf: number;
        equity_closes: number;
        etf_closes: number;
    }
    interface Evidence {
        schema: string;
        source: Source;
        policy_id: string;
        rows: Day[];
        costs_confirmed: boolean;
        through: string;
        basis: string;
    }
    interface Scenario {
        initial: number;
        target: number;
        sessions: number;
        paths: number;
        seed: number;
        block: number;
        monthly_cost: number;
        monthly_withdrawal: number;
        capital_cap: number;
        floor_fraction: number;
        drawdown_limit: number;
        drift: 'empirical' | 'conservative';
    }
    function quantile(a: number[], p: number): number;
    function random(seed: number): () => number;
    function validateEvidence(e: Evidence): void;
    function correlation(a: number[], b: number[]): number | null;
    function drawdown(r: number[]): number;
    function lowerMean(r: number[], block?: number, paths?: number, seed?: number): number | null;
    function analyze(e: Evidence): {
        source: Source;
        policy_id: string;
        through: string;
        sessions: number;
        books: {
            equity: {
                sessions: number;
                active_sessions: number;
                closed: number;
                contribution_usd: number;
                daily_mean: number | null;
                lower_mean_97_5: number | null;
                recent_mean: number | null;
                drawdown: number | null;
            };
            etf: {
                sessions: number;
                active_sessions: number;
                closed: number;
                contribution_usd: number;
                daily_mean: number | null;
                lower_mean_97_5: number | null;
                recent_mean: number | null;
                drawdown: number | null;
            };
        };
        correlation: number | null;
        downside_correlation: number | null;
        joint_loss_days: number;
        any_loss_days: number;
        joint_loss_fraction: number | null;
        diversification_ratio: number | null;
        joint_drawdown: number | null;
        joint_growth: number | null;
        basis: string;
    };
    function allocate(e: Evidence, current: {
        equity: number;
        etf: number;
    }, flat: boolean, freshEvidence: boolean): {
        scales: {
            equity: number;
            etf: number;
        };
        reasons: Record<string, string>;
        analysis: {
            source: Source;
            policy_id: string;
            through: string;
            sessions: number;
            books: {
                equity: {
                    sessions: number;
                    active_sessions: number;
                    closed: number;
                    contribution_usd: number;
                    daily_mean: number | null;
                    lower_mean_97_5: number | null;
                    recent_mean: number | null;
                    drawdown: number | null;
                };
                etf: {
                    sessions: number;
                    active_sessions: number;
                    closed: number;
                    contribution_usd: number;
                    daily_mean: number | null;
                    lower_mean_97_5: number | null;
                    recent_mean: number | null;
                    drawdown: number | null;
                };
            };
            correlation: number | null;
            downside_correlation: number | null;
            joint_loss_days: number;
            any_loss_days: number;
            joint_loss_fraction: number | null;
            diversification_ratio: number | null;
            joint_drawdown: number | null;
            joint_growth: number | null;
            basis: string;
        };
        basis: string;
    };
    function wilson(success: number, n: number): {
        estimate: number;
        lower: number;
        upper: number;
        count: number;
        paths: number;
    };
    function validateScenario(s: Scenario): void;
    function simulate(e: Evidence, s: Scenario): {
        status: string;
        reasons: string[];
        source: Source;
        sessions_observed: number;
        probabilities: null;
        policy_id?: undefined;
        through?: undefined;
        scenario?: undefined;
        terminal?: undefined;
        max_drawdown?: undefined;
        median_sessions_to_goal?: undefined;
        fan?: undefined;
        method?: undefined;
        limits?: undefined;
    } | {
        status: string;
        source: Source;
        policy_id: string;
        through: string;
        sessions_observed: number;
        scenario: Scenario;
        probabilities: {
            target_before_breach: {
                estimate: number;
                lower: number;
                upper: number;
                count: number;
                paths: number;
            };
            critical_breach: {
                estimate: number;
                lower: number;
                upper: number;
                count: number;
                paths: number;
            };
            floor_breach: {
                estimate: number;
                lower: number;
                upper: number;
                count: number;
                paths: number;
            };
            drawdown_breach: {
                estimate: number;
                lower: number;
                upper: number;
                count: number;
                paths: number;
            };
            terminal_target: {
                estimate: number;
                lower: number;
                upper: number;
                count: number;
                paths: number;
            };
        };
        terminal: {
            p05: number;
            p50: number;
            p95: number;
        };
        max_drawdown: {
            p50: number;
            p95: number;
        };
        median_sessions_to_goal: number | null;
        fan: {
            session: number;
            p05: number;
            p50: number;
            p95: number;
        }[];
        method: string;
        limits: string[];
        reasons?: undefined;
    };
    function survival(e: Evidence, s: Scenario): {
        status: string;
        reasons: string[];
        source: Source;
        sessions_observed: number;
        probabilities: null;
        policy_id?: undefined;
        through?: undefined;
        scenario?: undefined;
        terminal?: undefined;
        max_drawdown?: undefined;
        median_sessions_to_goal?: undefined;
        fan?: undefined;
        method?: undefined;
        limits?: undefined;
    } | {
        status: string;
        source: Source;
        policy_id: string;
        through: string;
        sessions_observed: number;
        scenario: Scenario;
        probabilities: {
            target_before_breach: {
                estimate: number;
                lower: number;
                upper: number;
                count: number;
                paths: number;
            };
            critical_breach: {
                estimate: number;
                lower: number;
                upper: number;
                count: number;
                paths: number;
            };
            floor_breach: {
                estimate: number;
                lower: number;
                upper: number;
                count: number;
                paths: number;
            };
            drawdown_breach: {
                estimate: number;
                lower: number;
                upper: number;
                count: number;
                paths: number;
            };
            terminal_target: {
                estimate: number;
                lower: number;
                upper: number;
                count: number;
                paths: number;
            };
        };
        terminal: {
            p05: number;
            p50: number;
            p95: number;
        };
        max_drawdown: {
            p50: number;
            p95: number;
        };
        median_sessions_to_goal: number | null;
        fan: {
            session: number;
            p05: number;
            p50: number;
            p95: number;
        }[];
        method: string;
        limits: string[];
        reasons?: undefined;
    } | {
        sensitivity: {
            block: number | undefined;
            target: {
                estimate: number;
                lower: number;
                upper: number;
                count: number;
                paths: number;
            } | undefined;
            critical: {
                estimate: number;
                lower: number;
                upper: number;
                count: number;
                paths: number;
            } | undefined;
            terminal: {
                p05: number;
                p50: number;
                p95: number;
            } | undefined;
        }[];
        changes_orders: boolean;
        status: string;
        reasons: string[];
        source: Source;
        sessions_observed: number;
        probabilities: null;
        policy_id?: undefined;
        through?: undefined;
        scenario?: undefined;
        terminal?: undefined;
        max_drawdown?: undefined;
        median_sessions_to_goal?: undefined;
        fan?: undefined;
        method?: undefined;
        limits?: undefined;
    } | {
        sensitivity: {
            block: number | undefined;
            target: {
                estimate: number;
                lower: number;
                upper: number;
                count: number;
                paths: number;
            } | undefined;
            critical: {
                estimate: number;
                lower: number;
                upper: number;
                count: number;
                paths: number;
            } | undefined;
            terminal: {
                p05: number;
                p50: number;
                p95: number;
            } | undefined;
        }[];
        changes_orders: boolean;
        status: string;
        source: Source;
        policy_id: string;
        through: string;
        sessions_observed: number;
        scenario: Scenario;
        probabilities: {
            target_before_breach: {
                estimate: number;
                lower: number;
                upper: number;
                count: number;
                paths: number;
            };
            critical_breach: {
                estimate: number;
                lower: number;
                upper: number;
                count: number;
                paths: number;
            };
            floor_breach: {
                estimate: number;
                lower: number;
                upper: number;
                count: number;
                paths: number;
            };
            drawdown_breach: {
                estimate: number;
                lower: number;
                upper: number;
                count: number;
                paths: number;
            };
            terminal_target: {
                estimate: number;
                lower: number;
                upper: number;
                count: number;
                paths: number;
            };
        };
        terminal: {
            p05: number;
            p50: number;
            p95: number;
        };
        max_drawdown: {
            p50: number;
            p95: number;
        };
        median_sessions_to_goal: number | null;
        fan: {
            session: number;
            p05: number;
            p50: number;
            p95: number;
        }[];
        method: string;
        limits: string[];
        reasons?: undefined;
    };
    function variants<T extends Record<string, unknown>>(base: T): T[];
}
