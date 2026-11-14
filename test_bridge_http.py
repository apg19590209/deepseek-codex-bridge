"""Local HTTP integration; upstream and credentials are synthetic."""
import contextlib
import copy
import io
import json
import threading
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch
import bridge

class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.server = bridge.ThreadedHTTPServer(("127.0.0.1", 0), bridge.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:%s/v1/responses" % self.server.server_port
        self.client = urllib.request.urlopen

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, payload):
        return urllib.request.Request(self.url, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Authorization": "Bearer synthetic-test-value"})

    def test_text_roundtrip_and_auth(self):
        chunks = [
            {"choices": [{"delta": {"content": "Hello"}, "finish_reason": None}]},
            {"choices": [{"delta": {}, "finish_reason": "stop"}]}]
        stream = io.BytesIO(("".join("data: " + json.dumps(c) + "\n\n" for c in chunks)
                            + "data: [DONE]\n\n").encode())
        captured = []
        def fake_upstream(req, **kwargs):
            captured.append(req)
            return stream
        with patch.object(bridge.urllib.request, "urlopen", side_effect=fake_upstream), contextlib.redirect_stderr(io.StringIO()):
            with self.client(self.request({"input": "hello", "stream": True}), timeout=5) as response:
                body = response.read().decode()
        self.assertEqual(captured[0].get_header("Authorization"), "Bearer synthetic-test-value")
        self.assertEqual(json.loads(captured[0].data)["messages"], [{"role": "user", "content": "hello"}])
        events = [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]
        self.assertEqual(events[-1]["type"], "response.completed")
        self.assertEqual(events[-1]["response"]["output"][0]["content"][0]["text"], "Hello")
        self.assertEqual([e["sequence_number"] for e in events], list(range(len(events))))

    def test_unsupported_tool_rejected_before_upstream(self):
        with patch.object(bridge.urllib.request, "urlopen") as upstream:
            with self.assertRaises(urllib.error.HTTPError) as exc:
                self.client(self.request({"input": "hello", "tools": [{"type": "custom", "name": "patch"}]}), timeout=5)
            self.assertEqual(exc.exception.code, 400)
            exc.exception.close()
            upstream.assert_not_called()

    def test_invalid_request_and_missing_auth(self):
        for raw in (b'', b'{bad', b'[]', b'{}'):
            with self.subTest(raw=raw), self.assertRaises(urllib.error.HTTPError) as exc:
                self.client(urllib.request.Request(self.url, data=raw), timeout=5)
            self.assertEqual(exc.exception.code, 400)
            exc.exception.close()
        with self.assertRaises(urllib.error.HTTPError) as exc:
            self.client(urllib.request.Request(self.url, data=b'{"input":"hello"}'), timeout=5)
        self.assertEqual(exc.exception.code, 401)
        exc.exception.close()

    def test_upstream_network_failure_is_502(self):
        with patch.object(bridge.urllib.request, 'urlopen', side_effect=urllib.error.URLError('synthetic')):
            with self.assertRaises(urllib.error.HTTPError) as exc:
                self.client(self.request({'input': 'hello'}), timeout=5)
        self.assertEqual(exc.exception.code, 502)
        exc.exception.close()

if __name__ == "__main__":
    unittest.main()
