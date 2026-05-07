import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as proxy  # noqa: E402


class FakeResponse:
    def __init__(self, status_code=200, payload=None, lines=None):
        self.status_code = status_code
        self._payload = payload or {}
        self._lines = lines or []
        self.content = json.dumps(self._payload).encode("utf-8")
        self.text = self.content.decode("utf-8", "replace")

    def json(self):
        return self._payload

    def iter_lines(self, decode_unicode=False, chunk_size=1):
        for item in self._lines:
            yield item


class RedLightningClaudeTests(unittest.TestCase):
    def test_resolve_model_accepts_raw_ids(self):
        alias = proxy.resolve_model("anthropic/claude-sonnet-4-6")
        raw = proxy.resolve_model("lightning-ai/deepseek-v4-pro")
        self.assertEqual(alias["target"], "anthropic/claude-sonnet-4-6")
        self.assertEqual(raw["id"], "lightning-ai/deepseek-v4-pro")

    def test_clamp_max_tokens_respects_context(self):
        clamped = proxy.clamp_max_tokens(32000, 238599, 262144)
        self.assertEqual(clamped, 19449)

    def test_anthropic_payload_converts_tools_and_tool_results(self):
        body = {
            "model": "anthropic/claude-sonnet-4-6",
            "system": "Seja conciso.",
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "Veja isso"}]},
                {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_1", "name": "shell", "input": {"command": "dir"}}]},
                {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "ok"}]},
            ],
            "tools": [{"name": "shell", "description": "Executa", "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}}}],
            "tool_choice": {"type": "tool", "name": "shell"},
        }
        payload = proxy.anthropic_to_openai_payload(body, proxy.resolve_model(body["model"]))
        self.assertEqual(payload["model"], "anthropic/claude-sonnet-4-6")
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertEqual(payload["messages"][2]["tool_calls"][0]["function"]["name"], "shell")
        self.assertEqual(payload["messages"][3]["role"], "tool")
        self.assertEqual(payload["tool_choice"]["function"]["name"], "shell")

    def test_anthropic_payload_preserves_tool_result_before_followup_user_text(self):
        body = {
            "model": "anthropic/claude-sonnet-4-6",
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": "toolu_1", "name": "shell", "input": {"command": "dir"}}
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": "toolu_1", "content": "resultado"},
                        {"type": "text", "text": "docker nao, poe xampp mesmo"},
                    ],
                },
            ],
        }
        payload = proxy.anthropic_to_openai_payload(body, proxy.resolve_model(body["model"]))
        self.assertEqual(payload["messages"][0]["role"], "assistant")
        self.assertEqual(payload["messages"][1]["role"], "tool")
        self.assertEqual(payload["messages"][1]["tool_call_id"], "toolu_1")
        self.assertEqual(payload["messages"][2]["role"], "user")
        self.assertEqual(payload["messages"][2]["content"], "docker nao, poe xampp mesmo")

    def test_anthropic_message_from_openai_maps_tool_calls(self):
        payload = {
            "id": "chatcmpl_1",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {"id": "call_1", "type": "function", "function": {"name": "shell", "arguments": "{\"command\":\"dir\"}"}}
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 3},
        }
        message = proxy.anthropic_message_from_openai(payload, "anthropic/claude-sonnet-4-6")
        self.assertEqual(message["stop_reason"], "tool_use")
        self.assertEqual(message["content"][0]["type"], "tool_use")
        self.assertEqual(message["content"][0]["name"], "shell")

    def test_stream_conversion_emits_text_and_stop(self):
        lines = [
            b'data: {"choices":[{"delta":{"content":"ola "},"finish_reason":null}]}',
            b'data: {"choices":[{"delta":{"content":"mundo"},"finish_reason":"stop"}],"usage":{"prompt_tokens":3,"completion_tokens":2}}',
            b"data: [DONE]",
        ]
        response = FakeResponse(lines=lines)
        text = "".join(proxy.anthropic_sse_from_openai_stream(response, "anthropic/claude-sonnet-4-6"))
        self.assertIn('"type": "message_start"', text)
        self.assertIn('"text": "ola "', text)
        self.assertIn('"text": "mundo"', text)
        self.assertIn('"stop_reason": "end_turn"', text)

    def test_stream_conversion_emits_tool_use(self):
        lines = [
            b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","type":"function","function":{"name":"shell","arguments":"{\\"command\\""}}]},"finish_reason":null}]}',
            b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":":\\"dir\\"}"}}]},"finish_reason":"tool_calls"}]}',
            b"data: [DONE]",
        ]
        response = FakeResponse(lines=lines)
        text = "".join(proxy.anthropic_sse_from_openai_stream(response, "anthropic/claude-sonnet-4-6"))
        self.assertIn('"type": "tool_use"', text)
        self.assertIn('"partial_json": "{\\"command\\""', text)
        self.assertIn('"stop_reason": "tool_use"', text)

    def test_models_endpoint_requires_auth(self):
        with proxy.app.test_client() as client:
            response = client.get("/v1/models")
        self.assertEqual(response.status_code, 401)

    def test_models_endpoint_lists_curated_models(self):
        with proxy.app.test_client() as client:
            response = client.get("/v1/models", headers={"Authorization": "Bearer red"})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        ids = [item["id"] for item in data["data"]]
        self.assertIn("anthropic/claude-opus-4-7", ids)
        self.assertIn("lightning-ai/deepseek-v4-pro", ids)

    def test_messages_endpoint_forwards_to_lightning(self):
        fake = FakeResponse(
            payload={
                "id": "chatcmpl_1",
                "choices": [{"finish_reason": "stop", "message": {"content": "OK"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            }
        )
        with patch.object(proxy, "proxy_openai_chat", return_value=fake), patch.object(proxy.KEY_POOL, "has_keys", return_value=True), patch.object(proxy.KEY_POOL, "acquire", return_value={"token": "fake"}), patch.object(proxy.KEY_POOL, "on_success", return_value=None):
            with proxy.app.test_client() as client:
                response = client.post(
                    "/v1/messages",
                    headers={"Authorization": "Bearer red"},
                    json={"model": "anthropic/claude-sonnet-4-6", "messages": [{"role": "user", "content": "oi"}]},
                )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["model"], "anthropic/claude-sonnet-4-6")
        self.assertEqual(body["content"][0]["text"], "OK")

    def test_rate_limit_rotates_to_next_key(self):
        limited = FakeResponse(status_code=429, payload={"status": 429, "title": "Too Many Requests"})
        ok = FakeResponse(
            payload={
                "id": "chatcmpl_3",
                "choices": [{"finish_reason": "stop", "message": {"content": "OK"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            }
        )
        calls = []
        pool_items = [{"token": "key1"}, {"token": "key2"}]

        def fake_acquire():
            return pool_items[len(calls)]

        def fake_proxy(payload, *, stream, api_key):
            calls.append(api_key)
            return limited if api_key == "key1" else ok

        with patch.object(proxy, "proxy_openai_chat", side_effect=fake_proxy), \
             patch.object(proxy.KEY_POOL, "acquire", side_effect=fake_acquire), \
             patch.object(proxy.KEY_POOL, "on_429", return_value=None) as on_429, \
             patch.object(proxy.KEY_POOL, "on_success", return_value=None) as on_success:
            response = proxy.proxy_openai_chat_with_context_retry(
                {"model": "anthropic/claude-sonnet-4-6", "messages": [{"role": "user", "content": "oi"}], "max_tokens": 64},
                stream=False,
                context_window=200000,
                input_tokens=1000,
            )
        self.assertIs(response, ok)
        self.assertEqual(calls, ["key1", "key2"])
        on_429.assert_called_once()
        on_success.assert_called_once()

    def test_server_error_rotates_to_next_key(self):
        broken = FakeResponse(status_code=502, payload={"error": {"message": "temporary failure"}})
        ok = FakeResponse(
            payload={
                "id": "chatcmpl_4",
                "choices": [{"finish_reason": "stop", "message": {"content": "OK"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            }
        )
        calls = []
        pool_items = [{"token": "key1"}, {"token": "key2"}]

        def fake_acquire():
            return pool_items[len(calls)]

        def fake_proxy(payload, *, stream, api_key):
            calls.append(api_key)
            return broken if api_key == "key1" else ok

        with patch.object(proxy, "proxy_openai_chat", side_effect=fake_proxy), \
             patch.object(proxy.KEY_POOL, "acquire", side_effect=fake_acquire), \
             patch.object(proxy.KEY_POOL, "on_5xx", return_value=None) as on_5xx, \
             patch.object(proxy.KEY_POOL, "on_success", return_value=None) as on_success:
            response = proxy.proxy_openai_chat_with_context_retry(
                {"model": "anthropic/claude-sonnet-4-6", "messages": [{"role": "user", "content": "oi"}], "max_tokens": 64},
                stream=False,
                context_window=200000,
                input_tokens=1000,
            )
        self.assertIs(response, ok)
        self.assertEqual(calls, ["key1", "key2"])
        on_5xx.assert_called_once()
        on_success.assert_called_once()

    def test_context_retry_reduces_max_tokens_after_upstream_400(self):
        too_long = FakeResponse(
            status_code=400,
            payload={
                "error": {
                    "message": "This model's maximum context length is 262144 tokens. However, you requested 23546 output tokens and your prompt contains at least 238599 input tokens, for a total of at least 262145 tokens. Please reduce the length of the messages.",
                    "type": "upstream_error",
                }
            },
        )
        ok = FakeResponse(
            payload={
                "id": "chatcmpl_2",
                "choices": [{"finish_reason": "stop", "message": {"content": "OK"}}],
                "usage": {"prompt_tokens": 238599, "completion_tokens": 12},
            }
        )
        calls = []

        def fake_proxy(payload, *, stream, api_key):
            calls.append(payload["max_tokens"])
            return too_long if len(calls) == 1 else ok

        with patch.object(proxy, "proxy_openai_chat", side_effect=fake_proxy), \
             patch.object(proxy.KEY_POOL, "acquire", return_value={"token": "key1"}), \
             patch.object(proxy.KEY_POOL, "on_success", return_value=None):
            response = proxy.proxy_openai_chat_with_context_retry(
                {"model": "anthropic/claude-sonnet-4-6", "messages": [{"role": "user", "content": "oi"}], "max_tokens": 23546},
                stream=False,
                context_window=262144,
                input_tokens=238599,
            )
        self.assertIs(response, ok)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], 19449)
        self.assertEqual(calls[1], 17401)


if __name__ == "__main__":
    unittest.main()
