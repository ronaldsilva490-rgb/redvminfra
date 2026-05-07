from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from copy import deepcopy
from typing import Any

import requests
from flask import Flask, Response, request


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except Exception:
        return int(default)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "sim"}


def split_values(value: str) -> list[str]:
    items: list[str] = []
    for raw in str(value or "").replace(";", "\n").replace(",", "\n").splitlines():
        item = raw.strip()
        if item:
            items.append(item)
    return items


SERVICE_NAME = "redlightningclaude"
HOST = os.getenv("REDLIGHTNINGCLAUDE_HOST", "0.0.0.0").strip() or "0.0.0.0"
PORT = env_int("REDLIGHTNINGCLAUDE_PORT", 5051)
LIGHTNING_BASE_URL = os.getenv("REDLIGHTNINGCLAUDE_BASE_URL", "https://lightning.ai/api/v1").rstrip("/")
LIGHTNING_API_KEY = (
    os.getenv("REDLIGHTNINGCLAUDE_API_KEY")
    or os.getenv("LIGHTNING_API_KEY")
    or ""
).strip()
LIGHTNING_API_KEYS = split_values(os.getenv("REDLIGHTNINGCLAUDE_API_KEYS", ""))
REQUIRE_AUTH = env_bool("REDLIGHTNINGCLAUDE_REQUIRE_AUTH", True)
AUTH_TOKENS = set(split_values(os.getenv("REDLIGHTNINGCLAUDE_AUTH_TOKENS", "red")))
DEFAULT_MODEL = (
    os.getenv("REDLIGHTNINGCLAUDE_DEFAULT_MODEL")
    or "anthropic/claude-sonnet-4-6"
).strip().lower()
STREAM_CHUNK_SIZE = max(1, env_int("REDLIGHTNINGCLAUDE_STREAM_CHUNK_SIZE", 1))
CONNECT_TIMEOUT = env_int("REDLIGHTNINGCLAUDE_CONNECT_TIMEOUT", 20)
READ_TIMEOUT = env_int("REDLIGHTNINGCLAUDE_READ_TIMEOUT", 360)
TLS_CERT = (os.getenv("REDLIGHTNINGCLAUDE_TLS_CERT") or "").strip()
TLS_KEY = (os.getenv("REDLIGHTNINGCLAUDE_TLS_KEY") or "").strip()
TOKEN_SAFETY_MARGIN = max(0, env_int("REDLIGHTNINGCLAUDE_TOKEN_SAFETY_MARGIN", 4096))
MIN_COMPLETION_TOKENS = max(1, env_int("REDLIGHTNINGCLAUDE_MIN_COMPLETION_TOKENS", 256))
MAX_CONTEXT_RETRIES = max(1, env_int("REDLIGHTNINGCLAUDE_MAX_CONTEXT_RETRIES", 5))
CONTEXT_RETRY_MARGIN_STEP = max(0, env_int("REDLIGHTNINGCLAUDE_CONTEXT_RETRY_MARGIN_STEP", 2048))
RATE_LIMIT_MIN_INTERVAL_SECONDS = max(0, env_int("REDLIGHTNINGCLAUDE_RATE_LIMIT_MIN_INTERVAL_SECONDS", 1))
RATE_LIMIT_COOLDOWN_SECONDS = max(1, env_int("REDLIGHTNINGCLAUDE_RATE_LIMIT_COOLDOWN_SECONDS", 12))
RATE_LIMIT_COOLDOWN_STEP_SECONDS = max(0, env_int("REDLIGHTNINGCLAUDE_RATE_LIMIT_COOLDOWN_STEP_SECONDS", 4))
RATE_LIMIT_MAX_COOLDOWN_SECONDS = max(1, env_int("REDLIGHTNINGCLAUDE_RATE_LIMIT_MAX_COOLDOWN_SECONDS", 45))
MAX_429_RETRIES = max(0, env_int("REDLIGHTNINGCLAUDE_MAX_429_RETRIES", 6))
SERVER_ERROR_COOLDOWN_SECONDS = max(1, env_int("REDLIGHTNINGCLAUDE_SERVER_ERROR_COOLDOWN_SECONDS", 4))
MAX_5XX_RETRIES = max(0, env_int("REDLIGHTNINGCLAUDE_MAX_5XX_RETRIES", 4))

