import hashlib
import hmac
import io
import json
import unittest
from unittest.mock import Mock
from urllib.request import Request

from research.hf37.hf38_apps_script import AppsScriptDrive, GoogleContentRedirect, BATCH


class TestAppsScript(unittest.TestCase):
    def test_signed_upload_and_conflict(self):
        bridge = AppsScriptDrive("https://script.google.com/macros/s/test/exec", "folder", "x" * 32)
        bridge.opener = Mock()
        data = b"fixture"
        digest = hashlib.sha256(data).hexdigest()
        bridge.opener.open.return_value = io.BytesIO(b'{"status":"OK","id":"file","server_ms":2}')
        bridge.create("file", "folder", BATCH, digest, data)
        req = bridge.opener.open.call_args.args[0]
        envelope = json.loads(req.data)
        expected = hmac.digest(b"x" * 32, envelope["payload"].encode(), "sha256").hex()
        self.assertEqual(envelope["signature"], expected)
        self.assertEqual(json.loads(envelope["payload"])["sha256"], digest)
        self.assertEqual(bridge.timings[0]["script_ms"], 2)
        bridge.opener.open.return_value = io.BytesIO(b'{"status":"CONFLICT"}')
        with self.assertRaisesRegex(ValueError, "REJECTED"):
            bridge.create("file", "folder", BATCH, digest, data)

    def test_redirect_never_relays_post_body(self):
        handler = GoogleContentRedirect()
        post = Request("https://script.google.com/example", data=b"signed-data")
        redirected = handler.redirect_request(post, None, 302, "", {},
                                             "https://script.googleusercontent.com/example")
        self.assertEqual(redirected.get_method(), "GET")
        self.assertIsNone(redirected.data)
        with self.assertRaises(ValueError):
            handler.redirect_request(post, None, 302, "", {}, "https://example.com")
