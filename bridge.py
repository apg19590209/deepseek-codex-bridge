#!/usr/bin/env python3
from bridge_history import history
from bridge_namespaces import flatten, restore
from bridge_stream import relay
import sys
import http.server, json, os, socketserver, urllib.request, urllib.error, uuid

MAX_REQUEST_BYTES = 4 * 1024 * 1024

HOST = ".".join(["api", "deepseek", "com"])
UPSTREAM = "https" + "://" + HOST + "/v1/chat/completions"
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

def responses_to_chat(req):
    messages = history(req)

    tools = []
    for t in req.get("tools", []):
        if t.get("type") != "function":
            raise ValueError("Unsupported tool type: " + str(t.get("type")))
        if t.get("type") == "function":
            fn = t.get("function", t)
            tools.append({
                "type": "function",
                "function": {
                    "name": fn["name"],
                    "description": fn.get("description", ""),
                    "parameters": fn.get("parameters", {"type": "object", "properties": {}})
                }
            })

    chat_req = {
        "model": req.get("model", "deepseek-chat"),
        "messages": messages,
        "stream": True, "thinking": {"type": "disabled"}
    }
    if tools:
        chat_req["tools"] = tools
    choice = req.get("tool_choice")
    if choice is not None:
        if isinstance(choice, dict) and choice.get("type") == "function":
            choice = {"type": "function", "function": {"name": choice.get("name") or choice.get("function", {}).get("name")}}
        chat_req["tool_choice"] = choice
    if "max_output_tokens" in req:
        chat_req["max_tokens"] = req["max_output_tokens"]
    return chat_req

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_POST(self):
        if not self.path.endswith("/responses"):
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
            if length <= 0 or length > MAX_REQUEST_BYTES:
                raise ValueError("Invalid request size")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict) or not body.get("input"):
                raise ValueError("Request must be an object with input")
        except (ValueError, TypeError, UnicodeDecodeError):
            self.send_error(400, "Invalid request body")
            return
        auth = self.headers.get("Authorization") or (f"Bearer {API_KEY}" if API_KEY else "")
        if not auth or not auth.lower().startswith("bearer ") or not auth[7:].strip():
            self.send_error(401, "Bearer authorization required")
            return
        try:
            translated, tool_map = flatten(body)
            converted = responses_to_chat(translated)
        except (ValueError, KeyError, TypeError):
            self.send_error(400, "Unsupported request/tool schema; bridge cannot safely translate it")
            return
        print(json.dumps({"event": "bridge_request", "tool_types": [t.get("type") for t in body.get("tools", [])], "forwarded_tools": len(converted.get("tools", []))}), file=sys.stderr, flush=True)
        chat_payload = json.dumps(converted).encode("utf-8")

        req = urllib.request.Request(
            UPSTREAM,
            data=chat_payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": auth,
                "Accept": "text/event-stream"
            },
            method="POST"
        )
        try:
            resp = urllib.request.urlopen(req, timeout=120)
        except urllib.error.HTTPError as e:
            err = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(err)
            return
        except (urllib.error.URLError, TimeoutError, OSError):
            self.send_error(502, "Upstream connection failed")
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def emit(event_name, data_obj):
            msg = f"event: {event_name}\ndata: {json.dumps(data_obj)}\n\n".encode("utf-8")
            self.wfile.write(msg)
            self.wfile.flush()

        sequence = 0
        raw_emit = emit
        def sequenced_emit(name, payload):
            nonlocal sequence
            payload = dict(payload, type=name, sequence_number=sequence)
            sequence += 1
            raw_emit(name, payload)
        try:
            result = relay(resp, sequenced_emit, lambda item: restore(item, tool_map))
            print(json.dumps(dict(result, event="bridge_response")), file=sys.stderr, flush=True)
        except (BrokenPipeError, ConnectionResetError):
            print(json.dumps({"event": "bridge_client_disconnected"}), file=sys.stderr, flush=True)
        finally:
            resp.close()

class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

if __name__ == "__main__":
    server = ThreadedHTTPServer(("127.0.0.1", 8317), Handler)
    server.serve_forever()
