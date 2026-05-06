from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any

import requests
from flask import Flask, Response, jsonify, request


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "sim"}


def split_values(value: str) -> list[str]:
    items: list[str] = []
    for raw in (value or "").replace("\r", "\n").replace(";", "\n").replace(",", "\n").splitlines():
        item = raw.strip()
        if item:
            items.append(item)
    return items


def parse_statuses(value: str) -> set[int]:
    out: set[int] = set()
    for item in split_values(value):
        try:
            out.add(int(item))
        except ValueError:
            pass
    return out or {401, 402, 403, 408, 409, 429, 500, 502, 503, 504}


SERVICE_NAME = "redclaudeproxy"
UPSTREAM_BASE_URL = os.getenv(
    "REDCLAUDEPROXY_UPSTREAM_BASE_URL",
    os.getenv("REDCLAUDEPROXY_VERCEL_BASE_URL", "http://127.0.0.1:8080/v1"),
).rstrip("/")
HOST = os.getenv("REDCLAUDEPROXY_HOST", "127.0.0.1")
PORT = env_int("REDCLAUDEPROXY_PORT", 8096)
CONNECT_TIMEOUT = env_int("REDCLAUDEPROXY_CONNECT_TIMEOUT", 20)
READ_TIMEOUT = env_int("REDCLAUDEPROXY_READ_TIMEOUT", 360)
STREAM_CHUNK_SIZE = max(1, env_int("REDCLAUDEPROXY_STREAM_CHUNK_SIZE", 1))
RETRY_STATUSES = parse_statuses(os.getenv("REDCLAUDEPROXY_RETRY_STATUSES", "401,402,403,408,409,429,500,502,503,504"))
CORS_ENABLED = env_bool("REDCLAUDEPROXY_CORS", True)
INBOUND_TOKENS = set(split_values(os.getenv("REDCLAUDEPROXY_AUTH_TOKENS", os.getenv("REDCLAUDEPROXY_AUTH_TOKEN", ""))))
REQUIRE_AUTH = env_bool("REDCLAUDEPROXY_REQUIRE_AUTH", bool(INBOUND_TOKENS))
DATA_DIR = Path(os.getenv("REDCLAUDEPROXY_DATA_DIR", "/var/lib/redclaudeproxy"))
USAGE_FILE = Path(os.getenv("REDCLAUDEPROXY_USAGE_FILE", str(DATA_DIR / "usage.json")))
CLAUDE_UNKNOWN_MODEL_FALLBACK = env_bool("REDCLAUDEPROXY_CLAUDE_UNKNOWN_MODEL_FALLBACK", True)
CLAUDE_STICKY_TTL_SECONDS = env_int("REDCLAUDEPROXY_CLAUDE_STICKY_TTL_SECONDS", 6 * 60 * 60)
MODEL_REFRESH_TTL_SECONDS = max(15, env_int("REDCLAUDEPROXY_MODEL_REFRESH_TTL_SECONDS", 300))
MODEL_INCLUDE_PREFIXES = tuple(split_values(os.getenv("REDCLAUDEPROXY_MODEL_INCLUDE_PREFIXES", "claude-red-")))
MODEL_INCLUDE_ALL = env_bool("REDCLAUDEPROXY_MODEL_INCLUDE_ALL", False)
DEFAULT_MODEL_ID = os.getenv("REDCLAUDEPROXY_DEFAULT_MODEL", "claude-red-devstral-medium").strip().lower()

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "content-length",
    "content-encoding",
}

CLIENT_HEADER_ALLOWLIST = {
    "accept",
    "accept-language",
    "anthropic-beta",
    "anthropic-version",
    "content-type",
    "openai-beta",
    "user-agent",
    "x-stainless-arch",
    "x-stainless-lang",
    "x-stainless-os",
    "x-stainless-package-version",
    "x-stainless-runtime",
    "x-stainless-runtime-version",
}

CLAUDE_MODEL_ALIASES = [
    {
        "id": "alibaba/qwen-3.6-max-preview",
        "target": "alibaba/qwen-3.6-max-preview",
        "display_name": "Alibaba Qwen 3.6 Max Preview",
        "provider": "alibaba",
        "context_window": 200_000,
        "tool_call_tested": False,
        "note": "Modelo solicitado para o RED Proxy Pro; pendente de validacao completa de tool calling.",
    },
    {
        "id": "alibaba/qwen3.5-flash",
        "target": "alibaba/qwen3.5-flash",
        "display_name": "Alibaba Qwen 3.5 Flash",
        "provider": "alibaba",
        "context_window": 200_000,
        "tool_call_tested": False,
        "note": "Modelo solicitado para o RED Proxy Pro; pendente de validacao completa de tool calling.",
    },
    {
        "id": "alibaba/qwen3.5-plus",
        "target": "alibaba/qwen3.5-plus",
        "display_name": "Alibaba Qwen 3.5 Plus",
        "provider": "alibaba",
        "context_window": 200_000,
        "tool_call_tested": False,
        "note": "Modelo solicitado para o RED Proxy Pro; pendente de validacao completa de tool calling.",
    },
    {
        "id": "alibaba/qwen3.6-27b",
        "target": "alibaba/qwen3.6-27b",
        "display_name": "Alibaba Qwen 3.6 27B",
        "provider": "alibaba",
        "context_window": 200_000,
        "tool_call_tested": False,
        "note": "Modelo solicitado para o RED Proxy Pro; pendente de validacao completa de tool calling.",
    },
    {
        "id": "anthropic/claude-sonnet-4.5",
        "target": "anthropic/claude-sonnet-4.5",
        "display_name": "Anthropic Claude Sonnet 4.5",
        "provider": "anthropic",
        "context_window": 200_000,
        "tool_call_tested": False,
        "note": "Modelo solicitado para o RED Proxy Pro; pendente de validacao completa de tool calling.",
    },
    {
        "id": "anthropic/claude-sonnet-4.6",
        "target": "anthropic/claude-sonnet-4.6",
        "display_name": "Anthropic Claude Sonnet 4.6",
        "provider": "anthropic",
        "aliases": ["claude-red-sonnet-46"],
        "context_window": 200_000,
        "tool_call_tested": True,
        "note": "Modelo validado no RED Proxy Pro com chat e tool call real.",
    },
    {
        "id": "deepseek/deepseek-v4-pro",
        "target": "deepseek/deepseek-v4-pro",
        "display_name": "DeepSeek V4 Pro",
        "provider": "deepseek",
        "context_window": 200_000,
        "tool_call_tested": False,
        "note": "Modelo solicitado para o RED Proxy Pro; pendente de validacao completa de tool calling.",
    },
    {
        "id": "google/gemini-3.1-pro-preview",
        "target": "google/gemini-3.1-pro-preview",
        "display_name": "Google Gemini 3.1 Pro Preview",
        "provider": "google",
        "context_window": 1_000_000,
        "tool_call_tested": False,
        "note": "Modelo solicitado para o RED Proxy Pro; pendente de validacao completa de tool calling.",
    },
    {
        "id": "moonshotai/kimi-k2.5",
        "target": "moonshotai/kimi-k2.5",
        "display_name": "MoonshotAI Kimi K2.5",
        "provider": "moonshotai",
        "context_window": 200_000,
        "tool_call_tested": False,
        "note": "Modelo solicitado para o RED Proxy Pro; pendente de validacao completa de tool calling.",
    },
    {
        "id": "moonshotai/kimi-k2.6",
        "target": "moonshotai/kimi-k2.6",
        "display_name": "MoonshotAI Kimi K2.6",
        "provider": "moonshotai",
        "aliases": ["claude-red-kimi-k26"],
        "context_window": 200_000,
        "tool_call_tested": True,
        "note": "Modelo validado anteriormente no RED Proxy Pro com tool calling.",
    },
    {
        "id": "openai/gpt-5.4-pro",
        "target": "openai/gpt-5.4-pro",
        "display_name": "OpenAI GPT 5.4 Pro",
        "provider": "openai",
        "context_window": 1_000_000,
        "tool_call_tested": False,
        "note": "Modelo solicitado para o RED Proxy Pro; pendente de validacao completa de tool calling.",
    },
    {
        "id": "openai/gpt-5.5",
        "target": "openai/gpt-5.5",
        "display_name": "OpenAI GPT 5.5",
        "provider": "openai",
        "aliases": ["claude-red-gpt-55"],
        "context_window": 1_000_000,
        "default": True,
        "tool_call_tested": True,
        "note": "Modelo validado no RED Proxy Pro e mantido como fallback padrao.",
    },
    {
        "id": "openai/gpt-5.5-pro",
        "target": "openai/gpt-5.5-pro",
        "display_name": "OpenAI GPT 5.5 Pro",
        "provider": "openai",
        "context_window": 1_000_000,
        "tool_call_tested": False,
        "note": "Modelo solicitado para o RED Proxy Pro; pendente de validacao completa de tool calling.",
    },
    {
        "id": "xai/grok-4.20-multi-agent",
        "target": "xai/grok-4.20-multi-agent",
        "display_name": "xAI Grok 4.20 Multi Agent",
        "provider": "xai",
        "context_window": 200_000,
        "tool_call_tested": False,
        "note": "Modelo solicitado para o RED Proxy Pro; pendente de validacao completa de tool calling.",
    },
    {
        "id": "xai/grok-4.20-reasoning",
        "target": "xai/grok-4.20-reasoning",
        "display_name": "xAI Grok 4.20 Reasoning",
        "provider": "xai",
        "context_window": 200_000,
        "tool_call_tested": False,
        "note": "Modelo solicitado para o RED Proxy Pro; pendente de validacao completa de tool calling.",
    },
    {
        "id": "xai/grok-4.3",
        "target": "xai/grok-4.3",
        "display_name": "xAI Grok 4.3",
        "provider": "xai",
        "context_window": 200_000,
        "tool_call_tested": False,
        "note": "Modelo solicitado para o RED Proxy Pro; pendente de validacao completa de tool calling.",
    },
    {
        "id": "xiaomi/mimo-v2.5",
        "target": "xiaomi/mimo-v2.5",
        "display_name": "Xiaomi MiMo v2.5",
        "provider": "xiaomi",
        "context_window": 200_000,
        "tool_call_tested": False,
        "note": "Modelo solicitado para o RED Proxy Pro; pendente de validacao completa de tool calling.",
    },
    {
        "id": "xiaomi/mimo-v2.5-pro",
        "target": "xiaomi/mimo-v2.5-pro",
        "display_name": "Xiaomi MiMo v2.5 Pro",
        "provider": "xiaomi",
        "context_window": 200_000,
        "tool_call_tested": False,
        "note": "Modelo solicitado para o RED Proxy Pro; pendente de validacao completa de tool calling.",
    },
    {
        "id": "zai/glm-5.1",
        "target": "zai/glm-5.1",
        "display_name": "Z.ai GLM 5.1",
        "provider": "zai",
        "aliases": ["claude-red-glm-51"],
        "context_window": 200_000,
        "tool_call_tested": True,
        "note": "Modelo validado anteriormente no RED Proxy Pro com tool calling.",
    },
]

