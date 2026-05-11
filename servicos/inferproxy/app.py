from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

import requests
from flask import Flask, Response, jsonify, request


SERVICE_NAME = "inferproxy"
HOST = os.getenv("INFERPROXY_HOST", "127.0.0.1")
PORT = int(os.getenv("INFERPROXY_PORT", "5066"))
INFERALL_BASE_URL = os.getenv("INFERPROXY_INFERALL_BASE_URL", "https://api.inferall.ai").rstrip("/")
INFERALL_API_KEY = os.getenv("INFERALL_API_KEY", "").strip()
INBOUND_TOKENS = {
    item.strip()
    for item in os.getenv("INFERPROXY_AUTH_TOKENS", os.getenv("INFERPROXY_AUTH_TOKEN", "")).replace(";", ",").split(",")
    if item.strip()
}
CONNECT_TIMEOUT = int(os.getenv("INFERPROXY_CONNECT_TIMEOUT", "20"))
READ_TIMEOUT = int(os.getenv("INFERPROXY_READ_TIMEOUT", "360"))
STREAM_CHUNK_SIZE = max(1, int(os.getenv("INFERPROXY_STREAM_CHUNK_SIZE", "1")))
UPSTREAM_MODE = os.getenv("INFERPROXY_UPSTREAM_MODE", "messages").strip().lower()
COMPACT_CLAUDE_TOOLS = os.getenv("INFERPROXY_COMPACT_CLAUDE_TOOLS", "1").strip().lower() not in {"0", "false", "no", "off"}
UPSTREAM_RETRY_ATTEMPTS = max(1, int(os.getenv("INFERPROXY_UPSTREAM_RETRY_ATTEMPTS", "2")))
UPSTREAM_RETRY_SLEEP = max(0.0, float(os.getenv("INFERPROXY_UPSTREAM_RETRY_SLEEP", "0.8")))
ENABLE_MODEL_FALLBACK = os.getenv("INFERPROXY_ENABLE_MODEL_FALLBACK", "0").strip().lower() not in {"0", "false", "no", "off"}
FALLBACK_MODEL_IDS = [
    item.strip()
    for item in os.getenv("INFERPROXY_FALLBACK_MODELS", "").split(",")
    if item.strip()
]
FAILURE_DUMP_PATH = os.getenv("INFERPROXY_FAILURE_DUMP_PATH", "/var/log/inferproxy_failed_requests.jsonl")
FAILURE_DUMP_FULL_TOOLS = os.getenv("INFERPROXY_FAILURE_DUMP_FULL_TOOLS", "1").strip().lower() not in {"0", "false", "no", "off"}
PRESERVE_ORIGINAL_TOOLS_IN_SYSTEM = os.getenv("INFERPROXY_PRESERVE_ORIGINAL_TOOLS_IN_SYSTEM", "0").strip().lower() not in {"0", "false", "no", "off"}
OPUS_ABORT_RETRY_WITHOUT_THINKING = os.getenv("INFERPROXY_OPUS_ABORT_RETRY_WITHOUT_THINKING", "1").strip().lower() not in {"0", "false", "no", "off"}
OPUS_ABORT_RETRY_ATTEMPTS = max(1, int(os.getenv("INFERPROXY_OPUS_ABORT_RETRY_ATTEMPTS", "3")))
OPUS_DISABLE_THINKING_AFTER_TOOLS = {
    item.strip()
    for item in os.getenv("INFERPROXY_OPUS_DISABLE_THINKING_AFTER_TOOLS", "Write,Edit,NotebookEdit").split(",")
    if item.strip()
}
DEFAULT_BLOCKED_TOOL_NAMES = {
    # InferAll's Anthropic route currently rejects schemas containing a `title`
    # input property. These two Claude Desktop housekeeping tools are optional,
    # and removing them preserves the rest of the Code/Desktop tool surface.
    "mcp__ccd_session__mark_chapter",
    "mcp__ccd_session__spawn_task",
}
BLOCKED_TOOL_NAMES = {
    item.strip()
    for item in os.getenv("INFERPROXY_BLOCKED_TOOL_NAMES", ",".join(sorted(DEFAULT_BLOCKED_TOOL_NAMES))).split(",")
    if item.strip()
}


MODEL_ALIASES: list[dict[str, Any]] = [
    {
        "id": "Kimi 2.6",
        "provider": "nvidia",
        "target": "moonshotai/kimi-k2.6",
        "context_window": 200_000,
    },
    {
        "id": "Qwen 3.6 Coder 480B",
        "provider": "nvidia",
        "target": "qwen/qwen3-coder-480b-a35b-instruct",
        "context_window": 200_000,
    },
    {
        "id": "Sonnet 4.6",
        "provider": "anthropic",
        "target": "claude-sonnet-4-6-20250327",
        "context_window": 200_000,
    },
    {
        "id": "Opus 4.6",
        "provider": "anthropic",
        "target": "claude-opus-4-6-20250327",
        "context_window": 200_000,
    },
]

PROVIDER_PREFIXES = {
    "anthropic",
    "gemini",
    "google",
    "minimax",
    "nvidia",
    "openai",
    "replicate",
    "runway",
}

app = Flask(__name__)
http = requests.Session()
logging.basicConfig(level=os.getenv("INFERPROXY_LOG_LEVEL", "INFO").upper(), format="%(asctime)s %(levelname)s %(message)s")
app.logger.setLevel(os.getenv("INFERPROXY_LOG_LEVEL", "INFO").upper())
logging.getLogger("werkzeug").setLevel(os.getenv("INFERPROXY_WERKZEUG_LOG_LEVEL", "WARNING").upper())


