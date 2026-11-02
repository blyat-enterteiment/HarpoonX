"""Authentication and redirect regression tests; loopback and synthetic secrets only."""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from server import Gateway, handler, validate_service_token

TOKEN = 'SYNTHETIC-GATEWAY-TOKEN-NOT-A-REAL-SECRET'


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.gateway = Gateway(str(Path(self.tmp.name)/'db.sqlite'), 'synthetic-model',
                               'synthetic-provider-key', 1, 2, 1, 1)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler(self.gateway, TOKEN, {'https://panel.example.test'}))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def request(self, method='GET', path='/v1/health', headers=(), body=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        try:
            connection.putrequest(method, path)
            for name, value in headers:
                connection.putheader(name, value)
            connection.endheaders(body)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def post(self, extra):
        return self.request('POST', '/v1/jobs', [('Authorization', 'Bearer '+TOKEN), ('Content-Type', 'application/json'), *extra], b'{}')

    def test_non_ascii_authorization_is_401_not_connection_abort(self):
        self.assertEqual(self.request(headers=[('Authorization', 'Bearer caf\xe9')])[0], 401)

    def test_duplicate_authorization_headers_rejected(self):
        self.assertEqual(self.request(headers=[('Authorization', 'Bearer '+TOKEN), ('Authorization', 'Bearer wrong')])[0], 401)

    def test_wrong_scheme_rejected(self):
        self.assertEqual(self.request(headers=[('Authorization', 'Basic '+TOKEN)])[0], 401)

    def test_missing_authentication_rejected(self):
        self.assertEqual(self.request()[0], 401)

    def test_valid_bearer_returns_no_secrets(self):
        status, body = self.request(headers=[('Authorization', 'Bearer '+TOKEN)])
        self.assertEqual(status, 200)
        self.assertNotIn(TOKEN, json.dumps(body))
        self.assertNotIn(self.gateway.key, json.dumps(body))

    def test_cross_origin_rejected_even_with_bearer(self):
        self.assertEqual(self.request(headers=[('Authorization', 'Bearer '+TOKEN), ('Origin', 'https://evil.invalid')])[0], 401)

    def test_duplicate_content_length_rejected(self):
        self.assertEqual(self.post([('Content-Length', '2'), ('Content-Length', '2')])[0], 400)

    def test_chunked_body_rejected(self):
        self.assertEqual(self.post([('Content-Length', '2'), ('Transfer-Encoding', 'chunked')])[0], 400)

    def test_invalid_length_rejected(self):
        for length in ('-1', '30001', 'invalid'):
            with self.subTest(length=length):
                self.assertEqual(self.post([('Content-Length', length)])[0], 400)

    def test_invalid_service_tokens_fail_at_startup(self):
        for token in ('', 'short', '\xe9'*32, 'x'*257, 'x'*31+' '):
            with self.subTest(length=len(token)):
                with self.assertRaises(ValueError):
                    validate_service_token(token)

    def test_provider_redirect_never_reaches_second_destination(self):
        self.assert_redirect_blocked(self.gateway.opener)

    def test_installer_redirect_never_reaches_second_destination(self):
        spec = importlib.util.spec_from_file_location('installer', Path(__file__).parents[1]/'deploy/configure.py')
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        self.assert_redirect_blocked(urllib.request.build_opener(installer.NoRedirect()).open)

    def assert_redirect_blocked(self, opener):
        received = []
        class RedirectFixture(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                if self.path == '/target':
                    received.append(dict(self.headers))
                    self.send_response(200)
                else:
                    self.send_response(int(self.path[1:]))
                    self.send_header('Location', '/target')
                self.end_headers()
            do_POST = do_GET
        server = ThreadingHTTPServer(('127.0.0.1', 0), RedirectFixture)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for code in (301, 302, 303, 307, 308):
                for method in ('GET', 'POST'):
                    with self.subTest(code=code, method=method):
                        req = urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/'+str(code),
                            data=b'{}' if method=='POST' else None,
                            headers={'Authorization':'Bearer synthetic-key'}, method=method)
                        with self.assertRaises(urllib.error.HTTPError) as result:
                            opener(req, timeout=3)
                        self.assertEqual(result.exception.code, code)
                        result.exception.close()
            self.assertEqual(received, [])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main(verbosity=2)
