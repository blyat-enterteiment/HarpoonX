/** Read-only presentation model. It has no broker, credentials or order authority. */
declare namespace HUX {
    type Code = 'ON' | 'OFF' | 'WAIT' | 'ERROR';
    interface Status {
        code: Code;
        label: string;
        reason: string;
    }
    interface EngineState {
        connected: boolean;
        armed: boolean;
        reconciled: boolean;
        halt: string;
        lastTick: number;
        staleMs: number;
        now: number;
        marketOpen: boolean;
        pending: boolean;
        visible: boolean;
        cryptoBook: boolean;
    }
    function state(code: Code, reason: string): Status;
    function entries(e: EngineState): Status;
    function exits(e: EngineState, count: number): Status;
    interface Manifest {
        id: string;
        version: string;
        book: string;
        family: string;
        name: string;
        binding: string;
    }
    function merge<T extends Manifest>(current: T[], incoming: T[], stable: (m: T) => string): {
        catalog: T[];
        added: number;
        duplicates: number;
    };
    function rootJson(name: string, path?: string): boolean;
}
