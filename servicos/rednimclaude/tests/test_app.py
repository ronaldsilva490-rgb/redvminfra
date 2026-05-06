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


class RedNimClaudeTests(unittest.TestCase):
    def test_clamp_max_tokens_reduces_only_output_budget(self):
        clamped = proxy.clamp_max_tokens(32000, 230145, 262144)
        self.assertEqual(clamped, 27903)

    def test_resolve_model_accepts_alias_and_target(self):
        alias = proxy.resolve_model("nim-glm-5.1")
        raw = proxy.resolve_model("z-ai/glm-5.1")
        self.assertEqual(alias["target"], "z-ai/glm-5.1")
        self.assertEqual(raw["id"], "nim-glm-5.1")

    def test_anthropic_payload_converts_tools_and_tool_results(self):
        body = {
            "model": "nim-qwen-next-80b",
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
        self.assertEqual(payload["model"], "qwen/qwen3-next-80b-a3b-instruct")
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertEqual(payload["messages"][2]["tool_calls"][0]["function"]["name"], "shell")
        self.assertEqual(payload["messages"][3]["role"], "tool")
        self.assertEqual(payload["tool_choice"]["function"]["name"], "shell")

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
        message = proxy.anthropic_message_from_openai(payload, "nim-glm-5.1")
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
        text = "".join(proxy.anthropic_sse_from_openai_stream(response, "nim-glm-5.1"))
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
        text = "".join(proxy.anthropic_sse_from_openai_stream(response, "nim-glm-5.1"))
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
        self.assertIn("nim-qwen-next-80b", ids)
        self.assertNotIn("nim-nemotron-3-super", ids)

    def test_messages_endpoint_forwards_to_nim(self):
        fake = FakeResponse(
            payload={
                "id": "chatcmpl_1",
                "choices": [{"finish_reason": "stop", "message": {"content": "OK"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            }
        )
        with patch.object(proxy, "proxy_openai_chat", return_value=fake), patch.object(proxy, "NVIDIA_API_KEY", "fake"):
            with proxy.app.test_client() as client:
                response = client.post(
                    "/v1/messages",
                    headers={"Authorization": "Bearer red"},
                    json={"model": "nim-qwen-next-80b", "messages": [{"role": "user", "content": "oi"}]},
                )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["model"], "nim-qwen-next-80b")
        self.assertEqual(body["content"][0]["text"], "OK")

    def test_context_retry_reduces_max_tokens_after_upstream_400(self):
        too_long = FakeResponse(
            status_code=400,
            payload={
                "error": {
                    "message": "This model's maximum context length is 262144 tokens. However, you requested 32000 output tokens and your prompt contains at least 230145 input tokens, for a total of at least 262145 tokens. Please reduce the length of the messages.",
                    "type": "upstream_error",
                }
            },
        )
        ok = FakeResponse(
            payload={
                "id": "chatcmpl_2",
                "choices": [{"finish_reason": "stop", "message": {"content": "OK"}}],
                "usage": {"prompt_tokens": 230145, "completion_tokens": 12},
            }
        )
        calls = []

        def fake_proxy(payload, *, stream):
            calls.append((payload["max_tokens"], stream))
            return too_long if len(calls) == 1 else ok

        with patch.object(proxy, "proxy_openai_chat", side_effect=fake_proxy):
            response = proxy.proxy_openai_chat_with_context_retry(
                {"model": "qwen/qwen3.5-122b-a10b", "messages": [{"role": "user", "content": "oi"}], "max_tokens": 32000},
                stream=False,
                context_window=262144,
                input_tokens=1000,
            )
        self.assertIs(response, ok)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0], 32000)
        self.assertEqual(calls[1][0], 26879)

    def test_context_retry_can_retry_more_than_once(self):
        too_long_1 = FakeResponse(
            status_code=400,
            payload={
                "error": {
                    "message": "This model's maximum context length is 262144 tokens. However, you requested 31487 output tokens and your prompt contains at least 230658 input tokens, for a total of at least 262145 tokens. Please reduce the length of the messages.",
                    "type": "upstream_error",
                }
            },
        )
        too_long_2 = FakeResponse(
            status_code=400,
            payload={
                "error": {
                    "message": "This model's maximum context length is 262144 tokens. However, you requested 31231 output tokens and your prompt contains at least 230700 input tokens, for a total of at least 261931 tokens. Please reduce the length of the messages.",
                    "type": "upstream_error",
                }
            },
        )
        ok = FakeResponse(
            payload={
                "id": "chatcmpl_3",
                "choices": [{"finish_reason": "stop", "message": {"content": "OK"}}],
                "usage": {"prompt_tokens": 230700, "completion_tokens": 12},
            }
        )
        calls = []

        def fake_proxy(payload, *, stream):
            calls.append(payload["max_tokens"])
            if len(calls) == 1:
                return too_long_1
            if len(calls) == 2:
                return too_long_2
            return ok

        with patch.object(proxy, "proxy_openai_chat", side_effect=fake_proxy):
            response = proxy.proxy_openai_chat_with_context_retry(
                {"model": "qwen/qwen3.5-122b-a10b", "messages": [{"role": "user", "content": "oi"}], "max_tokens": 32000},
                stream=False,
                context_window=262144,
                input_tokens=230145,
            )
        self.assertIs(response, ok)
        self.assertEqual(calls[:3], [27903, 26366, 25300])

    def test_rate_limit_retry_hides_single_429(self):
        limited = FakeResponse(status_code=429, payload={"status": 429, "title": "Too Many Requests"})
        ok = FakeResponse(
            payload={
                "id": "chatcmpl_4",
                "choices": [{"finish_reason": "stop", "message": {"content": "OK"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            }
        )
        calls = []

        def fake_proxy(payload, *, stream):
            calls.append(payload["max_tokens"])
            return limited if len(calls) == 1 else ok

        with patch.object(proxy, "proxy_openai_chat", side_effect=fake_proxy), \
             patch.object(proxy.NIM_RATE_LIMITER, "wait_for_slot", return_value=None), \
             patch.object(proxy.NIM_RATE_LIMITER, "on_429", return_value=None) as on_429, \
             patch.object(proxy.NIM_RATE_LIMITER, "on_success", return_value=None) as on_success:
            response = proxy.proxy_openai_chat_with_context_retry(
                {"model": "qwen/qwen3.5-122b-a10b", "messages": [{"role": "user", "content": "oi"}], "max_tokens": 100},
                stream=False,
                context_window=262144,
                input_tokens=1000,
            )
        self.assertIs(response, ok)
        self.assertEqual(len(calls), 2)
        on_429.assert_called_once()
        on_success.assert_called_once()


if __name__ == "__main__":
    unittest.main()
