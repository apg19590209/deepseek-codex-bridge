"""Translation-rejection diagnostics: stage, exception class, allowlisted reason only."""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

REASON = "Unsupported request/tool schema; bridge cannot safely translate it"

RUNNER = textwrap.dedent('''
    import json, sys, threading, urllib.error, urllib.request
    import bridge
    payload = json.load(sys.stdin)
    server = bridge.ThreadedHTTPServer(("127.0.0.1", 0), bridge.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    request = urllib.request.Request("http://127.0.0.1:%d/v1/responses" % server.server_port,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer synthetic-test-value"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            code, reason = response.status, ""
            response.read()
    except urllib.error.HTTPError as exc:
        code, reason = exc.code, exc.reason
        exc.close()
    server.shutdown()
    server.server_close()
    thread.join()
    json.dump({"code": code, "reason": reason}, sys.stdout)
    sys.stdout.flush()
''')

DIRECT_RUNNER = textwrap.dedent("""
    import io, json, sys
    import bridge

    def run():
        payload = json.loads(sys.stdin.read())
        handler = type("Handler", (), {})()
        handler.send_error = lambda code, message=None: None
        handler.send_response = lambda code: None
        handler.send_header = lambda key, value: None
        handler.end_headers = lambda: None
        handler.wfile = io.BytesIO()
        handler.rfile = io.BytesIO(json.dumps(payload).encode())
        handler.headers = {"Content-Length": str(len(json.dumps(payload).encode())),
                           "Authorization": "Bearer synthetic-test-value"}
        handler.path = "/v1/responses"
        bridge.Handler.do_POST(handler)

    run()
""")

HERE = os.path.dirname(os.path.abspath(__file__))


class DiagnosticTests(unittest.TestCase):
    def reject(self, payload):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, "-c", RUNNER], cwd=HERE,
                input=json.dumps(payload).encode(), capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        outcome = json.loads(result.stdout)
        stderr = result.stderr.decode()
        self.assertEqual(outcome["code"], 400)
        self.assertEqual(outcome["reason"], REASON)
        events = [json.loads(line) for line in stderr.splitlines() if line.strip()]
        self.assertEqual([e["event"] for e in events], ["bridge_translation_rejected"], stderr)
        return events[0], stderr

    def test_flatten_stage_rejection_logged(self):
        event, _ = self.reject({"input": "hello", "tools": [{"type": "custom", "name": "patch"}]})
        self.assertEqual(event["stage"], "flatten")
        self.assertEqual(event["exception"], "ValueError")
        self.assertEqual(event["reason"], "Unsupported child tool type")

    def test_responses_to_chat_stage_rejection_logged(self):
        event, _ = self.reject({"input": [{"type": "message", "role": "user",
            "content": [{"type": "input_image", "image_url": "https://example.invalid/x.png"}]}]})
        self.assertEqual(event["stage"], "responses_to_chat")
        self.assertEqual(event["exception"], "ValueError")
        self.assertEqual(event["reason"], "Unsupported non-text content")

    def test_allowlisted_labels_kept(self):
        cases = (
            ({"input": "hello", "tools": [{"type": "namespace", "name": "ns",
                                           "tools": [{"type": "custom", "name": "patch"}]}]},
             "flatten", "Unsupported child tool type"),
            ({"input": "hello", "tools": [{"type": "function", "function": {"name": "run"}},
                                          {"type": "function", "function": {"name": "run"}}]},
             "flatten", "Duplicate tool identity"),
            ({"input": [{"type": "message", "role": "user", "content": "hello"},
                        {"type": "message", "role": "tool", "content": "result"}]},
             "responses_to_chat", "Unsupported message role"),
            ({"input": [{"type": "function_call", "name": "run", "arguments": "{}"}]},
             "responses_to_chat", "Tool call lacks call_id"),
            ({"input": [{"type": "unknown_item"}]},
             "responses_to_chat", "Unsupported history item"),
        )
        for payload, stage, label in cases:
            with self.subTest(stage=stage, label=label):
                event, _ = self.reject(payload)
                self.assertEqual(event["stage"], stage)
                self.assertEqual(event["reason"], label)
                self.assertEqual(set(event), {"event", "stage", "exception", "reason"})

    def test_unlisted_details_suppressed(self):
        secret = "PRIVATE-CANARY-7f3c9a-QWERTY"
        payload = {"input": [{"type": "message", "role": "user",
                              "content": [{"type": "input_text", "text": 7}]}]}
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, "-c", DIRECT_RUNNER], cwd=HERE,
                input=json.dumps(payload).encode(), capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        stderr = result.stderr.decode()
        event = json.loads(stderr.strip().splitlines()[-1])
        self.assertEqual(event["stage"], "responses_to_chat")
        self.assertEqual(event["exception"], "TypeError")
        self.assertEqual(event["reason"], "details omitted")
        self.assertNotIn(secret, stderr)

    def test_flatten_raise_details_never_logged(self):
        secret = "PRIVATE-CANARY-7f3c9a-QWERTY"
        event, stderr = self.reject({"input": "hello", "tools": [{"type": "namespace", "name": secret,
                                                                 "tools": [{"type": "custom", "name": secret}]}]})
        self.assertEqual(event["stage"], "flatten")
        self.assertEqual(event["reason"], "Unsupported child tool type")
        self.assertNotIn(secret, stderr)

    def test_allowlisted_label_without_request_detail(self):
        secret = "PRIVATE-CANARY-7f3c9a-QWERTY"
        cases = (
            ({"input": [{"type": "message", "role": "user",
                         "content": [{"type": "input_image", "image_url": secret}]}]},
             "Unsupported non-text content"),
            ({"input": [{"type": "message", "role": "user", "content": secret},
                        {"type": "message", "role": secret, "content": "body " + secret}]},
             "Unsupported message role"),
        )
        for payload, label in cases:
            with self.subTest(label=label):
                event, stderr = self.reject(payload)
                self.assertEqual(event["reason"], label)
                self.assertNotIn(secret, stderr)

    def test_request_contents_and_auth_not_logged(self):
        canaries = ("private prompt text", "/root/private/path/image.png")
        _, stderr = self.reject({"input": [{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": canaries[0]},
            {"type": "input_image", "image_url": canaries[1]}]}]})
        for canary in canaries:
            self.assertNotIn(canary, stderr)


if __name__ == "__main__":
    unittest.main()
