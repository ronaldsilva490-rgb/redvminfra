import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import proxy  # noqa: E402


class FakeUpstreamResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.headers = {"Content-Type": "application/json"}
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


class FakeKeyPool:
    def __init__(self):
        self.keys = [
            {"id": 1, "key": "vck_empty", "failures": 0, "successes": 0, "cooldown_until": 0},
            {"id": 2, "key": "vck_good", "failures": 0, "successes": 0, "cooldown_until": 0},
        ]

    def get_key(self, exclude=None):
        exclude = set(exclude or [])
        for key in self.keys:
            if key["id"] not in exclude:
                return key["id"], key["key"]
        return None, None

    def report_failure(self, key_id, is_rate_limit=False, status_code=None, error_message=""):
        for key in self.keys:
            if key["id"] == key_id:
                key["failures"] += 1
                key["last_status"] = status_code
                key["last_error"] = proxy.safe_upstream_error_message(status_code or 0, error_message)
                key["cooldown_until"] = 1

    def report_success(self, key_id):
        for key in self.keys:
            if key["id"] == key_id:
                key["successes"] += 1

    def active_count(self):
        return len(self.keys)


class ResponsesAdapterTests(unittest.TestCase):
    def test_upstream_request_failovers_402_without_leaking_billing_error(self):
        raw_billing_error = {
            "error": {
                "message": "Insufficient funds. Please add credits: https://vercel.com/d?to=top-up",
                "type": "insufficient_funds",
            }
        }
        ok_payload = {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}
        responses = [FakeUpstreamResponse(402, raw_billing_error), FakeUpstreamResponse(200, ok_payload)]
        seen_auth = []
        fake_pool = FakeKeyPool()

        def fake_request(**kwargs):
            seen_auth.append(kwargs["headers"]["Authorization"])
            return responses.pop(0)

        with patch.object(proxy, "key_pool", fake_pool), patch.object(proxy.http_session, "request", side_effect=fake_request):
            resp, error_response = proxy.upstream_request("POST", "/v1/chat/completions", "127.0.0.1", json_body={"model": "x"})

        self.assertIsNone(error_response)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(seen_auth, ["Bearer vck_empty", "Bearer vck_good"])
        self.assertEqual(fake_pool.keys[0]["last_status"], 402)
        self.assertEqual(fake_pool.keys[0]["last_error"], "upstream key unavailable")
        self.assertEqual(fake_pool.keys[1]["successes"], 1)

    def test_upstream_request_exhausted_402_returns_sanitized_error(self):
        raw_billing_error = {
            "error": {
                "message": "Insufficient funds. Please add credits: https://vercel.com/d?to=top-up",
                "type": "insufficient_funds",
            }
        }
        responses = [FakeUpstreamResponse(402, raw_billing_error), FakeUpstreamResponse(402, raw_billing_error)]
        fake_pool = FakeKeyPool()

        def fake_request(**_kwargs):
            return responses.pop(0)

        with patch.object(proxy, "key_pool", fake_pool), patch.object(proxy.http_session, "request", side_effect=fake_request):
            resp, error_response = proxy.upstream_request("POST", "/v1/chat/completions", "127.0.0.1", json_body={"model": "x"})

        self.assertIsNone(resp)
        self.assertEqual(error_response.status_code, 503)
        body = error_response.get_data(as_text=True)
        self.assertNotIn("Insufficient funds", body)
        self.assertNotIn("vercel.com", body)
        self.assertIn("internal failover", body)

    def test_codex_tool_catalog_converts_without_dropping_function_tools(self):
        codex_tools = [
            {
                "type": "function",
                "name": "shell",
                "description": "Runs a shell command.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "array",
                            "items": {"type": "string"},
                        }
                    },
                    "required": ["command"],
                },
            },
            {"type": "function", "name": "update_plan", "parameters": {"type": "object", "properties": {}}},
            {"type": "function", "name": "request_user_input", "parameters": {"type": "object", "properties": {}}},
            {"type": "function", "name": "tool_suggest", "parameters": {"type": "object", "properties": {}}},
            {"type": "function", "name": "view_image", "parameters": {"type": "object", "properties": {}}},
            {"type": "function", "name": "spawn_agent", "parameters": {"type": "object", "properties": {}}},
            {"type": "function", "name": "send_input", "parameters": {"type": "object", "properties": {}}},
            {"type": "function", "name": "wait_agent", "parameters": {"type": "object", "properties": {}}},
            {"type": "function", "name": "close_agent", "parameters": {"type": "object", "properties": {}}},
            {"type": "function", "name": "apply_patch", "parameters": {"type": "object", "properties": {}}},
            {"type": "function", "name": "mcp__filesystem__read_file", "parameters": {"type": "object", "properties": {}}},
            {"type": "web_search", "external_web_access": True},
            {"type": "image_generation", "output_format": "png"},
        ]

        converted = proxy.responses_tools_to_chat_tools(codex_tools)
        names = [item["function"]["name"] for item in converted]

        self.assertEqual(
            names,
            [
                "shell",
                "update_plan",
                "request_user_input",
                "tool_suggest",
                "view_image",
                "spawn_agent",
                "send_input",
                "wait_agent",
                "close_agent",
                "apply_patch",
                "mcp__filesystem__read_file",
                "web_search",
                "image_generation",
            ],
        )
        self.assertEqual(converted[0]["function"]["parameters"]["properties"]["command"]["type"], "array")

    def test_mistral_models_are_detected_as_first_class_provider(self):
        descriptor = proxy.model_descriptor("mistral-medium-3.5")

        self.assertEqual(descriptor["provider"], "mistral")
        self.assertEqual(descriptor["route_model"], "mistral-medium-3.5")
        self.assertIn("chat", descriptor["capabilities"])
        self.assertTrue(descriptor["function_calling"])

    def test_mistral_prefixed_model_name_normalizes_to_raw_id(self):
        model_id, model_info = proxy.normalize_mistral_model("Mistral - devstral-latest")

        self.assertEqual(model_id, "devstral-latest")
        self.assertIn("chat", model_info["capabilities"])

    def test_ollama_tags_include_direct_mistral_models_for_pageassist(self):
        raw = json.dumps({"models": []}).encode("utf-8")

        data = json.loads(proxy.augment_tags_body(raw).decode("utf-8"))
        names = {item["name"] for item in data["models"]}

        self.assertIn("devstral-medium-latest", names)
        self.assertIn("mistral-small-latest", names)

    def test_mistral_model_details_use_ollama_show_shape(self):
        model_id, model_info = proxy.normalize_mistral_model("devstral-medium-latest")

        details = proxy.mistral_model_details(model_id, model_info)

        self.assertEqual(details["details"]["format"], "mistral")
        self.assertEqual(details["model_info"]["red.provider"], "mistral")
        self.assertIn("chat", details["capabilities"])

    def test_claude_gateway_alias_routes_to_target_model(self):
        descriptor = proxy.model_descriptor("claude-red-devstral-medium")

        self.assertEqual(descriptor["id"], "claude-red-devstral-medium")
        self.assertEqual(descriptor["route_model"], "devstral-medium-latest")
        self.assertTrue(descriptor["gateway_alias"])
        self.assertIn("chat", descriptor["capabilities"])

    def test_claude_gateway_aliases_include_all_tool_call_passed_models(self):
        expected = {
            "claude-red-mistral-medium": "mistral-medium-3.5",
            "claude-red-devstral": "devstral-latest",
            "claude-red-devstral-medium": "devstral-medium-latest",
            "claude-red-mistral-large": "mistral-large-latest",
            "claude-red-mistral-small": "mistral-small-latest",
            "claude-red-mistral-vibe": "mistral-vibe-cli-latest",
            "claude-red-codestral": "codestral-latest",
            "claude-red-ollama-gemma4-31b": "gemma4:31b",
            "claude-red-ollama-nemotron3-super": "nemotron-3-super",
            "claude-red-ollama-minimax-m25": "minimax-m2.5",
            "claude-red-ollama-qwen3-vl-235b": "qwen3-vl:235b-instruct",
            "claude-red-ollama-gpt-oss-120b": "gpt-oss:120b",
            "claude-red-ollama-qwen3-coder-480b": "qwen3-coder:480b",
            "claude-red-nim-nemotron3-super": "nvidia/nemotron-3-super-120b-a12b",
            "claude-red-nim-glm51": "z-ai/glm-5.1",
            "claude-red-nim-gemma4-31b": "google/gemma-4-31b-it",
            "claude-red-nim-qwen35-397b": "qwen/qwen3.5-397b-a17b",
            "claude-red-nim-mistral-small4": "mistralai/mistral-small-4-119b-2603",
            "claude-red-nim-kimi-k26": "moonshotai/kimi-k2.6",
            "claude-red-nim-kimi-thinking": "moonshotai/kimi-k2-thinking",
            "claude-red-qwen-next": "qwen/qwen3-next-80b-a3b-instruct",
            "claude-red-qwen-35-122b": "qwen/qwen3.5-122b-a10b",
            "claude-red-glm51": "z-ai/glm-5.1",
            "claude-red-qwen3-coder-next": "qwen3-coder-next",
        }

        alias_map = {item["id"]: item["target"] for item in proxy.CLAUDE_GATEWAY_MODEL_ALIASES}

        self.assertEqual(alias_map, expected)

    def test_legacy_aliases_route_but_are_not_listed(self):
        descriptor = proxy.model_descriptor("claude-red-glm51")

        self.assertEqual(descriptor["route_model"], "z-ai/glm-5.1")
        self.assertEqual(descriptor["display_name"], "RED NIM GLM 5.1 Legacy")

        listed = [item["id"] for item in proxy.model_descriptors("127.0.0.1")]

        self.assertNotIn("claude-red-glm51", listed)
        self.assertIn("claude-red-nim-glm51", listed)

    def test_claude_gateway_alias_can_override_capabilities(self):
        descriptor = proxy.model_descriptor("claude-red-ollama-gemma4-31b")

        self.assertEqual(descriptor["route_model"], "gemma4:31b")
        self.assertEqual(descriptor["kind"], "vision")
        self.assertIn("vision", descriptor["capabilities"])

    def test_public_model_entry_includes_anthropic_model_fields(self):
        entry = proxy.public_model_entry(proxy.model_descriptor("claude-red-devstral-medium"))

        self.assertEqual(entry["object"], "model")
        self.assertEqual(entry["type"], "model")
        self.assertEqual(entry["display_name"], "RED MIS Devstral Medium")
        self.assertIn("created_at", entry)
        self.assertTrue(entry["red"]["gateway_alias"])

    def test_claude_gateway_display_names_include_provider_prefix(self):
        prefixes_by_id = {
            "claude-red-mistral-medium": "RED MIS ",
            "claude-red-ollama-gemma4-31b": "RED OLL ",
            "claude-red-nim-glm51": "RED NIM ",
            "claude-red-qwen-next": "RED NIM ",
            "claude-red-qwen3-coder-next": "RED OLL ",
        }

        for model_id, prefix in prefixes_by_id.items():
            entry = proxy.public_model_entry(proxy.model_descriptor(model_id))
            self.assertTrue(entry["display_name"].startswith(prefix), entry["display_name"])

    def test_route_json_body_uses_route_model_but_keeps_alias_metadata(self):
        body = {"model": "claude-red-devstral-medium", "messages": [{"role": "user", "content": "ola"}]}

        routed_body, routing, error_response = proxy.route_json_body(body, "/v1/messages", "127.0.0.1")

        self.assertIsNone(error_response)
        self.assertEqual(routed_body["model"], "devstral-medium-latest")
        self.assertEqual(routing["resolved_model"], "claude-red-devstral-medium")
        self.assertEqual(routing["route_model"], "devstral-medium-latest")

    def test_anthropic_count_tokens_estimates_structured_inputs(self):
        body = {
            "model": "claude-red-devstral-medium",
            "system": "Voce e um agente de codigo.",
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "Crie um plano curto."}]},
                {
                    "role": "assistant",
                    "content": [{"type": "tool_use", "id": "toolu_1", "name": "shell", "input": {"command": "dir"}}],
                },
                {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "ok"}]},
            ],
            "tools": [
                {
                    "name": "shell",
                    "description": "Executa comandos",
                    "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}},
                }
            ],
        }

        tokens = proxy.estimate_anthropic_input_tokens(body)

        self.assertGreater(tokens, 20)

    def test_anthropic_tool_calls_convert_to_tool_use_blocks(self):
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
                                    "id": "call_shell",
                                    "type": "function",
                                    "function": {"name": "shell", "arguments": "{\"command\":\"dir\"}"},
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
        self.assertEqual(message["model"], "claude-red-devstral-medium")
        self.assertEqual(message["content"][0]["type"], "tool_use")
        self.assertEqual(message["content"][0]["name"], "shell")

    def test_anthropic_to_openai_payload_preserves_stream(self):
        payload = proxy.anthropic_to_openai_payload(
            {
                "model": "claude-red-devstral-medium",
                "stream": True,
                "messages": [{"role": "user", "content": "ola"}],
            },
            "devstral-medium-latest",
        )

        self.assertTrue(payload["stream"])

    def test_openai_stream_converts_to_incremental_anthropic_sse(self):
        class FakeStream:
            def iter_lines(self, decode_unicode=True):
                chunks = [
                    {"choices": [{"delta": {"content": "ola "}, "finish_reason": None}]},
                    {"choices": [{"delta": {"content": "mundo"}, "finish_reason": None}]},
                    {"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 3, "completion_tokens": 2}},
                ]
                for chunk in chunks:
                    yield "data: " + json.dumps(chunk)
                yield "data: [DONE]"

        text = "".join(proxy.anthropic_sse_from_openai_stream(FakeStream(), "claude-red-devstral-medium"))

        self.assertIn('"type": "message_start"', text)
        self.assertIn('"text": "ola "', text)
        self.assertIn('"text": "mundo"', text)
        self.assertLess(text.index('"text": "ola "'), text.index('"text": "mundo"'))
        self.assertIn('"stop_reason": "end_turn"', text)

    def test_anthropic_sse_escapes_unicode_to_avoid_mojibake(self):
        message = {
            "id": "msg_unicode",
            "type": "message",
            "role": "assistant",
            "model": "claude-red-devstral-medium",
            "content": [{"type": "text", "text": "voc\u00ea a\u00e7\u00e3o \U0001f642"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 1, "output_tokens": 2},
        }

        text = "".join(proxy.anthropic_sse_from_message(message))

        self.assertIn("\\u00ea", text)
        self.assertIn("\\u00e7\\u00e3o", text)
        self.assertIn("\\ud83d\\ude42", text)
        self.assertNotIn("voc\u00ea", text)

    def test_openai_stream_bytes_are_decoded_as_utf8_before_sse_escape(self):
        class FakeByteStream:
            def iter_lines(self, decode_unicode=False):
                chunk = {"choices": [{"delta": {"content": "voc\u00ea"}, "finish_reason": None}]}
                yield ("data: " + json.dumps(chunk, ensure_ascii=False)).encode("utf-8")
                yield b'data: [DONE]'

        text = "".join(proxy.anthropic_sse_from_openai_stream(FakeByteStream(), "claude-red-devstral-medium"))

        self.assertIn("voc\\u00ea", text)
        self.assertNotIn("voc\\u00c3", text)

    def test_openai_tool_stream_converts_to_anthropic_tool_use(self):
        class FakeToolStream:
            def iter_lines(self, decode_unicode=True):
                chunks = [
                    {
                        "choices": [
                            {
                                "delta": {
                                    "tool_calls": [
                                        {
                                            "index": 0,
                                            "id": "call_shell",
                                            "type": "function",
                                            "function": {"name": "shell", "arguments": "{\"command\""},
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
                                "delta": {
                                    "tool_calls": [
                                        {"index": 0, "function": {"arguments": ":\"dir\"}"}}
                                    ]
                                },
                                "finish_reason": "tool_calls",
                            }
                        ]
                    },
                ]
                for chunk in chunks:
                    yield "data: " + json.dumps(chunk)
                yield "data: [DONE]"

        text = "".join(proxy.anthropic_sse_from_openai_stream(FakeToolStream(), "claude-red-devstral-medium"))

        self.assertIn('"type": "tool_use"', text)
        self.assertIn('"name": "shell"', text)
        self.assertIn('"partial_json": "{\\"command\\""', text)
        self.assertIn('"partial_json": ":\\"dir\\"}"', text)
        self.assertIn('"stop_reason": "tool_use"', text)

    def test_anthropic_count_tokens_endpoint_shape(self):
        with proxy.app.test_client() as client:
            response = client.post(
                "/v1/messages/count_tokens",
                json={
                    "model": "claude-red-devstral-medium",
                    "messages": [{"role": "user", "content": "ola"}],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("input_tokens", response.get_json())

    def test_codex_input_tools_and_tool_outputs_convert_to_chat(self):
        body = {
            "model": "qwen3-coder-next",
            "instructions": "system rules",
            "input": [
                {"role": "user", "content": [{"type": "input_text", "text": "run a command"}]},
                {
                    "type": "function_call",
                    "call_id": "call_shell_1",
                    "name": "shell",
                    "arguments": "{\"command\":\"pwd\"}",
                },
                {
                    "type": "function_call_output",
                    "call_id": "call_shell_1",
                    "output": "C:\\Projetos\\redvm",
                },
            ],
            "tools": [
                {
                    "type": "function",
                    "name": "shell",
                    "description": "Run a command",
                    "parameters": {"type": "object", "properties": {"command": {"type": "string"}}},
                    "strict": False,
                },
                {"type": "web_search", "external_web_access": False},
                {"type": "image_generation", "output_format": "png"},
            ],
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "max_output_tokens": 123,
        }

        chat = proxy.responses_to_chat_payload(body)

        self.assertEqual(chat["model"], "qwen3-coder-next")
        self.assertGreaterEqual(chat["max_tokens"], 123)
        self.assertEqual(chat["messages"][0], {"role": "system", "content": "system rules"})
        self.assertEqual(chat["messages"][2]["role"], "assistant")
        self.assertEqual(chat["messages"][2]["tool_calls"][0]["id"], "call_shell_1")
        self.assertEqual(chat["messages"][3]["role"], "tool")
        self.assertEqual(chat["messages"][3]["tool_call_id"], "call_shell_1")
        self.assertEqual([item["function"]["name"] for item in chat["tools"]], ["shell", "web_search", "image_generation"])

    def test_developer_role_converts_to_system_for_strict_chat_backends(self):
        chat = proxy.responses_to_chat_payload(
            {
                "model": "strict-chat",
                "input": [
                    {"role": "user", "content": [{"type": "input_text", "text": "hello"}]},
                    {"role": "developer", "content": [{"type": "input_text", "text": "follow project rules"}]},
                ],
            }
        )

        self.assertEqual(chat["messages"][0], {"role": "system", "content": "follow project rules"})
        self.assertEqual(chat["messages"][1], {"role": "user", "content": "hello"})

    def test_responses_min_output_tokens_prevents_codex_code_truncation(self):
        chat = proxy.responses_to_chat_payload({"model": "coder", "input": "write code", "max_output_tokens": 512})

        self.assertGreaterEqual(chat["max_tokens"], proxy.RESPONSES_MIN_OUTPUT_TOKENS)

    def test_chat_tool_calls_convert_to_responses_function_calls(self):
        data = {
            "id": "chatcmpl_test",
            "created": 1777938843,
            "model": "qwen3-coder-next",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_shell_2",
                                "type": "function",
                                "function": {"name": "shell", "arguments": "{\"command\":\"Get-ChildItem\"}"},
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
        }

        response = proxy.responses_from_chat(data, "qwen3-coder-next", {"tools": [{"type": "function", "name": "shell"}]})

        self.assertEqual(response["object"], "response")
        self.assertEqual(response["output"][0]["type"], "function_call")
        self.assertEqual(response["output"][0]["call_id"], "call_shell_2")
        self.assertEqual(response["output"][0]["name"], "shell")
        self.assertEqual(
            json.loads(response["output"][0]["arguments"])["command"],
            ["powershell.exe", "-Command", "Get-ChildItem"],
        )
        self.assertEqual(response["usage"]["total_tokens"], 14)

    def test_shell_tool_string_command_is_normalized_for_codex(self):
        response = proxy.responses_from_chat(
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "id": "call_shell_string",
                                    "type": "function",
                                    "function": {
                                        "name": "shell",
                                        "arguments": json.dumps(
                                            {"command": "powershell.exe -Command 'python -m unittest -v'"}
                                        ),
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
            "model",
            {},
        )

        args = json.loads(response["output"][0]["arguments"])
        self.assertEqual(args["command"], ["powershell.exe", "-Command", "python -m unittest -v"])

    def test_textual_tool_call_markup_is_converted_for_codex(self):
        response = proxy.responses_from_chat(
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": (
                                "Vou criar o arquivo agora.\n"
                                "<tool_call>shell"
                                "<arg_key>command</arg_key>"
                                "<arg_value>[\"powershell.exe\", \"-Command\", \"Write-Output ok\"]</arg_value>"
                                "</tool_call>"
                            ),
                        }
                    }
                ]
            },
            "model",
            {"tools": [{"type": "function", "name": "shell"}]},
        )

        self.assertEqual(response["output"][0]["type"], "message")
        self.assertNotIn("<tool_call>", response["output_text"])
        self.assertEqual(response["output"][1]["type"], "function_call")
        self.assertEqual(response["output"][1]["name"], "shell")
        args = json.loads(response["output"][1]["arguments"])
        self.assertEqual(args["command"], ["powershell.exe", "-Command", "Write-Output ok"])

    def test_textual_tool_call_markup_is_left_as_text_without_matching_tool(self):
        text = "<tool_call>shell<arg_key>command</arg_key><arg_value>dir</arg_value></tool_call>"
        response = proxy.responses_from_chat(
            {"choices": [{"message": {"role": "assistant", "content": text}}]},
            "model",
            {"tools": [{"type": "function", "name": "apply_patch"}]},
        )

        self.assertEqual(len(response["output"]), 1)
        self.assertIn("<tool_call>", response["output_text"])

    def test_json_response_format_strips_markdown_fence(self):
        data = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "```json\n{\"ok\": true, \"lang\": \"pt-BR\"}\n```",
                    }
                }
            ]
        }

        response = proxy.responses_from_chat(
            data,
            "qwen3-coder:480b",
            {"text": {"format": {"type": "json_object"}}},
        )

        self.assertEqual(json.loads(response["output_text"]), {"ok": True, "lang": "pt-BR"})
        self.assertEqual(response["output"][0]["content"][0]["text"], response["output_text"])

    def test_responses_function_call_output_round_trip_matches_codex_loop(self):
        first_chat = {
            "id": "chatcmpl_tool",
            "created": 1777938843,
            "model": "mock-codex",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_shell_roundtrip",
                                "type": "function",
                                "function": {
                                    "name": "shell",
                                    "arguments": json.dumps(
                                        {"command": ["powershell.exe", "-Command", "Write-Output ok"]}
                                    ),
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
        }

        responses_payload = proxy.responses_from_chat(first_chat, "mock-codex", {"tools": [{"type": "function", "name": "shell"}]})
        next_request = proxy.responses_to_chat_payload(
            {
                "model": "mock-codex",
                "input": [
                    responses_payload["output"][0],
                    {
                        "type": "function_call_output",
                        "call_id": "call_shell_roundtrip",
                        "output": {"output": "ok\r\n", "metadata": {"exit_code": 0}},
                    },
                ],
            }
        )

        self.assertEqual(next_request["messages"][0]["role"], "assistant")
        self.assertEqual(next_request["messages"][0]["tool_calls"][0]["id"], "call_shell_roundtrip")
        self.assertEqual(next_request["messages"][1]["role"], "tool")
        self.assertEqual(next_request["messages"][1]["tool_call_id"], "call_shell_roundtrip")
        self.assertIn('"exit_code": 0', next_request["messages"][1]["content"])

    def test_textual_tool_history_payload_removes_tool_role_for_strict_nim_models(self):
        payload = {
            "model": "strict-nim",
            "messages": [
                {"role": "user", "content": "run it"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "shell", "arguments": "{\"command\":[\"pwd\"]}"},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "call_1", "content": "{\"output\":\"ok\"}"},
            ],
        }

        rewritten = proxy.textual_tool_history_payload(payload)

        self.assertFalse(any(message["role"] == "tool" for message in rewritten["messages"]))
        self.assertNotIn("tool_calls", rewritten["messages"][1])
        self.assertIn("Chamadas de ferramenta solicitadas", rewritten["messages"][1]["content"])
        self.assertEqual(rewritten["messages"][2]["role"], "user")
        self.assertIn("Resultado da ferramenta call_1", rewritten["messages"][2]["content"])

    def test_responses_sse_contains_codex_relevant_events(self):
        data = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "checking",
                        "tool_calls": [
                            {
                                "id": "call_plan_1",
                                "type": "function",
                                "function": {"name": "update_plan", "arguments": "{\"plan\":[]}"},
                            }
                        ],
                    }
                }
            ],
            "usage": {},
        }

        stream = "".join(proxy.responses_sse_from_chat(data, "qwen3-coder-next", {"stream": True}))

        self.assertIn("event: response.created", stream)
        self.assertIn("event: response.output_text.delta", stream)
        self.assertIn("event: response.function_call_arguments.delta", stream)
        self.assertIn("event: response.output_item.done", stream)
        self.assertIn("event: response.completed", stream)


if __name__ == "__main__":
    unittest.main()
