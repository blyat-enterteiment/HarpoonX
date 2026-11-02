/** HARPOON Tensor Library 1.0.0. Float64; explicit masks; no network or order authority. */
declare namespace HTensor {
    const VERSION = "1.0.0";
    interface Matrix {
        rows: number;
        cols: number;
        data: Float64Array;
    }
    interface Record {
        asset: string;
        at: number;
        availableAt: number;
        values: Array<number | null>;
    }
    interface Cube {
        schema: string;
        version: string;
        axes: {
            assets: string[];
            times: number[];
            features: string[];
        };
        shape: [number, number, number];
        data: Float64Array;
        mask: Uint8Array;
        observed_at: Float64Array;
        cutoff: number;
        excluded_future: number;
        duplicates: number;
        truncated_times: number;
    }
    function dot(a: ArrayLike<number>, b: ArrayLike<number>): number;
    function matrix(rows: number[][]): Matrix;
    function multiply(a: Matrix, b: Matrix): Matrix;
    function design(xs: number[][], means: number[], scales: number[], clip?: number): Matrix;
    function ridgeSystem(z: Matrix, targets: number[], lambda?: number): {
        a: number[][];
        b: number[];
    };
    function build(records: Record[], features: string[], cutoff: number, maxTimes?: number): Cube;
    function statistics(cube: Cube): {
        shape: [number, number, number];
        bytes: number;
        present: number;
        cells: number;
        coverage: number;
        complete_rows: number;
        features: {
            name: string;
            count: number;
            mean: number | null;
            sd: number | null;
        }[];
        covariance_complete_cases: (number | null)[][];
        covariance_shrinkage_20pct: (number | null)[][];
        basis: string;
    };
    function serialize(cube: Cube): {
        data: number[];
        mask: number[];
        observed_at: number[];
        layout: string;
        limits: string;
        schema: string;
        version: string;
        axes: {
            assets: string[];
            times: number[];
            features: string[];
        };
        shape: [number, number, number];
        cutoff: number;
        excluded_future: number;
        duplicates: number;
        truncated_times: number;
    };
}