def now_s() -> int:
    return int(time.time())


def auth_ok() -> bool:
    if not INBOUND_TOKENS:
        return True
    header = request.headers.get("authorization") or request.headers.get("x-api-key") or ""
    token = header.removeprefix("Bearer").strip() if header.lower().startswith("bearer") else header.strip()
    return token in INBOUND_TOKENS


def require_auth() -> Response | None:
    if auth_ok():
        return None
    return jsonify({"type": "error", "error": {"type": "authentication_error", "message": "invalid inferproxy token"}}), 401


def default_alias() -> dict[str, Any]:
    return MODEL_ALIASES[0]


def resolve_model(model_id: Any) -> dict[str, Any]:
    raw = str(model_id or "").strip()
    lowered = raw.lower()
    for item in MODEL_ALIASES:
        if lowered == item["id"].lower() or lowered == item["target"].lower():
            return deepcopy(item)
    if "/" in raw:
        provider, target = raw.split("/", 1)
        if provider.lower() in PROVIDER_PREFIXES and target:
            return {
                "id": raw,
                "provider": provider.lower(),
                "target": target,
                "context_window": 200_000,
            }
    alias = deepcopy(default_alias())
    alias["requested_model"] = raw
    return alias


def fallback_aliases(primary: dict[str, Any]) -> list[dict[str, Any]]:
    aliases: list[dict[str, Any]] = [deepcopy(primary)]
    if not ENABLE_MODEL_FALLBACK:
        return aliases
    seen = {str(primary.get("target") or primary.get("id") or "").lower()}
    for model_id in FALLBACK_MODEL_IDS:
        alias = resolve_model(model_id)
        key = str(alias.get("target") or alias.get("id") or "").lower()
        if key and key not in seen:
            seen.add(key)
            aliases.append(alias)
    return aliases


def should_retry_upstream(status_code: int) -> bool:
    return status_code in {408, 409, 425, 429, 500, 502, 503, 504}


def request_summary(body: dict[str, Any]) -> dict[str, Any]:
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    return {
        "bytes": len(raw),
        "messages": len(body.get("messages") or []),
        "tools": len(body.get("tools") or []),
        "stream": bool(body.get("stream")),
        "thinking": bool(body.get("thinking")),
        "output_config": bool(body.get("output_config")),
        "metadata": bool(body.get("metadata")),
    }


def json_size(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    except Exception:
        return 0


def short_text(value: Any, limit: int = 400) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit] + f"...[+{len(text) - limit}]"


def safe_request_headers() -> dict[str, Any]:
    try:
        return {
            "user_agent": request.headers.get("user-agent", ""),
            "anthropic_version": request.headers.get("anthropic-version", ""),
            "anthropic_beta": request.headers.get("anthropic-beta", ""),
            "content_type": request.headers.get("content-type", ""),
            "content_length": request.headers.get("content-length", ""),
            "query_string": request.query_string.decode("utf-8", "replace"),
        }
    except RuntimeError:
        return {}


def content_shape(content: Any) -> Any:
    if isinstance(content, str):
        return {"kind": "string", "len": len(content)}
    if isinstance(content, list):
        output: list[dict[str, Any]] = []
        for item in content:
            if isinstance(item, dict):
                item_type = str(item.get("type") or "")
                row: dict[str, Any] = {"type": item_type}
                if item_type == "text":
                    row["text_len"] = len(str(item.get("text") or ""))
                elif item_type == "thinking":
                    row["thinking_len"] = len(str(item.get("thinking") or ""))
                    row["has_signature"] = bool(item.get("signature"))
                elif item_type == "tool_use":
                    row["name"] = str(item.get("name") or "")
                    row["input_keys"] = sorted((item.get("input") or {}).keys()) if isinstance(item.get("input"), dict) else []
                elif item_type == "tool_result":
                    row["tool_use_id"] = str(item.get("tool_use_id") or "")
                    row["content_shape"] = content_shape(item.get("content"))
                elif item_type == "image":
                    source = item.get("source") if isinstance(item.get("source"), dict) else {}
                    row["source_type"] = source.get("type")
                    row["media_type"] = source.get("media_type")
                else:
                    row["keys"] = sorted(item.keys())
                output.append(row)
            else:
                output.append({"type": type(item).__name__, "len": len(str(item))})
        return output
    if content is None:
        return {"kind": "none"}
    return {"kind": type(content).__name__, "size": json_size(content)}


def message_shapes(messages: Any) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    if not isinstance(messages, list):
        return output
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            output.append({"index": index, "kind": type(message).__name__})
            continue
        output.append(
            {
                "index": index,
                "role": message.get("role"),
                "keys": sorted(message.keys()),
                "content_shape": content_shape(message.get("content")),
            }
        )
    return output


def system_shape(system: Any) -> Any:
    if isinstance(system, str):
        return {"kind": "string", "len": len(system)}
    if isinstance(system, list):
        return [
            {
                "type": block.get("type") if isinstance(block, dict) else type(block).__name__,
                "text_len": len(str(block.get("text") or "")) if isinstance(block, dict) else len(str(block)),
                "keys": sorted(block.keys()) if isinstance(block, dict) else [],
            }
            for block in system
        ]
    if system is None:
        return {"kind": "none"}
    return {"kind": type(system).__name__, "size": json_size(system)}


