"use strict";
var HGateway24;
(function (HGateway24) {
    function localOrigin(origin) {
        try {
            const u = new URL(origin);
            return u.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(u.hostname) && u.origin === origin;
        }
        catch {
            return false;
        }
    }
    HGateway24.localOrigin = localOrigin;
    function eligible(origin) {
        try {
            const u = new URL(origin);
            return u.origin === origin && (u.protocol === 'https:' || localOrigin(origin));
        }
        catch {
            return false;
        }
    }
    HGateway24.eligible = eligible;
    function route(path) {
        if (!/^\/v1\/(?:bootstrap|session|logout|config|provider-check|health|review-policy|jobs(?:\/[A-Za-z0-9-]{1,80})?|reviews(?:\/[A-Za-z0-9-]{1,80})?)$/.test(path))
            throw Error('Ruta fuera del gateway HARPOON');
        return path;
    }
    HGateway24.route = route;
    function connected(s) { return Boolean(s?.authenticated && s.csrf && s.expires && s.expires * 1000 > Date.now()); }
    HGateway24.connected = connected;
})(HGateway24 || (HGateway24 = {}));
