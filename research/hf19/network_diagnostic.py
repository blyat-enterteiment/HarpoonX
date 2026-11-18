"""HF19 diagnostic only: DNS, TCP, TLS and unauthenticated HTTPS from Render runtime.
No API keys, orders, broker calls, or arbitrary destination input.
"""
import http.server
import json
import os
import socket
import ssl
import urllib.error
import urllib.request

HOST = "data.alpaca.markets"

def check():
    result = {"target": HOST, "dns": False, "tcp443": False,
              "tls_valid": False, "https_response": False}
    try:
        addresses = socket.getaddrinfo(HOST, 443, type=socket.SOCK_STREAM)
        result["dns"] = bool(addresses)
    except Exception as exc:
        result["error_stage"] = "dns"
        result["error_type"] = type(exc).__name__
        return result
    try:
        with socket.create_connection((HOST, 443), timeout=8):
            result["tcp443"] = True
    except Exception as exc:
        result["error_stage"] = "tcp"
        result["error_type"] = type(exc).__name__
        return result
    try:
        context = ssl.create_default_context()
        with socket.create_connection((HOST, 443), timeout=8) as raw:
            with context.wrap_socket(raw, server_hostname=HOST) as secure:
                result["tls_valid"] = secure.version() is not None
    except Exception as exc:
        result["error_stage"] = "tls"
        result["error_type"] = type(exc).__name__
        return result
    try:
        req = urllib.request.Request("https://" + HOST + "/v2/stocks/AAPL/quotes?feed=iex&limit=1",
                                     headers={"User-Agent": "HarpoonX-HF19-network-diagnostic"})
        with urllib.request.urlopen(req, timeout=10, context=ssl.create_default_context()) as resp:
            result["https_response"] = True
            result["http_status"] = resp.status
    except urllib.error.HTTPError as exc:
        result["https_response"] = True
        result["http_status"] = exc.code
        result["authentication"] = "NOT_ATTEMPTED"
    except Exception as exc:
        result["error_stage"] = "https"
        result["error_type"] = type(exc).__name__
    return result

DIAGNOSTIC = check()
print("HF19_STARTUP_NETWORK_RESULT " + json.dumps(DIAGNOSTIC, sort_keys=True), flush=True)

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        print("HF19_HTTP_REQUEST " + repr(self.path[:120]), flush=True)
        payload = json.dumps(DIAGNOSTIC, sort_keys=True).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
    def log_message(self, *args):
        return

if __name__ == "__main__":
    http.server.HTTPServer(("0.0.0.0", int(os.environ.get("PORT", "10000"))), Handler).serve_forever()