def schema_snapshot(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {"kind": type(schema).__name__}
    properties = schema.get("properties")
    prop_names = sorted(properties.keys()) if isinstance(properties, dict) else []
    return {
        "type": schema.get("type"),
        "keys": sorted(schema.keys()),
        "property_count": len(prop_names),
        "property_names": prop_names[:80],
        "required": schema.get("required") if isinstance(schema.get("required"), list) else None,
        "additional_properties_type": type(schema.get("additionalProperties")).__name__ if "additionalProperties" in schema else None,
        "size": json_size(schema),
    }


def tool_snapshots(tools: Any) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    if not isinstance(tools, list):
        return output
    for index, tool in enumerate(tools):
        if not isinstance(tool, dict):
            output.append({"index": index, "kind": type(tool).__name__})
            continue
        schema = tool.get("input_schema") or tool.get("parameters")
        output.append(
            {
                "index": index,
                "name": str(tool.get("name") or ""),
                "name_valid_anthropic": bool(re.fullmatch(r"[A-Za-z0-9_-]{1,128}", str(tool.get("name") or ""))),
                "description_len": len(str(tool.get("description") or "")),
                "keys": sorted(tool.keys()),
                "schema": schema_snapshot(schema),
            }
        )
    return output


def filter_upstream_tools(tools: Any) -> list[dict[str, Any]]:
    if not isinstance(tools, list):
        return []
    output: list[dict[str, Any]] = []
    filtered: list[str] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = str(tool.get("name") or "")
        if name in BLOCKED_TOOL_NAMES:
            filtered.append(name)
            continue
        output.append(tool)
    if filtered:
        app.logger.warning("messages filtered_tools_for_upstream count=%d names=%s", len(filtered), ",".join(filtered))
    return output


def is_opus_alias(alias: dict[str, Any]) -> bool:
    text = f"{alias.get('id', '')} {alias.get('target', '')}".lower()
    return "opus" in text


def tool_use_names_by_id(messages: Any) -> dict[str, str]:
    names: dict[str, str] = {}
    if not isinstance(messages, list):
        return names
    for message in messages:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "tool_use":
                continue
            tool_id = str(item.get("id") or "")
            name = str(item.get("name") or "")
            if tool_id and name:
                names[tool_id] = name
    return names


def last_tool_result_names(messages: Any) -> set[str]:
    if not isinstance(messages, list) or not messages:
        return set()
    id_to_name = tool_use_names_by_id(messages)
    last = messages[-1]
    if not isinstance(last, dict):
        return set()
    content = last.get("content")
    if not isinstance(content, list):
        return set()
    names: set[str] = set()
    for item in content:
        if not isinstance(item, dict) or item.get("type") != "tool_result":
            continue
        tool_use_id = str(item.get("tool_use_id") or "")
        name = id_to_name.get(tool_use_id)
        if name:
            names.add(name)
    return names


def should_disable_opus_post_tool_thinking(body: dict[str, Any], alias: dict[str, Any]) -> tuple[bool, set[str]]:
    if not body.get("thinking") or not is_opus_alias(alias):
        return False, set()
    names = last_tool_result_names(body.get("messages"))
    matched = names.intersection(OPUS_DISABLE_THINKING_AFTER_TOOLS)
    return bool(matched), matched


def remove_thinking_for_opus_if_needed(payload: dict[str, Any], original_body: dict[str, Any], alias: dict[str, Any]) -> None:
    should_disable, matched = should_disable_opus_post_tool_thinking(original_body, alias)
    if not should_disable:
        return
    if payload.pop("thinking", None) is not None:
        app.logger.warning(
            "messages disabled_opus_thinking_after_tool model=%s tools=%s",
            alias.get("id"),
            ",".join(sorted(matched)),
        )


def is_inferall_operation_aborted(text: str) -> bool:
    lowered = str(text or "").lower()
    return "operation was aborted" in lowered or "this operation was aborted" in lowered


def dump_failed_request(
    *,
    body: dict[str, Any],
    payload: dict[str, Any],
    alias: dict[str, Any],
    status: int,
    upstream_body: str,
    started: float,
    note: str,
) -> str:
    dump_id = f"fail_{int(time.time())}_{uuid.uuid4().hex[:10]}"
    record: dict[str, Any] = {
        "id": dump_id,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "service": SERVICE_NAME,
        "note": note,
        "status": status,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "alias": {"id": alias.get("id"), "target": alias.get("target"), "provider": alias.get("provider")},
        "request_headers": safe_request_headers(),
        "incoming_summary": request_summary(body),
        "payload_summary": request_summary(payload),
        "incoming_keys": sorted(body.keys()),
        "payload_keys": sorted(payload.keys()),
        "incoming_system_shape": system_shape(body.get("system")),
        "payload_system_shape": system_shape(payload.get("system")),
        "incoming_message_shapes": message_shapes(body.get("messages")),
        "payload_message_shapes": message_shapes(payload.get("messages")),
        "incoming_tool_snapshots": tool_snapshots(body.get("tools")),
        "payload_tool_snapshots": tool_snapshots(payload.get("tools")),
        "tool_choice": body.get("tool_choice"),
        "thinking": body.get("thinking"),
        "output_config": body.get("output_config"),
        "metadata": body.get("metadata"),
        "upstream_body_preview": short_text(upstream_body, 1200),
    }
    if FAILURE_DUMP_FULL_TOOLS:
        record["incoming_tools_full"] = body.get("tools") if isinstance(body.get("tools"), list) else []
        record["payload_tools_full"] = payload.get("tools") if isinstance(payload.get("tools"), list) else []
    try:
        dump_path = Path(FAILURE_DUMP_PATH)
        dump_path.parent.mkdir(parents=True, exist_ok=True)
        with dump_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    except Exception as exc:
        app.logger.warning("failed_request_dump_write_error id=%s path=%s error=%s", dump_id, FAILURE_DUMP_PATH, exc)
    return dump_id


def anthropic_system_text(body: dict[str, Any]) -> str:
    system = body.get("system")
    if isinstance(system, str):
        return system
    if isinstance(system, list):
        parts: list[str] = []
        for block in system:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
            else:
                parts.append(json.dumps(block, ensure_ascii=False, separators=(",", ":")))
        return "\n\n".join(part for part in parts if part)
    if system is None:
        return ""
    return json.dumps(system, ensure_ascii=False, separators=(",", ":"))


def image_source_to_url(source: Any) -> str | None:
    if not isinstance(source, dict):
        return None
    source_type = str(source.get("type") or "").strip()
    if source_type == "url" and source.get("url"):
        return str(source["url"])
    if source_type == "base64" and source.get("data"):
        media_type = str(source.get("media_type") or "image/png")
        return f"data:{media_type};base64,{source['data']}"
    return None


def text_from_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if not isinstance(item, dict):
                parts.append(json.dumps(item, ensure_ascii=False, separators=(",", ":")))
                continue
            item_type = str(item.get("type") or "")
            if item_type == "text":
                parts.append(str(item.get("text") or ""))
            elif item_type == "thinking":
                parts.append(str(item.get("thinking") or ""))
            elif item_type == "tool_result":
                parts.append(text_from_content(item.get("content")))
            elif item_type == "image":
                parts.append("[image]")
            else:
                parts.append(json.dumps(item, ensure_ascii=False, separators=(",", ":")))
        return "\n".join(part for part in parts if part)
    return json.dumps(content, ensure_ascii=False, separators=(",", ":"))


def content_block_to_openai_part(block: dict[str, Any]) -> dict[str, Any] | None:
    block_type = str(block.get("type") or "")
    if block_type == "text":
        return {"type": "text", "text": str(block.get("text") or "")}
    if block_type == "thinking":
        return {"type": "text", "text": str(block.get("thinking") or "")}
    if block_type == "image":
        url = image_source_to_url(block.get("source"))
        if url:
            return {"type": "image_url", "image_url": {"url": url}}
        return {"type": "text", "text": json.dumps(block, ensure_ascii=False, separators=(",", ":"))}
    return None


def anthropic_messages_to_openai(body: dict[str, Any]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    system_text = anthropic_system_text(body)
    if system_text:
        messages.append({"role": "system", "content": system_text})

    for message in body.get("messages") or []:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "user")
        content = message.get("content")
        if isinstance(content, str):
            messages.append({"role": role, "content": content})
            continue
        if not isinstance(content, list):
            messages.append({"role": role, "content": text_from_content(content)})
            continue

        if role == "assistant":
            text_parts: list[dict[str, Any]] = []
            tool_calls: list[dict[str, Any]] = []
            for block in content:
                if not isinstance(block, dict):
                    text_parts.append({"type": "text", "text": text_from_content(block)})
                    continue
                block_type = str(block.get("type") or "")
                if block_type == "tool_use":
                    tool_calls.append(
                        {
                            "id": str(block.get("id") or f"call_{uuid.uuid4().hex[:10]}"),
                            "type": "function",
                            "function": {
                                "name": str(block.get("name") or ""),
                                "arguments": json.dumps(block.get("input") or {}, ensure_ascii=False, separators=(",", ":")),
                            },
                        }
                    )
                    continue
                part = content_block_to_openai_part(block)
                if part:
                    text_parts.append(part)
                else:
                    text_parts.append({"type": "text", "text": json.dumps(block, ensure_ascii=False, separators=(",", ":"))})

            assistant_message: dict[str, Any] = {"role": "assistant"}
            if text_parts:
                assistant_message["content"] = text_from_content(text_parts)
            else:
                assistant_message["content"] = ""
            if tool_calls:
                assistant_message["tool_calls"] = tool_calls
            messages.append(assistant_message)
            continue

        pending_parts: list[dict[str, Any]] = []
        for block in content:
            if not isinstance(block, dict):
                pending_parts.append({"type": "text", "text": text_from_content(block)})
                continue
            block_type = str(block.get("type") or "")
            if block_type == "tool_result":
                if pending_parts:
                    messages.append({"role": role, "content": openai_content_value(pending_parts)})
                    pending_parts = []
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": str(block.get("tool_use_id") or f"call_{uuid.uuid4().hex[:10]}"),
                        "content": text_from_content(block.get("content")),
                    }
                )
                continue
            part = content_block_to_openai_part(block)
            if part:
                pending_parts.append(part)
            else:
                pending_parts.append({"type": "text", "text": json.dumps(block, ensure_ascii=False, separators=(",", ":"))})
        if pending_parts:
            messages.append({"role": role, "content": openai_content_value(pending_parts)})

    return messages


