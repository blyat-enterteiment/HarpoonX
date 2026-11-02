"""HARPOON XXIV: same-origin UI and the unchanged research gateway.
Run behind HTTPS; exactly one process and a persistent private data directory.
No Alpaca key, broker request, model-generated code or trading authority here.
"""
from __future__ import annotations
import collections
from types import ModuleType
from typing import TypedDict
fcntl: ModuleType | None
try:
    import fcntl as _fcntl
    fcntl = _fcntl
except ImportError:
    fcntl = None
import contextlib
import hmac
import http.cookies
import json
import math
import os
from pathlib import Path
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from cryptography.fernet import Fernet
from server import Gateway, handler
from supervision import ReviewError

VERSION = '24.0.0'
DEFAULT_CONFIG = dict(model='gpt-6-astra', input_rate=10.0, output_rate=50.0,
                      cached_rate=1.0, cache_write_rate=12.5, monthly_cap=30.0, run_cap=10.0)
COOKIE = 'harpoon24_session'


def atomic_private(path: Path, data: bytes) -> None:
    temp = path.with_name(path.name + '.' + secrets.token_hex(8) + '.tmp')
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temp.unlink()


def validate_config(value: object, old: dict | None = None) -> dict:
    if not isinstance(value, dict) or set(value) != set(DEFAULT_CONFIG) | {'api_key'}:
        raise ValueError('Configuración incompleta o con campos desconocidos')
    c = dict(value)
    if not isinstance(c['model'], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,119}', c['model']):
        raise ValueError('Identificador de modelo inválido')
    if c['api_key'] == '' and old:
        c['api_key'] = old['api_key']
    if not isinstance(c['api_key'], str) or not 20 <= len(c['api_key']) <= 512 or any(ch.isspace() for ch in c['api_key']):
        raise ValueError('Introduce una API key válida; no se acepta texto ni espacios')
    for name in DEFAULT_CONFIG:
        if name == 'model':
            continue
        v = c[name]
        if type(v) not in (float, int) or not math.isfinite(v) or not 0 <= v <= 1000:
            raise ValueError('Tarifa o límite inválido: ' + name)
        if name != 'cached_rate' and v <= 0:
            raise ValueError('La tarifa o límite debe ser positivo: ' + name)
    if c['cached_rate'] > c['input_rate'] or c['cache_write_rate'] < c['input_rate']:
        raise ValueError('Las tarifas de caché no son coherentes')
    if c['run_cap'] > c['monthly_cap']:
        raise ValueError('El techo por investigación no puede superar el mensual')
    return c


class ReviewSlot:
    def __init__(self, owner):
        self.owner = owner

    def __getattr__(self, name):
        if name not in ('get', 'submit', 'configure', 'health'):
            raise AttributeError(name)
        def call(*args, **kwargs):
            with self.owner.lock:
                reviews = self.owner.require().reviews
                prior = reviews.get(args[0]['id']) if name == 'submit' else None
                result = getattr(reviews, name)(*args, **kwargs)
                if name == 'submit' and prior is None:
                    self.owner.remember('review', result['id'])
                return self.owner.provenance('review', result) if name in ('get','submit') else result
        return call