# Fallback local: usado apenas se o proxy normal ainda nao responder ao
# catalogo. Em operacao normal, a lista vem dinamicamente de
# REDCLAUDEPROXY_UPSTREAM_BASE_URL + /models.
CLAUDE_MODEL_ALIASES = [
    {
        "id": "claude-red-devstral-medium",
        "target": "devstral-medium-latest",
        "display_name": "RED MIS Devstral Medium",
        "provider": "mistralai",
        "context_window": 262_144,
        "tool_call_tested": True,
        "note": "Fallback local para o alias de codigo/agente do proxy normal.",
    },
    {
        "id": "claude-red-mistral-medium",
        "target": "mistral-medium-3.5",
        "display_name": "RED MIS Medium 3.5",
        "provider": "mistralai",
        "context_window": 262_144,
        "tool_call_tested": True,
        "note": "Fallback local para Mistral Medium no proxy normal.",
    },
    {
        "id": "claude-red-nim-glm51",
        "target": "NIM - z-ai/glm-5.1",
        "display_name": "RED NIM GLM 5.1",
        "provider": "nvidia",
        "context_window": 200_000,
        "tool_call_tested": True,
        "note": "Fallback local para GLM 5.1 via NIM no proxy normal.",
    },
    {
        "id": "claude-red-nim-kimi-k26",
        "target": "NIM - moonshotai/kimi-k2.6",
        "display_name": "RED NIM Kimi K2.6",
        "provider": "nvidia",
        "context_window": 200_000,
        "tool_call_tested": True,
        "note": "Fallback local para Kimi K2.6 via NIM no proxy normal.",
    },
    {
        "id": "claude-red-qwen3-coder-next",
        "target": "qwen3-coder-next",
        "display_name": "RED OLL Qwen3 Coder Next",
        "provider": "ollama",
        "context_window": 200_000,
        "tool_call_tested": True,
        "note": "Fallback local para Qwen coder no proxy normal.",
    },
]