def openai_content_value(parts: list[dict[str, Any]]) -> str | list[dict[str, Any]]:
    if any(part.get("type") == "image_url" for part in parts):
        return parts
    return text_from_content(parts)


def tool_schema_to_openai(tool: dict[str, Any]) -> dict[str, Any]:
    if tool.get("type") == "function" and isinstance(tool.get("function"), dict):
        return deepcopy(tool)
    name = str(tool.get("name") or "")
    description = str(tool.get("description") or "")
    parameters = deepcopy(tool.get("input_schema") or tool.get("parameters") or {"type": "object", "properties": {}})
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
        },
    }


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
        if choice_type == "tool" and value.get("name"):
            return {"type": "function", "function": {"name": str(value["name"])}}
    return value


def inferall_payload_from_anthropic(body: dict[str, Any], alias: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "provider": alias["provider"],
        "operation": "chat",
        "model": alias["target"],
        "messages": anthropic_messages_to_openai(body),
        "max_tokens": body.get("max_tokens") or 2048,
        "stream": bool(body.get("stream")),
    }
    for key in ("temperature", "top_p", "stop"):
        if key in body:
            payload[key] = deepcopy(body[key])
    if isinstance(body.get("tools"), list) and body["tools"]:
        payload["tools"] = [tool_schema_to_openai(tool) for tool in filter_upstream_tools(body["tools"]) if isinstance(tool, dict)]
    if "tool_choice" in body:
        payload["tool_choice"] = anthropic_tool_choice_to_openai(body.get("tool_choice"))
    if isinstance(body.get("metadata"), dict):
        payload["metadata"] = deepcopy(body["metadata"])
    output_config = body.get("output_config")
    if isinstance(output_config, dict) and output_config.get("effort"):
        payload["reasoning_effort"] = str(output_config["effort"])
    thinking = body.get("thinking")
    if isinstance(thinking, dict) and str(thinking.get("type") or "").lower() not in {"", "disabled", "none"}:
        payload["enable_thinking"] = True
        payload["thinking"] = deepcopy(thinking)
    return payload


