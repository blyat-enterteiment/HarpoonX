/** XII: pure deterministic primitives. No network, orders or model-generated code. */
declare namespace HXII {
    const VERSION = "12.0.0";
    const POLICY = "XII-EVENT-1";
    const REQUIRED = 384;
    const FEATURES: readonly ["rvol", "momentum_bps", "spread_bps", "volume_acceleration", "atr_pct", "vwap_distance", "sector_relative_bps", "session_minutes"];
    type Feature = Record<string, unknown>;
    interface TrainingRow {
        at: number;
        end: number;
        day: string;
        feature: Feature;
        target: number;
    }
    interface Selector {
        version: string;
        through: number;
        cutoff: number;
        n: number;
        days: number;
        calibration_n: number;
        means: number[];
        scales: number[];
        weights: number[];
        bias: number;
        margin: number;
        features: string[];
        basis: string;
    }
    function vector(f: Feature): number[] | null;
    function fitSelector(input: TrainingRow[], cutoff: number): Selector | null;
    function selection(f: Feature, m: Selector | null | undefined, at: number): {
        eligible: boolean;
        estimate: null;
        lower: null;
        reason: string;
    } | {
        eligible: boolean;
        estimate: number;
        lower: number;
        reason: string;
    };
    function cluster(f: Feature): string;
    interface Exposure {
        symbol: string;
        factor: string;
        leverage: number;
        nominal: number;
        risk: number;
    }
    function clusterRoom(f: Feature, active: Exposure[], budget: number, exposureCap?: number, riskCap?: number): {
        cluster: string;
        nominal: number;
        risk: number;
        members: string[];
    };
    interface VolState {
        at: number;
        bid: number;
        rate: number;
        count: number;
    }
    function updateVol(prior: VolState | null | undefined, bid: number, at: number, entryAtr: number): {
        state: VolState | null;
        atr: number;
    };
    function bucket(f: Feature): {
        book: string;
        session: string;
        liquidity: string;
        regime: string;
    };
    interface AttributionRow {
        id: string;
        symbol: string;
        feature: Feature;
        net: number | null;
        gross: number | null;
        risk: number;
        filled: boolean;
        decision: string;
        mfe: number | null;
        mae: number | null;
        hours: number | null;
        first_target_minutes: number | null;
        giveback: number | null;
        source: 'broker' | 'shadow';
    }
    function attribution(rows: AttributionRow[]): {
        broker: {
            signals: number;
            filled: number;
            net: number | null;
            expectancy_r: number | null;
            mfe: number | null;
            mae: number | null;
            hours: number | null;
            minutes_tp1: number | null;
            giveback_r: number | null;
        };
        shadow: {
            signals: number;
            filled: number;
            net: number | null;
            expectancy_r: number | null;
            mfe: number | null;
            mae: number | null;
            hours: number | null;
            minutes_tp1: number | null;
            giveback_r: number | null;
        };
        groups: {
            signals: number;
            filled: number;
            net: number | null;
            expectancy_r: number | null;
            mfe: number | null;
            mae: number | null;
            hours: number | null;
            minutes_tp1: number | null;
            giveback_r: number | null;
            rows: undefined;
            source: string;
            dimension: string;
            bucket: string;
        }[];
        recent: AttributionRow[];
        basis: string;
    };
    function variants<T extends Record<string, unknown>>(base: T): T[];
    function stage(closed: number, completeDays: number, net: number, drawdown: number, costsComplete: boolean): 1 | 0.5 | 0.25;
}
