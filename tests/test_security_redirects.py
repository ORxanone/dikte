"""Credential redirects are exercised only against disposable loopback servers."""
import http.server
import threading
import unittest
import urllib.request
from dikte import api


class CredentialRedirects(unittest.TestCase):
    def test_headers_are_not_reused_after_redirects(self):
        for method, data in (("GET", None), ("POST", b"synthetic")):
            for destination in ("https://different.invalid/models", "http://configured.invalid/models", "https://configured.invalid/next"):
                with self.subTest(method=method, destination=destination):
                    req = api._authenticated_request("https://configured.invalid/models", data=data,
                        headers={"aUtHoRiZaTiOn": "Bearer synthetic-only", "User-Agent": "test"}, method=method)
                    self.assertEqual(req.get_header("Authorization"), "Bearer synthetic-only")
                    redirected = urllib.request.HTTPRedirectHandler().redirect_request(
                        req, None, 302, "Found", {}, destination)
                    self.assertFalse(any(k.lower() == "authorization" for k, _ in redirected.header_items()))
                    self.assertEqual(redirected.get_header("User-agent"), "test")

    def test_real_get_and_post_redirects_strip_bearer_with_and_without_abort(self):
        original, received = [], []
        class Destination(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                received.append(self.headers.get("Authorization"))
                body = b'{"data": []}'
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *args):
                pass
        target = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Destination)
        class Redirect(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                original.append(self.headers.get("Authorization"))
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{target.server_port}/models")
                self.send_header("Content-Length", "0")
                self.end_headers()
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                self.do_GET()
            def log_message(self, *args):
                pass
        source = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
        threads = []
        for server in (target, source):
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            threads.append(thread)
        try:
            url = f"http://127.0.0.1:{source.server_port}/models"
            headers = {"Authorization": "Bearer synthetic-only"}
            api._get_json(url, headers)
            api._request(url, b"{}", headers)
            api._request(url, b"{}", headers, aborter=api.Aborter())
            self.assertEqual(original, ["Bearer synthetic-only"] * 3)
            self.assertEqual(received, [None] * 3)
        finally:
            for server in (source, target):
                server.shutdown()
                server.server_close()
            for thread in threads:
                thread.join(timeout=2)