def build_claude_alias_by_id(model_aliases: list[dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for item in model_aliases or current_claude_model_aliases():
        for model_id in [item["id"], *item.get("aliases", [])]:
            output[str(model_id).lower()] = item
    return output


def build_claude_alias_by_target(model_aliases: list[dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    return {str(item["target"]).lower(): item for item in model_aliases or current_claude_model_aliases()}


_claude_model_cache_lock = Lock()
_claude_model_cache_loaded_at = 0.0
_claude_model_cache_error = ""
_claude_model_cache: list[dict[str, Any]] = []
UNKNOWN_CLAUDE_MODELS_LOGGED: set[str] = set()
CLAUDE_CLIENT_LAST_ALIAS: dict[str, tuple[float, str]] = {}
CLAUDE_CLIENT_MODEL_LOCK = Lock()


def first_active_upstream_key() -> KeyState | None:
    try:
        pool = key_pool
    except NameError:
        return None
    with pool.lock:
        now = time.time()
        for key in pool.keys:
            if key.active and key.cooldown_until <= now:
                return key
        return pool.keys[0] if pool.keys else None


def upstream_catalog_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "redclaudeproxy/1.0",
    }
    key = first_active_upstream_key()
    if key and key.key:
        headers["Authorization"] = f"Bearer {key.key}"
    return headers


def model_context_window(entry: dict[str, Any]) -> int:
    red = entry.get("red") if isinstance(entry.get("red"), dict) else {}
    for source in (entry, red):
        for field in ("context_window", "context_length", "max_context_length", "input_token_limit", "max_input_tokens", "max_context"):
            value = source.get(field)
            try:
                if value:
                    return int(value)
            except (TypeError, ValueError):
                continue
    return 200_000


def should_publish_upstream_model(model_id: str, red: dict[str, Any]) -> bool:
    model_key = model_id.lower()
    if MODEL_INCLUDE_ALL:
        capabilities = red.get("capabilities") if isinstance(red.get("capabilities"), list) else []
        return "embedding" not in capabilities and red.get("kind") not in {"embedding", "rerank", "image"}
    return any(model_key.startswith(prefix.lower()) for prefix in MODEL_INCLUDE_PREFIXES)


def upstream_model_to_claude_alias(entry: dict[str, Any]) -> dict[str, Any] | None:
    model_id = str(entry.get("id") or "").strip()
    if not model_id:
        return None
    red = entry.get("red") if isinstance(entry.get("red"), dict) else {}
    if not should_publish_upstream_model(model_id, red):
        return None
    target = str(red.get("route_model") or red.get("target_model") or red.get("target") or model_id).strip() or model_id
    provider = str(red.get("provider") or entry.get("owned_by") or "redproxy").strip() or "redproxy"
    context_window = model_context_window(entry)
    display_name = str(entry.get("display_name") or model_id).strip() or model_id
    return {
        "id": model_id,
        "target": target,
        "display_name": display_name,
        "provider": provider,
        "context_window": context_window,
        "tool_call_tested": bool(red.get("tool_call_tested") or red.get("function_calling")),
        "note": str(red.get("note") or "Modelo importado do proxy normal RED.").strip(),
        "source": "normal-proxy",
        "upstream_red": red,
    }


def fetch_upstream_claude_aliases() -> list[dict[str, Any]]:
    catalog_url = f"{UPSTREAM_BASE_URL}/models"
    separator = "&" if "?" in catalog_url else "?"
    resp = http.get(
        f"{catalog_url}{separator}include_gateway_aliases=1&full=1",
        headers=upstream_catalog_headers(),
        timeout=(CONNECT_TIMEOUT, min(60, READ_TIMEOUT)),
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"normal proxy model catalog HTTP {resp.status_code}: {resp.text[:180]}")
    data = resp.json()
    aliases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in data.get("data") or []:
        if not isinstance(entry, dict):
            continue
        alias = upstream_model_to_claude_alias(entry)
        if not alias:
            continue
        key = alias["id"].lower()
        if key in seen:
            continue
        seen.add(key)
        aliases.append(alias)
    if not aliases:
        raise RuntimeError("normal proxy returned no Claude-compatible models")
    return sorted(aliases, key=lambda item: str(item["id"]).lower())


def current_claude_model_aliases(force: bool = False) -> list[dict[str, Any]]:
    global _claude_model_cache_loaded_at, _claude_model_cache_error, _claude_model_cache
    now = time.time()
    if not force and _claude_model_cache and (now - _claude_model_cache_loaded_at) < MODEL_REFRESH_TTL_SECONDS:
        return list(_claude_model_cache)
    with _claude_model_cache_lock:
        now = time.time()
        if not force and _claude_model_cache and (now - _claude_model_cache_loaded_at) < MODEL_REFRESH_TTL_SECONDS:
            return list(_claude_model_cache)
        try:
            aliases = fetch_upstream_claude_aliases()
            _claude_model_cache = aliases
            _claude_model_cache_loaded_at = now
            _claude_model_cache_error = ""
            return list(aliases)
        except Exception as exc:
            _claude_model_cache_error = str(exc)[:300]
            if _claude_model_cache:
                return list(_claude_model_cache)
            return list(CLAUDE_MODEL_ALIASES)


def default_claude_alias() -> dict[str, Any]:
    aliases = current_claude_model_aliases()
    for item in aliases:
        if DEFAULT_MODEL_ID and str(item.get("id", "")).lower() == DEFAULT_MODEL_ID:
            return item
    for item in aliases:
        if item.get("default"):
            return item
    return sorted(aliases, key=lambda item: str(item["target"]).lower())[0]


def claude_client_key() -> str:
    forwarded_for = str(request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
    real_ip = str(request.headers.get("x-real-ip") or "").strip()
    remote_ip = forwarded_for or real_ip or str(request.remote_addr or "")
    user_agent = str(request.headers.get("user-agent") or "")[:120]
    organization = str(request.headers.get("anthropic-organization-id") or request.headers.get("x-organization-id") or "")
    return "|".join([remote_ip, organization, user_agent])


def remember_claude_alias(alias: dict[str, Any]) -> None:
    alias_id = str(alias.get("id") or "")
    if not alias_id:
        return
    now = time.time()
    key = claude_client_key()
    with CLAUDE_CLIENT_MODEL_LOCK:
        CLAUDE_CLIENT_LAST_ALIAS[key] = (now, alias_id)
        expired_before = now - max(60, CLAUDE_STICKY_TTL_SECONDS)
        for old_key, (timestamp, _old_alias_id) in list(CLAUDE_CLIENT_LAST_ALIAS.items()):
            if timestamp < expired_before:
                CLAUDE_CLIENT_LAST_ALIAS.pop(old_key, None)


def last_claude_alias_for_request() -> dict[str, Any] | None:
    key = claude_client_key()
    now = time.time()
    with CLAUDE_CLIENT_MODEL_LOCK:
        stored = CLAUDE_CLIENT_LAST_ALIAS.get(key)
        if not stored:
            return None
        timestamp, alias_id = stored
        if timestamp < now - max(60, CLAUDE_STICKY_TTL_SECONDS):
            CLAUDE_CLIENT_LAST_ALIAS.pop(key, None)
            return None
    return build_claude_alias_by_id().get(alias_id.lower())


def normalize_int_dict(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    output: dict[str, int] = {}
    for key, raw in value.items():
        try:
            output[str(key)] = int(raw or 0)
        except (TypeError, ValueError):
            continue
    return output


def normalize_float(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    if not text:
        return 0.0
    cleaned = re_numeric_text(text)
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def re_numeric_text(text: str) -> str:
    return "".join(char for char in text if char.isdigit() or char in ".-")


def normalize_usage_item(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "total_requests": int(value.get("total_requests", value.get("requests", 0)) or 0),
        "successes": int(value.get("successes", 0) or 0),
        "prompt_tokens": int(value.get("prompt_tokens", 0) or 0),
        "completion_tokens": int(value.get("completion_tokens", 0) or 0),
        "reasoning_tokens": int(value.get("reasoning_tokens", 0) or 0),
        "total_tokens": int(value.get("total_tokens", 0) or 0),
        "total_cost": normalize_float(value.get("total_cost", value.get("cost", 0))),
        "market_cost": normalize_float(value.get("market_cost", 0)),
        "last_used_at": float(value.get("last_used_at", 0) or 0),
        "endpoints": normalize_int_dict(value.get("endpoints", {})),
    }


def normalize_model_usage(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    output: dict[str, dict[str, Any]] = {}
    for model, usage in value.items():
        name = str(model or "").strip() or "sem-modelo"
        output[name] = normalize_usage_item(usage)
    return output


def usage_has_values(usage: dict[str, Any]) -> bool:
    return any(
        [
            int(usage.get("prompt_tokens", 0) or 0),
            int(usage.get("completion_tokens", 0) or 0),
            int(usage.get("reasoning_tokens", 0) or 0),
            int(usage.get("total_tokens", 0) or 0),
            float(usage.get("total_cost", 0) or 0),
            float(usage.get("market_cost", 0) or 0),
        ]
    )


def extract_usage(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    if not usage and isinstance(payload.get("response"), dict):
        usage = payload["response"].get("usage") if isinstance(payload["response"].get("usage"), dict) else {}
    if not usage:
        return {}

    completion_details = usage.get("completion_tokens_details")
    if not isinstance(completion_details, dict):
        completion_details = {}
    prompt_tokens = int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0)
    completion_tokens = int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0)
    reasoning_tokens = int(usage.get("reasoning_tokens", completion_details.get("reasoning_tokens", 0)) or 0)
    total_tokens = int(usage.get("total_tokens", prompt_tokens + completion_tokens + reasoning_tokens) or 0)
    total_cost = first_number(
        usage,
        payload,
        keys=("cost", "total_cost", "estimated_cost", "redclaudeproxy_cost", "upstream_cost"),
    )
    market_cost = first_number(usage, payload, keys=("market_cost", "provider_cost", "upstream_cost"))
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "reasoning_tokens": reasoning_tokens,
        "total_tokens": total_tokens,
        "total_cost": total_cost,
        "market_cost": market_cost,
    }


def first_number(*sources: Any, keys: tuple[str, ...]) -> float:
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            if key in source:
                value = source.get(key)
                if isinstance(value, dict):
                    value = value.get("total") or value.get("amount") or value.get("usd")
                number = normalize_float(value)
                if number:
                    return number
    return 0.0


def extract_usage_from_bytes(content: bytes) -> dict[str, Any]:
    if not content:
        return {}
    try:
        payload = json.loads(content.decode("utf-8", errors="replace"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return extract_usage(payload)


def extract_message_text(message: dict[str, Any]) -> str:
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") in {"text", "output_text"}:
                    parts.append(str(item.get("text") or ""))
                elif "content" in item:
                    parts.append(str(item.get("content") or ""))
            elif item is not None:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    return "" if content is None else str(content)


def sse_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def iter_utf8_lines(upstream: requests.Response):
    for line in upstream.iter_lines(decode_unicode=False):
        if isinstance(line, bytes):
            yield line.decode("utf-8", errors="replace")
        elif line is not None:
            yield str(line)


def request_model_name() -> str:
    if not request.is_json:
        return ""
    try:
        payload = request.get_json(silent=True) or {}
    except Exception:
        return ""
    return str(payload.get("model", "") or "").strip()


@dataclass
class KeyState:
    name: str
    key: str
    active: bool = True
    cooldown_until: float = 0.0
    total_requests: int = 0
    successes: int = 0
    failures: int = 0
    last_status: int | None = None
    last_error: str = ""
    last_used_at: float = 0.0
    total_latency: float = 0.0
    status_counts: dict[str, int] = field(default_factory=dict)
    endpoint_counts: dict[str, int] = field(default_factory=dict)
    model_usage: dict[str, dict[str, Any]] = field(default_factory=dict)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    market_cost: float = 0.0

    def public(self) -> dict[str, Any]:
        now = time.time()
        avg_latency = self.total_latency / self.successes if self.successes else None
        top_models = sorted(
            (dict(value, model=model) for model, value in self.model_usage.items()),
            key=lambda item: (float(item.get("total_cost", 0) or 0), int(item.get("total_requests", 0) or 0)),
            reverse=True,
        )[:8]
        return {
            "name": self.name,
            "active": self.active,
            "cooldown": max(0, round(self.cooldown_until - now, 1)),
            "total_requests": self.total_requests,
            "successes": self.successes,
            "failures": self.failures,
            "last_status": self.last_status,
            "last_error": self.last_error,
            "last_used_at": self.last_used_at,
            "avg_latency": round(avg_latency, 3) if avg_latency is not None else None,
            "status_counts": dict(self.status_counts),
            "endpoint_counts": dict(self.endpoint_counts),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "total_tokens": self.total_tokens,
            "total_cost": round(self.total_cost, 8),
            "market_cost": round(self.market_cost, 8),
            "top_models": top_models,
        }

    def saved_metrics(self) -> dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "successes": self.successes,
            "failures": self.failures,
            "last_status": self.last_status,
            "last_error": self.last_error,
            "last_used_at": self.last_used_at,
            "cooldown_until": self.cooldown_until,
            "total_latency": self.total_latency,
            "status_counts": self.status_counts,
            "endpoint_counts": self.endpoint_counts,
            "model_usage": self.model_usage,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost,
            "market_cost": self.market_cost,
        }

    def apply_saved_metrics(self, data: dict[str, Any]) -> None:
        self.total_requests = int(data.get("total_requests", self.total_requests) or 0)
        self.successes = int(data.get("successes", self.successes) or 0)
        self.failures = int(data.get("failures", self.failures) or 0)
        self.last_status = data.get("last_status", self.last_status)
        self.last_error = sanitize_saved_error(self.last_status, str(data.get("last_error", self.last_error) or ""))
        self.last_used_at = float(data.get("last_used_at", self.last_used_at) or 0)
        self.cooldown_until = float(data.get("cooldown_until", self.cooldown_until) or 0)
        self.total_latency = float(data.get("total_latency", self.total_latency) or 0)
        self.status_counts = normalize_int_dict(data.get("status_counts", self.status_counts))
        self.endpoint_counts = normalize_int_dict(data.get("endpoint_counts", self.endpoint_counts))
        self.model_usage = normalize_model_usage(data.get("model_usage", self.model_usage))
        self.prompt_tokens = int(data.get("prompt_tokens", self.prompt_tokens) or 0)
        self.completion_tokens = int(data.get("completion_tokens", self.completion_tokens) or 0)
        self.reasoning_tokens = int(data.get("reasoning_tokens", self.reasoning_tokens) or 0)
        self.total_tokens = int(data.get("total_tokens", self.total_tokens) or 0)
        self.total_cost = float(data.get("total_cost", self.total_cost) or 0)
        self.market_cost = float(data.get("market_cost", self.market_cost) or 0)


class KeyPool:
    def __init__(self, keys: list[KeyState]):
        self.keys = keys
        self.lock = Lock()
        self.cursor = 0
        self.load_usage()

    def healthy_count(self) -> int:
        now = time.time()
        with self.lock:
            return sum(1 for key in self.keys if key.active and key.cooldown_until <= now)

    def choose(self, exclude: set[str] | None = None) -> KeyState | None:
        exclude = exclude or set()
        now = time.time()
        with self.lock:
            if not self.keys:
                return None
            total = len(self.keys)
            for offset in range(total):
                index = (self.cursor + offset) % total
                key = self.keys[index]
                if key.name in exclude:
                    continue
                if key.active and key.cooldown_until <= now:
                    self.cursor = (index + 1) % total
                    key.total_requests += 1
                    key.last_used_at = now
                    self.save_usage_locked()
                    return key

            # If every key is cooling down, use the one that comes back first.
            candidates = [key for key in self.keys if key.active and key.name not in exclude]
            if not candidates:
                return None
            key = min(candidates, key=lambda item: item.cooldown_until)
            key.total_requests += 1
            key.last_used_at = now
            self.save_usage_locked()
            return key

    def mark_success(self, key: KeyState, status: int, latency: float, *, model: str = "", endpoint: str = "", usage: dict[str, Any] | None = None) -> None:
        with self.lock:
            key.successes += 1
            key.last_status = status
            key.last_error = ""
            key.total_latency += latency
            key.status_counts[str(status)] = key.status_counts.get(str(status), 0) + 1
            self.record_model_locked(key, model=model, endpoint=endpoint, request_count=1, success_count=1, usage=usage or {})
            self.save_usage_locked()

    def mark_failure(self, key: KeyState, status: int | None, error: str, latency: float = 0.0) -> None:
        with self.lock:
            key.failures += 1
            key.last_status = status
            key.last_error = error[:300]
            if latency:
                key.total_latency += latency
            if status is not None:
                key.status_counts[str(status)] = key.status_counts.get(str(status), 0) + 1
                cooldown = cooldown_for_status(status)
                if cooldown:
                    key.cooldown_until = max(key.cooldown_until, time.time() + cooldown)
            self.save_usage_locked()

    def record_usage(self, key: KeyState, *, model: str = "", endpoint: str = "", usage: dict[str, Any] | None = None) -> None:
        if not usage or not usage_has_values(usage):
            return
        with self.lock:
            self.record_model_locked(key, model=model, endpoint=endpoint, request_count=0, success_count=0, usage=usage)
            self.save_usage_locked()

    def record_model_locked(
        self,
        key: KeyState,
        *,
        model: str,
        endpoint: str,
        request_count: int,
        success_count: int,
        usage: dict[str, Any],
    ) -> None:
        now = time.time()
        model_name = str(model or "sem-modelo").strip() or "sem-modelo"
        endpoint_name = str(endpoint or "desconhecido").strip() or "desconhecido"
        key.endpoint_counts[endpoint_name] = key.endpoint_counts.get(endpoint_name, 0) + max(0, request_count)
        if model_name == "sem-modelo" and not usage_has_values(usage):
            return

        item = normalize_usage_item(key.model_usage.get(model_name, {}))
        item["total_requests"] = int(item.get("total_requests", 0) or 0) + max(0, request_count)
        item["successes"] = int(item.get("successes", 0) or 0) + max(0, success_count)
        endpoints = normalize_int_dict(item.get("endpoints", {}))
        endpoints[endpoint_name] = endpoints.get(endpoint_name, 0) + max(0, request_count)
        item["endpoints"] = endpoints
        item["last_used_at"] = now

        if usage_has_values(usage):
            prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
            completion_tokens = int(usage.get("completion_tokens", 0) or 0)
            reasoning_tokens = int(usage.get("reasoning_tokens", 0) or 0)
            total_tokens = int(usage.get("total_tokens", 0) or (prompt_tokens + completion_tokens + reasoning_tokens))
            total_cost = normalize_float(usage.get("total_cost", 0))
            market_cost = normalize_float(usage.get("market_cost", 0))

            key.prompt_tokens += prompt_tokens
            key.completion_tokens += completion_tokens
            key.reasoning_tokens += reasoning_tokens
            key.total_tokens += total_tokens
            key.total_cost += total_cost
            key.market_cost += market_cost

            item["prompt_tokens"] = int(item.get("prompt_tokens", 0) or 0) + prompt_tokens
            item["completion_tokens"] = int(item.get("completion_tokens", 0) or 0) + completion_tokens
            item["reasoning_tokens"] = int(item.get("reasoning_tokens", 0) or 0) + reasoning_tokens
            item["total_tokens"] = int(item.get("total_tokens", 0) or 0) + total_tokens
            item["total_cost"] = normalize_float(item.get("total_cost", 0)) + total_cost
            item["market_cost"] = normalize_float(item.get("market_cost", 0)) + market_cost

        key.model_usage[model_name] = item

    def public(self) -> list[dict[str, Any]]:
        with self.lock:
            return [key.public() for key in self.keys]

    def summary(self) -> dict[str, Any]:
        now = time.time()
        with self.lock:
            return {
                "total": len(self.keys),
                "active": sum(1 for key in self.keys if key.active),
                "healthy": sum(1 for key in self.keys if key.active and key.cooldown_until <= now),
                "cooldown": sum(1 for key in self.keys if key.cooldown_until > now),
                "total_requests": sum(key.total_requests for key in self.keys),
                "successes": sum(key.successes for key in self.keys),
                "failures": sum(key.failures for key in self.keys),
                "prompt_tokens": sum(key.prompt_tokens for key in self.keys),
                "completion_tokens": sum(key.completion_tokens for key in self.keys),
                "reasoning_tokens": sum(key.reasoning_tokens for key in self.keys),
                "total_tokens": sum(key.total_tokens for key in self.keys),
                "total_cost": round(sum(key.total_cost for key in self.keys), 8),
                "market_cost": round(sum(key.market_cost for key in self.keys), 8),
            }

    def model_summary(self) -> list[dict[str, Any]]:
        combined: dict[str, dict[str, Any]] = {}
        with self.lock:
            for key in self.keys:
                for model, usage in key.model_usage.items():
                    item = combined.setdefault(
                        model,
                        {
                            "model": model,
                            "keys": set(),
                            "total_requests": 0,
                            "successes": 0,
                            "prompt_tokens": 0,
                            "completion_tokens": 0,
                            "reasoning_tokens": 0,
                            "total_tokens": 0,
                            "total_cost": 0.0,
                            "market_cost": 0.0,
                        },
                    )
                    normalized = normalize_usage_item(usage)
                    item["keys"].add(key.name)
                    item["total_requests"] += int(normalized.get("total_requests", 0) or 0)
                    item["successes"] += int(normalized.get("successes", 0) or 0)
                    item["prompt_tokens"] += int(normalized.get("prompt_tokens", 0) or 0)
                    item["completion_tokens"] += int(normalized.get("completion_tokens", 0) or 0)
                    item["reasoning_tokens"] += int(normalized.get("reasoning_tokens", 0) or 0)
                    item["total_tokens"] += int(normalized.get("total_tokens", 0) or 0)
                    item["total_cost"] += normalize_float(normalized.get("total_cost", 0))
                    item["market_cost"] += normalize_float(normalized.get("market_cost", 0))
        rows = []
        for item in combined.values():
            key_names = sorted(item.pop("keys"))
            item["keys"] = key_names
            item["key_count"] = len(key_names)
            item["total_cost"] = round(item["total_cost"], 8)
            item["market_cost"] = round(item["market_cost"], 8)
            rows.append(item)
        return sorted(rows, key=lambda item: (float(item.get("total_cost", 0) or 0), int(item.get("total_requests", 0) or 0)), reverse=True)

    def load_usage(self) -> None:
        if not USAGE_FILE.exists():
            return
        try:
            data = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        keys_data = data.get("keys", {}) if isinstance(data, dict) else {}
        if not isinstance(keys_data, dict):
            return
        with self.lock:
            for key in self.keys:
                saved = keys_data.get(key.name)
                if isinstance(saved, dict):
                    key.apply_saved_metrics(saved)

    def save_usage_locked(self) -> None:
        payload = {
            "service": SERVICE_NAME,
            "updated_at": time.time(),
            "keys": {key.name: key.saved_metrics() for key in self.keys},
        }
        try:
            USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = USAGE_FILE.with_suffix(f"{USAGE_FILE.suffix}.tmp")
            tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp_path, USAGE_FILE)
        except OSError:
            pass


def parse_key_entry(entry: str, index: int) -> KeyState | None:
    entry = entry.strip()
    if not entry:
        return None
    for separator in (":", "=", "|"):
        if separator in entry:
            left, right = entry.split(separator, 1)
            left = left.strip()
            right = right.strip()
            if left.startswith("vck_"):
                name = right or f"key{index}"
                key = left
            else:
                name = left or f"key{index}"
                key = right
            if key:
                return KeyState(name=name, key=key)
    return KeyState(name=f"key{index}", key=entry)


def load_keys() -> list[KeyState]:
    raw_entries: list[str] = []
    keys_file = os.getenv("REDCLAUDEPROXY_KEYS_FILE", "").strip()
    if keys_file:
        try:
            with open(keys_file, "r", encoding="utf-8") as handle:
                raw_entries.extend(split_values(handle.read()))
        except OSError:
            pass
    raw_entries.extend(split_values(os.getenv("REDCLAUDEPROXY_KEYS", "")))
    if not raw_entries:
        upstream_token = os.getenv("REDCLAUDEPROXY_UPSTREAM_TOKEN", "").strip()
        if upstream_token:
            raw_entries.append("normal:" + upstream_token)
    keys: list[KeyState] = []
    seen_names: set[str] = set()
    seen_keys: set[str] = set()
    for index, entry in enumerate(raw_entries, start=1):
        parsed = parse_key_entry(entry, index)
        if not parsed or not parsed.key:
            continue
        if parsed.key in seen_keys:
            continue
        base_name = parsed.name
        suffix = 2
        while parsed.name in seen_names:
            parsed.name = f"{base_name}-{suffix}"
            suffix += 1
        seen_names.add(parsed.name)
        seen_keys.add(parsed.key)
        keys.append(parsed)
    return keys


def cooldown_for_status(status: int) -> int:
    if status == 401:
        return env_int("REDCLAUDEPROXY_COOLDOWN_401", 3600)
    if status == 402:
        return env_int("REDCLAUDEPROXY_COOLDOWN_402", 21600)
    if status == 403:
        return env_int("REDCLAUDEPROXY_COOLDOWN_403", 300)
    if status == 429:
        return env_int("REDCLAUDEPROXY_COOLDOWN_429", 180)
    if status >= 500:
        return env_int("REDCLAUDEPROXY_COOLDOWN_5XX", 60)
    return env_int(f"REDCLAUDEPROXY_COOLDOWN_{status}", 60)


SENSITIVE_UPSTREAM_ERROR_MARKERS = (
    "insufficient_funds",
    "insufficient funds",
    "add credits",
    "top up",
    "top-up",
    "billing",
    "payment required",
    "vercel.com/d",
)


def raw_error_message_from_response(resp: requests.Response) -> str:
    try:
        payload = resp.json()
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            return str(error.get("message") or error.get("type") or resp.text[:300])
    except Exception:
        pass
    return resp.text[:300]


def is_sensitive_upstream_error(status: int, message: str) -> bool:
    if status in {401, 402, 403}:
        return True
    normalized = message.lower()
    return any(marker in normalized for marker in SENSITIVE_UPSTREAM_ERROR_MARKERS)


def safe_upstream_error_message(status: int, message: str) -> str:
    if status == 401:
        return "upstream key rejected"
    if status == 402:
        return "upstream key unavailable"
    if status == 403:
        return "upstream key forbidden for this request"
    if status == 429:
        return "upstream key rate limited"
    if status >= 500:
        return "upstream provider temporarily unavailable"
    if is_sensitive_upstream_error(status, message):
        return "upstream provider rejected the request; details were hidden by redclaudeproxy"
    cleaned = re.sub(r"https?://\S+", "[redacted-url]", message or "")
    return cleaned[:300] or f"upstream error {status}"


def sanitize_saved_error(status: Any, message: str) -> str:
    if not message:
        return ""
    try:
        status_int = int(status)
    except (TypeError, ValueError):
        status_int = 0
    return safe_upstream_error_message(status_int, message)


def error_message_from_response(resp: requests.Response) -> str:
    return safe_upstream_error_message(resp.status_code, raw_error_message_from_response(resp))


def sanitized_attempts(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    safe_attempts: list[dict[str, Any]] = []
    for attempt in attempts:
        safe = dict(attempt)
        if "error" in safe:
            safe["error"] = re.sub(r"https?://\S+", "[redacted-url]", str(safe["error"]))[:180]
        safe_attempts.append(safe)
    return safe_attempts


def redclaudeproxy_upstream_error_response(
    *,
    status: int,
    message: str,
    attempts: list[dict[str, Any]],
    source_response: requests.Response | None = None,
) -> Response:
    payload = {
        "error": {
            "message": message,
            "type": "redclaudeproxy_upstream_unavailable",
        },
        "attempts": sanitized_attempts(attempts),
    }
    headers: dict[str, str]
    if source_response is not None and attempts:
        headers = response_headers(source_response, attempts[-1]["key"], attempts)
    else:
        headers = {"X-Request-Id": request_id(), "X-RedClaudeProxy-Attempts": str(len(attempts))}
    headers["X-RedClaudeProxy-Last-Error"] = message[:180]
    return Response(json.dumps(payload, ensure_ascii=False), status=status, headers=headers, content_type="application/json")


def resolve_claude_model(
    model: str,
    *,
    allow_fallback: bool = False,
    fallback_alias: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    model_id = str(model or "").strip()
    if not model_id:
        return fallback_alias if allow_fallback and fallback_alias is not None else default_claude_alias()
    aliases = current_claude_model_aliases()
    alias_by_id = build_claude_alias_by_id(aliases)
    alias_by_target = build_claude_alias_by_target(aliases)
    alias = alias_by_id.get(model_id.lower()) or alias_by_target.get(model_id.lower())
    if alias is not None:
        return alias
    if allow_fallback and CLAUDE_UNKNOWN_MODEL_FALLBACK:
        fallback = fallback_alias or default_claude_alias()
        normalized = model_id.lower()
        log_key = f"{normalized}->{fallback['id']}"
        if log_key not in UNKNOWN_CLAUDE_MODELS_LOGGED:
            UNKNOWN_CLAUDE_MODELS_LOGGED.add(log_key)
            print(
                f"[redclaudeproxy] Claude gateway unknown model {model_id!r}; using fallback {fallback['id']!r}",
                flush=True,
            )
        return fallback
    return None


def public_claude_model_entry(alias: dict[str, Any]) -> dict[str, Any]:
    created = 1775520000
    context_window = int(alias.get("context_window") or 200_000)
    return {
        "id": alias["id"],
        "object": "model",
        "type": "model",
        "created": created,
        "created_at": created,
        "owned_by": alias["provider"],
        "display_name": alias["display_name"],
        "context_window": context_window,
        "context_length": context_window,
        "max_context_length": context_window,
        "input_token_limit": context_window,
        "max_input_tokens": context_window,
        "metadata": {
            "context_window": context_window,
            "context_length": context_window,
            "max_context_length": context_window,
            "input_token_limit": context_window,
        },
        "red": {
            "gateway": "redclaudeproxy",
            "provider": alias["provider"],
            "target": alias["target"],
            "gateway_alias": True,
            "tool_call_tested": bool(alias.get("tool_call_tested", False)),
            "aliases": alias.get("aliases", []),
            "context_window": context_window,
            "max_context_length": context_window,
            "note": alias.get("note", ""),
        },
    }


def anthropic_text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return "" if content is None else str(content)
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
    return "\n".join(part for part in parts if part)


def anthropic_system_messages(system: Any) -> list[dict[str, Any]]:
    text = anthropic_text_from_content(system)
    return [{"role": "system", "content": text}] if text else []


def anthropic_message_to_openai(message: dict[str, Any]) -> list[dict[str, Any]]:
    role = message.get("role", "user")
    content = message.get("content", "")
    if isinstance(content, str):
        return [{"role": role, "content": content}]
    if not isinstance(content, list):
        return [{"role": role, "content": "" if content is None else str(content)}]

    out: list[dict[str, Any]] = []
    text_parts: list[str] = []
    openai_parts: list[dict[str, Any]] = []
    assistant_tool_calls: list[dict[str, Any]] = []

    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "text":
            text = str(block.get("text") or "")
            text_parts.append(text)
            openai_parts.append({"type": "text", "text": text})
        elif block_type == "image":
            source = block.get("source") or {}
            if source.get("type") == "base64" and source.get("data"):
                media_type = source.get("media_type") or "image/jpeg"
                openai_parts.append({"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{source['data']}"}})
            elif source.get("type") == "url" and source.get("url"):
                openai_parts.append({"type": "image_url", "image_url": {"url": source["url"]}})
        elif block_type == "tool_use":
            assistant_tool_calls.append(
                {
                    "id": block.get("id") or ("toolu_" + uuid.uuid4().hex),
                    "type": "function",
                    "function": {
                        "name": block.get("name") or "tool",
                        "arguments": json.dumps(block.get("input") or {}, ensure_ascii=False),
                    },
                }
            )
        elif block_type == "tool_result":
            if text_parts:
                out.append({"role": "user", "content": "\n".join(text_parts)})
                text_parts = []
            tool_content = block.get("content", "")
            if not isinstance(tool_content, str):
                tool_content = json.dumps(tool_content, ensure_ascii=False)
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": block.get("tool_use_id") or ("toolu_" + uuid.uuid4().hex),
                    "content": tool_content,
                }
            )

    if assistant_tool_calls:
        out.append({"role": "assistant", "content": "\n".join(text_parts), "tool_calls": assistant_tool_calls})
    elif openai_parts and any(part.get("type") == "image_url" for part in openai_parts):
        out.append({"role": role, "content": openai_parts})
    elif text_parts:
        out.append({"role": role, "content": "\n".join(text_parts)})
    elif not out:
        out.append({"role": role, "content": ""})
    return out


def anthropic_tools_to_openai(tools: Any) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        converted.append(
            {
                "type": "function",
                "function": {
                    "name": tool.get("name") or "tool",
                    "description": tool.get("description") or "",
                    "parameters": tool.get("input_schema") or {"type": "object", "properties": {}},
                },
            }
        )
    return converted


def anthropic_tool_choice_to_openai(tool_choice: Any):
    if not isinstance(tool_choice, dict):
        return None
    choice_type = tool_choice.get("type")
    if choice_type == "auto":
        return "auto"
    if choice_type == "any":
        return "required"
    if choice_type == "tool" and tool_choice.get("name"):
        return {"type": "function", "function": {"name": tool_choice["name"]}}
    return None


def anthropic_to_openai_payload(body: dict[str, Any], model_id: str) -> dict[str, Any]:
    messages: list[dict[str, Any]] = []
    messages.extend(anthropic_system_messages(body.get("system")))
    for message in body.get("messages") or []:
        if isinstance(message, dict):
            messages.extend(anthropic_message_to_openai(message))

    payload: dict[str, Any] = {
        "model": model_id,
        "messages": messages,
        "stream": bool(body.get("stream", False)),
        "max_tokens": int(body.get("max_tokens") or 1024),
    }
    if body.get("temperature") is not None:
        payload["temperature"] = body.get("temperature")
    if body.get("top_p") is not None:
        payload["top_p"] = body.get("top_p")
    if body.get("stop_sequences"):
        payload["stop"] = body.get("stop_sequences")
    tools = anthropic_tools_to_openai(body.get("tools"))
    if tools:
        payload["tools"] = tools
        tool_choice = anthropic_tool_choice_to_openai(body.get("tool_choice"))
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
    return payload


def anthropic_countable_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "\n".join(anthropic_countable_text(item) for item in value)
    if not isinstance(value, dict):
        return str(value)

    block_type = str(value.get("type") or "").strip()
    if block_type == "text":
        return str(value.get("text") or "")
    if block_type == "tool_result":
        return anthropic_countable_text(value.get("content"))
    if block_type == "tool_use":
        return json.dumps({"name": value.get("name") or "tool", "input": value.get("input") or {}}, ensure_ascii=False, sort_keys=True)
    if block_type in {"image", "document"}:
        source = value.get("source") or {}
        media_type = source.get("media_type") or block_type
        data = source.get("data") or source.get("url") or ""
        return f"[{block_type}:{media_type}:bytes~{len(str(data))}]"

    preferred_keys = ("role", "content", "text", "name", "description", "input", "input_schema")
    parts = [anthropic_countable_text(value.get(key)) for key in preferred_keys if key in value]
    return "\n".join(part for part in parts if part) if parts else json.dumps(value, ensure_ascii=False, sort_keys=True)


def estimate_anthropic_input_tokens(body: dict[str, Any]) -> int:
    parts: list[str] = []
    if not isinstance(body, dict):
        return 1
    parts.append(anthropic_countable_text(body.get("system")))
    for message in body.get("messages") or []:
        parts.append(anthropic_countable_text(message))
    if body.get("tools"):
        parts.append(json.dumps(body.get("tools"), ensure_ascii=False, sort_keys=True))
    if body.get("tool_choice"):
        parts.append(json.dumps(body.get("tool_choice"), ensure_ascii=False, sort_keys=True))
    text = "\n".join(part for part in parts if part)
    char_estimate = max(1, (len(text) + 3) // 4)
    structural_overhead = max(0, len(body.get("messages") or []) * 4 + len(body.get("tools") or []) * 12)
    return char_estimate + structural_overhead


def anthropic_response_from_openai(data: dict[str, Any], model_name: str) -> dict[str, Any]:
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content_blocks: list[dict[str, Any]] = []
    text = extract_message_text(message)
    if text:
        content_blocks.append({"type": "text", "text": text})
    for tool_call in message.get("tool_calls") or []:
        fn = tool_call.get("function") or {}
        args = fn.get("arguments") or "{}"
        try:
            parsed_args = json.loads(args)
        except Exception:
            parsed_args = {"_raw": args}
        content_blocks.append(
            {
                "type": "tool_use",
                "id": tool_call.get("id") or ("toolu_" + uuid.uuid4().hex),
                "name": fn.get("name") or "tool",
                "input": parsed_args,
            }
        )
    finish_reason = choice.get("finish_reason")
    usage = data.get("usage") or {}
    has_tool_use = any(block.get("type") == "tool_use" for block in content_blocks)
    return {
        "id": data.get("id") or ("msg_" + uuid.uuid4().hex),
        "type": "message",
        "role": "assistant",
        "model": model_name,
        "content": content_blocks,
        "stop_reason": "tool_use" if has_tool_use or finish_reason == "tool_calls" else ("max_tokens" if finish_reason == "length" else "end_turn"),
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("prompt_tokens") or usage.get("input_tokens") or 0,
            "output_tokens": usage.get("completion_tokens") or usage.get("output_tokens") or 0,
        },
    }


def anthropic_sse_event(event_type: str, payload: dict[str, Any]):
    yield f"event: {event_type}\n"
    yield "data: " + sse_json(payload) + "\n\n"


def anthropic_sse_from_message(message: dict[str, Any]):
    start_message = dict(message)
    start_message["content"] = []
    yield from anthropic_sse_event("message_start", {"type": "message_start", "message": start_message})

    for index, block in enumerate(message.get("content") or []):
        empty_block = dict(block)
        if empty_block.get("type") == "text":
            text = empty_block.pop("text", "")
            tool_input = {}
        elif empty_block.get("type") == "tool_use":
            text = ""
            tool_input = empty_block.pop("input", {})
        else:
            text = ""
            tool_input = {}
        yield from anthropic_sse_event("content_block_start", {"type": "content_block_start", "index": index, "content_block": empty_block})
        if block.get("type") == "text":
            yield from anthropic_sse_event("content_block_delta", {"type": "content_block_delta", "index": index, "delta": {"type": "text_delta", "text": text}})
        elif block.get("type") == "tool_use":
            yield from anthropic_sse_event("content_block_delta", {"type": "content_block_delta", "index": index, "delta": {"type": "input_json_delta", "partial_json": sse_json(tool_input)}})
        yield from anthropic_sse_event("content_block_stop", {"type": "content_block_stop", "index": index})

    yield from anthropic_sse_event("message_delta", {"type": "message_delta", "delta": {"stop_reason": message.get("stop_reason"), "stop_sequence": None}, "usage": message.get("usage") or {}})
    yield from anthropic_sse_event("message_stop", {"type": "message_stop"})


def iter_openai_sse_json(upstream: requests.Response):
    for line in iter_utf8_lines(upstream):
        line = line.strip()
        if not line or line.startswith(":"):
            continue
        if line.startswith("data:"):
            line = line[5:].strip()
        elif line.startswith("event:"):
            continue
        if not line or line == "[DONE]":
            break
        try:
            yield json.loads(line)
        except Exception:
            continue


def openai_finish_to_anthropic_stop_reason(finish_reason: str | None, used_tool: bool) -> str:
    if used_tool or finish_reason == "tool_calls":
        return "tool_use"
    if finish_reason == "length":
        return "max_tokens"
    return "end_turn"


def anthropic_sse_from_openai_stream(upstream: requests.Response, model_name: str):
    message_id = "msg_" + uuid.uuid4().hex
    start_message = {
        "id": message_id,
        "type": "message",
        "role": "assistant",
        "model": model_name,
        "content": [],
        "stop_reason": None,
        "stop_sequence": None,
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }
    yield from anthropic_sse_event("message_start", {"type": "message_start", "message": start_message})

    next_content_index = 0
    text_index: int | None = None
    text_open = False
    text_len = 0
    finish_reason: str | None = None
    input_tokens = 0
    output_tokens = 0
    tool_states: dict[int, dict[str, Any]] = {}
    used_tool = False

    def close_text_block():
        nonlocal text_index, text_open
        if text_open and text_index is not None:
            index = text_index
            text_open = False
            text_index = None
            yield from anthropic_sse_event("content_block_stop", {"type": "content_block_stop", "index": index})

    def ensure_text_block():
        nonlocal next_content_index, text_index, text_open
        if text_index is None:
            text_index = next_content_index
            next_content_index += 1
            text_open = True
            yield from anthropic_sse_event("content_block_start", {"type": "content_block_start", "index": text_index, "content_block": {"type": "text", "text": ""}})
        elif not text_open:
            text_open = True
            yield from anthropic_sse_event("content_block_start", {"type": "content_block_start", "index": text_index, "content_block": {"type": "text", "text": ""}})

    def ensure_tool_block(openai_index: int):
        nonlocal next_content_index, used_tool
        state = tool_states.setdefault(openai_index, {"id": "toolu_" + uuid.uuid4().hex, "name": None, "args_pending": "", "content_index": None, "open": False})
        if state["open"]:
            return
        name = state.get("name")
        if not name:
            return
        yield from close_text_block()
        state["content_index"] = next_content_index
        next_content_index += 1
        state["open"] = True
        used_tool = True
        yield from anthropic_sse_event(
            "content_block_start",
            {"type": "content_block_start", "index": state["content_index"], "content_block": {"type": "tool_use", "id": state["id"], "name": name, "input": {}}},
        )
        if state["args_pending"]:
            pending = state["args_pending"]
            state["args_pending"] = ""
            yield from anthropic_sse_event("content_block_delta", {"type": "content_block_delta", "index": state["content_index"], "delta": {"type": "input_json_delta", "partial_json": pending}})

    try:
        for item in iter_openai_sse_json(upstream):
            usage = item.get("usage") or {}
            input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens") or input_tokens
            output_tokens = usage.get("completion_tokens") or usage.get("output_tokens") or output_tokens
            for choice in item.get("choices") or []:
                finish_reason = choice.get("finish_reason") or finish_reason
                delta = choice.get("delta") or {}
                content = delta.get("content")
                if content:
                    yield from ensure_text_block()
                    text_len += len(content)
                    yield from anthropic_sse_event("content_block_delta", {"type": "content_block_delta", "index": text_index, "delta": {"type": "text_delta", "text": content}})
                for tool_call in delta.get("tool_calls") or []:
                    openai_index = int(tool_call.get("index") or 0)
                    state = tool_states.setdefault(openai_index, {"id": "toolu_" + uuid.uuid4().hex, "name": None, "args_pending": "", "content_index": None, "open": False})
                    if tool_call.get("id"):
                        state["id"] = tool_call.get("id")
                    function = tool_call.get("function") or {}
                    if function.get("name"):
                        state["name"] = function.get("name")
                        yield from ensure_tool_block(openai_index)
                    arguments = function.get("arguments") or ""
                    if arguments:
                        if not state["open"]:
                            state["args_pending"] += arguments
                            yield from ensure_tool_block(openai_index)
                        else:
                            yield from anthropic_sse_event("content_block_delta", {"type": "content_block_delta", "index": state["content_index"], "delta": {"type": "input_json_delta", "partial_json": arguments}})
    finally:
        upstream.close()

    yield from close_text_block()
    for openai_index, state in sorted(tool_states.items(), key=lambda item: item[1].get("content_index") or 10**9):
        if not state["open"]:
            state["name"] = state.get("name") or "tool"
            yield from ensure_tool_block(openai_index)
        if state["open"]:
            yield from anthropic_sse_event("content_block_stop", {"type": "content_block_stop", "index": state["content_index"]})

    if not output_tokens and text_len:
        output_tokens = max(1, (text_len + 3) // 4)
    stop_reason = openai_finish_to_anthropic_stop_reason(finish_reason, used_tool)
    yield from anthropic_sse_event("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None}, "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens}})
    yield from anthropic_sse_event("message_stop", {"type": "message_stop"})


app = Flask(__name__)
http = requests.Session()
key_pool = KeyPool(load_keys())
started_at = time.time()


def request_id() -> str:
    return request.headers.get("X-Request-Id") or f"rpp-{int(time.time() * 1000)}"


def inbound_token() -> str:
    auth = request.headers.get("Authorization", "").strip()
    if auth:
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        return auth
    for header in ("X-API-Key", "api-key", "apikey"):
        value = request.headers.get(header, "").strip()
        if value:
            return value
    return ""


def authorize() -> Response | None:
    if request.method == "OPTIONS":
        return None
    if not REQUIRE_AUTH:
        return None
    if inbound_token() in INBOUND_TOKENS:
        return None
    return jsonify({"error": {"message": "redclaudeproxy authorization required", "type": "authentication_error"}}), 401


def cors_preflight() -> Response:
    response = Response("", status=204, content_type="text/plain")
    add_cors_headers(response)
    return response


def add_cors_headers(response: Response) -> Response:
    if not CORS_ENABLED:
        return response
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Authorization, X-API-Key, api-key, apikey, Content-Type, Accept, Origin, X-Requested-With, OpenAI-Beta, Anthropic-Beta, Anthropic-Version"
    response.headers["Access-Control-Expose-Headers"] = "Content-Type, X-Request-Id, X-RedClaudeProxy-Key, X-RedClaudeProxy-Attempts"
    response.headers["Access-Control-Max-Age"] = "86400"
    return response


@app.after_request
def after_request(response: Response) -> Response:
    return add_cors_headers(response)


def upstream_headers(key: KeyState) -> dict[str, str]:
    headers: dict[str, str] = {
        "Authorization": f"Bearer {key.key}",
        "User-Agent": "redclaudeproxy/1.0",
    }
    for name, value in request.headers.items():
        lower = name.lower()
        if lower in CLIENT_HEADER_ALLOWLIST and value:
            headers[name] = value
    if "Accept" not in headers:
        headers["Accept"] = "application/json"
    return headers


def response_headers(resp: requests.Response, key_name: str, attempts: list[dict[str, Any]]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for name, value in resp.headers.items():
        if name.lower() not in HOP_BY_HOP_HEADERS:
            headers[name] = value
    headers["X-RedClaudeProxy-Key"] = key_name
    headers["X-RedClaudeProxy-Attempts"] = str(len(attempts))
    headers["X-Request-Id"] = request_id()
    if "text/event-stream" in headers.get("Content-Type", "").lower():
        headers["Cache-Control"] = "no-cache"
        headers["X-Accel-Buffering"] = "no"
    return headers


def should_stream_request() -> bool:
    if "text/event-stream" in request.headers.get("Accept", "").lower():
        return True
    if not request.is_json:
        return False
    try:
        payload = request.get_json(silent=True) or {}
    except Exception:
        return False
    return bool(payload.get("stream"))


def proxy_v1(path: str) -> Response:
    auth_error = authorize()
    if auth_error is not None:
        return auth_error
    if request.method == "OPTIONS":
        return cors_preflight()
    if not key_pool.keys:
        return jsonify({"error": {"message": "REDCLAUDEPROXY_KEYS/REDCLAUDEPROXY_UPSTREAM_TOKEN is empty", "type": "configuration_error"}}), 503

    upstream_url = f"{UPSTREAM_BASE_URL}/{path.lstrip('/')}"
    endpoint = f"/v1/{path.lstrip('/')}"
    model_name = request_model_name()
    method = request.method
    body = request.get_data() if method not in {"GET", "HEAD"} else None
    stream = should_stream_request()
    attempts: list[dict[str, Any]] = []
    used_names: set[str] = set()
    last_response: requests.Response | None = None
    last_error = ""
    last_error_sensitive = False

    for _ in range(len(key_pool.keys)):
        key = key_pool.choose(exclude=used_names)
        if key is None:
            break
        used_names.add(key.name)
        started = time.perf_counter()
        try:
            resp = http.request(
                method,
                upstream_url,
                params=request.args,
                data=body,
                headers=upstream_headers(key),
                stream=stream,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
        except requests.RequestException as exc:
            latency = time.perf_counter() - started
            key_pool.mark_failure(key, None, str(exc), latency)
            attempts.append({"key": key.name, "status": None, "latency": round(latency, 3), "error": str(exc)[:180]})
            last_error = str(exc)
            last_error_sensitive = False
            continue

        latency = time.perf_counter() - started
        attempts.append({"key": key.name, "status": resp.status_code, "latency": round(latency, 3)})
        if resp.status_code < 400:
            if stream:
                key_pool.mark_success(key, resp.status_code, latency, model=model_name, endpoint=endpoint)
                return stream_response(resp, key, model_name, endpoint, attempts)
            content = resp.content
            usage = extract_usage_from_bytes(content)
            key_pool.mark_success(key, resp.status_code, latency, model=model_name, endpoint=endpoint, usage=usage)
            headers = response_headers(resp, key.name, attempts)
            resp.close()
            return Response(content, status=resp.status_code, headers=headers)

        last_response = resp
        raw_error = raw_error_message_from_response(resp)
        last_error = safe_upstream_error_message(resp.status_code, raw_error)
        last_error_sensitive = is_sensitive_upstream_error(resp.status_code, raw_error)
        key_pool.mark_failure(key, resp.status_code, last_error, latency)
        if resp.status_code not in RETRY_STATUSES:
            break
        resp.close()

    if last_response is not None:
        if last_response.status_code in RETRY_STATUSES or last_error_sensitive:
            response = redclaudeproxy_upstream_error_response(
                status=503,
                message="upstream provider unavailable after internal failover",
                attempts=attempts,
                source_response=last_response,
            )
            last_response.close()
            return response
        content = last_response.content
        headers = response_headers(last_response, attempts[-1]["key"], attempts)
        headers["X-RedClaudeProxy-Last-Error"] = last_error[:180]
        status = last_response.status_code
        last_response.close()
        return Response(content, status=status, headers=headers)

    return redclaudeproxy_upstream_error_response(
        status=503,
        message=last_error or "no available redclaudeproxy upstream token",
        attempts=attempts,
    )


def stream_response(resp: requests.Response, key: KeyState, model_name: str, endpoint: str, attempts: list[dict[str, Any]]) -> Response:
    headers = response_headers(resp, key.name, attempts)

    def generate():
        line_buffer = b""
        usage_recorded = False
        try:
            for chunk in resp.iter_content(chunk_size=STREAM_CHUNK_SIZE):
                if chunk:
                    if not usage_recorded:
                        line_buffer += chunk
                        while b"\n" in line_buffer:
                            raw_line, line_buffer = line_buffer.split(b"\n", 1)
                            line = raw_line.decode("utf-8", errors="replace").strip()
                            if not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if not data or data == "[DONE]":
                                continue
                            try:
                                payload = json.loads(data)
                            except json.JSONDecodeError:
                                continue
                            usage = extract_usage(payload)
                            if usage_has_values(usage):
                                key_pool.record_usage(key, model=model_name, endpoint=endpoint, usage=usage)
                                usage_recorded = True
                                break
                        if len(line_buffer) > 65536:
                            line_buffer = line_buffer[-4096:]
                    yield chunk
        finally:
            resp.close()

    return Response(generate(), status=resp.status_code, headers=headers)


def upstream_chat_completion(payload: dict[str, Any], *, endpoint: str, stream: bool) -> tuple[requests.Response | None, KeyState | None, list[dict[str, Any]], Response | None]:
    upstream_url = f"{UPSTREAM_BASE_URL}/chat/completions"
    model_name = str(payload.get("model", "") or "").strip()
    attempts: list[dict[str, Any]] = []
    used_names: set[str] = set()
    last_response: requests.Response | None = None
    last_error = ""
    last_error_sensitive = False

    for _ in range(len(key_pool.keys)):
        key = key_pool.choose(exclude=used_names)
        if key is None:
            break
        used_names.add(key.name)
        started = time.perf_counter()
        try:
            resp = http.request(
                "POST",
                upstream_url,
                json=payload,
                headers=upstream_headers(key),
                stream=stream,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
        except requests.RequestException as exc:
            latency = time.perf_counter() - started
            key_pool.mark_failure(key, None, str(exc), latency)
            attempts.append({"key": key.name, "status": None, "latency": round(latency, 3), "error": str(exc)[:180]})
            last_error = str(exc)
            last_error_sensitive = False
            continue

        latency = time.perf_counter() - started
        attempts.append({"key": key.name, "status": resp.status_code, "latency": round(latency, 3)})
        if resp.status_code < 400:
            if stream:
                key_pool.mark_success(key, resp.status_code, latency, model=model_name, endpoint=endpoint)
                return resp, key, attempts, None
            content = resp.content
            usage = extract_usage_from_bytes(content)
            key_pool.mark_success(key, resp.status_code, latency, model=model_name, endpoint=endpoint, usage=usage)
            resp._content = content
            return resp, key, attempts, None

        last_response = resp
        raw_error = raw_error_message_from_response(resp)
        last_error = safe_upstream_error_message(resp.status_code, raw_error)
        last_error_sensitive = is_sensitive_upstream_error(resp.status_code, raw_error)
        key_pool.mark_failure(key, resp.status_code, last_error, latency)
        if resp.status_code not in RETRY_STATUSES:
            break
        resp.close()

    if last_response is not None:
        if last_response.status_code in RETRY_STATUSES or last_error_sensitive:
            response = redclaudeproxy_upstream_error_response(
                status=503,
                message="upstream provider unavailable after internal failover",
                attempts=attempts,
                source_response=last_response,
            )
            last_response.close()
            return None, None, attempts, response
        content = last_response.content
        headers = response_headers(last_response, attempts[-1]["key"], attempts)
        headers["X-RedClaudeProxy-Last-Error"] = last_error[:180]
        status = last_response.status_code
        last_response.close()
        return None, None, attempts, Response(content, status=status, headers=headers)

    return None, None, attempts, redclaudeproxy_upstream_error_response(
        status=503,
        message=last_error or "no available redclaudeproxy upstream token",
        attempts=attempts,
    )


@app.get("/")
def index():
    return jsonify(
        {
            "service": SERVICE_NAME,
            "status": "ok",
            "upstream": UPSTREAM_BASE_URL,
            "endpoints": ["/v1/models", "/v1/messages", "/v1/messages/count_tokens", "/v1/chat/completions", "/v1/responses"],
            "keys_total": len(key_pool.keys),
            "keys_healthy": key_pool.healthy_count(),
            "auth_required": REQUIRE_AUTH,
        }
    )


@app.get("/healthz")
def healthz():
    status = "ok" if key_pool.keys else "error"
    return jsonify(
        {
            "ok": bool(key_pool.keys),
            "status": status,
            "service": SERVICE_NAME,
            "upstream": UPSTREAM_BASE_URL,
            "keys_total": len(key_pool.keys),
            "keys_healthy": key_pool.healthy_count(),
            "summary": key_pool.summary(),
            "uptime_seconds": round(time.time() - started_at, 1),
        }
    ), 200 if key_pool.keys else 503


@app.get("/admin/stats")
@app.get("/admin/keys")
def admin_stats():
    auth_error = authorize()
    if auth_error is not None:
        return auth_error
    return jsonify(
        {
            "service": SERVICE_NAME,
            "upstream": UPSTREAM_BASE_URL,
            "auth_required": REQUIRE_AUTH,
            "retry_statuses": sorted(RETRY_STATUSES),
            "usage_file": str(USAGE_FILE),
            "model_catalog": {
                "source": "normal-proxy",
                "include_prefixes": list(MODEL_INCLUDE_PREFIXES),
                "include_all": MODEL_INCLUDE_ALL,
                "ttl_seconds": MODEL_REFRESH_TTL_SECONDS,
                "loaded_at": _claude_model_cache_loaded_at,
                "count": len(current_claude_model_aliases()),
                "last_error": _claude_model_cache_error,
            },
            "summary": key_pool.summary(),
            "models": key_pool.model_summary(),
            "keys": key_pool.public(),
        }
    )


@app.get("/v1/models")
def claude_models():
    auth_error = authorize()
    if auth_error is not None:
        return auth_error
    models = current_claude_model_aliases(force=request.args.get("refresh") in {"1", "true", "yes"})
    return jsonify({"object": "list", "data": [public_claude_model_entry(item) for item in models]})


@app.post("/v1/messages/count_tokens")
def anthropic_count_tokens():
    auth_error = authorize()
    if auth_error is not None:
        return auth_error
    body = request.get_json(silent=True) or {}
    requested_model = str(body.get("model", "") or "")
    requested_alias = resolve_claude_model(requested_model)
    if requested_alias is not None and requested_model.strip():
        remember_claude_alias(requested_alias)
    alias = requested_alias or resolve_claude_model(
        requested_model,
        allow_fallback=True,
        fallback_alias=last_claude_alias_for_request(),
    )
    if alias is None:
        return jsonify({"error": {"message": "modelo indisponivel no Claude gateway do RED normal", "type": "invalid_request_error"}}), 400
    return jsonify({"input_tokens": estimate_anthropic_input_tokens(body)})


@app.post("/v1/messages")
def anthropic_messages():
    auth_error = authorize()
    if auth_error is not None:
        return auth_error
    if not key_pool.keys:
        return jsonify({"error": {"message": "REDCLAUDEPROXY_KEYS/REDCLAUDEPROXY_UPSTREAM_TOKEN is empty", "type": "configuration_error"}}), 503
    body = request.get_json(silent=True) or {}
    requested_model = str(body.get("model", "") or "")
    requested_alias = resolve_claude_model(requested_model)
    if requested_alias is not None and requested_model.strip():
        remember_claude_alias(requested_alias)
    alias = requested_alias or resolve_claude_model(
        requested_model,
        allow_fallback=True,
        fallback_alias=last_claude_alias_for_request(),
    )
    if alias is None:
        return jsonify(
            {
                "error": {
                    "message": "modelo indisponivel no Claude gateway do RED normal",
                    "type": "invalid_request_error",
                },
                "available_models": [item["id"] for item in current_claude_model_aliases()],
            }
        ), 400

    payload = anthropic_to_openai_payload(body, alias["target"])
    stream = bool(body.get("stream"))
    upstream, _key, _attempts, error_response = upstream_chat_completion(payload, endpoint="/v1/messages", stream=stream)
    if error_response is not None:
        return error_response
    assert upstream is not None
    if stream:
        return Response(
            anthropic_sse_from_openai_stream(upstream, alias["id"]),
            status=200,
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            content_type="text/event-stream; charset=utf-8",
        )
    try:
        data = upstream.json()
    except ValueError:
        content = upstream.content
        upstream.close()
        return Response(content, status=502, content_type="application/json")
    upstream.close()
    return jsonify(anthropic_response_from_openai(data, alias["id"]))


@app.route("/v1/<path:path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def v1_proxy(path: str):
    return proxy_v1(path)


@app.route("/<path:path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def fallback(path: str):
    if path.startswith("v1/"):
        return proxy_v1(path[3:])
    return jsonify(
        {
            "error": {
                "message": "use /v1/... endpoints",
                "type": "not_found",
            }
        }
    ), 404


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, threaded=True)

