declare const DEFAULTS: {
    profile: Record<string, unknown>;
};
declare const HPSecurities: {
    profiles(): Record<string, unknown>[];
};
declare const HLab: {
    validate(x: unknown): Record<string, unknown>;
};
declare namespace HXX {
    const API = "harpoon.plugin/1";
    type Book = 'equity' | 'etf' | 'crypto';
    interface Manifest {
        api: string;
        id: string;
        version: string;
        name: string;
        book: Book;
        family: string;
        binding: 'host' | 'fixed';
        params: Record<string, unknown>;
    }
    function stable(v: unknown): string;
    function digest(v: unknown): Promise<string>;
    function recipe(p: Record<string, unknown>): Record<string, unknown>;
    function validate(raw: unknown): Manifest;
    function host(book: Book): Manifest;
    function builtins(): Manifest[];
    function securities(m: Manifest, base: Record<string, unknown>): Record<string, unknown>;
    function cryptoConfig(m: Manifest, base: HC19.Config): HC19.Config;
    function recovery(m: Manifest): HPRecovery.Manifest;
    function packet(manifests: Manifest[]): Promise<{
        schema: string;
        manifests: Manifest[];
        sha256: string;
    }>;
    function unpack(raw: unknown): Promise<Manifest[]>;
    function stamp(m: Manifest, profile: unknown): {
        api: string;
        id: string;
        version: string;
        manifest: Manifest;
        resolved: unknown;
        canonical: string;
    };
}
