from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sys
import time


LOG_PATH = sys.argv[1] if len(sys.argv) > 1 else "mock_codex_chat_upstream.jsonl"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 18181


def write_log(item):
    with open(LOG_PATH, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def chat_response(message, finish_reason="stop"):
    return {
        "id": "chatcmpl_mock_codex",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "mock-codex",
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


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
        if self.path.endswith("/api/tags"):
            self._send_json(200, {"models": [{"name": "mock-codex", "model": "mock-codex"}]})
            return
        if self.path.endswith("/v1/models"):
            self._send_json(
                200,
                {"object": "list", "data": [{"id": "mock-codex", "object": "model", "created": int(time.time()), "owned_by": "mock"}]},
            )
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length else b""
        body = json.loads(raw.decode("utf-8") or "{}")
        write_log({"method": "POST", "path": self.path, "headers": dict(self.headers), "body": body})
        if self.path.endswith("/v1/chat/completions"):
            has_tool_output = any(message.get("role") == "tool" for message in body.get("messages") or [])
            if not has_tool_output:
                self._send_json(
                    200,
                    chat_response(
                        {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_shell_mock_1",
                                    "type": "function",
                                    "function": {
                                        "name": "shell",
                                        "arguments": json.dumps(
                                            {
                                                "command": [
                                                    "powershell.exe",
                                                    "-Command",
                                                    "Write-Output codex-proxy-tool-ok",
                                                ]
                                            }
                                        ),
                                    },
                                }
                            ],
                        },
                        "tool_calls",
                    ),
                )
                return
            self._send_json(200, chat_response({"role": "assistant", "content": "codex-proxy-final-ok"}))
            return
        self._send_json(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    write_log({"event": "start", "port": PORT})
    server.serve_forever()
