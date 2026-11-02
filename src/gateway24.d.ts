declare namespace HGateway24 {
    type Session = {
        authenticated: boolean;
        csrf?: string;
        expires?: number;
    };
    type Credentials = {
        url: string;
        token: string;
        mode?: 'integrated';
    };
    function localOrigin(origin: string): boolean;
    function eligible(origin: string): boolean;
    function route(path: string): string;
    function connected(s: Session | null): boolean;
}