def inferall_headers() -> dict[str, str]:
    if not INFERALL_API_KEY:
        raise RuntimeError("INFERALL_API_KEY is required")
    try:
        anthropic_version = request.headers.get("anthropic-version", "2023-06-01")
        anthropic_beta = request.headers.get("anthropic-beta", "")
    except RuntimeError:
        anthropic_version = "2023-06-01"
        anthropic_beta = ""
    return {
        "Authorization": f"Bearer {INFERALL_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Connection": "close",
        "anthropic-version": anthropic_version,
        "anthropic-beta": anthropic_beta,
        "User-Agent": "RED InferProxy/0.1",
    }


def close_after_iter(response: requests.Response, chunks: Iterable[bytes | str]) -> Iterable[bytes | str]:
    try:
        yield from chunks
    finally:
        safe_close_response(response)


def safe_close_response(response: Any) -> None:
    close = getattr(response, "close", None)
    if callable(close):
        close()


def upstream_generate(payload: dict[str, Any], *, stream: bool) -> requests.Response:
    return http.post(
        f"{INFERALL_BASE_URL}/ai/v1/generate",
        headers=inferall_headers(),
        json=payload,
        stream=stream,
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
    )


def inferall_anthropic_payload(body: dict[str, Any], alias: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(body)
    payload["model"] = alias["target"]
    if COMPACT_CLAUDE_TOOLS and isinstance(payload.get("tools"), list) and payload["tools"]:
        original_tools = deepcopy(filter_upstream_tools(payload["tools"]))
        payload["tools"] = [compact_anthropic_tool(tool) for tool in original_tools if isinstance(tool, dict)]
        if PRESERVE_ORIGINAL_TOOLS_IN_SYSTEM:
            preserve_original_tools_in_system(payload, original_tools)
    elif isinstance(payload.get("tools"), list) and payload["tools"]:
        payload["tools"] = filter_upstream_tools(payload["tools"])
    remove_thinking_for_opus_if_needed(payload, body, alias)
    return payload


def compact_json_schema(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}
    schema_type = schema.get("type") or "object"
    output: dict[str, Any] = {"type": schema_type}
    properties = schema.get("properties")
    if isinstance(properties, dict):
        output["properties"] = {}
        for name, value in properties.items():
            if isinstance(value, dict):
                item: dict[str, Any] = {"type": value.get("type") or "string"}
                if "enum" in value:
                    item["enum"] = deepcopy(value["enum"])
                if "items" in value:
                    item["items"] = compact_json_schema(value["items"])
                if isinstance(value.get("properties"), dict):
                    nested = compact_json_schema(value)
                    item.update(nested)
                output["properties"][name] = item
            else:
                output["properties"][name] = {"type": "string"}
    else:
        output["properties"] = {}
    if isinstance(schema.get("required"), list):
        output["required"] = deepcopy(schema["required"])
    if "additionalProperties" in schema and isinstance(schema.get("additionalProperties"), bool):
        output["additionalProperties"] = schema["additionalProperties"]
    return output


def compact_anthropic_tool(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(tool.get("name") or ""),
        "description": str(tool.get("description") or ""),
        "input_schema": compact_json_schema(tool.get("input_schema") or tool.get("parameters") or {}),
    }


def preserve_original_tools_in_system(payload: dict[str, Any], original_tools: list[dict[str, Any]]) -> None:
    text = (
        "Original Claude Code tool schemas preserved for semantic fidelity. "
        "The API-level tool schemas may be compacted for provider compatibility; "
        "use these original definitions to understand exact tool behavior:\n"
        + json.dumps(original_tools, ensure_ascii=False, separators=(",", ":"))
    )
    system = payload.get("system")
    block = {"type": "text", "text": text}
    if isinstance(system, list):
        payload["system"] = [*system, block]
    elif isinstance(system, str) and system:
        payload["system"] = [{"type": "text", "text": system}, block]
    elif system:
        payload["system"] = [{"type": "text", "text": json.dumps(system, ensure_ascii=False, separators=(",", ":"))}, block]
    else:
        payload["system"] = [block]


def upstream_messages(payload: dict[str, Any], *, stream: bool) -> requests.Response:
    return http.post(
        f"{INFERALL_BASE_URL}/v1/messages",
        headers=inferall_headers(),
        json=payload,
        stream=stream,
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
    )


def error_response(status: int, message: str, upstream_body: str = "") -> Response:
    payload = {
        "type": "error",
        "error": {
            "type": "upstream_error",
            "message": message,
        },
    }
    if upstream_body:
        payload["error"]["upstream_body"] = upstream_body[:1200]
    return jsonify(payload), status


def build_messages_payload(body: dict[str, Any], alias: dict[str, Any]) -> dict[str, Any]:
    if UPSTREAM_MODE == "generate":
        return inferall_payload_from_anthropic(body, alias)
    return inferall_anthropic_payload(body, alias)


def post_upstream_messages_with_fallback(body: dict[str, Any], primary_alias: dict[str, Any]) -> tuple[requests.Response | None, dict[str, Any], str]:
    last_text = ""
    selected_alias = deepcopy(primary_alias)
    for alias in fallback_aliases(primary_alias):
        selected_alias = deepcopy(alias)
        payload = build_messages_payload(body, alias)
        stream = bool(payload.get("stream"))
        attempt_limit = UPSTREAM_RETRY_ATTEMPTS
        if is_opus_alias(alias) and not payload.get("thinking"):
            attempt_limit = max(attempt_limit, OPUS_ABORT_RETRY_ATTEMPTS)
        for attempt in range(1, attempt_limit + 1):
            try:
                upstream = upstream_generate(payload, stream=stream) if UPSTREAM_MODE == "generate" else upstream_messages(payload, stream=stream)
            except Exception as exc:
                last_text = str(exc)
                app.logger.warning(
                    "messages upstream_exception model=%s target=%s stream=%s attempt=%d/%d error=%s",
                    alias["id"],
                    alias["target"],
                    stream,
                    attempt,
                    attempt_limit,
                    exc,
                )
                if attempt < attempt_limit and UPSTREAM_RETRY_SLEEP:
                    time.sleep(UPSTREAM_RETRY_SLEEP)
                continue
            if upstream.status_code < 400:
                if alias["target"] != primary_alias["target"]:
                    app.logger.warning(
                        "messages fallback_success requested=%s fallback=%s target=%s",
                        primary_alias["id"],
                        alias["id"],
                        alias["target"],
                    )
                return upstream, alias, last_text
            last_text = upstream.text
            status = upstream.status_code
            safe_close_response(upstream)
            app.logger.warning(
                "messages upstream_error model=%s target=%s stream=%s status=%s attempt=%d/%d body=%s",
                alias["id"],
                alias["target"],
                stream,
                status,
                attempt,
                attempt_limit,
                last_text[:300],
            )
            if (
                OPUS_ABORT_RETRY_WITHOUT_THINKING
                and UPSTREAM_MODE == "messages"
                and is_opus_alias(alias)
                and payload.get("thinking")
                and is_inferall_operation_aborted(last_text)
            ):
                rescue_payload = deepcopy(payload)
                rescue_payload.pop("thinking", None)
                app.logger.warning(
                    "messages retrying_opus_abort_without_thinking model=%s target=%s",
                    alias["id"],
                    alias["target"],
                )
                try:
                    rescue = upstream_messages(rescue_payload, stream=stream)
                except Exception as exc:
                    last_text = str(exc)
                    app.logger.warning(
                        "messages opus_no_thinking_rescue_exception model=%s target=%s stream=%s error=%s",
                        alias["id"],
                        alias["target"],
                        stream,
                        exc,
                    )
                else:
                    if rescue.status_code < 400:
                        app.logger.warning(
                            "messages opus_no_thinking_rescue_success model=%s target=%s status=%s",
                            alias["id"],
                            alias["target"],
                            rescue.status_code,
                        )
                        return rescue, alias, last_text
                    last_text = rescue.text
                    status = rescue.status_code
                    safe_close_response(rescue)
                    app.logger.warning(
                        "messages opus_no_thinking_rescue_error model=%s target=%s status=%s body=%s",
                        alias["id"],
                        alias["target"],
                        status,
                        last_text[:300],
                    )
            if not should_retry_upstream(status):
                return upstream, alias, last_text
            if attempt < attempt_limit and UPSTREAM_RETRY_SLEEP:
                time.sleep(UPSTREAM_RETRY_SLEEP)
    return None, selected_alias, last_text


def estimate_tokens(body: dict[str, Any]) -> int:
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    return max(1, len(raw) // 4)


def text_from_openai_like(data: dict[str, Any]) -> str:
    if isinstance(data.get("text"), str):
        return data["text"]
    if isinstance(data.get("content"), str):
        return data["content"]
    if isinstance(data.get("response"), str):
        return data["response"]
    if isinstance(data.get("output"), str):
        return data["output"]
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return text_from_content(content)
        text = choices[0].get("text") if isinstance(choices[0], dict) else None
        if isinstance(text, str):
            return text
    return ""


def reasoning_from_openai_like(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict):
            for key in ("reasoning_content", "reasoning", "thinking"):
                if isinstance(message.get(key), str):
                    return message[key]
    for key in ("reasoning_content", "reasoning", "thinking"):
        if isinstance(data.get(key), str):
            return data[key]
    return ""


def tool_uses_from_openai_like(data: dict[str, Any]) -> list[dict[str, Any]]:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return []
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        return []
    output: list[dict[str, Any]] = []
    for call in message.get("tool_calls") or []:
        if not isinstance(call, dict):
            continue
        function = call.get("function") or {}
        args = function.get("arguments") or "{}"
        try:
            parsed_args = json.loads(args) if isinstance(args, str) else args
        except Exception:
            parsed_args = {"_raw": args}
        output.append(
            {
                "type": "tool_use",
                "id": str(call.get("id") or f"toolu_{uuid.uuid4().hex[:10]}"),
                "name": str(function.get("name") or ""),
                "input": parsed_args if isinstance(parsed_args, dict) else {"_value": parsed_args},
            }
        )
    return output


def anthropic_message_from_openai(data: dict[str, Any], model: str) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    reasoning = reasoning_from_openai_like(data)
    if reasoning:
        content.append({"type": "thinking", "thinking": reasoning, "signature": f"inferproxy:{uuid.uuid4().hex}"})
    text = text_from_openai_like(data)
    if text:
        content.append({"type": "text", "text": text})
    content.extend(tool_uses_from_openai_like(data))
    if not content:
        content.append({"type": "text", "text": ""})
    has_tool = any(block.get("type") == "tool_use" for block in content)
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    return {
        "id": str(data.get("id") or f"msg_{uuid.uuid4().hex}"),
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_reason": "tool_use" if has_tool else "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("completion_tokens") or usage.get("output_tokens") or 0),
        },
    }


