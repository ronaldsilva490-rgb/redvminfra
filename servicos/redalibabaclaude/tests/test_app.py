import json
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
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


class RedAlibabaClaudeTests(unittest.TestCase):
    def test_resolve_model_accepts_raw_ids(self):
        alias = proxy.resolve_model("Qwen 3.6 Plus")
        raw = proxy.resolve_model("DeepSeek V4 Pro")
        self.assertEqual(alias["target"], "qwen3.6-plus")
        self.assertEqual(raw["id"], "DeepSeek V4 Pro")

    def test_resolve_model_accepts_legacy_aliases_without_publishing_them(self):
        legacy = proxy.resolve_model("ALI-SG/qwen3.6-plus")
        raw = proxy.resolve_model("qwen3.6-plus")
        self.assertEqual(legacy["id"], "Qwen 3.6 Plus")
        self.assertEqual(legacy["target"], "qwen3.6-plus")
        self.assertEqual(raw["id"], "Qwen 3.6 Plus")

    def test_resolve_model_maps_internal_claude_model_to_default(self):
        alias = proxy.resolve_model("claude-haiku-4-5-20251001")
        self.assertEqual(alias["id"], proxy.default_model()["id"])

    def test_clamp_max_tokens_respects_context(self):
        clamped = proxy.clamp_max_tokens(32000, 238599, 262144)
        self.assertEqual(clamped, 19449)

    def test_clamp_max_tokens_leaves_normal_requests_uncapped(self):
        clamped = proxy.clamp_max_tokens(32000, 1000, 262144)
        self.assertEqual(clamped, 32000)

    def test_apply_context_guard_caps_known_internal_tool_requests(self):
        payload = {
            "messages": [{"role": "system", "content": "You can use WebSearch for current data."}],
            "max_tokens": 32000,
        }
        guarded = proxy.apply_context_guard(payload, input_tokens=1000, context_window=262144)
        self.assertEqual(guarded["max_tokens"], 8192)

    def test_websearch_fallback_replaces_empty_client_search_tool_result(self):
        body = {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "call_search",
                            "name": "WebSearch",
                            "input": {"query": "nextjs ecommerce"},
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "call_search",
                            "content": 'Web search results for query: "nextjs ecommerce"\n\n\nREMINDER: cite sources.',
                        }
                    ],
                },
                {"role": "user", "content": "continue"},
            ]
        }
        fake_results = [{"title": "Next.js Commerce", "url": "https://example.com", "snippet": "Starter ecommerce"}]
        with patch.object(proxy, "red_search", return_value=fake_results):
            messages = proxy.anthropic_messages_to_openai(body)
        tool_messages = [item for item in messages if item["role"] == "tool"]
        self.assertEqual(len(tool_messages), 1)
        self.assertIn("RED Search/SearXNG fallback results", tool_messages[0]["content"])
        self.assertIn("https://example.com", tool_messages[0]["content"])

    def test_internal_websearch_executes_before_returning_tool_use_to_client(self):
        tool_call = FakeResponse(
            payload={
                "id": "chatcmpl_tool",
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_search",
                                    "type": "function",
                                    "function": {
                                        "name": "WebSearch",
                                        "arguments": json.dumps({"query": "nextjs ecommerce"}),
                                    },
                                }
                            ],
                        },
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            }
        )
        final = FakeResponse(
            payload={
                "id": "chatcmpl_final",
                "choices": [{"finish_reason": "stop", "message": {"content": "Usei a busca RED."}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 10},
            }
        )
        payloads = []

        def fake_proxy(payload, *, stream, api_key, base_url):
            payloads.append(payload)
            return tool_call if len(payloads) == 1 else final

        with patch.object(proxy, "proxy_openai_chat", side_effect=fake_proxy), \
             patch.object(proxy, "red_search", return_value=[{"title": "Result", "url": "https://example.com", "snippet": "Snippet"}]), \
             patch.object(proxy.POOL_BY_BACKEND["sg"], "acquire", return_value={"token": "key1"}), \
             patch.object(proxy.POOL_BY_BACKEND["sg"], "on_success", return_value=None):
            response, upstream_stream = proxy.proxy_anthropic_payload_with_internal_tools(
                {
                    "model": "qwen3.6-plus",
                    "messages": [{"role": "user", "content": "pesquise na web"}],
                    "tools": [{"type": "function", "function": {"name": "WebSearch", "parameters": {"type": "object"}}}],
                    "stream": False,
                    "max_tokens": 1024,
                },
                alias=proxy.resolve_model("Qwen 3.6 Plus"),
                stream=False,
                context_window=262144,
                input_tokens=100,
            )
        self.assertIs(response, final)
        self.assertFalse(upstream_stream)
        self.assertEqual(len(payloads), 2)
        self.assertEqual(payloads[1]["messages"][-1]["role"], "tool")
        self.assertIn("RED Search/SearXNG fallback results", payloads[1]["messages"][-1]["content"])

    def test_internal_webfetch_executes_before_returning_tool_use_to_client(self):
        tool_call = FakeResponse(
            payload={
                "id": "chatcmpl_tool",
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_fetch",
                                    "type": "function",
                                    "function": {
                                        "name": "WebFetch",
                                        "arguments": json.dumps({"url": "https://example.com", "prompt": "Resumo"}),
                                    },
                                }
                            ],
                        },
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            }
        )
        final = FakeResponse(
            payload={
                "id": "chatcmpl_final",
                "choices": [{"finish_reason": "stop", "message": {"content": "Usei o fetch RED."}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 10},
            }
        )
        payloads = []

        def fake_proxy(payload, *, stream, api_key, base_url):
            payloads.append(payload)
            return tool_call if len(payloads) == 1 else final

        with patch.object(proxy, "proxy_openai_chat", side_effect=fake_proxy), \
             patch.object(proxy, "red_fetch", return_value="WebFetch result for URL: https://example.com\n\nContent:\nOK"), \
             patch.object(proxy.POOL_BY_BACKEND["sg"], "acquire", return_value={"token": "key1"}), \
             patch.object(proxy.POOL_BY_BACKEND["sg"], "on_success", return_value=None):
            response, upstream_stream = proxy.proxy_anthropic_payload_with_internal_tools(
                {
                    "model": "qwen3.6-plus",
                    "messages": [{"role": "user", "content": "abra a fonte"}],
                    "tools": [{"type": "function", "function": {"name": "WebFetch", "parameters": {"type": "object"}}}],
                    "stream": False,
                    "max_tokens": 1024,
                },
                alias=proxy.resolve_model("Qwen 3.6 Plus"),
                stream=False,
                context_window=262144,
                input_tokens=100,
            )
        self.assertIs(response, final)
        self.assertFalse(upstream_stream)
        self.assertEqual(len(payloads), 2)
        self.assertEqual(payloads[1]["messages"][-1]["role"], "tool")
        self.assertIn("WebFetch result for URL", payloads[1]["messages"][-1]["content"])

    def test_streaming_requests_preserve_stream_for_claude_code_ui(self):
        ok = FakeResponse(lines=[b"data: [DONE]"])
        payloads = []

        def fake_proxy(payload, *, stream, api_key, base_url):
            payloads.append((payload, stream))
            return ok

        with patch.object(proxy, "WEBSEARCH_INTERNALIZE_STREAM_REQUESTS", False), \
             patch.object(proxy, "proxy_openai_chat", side_effect=fake_proxy), \
             patch.object(proxy.POOL_BY_BACKEND["sg"], "acquire", return_value={"token": "key1"}), \
             patch.object(proxy.POOL_BY_BACKEND["sg"], "on_success", return_value=None):
            response, upstream_stream = proxy.proxy_anthropic_payload_with_internal_tools(
                {
                    "model": "qwen3.6-plus",
                    "messages": [{"role": "user", "content": "oi"}],
                    "stream": True,
                    "max_tokens": 1024,
                },
                alias=proxy.resolve_model("Qwen 3.6 Plus"),
                stream=True,
                context_window=262144,
                input_tokens=100,
            )
        self.assertIs(response, ok)
        self.assertTrue(upstream_stream)
        self.assertEqual(len(payloads), 1)
        self.assertIs(payloads[0][0]["stream"], True)
        self.assertIs(payloads[0][1], True)

    def test_webfetch_fallback_replaces_failed_client_fetch_tool_result(self):
        body = {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "call_fetch",
                            "name": "WebFetch",
                            "input": {"url": "https://example.com", "prompt": "Resumo"},
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "call_fetch",
                            "content": "Error: Claude Code is unable to fetch from example.com",
                            "is_error": True,
                        }
                    ],
                },
            ]
        }
        with patch.object(proxy, "red_fetch", return_value="WebFetch result for URL: https://example.com\n\nContent:\nOK"):
            messages = proxy.anthropic_messages_to_openai(body)
        tool_messages = [item for item in messages if item["role"] == "tool"]
        self.assertEqual(len(tool_messages), 1)
        self.assertIn("WebFetch result for URL", tool_messages[0]["content"])

    def test_anthropic_payload_converts_tools_and_tool_results(self):
        body = {
            "model": "Qwen 3.6 Plus",
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
        self.assertEqual(payload["model"], "qwen3.6-plus")
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertEqual(payload["messages"][2]["tool_calls"][0]["function"]["name"], "shell")
        self.assertEqual(payload["messages"][3]["role"], "tool")
        self.assertEqual(payload["tool_choice"]["function"]["name"], "shell")

    def test_anthropic_payload_preserves_tool_result_before_followup_user_text(self):
        body = {
            "model": "Qwen 3.6 Plus",
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
        message = proxy.anthropic_message_from_openai(payload, "Qwen 3.6 Plus")
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
        text = "".join(proxy.anthropic_sse_from_openai_stream(response, "Qwen 3.6 Plus"))
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
        text = "".join(proxy.anthropic_sse_from_openai_stream(response, "Qwen 3.6 Plus"))
        self.assertIn('"type": "tool_use"', text)
        self.assertIn('"partial_json": "{\\"command\\""', text)
        self.assertIn('"stop_reason": "tool_use"', text)

    def test_stream_internal_websearch_preserves_thinking_and_continues(self):
        first = FakeResponse(
            lines=[
                b'data: {"choices":[{"delta":{"reasoning_content":"vou buscar"},"finish_reason":null}]}',
                b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_search","type":"function","function":{"name":"WebSearch","arguments":"{\\"query\\""}}]},"finish_reason":null}]}',
                b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":":\\"noticias hoje\\"}"}}]},"finish_reason":"tool_calls"}]}',
                b"data: [DONE]",
            ]
        )
        second = FakeResponse(
            lines=[
                b'data: {"choices":[{"delta":{"reasoning_content":"resultado recebido"},"finish_reason":null}]}',
                b'data: {"choices":[{"delta":{"content":"Achei fontes RED."},"finish_reason":"stop"}],"usage":{"prompt_tokens":50,"completion_tokens":8}}',
                b"data: [DONE]",
            ]
        )
        payloads = []

        def fake_proxy(payload, *, stream, api_key, base_url):
            payloads.append(payload)
            return second

        with patch.object(proxy, "EXPERIMENTAL_THINKING_BLOCKS", True), \
             patch.object(proxy, "proxy_openai_chat", side_effect=fake_proxy), \
             patch.object(proxy, "red_search", return_value=[{"title": "Fonte", "url": "https://example.com", "snippet": "Resumo"}]), \
             patch.object(proxy.POOL_BY_BACKEND["sg"], "acquire", return_value={"token": "key1"}), \
             patch.object(proxy.POOL_BY_BACKEND["sg"], "on_success", return_value=None):
            text = "".join(
                proxy.anthropic_sse_from_openai_stream_with_internal_tools(
                    first,
                    payload={
                        "model": "qwen3.6-plus",
                        "messages": [{"role": "user", "content": "pesquise"}],
                        "tools": [{"type": "function", "function": {"name": "WebSearch", "parameters": {"type": "object"}}}],
                        "stream": True,
                        "max_tokens": 1024,
                    },
                    alias=proxy.resolve_model("Qwen 3.6 Plus"),
                    model_name="Qwen 3.6 Plus",
                    context_window=262144,
                    input_tokens=100,
                )
            )
        self.assertIn('"type": "thinking_delta"', text)
        self.assertIn("Achei fontes RED.", text)
        self.assertIn('"stop_reason": "end_turn"', text)
        self.assertNotIn('"name": "WebSearch"', text)
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["messages"][-1]["role"], "tool")
        self.assertIn("RED Search/SearXNG fallback results", payloads[0]["messages"][-1]["content"])

    def test_detects_missing_required_tool_arguments(self):
        payload = {
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "Write",
                        "parameters": {
                            "type": "object",
                            "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}},
                            "required": ["file_path", "content"],
                        },
                    },
                }
            ]
        }
        data = {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "tool_calls": [
                            {
                                "id": "call_write",
                                "type": "function",
                                "function": {"name": "Write", "arguments": "{}"},
                            }
                        ]
                    },
                }
            ]
        }
        invalids = proxy.invalid_tool_calls_from_openai(data, payload)
        self.assertEqual(len(invalids), 1)
        self.assertEqual(invalids[0]["name"], "Write")
        self.assertEqual(invalids[0]["missing"], ["file_path", "content"])

    def test_stream_tool_repair_retries_empty_write_before_client_tool_use(self):
        first = FakeResponse(
            lines=[
                b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_write","type":"function","function":{"name":"Write","arguments":"{}"}}]},"finish_reason":"tool_calls"}]}',
                b"data: [DONE]",
            ]
        )
        second = FakeResponse(
            lines=[
                b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_write2","type":"function","function":{"name":"Write","arguments":"{\\"file_path\\":\\"portfolio.html\\",\\"content\\":\\"ok\\"}"}}]},"finish_reason":"tool_calls"}]}',
                b"data: [DONE]",
            ]
        )
        repaired_payloads = []

        def fake_retry(payload, *, alias, stream, context_window, input_tokens):
            repaired_payloads.append(json.loads(json.dumps(payload)))
            return second

        with patch.object(proxy, "LIVE_EXTERNAL_TOOL_STREAMING", False), \
             patch.object(proxy, "TOOL_REPAIR_MAX_ROUNDS", 2), \
             patch.object(proxy, "proxy_openai_chat_with_context_retry", side_effect=fake_retry):
            text = "".join(
                proxy.anthropic_sse_from_openai_stream_with_internal_tools(
                    first,
                    payload={
                        "model": "qwen3.6-plus",
                        "messages": [{"role": "user", "content": "crie um arquivo"}],
                        "tools": [
                            {
                                "type": "function",
                                "function": {
                                    "name": "Write",
                                    "parameters": {
                                        "type": "object",
                                        "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}},
                                        "required": ["file_path", "content"],
                                    },
                                },
                            }
                        ],
                        "stream": True,
                        "max_tokens": 1024,
                    },
                    alias=proxy.resolve_model("Qwen 3.6 Plus"),
                    model_name="Qwen 3.6 Plus",
                    context_window=262144,
                    input_tokens=100,
                )
            )
        self.assertEqual(len(repaired_payloads), 1)
        self.assertEqual(repaired_payloads[0]["messages"][-1]["role"], "tool")
        self.assertIn("missing required fields", repaired_payloads[0]["messages"][-1]["content"])
        self.assertNotIn('"partial_json": "{}"', text)
        self.assertIn('\\"file_path\\":\\"portfolio.html\\"', text)
        self.assertIn('"stop_reason": "tool_use"', text)

    def test_stream_tool_repair_handles_truncated_json_without_tool_result_history(self):
        first = FakeResponse(
            lines=[
                b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_write","type":"function","function":{"name":"Write","arguments":"{\\"file_path\\""}}]},"finish_reason":"stop"}]}',
                b"data: [DONE]",
            ]
        )
        second = FakeResponse(
            lines=[
                b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_write2","type":"function","function":{"name":"Write","arguments":"{\\"file_path\\":\\"landing.html\\",\\"content\\":\\"ok\\"}"}}]},"finish_reason":"tool_calls"}]}',
                b"data: [DONE]",
            ]
        )
        repaired_payloads = []

        def fake_retry(payload, *, alias, stream, context_window, input_tokens):
            repaired_payloads.append(json.loads(json.dumps(payload)))
            return second

        with patch.object(proxy, "LIVE_EXTERNAL_TOOL_STREAMING", False), \
             patch.object(proxy, "TOOL_REPAIR_MAX_ROUNDS", 2), \
             patch.object(proxy, "proxy_openai_chat_with_context_retry", side_effect=fake_retry):
            text = "".join(
                proxy.anthropic_sse_from_openai_stream_with_internal_tools(
                    first,
                    payload={
                        "model": "qwen3.6-plus",
                        "messages": [{"role": "user", "content": "crie uma landing page"}],
                        "tools": [
                            {
                                "type": "function",
                                "function": {
                                    "name": "Write",
                                    "parameters": {
                                        "type": "object",
                                        "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}},
                                        "required": ["file_path", "content"],
                                    },
                                },
                            }
                        ],
                        "stream": True,
                        "max_tokens": 1024,
                    },
                    alias=proxy.resolve_model("Qwen 3.6 Plus"),
                    model_name="Qwen 3.6 Plus",
                    context_window=262144,
                    input_tokens=100,
                )
            )
        self.assertEqual(len(repaired_payloads), 1)
        self.assertEqual(repaired_payloads[0]["messages"][-1]["role"], "user")
        self.assertIn("incomplete or invalid JSON", repaired_payloads[0]["messages"][-1]["content"])
        self.assertNotEqual(repaired_payloads[0]["messages"][-1]["role"], "tool")
        self.assertIn('\\"file_path\\"', text)
        self.assertIn(':\\"landing.html\\",\\"content\\":\\"ok\\"}', text)
        self.assertIn('"stop_reason": "tool_use"', text)

    def test_stream_external_write_tool_emits_input_json_deltas_live(self):
        response = FakeResponse(
            lines=[
                b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_write","type":"function","function":{"name":"Write","arguments":"{\\"file_path\\""}}]},"finish_reason":null}]}',
                b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":":\\"hello.html\\",\\"content\\":\\"<h1>"}}]},"finish_reason":null}]}',
                b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"Oi</h1>\\"}"}}]},"finish_reason":"tool_calls"}]}',
                b"data: [DONE]",
            ]
        )
        events = list(
            proxy.anthropic_sse_from_openai_stream_with_internal_tools(
                response,
                payload={
                    "model": "qwen3.6-plus",
                    "messages": [{"role": "user", "content": "crie uma pagina"}],
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "Write",
                                "parameters": {
                                    "type": "object",
                                    "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}},
                                    "required": ["file_path", "content"],
                                },
                            },
                        }
                    ],
                    "stream": True,
                    "max_tokens": 1024,
                },
                alias=proxy.resolve_model("Qwen 3.6 Plus"),
                model_name="Qwen 3.6 Plus",
                context_window=262144,
                input_tokens=100,
            )
        )
        text = "".join(events)
        self.assertIn('"content_block": {"type": "tool_use", "id": "call_write", "name": "Write", "input": {}}', text)
        self.assertIn('"partial_json": "{\\"file_path\\""', text)
        self.assertIn('"partial_json": ":\\"hello.html\\",\\"content\\":\\"<h1>"', text)
        self.assertIn('"partial_json": "Oi</h1>\\"}"', text)
        self.assertLess(
            text.index('"partial_json": "{\\"file_path\\""'),
            text.index('"partial_json": ":\\"hello.html\\",\\"content\\":\\"<h1>"'),
        )
        self.assertIn('"stop_reason": "tool_use"', text)

    def test_stream_thinking_only_retries_before_empty_success(self):
        first = FakeResponse(
            lines=[
                b'data: {"choices":[{"delta":{"reasoning_content":"vou criar, mas ainda nao chamei ferramenta"},"finish_reason":null}]}',
                b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
                b"data: [DONE]",
            ]
        )
        second = FakeResponse(
            lines=[
                b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_write","type":"function","function":{"name":"Write","arguments":"{\\"file_path\\":\\"portfolio.html\\",\\"content\\":\\"ok\\"}"}}]},"finish_reason":"tool_calls"}]}',
                b"data: [DONE]",
            ]
        )
        repaired_payloads = []

        def fake_retry(payload, *, alias, stream, context_window, input_tokens):
            repaired_payloads.append(json.loads(json.dumps(payload)))
            return second

        with patch.object(proxy, "EXPERIMENTAL_THINKING_BLOCKS", True), \
             patch.object(proxy, "EMPTY_OUTPUT_REPAIR_MAX_ROUNDS", 2), \
             patch.object(proxy, "proxy_openai_chat_with_context_retry", side_effect=fake_retry):
            text = "".join(
                proxy.anthropic_sse_from_openai_stream_with_internal_tools(
                    first,
                    payload={
                        "model": "qwen3.6-plus",
                        "messages": [{"role": "user", "content": "crie outro portfolio"}],
                        "tools": [
                            {
                                "type": "function",
                                "function": {
                                    "name": "Write",
                                    "parameters": {
                                        "type": "object",
                                        "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}},
                                        "required": ["file_path", "content"],
                                    },
                                },
                            }
                        ],
                        "stream": True,
                        "max_tokens": 1024,
                    },
                    alias=proxy.resolve_model("Qwen 3.6 Plus"),
                    model_name="Qwen 3.6 Plus",
                    context_window=262144,
                    input_tokens=100,
                )
            )
        self.assertEqual(len(repaired_payloads), 1)
        self.assertEqual(repaired_payloads[0]["messages"][-1]["role"], "user")
        self.assertIn("produced only hidden reasoning", repaired_payloads[0]["messages"][-1]["content"])
        self.assertIn('"type": "thinking_delta"', text)
        self.assertIn('\\"file_path\\":\\"portfolio.html\\"', text)
        self.assertIn('"stop_reason": "tool_use"', text)

    def test_stream_thinking_only_repair_failure_is_visible(self):
        first = FakeResponse(
            lines=[
                b'data: {"choices":[{"delta":{"reasoning_content":"planejei, mas nao entreguei"},"finish_reason":"tool_calls"}]}',
                b"data: [DONE]",
            ]
        )
        failed = FakeResponse(status_code=400, payload={"error": {"message": "context too large"}})

        with patch.object(proxy, "EXPERIMENTAL_THINKING_BLOCKS", True), \
             patch.object(proxy, "EMPTY_OUTPUT_REPAIR_MAX_ROUNDS", 2), \
             patch.object(proxy, "proxy_openai_chat_with_context_retry", return_value=failed):
            text = "".join(
                proxy.anthropic_sse_from_openai_stream_with_internal_tools(
                    first,
                    payload={
                        "model": "qwen3.6-plus",
                        "messages": [{"role": "user", "content": "crie outro portfolio"}],
                        "tools": [
                            {
                                "type": "function",
                                "function": {
                                    "name": "Write",
                                    "parameters": {
                                        "type": "object",
                                        "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}},
                                        "required": ["file_path", "content"],
                                    },
                                },
                            }
                        ],
                        "stream": True,
                        "max_tokens": 1024,
                    },
                    alias=proxy.resolve_model("Qwen 3.6 Plus"),
                    model_name="Qwen 3.6 Plus",
                    context_window=262144,
                    input_tokens=100,
                )
            )
        self.assertIn('"type": "thinking_delta"', text)
        self.assertIn("O proxy bloqueou a conclusao silenciosa", text)
        self.assertIn("Upstream status: 400", text)
        self.assertIn('"stop_reason": "end_turn"', text)

    def test_stream_todo_only_completion_retries_until_write_tool(self):
        first = FakeResponse(
            lines=[
                b'data: {"choices":[{"delta":{"content":"Vou criar a landing page agora."},"finish_reason":"stop"}]}',
                b"data: [DONE]",
            ]
        )
        second = FakeResponse(
            lines=[
                b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_write","type":"function","function":{"name":"Write","arguments":"{\\"file_path\\":\\"portfolio.html\\",\\"content\\":\\"ok\\"}"}}]},"finish_reason":"tool_calls"}]}',
                b"data: [DONE]",
            ]
        )
        repaired_payloads = []

        def fake_retry(payload, *, alias, stream, context_window, input_tokens):
            repaired_payloads.append(json.loads(json.dumps(payload)))
            return second

        with patch.object(proxy, "TODO_ONLY_REPAIR_MAX_ROUNDS", 1), \
             patch.object(proxy, "proxy_openai_chat_with_context_retry", side_effect=fake_retry):
            text = "".join(
                proxy.anthropic_sse_from_openai_stream_with_internal_tools(
                    first,
                    payload={
                        "model": "qwen3.6-plus",
                        "messages": [
                            {"role": "user", "content": "crie uma landing page moderna para portfolio de desenvolvedor"},
                            {
                                "role": "assistant",
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "call_todo",
                                        "type": "function",
                                        "function": {
                                            "name": "TodoWrite",
                                            "arguments": '{"items":[{"content":"criar landing page","status":"in_progress","priority":"high"}]}',
                                        },
                                    }
                                ],
                            },
                            {"role": "tool", "tool_call_id": "call_todo", "content": "lista de tarefas atualizada"},
                        ],
                        "tools": [
                            {"type": "function", "function": {"name": "TodoWrite", "parameters": {"type": "object"}}},
                            {
                                "type": "function",
                                "function": {
                                    "name": "Write",
                                    "parameters": {
                                        "type": "object",
                                        "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}},
                                        "required": ["file_path", "content"],
                                    },
                                },
                            },
                        ],
                        "stream": True,
                        "max_tokens": 1024,
                    },
                    alias=proxy.resolve_model("Qwen 3.6 Plus"),
                    model_name="Qwen 3.6 Plus",
                    context_window=262144,
                    input_tokens=100,
                )
            )
        self.assertEqual(len(repaired_payloads), 1)
        self.assertEqual(repaired_payloads[0]["messages"][-2]["role"], "assistant")
        self.assertIn("Vou criar a landing page agora.", repaired_payloads[0]["messages"][-2]["content"])
        self.assertEqual(repaired_payloads[0]["messages"][-1]["role"], "user")
        self.assertIn("did not actually execute a non-todo workspace action", repaired_payloads[0]["messages"][-1]["content"])
        self.assertIn("Vou criar a landing page agora.", text)
        self.assertIn('\\"file_path\\":\\"portfolio.html\\"', text)
        self.assertIn('"stop_reason": "tool_use"', text)

    def test_stream_plan_only_workspace_request_retries_until_write_tool(self):
        first = FakeResponse(
            lines=[
                b'data: {"choices":[{"delta":{"reasoning_content":"vou montar o html completo"},"finish_reason":null}]}',
                b'data: {"choices":[{"delta":{"content":"Vou criar uma landing page impressionante.\\n\\n"},"finish_reason":"stop"}]}',
                b"data: [DONE]",
            ]
        )
        second = FakeResponse(
            lines=[
                b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_write","type":"function","function":{"name":"Write","arguments":"{\\"file_path\\":\\"landing.html\\",\\"content\\":\\"ok\\"}"}}]},"finish_reason":"tool_calls"}]}',
                b"data: [DONE]",
            ]
        )
        repaired_payloads = []

        def fake_retry(payload, *, alias, stream, context_window, input_tokens):
            repaired_payloads.append(json.loads(json.dumps(payload)))
            return second

        with patch.object(proxy, "EXPERIMENTAL_THINKING_BLOCKS", True), \
             patch.object(proxy, "WORKSPACE_ACTION_REPAIR_MAX_ROUNDS", 1), \
             patch.object(proxy, "proxy_openai_chat_with_context_retry", side_effect=fake_retry):
            text = "".join(
                proxy.anthropic_sse_from_openai_stream_with_internal_tools(
                    first,
                    payload={
                        "model": "qwen3.6-plus",
                        "messages": [{"role": "user", "content": "quero que voce crie uma super landing page linda para portfolio de desenvolvedor"}],
                        "tools": [
                            {
                                "type": "function",
                                "function": {
                                    "name": "Write",
                                    "parameters": {
                                        "type": "object",
                                        "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}},
                                        "required": ["file_path", "content"],
                                    },
                                },
                            },
                        ],
                        "stream": True,
                        "max_tokens": 1024,
                    },
                    alias=proxy.resolve_model("Qwen 3.6 Plus"),
                    model_name="Qwen 3.6 Plus",
                    context_window=262144,
                    input_tokens=100,
                )
            )
        self.assertEqual(len(repaired_payloads), 1)
        self.assertEqual(repaired_payloads[0]["messages"][-2]["role"], "assistant")
        self.assertIn("Vou criar uma landing page impressionante.", repaired_payloads[0]["messages"][-2]["content"])
        self.assertEqual(repaired_payloads[0]["messages"][-1]["role"], "user")
        self.assertIn("did not execute any workspace tool", repaired_payloads[0]["messages"][-1]["content"])
        self.assertIn('"type": "thinking_delta"', text)
        self.assertIn("Vou criar uma landing page impressionante.", text)
        self.assertIn('\\"file_path\\"', text)
        self.assertIn(':\\"landing.html\\",\\"content\\":\\"ok\\"}', text)
        self.assertIn('"stop_reason": "tool_use"', text)

    def test_stream_tool_state_with_stop_finish_still_emits_tool_use(self):
        first = FakeResponse(
            lines=[
                b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_write","type":"function","function":{"name":"Write","arguments":"{\\"file_path\\""}}]},"finish_reason":null}]}',
                b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":":\\"landing.html\\",\\"content\\":\\"ok\\"}"}}]},"finish_reason":"stop"}]}',
                b"data: [DONE]",
            ]
        )
        text = "".join(
            proxy.anthropic_sse_from_openai_stream_with_internal_tools(
                first,
                payload={
                    "model": "qwen3.6-plus",
                    "messages": [{"role": "user", "content": "crie uma landing page"}],
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "Write",
                                "parameters": {
                                    "type": "object",
                                    "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}},
                                    "required": ["file_path", "content"],
                                },
                            },
                        }
                    ],
                    "stream": True,
                    "max_tokens": 1024,
                },
                alias=proxy.resolve_model("Qwen 3.6 Plus"),
                model_name="Qwen 3.6 Plus",
                context_window=262144,
                input_tokens=100,
            )
        )
        self.assertIn('"type": "tool_use"', text)
        self.assertIn('\\"file_path\\"', text)
        self.assertIn(':\\"landing.html\\",\\"content\\":\\"ok\\"}', text)
        self.assertIn('"stop_reason": "tool_use"', text)

    def test_workspace_action_contract_is_injected_for_artifact_requests(self):
        payload = proxy.anthropic_to_openai_payload(
            {
                "model": "Qwen 3.6 Plus",
                "messages": [{"role": "user", "content": "crie uma landing page em HTML"}],
                "tools": [
                    {
                        "name": "Write",
                        "input_schema": {
                            "type": "object",
                            "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}},
                            "required": ["file_path", "content"],
                        },
                    }
                ],
                "stream": True,
                "max_tokens": 1024,
            },
            proxy.resolve_model("Qwen 3.6 Plus"),
        )
        system_messages = [item["content"] for item in payload["messages"] if item.get("role") == "system"]
        self.assertTrue(any("Workspace action contract" in item for item in system_messages))

    def test_workspace_action_contract_is_not_injected_for_greetings(self):
        payload = proxy.anthropic_to_openai_payload(
            {
                "model": "Qwen 3.6 Plus",
                "messages": [{"role": "user", "content": "oi"}],
                "tools": [
                    {
                        "name": "Write",
                        "input_schema": {
                            "type": "object",
                            "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}},
                            "required": ["file_path", "content"],
                        },
                    }
                ],
                "stream": True,
                "max_tokens": 1024,
            },
            proxy.resolve_model("Qwen 3.6 Plus"),
        )
        system_messages = [item["content"] for item in payload["messages"] if item.get("role") == "system"]
        self.assertFalse(any("Workspace action contract" in item for item in system_messages))
        self.assertFalse(proxy.request_likely_requires_workspace_action(payload))

    def test_stream_greeting_does_not_trigger_workspace_action_repair(self):
        first = FakeResponse(
            lines=[
                b'data: {"choices":[{"delta":{"reasoning_content":"cumprimento simples"},"finish_reason":null}]}',
                b'data: {"choices":[{"delta":{"content":"Oi! Como posso ajudar?"},"finish_reason":"stop"}]}',
                b"data: [DONE]",
            ]
        )
        with patch.object(proxy, "WORKSPACE_ACTION_REPAIR_MAX_ROUNDS", 2), \
             patch.object(proxy, "proxy_openai_chat_with_context_retry") as fake_retry:
            text = "".join(
                proxy.anthropic_sse_from_openai_stream_with_internal_tools(
                    first,
                    payload={
                        "model": "qwen3.6-plus",
                        "messages": [{"role": "user", "content": "oi"}],
                        "tools": [
                            {
                                "type": "function",
                                "function": {
                                    "name": "Write",
                                    "parameters": {
                                        "type": "object",
                                        "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}},
                                        "required": ["file_path", "content"],
                                    },
                                },
                            }
                        ],
                        "stream": True,
                        "max_tokens": 1024,
                    },
                    alias=proxy.resolve_model("Qwen 3.6 Plus"),
                    model_name="Qwen 3.6 Plus",
                    context_window=262144,
                    input_tokens=100,
                )
            )
        fake_retry.assert_not_called()
        self.assertIn("Oi! Como posso ajudar?", text)
        self.assertNotIn("workspace", text.lower())
        self.assertNotIn("entrega concreta", text)

    def test_json_to_sse_tool_use_emits_input_delta(self):
        payload = {
            "id": "chatcmpl_json_tool",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "tool_calls": [
                            {
                                "id": "call_search",
                                "type": "function",
                                "function": {
                                    "name": "WebSearch",
                                    "arguments": json.dumps({"query": "nextjs ecommerce"}),
                                },
                            }
                        ]
                    },
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        text = "".join(proxy.anthropic_sse_from_openai_json(payload, "Qwen 3.6 Plus"))
        self.assertIn('"content_block": {"type": "tool_use", "id": "call_search", "name": "WebSearch", "input": {}}', text)
        self.assertIn('"type": "input_json_delta"', text)
        self.assertIn('\\"query\\": \\"nextjs ecommerce\\"', text)

    def test_models_endpoint_requires_auth(self):
        with proxy.app.test_client() as client:
            response = client.get("/v1/models")
        self.assertEqual(response.status_code, 401)

    def test_auth_401_logs_masked_probe_summary(self):
        with proxy.app.test_client() as client, io.StringIO() as buffer, redirect_stdout(buffer):
            response = client.post(
                "/v1/messages?beta=true",
                headers={
                    "Authorization": "Bearer wrong-secret-token",
                    "Anthropic-Version": "2023-06-01",
                    "Anthropic-Beta": "tools-2024-04-04",
                    "User-Agent": "Claude-Desktop-Test",
                },
                json={},
            )
            output = buffer.getvalue()
        self.assertEqual(response.status_code, 401)
        self.assertIn("[redalibabaclaude] auth-401 ", output)
        self.assertIn('"authorization_scheme": "bearer"', output)
        self.assertIn('"has_authorization": true', output)
        self.assertIn('wro...n(len=18)', output)
        self.assertNotIn("wrong-secret-token", output)

    def test_models_endpoint_lists_curated_models(self):
        with proxy.app.test_client() as client:
            response = client.get("/v1/models", headers={"Authorization": "Bearer red"})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        ids = [item["id"] for item in data["data"]]
        self.assertIn("Qwen 3.6 Plus", ids)
        self.assertIn("DeepSeek V4 Pro", ids)
        self.assertNotIn("ALI-SG/qwen3.6-plus", ids)

    def test_messages_endpoint_forwards_to_alibaba(self):
        fake = FakeResponse(
            payload={
                "id": "chatcmpl_1",
                "choices": [{"finish_reason": "stop", "message": {"content": "OK"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            }
        )
        with patch.object(proxy, "proxy_openai_chat", return_value=fake), patch.object(proxy.POOL_BY_BACKEND["sg"], "has_keys", return_value=True), patch.object(proxy.POOL_BY_BACKEND["sg"], "acquire", return_value={"token": "fake"}), patch.object(proxy.POOL_BY_BACKEND["sg"], "on_success", return_value=None):
            with proxy.app.test_client() as client:
                response = client.post(
                    "/v1/messages",
                    headers={"Authorization": "Bearer red"},
                    json={"model": "Qwen 3.6 Plus", "messages": [{"role": "user", "content": "oi"}]},
                )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["model"], "Qwen 3.6 Plus")
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

        def fake_proxy(payload, *, stream, api_key, base_url):
            calls.append(api_key)
            return limited if api_key == "key1" else ok

        with patch.object(proxy, "proxy_openai_chat", side_effect=fake_proxy), \
             patch.object(proxy.POOL_BY_BACKEND["sg"], "acquire", side_effect=fake_acquire), \
             patch.object(proxy.POOL_BY_BACKEND["sg"], "on_429", return_value=None) as on_429, \
             patch.object(proxy.POOL_BY_BACKEND["sg"], "on_success", return_value=None) as on_success:
            response = proxy.proxy_openai_chat_with_context_retry(
                {"model": "Qwen 3.6 Plus", "messages": [{"role": "user", "content": "oi"}], "max_tokens": 64},
                alias=proxy.resolve_model("Qwen 3.6 Plus"),
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

        def fake_proxy(payload, *, stream, api_key, base_url):
            calls.append(api_key)
            return broken if api_key == "key1" else ok

        with patch.object(proxy, "proxy_openai_chat", side_effect=fake_proxy), \
             patch.object(proxy.POOL_BY_BACKEND["sg"], "acquire", side_effect=fake_acquire), \
             patch.object(proxy.POOL_BY_BACKEND["sg"], "on_5xx", return_value=None) as on_5xx, \
             patch.object(proxy.POOL_BY_BACKEND["sg"], "on_success", return_value=None) as on_success:
            response = proxy.proxy_openai_chat_with_context_retry(
                {"model": "Qwen 3.6 Plus", "messages": [{"role": "user", "content": "oi"}], "max_tokens": 64},
                alias=proxy.resolve_model("Qwen 3.6 Plus"),
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
                    "message": "This model's maximum context length is 262144 tokens. However, you requested 8192 output tokens and your prompt contains at least 252000 input tokens, for a total of at least 260192 tokens. Please reduce the length of the messages.",
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

        def fake_proxy(payload, *, stream, api_key, base_url):
            calls.append(payload["max_tokens"])
            return too_long if len(calls) == 1 else ok

        with patch.object(proxy, "proxy_openai_chat", side_effect=fake_proxy), \
             patch.object(proxy.POOL_BY_BACKEND["sg"], "acquire", return_value={"token": "key1"}), \
             patch.object(proxy.POOL_BY_BACKEND["sg"], "on_success", return_value=None):
            response = proxy.proxy_openai_chat_with_context_retry(
                {"model": "Qwen 3.6 Plus", "messages": [{"role": "user", "content": "oi"}], "max_tokens": 23546},
                alias=proxy.resolve_model("Qwen 3.6 Plus"),
                stream=False,
                context_window=262144,
                input_tokens=238599,
            )
        self.assertIs(response, ok)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], 19449)
        self.assertEqual(calls[1], 4000)

    def test_max_tokens_range_error_retries_with_upstream_limit(self):
        too_many = FakeResponse(
            status_code=400,
            payload={
                "error": {
                    "message": "<400> InternalError.Algo.InvalidParameter: Range of max_tokens should be [1, 8192]",
                    "type": "upstream_error",
                }
            },
        )
        ok = FakeResponse(
            payload={
                "id": "chatcmpl_5",
                "choices": [{"finish_reason": "stop", "message": {"content": "OK"}}],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 12},
            }
        )
        calls = []

        def fake_proxy(payload, *, stream, api_key, base_url):
            calls.append(payload["max_tokens"])
            return too_many if len(calls) == 1 else ok

        with patch.object(proxy, "proxy_openai_chat", side_effect=fake_proxy), \
             patch.object(proxy.POOL_BY_BACKEND["sg"], "acquire", return_value={"token": "key1"}), \
             patch.object(proxy.POOL_BY_BACKEND["sg"], "on_success", return_value=None):
            response = proxy.proxy_openai_chat_with_context_retry(
                {"model": "Qwen 3.6 Plus", "messages": [{"role": "user", "content": "oi"}], "max_tokens": 32000},
                alias=proxy.resolve_model("Qwen 3.6 Plus"),
                stream=False,
                context_window=262144,
                input_tokens=1000,
            )
        self.assertIs(response, ok)
        self.assertEqual(calls, [32000, 8192])

    def test_openai_sanitize_removes_reasoning_content(self):
        payload = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "OK",
                        "reasoning_content": "hidden",
                    }
                }
            ]
        }
        cleaned = proxy.sanitize_openai_response_json(payload)
        self.assertEqual(cleaned["choices"][0]["message"]["content"], "OK")
        self.assertNotIn("reasoning_content", cleaned["choices"][0]["message"])

    def test_effort_max_enables_thinking_and_overrides_alias_default(self):
        body = {
            "model": "Qwen 3.6 Plus",
            "messages": [{"role": "user", "content": "oi"}],
            "output_config": {"effort": "max"},
            "thinking": {"type": "adaptive"},
        }
        payload = proxy.anthropic_to_openai_payload(body, proxy.resolve_model(body["model"]))
        merged = proxy.apply_alias_backend_options(payload, proxy.resolve_model(body["model"]))
        self.assertIs(merged["enable_thinking"], True)

    def test_forced_tool_choice_is_removed_when_thinking_is_enabled(self):
        body = {
            "model": "Qwen 3.6 Plus",
            "messages": [{"role": "user", "content": "pesquise"}],
            "tools": [
                {
                    "name": "WebSearch",
                    "description": "Search",
                    "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
                }
            ],
            "tool_choice": {"type": "tool", "name": "WebSearch"},
            "thinking": {"type": "adaptive"},
        }
        payload = proxy.anthropic_to_openai_payload(body, proxy.resolve_model(body["model"]))
        merged = proxy.apply_alias_backend_options(payload, proxy.resolve_model(body["model"]))
        self.assertIs(merged["enable_thinking"], True)
        self.assertNotIn("tool_choice", merged)

    def test_anthropic_payload_forces_thinking_even_without_effort(self):
        body = {
            "model": "Qwen 3.6 Plus",
            "messages": [{"role": "user", "content": "oi"}],
        }
        with patch.object(proxy, "FORCE_ANTHROPIC_THINKING", True):
            payload = proxy.anthropic_to_openai_payload(body, proxy.resolve_model(body["model"]))
        merged = proxy.apply_alias_backend_options(payload, proxy.resolve_model(body["model"]))
        self.assertIs(merged["enable_thinking"], True)

    def test_stream_conversion_can_emit_experimental_thinking_block(self):
        lines = [
            b'data: {"choices":[{"delta":{"reasoning_content":"pensei "},"finish_reason":null}]}',
            b'data: {"choices":[{"delta":{"reasoning_content":"nisso"},"finish_reason":null}]}',
            b'data: {"choices":[{"delta":{"content":"OK"},"finish_reason":"stop"}]}',
            b"data: [DONE]",
        ]
        response = FakeResponse(lines=lines)
        with patch.object(proxy, "EXPERIMENTAL_THINKING_BLOCKS", True):
            text = "".join(proxy.anthropic_sse_from_openai_stream(response, "Qwen 3.6 Plus"))
        self.assertIn('"type": "thinking"', text)
        self.assertIn('"type": "thinking_delta"', text)
        self.assertIn('"type": "signature_delta"', text)
        self.assertIn('"type": "text_delta"', text)
        self.assertIn('"index": 1', text)

    def test_json_sse_conversion_can_emit_experimental_thinking_block(self):
        data = {
            "id": "chatcmpl_test",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "reasoning_content": "analise interna",
                        "content": "OK",
                    },
                    "finish_reason": "stop",
                }
            ],
        }
        with patch.object(proxy, "EXPERIMENTAL_THINKING_BLOCKS", True):
            text = "".join(proxy.anthropic_sse_from_openai_json(data, "Qwen 3.6 Plus"))
        self.assertIn('"type": "thinking"', text)
        self.assertIn('"type": "thinking_delta"', text)
        self.assertIn('"type": "signature_delta"', text)
        self.assertIn('"index": 1', text)
        self.assertIn('"type": "text_delta"', text)

    def test_anthropic_message_preserves_reasoning_content_when_experimental(self):
        data = {
            "id": "chatcmpl_test",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "reasoning_content": "analise interna",
                        "content": "OK",
                    },
                    "finish_reason": "stop",
                }
            ],
        }
        with patch.object(proxy, "EXPERIMENTAL_THINKING_BLOCKS", True):
            message = proxy.anthropic_message_from_openai(data, "Qwen 3.6 Plus")
        self.assertEqual(message["content"][0]["type"], "thinking")
        self.assertEqual(message["content"][1]["type"], "text")

    def test_token_metrics_store_records_sqlite_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = proxy.TokenMetricsStore(
                enabled=True,
                db_path=Path(tmp) / "token_usage.sqlite3",
                queue_size=10,
            )
            store.record(
                {
                    "ts": 1778200000.0,
                    "request_id": "req_test",
                    "endpoint": "/v1/messages",
                    "client_ip": "127.0.0.1",
                    "model": "Qwen 3.6 Plus",
                    "provider": "alibaba",
                    "backend": "sg",
                    "target": "qwen3.6-plus",
                    "status_code": 200,
                    "success": True,
                    "stream": True,
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "total_tokens": 15,
                    "input_estimated": False,
                    "output_estimated": False,
                    "duration_ms": 123,
                    "stop_reason": "end_turn",
                    "error_type": "",
                }
            )
            store.flush()
            summary = store.summary()
            store.close()
        self.assertTrue(summary["enabled"])
        self.assertEqual(summary["summary"]["requests"], 1)
        self.assertEqual(summary["summary"]["input_tokens"], 10)
        self.assertEqual(summary["summary"]["output_tokens"], 5)
        self.assertEqual(summary["summary"]["total_tokens"], 15)
        self.assertEqual(summary["models"][0]["model"], "Qwen 3.6 Plus")

    def test_record_token_usage_uses_estimates_when_usage_is_missing(self):
        events = []
        context = {
            "ts": 1778200000.0,
            "request_id": "req_test",
            "endpoint": "/v1/chat/completions",
            "client_ip": "127.0.0.1",
            "model": "Qwen 3.6 Plus",
            "provider": "alibaba",
            "backend": "sg",
            "target": "qwen3.6-plus",
            "stream": False,
            "input_tokens_estimate": 12,
            "started_at": 1778199999.0,
        }
        with patch.object(proxy.token_metrics_store, "record", side_effect=events.append):
            proxy.record_token_usage(context, usage={}, output_tokens_estimate=4, stop_reason="end_turn")
        self.assertEqual(events[0]["input_tokens"], 12)
        self.assertEqual(events[0]["output_tokens"], 4)
        self.assertTrue(events[0]["input_estimated"])
        self.assertTrue(events[0]["output_estimated"])

    def test_admin_tokens_endpoint_returns_metrics_payload(self):
        with proxy.app.test_client() as client:
            with patch.object(
                proxy.token_metrics_store,
                "summary",
                return_value={
                    "enabled": True,
                    "db_path": "/tmp/token_usage.sqlite3",
                    "queue_depth": 0,
                    "dropped_events": 0,
                    "last_error": "",
                    "summary": {"requests": 1, "input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
                    "models": [],
                    "endpoints": [],
                    "recent": [],
                    "timeseries": [],
                },
            ):
                response = client.get("/admin/tokens", headers={"Authorization": "Bearer red"})
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["service"], "redalibabaclaude")
        self.assertEqual(body["summary"]["total_tokens"], 15)

    def test_anthropic_stream_records_token_usage_once(self):
        lines = [
            b'data: {"choices":[{"delta":{"content":"Oi"},"finish_reason":null}]}',
            b'data: {"choices":[],"usage":{"prompt_tokens":7,"completion_tokens":3,"total_tokens":10}}',
            b"data: [DONE]",
        ]
        context = {
            "ts": 1778200000.0,
            "request_id": "req_stream",
            "endpoint": "/v1/messages",
            "client_ip": "127.0.0.1",
            "model": "Qwen 3.6 Plus",
            "provider": "alibaba",
            "backend": "sg",
            "target": "qwen3.6-plus",
            "stream": True,
            "input_tokens_estimate": 99,
            "started_at": 1778199999.0,
        }
        events = []
        with patch.object(proxy.token_metrics_store, "record", side_effect=events.append):
            text = "".join(proxy.anthropic_sse_from_openai_stream(FakeResponse(lines=lines), "Qwen 3.6 Plus", metrics=context))
        self.assertIn('"type": "message_stop"', text)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["input_tokens"], 7)
        self.assertEqual(events[0]["output_tokens"], 3)
        self.assertEqual(events[0]["total_tokens"], 10)
        self.assertFalse(events[0]["input_estimated"])
        self.assertFalse(events[0]["output_estimated"])

    def test_openai_stream_records_token_usage_once(self):
        lines = [
            b'data: {"choices":[{"delta":{"content":"OK"},"finish_reason":"stop"}]}',
            b'data: {"choices":[],"usage":{"prompt_tokens":11,"completion_tokens":4,"total_tokens":15}}',
            b"data: [DONE]",
        ]
        context = {
            "ts": 1778200000.0,
            "request_id": "req_openai_stream",
            "endpoint": "/v1/chat/completions",
            "client_ip": "127.0.0.1",
            "model": "Qwen 3.6 Plus",
            "provider": "alibaba",
            "backend": "sg",
            "target": "qwen3.6-plus",
            "stream": True,
            "input_tokens_estimate": 99,
            "started_at": 1778199999.0,
        }
        events = []
        with patch.object(proxy.token_metrics_store, "record", side_effect=events.append):
            chunks = list(proxy.sanitized_openai_stream_chunks(FakeResponse(lines=lines), metrics=context))
        self.assertTrue(chunks[-1].startswith(b"data: [DONE]"))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["input_tokens"], 11)
        self.assertEqual(events[0]["output_tokens"], 4)
        self.assertEqual(events[0]["total_tokens"], 15)


if __name__ == "__main__":
    unittest.main()
