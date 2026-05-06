import json
import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("REDPROXYPRO_KEYS", "test:vck_fake")
os.environ.setdefault("REDPROXYPRO_AUTH_TOKENS", "red")

import app as proxy  # noqa: E402


class AnthropicAdapterTest(unittest.TestCase):
    def test_models_are_curated_tool_call_passed_aliases(self):
        with proxy.app.test_client() as client:
            response = client.get("/v1/models", headers={"Authorization": "Bearer red"})

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        ids = [item["id"] for item in data["data"]]
        self.assertEqual(
            ids,
            [
                "alibaba/qwen-3.6-max-preview",
                "alibaba/qwen3.5-flash",
                "alibaba/qwen3.5-plus",
                "alibaba/qwen3.6-27b",
                "anthropic/claude-sonnet-4.5",
                "anthropic/claude-sonnet-4.6",
                "deepseek/deepseek-v4-pro",
                "google/gemini-3.1-pro-preview",
                "moonshotai/kimi-k2.5",
                "moonshotai/kimi-k2.6",
                "openai/gpt-5.4-pro",
                "openai/gpt-5.5",
                "openai/gpt-5.5-pro",
                "xai/grok-4.20-multi-agent",
                "xai/grok-4.20-reasoning",
                "xai/grok-4.3",
                "xiaomi/mimo-v2.5",
                "xiaomi/mimo-v2.5-pro",
                "zai/glm-5.1",
            ],
        )
        self.assertIn("anthropic/claude-sonnet-4.6", ids)
        self.assertIn("openai/gpt-5.5", ids)
        self.assertNotIn("anthropic/claude-opus-4.7", ids)
        self.assertTrue(next(item for item in data["data"] if item["id"] == "openai/gpt-5.5")["red"]["tool_call_tested"])
        self.assertFalse(next(item for item in data["data"] if item["id"] == "xai/grok-4.3")["red"]["tool_call_tested"])
        gpt = next(item for item in data["data"] if item["id"] == "openai/gpt-5.5")
        self.assertEqual(gpt["context_window"], 1_000_000)
        self.assertEqual(gpt["red"]["max_context_length"], 1_000_000)

    def test_anthropic_tools_convert_to_openai_tools(self):
        payload = proxy.anthropic_to_openai_payload(
            {
                "model": "claude-red-sonnet-46",
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
            "anthropic/claude-sonnet-4.6",
        )

        self.assertEqual(payload["model"], "anthropic/claude-sonnet-4.6")
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
            "claude-red-sonnet-46",
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

        text = "".join(proxy.anthropic_sse_from_openai_stream(FakeStream(), "claude-red-sonnet-46"))
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
                    "model": "claude-red-sonnet-46",
                    "messages": [{"role": "user", "content": [{"type": "text", "text": "oi"}]}],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.get_json()["input_tokens"], 1)

    def test_unknown_claude_desktop_helper_model_falls_back_for_count_tokens(self):
        alias = proxy.resolve_claude_model("claude-3-5-haiku-latest", allow_fallback=True)
        self.assertEqual(alias["id"], "openai/gpt-5.5")

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
            sonnet = proxy.resolve_claude_model("claude-red-sonnet-46")
            proxy.remember_claude_alias(sonnet)

        with proxy.app.test_request_context("/v1/messages", headers=headers):
            alias = proxy.resolve_claude_model(
                "claude-3-5-haiku-latest",
                allow_fallback=True,
                fallback_alias=proxy.last_claude_alias_for_request(),
            )

        self.assertEqual(alias["id"], "anthropic/claude-sonnet-4.6")


if __name__ == "__main__":
    unittest.main()