http = requests.Session()
http.headers.update({"Accept": "application/json"})

MODELS = [
    {
        "id": "anthropic/claude-opus-4-7",
        "target": "anthropic/claude-opus-4-7",
        "display_name": "Lightning Claude Opus 4.7",
        "provider": "anthropic",
        "kind": "chat",
        "capabilities": ["chat", "tools"],
        "context_window": 1000000,
        "tool_call_tested": True,
        "default": False,
    },
    {
        "id": "anthropic/claude-sonnet-4-6",
        "target": "anthropic/claude-sonnet-4-6",
        "display_name": "Lightning Claude Sonnet 4.6",
        "provider": "anthropic",
        "kind": "chat",
        "capabilities": ["chat", "tools"],
        "context_window": 200000,
        "tool_call_tested": True,
        "default": True,
    },
    {
        "id": "lightning-ai/deepseek-v4-pro",
        "target": "lightning-ai/deepseek-v4-pro",
        "display_name": "Lightning DeepSeek V4 Pro",
        "provider": "lightning-ai",
        "kind": "chat",
        "capabilities": ["chat", "tools"],
        "context_window": 1048576,
        "tool_call_tested": True,
        "default": False,
    },
]
MODEL_BY_ID = {item["id"].lower(): item for item in MODELS}
MODEL_BY_TARGET = {item["target"].lower(): item for item in MODELS}

app = Flask(__name__)


class LightningKeyPool:
    def __init__(self, keys: list[str]) -> None:
        self._keys = [{"token": key, "next_allowed_at": 0.0, "cooldown_until": 0.0, "consecutive_429": 0} for key in keys if key]
        self._lock = threading.Lock()
        self._rr_index = 0

    def has_keys(self) -> bool:
        return bool(self._keys)

    def acquire(self) -> dict[str, Any] | None:
        if not self._keys:
            return None
        while True:
            with self._lock:
                now = time.monotonic()
                best_wait = None
                for offset in range(len(self._keys)):
                    idx = (self._rr_index + offset) % len(self._keys)
                    item = self._keys[idx]
                    target = max(item["next_allowed_at"], item["cooldown_until"])
                    wait = target - now
                    if wait <= 0:
                        item["next_allowed_at"] = now + RATE_LIMIT_MIN_INTERVAL_SECONDS
                        self._rr_index = (idx + 1) % len(self._keys)
                        return item
                    if best_wait is None or wait < best_wait:
                        best_wait = wait
            time.sleep(min(max(best_wait or 0.05, 0.05), 0.25))

    def on_success(self, item: dict[str, Any]) -> None:
        with self._lock:
            item["consecutive_429"] = 0

    def on_429(self, item: dict[str, Any]) -> None:
        with self._lock:
            item["consecutive_429"] += 1
            penalty = RATE_LIMIT_COOLDOWN_SECONDS + max(0, item["consecutive_429"] - 1) * RATE_LIMIT_COOLDOWN_STEP_SECONDS
            penalty = min(RATE_LIMIT_MAX_COOLDOWN_SECONDS, penalty)
            item["cooldown_until"] = max(item["cooldown_until"], time.monotonic() + penalty)

    def on_5xx(self, item: dict[str, Any]) -> None:
        with self._lock:
            item["cooldown_until"] = max(item["cooldown_until"], time.monotonic() + SERVER_ERROR_COOLDOWN_SECONDS)


def configured_lightning_keys() -> list[str]:
    keys: list[str] = []
    if LIGHTNING_API_KEY:
        keys.append(LIGHTNING_API_KEY)
    for key in LIGHTNING_API_KEYS:
        if key and key not in keys:
            keys.append(key)
    return keys


