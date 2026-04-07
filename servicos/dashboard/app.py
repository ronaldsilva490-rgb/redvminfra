#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import copy
import hashlib
import hmac
import json
import os
import platform
import re
import secrets
import shlex
import shutil
import signal
import socket
import struct
import subprocess
import threading
import time
import unicodedata
import urllib.error
import urllib.request
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    import docker
except ImportError:
    docker = None
import psutil
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from project_analyzer import (
    ANALYZER_VERSION as PROJECT_ANALYZER_VERSION,
    analyze_repo,
    generate_deploy_bundle,
    slugify as project_slugify,
)
import whatsapp_support as ws

try:
    import pty
except ImportError:
    pty = None

try:
    import termios
except ImportError:
    termios = None


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
DATA_DIR = Path(os.getenv("REDVM_DATA_DIR", str(BASE_DIR / "data")))
PROJECTS_DIR = DATA_DIR / "projects"
PROJECTS_FILE = PROJECTS_DIR / "registry.json"
PROJECT_REPORTS_DIR = PROJECTS_DIR / "reports"
PROJECT_BUNDLES_DIR = PROJECTS_DIR / "bundles"
WHATSAPP_DIR = DATA_DIR / "whatsapp"
PROJECT_RUNTIME_ROOT = Path(os.getenv("RED_PROJECT_RUNTIME_ROOT", "/opt/redvm-projects"))
PROJECT_SOURCES_ROOT = Path(os.getenv("RED_PROJECT_SOURCES_ROOT", "/opt/redvm-projects/sources"))
PROJECT_NGINX_ROUTES_DIR = Path(os.getenv("RED_PROJECT_NGINX_ROUTES_DIR", "/etc/nginx/redvm-routes"))
PROJECT_NGINX_SERVERS_DIR = Path(os.getenv("RED_PROJECT_NGINX_SERVERS_DIR", "/etc/nginx/conf.d"))

APP_TITLE = "Painel Red VM"
COOKIE_NAME = "redvm_dashboard_auth"
SECRET_KEY = os.getenv("REDVM_SECRET", "change-this-secret")
DASHBOARD_PASSWORD = os.getenv("REDVM_DASH_PASSWORD", "change-me")
TERMINAL_SHELL = os.getenv("REDVM_SHELL", "/bin/bash")
TERMINAL_HOME = os.getenv("REDVM_HOME", "/root")
PROXY_URL = os.getenv("RED_PROXY_URL", "http://127.0.0.1:8080").rstrip("/")
PROXY_SERVICE = os.getenv("RED_PROXY_SERVICE", "red-ollama-proxy.service")
PROXY_DATA_DIR = Path(os.getenv("RED_PROXY_DATA_DIR", "/var/lib/redvm-proxy"))
PROXY_KEYS_FILE = PROXY_DATA_DIR / "keys.json"
PROXY_LOG_FILE = PROXY_DATA_DIR / "proxy.log"
PROXY_MODEL_CACHE_TTL = int(os.getenv("RED_PROXY_MODEL_CACHE_TTL", "300") or 300)
PROXY_NVIDIA_SUFFIX = " (NVIDIA)"
PROXY_IMAGE_MODEL_HINTS = ("flux", "stable-diffusion")
PROJECT_PORT_BASE = int(os.getenv("RED_PROJECT_PORT_BASE", "3000") or 3000)
PROJECT_PORT_STEP = int(os.getenv("RED_PROJECT_PORT_STEP", "20") or 20)
PROJECT_WEBHOOK_BASE_PATH = os.getenv("RED_PROJECT_WEBHOOK_BASE_PATH", "/hooks/github").rstrip("/")
PROJECT_AI_TIMEOUT = int(os.getenv("RED_PROJECT_AI_TIMEOUT", "90") or 90)
PROJECT_HEALTH_RETRIES = int(os.getenv("RED_PROJECT_HEALTH_RETRIES", "6") or 6)
PROJECT_HEALTH_DELAY = float(os.getenv("RED_PROJECT_HEALTH_DELAY", "3") or 3)
PROJECT_SHARED_ROUTE_PREFIX = os.getenv("RED_PROJECT_SHARED_ROUTE_PREFIX", "/apps").rstrip("/") or "/apps"
PROJECT_PUBLIC_HOST = os.getenv("REDVM_PUBLIC_HOST", "redsystems.ddns.net").strip()
WHATSAPP_WEBHOOK_PATH = os.getenv("RED_WHATSAPP_WEBHOOK_PATH", "/hooks/whatsapp/evolution").rstrip("/") or "/hooks/whatsapp/evolution"
WHATSAPP_ALERT_COOLDOWN_SECONDS = int(os.getenv("RED_WHATSAPP_ALERT_COOLDOWN_SECONDS", "300") or 300)
WHATSAPP_ALERT_TYPES = {
    "deploy_failed",
    "deploy_success",
    "project_blocked",
    "service_failed",
    "proxy_unavailable",
    "disk_critical",
    "memory_critical",
}
WHATSAPP_RUNTIME_FILE = WHATSAPP_DIR / "runtime.json"
LOCAL_TIMEZONE_NAME = os.getenv("RED_LOCAL_TIMEZONE", "America/Sao_Paulo")
try:
    LOCAL_TIMEZONE = ZoneInfo(LOCAL_TIMEZONE_NAME)
except ZoneInfoNotFoundError:
    LOCAL_TIMEZONE = timezone(timedelta(hours=-3), name="America/Sao_Paulo")

PROXY_MODEL_DETAILS_CACHE: dict[str, dict[str, Any]] = {}
PROXY_MODEL_DETAILS_LOCK = threading.Lock()
PROJECTS_LOCK = threading.Lock()
WHATSAPP_ALERT_LOCK = threading.Lock()
WHATSAPP_SYNC_LOCK = threading.Lock()
WHATSAPP_ALERT_STATE: dict[str, float] = {}

VM_ASSISTANT_SYSTEM_PROMPT = """\
Você é o Assistente Operacional da VM Red.

Fale sempre em português do Brasil.
Use o contexto operacional fornecido pelo sistema como fonte principal da sua análise.
Ajude o operador a entender, diagnosticar, planejar e executar mudanças na VM com segurança.
Se recomendar ações, seja objetivo e prático. Sempre que fizer sentido, inclua comandos exatos ou passos claros.
Não invente estado da VM. Se algo não estiver claro no contexto, diga isso explicitamente.
Se houver risco operacional, destaque o risco antes da ação.
"""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_auth_token() -> str:
    return hmac.new(
        SECRET_KEY.encode("utf-8"),
        b"redvm-dashboard-auth",
        hashlib.sha256,
    ).hexdigest()


def is_authenticated_token(value: str | None) -> bool:
    return bool(value) and hmac.compare_digest(value, make_auth_token())


def ensure_authenticated(request: Request) -> None:
    if not is_authenticated_token(request.cookies.get(COOKIE_NAME)):
        raise HTTPException(status_code=401, detail="Não autenticado")


def require_json_body(payload: dict[str, Any], field: str) -> str:
    value = str(payload.get(field, "")).strip()
    if not value:
        raise HTTPException(status_code=400, detail=f"Campo obrigatório ausente: {field}")
    return value


def run_command(
    args: list[str],
    *,
    timeout: int = 30,
    check: bool = True,
    text: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        capture_output=True,
        text=text,
        timeout=timeout,
        check=check,
    )


def clamp_text(content: str, max_chars: int = 400_000) -> str:
    if len(content) <= max_chars:
        return content
    return content[:max_chars] + "\n\n... arquivo truncado ..."


def normalize_path(raw_path: str | None) -> Path:
    target = Path(raw_path or "/").expanduser()
    if not target.is_absolute():
        target = Path("/") / target
    return target.resolve(strict=False)


def path_payload(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "name": path.name or "/",
        "is_dir": path.is_dir(),
        "size": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }


def list_directory(raw_path: str | None) -> dict[str, Any]:
    target = normalize_path(raw_path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Caminho não encontrado")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="O caminho não é um diretório")

    items: list[dict[str, Any]] = []
    for entry in sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        try:
            stat = entry.stat()
        except OSError:
            continue
        items.append(
            {
                "name": entry.name,
                "path": str(entry.resolve(strict=False)),
                "is_dir": entry.is_dir(),
                "size": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            }
        )

    parent = str(target.parent) if target != Path("/") else None
    return {
        "current": str(target),
        "parent": parent,
        "items": items,
    }


def read_text_file(raw_path: str) -> dict[str, Any]:
    target = normalize_path(raw_path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    if not target.is_file():
        raise HTTPException(status_code=400, detail="O caminho não é um arquivo")

    content = target.read_text(encoding="utf-8", errors="replace")
    return {
        "path": str(target),
        "name": target.name,
        "content": clamp_text(content),
        "size": target.stat().st_size,
        "modified_at": datetime.fromtimestamp(target.stat().st_mtime, tz=timezone.utc).isoformat(),
    }


def save_text_file(raw_path: str, content: str) -> dict[str, Any]:
    target = normalize_path(raw_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return read_text_file(str(target))


def proxy_mask_key(value: str) -> str:
    secret = str(value or "").strip()
    if len(secret) <= 10:
        return "*" * len(secret)
    return f"{secret[:6]}...{secret[-4:]}"


def proxy_read_keys_file() -> dict[str, Any]:
    if not PROXY_KEYS_FILE.exists():
        return {"keys": [], "next_id": 1}
    try:
        data = json.loads(PROXY_KEYS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Arquivo de keys invalido: {exc}") from exc
    data.setdefault("keys", [])
    data.setdefault("next_id", 1)
    return data


def proxy_write_keys_file(data: dict[str, Any]) -> None:
    PROXY_DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROXY_KEYS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def proxy_parse_service_properties(raw: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for line in raw.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key] = value
    return result


def proxy_service_snapshot() -> dict[str, Any]:
    result = run_command(
        [
            "systemctl",
            "show",
            PROXY_SERVICE,
            "--property=Id,ActiveState,SubState,UnitFileState,MainPID,ExecMainStartTimestamp,FragmentPath",
        ],
        timeout=20,
        check=False,
    )
    props = proxy_parse_service_properties(result.stdout)
    active_state = props.get("ActiveState", "unknown")
    return {
        "service": props.get("Id", PROXY_SERVICE),
        "active": active_state,
        "sub": props.get("SubState", "unknown"),
        "unit_file_state": props.get("UnitFileState", "unknown"),
        "main_pid": int(props.get("MainPID", "0") or 0),
        "started_at": props.get("ExecMainStartTimestamp", ""),
        "fragment_path": props.get("FragmentPath", ""),
        "running": active_state == "active",
    }


def proxy_request_json(path: str, *, method: str = "GET", payload: dict[str, Any] | None = None, timeout: int = 30) -> tuple[int, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(f"{PROXY_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"raw": body}
        return exc.code, parsed
    except urllib.error.URLError as exc:
        return 0, {"error": str(exc.reason)}


def proxy_parse_log_line(line: str) -> dict[str, Any]:
    text = line.strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text, "timestamp": "", "level": "RAW", "message": text}
    payload["raw"] = text
    return payload


def proxy_log_tail(limit: int = 200) -> list[dict[str, Any]]:
    if not PROXY_LOG_FILE.exists():
        return []
    lines = PROXY_LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    parsed = [proxy_parse_log_line(line) for line in lines[-limit:]]
    return [item for item in parsed if item]


def proxy_model_details(model: str) -> dict[str, Any]:
    now = time.time()
    with PROXY_MODEL_DETAILS_LOCK:
        cached = PROXY_MODEL_DETAILS_CACHE.get(model)
        if cached and float(cached.get("expires_at", 0) or 0) > now:
            return dict(cached.get("data", {}))

    status_code, payload = proxy_request_json("/api/show", method="POST", payload={"model": model}, timeout=20)
    details = payload.get("details", {}) if isinstance(payload, dict) else {}
    if not isinstance(details, dict):
        details = {}
    capabilities_raw = payload.get("capabilities", []) if isinstance(payload, dict) else []
    if capabilities_raw is None:
        capabilities_raw = []
    families_raw = details.get("families", [])
    if families_raw is None:
        families_raw = []
    capabilities = [str(item).strip().lower() for item in capabilities_raw if str(item).strip()]
    data = {
        "status_code": status_code,
        "capabilities": capabilities,
        "supports_vision": "vision" in capabilities,
        "family": str(details.get("family", "") or ""),
        "families": [str(item) for item in families_raw if str(item).strip()],
        "parameter_size": str(details.get("parameter_size", "") or ""),
        "quantization_level": str(details.get("quantization_level", "") or ""),
        "license": str(payload.get("license", "") or "") if isinstance(payload, dict) else "",
        "template": str(payload.get("template", "") or "") if isinstance(payload, dict) else "",
        "details": details,
        "error": str(payload.get("error", "") or "") if isinstance(payload, dict) else "",
    }
    with PROXY_MODEL_DETAILS_LOCK:
        PROXY_MODEL_DETAILS_CACHE[model] = {
            "expires_at": now + PROXY_MODEL_CACHE_TTL,
            "data": data,
        }
    return dict(data)


def proxy_snapshot() -> dict[str, Any]:
    file_data = proxy_read_keys_file()
    service = proxy_service_snapshot()
    admin_status, admin_data = proxy_request_json("/admin/stats", timeout=10)
    tags_status, tags_data = proxy_request_json("/api/tags", timeout=20)
    keys = admin_data.get("keys") if admin_status == 200 and isinstance(admin_data, dict) else file_data.get("keys", [])
    now = time.time()
    visible_keys = []
    for key in keys:
        item = dict(key)
        item["key_masked"] = proxy_mask_key(item.get("key", ""))
        item.pop("key", None)
        cooldown_until = float(item.get("cooldown_until", 0) or 0)
        item["cooldown_remaining"] = max(int(cooldown_until - now), 0)
        visible_keys.append(item)

    summary = admin_data.get("summary", {}) if isinstance(admin_data, dict) else {}
    if not summary:
        summary = {
            "total": len(visible_keys),
            "active": sum(1 for key in visible_keys if key.get("active")),
            "cooldown": sum(1 for key in visible_keys if key.get("cooldown_remaining", 0) > 0),
            "total_requests": sum(int(key.get("total_requests", 0) or 0) for key in visible_keys),
            "successes": sum(int(key.get("successes", 0) or 0) for key in visible_keys),
            "failures": sum(int(key.get("failures", 0) or 0) for key in visible_keys),
        }

    tags_preview = []
    models: list[str] = []
    model_catalog: list[dict[str, Any]] = []
    if isinstance(tags_data, dict):
        model_entries = tags_data.get("models") or []
        tags_preview = model_entries[:8]
        models = [
            str(item.get("name") or item.get("model") or "").strip()
            for item in model_entries
            if str(item.get("name") or item.get("model") or "").strip()
        ]
        for item in model_entries:
            model_name = str(item.get("name") or item.get("model") or "").strip()
            if not model_name:
                continue
            detail = proxy_model_details(model_name)
            model_catalog.append(
                {
                    "name": model_name,
                    "model": model_name,
                    "size": int(item.get("size", 0) or 0),
                    "modified_at": str(item.get("modified_at", "") or ""),
                    "digest": str(item.get("digest", "") or ""),
                    "details_status": detail.get("status_code", 0),
                    "capabilities": detail.get("capabilities", []),
                    "supports_vision": bool(detail.get("supports_vision")),
                    "family": detail.get("family", ""),
                    "families": detail.get("families", []),
                    "parameter_size": detail.get("parameter_size", ""),
                    "quantization_level": detail.get("quantization_level", ""),
                    "details_error": detail.get("error", ""),
                }
            )

    return {
        "service": service,
        "proxy_url": PROXY_URL,
        "upstream": (admin_data.get("upstream") if isinstance(admin_data, dict) else None) or "",
        "status_code": admin_status,
        "reachable": admin_status == 200,
        "keys": visible_keys,
        "summary": summary,
        "cache": admin_data.get("cache", {}) if isinstance(admin_data, dict) else {},
        "tags_status": tags_status,
        "tags_error": tags_data.get("error") if isinstance(tags_data, dict) else "",
        "tags_preview": tags_preview,
        "models": models,
        "model_catalog": model_catalog,
        "data_dir": str(PROXY_DATA_DIR),
        "keys_file": str(PROXY_KEYS_FILE),
        "log_file": str(PROXY_LOG_FILE),
        "logs": proxy_log_tail(160),
    }


def proxy_snapshot_safe() -> dict[str, Any]:
    try:
        return proxy_snapshot()
    except Exception as exc:
        return {
            "service": {"service": PROXY_SERVICE, "active": "unknown", "sub": "error"},
            "proxy_url": PROXY_URL,
            "upstream": "",
            "status_code": 0,
            "reachable": False,
            "keys": [],
            "summary": {"total": 0, "active": 0, "cooldown": 0, "total_requests": 0, "successes": 0, "failures": 0},
            "cache": {"entries": 0},
            "tags_status": 0,
            "tags_error": str(exc),
            "tags_preview": [],
            "models": [],
            "model_catalog": [],
            "data_dir": str(PROXY_DATA_DIR),
            "keys_file": str(PROXY_KEYS_FILE),
            "log_file": str(PROXY_LOG_FILE),
            "logs": [],
        }


def proxy_force_reload() -> tuple[int, Any]:
    return proxy_request_json("/admin/reload", method="POST", payload={}, timeout=10)


def proxy_is_image_model(model: str) -> bool:
    normalized = str(model or "").strip()
    lowered = normalized.lower()
    return PROXY_NVIDIA_SUFFIX.lower() in lowered and any(hint in lowered for hint in PROXY_IMAGE_MODEL_HINTS)


def proxy_image_models() -> list[str]:
    status_code, payload = proxy_request_json("/api/tags", timeout=20)
    if status_code != 200 or not isinstance(payload, dict):
        return []
    entries = payload.get("models") or []
    names = [
        str(item.get("name") or item.get("model") or "").strip()
        for item in entries
        if isinstance(item, dict) and str(item.get("name") or item.get("model") or "").strip()
    ]
    return sorted((name for name in names if proxy_is_image_model(name)), key=str.lower)


def proxy_int_range(value: Any, *, default: int, minimum: int, maximum: int, step: int | None = None) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    number = max(minimum, min(maximum, number))
    if step and step > 1:
        number = number - (number % step)
    return max(minimum, min(maximum, number))


def proxy_image_min_steps(model: str) -> int:
    lowered = str(model or "").lower()
    if "stable-diffusion" in lowered:
        return 5
    if "flux.1-dev" in lowered:
        return 5
    return 1


def proxy_generate_image(payload: dict[str, Any]) -> dict[str, Any]:
    model = str(payload.get("model", "") or "").strip()
    prompt = str(payload.get("prompt", "") or "").strip()
    if not model:
        raise HTTPException(status_code=400, detail="Escolha um modelo NVIDIA de imagem.")
    if not proxy_is_image_model(model):
        raise HTTPException(status_code=400, detail="Este modelo nao parece ser um gerador de imagem NVIDIA.")
    if not prompt:
        raise HTTPException(status_code=400, detail="Digite um prompt para gerar a imagem.")
    if len(prompt) > 6000:
        raise HTTPException(status_code=400, detail="Prompt grande demais para um teste rapido.")

    image_models = proxy_image_models()
    if image_models and model not in image_models:
        raise HTTPException(status_code=400, detail="Modelo de imagem nao encontrado no catalogo atual do proxy.")

    request_payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "width": proxy_int_range(payload.get("width"), default=1024, minimum=512, maximum=1536, step=8),
        "height": proxy_int_range(payload.get("height"), default=1024, minimum=512, maximum=1536, step=8),
        "steps": proxy_int_range(payload.get("steps"), default=4, minimum=proxy_image_min_steps(model), maximum=50),
    }
    if str(payload.get("seed", "") or "").strip():
        request_payload["seed"] = proxy_int_range(payload.get("seed"), default=0, minimum=0, maximum=2_147_483_647)

    started = time.time()
    status_code, result = proxy_request_json("/api/images/generate", method="POST", payload=request_payload, timeout=180)
    if status_code != 200 or not isinstance(result, dict):
        detail = result.get("error") or result.get("message") or result.get("detail") if isinstance(result, dict) else str(result)
        raise HTTPException(status_code=502, detail=f"Falha no proxy de imagens: {detail or f'HTTP {status_code}'}")

    result.setdefault("model", model)
    result["dashboard_duration_ms"] = int((time.time() - started) * 1000)
    return result


def whatsapp_ensure_storage() -> None:
    ws.ensure_storage(WHATSAPP_DIR)


def whatsapp_read_config() -> dict[str, Any]:
    whatsapp_ensure_storage()
    config = ws.read_config(WHATSAPP_DIR)
    if not str(config.get("webhook_secret", "")).strip():
        config["webhook_secret"] = secrets.token_hex(24)
        ws.write_config(WHATSAPP_DIR, config)
    return config


def whatsapp_write_config(config: dict[str, Any]) -> dict[str, Any]:
    current = whatsapp_read_config()
    merged = ws.deep_merge(current, config or {})
    if not str(merged.get("webhook_secret", "")).strip():
        merged["webhook_secret"] = secrets.token_hex(24)
    ws.write_config(WHATSAPP_DIR, merged)
    return merged


def whatsapp_runtime_defaults() -> dict[str, Any]:
    return {
        "updated_at": "",
        "last_event": "",
        "connection_state": "",
        "qrcode_base64": "",
        "pairing_code": "",
        "last_payload_excerpt": "",
        "last_targets_sync_at": "",
        "last_targets_sync_count": 0,
        "last_targets_sync_chats": 0,
        "last_targets_sync_groups": 0,
        "last_targets_sync_status": "",
        "last_targets_sync_error": "",
        "last_webhook_sync_at": "",
        "last_webhook_sync_status": "",
        "last_webhook_sync_error": "",
        "last_webhook_sync_url": "",
    }


def whatsapp_read_runtime() -> dict[str, Any]:
    whatsapp_ensure_storage()
    payload = ws.read_json(WHATSAPP_RUNTIME_FILE, whatsapp_runtime_defaults())
    if not isinstance(payload, dict):
        payload = {}
    return ws.deep_merge(whatsapp_runtime_defaults(), payload)


def whatsapp_write_runtime(payload: dict[str, Any]) -> dict[str, Any]:
    merged = ws.deep_merge(whatsapp_runtime_defaults(), payload or {})
    ws.write_json(WHATSAPP_RUNTIME_FILE, merged)
    return merged


def whatsapp_update_runtime(changes: dict[str, Any]) -> dict[str, Any]:
    runtime = whatsapp_read_runtime()
    runtime.update(changes or {})
    runtime["updated_at"] = utc_now_iso()
    return whatsapp_write_runtime(runtime)


def parse_iso_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def whatsapp_log_append(kind: str, message: str, *, level: str = "info", meta: dict[str, Any] | None = None) -> dict[str, Any]:
    entry = {
        "id": uuid.uuid4().hex,
        "timestamp": utc_now_iso(),
        "kind": kind,
        "level": level,
        "message": message,
    }
    if meta:
        entry["meta"] = meta

    whatsapp_ensure_storage()
    log_file = ws.log_path(WHATSAPP_DIR)
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    app_ref = globals().get("app")
    if app_ref is not None and hasattr(app_ref.state, "whatsapp_log_lines"):
        app_ref.state.whatsapp_log_lines.append(entry)
        loop = getattr(app_ref.state, "loop", None)
        if loop is not None:
            try:
                asyncio.run_coroutine_threadsafe(
                    app_ref.state.hub.broadcast({"type": "whatsapp.log.append", "payload": {"lines": [entry]}}),
                    loop,
                )
            except Exception:
                pass
    return entry


def whatsapp_log_tail(limit: int = 200) -> list[dict[str, Any]]:
    whatsapp_ensure_storage()
    path = ws.log_path(WHATSAPP_DIR)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def whatsapp_public_webhook_url(request: Request | None = None) -> str:
    config = whatsapp_read_config()
    token = quote(str(config.get("webhook_secret", "") or "").strip(), safe="")
    if request is not None:
        base = str(request.base_url).rstrip("/")
        url = f"{base}{WHATSAPP_WEBHOOK_PATH}"
        return f"{url}?token={token}" if token else url
    public_host = PROJECT_PUBLIC_HOST or socket.gethostname()
    url = f"http://{public_host}{WHATSAPP_WEBHOOK_PATH}"
    return f"{url}?token={token}" if token else url


def whatsapp_masked_config(config: dict[str, Any]) -> dict[str, Any]:
    payload = dict(config)
    payload["api_key_masked"] = ws.mask_secret(str(config.get("api_key", "")))
    payload["webhook_secret_masked"] = ws.mask_secret(str(config.get("webhook_secret", "")))
    payload.pop("api_key", None)
    return payload


def whatsapp_request_json(
    config: dict[str, Any],
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
    headers: dict[str, str] | None = None,
) -> tuple[int, Any]:
    base_url = str(config.get("base_url", "") or "").rstrip("/")
    api_key = str(config.get("api_key", "") or "").strip()
    if not base_url or not api_key:
        return 0, {"error": "Evolution API nao configurada no dashboard."}

    data = None
    request_headers = {"Accept": "application/json", "apikey": api_key}
    if headers:
        request_headers.update(headers)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"

    request = urllib.request.Request(f"{base_url}{path}", data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"raw": body}
        return exc.code, parsed
    except urllib.error.URLError as exc:
        return 0, {"error": str(exc.reason)}


def whatsapp_connection_state(config: dict[str, Any]) -> dict[str, Any]:
    instance_name = str(config.get("instance_name", "") or "").strip()
    if not instance_name:
        return {"configured": False, "reachable": False, "state": "unconfigured"}
    status_code, payload = whatsapp_request_json(
        config,
        f"/instance/connectionState/{quote(instance_name, safe='')}",
        timeout=20,
    )
    state_name = ""
    if isinstance(payload, dict):
        state_name = str(payload.get("instance", {}).get("state", "") or payload.get("state", "") or "")
    return {
        "configured": bool(config.get("base_url")) and bool(config.get("api_key")),
        "reachable": status_code in {200, 404},
        "status_code": status_code,
        "state": state_name or ("open" if status_code == 200 else "unknown"),
        "raw": payload,
    }


def whatsapp_instance_details(config: dict[str, Any]) -> dict[str, Any]:
    instance_name = str(config.get("instance_name", "") or "").strip()
    if not instance_name:
        return {}
    status_code, payload = whatsapp_request_json(
        config,
        f"/instance/fetchInstances?instanceName={quote(instance_name, safe='')}",
        timeout=20,
    )
    if status_code != 200:
        return {}
    items = payload if isinstance(payload, list) else [payload]
    for item in items:
        if not isinstance(item, dict):
            continue
        instance = item.get("instance") if isinstance(item.get("instance"), dict) else item
        name = str(instance.get("instanceName", "") or instance.get("name", "") or instance.get("clientName", "") or "").strip()
        if not name or name == instance_name:
            integration = instance.get("integration")
            if isinstance(integration, dict):
                integration_name = str(integration.get("integration", "") or "").strip()
            else:
                integration_name = str(integration or "").strip()
            return {
                "instance_name": name,
                "owner": str(instance.get("owner", "") or instance.get("ownerJid", "") or instance.get("number", "") or "").strip(),
                "profile_name": str(instance.get("profileName", "") or "").strip(),
                "profile_status": str(instance.get("profileStatus", "") or "").strip(),
                "profile_picture_url": str(instance.get("profilePictureUrl", "") or instance.get("profilePicUrl", "") or "").strip(),
                "status": str(instance.get("status", "") or instance.get("connectionStatus", "") or "").strip(),
                "integration": integration_name,
            }
    return {}


def whatsapp_target_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (item.get("kind") != "group", str(item.get("name", "")).lower(), str(item.get("chat_id", "")))


def whatsapp_upsert_target(payload: dict[str, Any]) -> dict[str, Any]:
    config = whatsapp_read_config()
    target = ws.upsert_target(config, payload)
    ws.write_config(WHATSAPP_DIR, config)
    return target


def whatsapp_read_conversation(chat_id: str, *, kind: str = "private", name: str = "") -> dict[str, Any]:
    return ws.read_conversation(WHATSAPP_DIR, chat_id, kind=kind, name=name)


def whatsapp_write_conversation(conversation: dict[str, Any]) -> None:
    ws.write_conversation(WHATSAPP_DIR, conversation)


def whatsapp_snapshot(request: Request | None = None) -> dict[str, Any]:
    config = whatsapp_read_config()
    connection = whatsapp_connection_state(config)
    instance = whatsapp_instance_details(config) if bool(config.get("base_url")) and bool(config.get("api_key")) else {}
    runtime = whatsapp_read_runtime()
    if str(connection.get("state", "") or "").strip():
        runtime["connection_state"] = str(connection.get("state", "") or "").strip()
    conversations = [ws.conversation_preview(item) for item in ws.list_conversations(WHATSAPP_DIR)]
    targets = sorted(
        [ws.normalize_target(item) for item in (config.get("targets") or []) if isinstance(item, dict)],
        key=whatsapp_target_sort_key,
    )
    models = list((proxy_snapshot_safe() or {}).get("models", []))
    return {
        "configured": bool(config.get("base_url")) and bool(config.get("api_key")),
        "config": whatsapp_masked_config(config),
        "connection": connection,
        "instance": instance,
        "targets": targets,
        "conversations": conversations[:80],
        "conversation_count": len(conversations),
        "logs": list(app.state.whatsapp_log_lines) if hasattr(app.state, "whatsapp_log_lines") else whatsapp_log_tail(200),
        "models": models,
        "runtime": runtime,
        "webhook": {
            "path": WHATSAPP_WEBHOOK_PATH,
            "url": whatsapp_public_webhook_url(request),
            "secret": str(config.get("webhook_secret", "") or ""),
        },
    }


def whatsapp_is_status_chat(chat_id: str) -> bool:
    lowered = str(chat_id or "").strip().lower()
    return lowered in {"status@broadcast", "status"} or lowered.endswith("@status.broadcast")


def whatsapp_conversation_kind(chat_id: str) -> str:
    return "group" if str(chat_id or "").endswith("@g.us") else "private"


def whatsapp_nested_get(payload: dict[str, Any], path: list[str]) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def whatsapp_extract_mentions(message_payload: dict[str, Any]) -> list[str]:
    candidate_paths = [
        ["extendedTextMessage", "contextInfo", "mentionedJid"],
        ["imageMessage", "contextInfo", "mentionedJid"],
        ["videoMessage", "contextInfo", "mentionedJid"],
        ["documentMessage", "contextInfo", "mentionedJid"],
        ["conversation", "contextInfo", "mentionedJid"],
        ["contextInfo", "mentionedJid"],
    ]
    mentions: list[str] = []
    for path in candidate_paths:
        value = whatsapp_nested_get(message_payload, path)
        if isinstance(value, list):
            mentions.extend(str(item) for item in value if str(item).strip())
    return sorted({item for item in mentions if item})


def whatsapp_extract_context_info(message_payload: dict[str, Any]) -> dict[str, Any]:
    candidate_paths = [
        ["extendedTextMessage", "contextInfo"],
        ["imageMessage", "contextInfo"],
        ["videoMessage", "contextInfo"],
        ["documentMessage", "contextInfo"],
        ["buttonsResponseMessage", "contextInfo"],
        ["listResponseMessage", "contextInfo"],
        ["templateButtonReplyMessage", "contextInfo"],
        ["reactionMessage", "key"],
        ["contextInfo"],
    ]
    for path in candidate_paths:
        value = whatsapp_nested_get(message_payload, path)
        if isinstance(value, dict):
            return value
    return {}


def whatsapp_extract_text(message_payload: dict[str, Any], fallback: dict[str, Any]) -> str:
    candidate_paths = [
        ["conversation"],
        ["extendedTextMessage", "text"],
        ["imageMessage", "caption"],
        ["videoMessage", "caption"],
        ["documentMessage", "caption"],
        ["buttonsResponseMessage", "selectedDisplayText"],
        ["listResponseMessage", "title"],
        ["listResponseMessage", "singleSelectReply", "selectedRowId"],
        ["templateButtonReplyMessage", "selectedDisplayText"],
        ["templateButtonReplyMessage", "selectedId"],
        ["reactionMessage", "text"],
    ]
    for path in candidate_paths:
        value = whatsapp_nested_get(message_payload, path)
        if value is None:
            continue
        text = ws.normalize_text_content(value).strip()
        if text:
            return text
    fallback_keys = ["text", "body", "content", "caption", "speechToText"]
    for key in fallback_keys:
        text = ws.normalize_text_content(fallback.get(key, "")).strip()
        if text:
            return text
    return ""


def whatsapp_extract_quoted_entry(message_payload: dict[str, Any]) -> dict[str, Any]:
    context_info = whatsapp_extract_context_info(message_payload)
    quoted_payload = context_info.get("quotedMessage") if isinstance(context_info.get("quotedMessage"), dict) else {}
    quoted_text = whatsapp_extract_text(quoted_payload, context_info) if quoted_payload else ""
    quoted_message_id = str(
        context_info.get("stanzaId")
        or context_info.get("quotedMessageId")
        or context_info.get("quotedStanzaID")
        or ""
    ).strip()
    quoted_sender_jid = str(
        context_info.get("participant")
        or context_info.get("remoteJid")
        or context_info.get("sender")
        or ""
    ).strip()
    if not quoted_text and not quoted_message_id and not quoted_sender_jid:
        return {}
    return {
        "quoted_text": ws.normalize_text_content(quoted_text).strip(),
        "quoted_message_id": quoted_message_id,
        "quoted_sender_jid": quoted_sender_jid,
    }


def whatsapp_extract_message_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    event_name = str(payload.get("event", "") or payload.get("type", "") or "").strip()
    data = payload.get("data")
    candidates: list[Any] = []
    if isinstance(data, dict):
        if any(key in data for key in {"key", "message", "remoteJid", "chatId", "pushName"}):
            candidates.append(data)
        if isinstance(data.get("messages"), list):
            candidates.extend(data.get("messages") or [])
        if isinstance(data.get("message"), dict):
            candidates.append(data.get("message"))
    elif isinstance(data, list):
        candidates.extend(data)
    if isinstance(payload.get("messages"), list):
        candidates.extend(payload.get("messages") or [])

    rows: list[dict[str, Any]] = []
    for raw in candidates:
        if not isinstance(raw, dict):
            continue
        key = raw.get("key") if isinstance(raw.get("key"), dict) else {}
        message_payload = raw.get("message") if isinstance(raw.get("message"), dict) else raw
        remote_jid = str(
            key.get("remoteJid")
            or raw.get("remoteJid")
            or raw.get("chatId")
            or raw.get("from")
            or raw.get("jid")
            or ""
        ).strip()
        if not remote_jid:
            continue
        sender_jid = str(
            key.get("participant")
            or raw.get("participant")
            or raw.get("sender")
            or raw.get("senderJid")
            or remote_jid
        ).strip()
        rows.append(
            {
                "event": event_name,
                "id": str(key.get("id") or raw.get("id") or uuid.uuid4().hex),
                "remote_jid": remote_jid,
                "sender_jid": sender_jid,
                "from_me": bool(key.get("fromMe") or raw.get("fromMe")),
                "push_name": str(raw.get("pushName") or raw.get("senderName") or raw.get("notifyName") or "").strip(),
                "text": whatsapp_extract_text(message_payload if isinstance(message_payload, dict) else {}, raw),
                "mentions": whatsapp_extract_mentions(message_payload if isinstance(message_payload, dict) else {}),
                "quoted": whatsapp_extract_quoted_entry(message_payload if isinstance(message_payload, dict) else {}),
                "message_payload": message_payload if isinstance(message_payload, dict) else {},
                "raw": raw,
            }
        )
    return rows


def whatsapp_find_nested_string(payload: Any, candidate_keys: set[str]) -> str:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).lower() in candidate_keys and isinstance(value, str) and value.strip():
                return value.strip()
            nested = whatsapp_find_nested_string(value, candidate_keys)
            if nested:
                return nested
    elif isinstance(payload, list):
        for item in payload:
            nested = whatsapp_find_nested_string(item, candidate_keys)
            if nested:
                return nested
    return ""


def whatsapp_capture_runtime_event(event_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    lowered = str(event_name or "").strip().lower()
    excerpt = json.dumps(payload, ensure_ascii=False)[:2500]
    updates: dict[str, Any] = {"last_event": event_name, "last_payload_excerpt": excerpt}

    state_value = whatsapp_find_nested_string(payload, {"state", "status", "connection", "connectionstate"})
    normalized_state = state_value.lower().strip() if state_value else ""
    state_event = any(token in lowered for token in {"connection", "connect", "open", "close", "qrcode", "instance"})
    allowed_runtime_states = {"open", "connected", "close", "closed", "connecting", "disconnected"}
    if state_value and (state_event or normalized_state in allowed_runtime_states):
        updates["connection_state"] = state_value

    qr_value = whatsapp_find_nested_string(payload, {"qrcode", "qr", "base64", "qrbase64"})
    if qr_value and (len(qr_value) > 120 or qr_value.startswith("data:image")):
        updates["qrcode_base64"] = qr_value if qr_value.startswith("data:image") else f"data:image/png;base64,{qr_value}"

    pairing_code = whatsapp_find_nested_string(payload, {"pairingcode", "pairing_code", "code"})
    if pairing_code and len(pairing_code) < 80:
        updates["pairing_code"] = pairing_code

    state_is_open = state_value.lower() in {"open", "connected"} if state_value else False
    if "open" in lowered or "connected" in lowered or state_is_open:
        updates["qrcode_base64"] = ""
        updates["pairing_code"] = ""

    return whatsapp_update_runtime(updates)


def whatsapp_connection_ready(event_name: str, runtime: dict[str, Any]) -> bool:
    lowered = str(event_name or "").strip().lower()
    state_value = str(runtime.get("connection_state", "") or "").strip().lower()
    return state_value in {"open", "connected"} or "open" in lowered or "connected" in lowered


def whatsapp_store_targets_sync_result(
    result: dict[str, Any] | None = None,
    *,
    status: str,
    error: str = "",
) -> dict[str, Any]:
    result = result or {}
    return whatsapp_update_runtime(
        {
            "last_targets_sync_at": utc_now_iso(),
            "last_targets_sync_count": int(result.get("imported", 0) or 0),
            "last_targets_sync_chats": int(result.get("chat_count", 0) or 0),
            "last_targets_sync_groups": int(result.get("group_count", 0) or 0),
            "last_targets_sync_status": status,
            "last_targets_sync_error": error.strip(),
        }
    )


def whatsapp_store_webhook_sync_result(*, status: str, url: str = "", error: str = "") -> dict[str, Any]:
    return whatsapp_update_runtime(
        {
            "last_webhook_sync_at": utc_now_iso(),
            "last_webhook_sync_status": status,
            "last_webhook_sync_error": error.strip(),
            "last_webhook_sync_url": url.strip(),
        }
    )


def whatsapp_sync_webhook_remote(config: dict[str, Any], webhook_url: str) -> dict[str, Any]:
    instance_name = str(config.get("instance_name", "") or "").strip()
    if not instance_name:
        raise HTTPException(status_code=400, detail="Informe o nome da instancia.")
    payload = {
        "webhook": {
            "enabled": True,
            "url": webhook_url,
            "webhookByEvents": True,
            "webhookBase64": True,
            "events": ["MESSAGES_UPSERT", "MESSAGES_UPDATE", "CONNECTION_UPDATE", "QRCODE_UPDATED"],
        }
    }
    status_code, response_payload = whatsapp_request_json(
        config,
        f"/webhook/set/{quote(instance_name, safe='')}",
        method="POST",
        payload=payload,
        timeout=45,
    )
    if status_code in {200, 201, 204}:
        whatsapp_store_webhook_sync_result(status="success", url=webhook_url)
    else:
        whatsapp_store_webhook_sync_result(
            status="error",
            url=webhook_url,
            error=str(response_payload.get("error") if isinstance(response_payload, dict) else response_payload or ""),
        )
    return {"status_code": status_code, "payload": response_payload}


def whatsapp_should_auto_sync_targets(config: dict[str, Any], runtime: dict[str, Any], *, min_interval_seconds: int = 90) -> bool:
    if not bool(config.get("auto_sync_targets", True)):
        return False
    if not str(config.get("base_url", "") or "").strip():
        return False
    if not str(config.get("api_key", "") or "").strip():
        return False
    if not str(config.get("instance_name", "") or "").strip():
        return False
    if str(runtime.get("connection_state", "") or "").strip().lower() not in {"open", "connected"}:
        return False
    last_sync_at = parse_iso_datetime(runtime.get("last_targets_sync_at"))
    if last_sync_at is None:
        return True
    elapsed = (datetime.now(timezone.utc) - last_sync_at.astimezone(timezone.utc)).total_seconds()
    return elapsed >= max(15, min_interval_seconds)


def whatsapp_auto_sync_targets_if_ready(event_name: str, runtime: dict[str, Any] | None = None) -> dict[str, Any] | None:
    config = whatsapp_read_config()
    current_runtime = runtime or whatsapp_read_runtime()
    if not whatsapp_connection_ready(event_name, current_runtime):
        return None
    if not whatsapp_should_auto_sync_targets(config, current_runtime):
        return None

    with WHATSAPP_SYNC_LOCK:
        fresh_runtime = whatsapp_read_runtime()
        if not whatsapp_should_auto_sync_targets(config, fresh_runtime):
            return None
        try:
            result = whatsapp_sync_remote_targets(config)
            whatsapp_store_targets_sync_result(result, status="success")
            project_request_snapshot(include_heavy=True)
            return result
        except Exception as exc:
            whatsapp_store_targets_sync_result(status="error", error=str(exc))
            whatsapp_log_append(
                "sync",
                "Falha ao sincronizar contatos e grupos automaticamente apos a conexao do WhatsApp.",
                level="warning",
                meta={"error": str(exc), "event": event_name},
            )
            project_request_snapshot(include_heavy=True)
            return None


def whatsapp_target_for_chat(chat_id: str, *, name: str = "") -> dict[str, Any]:
    config = whatsapp_read_config()
    target = ws.find_target(config, chat_id)
    if target is not None:
        return target
    payload = {
        "chat_id": chat_id,
        "name": name,
        "kind": whatsapp_conversation_kind(chat_id),
        "alerts_enabled": False,
        "ai_enabled": True,
        "shell_enabled": False,
        "admin": False,
    }
    if bool(config.get("auto_sync_targets", True)):
        target = ws.upsert_target(config, payload)
        ws.write_config(WHATSAPP_DIR, config)
        return target
    return ws.normalize_target(payload)


def whatsapp_normalize_digits(value: Any) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def whatsapp_fold_text(value: Any) -> str:
    text = ws.normalize_text_content(value).casefold()
    return "".join(char for char in unicodedata.normalize("NFD", text) if unicodedata.category(char) != "Mn")


def whatsapp_prompt_match_text(value: Any) -> str:
    folded = whatsapp_fold_text(value)
    collapsed = re.sub(r"[^a-z0-9]+", " ", folded)
    return f" {collapsed.strip()} "


def whatsapp_prefix_pattern(prefix: str) -> re.Pattern[str] | None:
    base = ws.normalize_text_content(prefix).strip()
    if not base:
        return None
    base = re.sub(r"[\s,;:._-]+$", "", base) or base
    if not base:
        return None
    return re.compile(rf"^\s*{re.escape(base)}(?:[\s,;:._-]+|$)", flags=re.IGNORECASE)


def whatsapp_suffix_pattern(prefix: str) -> re.Pattern[str] | None:
    base = ws.normalize_text_content(prefix).strip()
    if not base:
        return None
    base = re.sub(r"[\s,;:._-]+$", "", base) or base
    if not base:
        return None
    return re.compile(rf"(?:^|[\s,;:._-]+){re.escape(base)}\s*$", flags=re.IGNORECASE)


def whatsapp_strip_group_trigger(text: str, *, prefix: str, mentioned: bool) -> tuple[bool, str]:
    clean = ws.normalize_text_content(text).strip()
    if not clean:
        return False, ""
    pattern = whatsapp_prefix_pattern(prefix)
    if pattern is not None:
        match = pattern.match(clean)
        if match:
            stripped = clean[match.end() :].strip(" ,:-")
            return True, stripped
    suffix_pattern = whatsapp_suffix_pattern(prefix)
    if suffix_pattern is not None:
        match = suffix_pattern.search(clean)
        if match:
            stripped = clean[: match.start()].strip(" ,:-")
            return True, stripped
    if mentioned:
        stripped = re.sub(r"@\S+", "", clean).strip(" ,:-")
        return True, stripped or clean
    return False, clean


def whatsapp_selected_model(config: dict[str, Any], target: dict[str, Any], conversation: dict[str, Any]) -> str:
    for candidate in [
        str(conversation.get("model", "") or "").strip(),
        str(target.get("model", "") or "").strip(),
        str(config.get("default_model", "") or "").strip(),
    ]:
        if candidate:
            return candidate
    models = list(proxy_snapshot_safe().get("models", []))
    return models[0] if models else ""


def whatsapp_model_candidates(config: dict[str, Any], target: dict[str, Any], conversation: dict[str, Any]) -> list[str]:
    available_models = [str(item).strip() for item in (proxy_snapshot_safe().get("models") or []) if str(item).strip()]
    primary_model = whatsapp_selected_model(config, target, conversation)
    fallback_config = config.get("fallback_models")
    if not isinstance(fallback_config, (list, tuple, set)):
        fallback_config = []
    configured_fallbacks = [
        str(item).strip()
        for item in fallback_config
        if str(item).strip()
    ]
    preferred_models = [
        "gemini-3-flash-preview",
        "glm-4.7",
        "qwen3-coder-next",
        "gemma3:27b",
        "qwen3-vl:235b",
    ]
    ordered: list[str] = []
    seen: set[str] = set()
    for model_name in [primary_model, *configured_fallbacks, *preferred_models, *available_models]:
        model = str(model_name or "").strip()
        if not model or model in seen:
            continue
        seen.add(model)
        if available_models and model not in available_models:
            continue
        ordered.append(model)
    if not ordered and primary_model:
        ordered.append(primary_model)
    return ordered[:4]


def whatsapp_resolve_quoted_context(
    config: dict[str, Any],
    conversation: dict[str, Any],
    entry: dict[str, Any],
) -> dict[str, Any]:
    quoted = entry.get("quoted") if isinstance(entry.get("quoted"), dict) else {}
    quoted_text = str(quoted.get("quoted_text", "") or "").strip()
    quoted_message_id = str(quoted.get("quoted_message_id", "") or "").strip()
    quoted_sender_jid = str(quoted.get("quoted_sender_jid", "") or "").strip()
    if not quoted_text and not quoted_message_id and not quoted_sender_jid:
        return {}

    quoted_role = ""
    quoted_name = ""
    if quoted_message_id:
        for item in reversed(conversation.get("messages") or []):
            if str(item.get("id", "") or "").strip() != quoted_message_id:
                continue
            quoted_role = str(item.get("role", "") or "").strip()
            quoted_name = str(item.get("quoted_name", "") or item.get("name", "") or "").strip()
            if not quoted_text:
                quoted_text = str(item.get("text", "") or "").strip()
            break

    if not quoted_role:
        bot_ids = whatsapp_bot_jids(config)
        quoted_role = "assistant" if quoted_sender_jid and quoted_sender_jid in bot_ids else "user"

    if not quoted_name:
        if quoted_role == "assistant":
            quoted_name = "RED Whatsapp A.I."
        elif quoted_sender_jid and quoted_sender_jid == str(entry.get("sender_jid", "") or "").strip():
            quoted_name = str(entry.get("push_name", "") or conversation.get("name", "") or "").strip()
        elif quoted_sender_jid:
            quoted_name = quoted_sender_jid
        else:
            quoted_name = "usuario"

    return {
        "quoted_text": ws.normalize_text_content(quoted_text).strip(),
        "quoted_message_id": quoted_message_id,
        "quoted_sender_jid": quoted_sender_jid,
        "quoted_role": quoted_role or "user",
        "quoted_name": quoted_name,
    }


def whatsapp_bot_jids(config: dict[str, Any]) -> set[str]:
    candidates: set[str] = set()
    raw_owner_values = [config.get("bot_number", "")]
    if not any(str(item or "").strip() for item in raw_owner_values):
        try:
            instance = whatsapp_instance_details(config)
        except Exception:
            instance = {}
        raw_owner_values.append(instance.get("owner", ""))
    for raw in raw_owner_values:
        text = str(raw or "").strip()
        if not text:
            continue
        candidates.add(text)
        digits = whatsapp_normalize_digits(text)
        if digits:
            candidates.add(digits)
            candidates.add(f"{digits}@s.whatsapp.net")
    return {item for item in candidates if item}


def whatsapp_ensure_bot_number(config: dict[str, Any]) -> dict[str, Any]:
    if whatsapp_normalize_digits(config.get("bot_number", "")):
        return config
    try:
        instance = whatsapp_instance_details(config)
    except Exception:
        instance = {}
    digits = whatsapp_normalize_digits(instance.get("owner", ""))
    if not digits:
        return config
    updated = dict(config)
    updated["bot_number"] = digits
    try:
        whatsapp_write_config(updated)
    except Exception:
        return updated
    return updated


def whatsapp_message_mentions_bot(config: dict[str, Any], mentions: list[Any]) -> bool:
    if not mentions:
        return False
    bot_ids = whatsapp_bot_jids(config)
    if not bot_ids:
        return False
    normalized_mentions: set[str] = set()
    for mention in mentions:
        text = str(mention or "").strip()
        if not text:
            continue
        normalized_mentions.add(text)
        digits = whatsapp_normalize_digits(text)
        if digits:
            normalized_mentions.add(digits)
            normalized_mentions.add(f"{digits}@s.whatsapp.net")
    return any(item in normalized_mentions for item in bot_ids)


def whatsapp_reply_trigger(
    config: dict[str, Any],
    target: dict[str, Any],
    conversation: dict[str, Any],
    incoming: dict[str, Any],
) -> tuple[bool, str]:
    if bool(target.get("muted")) or not bool(target.get("ai_enabled", True)):
        return False, ""

    text = ws.normalize_text_content(incoming.get("text", "")).strip()
    if not text:
        return False, ""

    if conversation.get("kind") != "group":
        return True, text

    respond_mode = str(target.get("respond_mode", "") or "prefix_or_mention").strip()
    if respond_mode == "never":
        return False, ""
    if respond_mode == "always":
        return True, text

    prefix = str(target.get("prefix_override", "") or config.get("group_prefix", "") or "red,").strip()
    mentions = incoming.get("mentions") if isinstance(incoming.get("mentions"), list) else []
    mentioned = whatsapp_message_mentions_bot(config, mentions)
    return whatsapp_strip_group_trigger(text, prefix=prefix, mentioned=mentioned)


def whatsapp_send_presence(config: dict[str, Any], chat_id: str, *, presence: str = "composing", delay: int = 2500) -> None:
    instance_name = str(config.get("instance_name", "") or "").strip()
    if not instance_name:
        return
    status_code, payload = whatsapp_request_json(
        config,
        f"/chat/sendPresence/{quote(instance_name, safe='')}",
        method="POST",
        payload={
            "number": ws.jid_to_destination(chat_id),
            "delay": delay,
            "presence": presence,
        },
        timeout=20,
    )
    if status_code not in {200, 201, 204}:
        whatsapp_log_append(
            "presence",
            f"Falha ao enviar presence para {chat_id}.",
            level="warning",
            meta={"status_code": status_code, "payload": payload},
        )


def whatsapp_mark_message_read(config: dict[str, Any], incoming: dict[str, Any]) -> None:
    instance_name = str(config.get("instance_name", "") or "").strip()
    if not instance_name or not bool(config.get("mark_as_read", True)):
        return
    status_code, payload = whatsapp_request_json(
        config,
        f"/chat/markMessageAsRead/{quote(instance_name, safe='')}",
        method="POST",
        payload={
            "readMessages": [
                {
                    "remoteJid": incoming.get("remote_jid", ""),
                    "fromMe": bool(incoming.get("from_me")),
                    "id": incoming.get("id", ""),
                }
            ]
        },
        timeout=20,
    )
    if status_code not in {200, 201, 204}:
        whatsapp_log_append(
            "read",
            f"Falha ao marcar mensagem como lida em {incoming.get('remote_jid', '')}.",
            level="warning",
            meta={"status_code": status_code, "payload": payload},
        )


def whatsapp_send_text(
    config: dict[str, Any],
    chat_id: str,
    text: str,
    *,
    incoming: dict[str, Any] | None = None,
    mention_sender: bool = False,
) -> list[dict[str, Any]]:
    instance_name = str(config.get("instance_name", "") or "").strip()
    if not instance_name:
        raise HTTPException(status_code=400, detail="Instancia WhatsApp nao configurada.")

    formatted = ws.format_markdown_for_whatsapp(text)
    chunks = ws.split_whatsapp_text(formatted)
    sent_rows: list[dict[str, Any]] = []
    mentioned: list[str] = []
    if mention_sender and incoming and incoming.get("sender_jid"):
        mentioned = [str(incoming.get("sender_jid", ""))]

    for index, chunk in enumerate(chunks):
        payload_data: dict[str, Any] = {
            "number": ws.jid_to_destination(chat_id),
            "text": chunk,
            "delay": 600,
            "linkPreview": True,
        }
        if mentioned:
            payload_data["mentioned"] = mentioned
        if incoming and index == 0 and incoming.get("id") and incoming.get("text"):
            payload_data["quoted"] = {
                "key": {"id": incoming.get("id")},
                "message": {"conversation": incoming.get("text")},
            }
        status_code, payload = whatsapp_request_json(
            config,
            f"/message/sendText/{quote(instance_name, safe='')}",
            method="POST",
            payload=payload_data,
            timeout=45,
        )
        if status_code not in {200, 201} and "quoted" in payload_data:
            payload_data.pop("quoted", None)
            status_code, payload = whatsapp_request_json(
                config,
                f"/message/sendText/{quote(instance_name, safe='')}",
                method="POST",
                payload=payload_data,
                timeout=45,
            )
        if status_code not in {200, 201}:
            raise HTTPException(
                status_code=503,
                detail=(payload.get("error") if isinstance(payload, dict) else str(payload)) or "Falha ao enviar mensagem no WhatsApp.",
            )
        sent_rows.append(payload if isinstance(payload, dict) else {"raw": payload})
    whatsapp_log_append(
        "send",
        f"Mensagem enviada para {chat_id}.",
        level="success",
        meta={"chunks": len(chunks), "preview": formatted[:180]},
    )
    return sent_rows


def whatsapp_dispatch_alert(event_type: str, title: str, body: str, *, meta: dict[str, Any] | None = None) -> None:
    if event_type not in WHATSAPP_ALERT_TYPES:
        return
    config = whatsapp_read_config()
    if not bool(config.get("enabled", False)):
        return

    key = f"{event_type}:{hashlib.sha1((title + body).encode('utf-8')).hexdigest()[:12]}"
    now = time.time()
    with WHATSAPP_ALERT_LOCK:
        last_sent = WHATSAPP_ALERT_STATE.get(key, 0.0)
        if now - last_sent < WHATSAPP_ALERT_COOLDOWN_SECONDS:
            return
        WHATSAPP_ALERT_STATE[key] = now

    targets = [
        ws.normalize_target(item)
        for item in (config.get("targets") or [])
        if isinstance(item, dict) and bool(item.get("alerts_enabled")) and not bool(item.get("muted"))
    ]
    if not targets:
        return

    message = "\n".join(part for part in [f"*{title}*", body.strip()] if part)
    success_count = 0
    for target in targets:
        try:
            whatsapp_send_text(config, str(target.get("chat_id", "")), message)
            success_count += 1
        except Exception as exc:
            whatsapp_log_append(
                "alert",
                f"Falha ao enviar alerta {event_type} para {target.get('chat_id', '')}.",
                level="warning",
                meta={"error": str(exc), "event_type": event_type},
            )
    if success_count:
        whatsapp_log_append(
            "alert",
            f"Alerta {event_type} enviado para {success_count} destino(s).",
            level="success",
            meta=meta,
        )


def whatsapp_models_text(selected_model: str = "") -> str:
    models = list(proxy_snapshot_safe().get("models", []))
    if not models:
        return "Nenhum modelo esta disponivel no proxy agora."
    lines = ["Modelos disponiveis no proxy:"]
    for index, model in enumerate(models, start=1):
        suffix = " (atual)" if model == selected_model else ""
        lines.append(f"{index}. {model}{suffix}")
    lines.append("")
    lines.append("Responda com o numero ou o nome do modelo para trocar.")
    return "\n".join(lines)


def whatsapp_resolve_model_choice(raw_text: str, models: list[str]) -> str:
    text = str(raw_text or "").strip()
    if not text:
        return ""
    if text.isdigit():
        index = int(text) - 1
        if 0 <= index < len(models):
            return models[index]
    lowered = text.lower()
    for model in models:
        if model.lower() == lowered:
            return model
    return ""


def whatsapp_format_services_summary() -> str:
    rows = parse_service_rows()
    important = [row for row in rows if row.get("active") in {"active", "failed"}][:12]
    if not important:
        return "Nenhum servico relevante foi encontrado."
    lines = ["Servicos da VM:"]
    for row in important:
        lines.append(f"- {row.get('unit')}: {row.get('active')}/{row.get('sub')}")
    return "\n".join(lines)


def whatsapp_format_docker_summary() -> str:
    snapshot = docker_snapshot()
    if not snapshot.get("available"):
        return "Docker indisponivel na VM."
    lines = [
        f"Containers: {len(snapshot.get('containers', []))}",
        f"Imagens: {len(snapshot.get('images', []))}",
    ]
    for row in snapshot.get("containers", [])[:10]:
        lines.append(f"- {row.get('name')}: {row.get('status')} ({row.get('image')})")
    return "\n".join(lines)


def whatsapp_format_proxy_summary() -> str:
    snapshot = proxy_snapshot_safe()
    return "\n".join(
        [
            f"Proxy IA: {'online' if snapshot.get('reachable') else 'offline'}",
            f"Servico: {snapshot.get('service', {}).get('active', 'unknown')}/{snapshot.get('service', {}).get('sub', 'unknown')}",
            f"Keys ativas: {snapshot.get('summary', {}).get('active', 0)}",
            f"Modelos: {len(snapshot.get('models', []))}",
        ]
    )


def whatsapp_format_projects_summary() -> str:
    projects = project_present_all(None)
    if not projects:
        return "Nenhum projeto cadastrado."
    lines = ["Projetos cadastrados:"]
    for item in projects[:12]:
        current_job = item.get("current_job") or {}
        state_name = current_job.get("status") or item.get("last_deployment_status") or "n/d"
        lines.append(f"- {item.get('name')}: {state_name}")
    return "\n".join(lines)


def whatsapp_now_local() -> datetime:
    return datetime.now(LOCAL_TIMEZONE)


def whatsapp_timezone_label() -> str:
    return getattr(LOCAL_TIMEZONE, "key", None) or LOCAL_TIMEZONE_NAME


def whatsapp_format_local_datetime(*, include_date: bool = True, include_time: bool = True) -> str:
    now = whatsapp_now_local()
    weekdays = [
        "segunda-feira",
        "terca-feira",
        "quarta-feira",
        "quinta-feira",
        "sexta-feira",
        "sabado",
        "domingo",
    ]
    months = [
        "",
        "janeiro",
        "fevereiro",
        "marco",
        "abril",
        "maio",
        "junho",
        "julho",
        "agosto",
        "setembro",
        "outubro",
        "novembro",
        "dezembro",
    ]
    lines: list[str] = []
    if include_date:
        lines.append(
            f"Data atual: {weekdays[now.weekday()]}, {now.day} de {months[now.month]} de {now.year}"
        )
    if include_time:
        lines.append(f"Hora atual: {now.strftime('%H:%M:%S')} ({whatsapp_timezone_label()})")
    return "\n".join(lines)


def whatsapp_format_vm_status() -> str:
    telemetry = telemetry_snapshot()
    return "\n".join(
        [
            f"Host: {socket.gethostname()}",
            f"CPU: {float(telemetry.get('cpu', {}).get('percent', 0) or 0):.1f}%",
            f"Memoria: {float(telemetry.get('memory', {}).get('percent', 0) or 0):.1f}%",
            f"Disco: {float(telemetry.get('disk', {}).get('percent', 0) or 0):.1f}%",
            "",
            whatsapp_format_proxy_summary(),
        ]
    )


def whatsapp_natural_response(prompt: str) -> str | None:
    normalized = whatsapp_prompt_match_text(prompt)

    asks_time = any(
        token in normalized
        for token in [
            " que horas ",
            " que horas sao ",
            " hora atual ",
            " horario atual ",
            " horario agora ",
            " horas agora ",
        ]
    )
    asks_date = any(
        token in normalized
        for token in [
            " que dia e hoje ",
            " que dia hoje ",
            " que dia e hj ",
            " que dia hj ",
            " data de hoje ",
            " dia de hoje ",
            " dia hoje ",
            " qual o dia de hoje ",
            " qual dia e hoje ",
            " qual a data ",
        ]
    )
    if asks_time or asks_date:
        return whatsapp_format_local_datetime(include_date=asks_date or not asks_time, include_time=asks_time or not asks_date)

    if any(
        token in normalized
        for token in [
            " status da vm ",
            " status do servidor ",
            " status do server ",
            " como esta a vm ",
            " como ta a vm ",
            " como esta o status da vm ",
            " como esta o servidor ",
            " como ta o servidor ",
            " saude da vm ",
            " saude do servidor ",
            " status do sistema ",
        ]
    ):
        return "\n\n".join(["Status atual da VM:", whatsapp_format_vm_status(), whatsapp_format_local_datetime()])

    if any(token in normalized for token in [" status do proxy ", " como esta o proxy ", " proxy ia ", " proxy do ollama "]):
        return "\n\n".join(["Status atual do proxy IA:", whatsapp_format_proxy_summary(), whatsapp_format_local_datetime(include_date=False, include_time=True)])

    if any(token in normalized for token in [" status do docker ", " como esta o docker ", " containers ativos ", " imagens docker "]):
        return "\n\n".join(["Status atual do Docker:", whatsapp_format_docker_summary(), whatsapp_format_local_datetime(include_date=False, include_time=True)])

    if any(token in normalized for token in [" status dos servicos ", " como estao os servicos ", " servicos da vm ", " servicos ativos "]):
        return "\n\n".join(["Status atual dos servicos:", whatsapp_format_services_summary(), whatsapp_format_local_datetime(include_date=False, include_time=True)])

    if any(token in normalized for token in [" status dos projetos ", " projetos cadastrados ", " como estao os projetos "]):
        return "\n\n".join(["Status atual dos projetos:", whatsapp_format_projects_summary(), whatsapp_format_local_datetime(include_date=False, include_time=True)])

    return None


def whatsapp_command_response(config: dict[str, Any], target: dict[str, Any], prompt: str) -> str | None:
    text = str(prompt or "").strip()
    lowered = text.lower()
    if lowered == "configurared":
        return whatsapp_models_text(str(target.get("model", "") or ""))
    if lowered in {"helpred", "ajudared"}:
        return "\n".join(
            [
                "Comandos disponiveis:",
                "- configurared",
                "- statusred",
                "- servicosred",
                "- dockerred",
                "- proxyred",
                "- projetosred",
                "- shellred <comando>  (somente admins autorizados)",
            ]
        )
    if lowered == "statusred":
        return whatsapp_format_vm_status()
    if lowered == "servicosred":
        return whatsapp_format_services_summary()
    if lowered == "dockerred":
        return whatsapp_format_docker_summary()
    if lowered == "proxyred":
        return whatsapp_format_proxy_summary()
    if lowered == "projetosred":
        return whatsapp_format_projects_summary()
    if lowered.startswith("shellred "):
        if not bool(target.get("admin")) or not bool(target.get("shell_enabled")):
            return "Este chat nao tem permissao para executar comandos shell."
        command = text[len("shellred ") :].strip()
        if not command:
            return "Informe um comando apos shellred."
        deny_tokens = ["rm -rf /", "mkfs", "shutdown", "reboot", "passwd ", "userdel ", "dd if=", ":(){", "poweroff"]
        if any(token in command.lower() for token in deny_tokens):
            return "Comando bloqueado pela politica de seguranca."
        result = run_command(["/bin/bash", "-lc", command], timeout=45, check=False)
        output = "\n".join(part for part in [result.stdout, result.stderr] if part).strip() or "(sem saida)"
        trimmed = output[:3000]
        return f"Comando: {command}\nExit code: {result.returncode}\n```\n{trimmed}\n```"
    natural_response = whatsapp_natural_response(text)
    if natural_response is not None:
        return natural_response
    return None


def whatsapp_vm_context_text() -> str:
    telemetry = telemetry_snapshot()
    proxy = proxy_snapshot_safe()
    docker_info = docker_snapshot()
    running_containers = [item.get("name") for item in docker_info.get("containers", []) if item.get("status") == "running"][:10]
    services = [row for row in parse_service_rows() if row.get("unit") in {"nginx.service", "docker.service", "ssh.service", "red-dashboard.service", PROXY_SERVICE}]
    lines = [
        f"Host: {socket.gethostname()}",
        f"CPU: {float(telemetry.get('cpu', {}).get('percent', 0) or 0):.1f}%",
        f"Memoria: {float(telemetry.get('memory', {}).get('percent', 0) or 0):.1f}%",
        f"Disco: {float(telemetry.get('disk', {}).get('percent', 0) or 0):.1f}%",
        f"Proxy IA: {'online' if proxy.get('reachable') else 'offline'} com {len(proxy.get('models', []))} modelos",
        f"Containers ativos: {', '.join(running_containers) if running_containers else 'nenhum'}",
    ]
    if services:
        lines.append("Servicos importantes:")
        lines.extend(f"- {row.get('unit')}: {row.get('active')}/{row.get('sub')}" for row in services)
    return "\n".join(lines)


def whatsapp_prompt_requests_vm_context(prompt: str) -> bool:
    normalized = whatsapp_prompt_match_text(prompt)
    tokens = [
        " vm ",
        " servidor ",
        " server ",
        " deploy ",
        " docker ",
        " container ",
        " containers ",
        " servico ",
        " servicos ",
        " nginx ",
        " firewall ",
        " memoria ",
        " memoria ram ",
        " cpu ",
        " disco ",
        " log ",
        " logs ",
        " porta ",
        " portas ",
        " proxy ",
        " postgres ",
        " postgresql ",
        " banco ",
        " status ",
        " reinicia ",
        " reiniciar ",
        " restart ",
    ]
    return any(token in normalized for token in tokens)


def whatsapp_should_use_vm_context(
    config: dict[str, Any],
    target: dict[str, Any],
    conversation: dict[str, Any],
    prompt: str,
) -> bool:
    scope = str(target.get("assistant_scope", "") or conversation.get("assistant_scope", "") or "").strip().lower()
    if scope in {"ai_only", "direct", "direct_ai"}:
        return False
    if scope in {"vm", "ops", "vm_assistant"}:
        return True
    if bool(target.get("admin")) or bool(target.get("shell_enabled")):
        return True
    return whatsapp_prompt_requests_vm_context(prompt)


def whatsapp_refresh_summary(config: dict[str, Any], conversation: dict[str, Any], model: str) -> dict[str, Any]:
    context_cfg = config.get("context") if isinstance(config.get("context"), dict) else {}
    trigger = max(int(context_cfg.get("summary_trigger_messages", 20) or 20), 6)
    keep_recent = max(int(context_cfg.get("summary_keep_recent", 10) or 10), 4)
    target_chars = max(int(context_cfg.get("summary_target_chars", 2200) or 2200), 600)
    messages = [item for item in (conversation.get("messages") or []) if isinstance(item, dict) and str(item.get("text", "")).strip()]
    if len(messages) <= trigger or not model:
        return conversation

    covered_count = int(conversation.get("summary_message_count", 0) or 0)
    new_limit = len(messages) - keep_recent
    if new_limit <= covered_count:
        return conversation

    excerpt_rows = messages[covered_count:new_limit]
    transcript = []
    for item in excerpt_rows:
        role = "assistente" if item.get("role") == "assistant" else "usuario"
        transcript.append(f"{role}: {str(item.get('text', '')).strip()}")
    if not transcript:
        return conversation

    payload = project_proxy_chat_once(
        model,
        [
            {
                "role": "system",
                "content": (
                    "Resuma a conversa abaixo em portugues do Brasil. "
                    "Mantenha apenas contexto util para proximas respostas: preferencias, decisoes, pendencias, estado operacional e fatos duradouros. "
                    f"Se houver resumo anterior, atualize-o. Limite aproximado: {target_chars} caracteres."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "resumo_anterior": conversation.get("summary", ""),
                        "novos_trechos": transcript,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        temperature=0.1,
        timeout=PROJECT_AI_TIMEOUT,
    )
    content = ""
    if isinstance(payload.get("message"), dict):
        content = str(payload["message"].get("content", "") or "")
    if not content:
        content = str(payload.get("response", "") or "")
    if content:
        conversation["summary"] = content[:target_chars]
        conversation["summary_updated_at"] = utc_now_iso()
        conversation["summary_message_count"] = new_limit
    return conversation


def whatsapp_collect_ai_response(
    model: str,
    messages: list[dict[str, Any]],
    *,
    chat_id: str,
    config: dict[str, Any],
) -> str:
    payload_data = {"model": model, "messages": messages, "stream": True}
    request = urllib.request.Request(
        f"{PROXY_URL}/api/chat",
        data=json.dumps(payload_data).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    collected: list[str] = []
    stream_timeout_seconds = 1.0
    started_at = time.monotonic()
    last_activity_at = started_at
    received_payload = False
    max_total_seconds = 45.0
    max_idle_before_first_payload = 12.0
    max_idle_after_first_payload = 18.0
    presence_stop = threading.Event()
    presence_thread: threading.Thread | None = None

    if bool(config.get("typing_presence", True)):
        def presence_worker() -> None:
            while not presence_stop.is_set():
                try:
                    whatsapp_send_presence(config, chat_id, presence="composing", delay=12000)
                except Exception:
                    pass
                if presence_stop.wait(8.0):
                    break

        presence_thread = threading.Thread(target=presence_worker, name=f"whatsapp-presence-{chat_id}", daemon=True)
        presence_thread.start()

    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            raw_socket = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
            if raw_socket is not None:
                try:
                    raw_socket.settimeout(stream_timeout_seconds)
                except Exception:
                    raw_socket = None

            while True:
                try:
                    raw_line = response.readline()
                except Exception as exc:
                    if is_stream_timeout_error(exc):
                        now = time.monotonic()
                        idle_limit = max_idle_after_first_payload if received_payload else max_idle_before_first_payload
                        if (now - started_at) >= max_total_seconds or (now - last_activity_at) >= idle_limit:
                            raise TimeoutError("Stream da IA excedeu o tempo limite de resposta.")
                        continue
                    raise

                if not raw_line:
                    break

                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                last_activity_at = time.monotonic()
                received_payload = True
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if payload.get("error"):
                    raise RuntimeError(str(payload.get("error")))

                message_payload = payload.get("message", {}) or {}
                chunk = str(message_payload.get("content", "") or "")
                if chunk:
                    collected.append(chunk)
                if payload.get("done"):
                    break
    finally:
        presence_stop.set()
        if presence_thread is not None:
            presence_thread.join(timeout=1.5)

    return "".join(collected)


def whatsapp_build_ai_messages(
    config: dict[str, Any],
    target: dict[str, Any],
    conversation: dict[str, Any],
    prompt: str,
    *,
    compact: bool = False,
) -> list[dict[str, str]]:
    context_cfg = config.get("context") if isinstance(config.get("context"), dict) else {}
    max_messages = max(int(context_cfg.get("max_messages", 28) or 28), 8)
    max_chars = max(int(context_cfg.get("max_chars", 14000) or 14000), 3000)
    if compact:
        max_messages = min(max_messages, 12)
        max_chars = min(max_chars, 6000)
    include_vm_context = whatsapp_should_use_vm_context(config, target, conversation, prompt)
    messages: list[dict[str, str]] = [
        {
            "role": "system",
            "content": "\n\n".join(
                part
                for part in [
                    str(config.get("system_prompt", "") or "").strip(),
                    f"Canal: {'grupo' if conversation.get('kind') == 'group' else 'privado'}",
                    f"Nome do chat: {conversation.get('name') or conversation.get('chat_id')}",
                    (
                        "Modo desta conversa: assistente conversacional direto. "
                        "Use primeiro o contexto da conversa e responda com naturalidade."
                        if not include_vm_context
                        else "Modo desta conversa: assistente operacional da VM. Use o contexto tecnico fornecido."
                    ),
                    whatsapp_vm_context_text() if include_vm_context else "",
                ]
                if part
            ),
        }
    ]
    if str(conversation.get("summary", "")).strip():
        messages.append(
            {
                "role": "system",
                "content": f"Resumo acumulado da conversa:\n{conversation.get('summary', '')}",
            }
        )
    messages.extend(ws.build_context_messages(conversation, max_messages=max_messages, max_chars=max_chars))
    return messages


def whatsapp_store_outgoing_message(
    conversation: dict[str, Any],
    text: str,
    *,
    model: str,
    response_payload: dict[str, Any] | None = None,
) -> None:
    message_id = ""
    if isinstance(response_payload, dict):
        message_id = str(response_payload.get("key", {}).get("id", "") or "")
    ws.append_message(
        conversation,
        {
            "id": message_id or uuid.uuid4().hex,
            "role": "assistant",
            "direction": "outgoing",
            "from_me": True,
            "text": text,
            "model": model,
            "content_type": "text",
        },
    )


def whatsapp_handle_message(entry: dict[str, Any]) -> None:
    chat_id = str(entry.get("remote_jid", "") or "").strip()
    if not chat_id or whatsapp_is_status_chat(chat_id):
        return
    entry_text = ws.normalize_text_content(entry.get("text", "")).strip()
    quoted_entry = entry.get("quoted") if isinstance(entry.get("quoted"), dict) else {}
    if not entry_text and not str(quoted_entry.get("quoted_text", "") or "").strip():
        return

    kind = whatsapp_conversation_kind(chat_id)
    target = whatsapp_target_for_chat(chat_id, name=str(entry.get("push_name", "") or ""))
    conversation = whatsapp_read_conversation(chat_id, kind=kind, name=str(target.get("name", "") or entry.get("push_name", "") or ""))
    config = whatsapp_read_config()
    if kind == "group" and not whatsapp_normalize_digits(config.get("bot_number", "")):
        config = whatsapp_ensure_bot_number(config)

    preferred_name = str(target.get("name", "") or entry.get("push_name", "") or "").strip()
    previous_name = str(conversation.get("name", "") or "").strip()
    if preferred_name and previous_name != preferred_name:
        conversation["name"] = preferred_name
        if kind != "group":
            summary_text = str(conversation.get("summary", "") or "")
            if summary_text and previous_name and previous_name != preferred_name:
                conversation["summary"] = summary_text.replace(previous_name, preferred_name)

    incoming_message = {
        "id": entry.get("id", uuid.uuid4().hex),
        "role": "assistant" if bool(entry.get("from_me")) else "user",
        "direction": "outgoing" if bool(entry.get("from_me")) else "incoming",
        "from_me": bool(entry.get("from_me")),
        "sender_jid": str(entry.get("sender_jid", "") or ""),
        "sender_name": str(entry.get("push_name", "") or ""),
        "text": entry_text,
        "content_type": "text",
    }
    incoming_message.update(whatsapp_resolve_quoted_context(config, conversation, entry))
    changed = ws.append_message(conversation, incoming_message)
    if changed:
        whatsapp_write_conversation(conversation)

    if bool(entry.get("from_me")):
        return

    try:
        whatsapp_mark_message_read(config, entry)
    except Exception:
        pass

    if bool(conversation.get("pending_model_selection")):
        should_reply, prompt = True, ws.normalize_text_content(entry.get("text", "")).strip()
    else:
        should_reply, prompt = whatsapp_reply_trigger(config, target, conversation, entry)
    if not should_reply:
        whatsapp_write_conversation(conversation)
        return
    if not prompt:
        if kind == "group":
            wake_reply = "Pode mandar. Estou ouvindo."
            response_payload = whatsapp_send_text(config, chat_id, wake_reply, incoming=entry, mention_sender=True)
            whatsapp_store_outgoing_message(
                conversation,
                wake_reply,
                model=str(conversation.get("model", "") or target.get("model", "") or config.get("default_model", "") or ""),
                response_payload=response_payload[0] if response_payload else None,
            )
            whatsapp_write_conversation(conversation)
            project_request_snapshot(include_heavy=False)
            return
        whatsapp_write_conversation(conversation)
        return

    if bool(conversation.get("pending_model_selection")):
        models = list(proxy_snapshot_safe().get("models", []))
        chosen = whatsapp_resolve_model_choice(prompt, models)
        if chosen:
            conversation["model"] = chosen
            conversation["pending_model_selection"] = False
            target = whatsapp_upsert_target({"chat_id": chat_id, "model": chosen})
            confirmation = f"Modelo atualizado para {chosen}."
            response_payload = whatsapp_send_text(config, chat_id, confirmation, incoming=entry, mention_sender=(kind == "group"))
            whatsapp_store_outgoing_message(conversation, confirmation, model=chosen, response_payload=response_payload[0] if response_payload else None)
            whatsapp_write_conversation(conversation)
            project_request_snapshot(include_heavy=False)
            return
        warning = "Nao reconheci esse modelo. Envie o numero listado ou o nome exato do modelo."
        response_payload = whatsapp_send_text(config, chat_id, warning, incoming=entry, mention_sender=(kind == "group"))
        whatsapp_store_outgoing_message(conversation, warning, model="", response_payload=response_payload[0] if response_payload else None)
        whatsapp_write_conversation(conversation)
        project_request_snapshot(include_heavy=False)
        return

    command_response = whatsapp_command_response(config, target, prompt)
    if command_response is not None:
        if prompt.lower() == "configurared":
            models = list(proxy_snapshot_safe().get("models", []))
            conversation["pending_model_selection"] = True
            conversation["pending_model_options"] = models
        response_payload = whatsapp_send_text(config, chat_id, command_response, incoming=entry, mention_sender=(kind == "group"))
        whatsapp_store_outgoing_message(
            conversation,
            command_response,
            model=str(conversation.get("model", "") or target.get("model", "") or ""),
            response_payload=response_payload[0] if response_payload else None,
        )
        whatsapp_write_conversation(conversation)
        project_request_snapshot(include_heavy=False)
        return

    model_candidates = whatsapp_model_candidates(config, target, conversation)
    if not model_candidates:
        fallback = "Nenhum modelo esta disponivel no proxy agora. Cadastre uma key valida e tente novamente."
        response_payload = whatsapp_send_text(config, chat_id, fallback, incoming=entry, mention_sender=(kind == "group"))
        whatsapp_store_outgoing_message(conversation, fallback, model="", response_payload=response_payload[0] if response_payload else None)
        whatsapp_write_conversation(conversation)
        project_request_snapshot(include_heavy=False)
        return

    use_vm_context = whatsapp_should_use_vm_context(config, target, conversation, prompt)
    selected_model = model_candidates[0]
    model = selected_model
    reply = ""
    final_error = ""
    for attempt_index, candidate_model in enumerate(model_candidates, start=1):
        compact_attempt = attempt_index > 1
        model = candidate_model
        whatsapp_log_append(
            "ai",
            f"Iniciando resposta da IA para {chat_id}.",
            meta={
                "model": model,
                "vm_context": use_vm_context,
                "kind": kind,
                "attempt": attempt_index,
                "compact": compact_attempt,
            },
        )
        ai_messages = whatsapp_build_ai_messages(config, target, conversation, prompt, compact=compact_attempt)
        ai_started_at = time.monotonic()
        try:
            reply = whatsapp_collect_ai_response(model, ai_messages, chat_id=chat_id, config=config)
            if not reply.strip():
                raise RuntimeError("Resposta vazia da IA.")
        except Exception as exc:
            final_error = project_exception_detail(exc)
            has_next = attempt_index < len(model_candidates)
            whatsapp_log_append(
                "ai",
                f"Falha ao responder no chat {chat_id}.",
                level="warning" if has_next else "error",
                meta={
                    "error": str(exc),
                    "model": model,
                    "attempt": attempt_index,
                    "fallback_next": model_candidates[attempt_index] if has_next else "",
                },
            )
            if has_next:
                continue
            reply = (
                "A IA nao conseguiu responder agora.\n\n"
                f"Detalhe tecnico: {final_error}"
            )
        else:
            whatsapp_log_append(
                "ai",
                f"Resposta da IA pronta para {chat_id}.",
                level="success",
                meta={
                    "model": model,
                    "vm_context": use_vm_context,
                    "latency": round(time.monotonic() - ai_started_at, 2),
                    "chars": len(reply),
                    "attempt": attempt_index,
                    "fallback_used": model != selected_model,
                },
            )
            break

    response_payload = whatsapp_send_text(config, chat_id, reply, incoming=entry, mention_sender=(kind == "group"))
    whatsapp_store_outgoing_message(conversation, reply, model=model, response_payload=response_payload[0] if response_payload else None)
    whatsapp_write_conversation(conversation)
    try:
        summary_before = (
            str(conversation.get("summary", "") or ""),
            int(conversation.get("summary_message_count", 0) or 0),
        )
        conversation = whatsapp_refresh_summary(config, conversation, model)
        summary_after = (
            str(conversation.get("summary", "") or ""),
            int(conversation.get("summary_message_count", 0) or 0),
        )
        if summary_after != summary_before:
            whatsapp_write_conversation(conversation)
    except Exception as exc:
        whatsapp_log_append("summary", f"Falha ao resumir a conversa {chat_id}.", level="warning", meta={"error": str(exc)})
    project_request_snapshot(include_heavy=False)


def whatsapp_process_webhook_payload(payload: dict[str, Any]) -> None:
    event_name = str(payload.get("event", "") or payload.get("type", "") or "").strip() or "unknown"
    runtime = whatsapp_capture_runtime_event(event_name, payload)
    entries = whatsapp_extract_message_entries(payload)
    whatsapp_log_append("webhook", f"Evento recebido da Evolution: {event_name}.", meta={"entries": len(entries)})
    for entry in entries:
        try:
            whatsapp_handle_message(entry)
        except Exception as exc:
            whatsapp_log_append(
                "message",
                f"Falha ao processar mensagem do chat {entry.get('remote_jid', '')}.",
                level="error",
                meta={"error": str(exc), "message_id": entry.get("id", "")},
            )
    whatsapp_auto_sync_targets_if_ready(event_name, runtime)


def whatsapp_sync_remote_targets(config: dict[str, Any]) -> dict[str, Any]:
    instance_name = str(config.get("instance_name", "") or "").strip()
    if not instance_name:
        raise HTTPException(status_code=400, detail="Informe o nome da instancia antes de sincronizar chats e grupos.")

    chats_status, chats_payload = whatsapp_request_json(
        config,
        f"/chat/findChats/{quote(instance_name, safe='')}",
        method="POST",
        timeout=45,
    )
    groups_status, groups_payload = whatsapp_request_json(
        config,
        f"/group/fetchAllGroups/{quote(instance_name, safe='')}?getParticipants=false",
        method="GET",
        timeout=45,
    )

    merged = whatsapp_read_config()
    imported = 0
    chat_count = 0
    group_count = 0

    if chats_status == 200 and isinstance(chats_payload, list):
        for item in chats_payload:
            if not isinstance(item, dict):
                continue
            chat_id = str(item.get("id", "") or item.get("remoteJid", "") or "").strip()
            if not chat_id or whatsapp_is_status_chat(chat_id):
                continue
            ws.upsert_target(
                merged,
                {
                    "chat_id": chat_id,
                    "name": str(item.get("name", "") or item.get("pushName", "") or item.get("subject", "") or "").strip(),
                    "kind": whatsapp_conversation_kind(chat_id),
                },
            )
            imported += 1
            chat_count += 1

    if groups_status == 200 and isinstance(groups_payload, list):
        for item in groups_payload:
            if not isinstance(item, dict):
                continue
            chat_id = str(item.get("id", "") or "").strip()
            if not chat_id:
                continue
            ws.upsert_target(
                merged,
                {
                    "chat_id": chat_id,
                    "name": str(item.get("subject", "") or "").strip(),
                    "kind": "group",
                },
            )
            imported += 1
            group_count += 1

    ws.write_config(WHATSAPP_DIR, merged)
    whatsapp_log_append(
        "sync",
        "Chats e grupos sincronizados com a Evolution.",
        level="success",
        meta={"imported": imported, "chat_count": chat_count, "group_count": group_count},
    )
    return {
        "imported": imported,
        "chat_count": chat_count,
        "group_count": group_count,
        "chats_status": chats_status,
        "groups_status": groups_status,
    }


def whatsapp_monitor_vm_health() -> None:
    telemetry = telemetry_snapshot()
    if float(telemetry.get("memory", {}).get("percent", 0) or 0) >= 92:
        whatsapp_dispatch_alert(
            "memory_critical",
            "Memoria critica na VM",
            f"Uso de memoria em {float(telemetry.get('memory', {}).get('percent', 0) or 0):.1f}%.",
        )
    if float(telemetry.get("disk", {}).get("percent", 0) or 0) >= 92:
        whatsapp_dispatch_alert(
            "disk_critical",
            "Disco critico na VM",
            f"Uso de disco em {float(telemetry.get('disk', {}).get('percent', 0) or 0):.1f}%.",
        )
    proxy_info = proxy_snapshot_safe()
    if not bool(proxy_info.get("reachable")):
        whatsapp_dispatch_alert(
            "proxy_unavailable",
            "Proxy IA indisponivel",
            f"Servico: {proxy_info.get('service', {}).get('active', 'unknown')}/{proxy_info.get('service', {}).get('sub', 'unknown')}",
        )
    failed_services = [row for row in parse_service_rows() if row.get("active") == "failed"][:4]
    if failed_services:
        whatsapp_dispatch_alert(
            "service_failed",
            "Servico falhou na VM",
            "\n".join(f"• {row.get('unit')}: {row.get('description')}" for row in failed_services),
        )

def project_ensure_storage() -> None:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    PROJECT_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    PROJECT_BUNDLES_DIR.mkdir(parents=True, exist_ok=True)
    PROJECT_RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    PROJECT_SOURCES_ROOT.mkdir(parents=True, exist_ok=True)


def project_registry_defaults() -> dict[str, Any]:
    return {"projects": []}


def project_read_registry() -> dict[str, Any]:
    project_ensure_storage()
    if not PROJECTS_FILE.exists():
        return project_registry_defaults()
    try:
        payload = json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return project_registry_defaults()
    if not isinstance(payload, dict):
        return project_registry_defaults()
    payload.setdefault("projects", [])
    return payload


def project_write_registry(data: dict[str, Any]) -> None:
    project_ensure_storage()
    PROJECTS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def project_report_path(project_id: str) -> Path:
    return PROJECT_REPORTS_DIR / project_id / "latest.json"


def project_bundle_dir(project_id: str) -> Path:
    return PROJECT_BUNDLES_DIR / project_id


def project_read_report(project_id: str) -> dict[str, Any]:
    target = project_report_path(project_id)
    if not target.exists():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def project_write_report(project_id: str, report: dict[str, Any]) -> None:
    target = project_report_path(project_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def project_listening_ports() -> list[int]:
    ports: set[int] = set()
    try:
        for conn in psutil.net_connections(kind="tcp"):
            if conn.status != psutil.CONN_LISTEN:
                continue
            if not conn.laddr:
                continue
            ports.add(int(conn.laddr.port))
    except Exception:
        return []
    return sorted(ports)


def project_vm_context(*, allowed_ports: list[int] | None = None) -> dict[str, Any]:
    telemetry = telemetry_snapshot()
    try:
        service = proxy_service_snapshot()
    except Exception:
        service = {"active": "unknown"}
    try:
        docker_info = docker_snapshot()
    except Exception:
        docker_info = {"available": False}
    return {
        "docker_available": bool(docker_info.get("available")),
        "proxy_active": service.get("active") == "active",
        "disk_free_bytes": int(telemetry.get("disk", {}).get("free", 0) or 0),
        "listening_ports": project_listening_ports(),
        "allowed_ports": sorted({int(item) for item in (allowed_ports or []) if int(item) > 0}),
    }


def project_name_from_repo_url(repo_url: str) -> str:
    parsed = urlparse(repo_url.strip())
    candidate = Path(parsed.path.rstrip("/")).name if parsed.path else ""
    if candidate.endswith(".git"):
        candidate = candidate[:-4]
    return candidate.strip()


def project_managed_repo_path(project_id: str) -> Path:
    return (PROJECT_SOURCES_ROOT / project_id).resolve(strict=False)


def project_request_snapshot(include_heavy: bool = True) -> None:
    loop = getattr(app.state, "loop", None)
    if loop is None:
        return
    try:
        asyncio.run_coroutine_threadsafe(emit_snapshot(include_heavy=include_heavy), loop)
    except Exception:
        return


def project_update_record(project_id: str, mutator: Any) -> dict[str, Any] | None:
    with PROJECTS_LOCK:
        registry = project_read_registry()
        projects = registry.get("projects", [])
        for index, project in enumerate(projects):
            if str(project.get("id", "")) != project_id:
                continue
            current = dict(project)
            mutator(current)
            current["updated_at"] = utc_now_iso()
            projects[index] = current
            registry["projects"] = projects
            project_write_registry(registry)
            return current
    return None


def project_append_activity(
    project_id: str,
    stage: str,
    message: str,
    *,
    level: str = "info",
    meta: dict[str, Any] | None = None,
) -> None:
    entry = {
        "id": uuid.uuid4().hex,
        "at": utc_now_iso(),
        "stage": stage,
        "level": level,
        "message": message,
    }
    if meta:
        entry["meta"] = meta

    def mutator(current: dict[str, Any]) -> None:
        activity = list(current.get("activity", []))[-79:]
        activity.append(entry)
        current["activity"] = activity

    project_update_record(project_id, mutator)
    project_request_snapshot(include_heavy=True)


def project_set_job_state(
    project_id: str,
    job_type: str,
    stage: str,
    detail: str,
    *,
    status: str = "running",
    progress: int | None = None,
    error: str = "",
) -> None:
    def mutator(current: dict[str, Any]) -> None:
        previous = dict(current.get("current_job", {}))
        started_at = previous.get("started_at") or utc_now_iso()
        current["current_job"] = {
            "id": previous.get("id") or uuid.uuid4().hex,
            "type": job_type,
            "stage": stage,
            "status": status,
            "detail": detail,
            "progress": progress,
            "started_at": started_at,
            "updated_at": utc_now_iso(),
            "completed_at": utc_now_iso() if status in {"success", "failed"} else "",
            "error": error,
        }

    project_update_record(project_id, mutator)
    project_request_snapshot(include_heavy=True)


def project_clear_pending_fix(project_id: str) -> None:
    def mutator(current: dict[str, Any]) -> None:
        current["pending_fix"] = None

    project_update_record(project_id, mutator)
    project_request_snapshot(include_heavy=True)


def project_set_pending_fix(project_id: str, pending_fix: dict[str, Any] | None) -> None:
    def mutator(current: dict[str, Any]) -> None:
        current["pending_fix"] = pending_fix

    project_update_record(project_id, mutator)
    project_request_snapshot(include_heavy=True)


def project_allocate_port_base(projects: list[dict[str, Any]]) -> int:
    used = {
        int(item.get("port_base", 0) or 0)
        for item in projects
        if int(item.get("port_base", 0) or 0) > 0
    }
    candidate = PROJECT_PORT_BASE
    while candidate in used:
        candidate += max(PROJECT_PORT_STEP, 1)
    return candidate


def project_unique_id(projects: list[dict[str, Any]], preferred: str) -> str:
    existing = {str(item.get("id", "")) for item in projects}
    base = project_slugify(preferred, fallback="project")
    candidate = base
    index = 2
    while candidate in existing:
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def project_webhook_path(project_id: str) -> str:
    return f"{PROJECT_WEBHOOK_BASE_PATH}/{project_id}"


def project_present(project: dict[str, Any], request: Request | None = None) -> dict[str, Any]:
    report = project_read_report(str(project.get("id", "")))
    webhook_path = project_webhook_path(str(project.get("id", "")))
    webhook_url = webhook_path
    if request is not None:
        webhook_url = f"{str(request.base_url).rstrip('/')}{webhook_path}"
    payload = dict(project)
    payload["analysis"] = report
    payload["webhook"] = {
        "path": webhook_path,
        "url": webhook_url,
        "secret": project.get("webhook_secret", ""),
        "provider": "github",
        "content_type": "application/json",
    }
    payload["managed_checkout"] = str(project.get("source_mode", "managed")) == "managed"
    payload["source_mode"] = project.get("source_mode", "managed")
    payload["setup_mode"] = project.get("setup_mode", "simple")
    return payload


def project_present_all(request: Request | None = None) -> list[dict[str, Any]]:
    with PROJECTS_LOCK:
        registry = project_read_registry()
        payload = [project_present(item, request) for item in registry.get("projects", [])]
    payload.sort(key=lambda item: str(item.get("name", "")).lower())
    return payload


def project_write_bundle_files(project_id: str, bundle: dict[str, Any]) -> dict[str, Any]:
    root = project_bundle_dir(project_id)
    dockerfiles_dir = root / "dockerfiles"
    dockerfiles_dir.mkdir(parents=True, exist_ok=True)
    for artifact in bundle.get("artifacts", []):
        name = str(artifact.get("name", "") or "").strip()
        if not name:
            continue
        target = dockerfiles_dir / name if artifact.get("kind") == "dockerfile" else root / name
        target.write_text(str(artifact.get("content", "")), encoding="utf-8")
        artifact["written_to"] = str(target)
    bundle["bundle_root"] = str(root)
    return bundle


def project_find_record(project_id: str) -> dict[str, Any] | None:
    with PROJECTS_LOCK:
        registry = project_read_registry()
        for project in registry.get("projects", []):
            if str(project.get("id", "")) == project_id:
                return dict(project)
    return None


def project_merge_overrides(current: dict[str, Any] | None, changes: dict[str, Any] | None) -> dict[str, Any]:
    merged = copy.deepcopy(current or {})
    if not isinstance(changes, dict):
        return merged
    merged.setdefault("services", {})
    for service_name, service_changes in (changes.get("services") or {}).items():
        if not isinstance(service_changes, dict):
            continue
        target = dict(merged["services"].get(service_name, {}))
        for key, value in service_changes.items():
            if value in (None, ""):
                continue
            target[str(key)] = value
        merged["services"][str(service_name)] = target
    return merged


def project_relaxed_install_command(component: dict[str, Any]) -> str:
    manager = str(component.get("package_manager", "") or "").strip()
    if manager == "pnpm":
        return "corepack enable && pnpm install --no-frozen-lockfile"
    if manager == "yarn":
        return "corepack enable && yarn install"
    if manager == "bun":
        return "bun install"
    return "npm install"


def project_apply_overrides_to_report(project: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    overrides = project.get("deployment_overrides") or {}
    service_overrides = overrides.get("services") if isinstance(overrides, dict) else {}
    if not isinstance(service_overrides, dict) or not service_overrides:
        return report

    components = [dict(item) for item in report.get("components", [])]
    services = [dict(item) for item in report.get("deployment_plan", {}).get("services", [])]
    routes = [dict(item) for item in report.get("deployment_plan", {}).get("routes", [])]
    component_by_id = {str(item.get("id", "")): item for item in components}
    applied: list[dict[str, Any]] = []

    for service in services:
        service_name = str(service.get("service_name", "") or "")
        override = service_overrides.get(service_name)
        if not isinstance(override, dict):
            continue
        component = component_by_id.get(str(service.get("component_id", "") or ""))
        if component is None:
            continue
        item_applied: dict[str, Any] = {"service_name": service_name}
        install_command = str(override.get("install_command", "") or "").strip()
        start_command = str(override.get("start_command", "") or "").strip()
        health_path = str(override.get("health_path", "") or "").strip()
        if install_command:
            component["override_install_command"] = install_command
            item_applied["install_command"] = install_command
        if start_command:
            component["start_command"] = start_command
            item_applied["start_command"] = start_command
        if health_path:
            component["health_path"] = health_path
            service["health_path"] = health_path
            item_applied["health_path"] = health_path
            for route in routes:
                if str(route.get("component_id", "") or "") == str(component.get("id", "") or ""):
                    route["health_path"] = health_path
        if len(item_applied) > 1:
            applied.append(item_applied)

    report["components"] = components
    report.setdefault("deployment_plan", {})
    report["deployment_plan"]["services"] = services
    report["deployment_plan"]["routes"] = routes
    report["applied_overrides"] = applied
    return report


def project_sync_repository(project_id: str, *, checkout_ref: str = "") -> dict[str, Any]:
    project = project_find_record(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projeto nao encontrado.")

    repo_path = Path(str(project.get("repo_path", "") or "")).expanduser().resolve(strict=False)
    source_mode = str(project.get("source_mode", "managed") or "managed")
    branch = str(project.get("branch", "main") or "main").strip() or "main"
    repo_url = str(project.get("repo_url", "") or "").strip()

    if source_mode != "managed":
        if not repo_path.exists():
            raise HTTPException(status_code=400, detail="O caminho manual do repositorio nao existe na VM.")
        head = ""
        if (repo_path / ".git").exists():
            try:
                head = run_command(["git", "-C", str(repo_path), "rev-parse", "HEAD"], timeout=30).stdout.strip()
            except Exception:
                head = ""
        project_append_activity(project_id, "sync", f"Usando checkout manual em {repo_path}.", level="info")
        project_update_record(
            project_id,
            lambda current: current.update({"last_synced_at": utc_now_iso(), "last_synced_commit": head}),
        )
        return {"mode": "manual", "path": str(repo_path), "head": head}

    if not repo_url:
        raise HTTPException(status_code=400, detail="Este projeto esta em modo gerenciado, mas nao tem URL de repositorio configurada.")

    PROJECT_SOURCES_ROOT.mkdir(parents=True, exist_ok=True)
    repo_path.parent.mkdir(parents=True, exist_ok=True)
    project_append_activity(project_id, "sync", f"Sincronizando repositorio {repo_url}.", level="info")

    if repo_path.exists() and not (repo_path / ".git").exists():
        shutil.rmtree(repo_path, ignore_errors=True)

    if not repo_path.exists():
        project_append_activity(project_id, "sync", "Baixando o repositorio pela primeira vez na VM.", level="info")
        run_command(
            ["git", "clone", "--branch", branch, "--single-branch", repo_url, str(repo_path)],
            timeout=1800,
        )
    else:
        run_command(["git", "-C", str(repo_path), "remote", "set-url", "origin", repo_url], timeout=30, check=False)
        run_command(["git", "-C", str(repo_path), "fetch", "origin", "--prune"], timeout=1800)

    if checkout_ref:
        run_command(["git", "-C", str(repo_path), "fetch", "origin", checkout_ref, "--depth", "1"], timeout=1800, check=False)
        run_command(["git", "-C", str(repo_path), "checkout", "--force", checkout_ref], timeout=180)
    else:
        remote_ref = f"origin/{branch}"
        run_command(["git", "-C", str(repo_path), "checkout", "--force", "-B", branch, remote_ref], timeout=180)
        run_command(["git", "-C", str(repo_path), "reset", "--hard", remote_ref], timeout=180)

    run_command(["git", "-C", str(repo_path), "clean", "-fd"], timeout=180, check=False)
    head = run_command(["git", "-C", str(repo_path), "rev-parse", "HEAD"], timeout=30).stdout.strip()
    project_update_record(
        project_id,
        lambda current: current.update({"last_synced_at": utc_now_iso(), "last_synced_commit": head}),
    )
    project_append_activity(project_id, "sync", f"Repositorio sincronizado na revisao {head[:12] or 'desconhecida'}.", level="success")
    return {"mode": "managed", "path": str(repo_path), "head": head}


def project_exception_detail(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    if isinstance(exc, subprocess.CalledProcessError):
        stdout = str(exc.stdout or "").strip()
        stderr = str(exc.stderr or "").strip()
        details = [part for part in [stdout, stderr] if part]
        return "\n".join(details) or str(exc)
    return str(exc)


def project_compose_logs(compose_file: Path, deploy_env: Path) -> str:
    if not compose_file.exists() or not deploy_env.exists():
        return ""
    result = project_run_compose(
        compose_file,
        deploy_env,
        "logs",
        "--no-color",
        "--tail",
        "120",
        check=False,
        timeout=240,
    )
    return "\n".join(part for part in [result.stdout, result.stderr] if part).strip()


def project_guess_fix_candidates(project: dict[str, Any], report: dict[str, Any], error_text: str) -> list[dict[str, Any]]:
    lower = error_text.lower()
    candidates: list[dict[str, Any]] = []
    components_by_id = {str(item.get("id", "")): dict(item) for item in report.get("components", [])}

    def add_candidate(item: dict[str, Any]) -> None:
        candidate_id = str(item.get("id", "") or "")
        if not candidate_id:
            return
        if any(existing.get("id") == candidate_id for existing in candidates):
            return
        candidates.append(item)

    lockfile_failure = any(token in lower for token in ["npm ci", "frozen-lockfile", "package-lock", "lockfile"])
    if lockfile_failure:
        for service in report.get("deployment_plan", {}).get("services", []):
            component = components_by_id.get(str(service.get("component_id", "") or ""))
            if not component or str(component.get("runtime", "")) != "node":
                continue
            install_command = project_relaxed_install_command(component)
            add_candidate(
                {
                    "id": f"relax-install:{service.get('service_name')}",
                    "label": f"Relaxar instalacao do {service.get('service_name')}",
                    "description": "Troca a instalacao estrita por uma versao mais tolerante para destravar builds com lockfile divergente.",
                    "changes": {"services": {str(service.get("service_name")): {"install_command": install_command}}},
                }
            )

    if any(token in lower for token in ["health check falhou", "urlopen error", "connection refused", "http error 404", "http 404"]):
        for service in report.get("deployment_plan", {}).get("services", []):
            component = components_by_id.get(str(service.get("component_id", "") or ""))
            if not component:
                continue
            if str(service.get("health_path", "/") or "/") == "/":
                continue
            if str(component.get("type", "")) not in {"frontend", "fullstack", "backend"}:
                continue
            add_candidate(
                {
                    "id": f"health-root:{service.get('service_name')}",
                    "label": f"Ajustar health check do {service.get('service_name')}",
                    "description": "Usa a raiz '/' como health check quando o endpoint detectado nao responde do jeito esperado.",
                    "changes": {"services": {str(service.get("service_name")): {"health_path": "/"}}},
                }
            )

    if "python main.py" in lower or ("can't open file" in lower and "main.py" in lower):
        repo_root = Path(str(project.get("repo_path", "") or ""))
        for service in report.get("deployment_plan", {}).get("services", []):
            component = components_by_id.get(str(service.get("component_id", "") or ""))
            if not component or str(component.get("runtime", "")) != "python":
                continue
            rel_path = str(component.get("rel_path", ".") or ".")
            component_root = (repo_root / rel_path).resolve(strict=False)
            for filename in ("app.py", "server.py", "main.py"):
                if not (component_root / filename).exists():
                    continue
                start_command = f"cd {rel_path} && python {filename}" if rel_path != "." else f"python {filename}"
                add_candidate(
                    {
                        "id": f"python-entry:{service.get('service_name')}:{filename}",
                        "label": f"Ajustar start do {service.get('service_name')}",
                        "description": f"Troca o comando de start para usar {filename}, que existe no repositorio detectado.",
                        "changes": {"services": {str(service.get("service_name")): {"start_command": start_command}}},
                    }
                )
                break

    return candidates


def project_generate_fix_ai_report(project: dict[str, Any], report: dict[str, Any], failure_context: dict[str, Any]) -> dict[str, Any]:
    proxy_info = proxy_snapshot()
    models = list(proxy_info.get("models", []))
    selected_model = models[0] if models else ""
    fallback = {
        "status": "unavailable",
        "model": "",
        "generated_at": utc_now_iso(),
        "content": "A IA de suporte nao esta disponivel agora. Revise o erro bruto e use uma das correcoes sugeridas abaixo, se houver.",
    }
    if not selected_model:
        return fallback

    context = {
        "project": {
            "name": project.get("name"),
            "repo_url": project.get("repo_url"),
            "branch": project.get("branch"),
        },
        "classification": report.get("classification"),
        "diagnostics": report.get("diagnostics"),
        "failure": failure_context,
    }
    try:
        payload = project_proxy_chat_once(
            selected_model,
            [
                {
                    "role": "system",
                    "content": (
                        "Voce e um engenheiro de plataforma analisando falhas de deploy numa VM Linux com Docker e Nginx. "
                        "Responda em portugues do Brasil. "
                        "Explique em markdown: O que falhou, Se o problema parece do repositorio, da geracao ou da VM, "
                        "Qual o menor proximo passo seguro e Quais riscos observar. "
                        "Nao invente fatos alem do contexto."
                    ),
                },
                {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
            ],
            timeout=PROJECT_AI_TIMEOUT,
        )
    except Exception as exc:
        return {
            "status": "error",
            "model": selected_model,
            "generated_at": utc_now_iso(),
            "content": f"Falha ao gerar analise da correcao por IA: {project_exception_detail(exc)}",
        }

    content = ""
    if isinstance(payload.get("message"), dict):
        content = str(payload["message"].get("content", "") or "")
    if not content:
        content = str(payload.get("response", "") or "")
    return {
        "status": "ready" if content else "empty",
        "model": selected_model,
        "generated_at": utc_now_iso(),
        "content": content or fallback["content"],
    }


def project_prepare_pending_fix(project: dict[str, Any], report: dict[str, Any], *, stage: str, error_text: str, logs: str = "") -> dict[str, Any] | None:
    raw_error = "\n\n".join(part for part in [error_text.strip(), logs.strip()] if part).strip()
    if not raw_error:
        return None
    excerpt = raw_error[:20_000]
    failure_context = {
        "stage": stage,
        "error_excerpt": excerpt,
        "generated_at": utc_now_iso(),
    }
    candidates = project_guess_fix_candidates(project, report, excerpt)
    ai_report = project_generate_fix_ai_report(project, report, failure_context)
    return {
        "status": "ready",
        "generated_at": utc_now_iso(),
        "stage": stage,
        "error_excerpt": excerpt,
        "ai_report": ai_report,
        "candidates": candidates,
    }


def project_apply_fix_candidate(project_id: str, candidate_id: str) -> dict[str, Any]:
    project = project_find_record(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projeto nao encontrado.")
    pending_fix = project.get("pending_fix") or {}
    candidates = pending_fix.get("candidates") if isinstance(pending_fix, dict) else []
    selected = next((item for item in (candidates or []) if str(item.get("id", "")) == candidate_id), None)
    if not isinstance(selected, dict):
        raise HTTPException(status_code=404, detail="Correcao sugerida nao encontrada.")
    changes = selected.get("changes")
    if not isinstance(changes, dict):
        raise HTTPException(status_code=400, detail="Esta sugestao nao possui uma correcao aplicavel automaticamente.")

    updated = project_update_record(
        project_id,
        lambda current: current.update(
            {
                "deployment_overrides": project_merge_overrides(current.get("deployment_overrides"), changes),
                "pending_fix": None,
            }
        ),
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Projeto nao encontrado.")
    project_append_activity(project_id, "fix", f"Correcao aplicada: {selected.get('label', candidate_id)}.", level="success")
    return updated


def project_store(payload: dict[str, Any]) -> dict[str, Any]:
    now = utc_now_iso()
    project_id = str(payload.get("id", "")).strip()
    repo_url = str(payload.get("repo_url", "") or "").strip()
    name = str(payload.get("name", "") or "").strip() or project_name_from_repo_url(repo_url)
    branch = str(payload.get("branch", "main") or "main").strip() or "main"
    manual_repo_path = str(payload.get("repo_path", "") or "").strip()
    source_mode = str(payload.get("source_mode", "") or "").strip().lower()
    setup_mode = str(payload.get("setup_mode", "simple") or "simple").strip().lower() or "simple"
    default_domain = str(payload.get("default_domain", "") or "").strip()
    default_base_path = str(payload.get("default_base_path", "/") or "/").strip() or "/"
    if not default_base_path.startswith("/"):
        default_base_path = f"/{default_base_path.lstrip('/')}"
    enabled = bool(payload.get("enabled", True))
    auto_deploy = bool(payload.get("auto_deploy", True))

    if not name:
        raise HTTPException(status_code=400, detail="Informe ao menos o endereco do repositorio ou um nome para o projeto.")

    with PROJECTS_LOCK:
        registry = project_read_registry()
        projects = registry.get("projects", [])
        current_index = -1
        for index, project in enumerate(projects):
            if str(project.get("id", "")) == project_id and project_id:
                current_index = index
                break

        if current_index >= 0:
            current = dict(projects[current_index])
        else:
            current = {
                "id": project_unique_id(projects, project_id or name),
                "created_at": now,
                "port_base": project_allocate_port_base(projects),
                "webhook_secret": secrets.token_hex(24),
                "deliveries": [],
                "deployments": [],
                "activity": [],
            }

        if source_mode not in {"managed", "manual"}:
            source_mode = "manual" if manual_repo_path else ("managed" if repo_url else "manual")

        if source_mode == "managed":
            if not repo_url:
                raise HTTPException(status_code=400, detail="No modo simples, informe a URL do repositorio para a VM baixar o codigo.")
            repo_path = str(project_managed_repo_path(str(current.get("id", ""))))
        else:
            repo_path = manual_repo_path or str(current.get("repo_path", "") or "").strip()
            if not repo_path:
                raise HTTPException(status_code=400, detail="Informe o caminho local do repositorio ou use o checkout gerenciado pela VM.")

        current.update(
            {
                "name": name,
                "repo_path": repo_path,
                "repo_url": repo_url,
                "branch": branch,
                "default_domain": default_domain,
                "default_base_path": default_base_path,
                "enabled": enabled,
                "auto_deploy": auto_deploy,
                "source_mode": source_mode,
                "setup_mode": setup_mode,
                "updated_at": now,
            }
        )

        if current_index >= 0:
            projects[current_index] = current
        else:
            projects.append(current)
        registry["projects"] = projects
        project_write_registry(registry)

    return current


def project_delete(project_id: str) -> None:
    project = project_find_record(project_id)
    latest_success = project_latest_successful_deployment(project_id)
    if latest_success:
        release_dir = Path(str(latest_success.get("release_dir", "") or ""))
        compose_file = release_dir / "docker-compose.generated.yml"
        deploy_env = release_dir / ".deploy.env"
        if compose_file.exists() and deploy_env.exists():
            project_run_compose(compose_file, deploy_env, "down", "--remove-orphans", check=False, timeout=600)
    with PROJECTS_LOCK:
        registry = project_read_registry()
        registry["projects"] = [
            item for item in registry.get("projects", []) if str(item.get("id", "")) != project_id
        ]
        project_write_registry(registry)
    report_dir = project_report_path(project_id).parent
    if report_dir.exists():
        for target in sorted(report_dir.rglob("*"), reverse=True):
            if target.is_file():
                target.unlink(missing_ok=True)
            elif target.is_dir():
                target.rmdir()
        report_dir.rmdir()
    bundle_dir = project_bundle_dir(project_id)
    if bundle_dir.exists():
        for target in sorted(bundle_dir.rglob("*"), reverse=True):
            if target.is_file():
                target.unlink(missing_ok=True)
            elif target.is_dir():
                target.rmdir()
        bundle_dir.rmdir()
    runtime_dir = project_runtime_dir(project_id)
    if runtime_dir.exists():
        for target in sorted(runtime_dir.rglob("*"), reverse=True):
            if target.is_file():
                target.unlink(missing_ok=True)
            elif target.is_dir():
                target.rmdir()
        runtime_dir.rmdir()
    if project and str(project.get("source_mode", "managed")) == "managed":
        source_dir = Path(str(project.get("repo_path", "") or ""))
        if source_dir.exists() and PROJECT_SOURCES_ROOT in source_dir.parents:
            for target in sorted(source_dir.rglob("*"), reverse=True):
                if target.is_file():
                    target.unlink(missing_ok=True)
                elif target.is_dir():
                    target.rmdir()
            source_dir.rmdir()
    project_route_include_path(project_id).unlink(missing_ok=True)
    project_server_conf_path(project_id).unlink(missing_ok=True)
    run_command(["nginx", "-t"], timeout=30, check=False)
    run_command(["systemctl", "reload", "nginx"], timeout=30, check=False)


def project_append_delivery(project_id: str, delivery: dict[str, Any]) -> None:
    with PROJECTS_LOCK:
        registry = project_read_registry()
        projects = registry.get("projects", [])
        for index, project in enumerate(projects):
            if str(project.get("id", "")) != project_id:
                continue
            current = dict(project)
            deliveries = list(current.get("deliveries", []))[-19:]
            deliveries.append(delivery)
            current["deliveries"] = deliveries
            current["updated_at"] = utc_now_iso()
            projects[index] = current
            registry["projects"] = projects
            project_write_registry(registry)
            project_request_snapshot(include_heavy=True)
            return


def project_update_delivery(project_id: str, delivery_id: str, **changes: Any) -> None:
    with PROJECTS_LOCK:
        registry = project_read_registry()
        projects = registry.get("projects", [])
        for index, project in enumerate(projects):
            if str(project.get("id", "")) != project_id:
                continue
            current = dict(project)
            deliveries = []
            for row in current.get("deliveries", []):
                item = dict(row)
                if str(item.get("id", "")) == delivery_id:
                    item.update(changes)
                deliveries.append(item)
            current["deliveries"] = deliveries
            current["updated_at"] = utc_now_iso()
            projects[index] = current
            registry["projects"] = projects
            project_write_registry(registry)
            project_request_snapshot(include_heavy=True)
            return


def project_append_deployment(project_id: str, deployment: dict[str, Any]) -> None:
    with PROJECTS_LOCK:
        registry = project_read_registry()
        projects = registry.get("projects", [])
        for index, project in enumerate(projects):
            if str(project.get("id", "")) != project_id:
                continue
            current = dict(project)
            deployments = list(current.get("deployments", []))[-19:]
            deployments.append(deployment)
            current["deployments"] = deployments
            current["updated_at"] = utc_now_iso()
            projects[index] = current
            registry["projects"] = projects
            project_write_registry(registry)
            project_request_snapshot(include_heavy=True)
            return


def project_update_deployment(project_id: str, deployment_id: str, **changes: Any) -> None:
    with PROJECTS_LOCK:
        registry = project_read_registry()
        projects = registry.get("projects", [])
        for index, project in enumerate(projects):
            if str(project.get("id", "")) != project_id:
                continue
            current = dict(project)
            deployments = []
            for row in current.get("deployments", []):
                item = dict(row)
                if str(item.get("id", "")) == deployment_id:
                    item.update(changes)
                deployments.append(item)
            current["deployments"] = deployments
            current["updated_at"] = utc_now_iso()
            projects[index] = current
            registry["projects"] = projects
            project_write_registry(registry)
            project_request_snapshot(include_heavy=True)
            return


def project_latest_successful_deployment(project_id: str) -> dict[str, Any] | None:
    project = project_find_record(project_id)
    if project is None:
        return None
    deployments = [row for row in project.get("deployments", []) if row.get("status") == "success"]
    if not deployments:
        return None
    return dict(deployments[-1])


def project_runtime_dir(project_id: str) -> Path:
    return PROJECT_RUNTIME_ROOT / project_id


def project_release_dir(project_id: str, release_id: str) -> Path:
    return project_runtime_dir(project_id) / "releases" / release_id


def project_ensure_runtime_dirs(project_id: str) -> None:
    root = project_runtime_dir(project_id)
    (root / "releases").mkdir(parents=True, exist_ok=True)
    PROJECT_NGINX_ROUTES_DIR.mkdir(parents=True, exist_ok=True)
    PROJECT_NGINX_SERVERS_DIR.mkdir(parents=True, exist_ok=True)


def project_shared_route_base(project_id: str) -> str:
    return f"{PROJECT_SHARED_ROUTE_PREFIX}/{project_id}".rstrip("/")


def project_build_effective_routes(project: dict[str, Any], report: dict[str, Any]) -> list[dict[str, Any]]:
    routes = []
    dashboard_domain = PROJECT_PUBLIC_HOST.lower()
    project_domain = str(project.get("default_domain", "") or "").strip().lower()
    dedicated_domain = bool(project_domain) and project_domain != dashboard_domain
    base_shared = project_shared_route_base(str(project.get("id", "")))
    for route in report.get("deployment_plan", {}).get("routes", []):
        item = dict(route)
        component = next((row for row in report.get("components", []) if row.get("id") == item.get("component_id")), {})
        item["component_type"] = component.get("type", "service")
        item["component_name"] = component.get("name", item.get("component_id"))
        item["domain"] = project_domain or dashboard_domain
        item["dedicated_domain"] = dedicated_domain
        if dedicated_domain:
            item["effective_path"] = item.get("path") or "/"
            item["publish_mode"] = "server"
        else:
            if item.get("component_type") == "backend":
                suffix = "/api"
            elif item.get("component_type") == "worker":
                suffix = f"/{project_slugify(item.get('component_name') or item.get('component_id') or 'worker', fallback='worker')}"
            else:
                suffix = ""
            item["effective_path"] = f"{base_shared}{suffix}/"
            item["publish_mode"] = "shared"
            if item.get("component_type") in {"frontend", "fullstack"}:
                item["path_warning"] = "Frontend em host compartilhado pode exigir ajuste de base path para ficar perfeito."
        routes.append(item)
    return routes


def project_route_include_path(project_id: str) -> Path:
    return PROJECT_NGINX_ROUTES_DIR / f"{project_id}.conf"


def project_server_conf_path(project_id: str) -> Path:
    return PROJECT_NGINX_SERVERS_DIR / f"{project_id}.conf"


def project_build_nginx_publish_content(project: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    routes = project_build_effective_routes(project, report)
    shared_lines: list[str] = []
    server_lines: list[str] = []
    domain = str(project.get("default_domain", "") or "").strip() or PROJECT_PUBLIC_HOST
    shared_route_base = project_shared_route_base(str(project.get("id", "")))

    shared_lines.append(f"# redvm project routes: {project.get('id')}")
    for route in routes:
        path = str(route.get("effective_path") or "/")
        port = route.get("target_host_port")
        if not port:
            continue
        if route.get("publish_mode") == "server":
            continue
        shared_lines.extend(
            [
                f"location ^~ {path} {{",
                f"    rewrite ^{path}(.*)$ /$1 break;",
                f"    proxy_pass http://127.0.0.1:{port}/;",
                "    proxy_http_version 1.1;",
                "    proxy_set_header Host $host;",
                "    proxy_set_header X-Real-IP $remote_addr;",
                "    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
                "    proxy_set_header X-Forwarded-Proto $scheme;",
                f"    proxy_set_header X-Forwarded-Prefix {shared_route_base};",
                "    proxy_redirect off;",
            ]
        )
        if route.get("component_type") in {"frontend", "fullstack"}:
            shared_lines.extend(
                [
                    "    sub_filter_once off;",
                    "    sub_filter_types text/html text/css application/javascript;",
                    f"    sub_filter 'href=\"/' 'href=\"{shared_route_base}/';",
                    f"    sub_filter 'src=\"/' 'src=\"{shared_route_base}/';",
                ]
            )
        shared_lines.extend(["}", ""])

    if any(route.get("publish_mode") == "server" for route in routes):
        server_lines.extend(["server {", "    listen 80;", f"    server_name {domain};", ""])
        for route in routes:
            if route.get("publish_mode") != "server":
                continue
            path = str(route.get("effective_path") or "/")
            port = route.get("target_host_port")
            server_lines.extend(
                [
                    f"    location {path} {{",
                    f"        proxy_pass http://127.0.0.1:{port}/;",
                    "        proxy_http_version 1.1;",
                    "        proxy_set_header Host $host;",
                    "        proxy_set_header X-Real-IP $remote_addr;",
                    "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
                    "        proxy_set_header X-Forwarded-Proto $scheme;",
                    "    }",
                    "",
                ]
            )
        server_lines.append("}")

    return {
        "routes": routes,
        "shared_include_content": "\n".join(shared_lines).rstrip() + ("\n" if shared_lines else ""),
        "server_conf_content": "\n".join(server_lines).rstrip() + ("\n" if server_lines else ""),
        "shared_include_path": str(project_route_include_path(str(project.get("id", "")))),
        "server_conf_path": str(project_server_conf_path(str(project.get("id", "")))),
    }


def project_ensure_nginx_include() -> None:
    default_conf = Path("/etc/nginx/sites-available/default")
    include_line = "    include /etc/nginx/redvm-routes/*.conf;"
    if not default_conf.exists():
        return
    content = default_conf.read_text(encoding="utf-8", errors="replace")
    if include_line in content:
        return
    marker = "    location / {"
    if marker not in content:
        raise RuntimeError("Nao foi possivel localizar o bloco principal do Nginx para incluir as rotas dos projetos.")
    content = content.replace(marker, include_line + "\n\n" + marker, 1)
    default_conf.write_text(content, encoding="utf-8")


def project_health_check(report: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    services = report.get("deployment_plan", {}).get("services", [])
    for service in services:
        host_port = int(service.get("host_port", 0) or 0)
        if not host_port:
            continue
        path = str(service.get("health_path", "/") or "/")
        target_url = f"http://127.0.0.1:{host_port}{path}"
        success = False
        detail = ""
        for attempt in range(1, PROJECT_HEALTH_RETRIES + 1):
            try:
                request = urllib.request.Request(target_url, method="GET")
                with urllib.request.urlopen(request, timeout=10) as response:
                    status_code = int(response.status)
                    if 200 <= status_code < 400:
                        success = True
                        detail = f"HTTP {status_code} em {attempt} tentativa(s)."
                        break
                    detail = f"HTTP {status_code}"
            except Exception as exc:
                detail = str(exc)
            time.sleep(PROJECT_HEALTH_DELAY)
        checks.append(
            {
                "service_name": service.get("service_name"),
                "target_url": target_url,
                "success": success,
                "detail": detail,
            }
        )
    overall = all(item.get("success") for item in checks) if checks else True
    return {"success": overall, "checks": checks}


def project_compose_files_for_release(project_id: str, release_id: str, report: dict[str, Any]) -> dict[str, Path]:
    release_dir = project_release_dir(project_id, release_id)
    release_dir.mkdir(parents=True, exist_ok=True)
    bundle = report.get("bundle", {})
    for artifact in bundle.get("artifacts", []):
        written_to = str(artifact.get("written_to", "") or "")
        if not written_to:
            continue
        source = Path(written_to)
        target = release_dir / source.name if artifact.get("kind") != "dockerfile" else release_dir / "dockerfiles" / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    deploy_env = release_dir / ".deploy.env"
    deploy_env.write_text(
        "\n".join(
            [
                f"REDVM_RELEASE_ID={release_id}",
                f"COMPOSE_PROJECT_NAME=redvm_{project_id}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "release_dir": release_dir,
        "compose_file": release_dir / "docker-compose.generated.yml",
        "deploy_env": deploy_env,
        "nginx_file": release_dir / "nginx.generated.conf",
        "env_example_file": release_dir / ".env.example",
    }


def project_run_compose(compose_file: Path, deploy_env: Path, *args: str, check: bool = True, timeout: int = 1200) -> subprocess.CompletedProcess[str]:
    return run_command(
        [
            "docker",
            "compose",
            "--env-file",
            str(deploy_env),
            "-f",
            str(compose_file),
            *args,
        ],
        timeout=timeout,
        check=check,
    )


def project_publish_nginx(project: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    project_ensure_nginx_include()
    publish = project_build_nginx_publish_content(project, report)
    shared_include_path = project_route_include_path(str(project.get("id", "")))
    server_conf_path = project_server_conf_path(str(project.get("id", "")))

    previous_shared = shared_include_path.read_text(encoding="utf-8", errors="replace") if shared_include_path.exists() else None
    previous_server = server_conf_path.read_text(encoding="utf-8", errors="replace") if server_conf_path.exists() else None

    if publish["shared_include_content"].strip():
        shared_include_path.write_text(publish["shared_include_content"], encoding="utf-8")
    elif shared_include_path.exists():
        shared_include_path.unlink()

    if publish["server_conf_content"].strip():
        server_conf_path.write_text(publish["server_conf_content"], encoding="utf-8")
    elif server_conf_path.exists():
        server_conf_path.unlink()

    try:
        run_command(["nginx", "-t"], timeout=30)
        run_command(["systemctl", "reload", "nginx"], timeout=30)
    except Exception:
        if previous_shared is None:
            shared_include_path.unlink(missing_ok=True)
        else:
            shared_include_path.write_text(previous_shared, encoding="utf-8")
        if previous_server is None:
            server_conf_path.unlink(missing_ok=True)
        else:
            server_conf_path.write_text(previous_server, encoding="utf-8")
        run_command(["nginx", "-t"], timeout=30, check=False)
        run_command(["systemctl", "reload", "nginx"], timeout=30, check=False)
        raise

    return publish


def project_rollback_to_release(project_id: str, previous: dict[str, Any] | None) -> None:
    if previous is None:
        return
    release_dir = Path(str(previous.get("release_dir", "") or ""))
    compose_file = release_dir / "docker-compose.generated.yml"
    deploy_env = release_dir / ".deploy.env"
    if not compose_file.exists() or not deploy_env.exists():
        return
    project_run_compose(compose_file, deploy_env, "up", "-d", "--remove-orphans", check=False, timeout=1200)


def project_deploy(
    project_id: str,
    *,
    reason: str = "manual",
    include_ai: bool = False,
    model: str = "",
    checkout_ref: str = "",
) -> dict[str, Any]:
    project = project_find_record(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projeto nao encontrado.")

    project_clear_pending_fix(project_id)
    project_append_activity(project_id, "deploy", f"Deploy solicitado ({reason}).", level="info")
    project_set_job_state(project_id, "deploy", "analysis", "Validando repositorio antes do deploy.", progress=5)
    report = project_run_analysis(project_id, include_ai=include_ai, model=model, checkout_ref=checkout_ref)
    project = project_find_record(project_id) or project
    if report.get("status") == "blocked":
        detail = "Projeto bloqueado pela analise deterministica. Corrija os erros antes do deploy."
        pending_fix = project_prepare_pending_fix(project, report, stage="analysis", error_text=detail)
        if pending_fix:
            project_set_pending_fix(project_id, pending_fix)
        project_append_activity(project_id, "deploy", detail, level="error")
        project_set_job_state(project_id, "deploy", "blocked", detail, status="failed", progress=100, error=detail)
        raise HTTPException(status_code=400, detail=detail)
    deployment_id = uuid.uuid4().hex
    release_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    previous_success = project_latest_successful_deployment(project_id)
    deployment = {
        "id": deployment_id,
        "release_id": release_id,
        "reason": reason,
        "requested_at": utc_now_iso(),
        "status": "running",
        "detail": "Preparando release.",
        "release_dir": str(project_release_dir(project_id, release_id)),
    }
    project_append_deployment(project_id, deployment)

    files = project_compose_files_for_release(project_id, release_id, report)
    compose_file = files["compose_file"]
    deploy_env = files["deploy_env"]
    release_dir = files["release_dir"]

    try:
        project_set_job_state(project_id, "deploy", "compose", "Validando o Docker Compose gerado.", progress=20)
        project_append_activity(project_id, "deploy", "Validando o compose da release.", level="info")
        project_run_compose(compose_file, deploy_env, "config", "-q", timeout=180)
        project_update_deployment(project_id, deployment_id, detail="Docker Compose validado.")
        project_set_job_state(project_id, "deploy", "build", "Construindo imagens e subindo containers.", progress=45)
        project_append_activity(project_id, "deploy", "Subindo a release com Docker Compose.", level="info")
        project_run_compose(compose_file, deploy_env, "up", "-d", "--build", "--remove-orphans", timeout=1800)
        project_set_job_state(project_id, "deploy", "health", "Executando health checks da release.", progress=75)
        project_append_activity(project_id, "deploy", "Executando health checks da release.", level="info")
        health = project_health_check(report)
        if not health.get("success"):
            raise RuntimeError("Health check falhou: " + "; ".join(row.get("detail", "") for row in health.get("checks", [])))
        project_set_job_state(project_id, "deploy", "publish", "Publicando rotas no Nginx.", progress=88)
        project_append_activity(project_id, "deploy", "Publicando as rotas do projeto no Nginx.", level="info")
        publish = project_publish_nginx(project, report)
        report["published_routes"] = publish.get("routes", [])
        project_write_report(project_id, report)
        project_update_deployment(
            project_id,
            deployment_id,
            status="success",
            completed_at=utc_now_iso(),
            detail="Deploy concluido com health check e publicacao Nginx.",
            health=health,
            nginx_published=True,
            public_routes=publish.get("routes", []),
            release_dir=str(release_dir),
        )
        with PROJECTS_LOCK:
            registry = project_read_registry()
            projects = registry.get("projects", [])
            for index, row in enumerate(projects):
                if str(row.get("id", "")) != project_id:
                    continue
                updated = dict(row)
                updated["last_deployed_at"] = utc_now_iso()
                updated["last_deployment_status"] = "success"
                updated["current_release_id"] = release_id
                updated["updated_at"] = utc_now_iso()
                projects[index] = updated
                registry["projects"] = projects
                project_write_registry(registry)
                break
        project_clear_pending_fix(project_id)
        project_append_activity(project_id, "deploy", f"Deploy concluido com sucesso na release {release_id}.", level="success")
        project_set_job_state(project_id, "deploy", "done", f"Deploy concluido com sucesso na release {release_id}.", status="success", progress=100)
        whatsapp_dispatch_alert(
            "deploy_success",
            f"Deploy concluido: {project.get('name')}",
            (
                f"Release {release_id} implantada com sucesso.\n\n"
                f"Projeto: {project.get('name')}\n"
                f"Rotas: {', '.join(publish.get('routes', [])) or 'nenhuma'}"
            ),
            meta={"project_id": project_id, "release_id": release_id},
        )
        return {"deployment_id": deployment_id, "release_id": release_id, "health": health, "routes": publish.get("routes", [])}
    except Exception as exc:
        detail = project_exception_detail(exc)
        project_update_deployment(
            project_id,
            deployment_id,
            status="failed",
            completed_at=utc_now_iso(),
            detail=detail,
            release_dir=str(release_dir),
        )
        if previous_success is not None:
            project_append_activity(project_id, "rollback", "Tentando rollback para a ultima release valida.", level="warning")
            project_rollback_to_release(project_id, previous_success)
        else:
            project_run_compose(compose_file, deploy_env, "down", "--remove-orphans", check=False, timeout=600)
        compose_logs = project_compose_logs(compose_file, deploy_env)
        pending_fix = project_prepare_pending_fix(project, report, stage="deploy", error_text=detail, logs=compose_logs)
        if pending_fix:
            project_set_pending_fix(project_id, pending_fix)
        project_append_activity(project_id, "deploy", f"Falha no deploy da release {release_id}: {detail}", level="error")
        with PROJECTS_LOCK:
            registry = project_read_registry()
            projects = registry.get("projects", [])
            for index, row in enumerate(projects):
                if str(row.get("id", "")) != project_id:
                    continue
                updated = dict(row)
                updated["last_deployment_status"] = "failed"
                updated["updated_at"] = utc_now_iso()
                projects[index] = updated
                registry["projects"] = projects
                project_write_registry(registry)
                break
        project_set_job_state(project_id, "deploy", "failed", "O deploy falhou.", status="failed", progress=100, error=detail)
        whatsapp_dispatch_alert(
            "deploy_failed",
            f"Falha de deploy: {project.get('name')}",
            (
                f"Release {release_id} falhou.\n\n"
                f"Projeto: {project.get('name')}\n"
                f"Detalhe: {detail[:1600]}"
            ),
            meta={"project_id": project_id, "release_id": release_id},
        )
        raise HTTPException(status_code=500, detail=f"Falha no deploy: {detail}") from exc


def project_proxy_chat_once(model: str, messages: list[dict[str, Any]], *, temperature: float = 0.2, timeout: int = PROJECT_AI_TIMEOUT) -> dict[str, Any]:
    status_code, payload = proxy_request_json(
        "/api/chat",
        method="POST",
        payload={
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        },
        timeout=timeout,
    )
    if status_code != 200:
        detail = payload.get("error") if isinstance(payload, dict) else str(payload)
        raise HTTPException(status_code=503, detail=detail or "Falha ao consultar o proxy IA.")
    return payload if isinstance(payload, dict) else {}


def project_generate_ai_report(project: dict[str, Any], analysis: dict[str, Any], model: str = "") -> dict[str, Any]:
    proxy_info = proxy_snapshot()
    models = list(proxy_info.get("models", []))
    selected_model = model or (models[0] if models else "")
    if not selected_model:
        return {
            "status": "unavailable",
            "model": "",
            "generated_at": utc_now_iso(),
            "content": "Nenhum modelo disponivel no proxy para gerar a leitura por IA.",
        }

    context = {
        "project": {
            "name": project.get("name"),
            "repo_url": project.get("repo_url"),
            "branch": project.get("branch"),
            "default_domain": project.get("default_domain"),
            "default_base_path": project.get("default_base_path"),
        },
        "analysis": {
            "classification": analysis.get("classification"),
            "brief": analysis.get("brief"),
            "components": analysis.get("components"),
            "deployment_plan": analysis.get("deployment_plan"),
            "diagnostics": analysis.get("diagnostics"),
        },
    }
    payload = project_proxy_chat_once(
        selected_model,
        [
            {
                "role": "system",
                "content": (
                    "Voce e um arquiteto de plataforma encarregado de explicar projetos cadastrados numa VM de deploy. "
                    "Responda em portugues do Brasil, de forma objetiva e pragmatica. "
                    "Use apenas o contexto fornecido. "
                    "Estruture a resposta em markdown com as secoes: Do que se trata, O que faz, Como deve ser implantado, Riscos e Sinais de alerta."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(context, ensure_ascii=False),
            },
        ],
        timeout=PROJECT_AI_TIMEOUT,
    )
    content = ""
    if isinstance(payload.get("message"), dict):
        content = str(payload["message"].get("content", "") or "")
    if not content:
        content = str(payload.get("response", "") or "")
    return {
        "status": "ready" if content else "empty",
        "model": selected_model,
        "generated_at": utc_now_iso(),
        "content": content or "A IA nao retornou conteudo util para este projeto.",
    }


def project_run_analysis(
    project_id: str,
    *,
    include_ai: bool = False,
    model: str = "",
    checkout_ref: str = "",
) -> dict[str, Any]:
    project = project_find_record(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projeto nao encontrado.")

    previous_report = project_read_report(project_id)
    report: dict[str, Any] = {}
    project_clear_pending_fix(project_id)
    project_append_activity(project_id, "analysis", "Analise iniciada.", level="info")
    project_set_job_state(project_id, "analysis", "sync", "Preparando repositorio para analise.", progress=5)

    try:
        sync_info = project_sync_repository(project_id, checkout_ref=checkout_ref)
        project = project_find_record(project_id) or project
        project_set_job_state(project_id, "analysis", "scan", "Escaneando estrutura do repositorio.", progress=35)
        report = analyze_repo(
            project.get("repo_path", ""),
            project_name=str(project.get("name", "") or ""),
            project_id=project_id,
            port_base=int(project.get("port_base", PROJECT_PORT_BASE) or PROJECT_PORT_BASE),
            default_domain=str(project.get("default_domain", "") or ""),
            default_base_path=str(project.get("default_base_path", "/") or "/"),
            vm_context=project_vm_context(
                allowed_ports=list(
                    range(
                        int(project.get("port_base", PROJECT_PORT_BASE) or PROJECT_PORT_BASE),
                        int(project.get("port_base", PROJECT_PORT_BASE) or PROJECT_PORT_BASE) + max(PROJECT_PORT_STEP, 1),
                    )
                )
            ),
        )
        report["project_id"] = project_id
        report["project_name"] = project.get("name", "")
        report["webhook_path"] = project_webhook_path(project_id)
        report["repo_url"] = project.get("repo_url", "")
        report["branch"] = project.get("branch", "main")
        report["deliveries"] = list(project.get("deliveries", []))[-20:]
        report["ai_report"] = previous_report.get("ai_report", {})
        report["analyzer"] = {"name": "deterministic-project-analyzer", "version": PROJECT_ANALYZER_VERSION}
        report["source_sync"] = sync_info
        report = project_apply_overrides_to_report(project, report)

        if include_ai:
            project_set_job_state(project_id, "analysis", "ai", "Gerando leitura assistida por IA.", progress=70)
            try:
                report["ai_report"] = project_generate_ai_report(project, report, model=model)
            except HTTPException as exc:
                report["ai_report"] = {
                    "status": "error",
                    "model": model,
                    "generated_at": utc_now_iso(),
                    "content": f"Falha ao gerar leitura por IA: {exc.detail}",
                }

        project_set_job_state(project_id, "analysis", "bundle", "Gerando bundle compativel para deploy.", progress=88)
        project_public_base = ""
        if project.get("default_domain"):
            project_public_base = f"http://{project.get('default_domain')}"
        bundle = generate_deploy_bundle(
            {
                **project,
                "webhook": {
                    "path": project_webhook_path(project_id),
                    "url": f"{project_public_base}{project_webhook_path(project_id)}" if project_public_base else project_webhook_path(project_id),
                    "secret": project.get("webhook_secret", ""),
                },
            },
            report,
            bundle_root=str(project_bundle_dir(project_id)),
            public_base_url=project_public_base,
        )
        report["bundle"] = project_write_bundle_files(project_id, bundle)

        project_write_report(project_id, report)
        project_update_record(
            project_id,
            lambda current: current.update(
                {
                    "last_analyzed_at": report.get("generated_at", utc_now_iso()),
                    "last_status": report.get("status", "unknown"),
                }
            ),
        )
        project_append_activity(
            project_id,
            "analysis",
            f"Analise concluida com status {report.get('status', 'unknown')}.",
            level="success" if report.get("status") == "ready" else "warning",
        )
        project_set_job_state(
            project_id,
            "analysis",
            "done",
            f"Analise concluida com status {report.get('status', 'unknown')}.",
            status="success",
            progress=100,
        )
        if str(report.get("status", "")).strip() == "blocked":
            whatsapp_dispatch_alert(
                "project_blocked",
                f"Projeto bloqueado: {project.get('name')}",
                (
                    f"O projeto {project.get('name')} foi analisado e ficou bloqueado para deploy.\n\n"
                    f"Repositorio: {project.get('repo_url') or project.get('repo_path')}\n"
                    f"Resumo: {report.get('brief') or 'Analise bloqueada.'}"
                ),
                meta={"project_id": project_id},
            )
        return report
    except Exception as exc:
        detail = project_exception_detail(exc)
        effective_report = report if report else previous_report
        if effective_report:
            pending_fix = project_prepare_pending_fix(project, effective_report, stage="analysis", error_text=detail)
            if pending_fix:
                project_set_pending_fix(project_id, pending_fix)
        project_append_activity(project_id, "analysis", f"Falha na analise: {detail}", level="error")
        project_set_job_state(project_id, "analysis", "failed", "A analise falhou.", status="failed", progress=100, error=detail)
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=f"Falha na analise do projeto: {detail}") from exc


def verify_github_signature(secret: str, body: bytes, signature_header: str) -> bool:
    if not secret or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def project_process_github_webhook(project_id: str, delivery_id: str, event_name: str, payload: dict[str, Any]) -> None:
    project = project_find_record(project_id)
    if project is None:
        return

    branch = str(project.get("branch", "main") or "main")
    received_ref = str(payload.get("ref", "") or "")
    expected_ref = f"refs/heads/{branch}"
    repo_name = str(payload.get("repository", {}).get("full_name", "") or "")
    repo_url = str(payload.get("repository", {}).get("html_url", "") or "")
    head_commit = str(payload.get("after", "") or "").strip()
    event_status = "ignored"
    detail = "Evento nao processado."

    if event_name != "push":
        detail = f"Evento {event_name} ignorado; o gateway atual reage apenas a push."
    elif received_ref != expected_ref:
        detail = f"Push recebido para {received_ref or 'ref desconhecida'}; branch monitorada = {expected_ref}."
    else:
        try:
            project_append_activity(project_id, "webhook", f"Push recebido de {repo_name or 'repositorio'} em {received_ref}.", level="info")
            report = project_run_analysis(project_id, include_ai=False, checkout_ref=head_commit)
            detail = f"Analise atualizada com status {report.get('status', 'unknown')}."
            if bool(project.get("auto_deploy", True)) and report.get("status") != "blocked":
                deploy_result = project_deploy(project_id, reason=f"github:{delivery_id}", checkout_ref=head_commit)
                detail += f" Deploy release {deploy_result.get('release_id')} concluido."
            event_status = "processed"
        except Exception as exc:
            event_status = "failed"
            detail = str(getattr(exc, "detail", "") or exc)

    project_update_delivery(
        project_id,
        delivery_id,
        completed_at=utc_now_iso(),
        status=event_status,
        detail=detail,
        repository=repo_name,
        repository_url=repo_url,
        ref=received_ref,
    )


def proxy_register_chat_job(connection_id: str, job: ProxyChatJob) -> None:
    with app.state.proxy_chat_lock:
        app.state.proxy_chat_jobs[connection_id] = job


def proxy_get_chat_job(connection_id: str) -> ProxyChatJob | None:
    with app.state.proxy_chat_lock:
        return app.state.proxy_chat_jobs.get(connection_id)


def proxy_clear_chat_job(connection_id: str, request_id: str | None = None) -> None:
    with app.state.proxy_chat_lock:
        current = app.state.proxy_chat_jobs.get(connection_id)
        if current is None:
            return
        if request_id and current.request_id != request_id:
            return
        app.state.proxy_chat_jobs.pop(connection_id, None)


def proxy_cancel_chat_job(connection_id: str) -> ProxyChatJob | None:
    job = proxy_get_chat_job(connection_id)
    if job is None:
        return None
    job.cancel()
    return job


def proxy_send_ws_message(connection_id: str, message: dict[str, Any]) -> None:
    future = asyncio.run_coroutine_threadsafe(app.state.hub.send(connection_id, message), app.state.loop)
    future.result(timeout=10)


def is_stream_timeout_error(exc: Exception) -> bool:
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return True
    return "timed out" in str(exc).lower()


def chat_stream_worker(
    event_prefix: str,
    connection_id: str,
    job: ProxyChatJob,
    model: str,
    messages: list[dict[str, Any]],
    options: dict[str, Any] | None = None,
) -> None:
    payload_data: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
    }
    if options:
        payload_data["options"] = options
    request = urllib.request.Request(
        f"{PROXY_URL}/api/chat",
        data=json.dumps(payload_data).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    collected: list[str] = []
    was_cancelled = False
    stream_timeout_seconds = 1.0

    try:
        proxy_send_ws_message(
            connection_id,
            {"type": f"{event_prefix}.started", "payload": {"model": model, "request_id": job.request_id}},
        )

        with urllib.request.urlopen(request, timeout=180) as response:
            job.attach_response(response)
            raw_socket = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
            if raw_socket is not None:
                try:
                    raw_socket.settimeout(stream_timeout_seconds)
                except Exception:
                    raw_socket = None

            while True:
                if job.cancel_event.is_set():
                    was_cancelled = True
                    break

                try:
                    raw_line = response.readline()
                except Exception as exc:
                    if is_stream_timeout_error(exc):
                        continue
                    if job.cancel_event.is_set():
                        was_cancelled = True
                        break
                    raise

                if not raw_line:
                    break

                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if payload.get("error"):
                    raise RuntimeError(str(payload["error"]))

                message = payload.get("message", {}) or {}
                chunk = str(message.get("content", ""))
                if chunk:
                    collected.append(chunk)
                    proxy_send_ws_message(
                        connection_id,
                        {
                            "type": f"{event_prefix}.chunk",
                            "payload": {
                                "model": model,
                                "request_id": job.request_id,
                                "chunk": chunk,
                            },
                        },
                    )

                if payload.get("done"):
                    break

            if job.cancel_event.is_set():
                was_cancelled = True

        if was_cancelled:
            proxy_send_ws_message(
                connection_id,
                {
                    "type": f"{event_prefix}.stopped",
                    "payload": {
                        "model": model,
                        "request_id": job.request_id,
                        "content": "".join(collected),
                    },
                },
            )
        else:
            proxy_send_ws_message(
                connection_id,
                {
                    "type": f"{event_prefix}.done",
                    "payload": {
                        "model": model,
                        "request_id": job.request_id,
                        "content": "".join(collected),
                    },
                },
            )
    except urllib.error.HTTPError as exc:
        if job.cancel_event.is_set():
            proxy_send_ws_message(
                connection_id,
                {
                    "type": f"{event_prefix}.stopped",
                    "payload": {
                        "model": model,
                        "request_id": job.request_id,
                        "content": "".join(collected),
                    },
                },
            )
            return
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body) if body else {}
            detail = parsed.get("error") or parsed.get("detail") or body
        except json.JSONDecodeError:
            detail = body or str(exc)
        proxy_send_ws_message(
            connection_id,
            {
                "type": f"{event_prefix}.error",
                "payload": {
                    "model": model,
                    "request_id": job.request_id,
                    "error": detail or str(exc),
                    "status_code": exc.code,
                },
            },
        )
    except Exception as exc:
        if job.cancel_event.is_set():
            proxy_send_ws_message(
                connection_id,
                {
                    "type": f"{event_prefix}.stopped",
                    "payload": {
                        "model": model,
                        "request_id": job.request_id,
                        "content": "".join(collected),
                    },
                },
            )
            return
        proxy_send_ws_message(
            connection_id,
            {
                "type": f"{event_prefix}.error",
                "payload": {
                    "model": model,
                    "request_id": job.request_id,
                    "error": str(exc),
                    "status_code": 0,
                },
            },
        )
    finally:
        job.finish()


def proxy_chat_stream_worker(
    connection_id: str,
    job: ProxyChatJob,
    model: str,
    messages: list[dict[str, Any]],
    options: dict[str, Any] | None = None,
) -> None:
    try:
        chat_stream_worker("proxy.chat", connection_id, job, model, messages, options)
    finally:
        proxy_clear_chat_job(connection_id, job.request_id)


def vm_register_assistant_job(connection_id: str, job: ProxyChatJob) -> None:
    with app.state.vm_assistant_lock:
        app.state.vm_assistant_jobs[connection_id] = job


def vm_get_assistant_job(connection_id: str) -> ProxyChatJob | None:
    with app.state.vm_assistant_lock:
        return app.state.vm_assistant_jobs.get(connection_id)


def vm_clear_assistant_job(connection_id: str, request_id: str | None = None) -> None:
    with app.state.vm_assistant_lock:
        current = app.state.vm_assistant_jobs.get(connection_id)
        if current is None:
            return
        if request_id and current.request_id != request_id:
            return
        app.state.vm_assistant_jobs.pop(connection_id, None)


def vm_cancel_assistant_job(connection_id: str) -> ProxyChatJob | None:
    job = vm_get_assistant_job(connection_id)
    if job is None:
        return None
    job.cancel()
    return job


def system_summary() -> dict[str, Any]:
    uname = platform.uname()
    boot_time = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc).isoformat()
    try:
        load = os.getloadavg()
    except OSError:
        load = (0.0, 0.0, 0.0)

    return {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "system": uname.system,
        "release": uname.release,
        "version": uname.version,
        "machine": uname.machine,
        "boot_time": boot_time,
        "timestamp": utc_now_iso(),
        "load_avg": {"one": load[0], "five": load[1], "fifteen": load[2]},
    }


def telemetry_snapshot() -> dict[str, Any]:
    cpu_percent = psutil.cpu_percent(interval=None)
    cpu_freq = psutil.cpu_freq()
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()

    return {
        "timestamp": utc_now_iso(),
        "cpu": {
            "percent": cpu_percent,
            "count": psutil.cpu_count(),
            "freq_current": cpu_freq.current if cpu_freq else None,
        },
        "memory": {
            "total": memory.total,
            "used": memory.used,
            "available": memory.available,
            "percent": memory.percent,
        },
        "swap": {
            "total": swap.total,
            "used": swap.used,
            "percent": swap.percent,
        },
        "disk": {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": disk.percent,
        },
        "network": {
            "bytes_sent": net.bytes_sent,
            "bytes_recv": net.bytes_recv,
            "packets_sent": net.packets_sent,
            "packets_recv": net.packets_recv,
        },
        "uptime_seconds": max(time.time() - psutil.boot_time(), 0),
    }


def process_snapshot(limit: int = 24) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for proc in psutil.process_iter(
        ["pid", "name", "username", "status", "cpu_percent", "memory_percent", "cmdline"]
    ):
        try:
            info = proc.info
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        rows.append(
            {
                "pid": info["pid"],
                "name": info.get("name") or "unknown",
                "user": info.get("username") or "unknown",
                "status": info.get("status") or "unknown",
                "cpu_percent": info.get("cpu_percent") or 0.0,
                "memory_percent": round(info.get("memory_percent") or 0.0, 2),
                "command": " ".join(info.get("cmdline") or []),
            }
        )

    rows.sort(key=lambda row: (row["cpu_percent"], row["memory_percent"]), reverse=True)
    return rows[:limit]


def firewall_snapshot() -> dict[str, Any]:
    try:
        result = run_command(["ufw", "status", "numbered"], timeout=15)
        lines = [line.rstrip() for line in result.stdout.splitlines() if line.strip()]
        return {"enabled": True, "raw": lines}
    except Exception as exc:
        return {"enabled": False, "raw": [str(exc)]}


def parse_service_rows() -> list[dict[str, Any]]:
    units_result = run_command(
        ["systemctl", "list-units", "--type=service", "--all", "--plain", "--no-pager", "--no-legend"],
        timeout=25,
    )
    unit_file_result = run_command(
        ["systemctl", "list-unit-files", "--type=service", "--plain", "--no-pager", "--no-legend"],
        timeout=25,
    )

    states: dict[str, dict[str, str]] = {}
    for line in unit_file_result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            states[parts[0]] = {
                "unit_file_state": parts[1],
                "vendor_preset": parts[2] if len(parts) > 2 else "",
            }

    rows: list[dict[str, Any]] = []
    for line in units_result.stdout.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        unit, load, active, sub, description = parts
        extra = states.get(unit, {"unit_file_state": "unknown", "vendor_preset": ""})
        rows.append(
            {
                "unit": unit,
                "load": load,
                "active": active,
                "sub": sub,
                "description": description,
                "unit_file_state": extra["unit_file_state"],
                "vendor_preset": extra["vendor_preset"],
            }
        )

    rows.sort(key=lambda row: (row["active"] != "active", row["unit"]))
    return rows


def docker_client() -> docker.DockerClient | None:
    try:
        return docker.from_env()
    except Exception:
        return None


def docker_snapshot() -> dict[str, Any]:
    client = docker_client()
    if not client:
        return {"available": False, "containers": [], "images": []}

    containers: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []

    try:
        for container in client.containers.list(all=True):
            stats_payload: dict[str, Any] | None = None
            if container.status == "running":
                try:
                    stats = container.stats(stream=False)
                    cpu_delta = (
                        stats["cpu_stats"]["cpu_usage"]["total_usage"]
                        - stats["precpu_stats"]["cpu_usage"]["total_usage"]
                    )
                    system_delta = (
                        stats["cpu_stats"].get("system_cpu_usage", 0)
                        - stats["precpu_stats"].get("system_cpu_usage", 0)
                    )
                    cpu_percent = 0.0
                    if system_delta > 0:
                        cores = len(stats["cpu_stats"].get("cpu_usage", {}).get("percpu_usage", []) or [1])
                        cpu_percent = (cpu_delta / system_delta) * cores * 100.0
                    memory_usage = stats["memory_stats"].get("usage", 0)
                    memory_limit = stats["memory_stats"].get("limit", 0)
                    stats_payload = {
                        "cpu_percent": round(cpu_percent, 2),
                        "memory_usage": memory_usage,
                        "memory_limit": memory_limit,
                        "memory_percent": round(
                            ((memory_usage / memory_limit) * 100.0) if memory_limit else 0.0,
                            2,
                        ),
                    }
                except Exception:
                    stats_payload = None

            containers.append(
                {
                    "id": container.id[:12],
                    "name": container.name,
                    "status": container.status,
                    "image": container.image.tags[0] if container.image.tags else container.image.short_id,
                    "created": container.attrs.get("Created"),
                    "ports": container.attrs.get("NetworkSettings", {}).get("Ports", {}),
                    "stats": stats_payload,
                }
            )
    except Exception:
        containers = []

    try:
        for image in client.images.list():
            images.append(
                {
                    "id": image.short_id,
                    "tags": image.tags,
                    "created": image.attrs.get("Created"),
                    "size": image.attrs.get("Size", 0),
                }
            )
    except Exception:
        images = []

    images.sort(key=lambda row: row["created"] or "", reverse=True)

    return {"available": True, "containers": containers, "images": images}


def vm_assistant_context_snapshot() -> dict[str, Any]:
    return {
        "system": system_summary(),
        "telemetry": telemetry_snapshot(),
        "services": parse_service_rows(),
        "docker": docker_snapshot(),
        "processes": process_snapshot(limit=12),
        "firewall": firewall_snapshot(),
        "proxy": proxy_snapshot(),
        "journal": list(app.state.journal_lines)[-16:],
        "proxy_logs": list(app.state.proxy_log_lines)[-16:],
    }


def vm_assistant_context_text(snapshot: dict[str, Any]) -> str:
    system = snapshot.get("system", {})
    telemetry = snapshot.get("telemetry", {})
    services = snapshot.get("services", [])
    docker = snapshot.get("docker", {})
    processes = snapshot.get("processes", [])
    firewall = snapshot.get("firewall", {})
    proxy = snapshot.get("proxy", {})

    important_units = {
        "nginx.service",
        "docker.service",
        "ssh.service",
        "red-dashboard.service",
        "red-ollama-proxy.service",
    }
    service_lines = [
        f"- {row.get('unit')}: {row.get('active')}/{row.get('sub')} ({row.get('description')})"
        for row in services
        if row.get("unit") in important_units
    ]
    failed_services = [row for row in services if row.get("active") == "failed"][:8]
    if failed_services:
        service_lines.append("Falhos:")
        service_lines.extend(
            f"- {row.get('unit')}: {row.get('description')}" for row in failed_services
        )

    running_containers = [row for row in docker.get("containers", []) if row.get("status") == "running"]
    container_lines = [
        f"- {row.get('name')} ({row.get('image')}) status={row.get('status')}"
        for row in docker.get("containers", [])[:10]
    ]

    process_lines = [
        f"- PID {row.get('pid')} {row.get('name')} cpu={float(row.get('cpu_percent', 0) or 0):.1f}% mem={float(row.get('memory_percent', 0) or 0):.1f}%"
        for row in processes[:10]
    ]

    firewall_lines = [f"- {line}" for line in (firewall.get("raw") or [])[:12]]
    journal_lines = [f"- {line}" for line in snapshot.get("journal", []) if line][:12]
    proxy_log_lines = [
        f"- {row.get('timestamp', '')} {row.get('level', '')} {row.get('message', '')}".strip()
        for row in snapshot.get("proxy_logs", [])
        if isinstance(row, dict)
    ][:12]

    return "\n".join(
        [
            "CONTEXTO OPERACIONAL ATUAL DA VM",
            "",
            "Sistema:",
            f"- Host: {system.get('hostname', 'n/d')}",
            f"- Kernel: {system.get('release', 'n/d')}",
            f"- Arquitetura: {system.get('machine', 'n/d')}",
            f"- Load avg: {system.get('load_avg', {}).get('one', 0):.2f} / {system.get('load_avg', {}).get('five', 0):.2f} / {system.get('load_avg', {}).get('fifteen', 0):.2f}",
            "",
            "Recursos:",
            f"- CPU: {float(telemetry.get('cpu', {}).get('percent', 0) or 0):.1f}% em {telemetry.get('cpu', {}).get('count', 0)} cores",
            f"- Memória: {float(telemetry.get('memory', {}).get('percent', 0) or 0):.1f}% usada; disponível={int(telemetry.get('memory', {}).get('available', 0) or 0)} bytes",
            f"- Disco: {float(telemetry.get('disk', {}).get('percent', 0) or 0):.1f}% usado; livre={int(telemetry.get('disk', {}).get('free', 0) or 0)} bytes",
            f"- Rede: recv={int(telemetry.get('network', {}).get('bytes_recv', 0) or 0)} bytes send={int(telemetry.get('network', {}).get('bytes_sent', 0) or 0)} bytes",
            "",
            "Serviços importantes:",
            *(service_lines or ["- Nenhum serviço importante encontrado."]),
            "",
            "Docker:",
            f"- Disponível: {docker.get('available', False)}",
            f"- Containers totais: {len(docker.get('containers', []))}",
            f"- Containers em execução: {len(running_containers)}",
            f"- Imagens: {len(docker.get('images', []))}",
            *(container_lines or ["- Nenhum container listado."]),
            "",
            "Processos quentes:",
            *(process_lines or ["- Nenhum processo listado."]),
            "",
            "Firewall:",
            *(firewall_lines or ["- Nenhuma regra disponível."]),
            "",
            "Proxy IA:",
            f"- Serviço: {proxy.get('service', {}).get('active', 'unknown')}/{proxy.get('service', {}).get('sub', 'unknown')}",
            f"- Reachable: {proxy.get('reachable', False)}",
            f"- Keys ativas: {proxy.get('summary', {}).get('active', 0)}",
            f"- Requests totais: {proxy.get('summary', {}).get('total_requests', 0)}",
            f"- Modelos detectados: {len(proxy.get('models', []))}",
            "",
            "Journal recente:",
            *(journal_lines or ["- Sem linhas recentes."]),
            "",
            "Logs recentes do proxy:",
            *(proxy_log_lines or ["- Sem logs recentes do proxy."]),
            "",
            "CAPACIDADES OPERACIONAIS DO PAINEL",
            "- O operador pode abrir terminal, reiniciar serviços, gerenciar Docker, editar arquivos, mexer no firewall e administrar o proxy IA.",
            "- Não assuma que ações já foram executadas; sugira com clareza o próximo passo mais seguro.",
        ]
    )


def vm_assistant_stream_worker(
    connection_id: str,
    job: ProxyChatJob,
    model: str,
    history: list[dict[str, Any]],
    prompt: str,
) -> None:
    try:
        context = vm_assistant_context_text(vm_assistant_context_snapshot())
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": f"{VM_ASSISTANT_SYSTEM_PROMPT}\n\n{context}",
            }
        ]
        for item in history:
            role = str(item.get("role", "")).strip()
            content = str(item.get("content", "")).strip()
            if role not in {"user", "assistant"} or not content:
                continue
            messages.append({"role": role, "content": content})
        if prompt.strip():
            messages.append({"role": "user", "content": prompt.strip()})
        chat_stream_worker("vm.assistant", connection_id, job, model, messages)
    finally:
        vm_clear_assistant_job(connection_id, job.request_id)


class ConnectionHub:
    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> str:
        await websocket.accept()
        connection_id = uuid.uuid4().hex
        async with self._lock:
            self._connections[connection_id] = websocket
        return connection_id

    async def disconnect(self, connection_id: str) -> None:
        async with self._lock:
            self._connections.pop(connection_id, None)

    async def send(self, connection_id: str, message: dict[str, Any]) -> None:
        async with self._lock:
            websocket = self._connections.get(connection_id)
        if websocket is None:
            return
        await websocket.send_text(json.dumps(message))

    async def broadcast(self, message: dict[str, Any]) -> None:
        async with self._lock:
            targets = list(self._connections.items())
        dead: list[str] = []
        payload = json.dumps(message)
        for connection_id, websocket in targets:
            try:
                await websocket.send_text(payload)
            except Exception:
                dead.append(connection_id)

        if dead:
            async with self._lock:
                for connection_id in dead:
                    self._connections.pop(connection_id, None)


class ProxyChatJob:
    def __init__(self, request_id: str) -> None:
        self.request_id = request_id
        self.cancel_event = threading.Event()
        self.finished_event = threading.Event()
        self._response: Any | None = None
        self._lock = threading.Lock()

    def attach_response(self, response: Any) -> None:
        with self._lock:
            self._response = response

    def clear_response(self) -> None:
        with self._lock:
            self._response = None

    def cancel(self) -> None:
        self.cancel_event.set()
        with self._lock:
            response = self._response
        if response is not None:
            try:
                response.close()
            except Exception:
                pass

    def finish(self) -> None:
        self.clear_response()
        self.finished_event.set()


class TerminalSession:
    def __init__(self, connection_id: str, hub: ConnectionHub, loop: asyncio.AbstractEventLoop) -> None:
        self.connection_id = connection_id
        self.hub = hub
        self.loop = loop
        self.session_id = uuid.uuid4().hex
        self.master_fd: int | None = None
        self.slave_fd: int | None = None
        self.process: subprocess.Popen[bytes] | None = None
        self.reader_thread: threading.Thread | None = None
        self.alive = False

    def start(self) -> str:
        if self.alive:
            return self.session_id
        if pty is None:
            raise RuntimeError("Terminal interativo indisponivel neste sistema.")

        self.master_fd, self.slave_fd = pty.openpty()
        env = os.environ.copy()
        env.update(
            {
                "TERM": "xterm-256color",
                "HOME": TERMINAL_HOME,
                "SHELL": TERMINAL_SHELL,
                "LANG": "C.UTF-8",
            }
        )
        self.process = subprocess.Popen(
            [TERMINAL_SHELL, "-l"],
            stdin=self.slave_fd,
            stdout=self.slave_fd,
            stderr=self.slave_fd,
            cwd=TERMINAL_HOME,
            env=env,
            close_fds=True,
            start_new_session=True,
        )
        self.resize(32, 120)
        self.alive = True
        self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.reader_thread.start()
        return self.session_id

    def _reader_loop(self) -> None:
        assert self.master_fd is not None
        while self.alive and self.process is not None:
            try:
                chunk = os.read(self.master_fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            message = {
                "type": "terminal.output",
                "payload": {
                    "session_id": self.session_id,
                    "chunk": chunk.decode("utf-8", errors="replace"),
                },
            }
            future = asyncio.run_coroutine_threadsafe(
                self.hub.send(self.connection_id, message),
                self.loop,
            )
            try:
                future.result(timeout=5)
            except Exception:
                break

        self.alive = False
        if self.process is not None and self.process.poll() is None:
            try:
                self.process.terminate()
            except OSError:
                pass

    def write(self, data: str) -> None:
        if self.master_fd is None or not self.alive:
            return
        os.write(self.master_fd, data.encode("utf-8", errors="replace"))

    def resize(self, rows: int, cols: int) -> None:
        if self.master_fd is None or termios is None:
            return
        packed = struct.pack("HHHH", rows, cols, 0, 0)
        termios_result = fcntl_ioctl(self.master_fd, termios.TIOCSWINSZ, packed)
        if termios_result is None:
            return

    def close(self) -> None:
        self.alive = False
        if self.process is not None and self.process.poll() is None:
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            except OSError:
                try:
                    self.process.terminate()
                except OSError:
                    pass
        for fd in (self.master_fd, self.slave_fd):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
        self.master_fd = None
        self.slave_fd = None


def fcntl_ioctl(fd: int, op: int, packed: bytes) -> bytes | None:
    try:
        import fcntl

        return fcntl.ioctl(fd, op, packed)
    except Exception:
        return None


app = FastAPI(title=APP_TITLE)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app.state.hub = ConnectionHub()
app.state.terminals = {}
app.state.proxy_chat_jobs = {}
app.state.proxy_chat_lock = threading.Lock()
app.state.vm_assistant_jobs = {}
app.state.vm_assistant_lock = threading.Lock()
app.state.journal_lines = deque(maxlen=400)
app.state.proxy_log_lines = deque(maxlen=400)
app.state.whatsapp_log_lines = deque(maxlen=400)
app.state.loop = None


async def emit_snapshot(include_heavy: bool = False) -> None:
    payload: dict[str, Any] = {
        "system": system_summary(),
        "telemetry": telemetry_snapshot(),
    }
    if include_heavy:
        payload["services"] = await asyncio.to_thread(parse_service_rows)
        payload["docker"] = await asyncio.to_thread(docker_snapshot)
        payload["processes"] = await asyncio.to_thread(process_snapshot)
        payload["firewall"] = await asyncio.to_thread(firewall_snapshot)
        payload["proxy"] = await asyncio.to_thread(proxy_snapshot_safe)
        payload["projects"] = await asyncio.to_thread(project_present_all, None)
        payload["whatsapp"] = await asyncio.to_thread(whatsapp_snapshot, None)
    await app.state.hub.broadcast({"type": "snapshot", "payload": payload})


async def snapshot_loop() -> None:
    tick = 0
    psutil.cpu_percent(interval=None)
    while True:
        include_heavy = tick % 5 == 0
        try:
            await emit_snapshot(include_heavy=include_heavy)
            if tick % 30 == 0:
                await asyncio.to_thread(whatsapp_monitor_vm_health)
        except Exception:
            pass
        tick += 1
        await asyncio.sleep(1)


async def journal_loop() -> None:
    process = await asyncio.create_subprocess_exec(
        "journalctl",
        "-n",
        "120",
        "-f",
        "-o",
        "short-iso",
        "--no-pager",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    assert process.stdout is not None
    while True:
        line = await process.stdout.readline()
        if not line:
            await asyncio.sleep(0.5)
            continue
        text = line.decode("utf-8", errors="replace").rstrip()
        app.state.journal_lines.append(text)
        await app.state.hub.broadcast(
            {"type": "journal.append", "payload": {"lines": [text]}}
        )


async def proxy_log_loop() -> None:
    position = 0
    last_inode: int | None = None
    while True:
        try:
            if not PROXY_LOG_FILE.exists():
                position = 0
                last_inode = None
                await asyncio.sleep(1)
                continue

            stat = PROXY_LOG_FILE.stat()
            inode = getattr(stat, "st_ino", None)
            if last_inode != inode or stat.st_size < position:
                position = 0
                last_inode = inode

            if stat.st_size == position:
                await asyncio.sleep(1)
                continue

            with PROXY_LOG_FILE.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(position)
                lines = handle.readlines()
                position = handle.tell()

            entries = [proxy_parse_log_line(line) for line in lines]
            entries = [entry for entry in entries if entry]
            if entries:
                for entry in entries:
                    app.state.proxy_log_lines.append(entry)
                await app.state.hub.broadcast(
                    {"type": "proxy.log.append", "payload": {"lines": entries}}
                )
        except Exception:
            await asyncio.sleep(1)
            continue

        await asyncio.sleep(1)


@app.on_event("startup")
async def on_startup() -> None:
    app.state.loop = asyncio.get_running_loop()
    asyncio.create_task(snapshot_loop())
    asyncio.create_task(journal_loop())
    for entry in proxy_log_tail(200):
        app.state.proxy_log_lines.append(entry)
    for entry in whatsapp_log_tail(200):
        app.state.whatsapp_log_lines.append(entry)
    asyncio.create_task(proxy_log_loop())


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    authenticated = is_authenticated_token(request.cookies.get(COOKIE_NAME))
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "app_title": APP_TITLE,
            "authenticated": authenticated,
        },
    )


@app.post("/login")
async def login(request: Request) -> JSONResponse:
    data = await request.json()
    password = str(data.get("password", ""))
    if password != DASHBOARD_PASSWORD:
        raise HTTPException(status_code=401, detail="Senha inválida")

    response = JSONResponse({"success": True})
    response.set_cookie(
        COOKIE_NAME,
        make_auth_token(),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )
    return response


@app.post("/logout")
async def logout() -> RedirectResponse:
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


@app.get("/api/bootstrap")
async def api_bootstrap(request: Request) -> JSONResponse:
    ensure_authenticated(request)
    projects_payload = project_present_all(request)
    payload = {
        "system": system_summary(),
        "telemetry": telemetry_snapshot(),
        "services": await asyncio.to_thread(parse_service_rows),
        "docker": await asyncio.to_thread(docker_snapshot),
        "processes": await asyncio.to_thread(process_snapshot),
        "firewall": await asyncio.to_thread(firewall_snapshot),
        "proxy": await asyncio.to_thread(proxy_snapshot_safe),
        "journal": list(app.state.journal_lines),
        "proxy_logs": list(app.state.proxy_log_lines),
        "projects": projects_payload,
        "whatsapp": await asyncio.to_thread(whatsapp_snapshot, request),
        "shortcuts": [
            "/",
            "/etc",
            "/opt",
            "/root",
            "/usr/local",
            "/var/log",
            "/var/www",
        ],
    }
    return JSONResponse(payload)


@app.get("/api/files")
async def api_files(request: Request, path: str | None = None) -> JSONResponse:
    ensure_authenticated(request)
    return JSONResponse(list_directory(path))


@app.get("/api/file")
async def api_file(request: Request, path: str) -> JSONResponse:
    ensure_authenticated(request)
    return JSONResponse(read_text_file(path))


@app.post("/api/file")
async def api_save_file(request: Request) -> JSONResponse:
    ensure_authenticated(request)
    payload = await request.json()
    path = require_json_body(payload, "path")
    content = str(payload.get("content", ""))
    return JSONResponse(save_text_file(path, content))


@app.get("/api/docker/container/{container_name}/logs")
async def api_container_logs(request: Request, container_name: str, tail: int = 200) -> JSONResponse:
    ensure_authenticated(request)
    client = docker_client()
    if not client:
        raise HTTPException(status_code=503, detail="Docker indisponível")

    try:
        container = client.containers.get(container_name)
        logs = container.logs(tail=max(10, min(tail, 1000)), timestamps=True).decode(
            "utf-8",
            errors="replace",
        )
        return JSONResponse({"logs": logs.splitlines()})
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/service/{unit}/{action}")
async def api_service_action(request: Request, unit: str, action: str) -> JSONResponse:
    ensure_authenticated(request)
    if action not in {"start", "stop", "restart", "enable", "disable"}:
        raise HTTPException(status_code=400, detail="Ação de serviço inválida")

    result = run_command(["systemctl", action, unit], timeout=60, check=False)
    await emit_snapshot(include_heavy=True)
    return JSONResponse(
        {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    )


@app.post("/api/docker/container/{container_name}/{action}")
async def api_container_action(request: Request, container_name: str, action: str) -> JSONResponse:
    ensure_authenticated(request)
    client = docker_client()
    if not client:
        raise HTTPException(status_code=503, detail="Docker indisponível")

    try:
        container = client.containers.get(container_name)
        if action == "start":
            container.start()
        elif action == "stop":
            container.stop(timeout=10)
        elif action == "restart":
            container.restart(timeout=10)
        elif action == "remove":
            container.remove(force=True)
        else:
            raise HTTPException(status_code=400, detail="Ação de container inválida")
    except Exception as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise

    await emit_snapshot(include_heavy=True)
    return JSONResponse({"success": True})


@app.post("/api/docker/prune")
async def api_docker_prune(request: Request) -> JSONResponse:
    ensure_authenticated(request)
    client = docker_client()
    if not client:
        raise HTTPException(status_code=503, detail="Docker indisponível")

    containers = client.containers.prune()
    images = client.images.prune(filters={"dangling": False})
    await emit_snapshot(include_heavy=True)
    return JSONResponse({"success": True, "containers": containers, "images": images})


@app.post("/api/firewall/allow")
async def api_firewall_allow(request: Request) -> JSONResponse:
    ensure_authenticated(request)
    payload = await request.json()
    rule = require_json_body(payload, "rule")
    parts = shlex.split(rule)
    result = run_command(["ufw", "allow", *parts], timeout=45, check=False)
    await emit_snapshot(include_heavy=True)
    return JSONResponse({"success": result.returncode == 0, "stdout": result.stdout, "stderr": result.stderr})


@app.post("/api/firewall/delete")
async def api_firewall_delete(request: Request) -> JSONResponse:
    ensure_authenticated(request)
    payload = await request.json()
    number = require_json_body(payload, "number")
    result = run_command(["ufw", "--force", "delete", number], timeout=45, check=False)
    await emit_snapshot(include_heavy=True)
    return JSONResponse({"success": result.returncode == 0, "stdout": result.stdout, "stderr": result.stderr})


@app.post("/api/process/{pid}/signal")
async def api_process_signal(request: Request, pid: int) -> JSONResponse:
    ensure_authenticated(request)
    payload = await request.json()
    signal_name = str(payload.get("signal", "TERM")).upper()
    mapping = {
        "TERM": signal.SIGTERM,
        "KILL": signal.SIGKILL,
        "INT": signal.SIGINT,
    }
    sig = mapping.get(signal_name)
    if sig is None:
        raise HTTPException(status_code=400, detail="Sinal inválido")

    try:
        os.kill(pid, sig)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await emit_snapshot(include_heavy=True)
    return JSONResponse({"success": True})


@app.get("/api/projects")
async def api_projects(request: Request) -> JSONResponse:
    ensure_authenticated(request)
    return JSONResponse({"projects": project_present_all(request)})


@app.post("/api/projects")
async def api_projects_save(request: Request) -> JSONResponse:
    ensure_authenticated(request)
    payload = await request.json()
    record = await asyncio.to_thread(project_store, payload)
    await emit_snapshot(include_heavy=True)
    return JSONResponse(project_present(record, request))


@app.get("/api/projects/{project_id}")
async def api_projects_detail(request: Request, project_id: str) -> JSONResponse:
    ensure_authenticated(request)
    project = project_find_record(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projeto nao encontrado.")
    return JSONResponse(project_present(project, request))


@app.post("/api/projects/{project_id}/analyze")
async def api_projects_analyze(request: Request, project_id: str) -> JSONResponse:
    ensure_authenticated(request)
    payload = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    include_ai = bool(payload.get("include_ai", False))
    model = str(payload.get("model", "") or "").strip()
    await asyncio.to_thread(project_run_analysis, project_id, include_ai=include_ai, model=model)
    project = project_find_record(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projeto nao encontrado apos a analise.")
    await emit_snapshot(include_heavy=True)
    return JSONResponse(project_present(project, request))


@app.get("/api/projects/{project_id}/bundle")
async def api_projects_bundle(request: Request, project_id: str) -> JSONResponse:
    ensure_authenticated(request)
    project = project_find_record(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projeto nao encontrado.")
    report = project_read_report(project_id)
    bundle = report.get("bundle") if isinstance(report, dict) else None
    if not isinstance(bundle, dict) or not bundle.get("artifacts"):
        raise HTTPException(status_code=404, detail="Bundle ainda nao foi gerado para este projeto.")
    return JSONResponse(bundle)


@app.post("/api/projects/{project_id}/deploy")
async def api_projects_deploy(request: Request, project_id: str) -> JSONResponse:
    ensure_authenticated(request)
    payload = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    reason = str(payload.get("reason", "manual") or "manual").strip() or "manual"
    include_ai = bool(payload.get("include_ai", False))
    model = str(payload.get("model", "") or "").strip()
    result = await asyncio.to_thread(project_deploy, project_id, reason=reason, include_ai=include_ai, model=model)
    await emit_snapshot(include_heavy=True)
    project = project_find_record(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projeto nao encontrado apos o deploy.")
    return JSONResponse({"project": project_present(project, request), "deployment": result})


@app.post("/api/projects/{project_id}/bootstrap")
async def api_projects_bootstrap(request: Request, project_id: str) -> JSONResponse:
    ensure_authenticated(request)
    payload = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    model = str(payload.get("model", "") or "").strip()
    result = await asyncio.to_thread(
        project_deploy,
        project_id,
        reason="simple-bootstrap",
        include_ai=True,
        model=model,
    )
    await emit_snapshot(include_heavy=True)
    project = project_find_record(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projeto nao encontrado apos o bootstrap.")
    return JSONResponse({"project": project_present(project, request), "deployment": result})


@app.post("/api/projects/{project_id}/apply-fix")
async def api_projects_apply_fix(request: Request, project_id: str) -> JSONResponse:
    ensure_authenticated(request)
    payload = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    candidate_id = require_json_body(payload, "candidate_id")
    retry_deploy = bool(payload.get("retry_deploy", False))
    updated = await asyncio.to_thread(project_apply_fix_candidate, project_id, candidate_id)
    deployment = None
    if retry_deploy:
        deployment = await asyncio.to_thread(project_deploy, project_id, reason=f"approved-fix:{candidate_id}", include_ai=False)
    await emit_snapshot(include_heavy=True)
    project = project_find_record(project_id) or updated
    return JSONResponse({"project": project_present(project, request), "deployment": deployment})


@app.post("/api/projects/{project_id}/rotate-secret")
async def api_projects_rotate_secret(request: Request, project_id: str) -> JSONResponse:
    ensure_authenticated(request)
    with PROJECTS_LOCK:
        registry = project_read_registry()
        projects = registry.get("projects", [])
        updated = None
        for index, project in enumerate(projects):
            if str(project.get("id", "")) != project_id:
                continue
            updated = dict(project)
            updated["webhook_secret"] = secrets.token_hex(24)
            updated["updated_at"] = utc_now_iso()
            projects[index] = updated
            break
        if updated is None:
            raise HTTPException(status_code=404, detail="Projeto nao encontrado.")
        registry["projects"] = projects
        project_write_registry(registry)
    await emit_snapshot(include_heavy=True)
    return JSONResponse(project_present(updated, request))


@app.delete("/api/projects/{project_id}")
async def api_projects_delete(request: Request, project_id: str) -> JSONResponse:
    ensure_authenticated(request)
    if project_find_record(project_id) is None:
        raise HTTPException(status_code=404, detail="Projeto nao encontrado.")
    await asyncio.to_thread(project_delete, project_id)
    await emit_snapshot(include_heavy=True)
    return JSONResponse({"success": True})


@app.post("/hooks/github/{project_id}")
async def github_project_webhook(project_id: str, request: Request) -> JSONResponse:
    project = project_find_record(project_id)
    if project is None or not bool(project.get("enabled", True)):
        raise HTTPException(status_code=404, detail="Webhook nao configurado para este projeto.")

    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_github_signature(str(project.get("webhook_secret", "")), body, signature):
        raise HTTPException(status_code=401, detail="Assinatura invalida.")

    try:
        payload = json.loads(body.decode("utf-8", errors="replace")) if body else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Payload JSON invalido: {exc}") from exc

    delivery_id = request.headers.get("X-GitHub-Delivery", uuid.uuid4().hex)
    event_name = request.headers.get("X-GitHub-Event", "unknown")
    delivery = {
        "id": delivery_id,
        "event": event_name,
        "received_at": utc_now_iso(),
        "status": "received",
        "repository": str(payload.get("repository", {}).get("full_name", "") or ""),
        "repository_url": str(payload.get("repository", {}).get("html_url", "") or ""),
        "ref": str(payload.get("ref", "") or ""),
        "head_commit": str(payload.get("after", "") or ""),
        "detail": "Webhook recebido e enfileirado para analise.",
    }
    await asyncio.to_thread(project_append_delivery, project_id, delivery)
    thread = threading.Thread(
        target=project_process_github_webhook,
        args=(project_id, delivery_id, event_name, payload),
        daemon=True,
    )
    thread.start()
    return JSONResponse({"accepted": True, "project_id": project_id, "delivery_id": delivery_id})


@app.get("/api/proxy")
async def api_proxy_snapshot(request: Request) -> JSONResponse:
    ensure_authenticated(request)
    return JSONResponse(await asyncio.to_thread(proxy_snapshot_safe))


@app.get("/api/proxy/logs")
async def api_proxy_logs(request: Request, tail: int = 200) -> JSONResponse:
    ensure_authenticated(request)
    safe_tail = max(20, min(tail, 1000))
    return JSONResponse({"logs": await asyncio.to_thread(proxy_log_tail, safe_tail)})


@app.get("/api/proxy/image-models")
async def api_proxy_image_models(request: Request) -> JSONResponse:
    ensure_authenticated(request)
    return JSONResponse({"models": await asyncio.to_thread(proxy_image_models)})


@app.post("/api/proxy/images/generate")
async def api_proxy_generate_image(request: Request) -> JSONResponse:
    ensure_authenticated(request)
    payload = await request.json()
    return JSONResponse(await asyncio.to_thread(proxy_generate_image, payload))


@app.get("/api/proxy/keys")
async def api_proxy_keys(request: Request) -> JSONResponse:
    ensure_authenticated(request)
    snapshot = await asyncio.to_thread(proxy_snapshot_safe)
    return JSONResponse({"keys": snapshot["keys"], "summary": snapshot["summary"]})


@app.post("/api/proxy/keys")
async def api_proxy_add_key(request: Request) -> JSONResponse:
    ensure_authenticated(request)
    payload = await request.json()
    key_value = require_json_body(payload, "key")
    label = str(payload.get("label", "")).strip()
    active = bool(payload.get("active", True))

    data = proxy_read_keys_file()
    next_id = int(data.get("next_id", 1) or 1)
    data.setdefault("keys", []).append(
        {
            "id": next_id,
            "label": label,
            "key": key_value,
            "active": active,
            "total_requests": 0,
            "successes": 0,
            "failures": 0,
            "cooldown_until": 0,
        }
    )
    data["next_id"] = next_id + 1
    proxy_write_keys_file(data)
    await asyncio.to_thread(proxy_force_reload)
    await emit_snapshot(include_heavy=True)
    return JSONResponse({"success": True, "id": next_id})


@app.post("/api/proxy/keys/{key_id}")
async def api_proxy_update_key(request: Request, key_id: int) -> JSONResponse:
    ensure_authenticated(request)
    payload = await request.json()
    data = proxy_read_keys_file()
    keys = data.setdefault("keys", [])
    target = next((item for item in keys if int(item.get("id", 0)) == key_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Key nao encontrada")

    if "label" in payload:
        target["label"] = str(payload.get("label", "")).strip()
    if "active" in payload:
        target["active"] = bool(payload.get("active"))
    if payload.get("key"):
        target["key"] = str(payload.get("key")).strip()
    if payload.get("reset_stats"):
        target["total_requests"] = 0
        target["successes"] = 0
        target["failures"] = 0
        target["cooldown_until"] = 0

    proxy_write_keys_file(data)
    await asyncio.to_thread(proxy_force_reload)
    await emit_snapshot(include_heavy=True)
    return JSONResponse({"success": True})


@app.delete("/api/proxy/keys/{key_id}")
async def api_proxy_delete_key(request: Request, key_id: int) -> JSONResponse:
    ensure_authenticated(request)
    data = proxy_read_keys_file()
    keys = data.setdefault("keys", [])
    filtered = [item for item in keys if int(item.get("id", 0)) != key_id]
    if len(filtered) == len(keys):
        raise HTTPException(status_code=404, detail="Key nao encontrada")
    data["keys"] = filtered
    proxy_write_keys_file(data)
    await asyncio.to_thread(proxy_force_reload)
    await emit_snapshot(include_heavy=True)
    return JSONResponse({"success": True})


@app.get("/api/whatsapp")
async def api_whatsapp_snapshot(request: Request) -> JSONResponse:
    ensure_authenticated(request)
    return JSONResponse(await asyncio.to_thread(whatsapp_snapshot, request))


@app.post("/api/whatsapp/config")
async def api_whatsapp_save_config(request: Request) -> JSONResponse:
    ensure_authenticated(request)
    payload = await request.json()
    editable = {
        "enabled": bool(payload.get("enabled", False)),
        "base_url": str(payload.get("base_url", "") or "").strip(),
        "api_key": str(payload.get("api_key", "") or "").strip() or whatsapp_read_config().get("api_key", ""),
        "instance_name": str(payload.get("instance_name", "") or "").strip() or "red-whatsapp-ai",
        "instance_token": str(payload.get("instance_token", "") or "").strip(),
        "bot_number": str(payload.get("bot_number", "") or "").strip(),
        "default_model": str(payload.get("default_model", "") or "").strip(),
        "group_prefix": str(payload.get("group_prefix", "") or "").strip() or "red,",
        "system_prompt": str(payload.get("system_prompt", "") or "").strip(),
        "mark_as_read": bool(payload.get("mark_as_read", True)),
        "typing_presence": bool(payload.get("typing_presence", True)),
        "auto_sync_targets": bool(payload.get("auto_sync_targets", True)),
        "context": {
            "max_messages": max(int(payload.get("context_max_messages", 28) or 28), 8),
            "max_chars": max(int(payload.get("context_max_chars", 14000) or 14000), 3000),
            "summary_trigger_messages": max(int(payload.get("summary_trigger_messages", 20) or 20), 6),
            "summary_keep_recent": max(int(payload.get("summary_keep_recent", 10) or 10), 4),
            "summary_target_chars": max(int(payload.get("summary_target_chars", 2200) or 2200), 600),
        },
    }
    if payload.get("webhook_secret"):
        editable["webhook_secret"] = str(payload.get("webhook_secret", "") or "").strip()
    saved = await asyncio.to_thread(whatsapp_write_config, editable)
    if bool(saved.get("base_url")) and bool(saved.get("api_key")) and bool(saved.get("instance_name")):
        try:
            await asyncio.to_thread(whatsapp_sync_webhook_remote, saved, whatsapp_public_webhook_url(request))
        except Exception as exc:
            await asyncio.to_thread(
                whatsapp_store_webhook_sync_result,
                status="error",
                url=whatsapp_public_webhook_url(request),
                error=str(exc),
            )
    await emit_snapshot(include_heavy=True)
    return JSONResponse(await asyncio.to_thread(whatsapp_snapshot, request))


@app.post("/api/whatsapp/targets/{chat_id}")
async def api_whatsapp_update_target(request: Request, chat_id: str) -> JSONResponse:
    ensure_authenticated(request)
    chat_id = unquote(chat_id)
    payload = await request.json()
    target = await asyncio.to_thread(
        whatsapp_upsert_target,
        {
            "chat_id": chat_id,
            "name": payload.get("name", ""),
            "kind": payload.get("kind", ""),
            "alerts_enabled": bool(payload.get("alerts_enabled", False)),
            "ai_enabled": bool(payload.get("ai_enabled", True)),
            "shell_enabled": bool(payload.get("shell_enabled", False)),
            "admin": bool(payload.get("admin", False)),
            "muted": bool(payload.get("muted", False)),
            "respond_mode": str(payload.get("respond_mode", "") or ""),
            "prefix_override": str(payload.get("prefix_override", "") or "").strip(),
            "model": str(payload.get("model", "") or "").strip(),
        },
    )
    await emit_snapshot(include_heavy=True)
    return JSONResponse({"target": target})


@app.get("/api/whatsapp/conversations/{chat_id}")
async def api_whatsapp_conversation(request: Request, chat_id: str) -> JSONResponse:
    ensure_authenticated(request)
    chat_id = unquote(chat_id)
    conversation = await asyncio.to_thread(whatsapp_read_conversation, chat_id, kind=whatsapp_conversation_kind(chat_id))
    return JSONResponse(conversation)


@app.delete("/api/whatsapp/conversations/{chat_id}")
async def api_whatsapp_delete_conversation(request: Request, chat_id: str) -> JSONResponse:
    ensure_authenticated(request)
    chat_id = unquote(chat_id)
    deleted = await asyncio.to_thread(ws.delete_conversation, WHATSAPP_DIR, chat_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversa nao encontrada.")
    await emit_snapshot(include_heavy=True)
    return JSONResponse({"deleted": True, "chat_id": chat_id})


@app.post("/api/whatsapp/test")
async def api_whatsapp_test(request: Request) -> JSONResponse:
    ensure_authenticated(request)
    config = whatsapp_read_config()
    state_payload = await asyncio.to_thread(whatsapp_connection_state, config)
    return JSONResponse(state_payload)


@app.post("/api/whatsapp/sync-targets")
async def api_whatsapp_sync_targets(request: Request) -> JSONResponse:
    ensure_authenticated(request)
    config = whatsapp_read_config()
    result = await asyncio.to_thread(whatsapp_sync_remote_targets, config)
    await asyncio.to_thread(whatsapp_store_targets_sync_result, result, status="manual")
    await emit_snapshot(include_heavy=True)
    return JSONResponse(result)


@app.post("/api/whatsapp/send-test")
async def api_whatsapp_send_test(request: Request) -> JSONResponse:
    ensure_authenticated(request)
    payload = await request.json()
    chat_id = require_json_body(payload, "chat_id")
    message = str(payload.get("message", "") or "").strip() or "Teste do painel RED VM."
    config = whatsapp_read_config()
    result = await asyncio.to_thread(whatsapp_send_text, config, chat_id, message)
    await emit_snapshot(include_heavy=True)
    return JSONResponse({"sent": True, "result": result})


@app.post("/api/whatsapp/instance/create")
async def api_whatsapp_create_instance(request: Request) -> JSONResponse:
    ensure_authenticated(request)
    config = whatsapp_read_config()
    if not str(config.get("base_url", "")).strip() or not str(config.get("api_key", "")).strip():
        raise HTTPException(status_code=400, detail="Configure a URL e a API key da Evolution antes de criar a instancia.")
    payload = {
        "instanceName": str(config.get("instance_name", "") or "red-whatsapp-ai"),
        "integration": "WHATSAPP-BAILEYS",
        "qrcode": True,
        "webhook": {
            "enabled": True,
            "url": whatsapp_public_webhook_url(request),
            "webhookByEvents": True,
            "webhookBase64": True,
            "events": ["MESSAGES_UPSERT", "MESSAGES_UPDATE", "CONNECTION_UPDATE", "QRCODE_UPDATED"],
        },
    }
    bot_number = re.sub(r"\D+", "", str(config.get("bot_number", "") or ""))
    if bot_number:
        payload["number"] = bot_number
    instance_token = str(config.get("instance_token", "") or "").strip()
    if instance_token:
        payload["token"] = instance_token
    status_code, response_payload = await asyncio.to_thread(
        whatsapp_request_json,
        config,
        "/instance/create",
        method="POST",
        payload=payload,
        timeout=60,
    )
    await asyncio.to_thread(whatsapp_capture_runtime_event, "instance.create", response_payload if isinstance(response_payload, dict) else {})
    try:
        await asyncio.to_thread(whatsapp_sync_webhook_remote, config, whatsapp_public_webhook_url(request))
    except Exception as exc:
        await asyncio.to_thread(
            whatsapp_store_webhook_sync_result,
            status="error",
            url=whatsapp_public_webhook_url(request),
            error=str(exc),
        )
    await emit_snapshot(include_heavy=True)
    return JSONResponse({"status_code": status_code, "payload": response_payload})


@app.post("/api/whatsapp/instance/connect")
async def api_whatsapp_connect_instance(request: Request) -> JSONResponse:
    ensure_authenticated(request)
    config = whatsapp_read_config()
    instance_name = str(config.get("instance_name", "") or "").strip()
    if not instance_name:
        raise HTTPException(status_code=400, detail="Informe o nome da instancia.")
    status_code, response_payload = await asyncio.to_thread(
        whatsapp_request_json,
        config,
        f"/instance/connect/{quote(instance_name, safe='')}",
        method="GET",
        timeout=60,
    )
    runtime = await asyncio.to_thread(whatsapp_capture_runtime_event, "instance.connect", response_payload if isinstance(response_payload, dict) else {})
    try:
        await asyncio.to_thread(whatsapp_sync_webhook_remote, config, whatsapp_public_webhook_url(request))
    except Exception as exc:
        await asyncio.to_thread(
            whatsapp_store_webhook_sync_result,
            status="error",
            url=whatsapp_public_webhook_url(request),
            error=str(exc),
        )
    await asyncio.to_thread(whatsapp_auto_sync_targets_if_ready, "instance.connect", runtime)
    await emit_snapshot(include_heavy=True)
    return JSONResponse({"status_code": status_code, "payload": response_payload})


@app.post("/api/whatsapp/webhook/sync")
async def api_whatsapp_sync_webhook(request: Request) -> JSONResponse:
    ensure_authenticated(request)
    config = whatsapp_read_config()
    response = await asyncio.to_thread(whatsapp_sync_webhook_remote, config, whatsapp_public_webhook_url(request))
    await emit_snapshot(include_heavy=True)
    return JSONResponse(response)


@app.post(WHATSAPP_WEBHOOK_PATH)
async def evolution_webhook(request: Request) -> JSONResponse:
    body = await request.body()
    config = whatsapp_read_config()
    expected = str(config.get("webhook_secret", "") or "").strip()
    provided = str(request.headers.get("Authorization", "") or "").strip()
    provided_query = str(request.query_params.get("token", "") or "").strip()
    if expected:
        valid_values = {expected, f"Bearer {expected}"}
        if provided not in valid_values and provided_query != expected:
            raise HTTPException(status_code=401, detail="Webhook do WhatsApp com autorizacao invalida.")
    try:
        payload = json.loads(body.decode("utf-8", errors="replace")) if body else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Payload JSON invalido: {exc}") from exc

    thread = threading.Thread(target=whatsapp_process_webhook_payload, args=(payload,), daemon=True)
    thread.start()
    return JSONResponse({"accepted": True})


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    if not is_authenticated_token(websocket.cookies.get(COOKIE_NAME)):
        await websocket.close(code=4401)
        return

    connection_id = await app.state.hub.connect(websocket)
    await app.state.hub.send(
        connection_id,
        {
            "type": "bootstrap",
            "payload": {
                "system": system_summary(),
                "telemetry": telemetry_snapshot(),
                "services": await asyncio.to_thread(parse_service_rows),
                "docker": await asyncio.to_thread(docker_snapshot),
                "processes": await asyncio.to_thread(process_snapshot),
                "firewall": await asyncio.to_thread(firewall_snapshot),
                "proxy": await asyncio.to_thread(proxy_snapshot_safe),
                "journal": list(app.state.journal_lines),
                "proxy_logs": list(app.state.proxy_log_lines),
                "whatsapp": await asyncio.to_thread(whatsapp_snapshot, None),
            },
        },
    )

    try:
        while True:
            raw = await websocket.receive_text()
            message = json.loads(raw)
            msg_type = message.get("type")

            if msg_type == "terminal.open":
                session = app.state.terminals.get(connection_id)
                if session is None:
                    session = TerminalSession(connection_id, app.state.hub, app.state.loop)
                    app.state.terminals[connection_id] = session
                session_id = session.start()
                await app.state.hub.send(
                    connection_id,
                    {"type": "terminal.opened", "payload": {"session_id": session_id}},
                )
            elif msg_type == "terminal.input":
                session = app.state.terminals.get(connection_id)
                if session:
                    session.write(str(message.get("payload", {}).get("data", "")))
            elif msg_type == "terminal.resize":
                session = app.state.terminals.get(connection_id)
                if session:
                    payload = message.get("payload", {})
                    session.resize(int(payload.get("rows", 32)), int(payload.get("cols", 120)))
            elif msg_type == "terminal.close":
                session = app.state.terminals.pop(connection_id, None)
                if session:
                    session.close()
            elif msg_type == "request.snapshot":
                await emit_snapshot(include_heavy=True)
            elif msg_type == "proxy.chat.start":
                payload = message.get("payload", {})
                model = str(payload.get("model", "")).strip()
                messages = payload.get("messages", [])
                options = payload.get("options", {})
                request_id = str(payload.get("request_id", "")).strip() or uuid.uuid4().hex
                if not model:
                    await app.state.hub.send(
                        connection_id,
                        {
                            "type": "proxy.chat.error",
                            "payload": {"error": "Selecione um modelo antes de enviar a mensagem.", "status_code": 0},
                        },
                    )
                    continue
                if not isinstance(messages, list) or not messages:
                    await app.state.hub.send(
                        connection_id,
                        {
                            "type": "proxy.chat.error",
                            "payload": {"error": "Historico de mensagens invalido.", "status_code": 0},
                        },
                    )
                    continue
                if proxy_get_chat_job(connection_id) is not None:
                    await app.state.hub.send(
                        connection_id,
                        {
                            "type": "proxy.chat.error",
                            "payload": {"error": "Ja existe uma resposta em andamento. Pare a resposta atual antes de iniciar outra.", "status_code": 0},
                        },
                    )
                    continue
                if not isinstance(options, dict):
                    options = {}
                job = ProxyChatJob(request_id)
                proxy_register_chat_job(connection_id, job)
                asyncio.create_task(asyncio.to_thread(proxy_chat_stream_worker, connection_id, job, model, messages, options))
            elif msg_type == "proxy.chat.stop":
                active_job = proxy_cancel_chat_job(connection_id)
                if active_job is None:
                    await app.state.hub.send(
                        connection_id,
                        {
                            "type": "proxy.chat.error",
                            "payload": {"error": "Nao existe resposta em andamento para interromper.", "status_code": 0},
                        },
                    )
                    continue
            elif msg_type == "vm.assistant.start":
                payload = message.get("payload", {})
                model = str(payload.get("model", "")).strip()
                prompt = str(payload.get("prompt", "")).strip()
                history = payload.get("history", [])
                request_id = str(payload.get("request_id", "")).strip() or uuid.uuid4().hex
                if not model:
                    await app.state.hub.send(
                        connection_id,
                        {
                            "type": "vm.assistant.error",
                            "payload": {"error": "Selecione um modelo antes de iniciar o assistente da VM.", "status_code": 0},
                        },
                    )
                    continue
                if not prompt:
                    await app.state.hub.send(
                        connection_id,
                        {
                            "type": "vm.assistant.error",
                            "payload": {"error": "Digite uma solicitação para o assistente da VM.", "status_code": 0},
                        },
                    )
                    continue
                if vm_get_assistant_job(connection_id) is not None:
                    await app.state.hub.send(
                        connection_id,
                        {
                            "type": "vm.assistant.error",
                            "payload": {"error": "Ja existe uma analise da VM em andamento. Pare a atual antes de iniciar outra.", "status_code": 0},
                        },
                    )
                    continue
                if not isinstance(history, list):
                    history = []
                job = ProxyChatJob(request_id)
                vm_register_assistant_job(connection_id, job)
                asyncio.create_task(asyncio.to_thread(vm_assistant_stream_worker, connection_id, job, model, history, prompt))
            elif msg_type == "vm.assistant.stop":
                active_job = vm_cancel_assistant_job(connection_id)
                if active_job is None:
                    await app.state.hub.send(
                        connection_id,
                        {
                            "type": "vm.assistant.error",
                            "payload": {"error": "Nao existe analise da VM em andamento para interromper.", "status_code": 0},
                        },
                    )
                    continue
    except WebSocketDisconnect:
        pass
    finally:
        session = app.state.terminals.pop(connection_id, None)
        if session:
            session.close()
        proxy_cancel_chat_job(connection_id)
        proxy_clear_chat_job(connection_id)
        vm_cancel_assistant_job(connection_id)
        vm_clear_assistant_job(connection_id)
        await app.state.hub.disconnect(connection_id)
