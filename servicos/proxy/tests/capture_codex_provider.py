from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sys
import time
import uuid


LOG_PATH = sys.argv[1] if len(sys.argv) > 1 else "codex_capture.jsonl"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 18080


def write_log(item):
    with open(LOG_PATH, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send_json(self, status, payload):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        write_log({"method": "GET", "path": self.path, "headers": dict(self.headers)})
        if self.path.endswith("/models"):
            self._send_json(
                200,
                {
                    "object": "list",
                    "data": [
                        {"id": "capture-model", "object": "model", "created": int(time.time()), "owned_by": "capture"}
                    ],
                },
            )
            return
        self._send_json(404, {"error": {"message": "not found"}})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            body = raw.decode("utf-8", errors="replace")
        write_log({"method": "POST", "path": self.path, "headers": dict(self.headers), "body": body})
        if self.path.endswith("/responses"):
            created = int(time.time())
            response = {
                "id": "resp_" + uuid.uuid4().hex,
                "object": "response",
                "created_at": created,
                "status": "completed",
                "model": body.get("model") or "capture-model",
                "output": [
                    {
                        "id": "msg_" + uuid.uuid4().hex,
                        "type": "message",
                        "status": "completed",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "captured",
                                "annotations": [],
                            }
                        ],
                    }
                ],
                "output_text": "captured",
                "error": None,
                "incomplete_details": None,
                "parallel_tool_calls": True,
                "previous_response_id": None,
                "reasoning": {"effort": None, "summary": None},
                "tool_choice": body.get("tool_choice") or "auto",
                "tools": body.get("tools") or [],
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            }
            self._send_json(200, response)
            return
        self._send_json(404, {"error": {"message": "not found"}})

    def log_message(self, fmt, *args):
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    write_log({"event": "start", "port": PORT})
    server.serve_forever()