KEY_POOL = LightningKeyPool(configured_lightning_keys())


def request_id() -> str:
    return str(uuid.uuid4())


def response_json(payload: dict[str, Any], status: int = 200) -> Response:
    response = Response(json.dumps(payload, ensure_ascii=False), status=status, content_type="application/json")
    response.headers["X-Request-Id"] = request_id()
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, Accept, Anthropic-Version, Anthropic-Beta"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


def error_response(message: str, status: int, error_type: str) -> Response:
    return response_json({"error": {"message": message, "type": error_type}}, status)


def authorize() -> Response | None:
    if not REQUIRE_AUTH:
        return None
    candidates = []
    auth = str(request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        candidates.append(auth[7:].strip())
    elif auth:
        candidates.append(auth)
    for header in ("X-API-Key", "api-key", "apikey"):
        value = str(request.headers.get(header) or "").strip()
        if value:
            candidates.append(value)
    if any(token in AUTH_TOKENS for token in candidates):
        return None
    return error_response("authorization required", 401, "authentication_error")


def default_model() -> dict[str, Any]:
    if DEFAULT_MODEL in MODEL_BY_ID:
        return MODEL_BY_ID[DEFAULT_MODEL]
    for item in MODELS:
        if item.get("default"):
            return item
    return MODELS[0]


def resolve_model(model_name: str | None) -> dict[str, Any] | None:
    if not model_name:
        return default_model()
    key = str(model_name).strip().lower()
    if key in MODEL_BY_ID:
        return MODEL_BY_ID[key]
    if key in MODEL_BY_TARGET:
        return MODEL_BY_TARGET[key]
    return None


def parse_json_body() -> tuple[dict[str, Any] | None, Response | None]:
    body = request.get_json(silent=True)
    if body is None:
        raw = request.get_data(cache=True) or b""
        if raw.strip():
            return None, error_response("invalid JSON body", 400, "invalid_request_error")
        return {}, None
    if not isinstance(body, dict):
        return None, error_response("JSON body must be an object", 400, "invalid_request_error")
    return body, None


def anthropic_system_text(body: dict[str, Any]) -> str:
    raw = body.get("system")
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        parts: list[str] = []
        for item in raw:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(part for part in parts if part)
    return ""


def tool_schema_to_openai(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": str(tool.get("name") or ""),
            "description": str(tool.get("description") or ""),
            "parameters": deepcopy(tool.get("input_schema") or {"type": "object", "properties": {}}),
        },
    }


def text_from_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text":
                    out.append(str(item.get("text") or ""))
                elif item.get("type") == "tool_result":
                    out.append(text_from_content(item.get("content")))
        return "\n".join(part for part in out if part)
    if isinstance(value, dict):
        return text_from_content(value.get("content"))
    return str(value or "")