class IntegratedGateway:
    """Configuration changes are serialized with submissions; original IDs/DB remain."""
    def __init__(self, directory: Path, opener=None, initial=None):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        self.opener = opener
        self.config = None
        self.gateway = None
        self.checked: dict[str, object] | None = None
        self.last_check = 0.0
        self.reviews = ReviewSlot(self)
        master_path = directory / 'gateway.master'
        env_key = os.environ.get('HARPOON_MASTER_KEY')
        if env_key:
            master = env_key.encode()
        elif master_path.exists():
            master = master_path.read_bytes()
        else:
            master = Fernet.generate_key()
            atomic_private(master_path, master)
        self.cipher = Fernet(master)
        path = directory / 'gateway.enc'
        if path.exists():
            # Never reset a damaged vault or its accounting silently.
            self.config = validate_config(json.loads(self.cipher.decrypt(path.read_bytes())))
        elif initial:
            self.config = validate_config(initial)
        if self.config:
            self.gateway = self.build(self.config)

    def build(self, c):
        g = Gateway(str(self.directory / 'research.sqlite'), c['model'], c['api_key'],
                       c['input_rate'], c['output_rate'], c['monthly_cap'], c['run_cap'],
                       opener=self.opener, cached_rate=c['cached_rate'], cache_write_rate=c['cache_write_rate'])
        with g.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS gateway24_models (kind TEXT, id TEXT, model TEXT, PRIMARY KEY(kind,id))')
        return g

    def remember(self, kind, identifier):
        with self.require().db() as db:
            db.execute('INSERT OR IGNORE INTO gateway24_models VALUES (?,?,?)', (kind,identifier,self.require().model))

    def provenance(self, kind, result):
        if result is None:
            return None
        with self.require().db() as db:
            row = db.execute('SELECT model FROM gateway24_models WHERE kind=? AND id=?', (kind,result['id'])).fetchone()
        return {**result, 'model':row[0], 'model_origin':'gateway24_submission'} if row else result

    def require(self):
        if self.gateway is None:
            raise ReviewError('Gateway disponible. Guarda primero la API key y el modelo en Conexiones.', 503)
        return self.gateway

    def public_config(self):
        with self.lock:
            return dict(version=VERSION, configured=bool(self.config),
                        config={k:v for k,v in (self.config or DEFAULT_CONFIG).items() if k != 'api_key'},
                        provider_check=self.checked, prices_verified_on=None,
                        pricing_status='operator_configured_not_verified',
                        pricing_source='https://developers.openai.com/api/docs/pricing')

    def configure(self, value):
        with self.lock:
            c = validate_config(value, self.config)
            if self.gateway:
                with self.gateway.db() as db:
                    busy = db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('pending','unknown')").fetchone()[0]
                    busy += db.execute("SELECT COUNT(*) FROM reviews WHERE status IN ('pending','running','unknown')").fetchone()[0]
                if busy:
                    raise ReviewError('Hay consultas pendientes o ambiguas. Conserva su configuración y reservas.', 409)
            # Construct before committing. Database and spent history are never replaced.
            next_gateway = self.build(c)
            atomic_private(self.directory / 'gateway.enc', self.cipher.encrypt(json.dumps(c).encode()))
            self.gateway, self.config, self.checked = next_gateway, c, None
            return self.public_config()

    def health(self):
        with self.lock:
            return {**self.require().health(), 'integrated_gateway': VERSION,
                    'provider_check': self.checked, 'inference_verified': False}

    def get(self, identifier):
        with self.lock:
            return self.provenance('job', self.require().get(identifier))

    def submit(self, *args, **kwargs):
        with self.lock:
            prior = self.require().get(args[0]['id'])
            result = self.require().submit(*args, **kwargs)
            if prior is None:
                self.remember('job', result['id'])
            return self.provenance('job', result)

    def check_provider(self):
        with self.lock:
            g = self.require()
            if time.monotonic() - self.last_check < 10:
                raise ReviewError('Espera 10 segundos antes de repetir la comprobación.', 429)
            self.last_check = time.monotonic()
            req = urllib.request.Request('https://api.openai.com/v1/models/' + urllib.parse.quote(g.model, safe=''),
                                         headers={'Authorization':'Bearer '+g.key}, method='GET')
            try:
                with g.opener(req, timeout=15) as response:
                    result = json.loads(response.read(100000))
                if result.get('id') != g.model:
                    raise ValueError('Modelo no confirmado')
            except urllib.error.HTTPError as error:
                self.checked = {'ok':False, 'http_status':error.code, 'at':time.time()}
                raise ReviewError('OpenAI rechazó la comprobación de clave/modelo (HTTP %s).' % error.code, 502) from None
            except Exception:
                self.checked = {'ok':False, 'at':time.time()}
                raise ReviewError('No se pudo confirmar OpenAI. No se consumieron tokens de generación.', 502) from None
            self.checked = {'ok':True, 'model':g.model, 'at':time.time(), 'generation_tokens':0,
                            'inference_verified':False, 'scope':'Clave y acceso al modelo; no prueba Responses ni rentabilidad'}
            return self.checked


class SessionEntry(TypedDict):
    csrf: str
    expires: float


