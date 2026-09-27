import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer

from webui import server


class MutationOriginTest(unittest.TestCase):
    """W09: a foreign page must not be able to drive state-changing endpoints."""

    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def post(self, headers):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        body = json.dumps({"document": {"schema_version": 1, "keyposes": []}})
        connection.putrequest("POST", "/api/keyposes/validate", skip_host=True)
        for name, value in {"Content-Length": str(len(body)), **headers}.items():
            connection.putheader(name, value)
        connection.endheaders(body.encode())
        response = connection.getresponse()
        response.read()
        connection.close()
        return response.status

    def test_same_origin_json_is_accepted(self):
        host = f"127.0.0.1:{self.port}"
        for headers in ({"Host": host, "Content-Type": "application/json"},
                        {"Host": f"localhost:{self.port}", "Origin": f"http://localhost:{self.port}",
                         "Content-Type": "application/json; charset=utf-8"}):
            with self.subTest(headers=headers):
                self.assertNotIn(self.post(headers), (403, 415))

    def test_foreign_or_simple_requests_are_rejected(self):
        host = f"127.0.0.1:{self.port}"
        cases = [
            ({"Host": host, "Origin": "http://evil.example", "Content-Type": "application/json"}, 403),
            ({"Host": f"evil.example:{self.port}", "Content-Type": "application/json"}, 403),
            ({"Host": host, "Content-Type": "text/plain"}, 415),
            ({"Host": host}, 415),
        ]
        for headers, expected in cases:
            with self.subTest(headers=headers):
                self.assertEqual(expected, self.post(headers))


if __name__ == "__main__":
    unittest.main()