def content_block_to_openai(block: dict[str, Any]) -> dict[str, Any] | None:
    block_type = str(block.get("type") or "").strip()
    if block_type == "text":
        return {"type": "text", "text": str(block.get("text") or "")}
    if block_type == "image":
        source = block.get("source") or {}
        source_type = str(source.get("type") or "").strip()
        media_type = str(source.get("media_type") or "image/png").strip() or "image/png"
        if source_type == "base64":
            data = str(source.get("data") or "")
            return {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{data}"}}
        if source_type == "url":
            url = str(source.get("url") or "")
            if url:
                return {"type": "image_url", "image_url": {"url": url}}
    return None


def anthropic_messages_to_openai(body: dict[str, Any]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    system_text = anthropic_system_text(body)
    if system_text:
        messages.append({"role": "system", "content": system_text})

    for message in body.get("messages") or []:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "user").strip() or "user"
        content = message.get("content")
        if isinstance(content, str):
            messages.append({"role": role, "content": content})
            continue
        if not isinstance(content, list):
            messages.append({"role": role, "content": text_from_content(content)})
            continue

        text_parts: list[dict[str, Any]] = []
        tool_calls: list[dict[str, Any]] = []
        tool_results: list[dict[str, Any]] = []

        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("type") or "").strip()
            if block_type in {"text", "image"}:
                converted = content_block_to_openai(block)
                if converted is not None:
                    text_parts.append(converted)
            elif block_type == "tool_use":
                tool_calls.append(
                    {
                        "id": str(block.get("id") or f"tool_{len(tool_calls)}"),
                        "type": "function",
                        "function": {
                            "name": str(block.get("name") or ""),
                            "arguments": json.dumps(block.get("input") or {}, ensure_ascii=False),
                        },
                    }
                )
            elif block_type == "tool_result":
                tool_results.append(
                    {
                        "role": "tool",
                        "tool_call_id": str(block.get("tool_use_id") or ""),
                        "content": text_from_content(block.get("content")),
                    }
                )

        if role == "assistant" and tool_calls:
            assistant_message: dict[str, Any] = {"role": "assistant", "tool_calls": tool_calls}
            if text_parts:
                if any(item.get("type") == "image_url" for item in text_parts):
                    assistant_message["content"] = text_parts
                else:
                    assistant_message["content"] = text_from_content(text_parts)
            else:
                assistant_message["content"] = ""
            messages.append(assistant_message)
        else:
            if text_parts:
                if any(item.get("type") == "image_url" for item in text_parts):
                    messages.append({"role": role, "content": text_parts})
                else:
                    messages.append({"role": role, "content": text_from_content(text_parts)})
        messages.extend(item for item in tool_results if item.get("tool_call_id"))
    return messages


def anthropic_tool_choice_to_openai(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"auto", "none"}:
            return lowered
        if lowered == "any":
            return "required"
    if isinstance(value, dict):
        choice_type = str(value.get("type") or "").strip().lower()
        if choice_type == "auto":
            return "auto"
        if choice_type == "any":
            return "required"
        if choice_type == "tool":
            name = str(value.get("name") or "").strip()
            if name:
                return {"type": "function", "function": {"name": name}}
    return None


def anthropic_to_openai_payload(body: dict[str, Any], alias: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": alias["target"],
        "messages": anthropic_messages_to_openai(body),
        "stream": bool(body.get("stream")),
        "temperature": body.get("temperature", 0),
        "max_tokens": body.get("max_tokens") or 2048,
    }
    if isinstance(body.get("tools"), list) and body.get("tools"):
        payload["tools"] = [tool_schema_to_openai(item) for item in body["tools"] if isinstance(item, dict)]
        tool_choice = anthropic_tool_choice_to_openai(body.get("tool_choice"))
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
    if isinstance(body.get("metadata"), dict):
        payload["metadata"] = deepcopy(body["metadata"])
    return payload