class Sessions:
    def __init__(self, token: str, ttl: int = 43200):
        if len(token) < 32 or len(token) > 256 or not token.isascii() or any(x.isspace() for x in token):
            raise ValueError('HARPOON_SERVICE_TOKEN debe contener 32–256 caracteres ASCII sin espacios')
        self.token, self.ttl = token, ttl
        self.lock = threading.Lock()
        self.active: dict[str, SessionEntry] = {}
        self.failures: collections.deque[float] = collections.deque(maxlen=30)

    def login(self, token):
        with self.lock:
            now = time.monotonic()
            while self.failures and self.failures[0] < now-60:
                self.failures.popleft()
            if len(self.failures) >= 12:
                raise ReviewError('Demasiados intentos. Espera un minuto.', 429)
            if not isinstance(token, str) or not token.isascii() or not hmac.compare_digest(token, self.token):
                self.failures.append(now)
                raise ReviewError('Acceso privado incorrecto', 401)
            self.active = {k:v for k,v in self.active.items() if v['expires'] > time.time()}
            if len(self.active) >= 16:
                raise ReviewError('Límite de sesiones. Cierra una sesión o espera su vencimiento.', 429)
            sid, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            entry: SessionEntry = {'csrf':csrf, 'expires':time.time()+self.ttl}
            self.active[sid] = entry
            return sid, dict(entry)

    def get(self, sid):
        with self.lock:
            entry = self.active.get(sid)
            return dict(entry) if entry and entry['expires'] > time.time() else None

    def logout(self, sid):
        with self.lock:
            self.active.pop(sid, None)


def integrated_handler(slot, token, public_origin, html, extra_origins=()):
    u = urllib.parse.urlsplit(public_origin)
    local = u.scheme == 'http' and u.hostname in ('127.0.0.1', 'localhost', '::1')
    if (u.scheme != 'https' and not local) or not u.netloc or u.path or u.query or u.fragment or u.username or u.password:
        raise ValueError('HARPOON_PUBLIC_ORIGIN requiere https://dominio sin ruta. HTTP sólo para loopback.')
    sessions = Sessions(token)
    origins = {public_origin, *extra_origins}
    base = handler(slot, token, origins)
    page = Path(html).read_bytes()

    # The parent is constructed with this gateway/token; mypy cannot model factory inheritance.
    class IntegratedHandler(base):  # type: ignore[valid-type,misc]
        server_version = 'HARPOON/24'
        sys_version = ''

        def setup(self):
            super().setup()
            self.connection.settimeout(20)

        def end_headers(self):
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Content-Security-Policy', "frame-ancestors 'none'")
            if not local:
                self.send_header('Strict-Transport-Security', 'max-age=31536000')
            super().end_headers()

        def sid(self):
            try:
                jar = http.cookies.SimpleCookie(self.headers.get('Cookie', ''))
                return jar[COOKIE].value if COOKIE in jar else ''
            except http.cookies.CookieError:
                return ''

        def session(self):
            return sessions.get(self.sid())

        def same_origin(self):
            return self.headers.get('Origin') == public_origin

        def cookie_auth(self):
            s = self.session()
            if not s or self.headers.get('Sec-Fetch-Site') == 'cross-site':
                return False
            if self.command in ('GET', 'HEAD'):
                return self.headers.get('Origin') in (None, public_origin)
            csrf = self.headers.get('X-Harpoon-CSRF', '')
            return self.same_origin() and csrf.isascii() and hmac.compare_digest(csrf, s['csrf'])

        def auth(self):
            authorization = self.headers.get('Authorization', '')
            return (authorization.isascii() and super().auth()) or self.cookie_auth()

        def body(self):
            length = int(self.headers.get('Content-Length', '0'))
            if (self.headers.get('Transfer-Encoding')
                    or len(self.headers.get_all('Content-Length', [])) != 1
                    or not 0 < length <= 30000 or self.headers.get_content_type() != 'application/json'):
                raise ValueError('Se requiere JSON de hasta 30 KB')
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError('Cuerpo incompleto')
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError('Se requiere un objeto')
            return result

        def session_reply(self, status, value, sid='', clear=False):
            data = json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            if sid or clear:
                cookie = '%s=%s; Path=/; HttpOnly; SameSite=Strict; Max-Age=%s' % (COOKIE, sid, 0 if clear else sessions.ttl)
                if not local:
                    cookie += '; Secure'
                self.send_header('Set-Cookie', cookie)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            try:
                if self.path in ('/', '/HARPOON_XXIV.html'):
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('Content-Length', str(len(page)))
                    self.end_headers()
                    self.wfile.write(page)
                    return
                if self.path == '/healthz':
                    return self.reply(200, {'status':'alive','version':VERSION})
                if self.path == '/v1/bootstrap':
                    return self.reply(200, {'schema':'HARPOON-INTEGRATED-24','version':VERSION,'same_origin':True})
                if self.path == '/v1/session':
                    s = self.session() if self.cookie_auth() else None
                    return self.session_reply(200 if s else 401, {'authenticated':bool(s), **(s or {})})
                if self.path == '/v1/config':
                    if not self.cookie_auth():
                        return self.reply(401, {'error':'Inicia sesión en el gateway integrado'})
                    return self.reply(200, slot.public_config())
                return super().do_GET()
            except ReviewError as error:
                return self.reply(error.status, {'error':str(error)})

        def do_POST(self):
            try:
                if self.path == '/v1/session':
                    if not self.same_origin():
                        return self.reply(403, {'error':'Origen no permitido'})
                    request = self.body()
                    if set(request) != {'token'}:
                        raise ValueError('Formato de acceso inválido')
                    sid, s = sessions.login(request['token'])
                    return self.session_reply(200, {'authenticated':True, **s}, sid)
                if self.path in ('/v1/logout', '/v1/config', '/v1/provider-check'):
                    if not self.cookie_auth():
                        return self.reply(401, {'error':'Sesión o protección CSRF inválida; vuelve a entrar'})
                    request = self.body()
                    if self.path == '/v1/logout':
                        sessions.logout(self.sid())
                        return self.session_reply(200, {'authenticated':False}, clear=True)
                    if self.path == '/v1/provider-check':
                        return self.reply(200, slot.check_provider())
                    return self.reply(200, slot.configure(request))
                return super().do_POST()
            except ReviewError as error:
                return self.reply(error.status, {'error':str(error)})
            except (ValueError, TypeError, KeyError):
                return self.reply(400, {'error':'Configuración o cuerpo inválido; revisa modelo, tarifas y límites'})
            except (OSError, RuntimeError):
                return self.reply(503, {'error':'No se pudo completar la operación. Conserva configuración e historial.'})

    return IntegratedHandler


