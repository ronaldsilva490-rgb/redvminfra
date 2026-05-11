from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import app as inferproxy


class FakeResponse:
    def __init__(self, status_code=200, payload=None, lines=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self._lines = lines or []
        self.headers = headers or {"Content-Type": "application/json"}
        self.text = json.dumps(self._payload)
        self.content = self.text.encode("utf-8")

    def json(self):
        return self._payload

    def iter_lines(self, decode_unicode=False, chunk_size=1):
        yield from self._lines

    def iter_content(self, chunk_size=1):
        yield self.text.encode("utf-8")


class StreamingOnlyResponse:
    status_code = 200
    headers = {"Content-Type": "text/event-stream"}

    @property
    def content(self):
        raise AssertionError("streaming response content was buffered")

    @property
    def text(self):
        raise AssertionError("streaming response text was buffered")

    def iter_content(self, chunk_size=1):
        yield b"event: message_start\n"
        yield b'data: {"type":"message_start","message":{"id":"msg_stream","type":"message","role":"assistant","content":[],"model":"Sonnet 4.6","stop_reason":null,"stop_sequence":null,"usage":{"input_tokens":0,"output_tokens":0}}}\n\n'


class InferProxyTranslationTests(unittest.TestCase):
    def test_claude_tool_schema_is_preserved_inside_openai_function(self) -> None:
        body = {
            "model": "Kimi 2.6",
            "messages": [{"role": "user", "content": "use a tool"}],
            "tools": [
                {
                    "name": "Write",
                    "description": "Writes a file",
                    "input_schema": {
                        "$schema": "http://json-schema.org/draft-07/schema#",
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}},
                        "required": ["file_path", "content"],
                    },
                }
            ],
            "tool_choice": {"type": "tool", "name": "Write"},
        }
        payload = inferproxy.inferall_payload_from_anthropic(body, inferproxy.resolve_model(body["model"]))

        self.assertEqual(payload["provider"], "nvidia")
        self.assertEqual(payload["operation"], "chat")
        self.assertEqual(payload["model"], "moonshotai/kimi-k2.6")
        params = payload["tools"][0]["function"]["parameters"]
        self.assertEqual(params["$schema"], "http://json-schema.org/draft-07/schema#")
        self.assertIs(params["additionalProperties"], False)
        self.assertEqual(payload["tool_choice"], {"type": "function", "function": {"name": "Write"}})

    def test_tool_use_and_tool_result_round_trip_to_openai_messages(self) -> None:
        body = {
            "system": [{"type": "text", "text": "You are a coding agent."}],
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Vou ler."},
                        {"type": "tool_use", "id": "toolu_read", "name": "Read", "input": {"file_path": "index.html"}},
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": "toolu_read", "content": "<html></html>"},
                    ],
                },
            ],
        }
        messages = inferproxy.anthropic_messages_to_openai(body)

        self.assertEqual(messages[0], {"role": "system", "content": "You are a coding agent."})
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[1]["tool_calls"][0]["function"]["name"], "Read")
        self.assertEqual(json.loads(messages[1]["tool_calls"][0]["function"]["arguments"])["file_path"], "index.html")
        self.assertEqual(messages[2], {"role": "tool", "tool_call_id": "toolu_read", "content": "<html></html>"})

    def test_effort_and_thinking_are_forwarded(self) -> None:
        body = {
            "model": "Sonnet 4.6",
            "messages": [{"role": "user", "content": "pense"}],
            "output_config": {"effort": "max"},
            "thinking": {"type": "adaptive"},
        }
        payload = inferproxy.inferall_payload_from_anthropic(body, inferproxy.resolve_model(body["model"]))

        self.assertEqual(payload["provider"], "anthropic")
        self.assertEqual(payload["model"], "claude-sonnet-4-6-20250327")
        self.assertEqual(payload["reasoning_effort"], "max")
        self.assertIs(payload["enable_thinking"], True)
        self.assertEqual(payload["thinking"], {"type": "adaptive"})

    def test_openai_response_with_tool_call_becomes_anthropic_tool_use(self) -> None:
        data = {
            "id": "chatcmpl_test",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_write",
                                "type": "function",
                                "function": {"name": "Write", "arguments": "{\"file_path\":\"index.html\",\"content\":\"ok\"}"},
                            }
                        ],
                    },
                }
            ],
        }
        message = inferproxy.anthropic_message_from_openai(data, "Kimi 2.6")

        self.assertEqual(message["stop_reason"], "tool_use")
        self.assertEqual(message["content"][0]["type"], "tool_use")
        self.assertEqual(message["content"][0]["name"], "Write")
        self.assertEqual(message["content"][0]["input"]["file_path"], "index.html")

    def test_stream_text_delta_becomes_anthropic_sse(self) -> None:
        lines = [
            b'data: {"choices":[{"delta":{"content":"Oi"}}]}',
            b"data: [DONE]",
        ]
        output = "".join(inferproxy.openai_delta_stream_to_anthropic(lines, "Kimi 2.6"))

        self.assertIn("event: message_start", output)
        self.assertIn("event: content_block_delta", output)
        self.assertIn('"text":"Oi"', output)
        self.assertIn("event: message_stop", output)

    def test_messages_route_returns_anthropic_shape(self) -> None:
        client = inferproxy.app.test_client()
        upstream = FakeResponse(
            payload={
                "id": "chatcmpl_ok",
                "choices": [{"message": {"content": "OK_ROUTE"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            }
        )

        old_mode = inferproxy.UPSTREAM_MODE
        inferproxy.UPSTREAM_MODE = "generate"
        try:
            with patch.object(inferproxy, "upstream_generate", return_value=upstream):
                response = client.post(
                    "/v1/messages",
                    json={"model": "Kimi 2.6", "messages": [{"role": "user", "content": "oi"}], "max_tokens": 32},
                )
        finally:
            inferproxy.UPSTREAM_MODE = old_mode

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["type"], "message")
        self.assertEqual(data["content"][0], {"type": "text", "text": "OK_ROUTE"})
        self.assertEqual(data["usage"], {"input_tokens": 10, "output_tokens": 2})

    def test_messages_mode_passes_anthropic_payload_to_v1_messages(self) -> None:
        client = inferproxy.app.test_client()
        upstream = FakeResponse(
            payload={
                "id": "msg_ok",
                "type": "message",
                "role": "assistant",
                "model": "moonshotai/kimi-k2.6",
                "content": [{"type": "text", "text": "OK_MESSAGES"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        )
        captured = {}

        def fake_upstream(payload, *, stream):
            captured["payload"] = payload
            captured["stream"] = stream
            return upstream

        old_mode = inferproxy.UPSTREAM_MODE
        inferproxy.UPSTREAM_MODE = "messages"
        try:
            with patch.object(inferproxy, "upstream_messages", side_effect=fake_upstream):
                response = client.post(
                    "/v1/messages",
                    json={
                        "model": "Kimi 2.6",
                        "messages": [{"role": "user", "content": "oi"}],
                        "tools": [{"name": "Write", "input_schema": {"type": "object"}}],
                        "thinking": {"type": "adaptive"},
                        "output_config": {"effort": "max"},
                        "max_tokens": 32,
                    },
                )
        finally:
            inferproxy.UPSTREAM_MODE = old_mode

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["payload"]["model"], "moonshotai/kimi-k2.6")
        self.assertEqual(captured["payload"]["tools"], [{"name": "Write", "description": "", "input_schema": {"type": "object", "properties": {}}}])
        self.assertNotIn("system", captured["payload"])
        self.assertEqual(captured["payload"]["thinking"], {"type": "adaptive"})
        self.assertEqual(captured["payload"]["output_config"], {"effort": "max"})
        self.assertEqual(response.get_json()["content"][0]["text"], "OK_MESSAGES")

    def test_opus_post_write_payload_removes_thinking_for_inferall_abort_avoidance(self) -> None:
        body = {
            "model": "Opus 4.6",
            "messages": [
                {
                    "role": "assistant",
                    "content": [{"type": "tool_use", "id": "toolu_write", "name": "Write", "input": {"file_path": "index.html", "content": "ok"}}],
                },
                {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_write", "content": "created"}]},
            ],
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": "high"},
        }

        payload = inferproxy.inferall_anthropic_payload(body, inferproxy.resolve_model(body["model"]))

        self.assertEqual(payload["model"], "claude-opus-4-6-20250327")
        self.assertNotIn("thinking", payload)
        self.assertEqual(payload["output_config"], {"effort": "high"})

    def test_sonnet_post_write_payload_keeps_thinking(self) -> None:
        body = {
            "model": "Sonnet 4.6",
            "messages": [
                {
                    "role": "assistant",
                    "content": [{"type": "tool_use", "id": "toolu_write", "name": "Write", "input": {"file_path": "index.html", "content": "ok"}}],
                },
                {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_write", "content": "created"}]},
            ],
            "thinking": {"type": "adaptive"},
        }

        payload = inferproxy.inferall_anthropic_payload(body, inferproxy.resolve_model(body["model"]))

        self.assertEqual(payload["thinking"], {"type": "adaptive"})

    def test_compact_tool_schema_preserves_required_names_and_basic_types(self) -> None:
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "command": {"description": "long", "type": "string"},
                "timeout": {"description": "long", "type": "number"},
                "mode": {"type": "string", "enum": ["a", "b"]},
            },
            "required": ["command"],
            "additionalProperties": False,
        }
        compact = inferproxy.compact_json_schema(schema)

        self.assertNotIn("$schema", compact)
        self.assertEqual(compact["properties"]["command"], {"type": "string"})
        self.assertEqual(compact["properties"]["timeout"], {"type": "number"})
        self.assertEqual(compact["properties"]["mode"], {"type": "string", "enum": ["a", "b"]})
        self.assertEqual(compact["required"], ["command"])
        self.assertIs(compact["additionalProperties"], False)

    def test_compact_tool_schema_preserves_eager_input_streaming(self) -> None:
        compact = inferproxy.compact_anthropic_tool(
            {
                "name": "Write",
                "input_schema": {"type": "object"},
                "eager_input_streaming": True,
            }
        )

        self.assertIs(compact["eager_input_streaming"], True)

    def test_messages_stream_does_not_buffer_upstream_content(self) -> None:
        client = inferproxy.app.test_client()

        old_mode = inferproxy.UPSTREAM_MODE
        inferproxy.UPSTREAM_MODE = "messages"
        try:
            with patch.object(inferproxy, "upstream_messages", return_value=StreamingOnlyResponse()):
                response = client.post(
                    "/v1/messages",
                    json={"model": "Sonnet 4.6", "messages": [{"role": "user", "content": "oi"}], "max_tokens": 32, "stream": True},
                )
        finally:
            inferproxy.UPSTREAM_MODE = old_mode

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Accel-Buffering"], "no")
        self.assertIn(b"message_start", response.get_data())

    def test_messages_route_retries_same_model_before_returning_error(self) -> None:
        client = inferproxy.app.test_client()
        first = FakeResponse(status_code=502, payload={"type": "error", "error": {"message": "All providers failed"}})
        second = FakeResponse(
            payload={
                "id": "msg_ok",
                "type": "message",
                "role": "assistant",
                "model": "qwen/qwen3-coder-480b-a35b-instruct",
                "content": [{"type": "text", "text": "OK_FALLBACK"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        )
        calls = []

        def fake_upstream(payload, *, stream):
            calls.append(payload["model"])
            if len(calls) == 1:
                return first
            return second

        old_attempts = inferproxy.UPSTREAM_RETRY_ATTEMPTS
        old_mode = inferproxy.UPSTREAM_MODE
        old_fallback = inferproxy.ENABLE_MODEL_FALLBACK
        inferproxy.UPSTREAM_RETRY_ATTEMPTS = 2
        inferproxy.UPSTREAM_MODE = "messages"
        inferproxy.ENABLE_MODEL_FALLBACK = False
        try:
            with patch.object(inferproxy, "upstream_messages", side_effect=fake_upstream):
                response = client.post(
                    "/v1/messages",
                    json={"model": "Sonnet 4.6", "messages": [{"role": "user", "content": "oi"}], "max_tokens": 32},
                )
        finally:
            inferproxy.UPSTREAM_RETRY_ATTEMPTS = old_attempts
            inferproxy.UPSTREAM_MODE = old_mode
            inferproxy.ENABLE_MODEL_FALLBACK = old_fallback

        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls[0], "claude-sonnet-4-6-20250327")
        self.assertEqual(calls[1], "claude-sonnet-4-6-20250327")
        self.assertEqual(response.get_json()["content"][0]["text"], "OK_FALLBACK")

    def test_opus_abort_is_retried_without_thinking_on_same_model(self) -> None:
        client = inferproxy.app.test_client()
        first = FakeResponse(status_code=500, payload={"error": "This operation was aborted"})
        second = FakeResponse(
            payload={
                "id": "msg_ok",
                "type": "message",
                "role": "assistant",
                "model": "claude-opus-4-6-20250327",
                "content": [{"type": "text", "text": "OK_OPUS_RESCUE"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        )
        payloads = []

        def fake_upstream(payload, *, stream):
            payloads.append(payload)
            return first if len(payloads) == 1 else second

        old_attempts = inferproxy.UPSTREAM_RETRY_ATTEMPTS
        old_mode = inferproxy.UPSTREAM_MODE
        old_rescue = inferproxy.OPUS_ABORT_RETRY_WITHOUT_THINKING
        inferproxy.UPSTREAM_RETRY_ATTEMPTS = 1
        inferproxy.UPSTREAM_MODE = "messages"
        inferproxy.OPUS_ABORT_RETRY_WITHOUT_THINKING = True
        try:
            with patch.object(inferproxy, "upstream_messages", side_effect=fake_upstream):
                response = client.post(
                    "/v1/messages",
                    json={
                        "model": "Opus 4.6",
                        "messages": [{"role": "user", "content": "oi"}],
                        "thinking": {"type": "adaptive"},
                        "max_tokens": 32,
                    },
                )
        finally:
            inferproxy.UPSTREAM_RETRY_ATTEMPTS = old_attempts
            inferproxy.UPSTREAM_MODE = old_mode
            inferproxy.OPUS_ABORT_RETRY_WITHOUT_THINKING = old_rescue

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payloads[0]["model"], "claude-opus-4-6-20250327")
        self.assertEqual(payloads[1]["model"], "claude-opus-4-6-20250327")
        self.assertIn("thinking", payloads[0])
        self.assertNotIn("thinking", payloads[1])
        self.assertEqual(response.get_json()["content"][0]["text"], "OK_OPUS_RESCUE")

    def test_opus_without_thinking_uses_opus_abort_retry_budget(self) -> None:
        client = inferproxy.app.test_client()
        failed = FakeResponse(status_code=500, payload={"error": "This operation was aborted"})
        success = FakeResponse(
            payload={
                "id": "msg_ok",
                "type": "message",
                "role": "assistant",
                "model": "claude-opus-4-6-20250327",
                "content": [{"type": "text", "text": "OK_OPUS_THIRD"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        )
        calls = []

        def fake_upstream(payload, *, stream):
            calls.append(payload)
            return success if len(calls) == 3 else failed

        old_attempts = inferproxy.UPSTREAM_RETRY_ATTEMPTS
        old_opus_attempts = inferproxy.OPUS_ABORT_RETRY_ATTEMPTS
        old_mode = inferproxy.UPSTREAM_MODE
        inferproxy.UPSTREAM_RETRY_ATTEMPTS = 1
        inferproxy.OPUS_ABORT_RETRY_ATTEMPTS = 3
        inferproxy.UPSTREAM_MODE = "messages"
        try:
            with patch.object(inferproxy, "upstream_messages", side_effect=fake_upstream):
                response = client.post(
                    "/v1/messages",
                    json={"model": "Opus 4.6", "messages": [{"role": "user", "content": "oi"}], "max_tokens": 32},
                )
        finally:
            inferproxy.UPSTREAM_RETRY_ATTEMPTS = old_attempts
            inferproxy.OPUS_ABORT_RETRY_ATTEMPTS = old_opus_attempts
            inferproxy.UPSTREAM_MODE = old_mode

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(calls), 3)
        self.assertEqual(response.get_json()["content"][0]["text"], "OK_OPUS_THIRD")

    def test_messages_route_does_not_fallback_to_another_model_by_default(self) -> None:
        client = inferproxy.app.test_client()
        failed = FakeResponse(status_code=502, payload={"type": "error", "error": {"message": "All providers failed"}})
        calls = []

        def fake_upstream(payload, *, stream):
            calls.append(payload["model"])
            return failed

        old_attempts = inferproxy.UPSTREAM_RETRY_ATTEMPTS
        old_mode = inferproxy.UPSTREAM_MODE
        old_fallback = inferproxy.ENABLE_MODEL_FALLBACK
        inferproxy.UPSTREAM_RETRY_ATTEMPTS = 1
        inferproxy.UPSTREAM_MODE = "messages"
        inferproxy.ENABLE_MODEL_FALLBACK = False
        try:
            with patch.object(inferproxy, "upstream_messages", side_effect=fake_upstream):
                response = client.post(
                    "/v1/messages",
                    json={"model": "Sonnet 4.6", "messages": [{"role": "user", "content": "oi"}], "max_tokens": 32},
                )
        finally:
            inferproxy.UPSTREAM_RETRY_ATTEMPTS = old_attempts
            inferproxy.UPSTREAM_MODE = old_mode
            inferproxy.ENABLE_MODEL_FALLBACK = old_fallback

        self.assertEqual(response.status_code, 502)
        self.assertEqual(calls, ["claude-sonnet-4-6-20250327"])


if __name__ == "__main__":
    unittest.main()