def estimate_tokens(body: dict[str, Any]) -> int:
    text_parts: list[str] = []
    system_text = anthropic_system_text(body)
    if system_text:
        text_parts.append(system_text)
    for message in body.get("messages") or []:
        if isinstance(message, dict):
            text_parts.append(text_from_content(message.get("content")))
    for tool in body.get("tools") or []:
        if isinstance(tool, dict):
            text_parts.append(json.dumps(tool, ensure_ascii=False))
    raw = "\n".join(part for part in text_parts if part)
    text_tokens = max(1, len(raw) // 4) if raw else 1
    image_count = 0
    for message in body.get("messages") or []:
        if isinstance(message, dict) and isinstance(message.get("content"), list):
            for block in message["content"]:
                if isinstance(block, dict) and str(block.get("type") or "") == "image":
                    image_count += 1
    return text_tokens + (image_count * 512)


def estimate_openai_tokens(payload: dict[str, Any]) -> int:
    text_parts: list[str] = []
    image_count = 0
    for message in payload.get("messages") or []:
        if not isinstance(message, dict):
            continue
        text_parts.append(str(message.get("role") or ""))
        content = message.get("content")
        if isinstance(content, str):
            text_parts.append(content)
        elif isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    text_parts.append(str(item))
                    continue
                item_type = str(item.get("type") or "")
                if item_type == "text":
                    text_parts.append(str(item.get("text") or ""))
                elif item_type == "image_url":
                    image_count += 1
                else:
                    text_parts.append(json.dumps(item, ensure_ascii=False))
        elif isinstance(content, dict):
            text_parts.append(json.dumps(content, ensure_ascii=False))
        elif content is not None:
            text_parts.append(str(content))
        for tool_call in message.get("tool_calls") or []:
            text_parts.append(json.dumps(tool_call, ensure_ascii=False))
    for tool in payload.get("tools") or []:
        if isinstance(tool, dict):
            text_parts.append(json.dumps(tool, ensure_ascii=False))
    raw = "\n".join(part for part in text_parts if part)
    text_tokens = max(1, len(raw) // 4) if raw else 1
    return text_tokens + (image_count * 512)


def clamp_max_tokens(requested: Any, input_tokens: int, context_window: int, *, extra_margin: int = 0) -> int:
    try:
        requested_int = int(requested)
    except Exception:
        requested_int = 2048
    requested_int = max(1, requested_int)
    available = max(1, int(context_window) - max(0, int(input_tokens)) - TOKEN_SAFETY_MARGIN - max(0, int(extra_margin)))
    if available < MIN_COMPLETION_TOKENS:
        return max(1, available)
    return max(1, min(requested_int, available))


def apply_context_guard(payload: dict[str, Any], *, input_tokens: int, context_window: int) -> dict[str, Any]:
    guarded = deepcopy(payload)
    guarded["max_tokens"] = clamp_max_tokens(guarded.get("max_tokens") or 2048, input_tokens, context_window)
    return guarded


def parse_context_error_limits(body: str) -> tuple[int, int] | None:
    if not body:
        return None
    max_match = re.search(r"maximum context length is\s+(\d+)", body, re.IGNORECASE)
    prompt_match = re.search(r"prompt contains at least\s+(\d+)\s+input tokens", body, re.IGNORECASE)
    if max_match and prompt_match:
        return int(max_match.group(1)), int(prompt_match.group(1))
    return None


def is_context_error(status_code: int, body: str) -> bool:
    lowered = (body or "").lower()
    return status_code == 400 and "maximum context length" in lowered and "input tokens" in lowered


def lightning_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def lightning_error_message(status_code: int, body: str) -> str:
    lowered = (body or "").lower()
    if status_code == 401:
        return "lightning api key rejected"
    if status_code == 402:
        return "lightning billing or balance issue"
    if status_code == 403:
        return "lightning request forbidden"
    if status_code == 404:
        return "lightning model or endpoint not found"
    if status_code == 429:
        return "lightning rate limit"
    if status_code >= 500:
        if "maxcompletiontokens" in lowered:
            return "upstream rejected max_tokens format"
        return "lightning provider temporary failure"
    if "failed to find the model" in lowered:
        return "lightning model missing from upstream"
    return body[:240] or f"upstream error {status_code}"


def proxy_openai_chat(payload: dict[str, Any], *, stream: bool, api_key: str) -> requests.Response:
    return http.post(
        f"{LIGHTNING_BASE_URL}/chat/completions",
        headers=lightning_headers(api_key),
        json=payload,
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
        stream=stream,
    )


def proxy_openai_chat_with_context_retry(
    payload: dict[str, Any],
    *,
    stream: bool,
    context_window: int,
    input_tokens: int,
) -> requests.Response:
    current_payload = apply_context_guard(payload, input_tokens=input_tokens, context_window=context_window)
    extra_margin = 0
    rate_retries_left = MAX_429_RETRIES
    server_retries_left = MAX_5XX_RETRIES
    for _attempt in range(MAX_CONTEXT_RETRIES + MAX_429_RETRIES + MAX_5XX_RETRIES + 1):
        pool_item = KEY_POOL.acquire()
        if pool_item is None:
            raise RuntimeError("lightning api key not configured")
        response = proxy_openai_chat(current_payload, stream=stream, api_key=str(pool_item["token"]))
        if response.status_code < 400:
            KEY_POOL.on_success(pool_item)
            return response
        try:
            body_text = response.text
        except Exception:
            body_text = ""
        if response.status_code == 429:
            KEY_POOL.on_429(pool_item)
            if rate_retries_left <= 0:
                return response
            rate_retries_left -= 1
            continue
        if response.status_code >= 500:
            KEY_POOL.on_5xx(pool_item)
            if server_retries_left <= 0:
                return response
            server_retries_left -= 1
            continue
        if not is_context_error(response.status_code, body_text):
            return response
        limits = parse_context_error_limits(body_text)
        if not limits:
            return response
        max_context, prompt_tokens = limits
        extra_margin += CONTEXT_RETRY_MARGIN_STEP
        next_payload = deepcopy(current_payload)
        next_payload["max_tokens"] = clamp_max_tokens(
            next_payload.get("max_tokens") or 2048,
            prompt_tokens,
            max_context,
            extra_margin=extra_margin,
        )
        if next_payload["max_tokens"] >= int(current_payload.get("max_tokens") or 0):
            return response
        current_payload = next_payload
    return response


def anthropic_message_from_openai(data: dict[str, Any], model_name: str) -> dict[str, Any]:
    choice = ((data.get("choices") or [{}]) or [{}])[0]
    message = choice.get("message") or {}
    content_blocks: list[dict[str, Any]] = []
    text = message.get("content")
    if isinstance(text, str) and text:
        content_blocks.append({"type": "text", "text": text})
    for tool_call in message.get("tool_calls") or []:
        function = tool_call.get("function") or {}
        arguments = function.get("arguments") or "{}"
        try:
            parsed_input = json.loads(arguments)
        except Exception:
            parsed_input = {"raw": arguments}
        content_blocks.append(
            {
                "type": "tool_use",
                "id": str(tool_call.get("id") or f"toolu_{uuid.uuid4().hex[:10]}"),
                "name": str(function.get("name") or ""),
                "input": parsed_input,
            }
        )
    finish_reason = str(choice.get("finish_reason") or "stop")
    stop_reason = "end_turn"
    if finish_reason == "tool_calls":
        stop_reason = "tool_use"
    elif finish_reason == "length":
        stop_reason = "max_tokens"
    usage = data.get("usage") or {}
    return {
        "id": data.get("id") or f"msg_{uuid.uuid4().hex}",
        "type": "message",
        "role": "assistant",
        "model": model_name,
        "content": content_blocks or [{"type": "text", "text": ""}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": int(usage.get("prompt_tokens") or 0),
            "output_tokens": int(usage.get("completion_tokens") or 0),
        },
    }


def sse_event(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=True)}\n\n"


def anthropic_sse_from_openai_stream(response: requests.Response, model_name: str):
    message_id = f"msg_{uuid.uuid4().hex}"
    yield sse_event(
        "message_start",
        {
            "type": "message_start",
            "message": {
                "id": message_id,
                "type": "message",
                "role": "assistant",
                "model": model_name,
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            },
        },
    )

    text_started = False
    text_closed = False
    tool_state: dict[int, dict[str, Any]] = {}
    usage_payload = {"input_tokens": 0, "output_tokens": 0}
    stop_reason = "end_turn"

    for raw_line in response.iter_lines(decode_unicode=False, chunk_size=STREAM_CHUNK_SIZE):
        if not raw_line:
            continue
        line = raw_line.decode("utf-8", "replace") if isinstance(raw_line, (bytes, bytearray)) else str(raw_line)
        if not line.startswith("data:"):
            continue
        data_text = line[5:].strip()
        if data_text == "[DONE]":
            break
        try:
            data = json.loads(data_text)
        except Exception:
            continue
        choice = ((data.get("choices") or [{}]) or [{}])[0]
        delta = choice.get("delta") or {}
        usage = data.get("usage") or {}
        if usage:
            usage_payload["input_tokens"] = int(usage.get("prompt_tokens") or usage_payload["input_tokens"])
            usage_payload["output_tokens"] = int(usage.get("completion_tokens") or usage_payload["output_tokens"])

        text_delta = delta.get("content")
        if isinstance(text_delta, str) and text_delta:
            if not text_started:
                text_started = True
                yield sse_event("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}})
            yield sse_event("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text_delta}})

        for tool_delta in delta.get("tool_calls") or []:
            try:
                index = int(tool_delta.get("index", 0))
            except Exception:
                index = 0
            block_index = index + (1 if text_started else 0)
            state = tool_state.setdefault(
                index,
                {
                    "started": False,
                    "id": str(tool_delta.get("id") or f"toolu_{uuid.uuid4().hex[:10]}"),
                    "name": "",
                },
            )
            function = tool_delta.get("function") or {}
            if function.get("name"):
                state["name"] = str(function["name"])
            if tool_delta.get("id"):
                state["id"] = str(tool_delta["id"])
            if not state["started"]:
                state["started"] = True
                yield sse_event(
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": block_index,
                        "content_block": {"type": "tool_use", "id": state["id"], "name": state["name"], "input": {}},
                    },
                )
            arguments = function.get("arguments")
            if arguments is not None:
                yield sse_event(
                    "content_block_delta",
                    {"type": "content_block_delta", "index": block_index, "delta": {"type": "input_json_delta", "partial_json": str(arguments)}},
                )

        finish_reason = choice.get("finish_reason")
        if finish_reason:
            if finish_reason == "tool_calls":
                stop_reason = "tool_use"
            elif finish_reason == "length":
                stop_reason = "max_tokens"
            else:
                stop_reason = "end_turn"

    if text_started and not text_closed:
        yield sse_event("content_block_stop", {"type": "content_block_stop", "index": 0})
        text_closed = True
    for index in sorted(tool_state):
        block_index = index + (1 if text_started else 0)
        yield sse_event("content_block_stop", {"type": "content_block_stop", "index": block_index})

    yield sse_event("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None}, "usage": usage_payload})
    yield sse_event("message_stop", {"type": "message_stop"})


def public_model_entry(alias: dict[str, Any]) -> dict[str, Any]:
    created = 1775520000
    return {
        "id": alias["id"],
        "object": "model",
        "type": "model",
        "created": created,
        "created_at": created,
        "display_name": alias["display_name"],
        "owned_by": alias["provider"],
        "context_window": alias["context_window"],
        "context_length": alias["context_window"],
        "max_context_length": alias["context_window"],
        "input_token_limit": alias["context_window"],
        "max_input_tokens": alias["context_window"],
        "red": {
            "gateway": SERVICE_NAME,
            "provider": alias["provider"],
            "target": alias["target"],
            "kind": alias["kind"],
            "capabilities": alias["capabilities"],
            "tool_call_tested": bool(alias.get("tool_call_tested")),
        },
    }


@app.after_request
def add_cors_headers(response: Response) -> Response:
    response.headers.setdefault("Access-Control-Allow-Origin", "*")
    response.headers.setdefault("Access-Control-Allow-Headers", "Authorization, Content-Type, Accept, Anthropic-Version, Anthropic-Beta")
    response.headers.setdefault("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    response.headers.setdefault("X-Request-Id", request_id())
    return response


@app.route("/", methods=["GET"])
def root() -> Response:
    return response_json({"service": SERVICE_NAME, "ok": True, "endpoints": ["/healthz", "/v1/models", "/v1/messages", "/v1/messages/count_tokens", "/v1/chat/completions"]})


@app.route("/healthz", methods=["GET"])
def healthz() -> Response:
    return response_json({"status": "ok", "service": SERVICE_NAME, "upstream_base_url": LIGHTNING_BASE_URL, "models": len(MODELS)})


@app.route("/v1/models", methods=["GET"])
def models() -> Response:
    auth_error = authorize()
    if auth_error is not None:
        return auth_error
    return response_json({"object": "list", "data": [public_model_entry(item) for item in MODELS]})


@app.route("/v1/messages/count_tokens", methods=["POST"])
def count_tokens() -> Response:
    auth_error = authorize()
    if auth_error is not None:
        return auth_error
    body, json_error = parse_json_body()
    if json_error is not None:
        return json_error
    alias = resolve_model(body.get("model"))
    if alias is None:
        return error_response("model not available in redlightningclaude", 404, "model_not_found")
    return response_json({"input_tokens": estimate_tokens(body)})


@app.route("/v1/messages", methods=["POST"])
def anthropic_messages() -> Response:
    auth_error = authorize()
    if auth_error is not None:
        return auth_error
    if not KEY_POOL.has_keys():
        return error_response("lightning api key not configured", 503, "configuration_error")
    body, json_error = parse_json_body()
    if json_error is not None:
        return json_error
    alias = resolve_model(body.get("model"))
    if alias is None:
        return error_response("model not available in redlightningclaude", 404, "model_not_found")
    payload = anthropic_to_openai_payload(body, alias)
    stream = bool(body.get("stream"))
    upstream = proxy_openai_chat_with_context_retry(
        payload,
        stream=stream,
        context_window=int(alias["context_window"]),
        input_tokens=estimate_tokens(body),
    )
    if upstream.status_code >= 400:
        try:
            body_text = upstream.text
        except Exception:
            body_text = ""
        return error_response(lightning_error_message(upstream.status_code, body_text), 502 if upstream.status_code >= 500 else upstream.status_code, "upstream_error")
    if stream:
        return Response(anthropic_sse_from_openai_stream(upstream, alias["id"]), status=200, content_type="text/event-stream; charset=utf-8")
    try:
        data = upstream.json()
    except Exception:
        return error_response("invalid upstream JSON", 502, "upstream_error")
    return response_json(anthropic_message_from_openai(data, alias["id"]))


@app.route("/v1/chat/completions", methods=["POST"])
def openai_chat_completions() -> Response:
    auth_error = authorize()
    if auth_error is not None:
        return auth_error
    if not KEY_POOL.has_keys():
        return error_response("lightning api key not configured", 503, "configuration_error")
    body, json_error = parse_json_body()
    if json_error is not None:
        return json_error
    alias = resolve_model(body.get("model"))
    if alias is None:
        return error_response("model not available in redlightningclaude", 404, "model_not_found")
    payload = deepcopy(body)
    payload["model"] = alias["target"]
    stream = bool(payload.get("stream"))
    upstream = proxy_openai_chat_with_context_retry(
        payload,
        stream=stream,
        context_window=int(alias["context_window"]),
        input_tokens=estimate_openai_tokens(payload),
    )
    if upstream.status_code >= 400:
        try:
            body_text = upstream.text
        except Exception:
            body_text = ""
        return error_response(lightning_error_message(upstream.status_code, body_text), 502 if upstream.status_code >= 500 else upstream.status_code, "upstream_error")
    if not stream:
        return Response(upstream.content, status=200, content_type="application/json")

    def generate():
        for chunk in upstream.iter_content(chunk_size=8192):
            if chunk:
                yield chunk

    return Response(generate(), status=200, content_type="text/event-stream; charset=utf-8")


@app.route("/<path:path>", methods=["OPTIONS"])
def options_passthrough(path: str) -> Response:
    return Response("", status=204)


if __name__ == "__main__":
    ssl_context = None
    if TLS_CERT and TLS_KEY and os.path.exists(TLS_CERT) and os.path.exists(TLS_KEY):
        ssl_context = (TLS_CERT, TLS_KEY)
    app.run(host=HOST, port=PORT, threaded=True, ssl_context=ssl_context)