def main():
    os.umask(0o077)
    directory = Path(os.environ.get('HARPOON_DATA', '/data'))
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if fcntl is None:
        raise SystemExit('El servicio integrado requiere Linux/macOS o el contenedor Docker incluido.')
    instance_lock = (directory / 'gateway.lock').open('a')
    try:
        fcntl.flock(instance_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('Ya hay una instancia del gateway usando este volumen.') from None
    initial = None
    if os.environ.get('OPENAI_API_KEY'):
        initial = {**DEFAULT_CONFIG, 'api_key':os.environ['OPENAI_API_KEY']}
        mappings = dict(model='OPENAI_MODEL', input_rate='OPENAI_INPUT_USD_PER_MILLION',
                        output_rate='OPENAI_OUTPUT_USD_PER_MILLION', cached_rate='OPENAI_CACHED_USD_PER_MILLION',
                        cache_write_rate='OPENAI_CACHE_WRITE_USD_PER_MILLION', monthly_cap='HARPOON_MONTHLY_CAP', run_cap='HARPOON_RUN_CAP')
        for field, env in mappings.items():
            if env in os.environ:
                initial[field] = os.environ[env] if field == 'model' else float(os.environ[env])
    slot = IntegratedGateway(directory, initial=initial)
    origin = os.environ['HARPOON_PUBLIC_ORIGIN'].rstrip('/')
    extra = tuple(x.strip() for x in os.environ.get('HARPOON_ALLOWED_ORIGINS','').split(',') if x.strip())
    app = integrated_handler(slot, os.environ['HARPOON_SERVICE_TOKEN'], origin,
                             Path(__file__).parents[1] / 'HARPOON_XXIV.html', extra)
    address = ('0.0.0.0', int(os.environ.get('PORT', '8080')))
    print('HARPOON XXIV activo. Acceso privado; no se imprimen claves.', flush=True)
    ThreadingHTTPServer(address, app).serve_forever()


if __name__ == '__main__':
    main()
