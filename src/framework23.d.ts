/** Contracts shared by UI, sandbox and recursive controller. No executable plugins. */
declare namespace HF23 {
    type Book = 'equity' | 'etf' | 'crypto' | 'options';
    interface Field {
        kind: 'number' | 'integer' | 'boolean' | 'enum';
        min?: number;
        max?: number;
        step?: number;
        values?: readonly (string | number)[];
        label: string;
    }
    const SEC: Record<string, Field>;
    const TREND: Record<string, Field>;
    const RECOVERY: Record<string, Field>;
    const OPTIONS: Record<string, Field>;
    const ASTRA: Record<string, Field>;
    function fields(book: Book, family: string): Record<string, Field>;
    function patch(book: Book, family: string, base: Record<string, unknown>, change: Record<string, unknown>, scope?: 'exits' | 'strategy'): {
        [x: string]: unknown;
    };
    const PREFLIGHT: string[];
    interface Pulse {
        attempt_at: number;
        sync_at: number;
        market_at: number;
        completed_at: number;
        failures: number;
        error: string;
        busy: boolean;
        duration_ms: number;
    }
    function emptyPulse(): Pulse;
    function health(p: Pulse, connected: boolean, armed: boolean, reconciled: boolean, marketOpen: boolean, now?: number, ttl?: number): {
        status: string;
        age_ms: number | null;
        attempt_age_ms: number | null;
        ready: boolean;
        reason: string;
    };
    interface Policy {
        cold_on: boolean;
        hot_on: boolean;
        auto_paper: boolean;
        interval_seconds: number;
        max_iterations: number;
        goal: 'take_profit';
        scope: 'exits' | 'strategy';
    }
    const defaults: Policy;
    function policy(p: Policy): Policy;
    function promotionGates(report: any, source: HM23.Source, mode: string, auto: boolean, flat: boolean, baselineCurrent: boolean): {
        gates: {
            paper_only: boolean;
            auto_paper_authorized: boolean;
            flat_and_reconciled: boolean;
            baseline_unchanged: boolean;
            native_report: boolean;
            accepted: boolean;
            all_native_gates: boolean;
            independent_evidence: boolean;
            prospective: boolean;
            diagnostic_excluded: boolean;
        };
        allowed: boolean;
        reasons: string[];
    };
    function stable(x: any): string;
    function digest(x: any): Promise<string>;
}
