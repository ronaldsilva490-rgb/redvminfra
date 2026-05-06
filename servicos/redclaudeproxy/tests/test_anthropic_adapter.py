import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("REDCLAUDEPROXY_KEYS", "normal:red")
os.environ.setdefault("REDCLAUDEPROXY_AUTH_TOKENS", "red")

import app as proxy  # noqa: E402


class FakeUpstreamResponse:
    def __init__(self, status_code, payload, headers=None):
        self.status_code = status_code
        self.headers = headers or {"Content-Type": "application/json"}
        self._content = json.dumps(payload).encode("utf-8")
        self.closed = False

    @property
    def content(self):
        return self._content

    @property
    def text(self):
        return self._content.decode("utf-8", errors="replace")

    def json(self):
        return json.loads(self.text)

    def close(self):
        self.closed = True


class AnthropicAdapterTest(unittest.TestCase):
    def run_with_key_pool(self, keys, callback):
        old_pool = proxy.key_pool
        old_cache = list(proxy._claude_model_cache)
        old_loaded_at = proxy._claude_model_cache_loaded_at
        try:
            with patch.object(proxy.KeyPool, "load_usage", lambda self: None), patch.object(proxy.KeyPool, "save_usage_locked", lambda self: None):
                proxy.key_pool = proxy.KeyPool([proxy.KeyState(name=name, key=key) for name, key in keys])
                proxy._claude_model_cache = list(proxy.CLAUDE_MODEL_ALIASES)
                proxy._claude_model_cache_loaded_at = proxy.time.time()
                return callback(proxy.key_pool)
        finally:
            proxy.key_pool = old_pool
            proxy._claude_model_cache = old_cache
            proxy._claude_model_cache_loaded_at = old_loaded_at

    def test_models_are_imported_from_normal_proxy_catalog(self):
        catalog = {
            "object": "list",
            "data": [
                {
                    "id": "claude-red-devstral-medium",
                    "display_name": "RED MIS Devstral Medium",
                    "owned_by": "mistralai",
                    "max_context_length": 262144,
                    "red": {
                        "provider": "mistral",
                        "route_model": "devstral-medium-latest",
                        "function_calling": True,
                        "note": "ok",
                    },
                },
                {
                    "id": "NIM - z-ai/glm-5.1",
                    "display_name": "NIM - z-ai/glm-5.1",
                    "owned_by": "nvidia",
                    "red": {"provider": "nvidia", "route_model": "NIM - z-ai/glm-5.1"},
                },
            ],
        }

        proxy._claude_model_cache = []
        with patch.object(proxy.http, "get", return_value=FakeUpstreamResponse(200, catalog)):
            with proxy.app.test_client() as client:
                response = client.get("/v1/models?refresh=1", headers={"Authorization": "Bearer red"})

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        ids = [item["id"] for item in data["data"]]
        self.assertEqual(ids, ["claude-red-devstral-medium"])
        model = data["data"][0]
        self.assertEqual(model["red"]["gateway"], "redclaudeproxy")
        self.assertEqual(model["red"]["target"], "devstral-medium-latest")
        self.assertEqual(model["context_window"], 262144)
        self.assertTrue(model["red"]["tool_call_tested"])

    def test_anthropic_tools_convert_to_openai_tools(self):
        payload = proxy.anthropic_to_openai_payload(
            {
                "model": "claude-red-devstral-medium",
                "messages": [{"role": "user", "content": "Veja o disco."}],
                "tools": [
                    {
                        "name": "get_disk",
                        "description": "Verifica disco",
                        "input_schema": {
                            "type": "object",
                            "properties": {"path": {"type": "string"}},
                            "required": ["path"],
                        },
                    }
                ],
                "tool_choice": {"type": "tool", "name": "get_disk"},
            },
            "devstral-medium-latest",
        )

        self.assertEqual(payload["model"], "devstral-medium-latest")
        self.assertEqual(payload["tools"][0]["function"]["name"], "get_disk")
        self.assertEqual(payload["tool_choice"]["function"]["name"], "get_disk")

    def test_openai_tool_call_converts_to_anthropic_tool_use(self):
        message = proxy.anthropic_response_from_openai(
            {
                "id": "chatcmpl_tool",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_disk",
                                    "type": "function",
                                    "function": {"name": "get_disk", "arguments": "{\"path\":\"C:/Projetos\"}"},
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"prompt_tokens": 11, "completion_tokens": 3},
            },
            "claude-red-devstral-medium",
        )

        self.assertEqual(message["stop_reason"], "tool_use")
        self.assertEqual(message["content"][0]["type"], "tool_use")
        self.assertEqual(message["content"][0]["name"], "get_disk")
        self.assertEqual(message["content"][0]["input"]["path"], "C:/Projetos")

    def test_anthropic_tool_result_converts_to_openai_tool_message(self):
        messages = []
        messages.extend(
            proxy.anthropic_message_to_openai(
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_disk",
                            "name": "get_disk",
                            "input": {"path": "C:/Projetos"},
                        }
                    ],
                }
            )
        )
        messages.extend(
            proxy.anthropic_message_to_openai(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_disk",
                            "content": "{\"free\":\"42G\"}",
                        }
                    ],
                }
            )
        )

        self.assertEqual(messages[0]["role"], "assistant")
        self.assertEqual(messages[0]["tool_calls"][0]["id"], "toolu_disk")
        self.assertEqual(messages[1]["role"], "tool")
        self.assertEqual(messages[1]["tool_call_id"], "toolu_disk")
        self.assertIn("42G", messages[1]["content"])

    def test_streaming_tool_call_is_anthropic_sse(self):
        class FakeStream:
            def iter_lines(self, decode_unicode=False):
                chunks = [
                    {
                        "choices": [
                            {
                                "delta": {
                                    "tool_calls": [
                                        {
                                            "index": 0,
                                            "id": "call_disk",
                                            "function": {"name": "get_disk", "arguments": "{\"path\""},
                                        }
                                    ]
                                },
                                "finish_reason": None,
                            }
                        ]
                    },
                    {
                        "choices": [
                            {
                                "delta": {"tool_calls": [{"index": 0, "function": {"arguments": ":\"C:/Projetos\"}"}}]},
                                "finish_reason": "tool_calls",
                            }
                        ]
                    },
                ]
                for chunk in chunks:
                    yield ("data: " + json.dumps(chunk)).encode("utf-8")
                yield b"data: [DONE]"

            def close(self):
                pass

        text = "".join(proxy.anthropic_sse_from_openai_stream(FakeStream(), "claude-red-devstral-medium"))
        self.assertIn('"type":"tool_use"', text)
        self.assertIn('"name":"get_disk"', text)
        self.assertIn('"partial_json":"{\\"path\\""', text)
        self.assertIn('"stop_reason":"tool_use"', text)

    def test_count_tokens_endpoint_shape(self):
        with proxy.app.test_client() as client:
            response = client.post(
                "/v1/messages/count_tokens",
                headers={"Authorization": "Bearer red"},
                json={
                    "model": "claude-red-devstral-medium",
                    "messages": [{"role": "user", "content": [{"type": "text", "text": "oi"}]}],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.get_json()["input_tokens"], 1)

    def test_unknown_claude_desktop_helper_model_falls_back_for_count_tokens(self):
        alias = proxy.resolve_claude_model("claude-3-5-haiku-latest", allow_fallback=True)
        self.assertEqual(alias["id"], "claude-red-devstral-medium")

        with proxy.app.test_client() as client:
            response = client.post(
                "/v1/messages/count_tokens",
                headers={"Authorization": "Bearer red"},
                json={
                    "model": "claude-3-5-haiku-latest",
                    "messages": [{"role": "user", "content": "web helper"}],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.get_json()["input_tokens"], 1)

    def test_unknown_helper_model_prefers_last_valid_client_model(self):
        headers = {"X-Forwarded-For": "203.0.113.10", "User-Agent": "ClaudeDesktopTest"}
        with proxy.CLAUDE_CLIENT_MODEL_LOCK:
            proxy.CLAUDE_CLIENT_LAST_ALIAS.clear()

        with proxy.app.test_request_context("/v1/messages", headers=headers):
            sonnet = proxy.resolve_claude_model("claude-red-devstral-medium")
            proxy.remember_claude_alias(sonnet)

        with proxy.app.test_request_context("/v1/messages", headers=headers):
            alias = proxy.resolve_claude_model(
                "claude-3-5-haiku-latest",
                allow_fallback=True,
                fallback_alias=proxy.last_claude_alias_for_request(),
            )

        self.assertEqual(alias["id"], "claude-red-devstral-medium")

    def test_402_key_rotates_to_next_key_without_leaking_billing_error(self):
        raw_billing_error = {
            "error": {
                "message": "Insufficient funds. Please add credits to your account: https://vercel.com/d?to=top-up",
                "type": "insufficient_funds",
            }
        }
        ok_completion = {
            "id": "chatcmpl_ok",
            "choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 1},
        }
        responses = [FakeUpstreamResponse(402, raw_billing_error), FakeUpstreamResponse(200, ok_completion)]
        seen_authorizations = []

        def fake_request(_method, _url, **kwargs):
            seen_authorizations.append(kwargs["headers"]["Authorization"])
            return responses.pop(0)

        def scenario(pool):
            with patch.object(proxy.http, "request", side_effect=fake_request):
                with proxy.app.test_client() as client:
                    response = client.post(
                        "/v1/messages",
                        headers={"Authorization": "Bearer red"},
                        json={
                            "model": "devstral-medium-latest",
                            "max_tokens": 16,
                            "messages": [{"role": "user", "content": "oi"}],
                        },
                    )

            self.assertEqual(response.status_code, 200)
            body = response.get_data(as_text=True)
            self.assertNotIn("Insufficient funds", body)
            self.assertNotIn("vercel.com", body)
            self.assertEqual(seen_authorizations, ["Bearer vck_empty", "Bearer vck_good"])
            self.assertEqual(pool.keys[0].last_status, 402)
            self.assertGreater(pool.keys[0].cooldown_until, 0)
            self.assertEqual(pool.keys[1].successes, 1)

        self.run_with_key_pool([("empty", "vck_empty"), ("good", "vck_good")], scenario)

    def test_exhausted_402_keys_return_sanitized_proxy_error(self):
        raw_billing_error = {
            "error": {
                "message": "Insufficient funds. Please add credits to your account: https://vercel.com/d?to=top-up",
                "type": "insufficient_funds",
            }
        }
        responses = [FakeUpstreamResponse(402, raw_billing_error), FakeUpstreamResponse(402, raw_billing_error)]

        def fake_request(_method, _url, **_kwargs):
            return responses.pop(0)

        def scenario(pool):
            with patch.object(proxy.http, "request", side_effect=fake_request):
                with proxy.app.test_client() as client:
                    response = client.post(
                        "/v1/messages",
                        headers={"Authorization": "Bearer red"},
                        json={
                            "model": "devstral-medium-latest",
                            "max_tokens": 16,
                            "messages": [{"role": "user", "content": "oi"}],
                        },
                    )

            self.assertEqual(response.status_code, 503)
            body = response.get_data(as_text=True)
            self.assertNotIn("Insufficient funds", body)
            self.assertNotIn("vercel.com", body)
            self.assertNotIn("rotate", body)
            data = response.get_json()
            self.assertEqual(data["error"]["type"], "redclaudeproxy_upstream_unavailable")
            self.assertEqual(data["error"]["message"], "upstream provider unavailable after internal failover")
            self.assertEqual(len(data["attempts"]), 2)
            self.assertEqual(pool.keys[0].last_status, 402)
            self.assertEqual(pool.keys[1].last_status, 402)

        self.run_with_key_pool([("empty1", "vck_empty1"), ("empty2", "vck_empty2")], scenario)


if __name__ == "__main__":
    unittest.main()

