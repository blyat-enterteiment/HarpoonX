/** Pure supervision contracts: no broker, mutation, credentials or model SDK. */
declare namespace HXXI {
    const VERSION = "21.0.0";
    type Mode = 'adaptive' | 'periodic' | 'logs' | 'paused';
    interface Config {
        enabled: boolean;
        mode: Mode;
        interval_seconds: number;
        heartbeat_seconds: number;
        daily_usd: number;
        monthly_usd: number;
        max_calls: number;
        output_tokens: number;
    }
    const defaults: Config;
    function configure(value: unknown): Config;
    function stable(v: unknown): string;
    function digest(v: unknown): Promise<string>;
    function finite(v: unknown): number | null;
    interface Window {
        start: number;
        end: number;
        key: string;
    }
    function windowAt(now: number, seconds: number, session: {
        open: number;
        close: number;
    } | null, cryptoBook: boolean): Window | null;
    interface Finding {
        severity: 'low' | 'medium' | 'high';
        title: string;
        evidence_ids: string[];
        recommendation: 'observe' | 'investigate' | 'propose_exit_trial';
        rationale: string;
    }
    interface Review {
        snapshot_id: string;
        config_hash: string;
        plugin_hash: string;
        verdict: 'no_issue_detected' | 'investigate' | 'insufficient_evidence';
        findings: Finding[];
        next_review_reason: string;
    }
    function validateReview(value: unknown, context: {
        snapshot_id: string;
        config_hash: string;
        plugin_hash: string;
        evidence: {
            id: string;
        }[];
    }): Review;
    function compound(c: {
        prior: number;
        realized: number;
        settled: number;
        peak: number;
        reserve: number;
        reserve_pct: number;
        growth_cap: number;
        capital_limit: number;
        equity: number;
    }): {
        budget: number;
        reserve: number;
    };
    function takeProfit(rows: {
        closed: boolean;
        gross?: number;
        net?: number;
        mfe_r?: number;
        captured_r?: number;
    }[]): {
        closed: number;
        net: number | null;
        net_complete: boolean;
        capture_proxy: number | null;
        paired: number;
    };
}