def sse_event(name: str, data: dict[str, Any]) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"


def openai_delta_stream_to_anthropic(lines: Iterable[bytes | str], model: str) -> Iterable[str]:
    message_id = f"msg_{uuid.uuid4().hex}"
    yield sse_event(
        "message_start",
        {
            "type": "message_start",
            "message": {
                "id": message_id,
                "type": "message",
                "role": "assistant",
                "model": model,
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            },
        },
    )
    text_open = False
    text_index = 0
    tool_state: dict[int, dict[str, Any]] = {}
    for raw in lines:
        line = raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
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
        text = delta.get("content")
        if isinstance(text, str) and text:
            if not text_open:
                text_open = True
                yield sse_event("content_block_start", {"type": "content_block_start", "index": text_index, "content_block": {"type": "text", "text": ""}})
            yield sse_event("content_block_delta", {"type": "content_block_delta", "index": text_index, "delta": {"type": "text_delta", "text": text}})
        for tool_delta in delta.get("tool_calls") or []:
            index = int(tool_delta.get("index") or 0)
            state = tool_state.setdefault(index, {"id": str(tool_delta.get("id") or f"toolu_{uuid.uuid4().hex[:10]}"), "name": "", "arguments": []})
            if tool_delta.get("id"):
                state["id"] = str(tool_delta["id"])
            function = tool_delta.get("function") or {}
            if function.get("name"):
                state["name"] = str(function["name"])
            if function.get("arguments") is not None:
                state["arguments"].append(str(function.get("arguments") or ""))
    if text_open:
        yield sse_event("content_block_stop", {"type": "content_block_stop", "index": text_index})
    next_index = 1 if text_open else 0
    for index in sorted(tool_state):
        state = tool_state[index]
        args = "".join(state["arguments"])
        try:
            parsed = json.loads(args) if args else {}
        except Exception:
            parsed = {"_raw": args}
        yield sse_event(
            "content_block_start",
            {
                "type": "content_block_start",
                "index": next_index,
                "content_block": {
                    "type": "tool_use",
                    "id": state["id"],
                    "name": state["name"],
                    "input": parsed if isinstance(parsed, dict) else {"_value": parsed},
                },
            },
        )
        yield sse_event("content_block_stop", {"type": "content_block_stop", "index": next_index})
        next_index += 1
    yield sse_event(
        "message_delta",
        {"type": "message_delta", "delta": {"stop_reason": "tool_use" if tool_state else "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 0}},
    )
    yield sse_event("message_stop", {"type": "message_stop"})


@app.get("/health")
@app.get("/ai/v1/health")
def health() -> Response:
    return jsonify({"ok": True, "service": SERVICE_NAME, "upstream": INFERALL_BASE_URL, "mode": UPSTREAM_MODE, "ts": now_s()})


@app.route("/", methods=["GET", "HEAD"])
def root() -> Response:
    return jsonify({"ok": True, "service": SERVICE_NAME})


@app.get("/v1/models")
def models() -> Response:
    err = require_auth()
    if err:
        return err
    return jsonify(
        {
            "object": "list",
            "data": [
                {
                    "id": item["id"],
                    "type": "model",
                    "display_name": item["id"],
                    "created_at": "2026-05-11T00:00:00Z",
                    "context_window": item["context_window"],
                    "max_tokens": 32_000,
                }
                for item in MODEL_ALIASES
            ],
        }
    )


@app.post("/v1/messages/count_tokens")
def count_tokens() -> Response:
    err = require_auth()
    if err:
        return err
    return jsonify({"input_tokens": estimate_tokens(request.get_json(silent=True) or {})})


@app.post("/v1/messages")
def messages() -> Response:
    err = require_auth()
    if err:
        return err
    started = time.monotonic()
    body = request.get_json(silent=True) or {}
    alias = resolve_model(body.get("model"))
    payload = build_messages_payload(body, alias)
    stream = bool(payload.get("stream"))
    summary = request_summary(body)
    app.logger.info(
        "messages start model=%s target=%s stream=%s mode=%s bytes=%d messages=%d tools=%d thinking=%s output_config=%s metadata=%s",
        alias["id"],
        alias["target"],
        stream,
        UPSTREAM_MODE,
        summary["bytes"],
        summary["messages"],
        summary["tools"],
        summary["thinking"],
        summary["output_config"],
        summary["metadata"],
    )
    upstream, alias, last_text = post_upstream_messages_with_fallback(body, alias)
    if upstream is None or upstream.status_code >= 400:
        status = upstream.status_code if upstream is not None else 502
        dump_id = dump_failed_request(
            body=body,
            payload=payload,
            alias=alias,
            status=status,
            upstream_body=last_text,
            started=started,
            note="messages_failed_after_retries",
        )
        app.logger.warning(
            "messages failed_after_retries model=%s stream=%s status=%s elapsed_ms=%d dump_id=%s",
            alias["id"],
            stream,
            status,
            int((time.monotonic() - started) * 1000),
            dump_id,
        )
        return error_response(status, "upstream provider temporary failure", last_text)
    if UPSTREAM_MODE != "generate":
        upstream_content = getattr(upstream, "content", None)
        if upstream_content is None:
            upstream_content = str(getattr(upstream, "text", "")).encode("utf-8")
        content_type = upstream.headers.get("Content-Type", "application/json")
        if stream:
            response = Response(
                close_after_iter(upstream, upstream.iter_content(chunk_size=STREAM_CHUNK_SIZE)),
                status=upstream.status_code,
                headers={"Content-Type": content_type},
            )
            response.call_on_close(lambda: safe_close_response(upstream))
            app.logger.info("messages stream_open model=%s status=%s elapsed_ms=%d", alias["id"], upstream.status_code, int((time.monotonic() - started) * 1000))
            return response
        safe_close_response(upstream)
        app.logger.info("messages complete model=%s status=%s elapsed_ms=%d bytes=%d", alias["id"], upstream.status_code, int((time.monotonic() - started) * 1000), len(upstream_content))
        return Response(upstream_content, status=upstream.status_code, headers={"Content-Type": content_type})
    if stream:
        response = Response(
            close_after_iter(upstream, openai_delta_stream_to_anthropic(upstream.iter_lines(decode_unicode=False, chunk_size=STREAM_CHUNK_SIZE), alias["id"])),
            mimetype="text/event-stream",
        )
        response.call_on_close(lambda: safe_close_response(upstream))
        app.logger.info("messages generate_stream_open model=%s status=%s elapsed_ms=%d", alias["id"], upstream.status_code, int((time.monotonic() - started) * 1000))
        return response
    try:
        data = upstream.json()
    except Exception:
        data = {"text": upstream.text}
    safe_close_response(upstream)
    app.logger.info("messages generate_complete model=%s status=%s elapsed_ms=%d", alias["id"], upstream.status_code, int((time.monotonic() - started) * 1000))
    return jsonify(anthropic_message_from_openai(data, alias["id"]))


@app.post("/v1/chat/completions")
def chat_completions() -> Response:
    err = require_auth()
    if err:
        return err
    started = time.monotonic()
    body = request.get_json(silent=True) or {}
    alias = resolve_model(body.get("model"))
    payload = {
        "provider": alias["provider"],
        "operation": "chat",
        "model": alias["target"],
        "messages": body.get("messages") or [],
        "max_tokens": body.get("max_tokens") or 2048,
        "stream": bool(body.get("stream")),
    }
    for key in ("temperature", "top_p", "stop", "tools", "tool_choice", "metadata", "reasoning_effort"):
        if key in body:
            payload[key] = deepcopy(body[key])
    try:
        upstream = upstream_generate(payload, stream=bool(payload["stream"]))
    except Exception as exc:
        app.logger.warning("chat_completions upstream_exception model=%s elapsed_ms=%d error=%s", alias["id"], int((time.monotonic() - started) * 1000), exc)
        return error_response(502, f"inferall request failed: {exc}")
    if upstream.status_code >= 400:
        text = upstream.text
        safe_close_response(upstream)
        app.logger.warning("chat_completions upstream_error model=%s status=%s elapsed_ms=%d body=%s", alias["id"], upstream.status_code, int((time.monotonic() - started) * 1000), text[:300])
        return error_response(upstream.status_code, "inferall rejected request", text)
    response = Response(
        close_after_iter(upstream, upstream.iter_content(chunk_size=STREAM_CHUNK_SIZE)),
        status=200,
        headers={"Content-Type": upstream.headers.get("Content-Type", "application/json")},
    )
    response.call_on_close(lambda: safe_close_response(upstream))
    app.logger.info("chat_completions stream_open model=%s status=%s elapsed_ms=%d", alias["id"], upstream.status_code, int((time.monotonic() - started) * 1000))
    return response


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, threaded=True)

