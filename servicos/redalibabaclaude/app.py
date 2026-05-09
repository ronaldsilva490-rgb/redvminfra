from __future__ import annotations

import json
import os
import queue
import re
import hashlib
import html
import sqlite3
import threading
import time
import uuid
from copy import deepcopy
from pathlib import Path
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


SERVICE_NAME = "redalibabaclaude"
HOST = os.getenv("REDALIBABACLAUDE_HOST", "0.0.0.0").strip() or "0.0.0.0"
PORT = env_int("REDALIBABACLAUDE_PORT", 5052)
REQUIRE_AUTH = env_bool("REDALIBABACLAUDE_REQUIRE_AUTH", True)
AUTH_TOKENS = set(split_values(os.getenv("REDALIBABACLAUDE_AUTH_TOKENS", "red")))
DEFAULT_MODEL = (
    os.getenv("REDALIBABACLAUDE_DEFAULT_MODEL")
    or "qwen-coder-plus"
).strip().lower()
STREAM_CHUNK_SIZE = max(1, env_int("REDALIBABACLAUDE_STREAM_CHUNK_SIZE", 1))
CONNECT_TIMEOUT = env_int("REDALIBABACLAUDE_CONNECT_TIMEOUT", 20)
READ_TIMEOUT = env_int("REDALIBABACLAUDE_READ_TIMEOUT", 360)
TLS_CERT = (os.getenv("REDALIBABACLAUDE_TLS_CERT") or "").strip()
TLS_KEY = (os.getenv("REDALIBABACLAUDE_TLS_KEY") or "").strip()
TOKEN_SAFETY_MARGIN = max(0, env_int("REDALIBABACLAUDE_TOKEN_SAFETY_MARGIN", 4096))
MIN_COMPLETION_TOKENS = max(1, env_int("REDALIBABACLAUDE_MIN_COMPLETION_TOKENS", 256))
MAX_OUTPUT_TOKENS = max(1, env_int("REDALIBABACLAUDE_MAX_OUTPUT_TOKENS", 8192))
MAX_CONTEXT_RETRIES = max(1, env_int("REDALIBABACLAUDE_MAX_CONTEXT_RETRIES", 5))
CONTEXT_RETRY_MARGIN_STEP = max(0, env_int("REDALIBABACLAUDE_CONTEXT_RETRY_MARGIN_STEP", 2048))
RATE_LIMIT_MIN_INTERVAL_SECONDS = max(0, env_int("REDALIBABACLAUDE_RATE_LIMIT_MIN_INTERVAL_SECONDS", 1))
RATE_LIMIT_COOLDOWN_SECONDS = max(1, env_int("REDALIBABACLAUDE_RATE_LIMIT_COOLDOWN_SECONDS", 12))
RATE_LIMIT_COOLDOWN_STEP_SECONDS = max(0, env_int("REDALIBABACLAUDE_RATE_LIMIT_COOLDOWN_STEP_SECONDS", 4))
RATE_LIMIT_MAX_COOLDOWN_SECONDS = max(1, env_int("REDALIBABACLAUDE_RATE_LIMIT_MAX_COOLDOWN_SECONDS", 45))
MAX_429_RETRIES = max(0, env_int("REDALIBABACLAUDE_MAX_429_RETRIES", 6))
SERVER_ERROR_COOLDOWN_SECONDS = max(1, env_int("REDALIBABACLAUDE_SERVER_ERROR_COOLDOWN_SECONDS", 4))
MAX_5XX_RETRIES = max(0, env_int("REDALIBABACLAUDE_MAX_5XX_RETRIES", 4))
EXPERIMENTAL_THINKING_BLOCKS = env_bool("REDALIBABACLAUDE_EXPERIMENTAL_THINKING_BLOCKS", False)
FAKE_THINKING_SIGNATURE_PREFIX = os.getenv("REDALIBABACLAUDE_FAKE_THINKING_SIGNATURE_PREFIX", "redalibaba").strip() or "redalibaba"
FORCE_ANTHROPIC_THINKING = env_bool("REDALIBABACLAUDE_FORCE_ANTHROPIC_THINKING", True)
WEBSEARCH_FALLBACK_ENABLED = env_bool("REDALIBABACLAUDE_WEBSEARCH_FALLBACK_ENABLED", True)
WEBSEARCH_INTERNALIZE_STREAM_REQUESTS = env_bool("REDALIBABACLAUDE_WEBSEARCH_INTERNALIZE_STREAM_REQUESTS", False)
WEBSEARCH_FALLBACK_URL = os.getenv("REDALIBABACLAUDE_WEBSEARCH_FALLBACK_URL", "http://127.0.0.1:8088/search").strip() or "http://127.0.0.1:8088/search"
WEBSEARCH_FALLBACK_MAX_RESULTS = max(1, env_int("REDALIBABACLAUDE_WEBSEARCH_FALLBACK_MAX_RESULTS", 5))
WEBSEARCH_FALLBACK_MAX_QUERIES = max(1, env_int("REDALIBABACLAUDE_WEBSEARCH_FALLBACK_MAX_QUERIES", 3))
WEBSEARCH_FALLBACK_TIMEOUT = max(1, env_int("REDALIBABACLAUDE_WEBSEARCH_FALLBACK_TIMEOUT", 8))
WEBSEARCH_FALLBACK_LANGUAGE = os.getenv("REDALIBABACLAUDE_WEBSEARCH_FALLBACK_LANGUAGE", "pt-BR").strip() or "pt-BR"
WEBSEARCH_INTERNAL_MAX_ROUNDS = max(0, env_int("REDALIBABACLAUDE_WEBSEARCH_INTERNAL_MAX_ROUNDS", 2))
TOOL_REPAIR_MAX_ROUNDS = max(0, env_int("REDALIBABACLAUDE_TOOL_REPAIR_MAX_ROUNDS", 3))
EMPTY_OUTPUT_REPAIR_MAX_ROUNDS = max(0, env_int("REDALIBABACLAUDE_EMPTY_OUTPUT_REPAIR_MAX_ROUNDS", 2))
TODO_ONLY_REPAIR_MAX_ROUNDS = max(0, env_int("REDALIBABACLAUDE_TODO_ONLY_REPAIR_MAX_ROUNDS", 2))
WEBFETCH_FALLBACK_TIMEOUT = max(1, env_int("REDALIBABACLAUDE_WEBFETCH_FALLBACK_TIMEOUT", 12))
WEBFETCH_FALLBACK_MAX_CHARS = max(1000, env_int("REDALIBABACLAUDE_WEBFETCH_FALLBACK_MAX_CHARS", 24000))
DATA_DIR = Path(os.getenv("REDALIBABACLAUDE_DATA_DIR", "/var/lib/redalibabaclaude")).expanduser()
TOKEN_METRICS_ENABLED = env_bool("REDALIBABACLAUDE_TOKEN_METRICS_ENABLED", False)
TOKEN_METRICS_DB = Path(os.getenv("REDALIBABACLAUDE_TOKEN_METRICS_DB", str(DATA_DIR / "token_usage.sqlite3"))).expanduser()
TOKEN_METRICS_QUEUE_SIZE = max(100, env_int("REDALIBABACLAUDE_TOKEN_METRICS_QUEUE_SIZE", 10000))
TOKEN_METRICS_RECENT_LIMIT = max(10, env_int("REDALIBABACLAUDE_TOKEN_METRICS_RECENT_LIMIT", 80))

ALIBABA_SG_BASE_URL = os.getenv("REDALIBABACLAUDE_SG_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1").rstrip("/")
ALIBABA_US_BASE_URL = os.getenv("REDALIBABACLAUDE_US_BASE_URL", "https://dashscope-us.aliyuncs.com/compatible-mode/v1").rstrip("/")
ALIBABA_SG_API_KEY = (
    os.getenv("REDALIBABACLAUDE_SG_API_KEY")
    or os.getenv("DASHSCOPE_SG_API_KEY")
    or ""
).strip()
ALIBABA_US_API_KEY = (
    os.getenv("REDALIBABACLAUDE_US_API_KEY")
    or os.getenv("DASHSCOPE_US_API_KEY")
    or ""
).strip()
ALIBABA_SG_API_KEYS = split_values(os.getenv("REDALIBABACLAUDE_SG_API_KEYS", ""))
ALIBABA_US_API_KEYS = split_values(os.getenv("REDALIBABACLAUDE_US_API_KEYS", ""))

http = requests.Session()
websearch_cache: dict[str, list[dict[str, str]]] = {}
http.headers.update(
    {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; REDSystemsBot/1.0; +https://redsystems.ddns.net)",
    }
)


class JsonResponseShim:
    def __init__(self, payload: dict[str, Any], status_code: int = 200):
        self.status_code = status_code
        self._payload = payload
        self.content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.text = self.content.decode("utf-8", "replace")

    def json(self) -> dict[str, Any]:
        return self._payload


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def first_positive_int(*values: Any) -> tuple[int, bool]:
    for value in values:
        number = safe_int(value, 0)
        if number > 0:
            return number, True
    return 0, False


def estimate_output_tokens_from_text(text: str) -> int:
    cleaned = str(text or "")
    if not cleaned:
        return 0
    return max(1, len(cleaned) // 4)


class TokenMetricsStore:
    def __init__(self, *, enabled: bool, db_path: Path, queue_size: int = 10000) -> None:
        self.enabled = enabled
        self.db_path = db_path
        self.queue: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=queue_size)
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None
        self.dropped_events = 0
        self.last_error = ""

    def start(self) -> None:
        if not self.enabled:
            return
        with self.lock:
            if self.thread and self.thread.is_alive():
                return
            self.thread = threading.Thread(target=self._writer_loop, name="redalibabaclaude-token-metrics", daemon=True)
            self.thread.start()

    def record(self, event: dict[str, Any]) -> None:
        if not self.enabled:
            return
        self.start()
        try:
            self.queue.put_nowait(dict(event))
        except queue.Full:
            self.dropped_events += 1

    def flush(self) -> None:
        if not self.enabled:
            return
        self.queue.join()

    def close(self) -> None:
        if not self.enabled:
            return
        thread = self.thread
        if not thread or not thread.is_alive():
            return
        try:
            self.queue.put(None, timeout=1.0)
        except Exception:
            return
        thread.join(timeout=2.0)

    def _writer_loop(self) -> None:
        for attempt in range(6):
            try:
                self._init_db()
                break
            except Exception as exc:
                self.last_error = str(exc)[:240]
                time.sleep(min(0.25 * (attempt + 1), 2.0))
        else:
            return
        while True:
            item = self.queue.get()
            try:
                if item is None:
                    return
                self._write_event(item)
            except Exception as exc:
                self.last_error = str(exc)[:240]
            finally:
                self.queue.task_done()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    request_id TEXT,
                    endpoint TEXT,
                    client_ip TEXT,
                    model TEXT,
                    provider TEXT,
                    backend TEXT,
                    target TEXT,
                    status_code INTEGER,
                    success INTEGER,
                    stream INTEGER,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    total_tokens INTEGER,
                    input_estimated INTEGER,
                    output_estimated INTEGER,
                    duration_ms INTEGER,
                    stop_reason TEXT,
                    error_type TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_events_ts ON usage_events(ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_events_model ON usage_events(model)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_events_endpoint ON usage_events(endpoint)")
            conn.commit()
        finally:
            conn.close()

    def _write_event(self, event: dict[str, Any]) -> None:
        row = {
            "ts": float(event.get("ts") or time.time()),
            "request_id": str(event.get("request_id") or ""),
            "endpoint": str(event.get("endpoint") or ""),
            "client_ip": str(event.get("client_ip") or ""),
            "model": str(event.get("model") or ""),
            "provider": str(event.get("provider") or ""),
            "backend": str(event.get("backend") or ""),
            "target": str(event.get("target") or ""),
            "status_code": safe_int(event.get("status_code"), 0),
            "success": 1 if event.get("success") else 0,
            "stream": 1 if event.get("stream") else 0,
            "input_tokens": max(0, safe_int(event.get("input_tokens"), 0)),
            "output_tokens": max(0, safe_int(event.get("output_tokens"), 0)),
            "input_estimated": 1 if event.get("input_estimated") else 0,
            "output_estimated": 1 if event.get("output_estimated") else 0,
            "duration_ms": max(0, safe_int(event.get("duration_ms"), 0)),
            "stop_reason": str(event.get("stop_reason") or ""),
            "error_type": str(event.get("error_type") or ""),
        }
        row["total_tokens"] = max(0, safe_int(event.get("total_tokens"), row["input_tokens"] + row["output_tokens"]))
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO usage_events (
                    ts, request_id, endpoint, client_ip, model, provider, backend, target,
                    status_code, success, stream, input_tokens, output_tokens, total_tokens,
                    input_estimated, output_estimated, duration_ms, stop_reason, error_type
                )
                VALUES (
                    :ts, :request_id, :endpoint, :client_ip, :model, :provider, :backend, :target,
                    :status_code, :success, :stream, :input_tokens, :output_tokens, :total_tokens,
                    :input_estimated, :output_estimated, :duration_ms, :stop_reason, :error_type
                )
                """,
                row,
            )
            conn.commit()
        finally:
            conn.close()

    def summary(self, *, recent_limit: int = 80) -> dict[str, Any]:
        if not self.enabled:
            return {
                "enabled": False,
                "db_path": str(self.db_path),
                "queue_depth": self.queue.qsize(),
                "dropped_events": self.dropped_events,
                "last_error": self.last_error,
                "summary": {},
                "models": [],
                "endpoints": [],
                "recent": [],
                "timeseries": [],
            }
        self.start()
        try:
            self._init_db()
            conn = self._connect()
            try:
                total = dict(conn.execute(
                    """
                    SELECT
                        COUNT(*) AS requests,
                        COALESCE(SUM(success), 0) AS successes,
                        COALESCE(SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END), 0) AS failures,
                        COALESCE(SUM(input_tokens), 0) AS input_tokens,
                        COALESCE(SUM(output_tokens), 0) AS output_tokens,
                        COALESCE(SUM(total_tokens), 0) AS total_tokens,
                        COALESCE(SUM(input_estimated), 0) AS input_estimated_events,
                        COALESCE(SUM(output_estimated), 0) AS output_estimated_events,
                        COALESCE(MAX(ts), 0) AS last_ts
                    FROM usage_events
                    """
                ).fetchone() or {})
                models = [dict(row) for row in conn.execute(
                    """
                    SELECT
                        model,
                        provider,
                        backend,
                        COUNT(*) AS requests,
                        COALESCE(SUM(input_tokens), 0) AS input_tokens,
                        COALESCE(SUM(output_tokens), 0) AS output_tokens,
                        COALESCE(SUM(total_tokens), 0) AS total_tokens,
                        COALESCE(SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END), 0) AS failures,
                        COALESCE(MAX(ts), 0) AS last_ts
                    FROM usage_events
                    GROUP BY model, provider, backend
                    ORDER BY total_tokens DESC, requests DESC
                    LIMIT 80
                    """
                ).fetchall()]
                endpoints = [dict(row) for row in conn.execute(
                    """
                    SELECT
                        endpoint,
                        COUNT(*) AS requests,
                        COALESCE(SUM(input_tokens), 0) AS input_tokens,
                        COALESCE(SUM(output_tokens), 0) AS output_tokens,
                        COALESCE(SUM(total_tokens), 0) AS total_tokens,
                        COALESCE(SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END), 0) AS failures
                    FROM usage_events
                    GROUP BY endpoint
                    ORDER BY total_tokens DESC, requests DESC
                    """
                ).fetchall()]
                recent = [dict(row) for row in conn.execute(
                    """
                    SELECT
                        id, ts, request_id, endpoint, client_ip, model, provider, backend, target,
                        status_code, success, stream, input_tokens, output_tokens, total_tokens,
                        input_estimated, output_estimated, duration_ms, stop_reason, error_type
                    FROM usage_events
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (max(1, min(recent_limit, 500)),),
                ).fetchall()]
                since = time.time() - 3600
                timeseries = [dict(row) for row in conn.execute(
                    """
                    SELECT
                        CAST(ts / 60 AS INTEGER) * 60 AS bucket_ts,
                        COUNT(*) AS requests,
                        COALESCE(SUM(input_tokens), 0) AS input_tokens,
                        COALESCE(SUM(output_tokens), 0) AS output_tokens,
                        COALESCE(SUM(total_tokens), 0) AS total_tokens
                    FROM usage_events
                    WHERE ts >= ?
                    GROUP BY bucket_ts
                    ORDER BY bucket_ts ASC
                    """,
                    (since,),
                ).fetchall()]
            finally:
                conn.close()
        except Exception as exc:
            self.last_error = str(exc)[:240]
            return {
                "enabled": True,
                "db_path": str(self.db_path),
                "queue_depth": self.queue.qsize(),
                "dropped_events": self.dropped_events,
                "last_error": self.last_error,
                "summary": {},
                "models": [],
                "endpoints": [],
                "recent": [],
                "timeseries": [],
            }
        return {
            "enabled": True,
            "db_path": str(self.db_path),
            "queue_depth": self.queue.qsize(),
            "dropped_events": self.dropped_events,
            "last_error": self.last_error,
            "summary": total,
            "models": models,
            "endpoints": endpoints,
            "recent": recent,
            "timeseries": timeseries,
        }


token_metrics_store = TokenMetricsStore(
    enabled=TOKEN_METRICS_ENABLED,
    db_path=TOKEN_METRICS_DB,
    queue_size=TOKEN_METRICS_QUEUE_SIZE,
)

MODELS = [
    {
        "id": "Qwen Coder Plus",
        "target": "qwen-coder-plus",
        "legacy_ids": ["ALI-SG/qwen-coder-plus", "qwen-coder-plus"],
        "display_name": "Qwen Coder Plus",
        "provider": "alibaba",
        "backend": "sg",
        "kind": "chat",
        "capabilities": ["chat", "tools"],
        "context_window": 262144,
        "tool_call_tested": True,
        "default": True,
    },
    {
        "id": "Qwen 3.6 Plus",
        "target": "qwen3.6-plus",
        "legacy_ids": ["ALI-SG/qwen3.6-plus", "qwen3.6-plus"],
        "display_name": "Qwen 3.6 Plus",
        "provider": "alibaba",
        "backend": "sg",
        "kind": "chat",
        "capabilities": ["chat", "tools"],
        "context_window": 262144,
        "tool_call_tested": True,
        "extra_body": {"enable_thinking": False},
        "default": False,
    },
    {
        "id": "Qwen 3.6 Max Preview",
        "target": "qwen3.6-max-preview",
        "legacy_ids": ["ALI-SG/qwen3.6-max-preview", "qwen3.6-max-preview"],
        "display_name": "Qwen 3.6 Max Preview",
        "provider": "alibaba",
        "backend": "sg",
        "kind": "chat",
        "capabilities": ["chat", "tools"],
        "context_window": 262144,
        "tool_call_tested": True,
        "extra_body": {"enable_thinking": False},
        "default": False,
    },
    {
        "id": "Qwen3 Coder Next",
        "target": "qwen3-coder-next",
        "legacy_ids": ["ALI-SG/qwen3-coder-next", "qwen3-coder-next"],
        "display_name": "Qwen3 Coder Next",
        "provider": "alibaba",
        "backend": "sg",
        "kind": "chat",
        "capabilities": ["chat", "tools"],
        "context_window": 262144,
        "tool_call_tested": True,
        "default": False,
    },
    {
        "id": "Qwen3 Coder Plus",
        "target": "qwen3-coder-plus",
        "legacy_ids": ["ALI-US/qwen3-coder-plus", "qwen3-coder-plus"],
        "display_name": "Qwen3 Coder Plus",
        "provider": "alibaba",
        "backend": "us",
        "kind": "chat",
        "capabilities": ["chat", "tools"],
        "context_window": 262144,
        "tool_call_tested": True,
        "default": False,
    },
    {
        "id": "DeepSeek V4 Pro",
        "target": "deepseek-v4-pro",
        "legacy_ids": ["ALI-US/deepseek-v4-pro", "deepseek-v4-pro"],
        "display_name": "DeepSeek V4 Pro",
        "provider": "alibaba",
        "backend": "us",
        "kind": "chat",
        "capabilities": ["chat", "tools"],
        "context_window": 262144,
        "tool_call_tested": True,
        "default": False,
    },
    {
        "id": "DeepSeek V4 Flash",
        "target": "deepseek-v4-flash",
        "legacy_ids": ["ALI-US/deepseek-v4-flash", "deepseek-v4-flash"],
        "display_name": "DeepSeek V4 Flash",
        "provider": "alibaba",
        "backend": "us",
        "kind": "chat",
        "capabilities": ["chat", "tools"],
        "context_window": 262144,
        "tool_call_tested": True,
        "default": False,
    },
    {
        "id": "Kimi K2.5",
        "target": "kimi-k2.5",
        "legacy_ids": ["ALI-US/kimi-k2.5", "kimi-k2.5"],
        "display_name": "Kimi K2.5",
        "provider": "alibaba",
        "backend": "us",
        "kind": "chat",
        "capabilities": ["chat", "tools"],
        "context_window": 262144,
        "tool_call_tested": True,
        "default": False,
    },
]
MODEL_BY_ID = {item["id"].lower(): item for item in MODELS}
for item in MODELS:
    for legacy_id in item.get("legacy_ids", []):
        MODEL_BY_ID[str(legacy_id).lower()] = item
MODEL_BY_TARGET = {item["target"].lower(): item for item in MODELS}

app = Flask(__name__)


class BackendKeyPool:
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


def configured_backend_keys(primary_key: str, extra_keys: list[str]) -> list[str]:
    keys: list[str] = []
    if primary_key:
        keys.append(primary_key)
    for key in extra_keys:
        if key and key not in keys:
            keys.append(key)
    return keys


BACKENDS = {
    "sg": {
        "id": "sg",
        "base_url": ALIBABA_SG_BASE_URL,
        "display_name": "Alibaba Singapore",
        "keys": configured_backend_keys(ALIBABA_SG_API_KEY, ALIBABA_SG_API_KEYS),
    },
    "us": {
        "id": "us",
        "base_url": ALIBABA_US_BASE_URL,
        "display_name": "Alibaba US Virginia",
        "keys": configured_backend_keys(ALIBABA_US_API_KEY, ALIBABA_US_API_KEYS),
    },
}
POOL_BY_BACKEND = {backend_id: BackendKeyPool(cfg["keys"]) for backend_id, cfg in BACKENDS.items()}


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


def client_ip() -> str:
    forwarded = str(request.headers.get("X-Forwarded-For") or "").split(",", 1)[0].strip()
    return forwarded or str(request.remote_addr or "")


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
    if key.startswith("claude-haiku-") or key.startswith("claude-sonnet-") or key.startswith("claude-opus-"):
        return default_model()
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


def red_search(query: str, *, max_results: int | None = None) -> list[dict[str, str]]:
    normalized = re.sub(r"\s+", " ", str(query or "")).strip()
    if not normalized:
        return []
    cache_key = normalized.lower()
    if cache_key in websearch_cache:
        return websearch_cache[cache_key]
    limit = max_results or WEBSEARCH_FALLBACK_MAX_RESULTS
    try:
        response = http.get(
            WEBSEARCH_FALLBACK_URL,
            params={"q": normalized, "format": "json", "language": WEBSEARCH_FALLBACK_LANGUAGE, "pageno": "1"},
            timeout=(5, WEBSEARCH_FALLBACK_TIMEOUT),
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        websearch_cache[cache_key] = []
        return []
    results: list[dict[str, str]] = []
    for item in data.get("results") or []:
        if not isinstance(item, dict):
            continue
        title = re.sub(r"\s+", " ", str(item.get("title") or "")).strip()
        url = str(item.get("url") or "").strip()
        snippet = re.sub(r"\s+", " ", str(item.get("content") or item.get("snippet") or "")).strip()
        if not url or not title:
            continue
        results.append({"title": title, "url": url, "snippet": snippet})
        if len(results) >= limit:
            break
    websearch_cache[cache_key] = results
    return results


def is_empty_or_failed_websearch_result(content: Any) -> bool:
    text = text_from_content(content)
    lowered = text.lower()
    if "web search results for query" not in lowered:
        return False
    if "api error:" in lowered:
        return True
    stripped = re.sub(r"reminder:.*", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    return len(lines) <= 2


def format_red_search_results(query: str, results: list[dict[str, str]]) -> str:
    lines = [
        f'Web search results for query: "{query}"',
        "",
        "RED Search/SearXNG fallback results:",
    ]
    for index, result in enumerate(results, 1):
        lines.append(f"{index}. {result['title']}")
        lines.append(f"   URL: {result['url']}")
        if result.get("snippet"):
            lines.append(f"   Trecho: {result['snippet']}")
    lines.append("")
    lines.append("REMINDER: You MUST include the sources above in your response to the user using markdown hyperlinks.")
    return "\n".join(lines)


def html_to_text(raw: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript|svg|canvas|iframe)\b.*?</\1>", " ", raw or "")
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</(p|div|li|h[1-6]|section|article|tr)>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def red_fetch(url: str, prompt: str = "") -> str:
    target = str(url or "").strip()
    if not re.match(r"^https?://", target, flags=re.IGNORECASE):
        return f"WebFetch error: invalid URL {target!r}"
    try:
        response = http.get(
            target,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.5",
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.7,en;q=0.6",
                "Cache-Control": "no-cache",
            },
            timeout=(5, WEBFETCH_FALLBACK_TIMEOUT),
            allow_redirects=True,
        )
    except Exception as exc:
        return f"WebFetch error while fetching {target}: {exc}"

    content_type = response.headers.get("content-type", "")
    raw = response.text or ""
    text = html_to_text(raw) if "html" in content_type.lower() else raw.strip()
    if not text:
        return f"WebFetch received {len(response.content or b'')} bytes from {response.url} with status {response.status_code}, but no readable text was extracted."
    if len(text) > WEBFETCH_FALLBACK_MAX_CHARS:
        text = text[:WEBFETCH_FALLBACK_MAX_CHARS].rstrip() + "\n\n[truncated by RED WebFetch]"

    lines = [
        f"WebFetch result for URL: {target}",
        f"Final URL: {response.url}",
        f"HTTP status: {response.status_code}",
    ]
    if prompt:
        lines.append(f"Prompt: {prompt}")
    lines.extend(["", "Content:", text])
    return "\n".join(lines)


def is_failed_webfetch_result(content: Any) -> bool:
    text = text_from_content(content).lower()
    return "unable to fetch from" in text or "webfetch failed" in text or "required parameter `url` is missing" in text


def websearch_fallback_tool_results(body: dict[str, Any]) -> dict[str, str]:
    if not WEBSEARCH_FALLBACK_ENABLED:
        return {}
    tool_queries: dict[str, str] = {}
    webfetch_calls: dict[str, dict[str, str]] = {}
    fallback_results: dict[str, str] = {}
    for message in body.get("messages") or []:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "").strip()
        content = message.get("content")
        if not isinstance(content, list):
            continue
        if role == "assistant":
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                tool_id = str(block.get("id") or "")
                tool_input = block.get("input") or {}
                tool_name = str(block.get("name") or "").strip()
                if tool_name == "WebSearch":
                    query = str(tool_input.get("query") or "").strip() if isinstance(tool_input, dict) else ""
                    if tool_id and query:
                        tool_queries[tool_id] = query
                elif tool_name == "WebFetch":
                    url = str(tool_input.get("url") or "").strip() if isinstance(tool_input, dict) else ""
                    prompt = str(tool_input.get("prompt") or "").strip() if isinstance(tool_input, dict) else ""
                    if tool_id and url:
                        webfetch_calls[tool_id] = {"url": url, "prompt": prompt}
        elif role == "user":
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                tool_use_id = str(block.get("tool_use_id") or "")
                query = tool_queries.get(tool_use_id)
                webfetch_call = webfetch_calls.get(tool_use_id)
                if query and is_empty_or_failed_websearch_result(block.get("content")):
                    results = red_search(query)
                    if not results:
                        continue
                    fallback_results[tool_use_id] = format_red_search_results(query, results)
                elif webfetch_call and is_failed_webfetch_result(block.get("content")):
                    fallback_results[tool_use_id] = red_fetch(webfetch_call["url"], webfetch_call.get("prompt", ""))
                else:
                    continue
                if len(fallback_results) >= WEBSEARCH_FALLBACK_MAX_QUERIES:
                    break
        if len(fallback_results) >= WEBSEARCH_FALLBACK_MAX_QUERIES:
            break
    return fallback_results


def anthropic_messages_to_openai(body: dict[str, Any]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    system_text = anthropic_system_text(body)
    fallback_tool_results = websearch_fallback_tool_results(body)
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

        if role != "assistant":
            pending_parts: list[dict[str, Any]] = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = str(block.get("type") or "").strip()
                if block_type in {"text", "image"}:
                    converted = content_block_to_openai(block)
                    if converted is not None:
                        pending_parts.append(converted)
                    continue
                if block_type == "tool_result":
                    if pending_parts:
                        if any(item.get("type") == "image_url" for item in pending_parts):
                            messages.append({"role": role, "content": pending_parts})
                        else:
                            messages.append({"role": role, "content": text_from_content(pending_parts)})
                        pending_parts = []
                    tool_call_id = str(block.get("tool_use_id") or "")
                    if tool_call_id:
                        tool_content = fallback_tool_results.get(tool_call_id, block.get("content"))
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call_id,
                                "content": text_from_content(tool_content),
                            }
                        )
            if pending_parts:
                if any(item.get("type") == "image_url" for item in pending_parts):
                    messages.append({"role": role, "content": pending_parts})
                else:
                    messages.append({"role": role, "content": text_from_content(pending_parts)})
            continue

        text_parts: list[dict[str, Any]] = []
        tool_calls: list[dict[str, Any]] = []

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
    apply_effort_options(payload, body)
    return payload


def request_effort(body: dict[str, Any]) -> str:
    output_config = body.get("output_config")
    if isinstance(output_config, dict):
        effort = str(output_config.get("effort") or "").strip().lower()
        if effort:
            return effort
    metadata = body.get("metadata")
    if isinstance(metadata, dict):
        effort = str(metadata.get("effort") or "").strip().lower()
        if effort:
            return effort
    return ""


def apply_effort_options(payload: dict[str, Any], body: dict[str, Any]) -> None:
    effort = request_effort(body)
    thinking = body.get("thinking")
    thinking_requested = isinstance(thinking, dict) and str(thinking.get("type") or "").strip().lower() not in {"", "disabled", "none"}
    if FORCE_ANTHROPIC_THINKING or effort in {"high", "xhigh", "max"} or thinking_requested:
        payload["enable_thinking"] = True


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


def clamp_max_tokens(requested: Any, input_tokens: int, context_window: int, *, extra_margin: int = 0, output_cap: int | None = None) -> int:
    try:
        requested_int = int(requested)
    except Exception:
        requested_int = 2048
    requested_int = max(1, requested_int)
    cap = int(output_cap) if output_cap else requested_int
    cap = max(1, cap)
    available = max(1, int(context_window) - max(0, int(input_tokens)) - TOKEN_SAFETY_MARGIN - max(0, int(extra_margin)))
    if available < MIN_COMPLETION_TOKENS:
        return max(1, min(available, cap))
    return max(1, min(requested_int, available, cap))


def is_internal_tool_request(payload: dict[str, Any]) -> bool:
    system_text = "\n".join(str(message.get("content") or "") for message in payload.get("messages") or [] if isinstance(message, dict) and message.get("role") == "system")
    if "WebSearch" in system_text or "WebFetch" in system_text:
        return True
    if "Generate a concise, sentence-case title" in system_text:
        return True
    return False


def apply_context_guard(payload: dict[str, Any], *, input_tokens: int, context_window: int) -> dict[str, Any]:
    guarded = deepcopy(payload)
    guarded["max_tokens"] = clamp_max_tokens(
        guarded.get("max_tokens") or 2048,
        input_tokens,
        context_window,
        output_cap=MAX_OUTPUT_TOKENS if is_internal_tool_request(guarded) else None,
    )
    return guarded


def parse_context_error_limits(body: str) -> tuple[int, int] | None:
    if not body:
        return None
    max_match = re.search(r"maximum context length is\s+(\d+)", body, re.IGNORECASE)
    prompt_match = re.search(r"prompt contains at least\s+(\d+)\s+input tokens", body, re.IGNORECASE)
    if max_match and prompt_match:
        return int(max_match.group(1)), int(prompt_match.group(1))
    return None


def parse_max_tokens_range(body: str) -> int | None:
    if not body:
        return None
    match = re.search(r"Range of max_tokens should be \[1,\s*(\d+)\]", body, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def is_max_tokens_range_error(status_code: int, body: str) -> bool:
    lowered = (body or "").lower()
    return status_code == 400 and "range of max_tokens should be" in lowered


def is_context_error(status_code: int, body: str) -> bool:
    lowered = (body or "").lower()
    return status_code == 400 and "maximum context length" in lowered and "input tokens" in lowered


def alibaba_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def alibaba_error_message(status_code: int, body: str) -> str:
    lowered = (body or "").lower()
    if status_code == 401:
        return "alibaba api key rejected"
    if status_code == 402:
        return "alibaba billing or balance issue"
    if status_code == 403:
        if "unpurchased" in lowered:
            return "alibaba model not enabled for this account"
        return "alibaba request forbidden"
    if status_code == 404:
        return "alibaba model or endpoint not found"
    if status_code == 429:
        return "alibaba rate limit"
    if status_code >= 500:
        return "alibaba provider temporary failure"
    if "incorrect api key" in lowered:
        return "alibaba api key rejected"
    if "failed to find the model" in lowered:
        return "alibaba model missing from upstream"
    return body[:240] or f"upstream error {status_code}"


def alias_backend(alias: dict[str, Any]) -> dict[str, Any]:
    return BACKENDS[str(alias.get("backend") or "").strip().lower()]


def backend_pool(alias: dict[str, Any]) -> BackendKeyPool:
    return POOL_BY_BACKEND[str(alias.get("backend") or "").strip().lower()]


def backend_has_keys(alias: dict[str, Any]) -> bool:
    return backend_pool(alias).has_keys()


def apply_alias_backend_options(payload: dict[str, Any], alias: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(payload)
    merged["model"] = alias["target"]
    extra_body = alias.get("extra_body") or {}
    for key, value in extra_body.items():
        if key == "enable_thinking" and merged.get("enable_thinking") is True:
            continue
        merged[key] = value
    tool_choice = merged.get("tool_choice")
    tool_choice_allowed = tool_choice is None or (isinstance(tool_choice, str) and tool_choice in {"auto", "none"})
    if merged.get("enable_thinking") is True and not tool_choice_allowed:
        # Alibaba rejects forced/required tool_choice while thinking is enabled.
        # Keeping tools available in auto mode preserves thinking and tool calls.
        merged.pop("tool_choice", None)
    return merged


def token_usage_from_openai_usage(
    usage: dict[str, Any] | None,
    *,
    fallback_input_tokens: int = 0,
    fallback_output_tokens: int = 0,
) -> dict[str, Any]:
    usage = usage or {}
    input_tokens, input_exact = first_positive_int(usage.get("prompt_tokens"), usage.get("input_tokens"))
    output_tokens, output_exact = first_positive_int(usage.get("completion_tokens"), usage.get("output_tokens"))
    total_tokens, total_exact = first_positive_int(usage.get("total_tokens"))
    if not input_exact and fallback_input_tokens > 0:
        input_tokens = fallback_input_tokens
    if not output_exact and fallback_output_tokens > 0:
        output_tokens = fallback_output_tokens
    if not total_exact:
        total_tokens = input_tokens + output_tokens
    return {
        "input_tokens": max(0, input_tokens),
        "output_tokens": max(0, output_tokens),
        "total_tokens": max(0, total_tokens),
        "input_estimated": not input_exact and input_tokens > 0,
        "output_estimated": not output_exact and output_tokens > 0,
    }


def metrics_context(
    *,
    endpoint: str,
    alias: dict[str, Any],
    stream: bool,
    input_tokens_estimate: int,
    started_at: float,
) -> dict[str, Any]:
    return {
        "ts": time.time(),
        "request_id": str(request.headers.get("X-Request-Id") or uuid.uuid4()),
        "endpoint": endpoint,
        "client_ip": client_ip(),
        "model": alias.get("id") or "",
        "provider": alias.get("provider") or "",
        "backend": alias.get("backend") or "",
        "target": alias.get("target") or "",
        "stream": bool(stream),
        "input_tokens_estimate": max(0, int(input_tokens_estimate or 0)),
        "started_at": started_at,
    }


def record_token_usage(
    context: dict[str, Any] | None,
    *,
    usage: dict[str, Any] | None = None,
    status_code: int = 200,
    success: bool = True,
    output_tokens_estimate: int = 0,
    stop_reason: str = "",
    error_type: str = "",
) -> None:
    if not context:
        return
    tokens = token_usage_from_openai_usage(
        usage,
        fallback_input_tokens=safe_int(context.get("input_tokens_estimate"), 0),
        fallback_output_tokens=output_tokens_estimate,
    )
    event = {
        "ts": context.get("ts") or time.time(),
        "request_id": context.get("request_id") or "",
        "endpoint": context.get("endpoint") or "",
        "client_ip": context.get("client_ip") or "",
        "model": context.get("model") or "",
        "provider": context.get("provider") or "",
        "backend": context.get("backend") or "",
        "target": context.get("target") or "",
        "stream": bool(context.get("stream")),
        "status_code": status_code,
        "success": success,
        "duration_ms": int(max(0, (time.time() - float(context.get("started_at") or time.time())) * 1000)),
        "stop_reason": stop_reason,
        "error_type": error_type,
    }
    event.update(tokens)
    token_metrics_store.record(event)


def proxy_openai_chat(payload: dict[str, Any], *, stream: bool, api_key: str, base_url: str) -> requests.Response:
    return http.post(
        f"{base_url}/chat/completions",
        headers=alibaba_headers(api_key),
        json=payload,
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
        stream=stream,
    )


def proxy_openai_chat_with_context_retry(
    payload: dict[str, Any],
    *,
    alias: dict[str, Any],
    stream: bool,
    context_window: int,
    input_tokens: int,
) -> requests.Response:
    backend = alias_backend(alias)
    pool = backend_pool(alias)
    current_payload = apply_context_guard(apply_alias_backend_options(payload, alias), input_tokens=input_tokens, context_window=context_window)
    extra_margin = 0
    rate_retries_left = MAX_429_RETRIES
    server_retries_left = MAX_5XX_RETRIES
    output_limit_retry_used = False
    for _attempt in range(MAX_CONTEXT_RETRIES + MAX_429_RETRIES + MAX_5XX_RETRIES + 2):
        pool_item = pool.acquire()
        if pool_item is None:
            raise RuntimeError("alibaba api key not configured")
        response = proxy_openai_chat(current_payload, stream=stream, api_key=str(pool_item["token"]), base_url=str(backend["base_url"]))
        if response.status_code < 400:
            pool.on_success(pool_item)
            return response
        try:
            body_text = response.text
        except Exception:
            body_text = ""
        if response.status_code == 429:
            pool.on_429(pool_item)
            if rate_retries_left <= 0:
                return response
            rate_retries_left -= 1
            continue
        if response.status_code >= 500:
            pool.on_5xx(pool_item)
            if server_retries_left <= 0:
                return response
            server_retries_left -= 1
            continue
        if is_max_tokens_range_error(response.status_code, body_text) and not output_limit_retry_used:
            max_allowed = parse_max_tokens_range(body_text) or MAX_OUTPUT_TOKENS
            next_payload = deepcopy(current_payload)
            try:
                current_max_tokens = int(next_payload.get("max_tokens") or 0)
            except Exception:
                current_max_tokens = 0
            next_payload["max_tokens"] = max(1, min(current_max_tokens or max_allowed, max_allowed))
            output_limit_retry_used = True
            if next_payload["max_tokens"] < current_max_tokens or current_max_tokens <= 0:
                current_payload = next_payload
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


def proxy_anthropic_payload_with_internal_tools(
    payload: dict[str, Any],
    *,
    alias: dict[str, Any],
    stream: bool,
    context_window: int,
    input_tokens: int,
) -> tuple[requests.Response, bool]:
    current_payload = deepcopy(payload)
    if stream and not WEBSEARCH_INTERNALIZE_STREAM_REQUESTS:
        current_payload["stream"] = True
        upstream = proxy_openai_chat_with_context_retry(
            current_payload,
            alias=alias,
            stream=True,
            context_window=context_window,
            input_tokens=input_tokens,
        )
        return upstream, True

    max_internal_rounds = max(WEBSEARCH_INTERNAL_MAX_ROUNDS, TOOL_REPAIR_MAX_ROUNDS, EMPTY_OUTPUT_REPAIR_MAX_ROUNDS)
    for round_index in range(max_internal_rounds + 1):
        request_payload = deepcopy(current_payload)
        if WEBSEARCH_FALLBACK_ENABLED:
            request_payload["stream"] = False
        else:
            request_payload["stream"] = stream
        upstream = proxy_openai_chat_with_context_retry(
            request_payload,
            alias=alias,
            stream=bool(request_payload.get("stream")),
            context_window=context_window,
            input_tokens=input_tokens,
        )
        if upstream.status_code >= 400 or not WEBSEARCH_FALLBACK_ENABLED or bool(request_payload.get("stream")):
            return upstream, bool(request_payload.get("stream"))
        try:
            data = upstream.json()
        except Exception:
            return upstream, False
        invalids = invalid_tool_calls_from_openai(data, current_payload)
        if invalids:
            if round_index < TOOL_REPAIR_MAX_ROUNDS:
                current_payload = append_invalid_tool_results(current_payload, data, invalids)
                input_tokens = estimate_openai_tokens(current_payload)
                continue
            return synthetic_tool_validation_response(current_payload, invalids), False
        calls = internal_tool_calls_from_openai(data)
        if not calls:
            if not openai_has_visible_output(data):
                if round_index < EMPTY_OUTPUT_REPAIR_MAX_ROUNDS:
                    current_payload = append_empty_output_repair(current_payload)
                    input_tokens = estimate_openai_tokens(current_payload)
                    continue
                return synthetic_empty_output_response(current_payload), False
            return upstream, False
        if round_index >= WEBSEARCH_INTERNAL_MAX_ROUNDS:
            return upstream, False
        current_payload = append_internal_tool_results(current_payload, data, calls)
        input_tokens = estimate_openai_tokens(current_payload)
    return upstream, False


def anthropic_message_from_openai(data: dict[str, Any], model_name: str) -> dict[str, Any]:
    choice = ((data.get("choices") or [{}]) or [{}])[0]
    message = choice.get("message") or {}
    content_blocks: list[dict[str, Any]] = []
    reasoning_text = message.get("reasoning_content")
    if EXPERIMENTAL_THINKING_BLOCKS and isinstance(reasoning_text, str) and reasoning_text:
        content_blocks.append(
            {
                "type": "thinking",
                "thinking": reasoning_text,
                "signature": fake_thinking_signature(reasoning_text, data.get("id") or ""),
            }
        )
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


def openai_response_text(data: dict[str, Any]) -> str:
    parts: list[str] = []
    for choice in data.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        delta = choice.get("delta") or {}
        delta_content = delta.get("content") if isinstance(delta, dict) else None
        if isinstance(delta_content, str):
            parts.append(delta_content)
    return "".join(parts)


def openai_stop_reason(data: dict[str, Any]) -> str:
    choice = ((data.get("choices") or [{}]) or [{}])[0]
    finish_reason = str(choice.get("finish_reason") or "")
    if finish_reason == "tool_calls":
        return "tool_use"
    if finish_reason == "length":
        return "max_tokens"
    return finish_reason or "end_turn"


def internal_tool_calls_from_openai(data: dict[str, Any]) -> list[dict[str, Any]]:
    choice = ((data.get("choices") or [{}]) or [{}])[0]
    message = choice.get("message") or {}
    if str(choice.get("finish_reason") or "") != "tool_calls":
        return []
    calls: list[dict[str, Any]] = []
    for tool_call in message.get("tool_calls") or []:
        if not isinstance(tool_call, dict):
            continue
        function = tool_call.get("function") or {}
        name = str(function.get("name") or "").strip()
        arguments = function.get("arguments") or "{}"
        try:
            parsed = json.loads(arguments)
        except Exception:
            parsed = {}
        if name == "WebSearch":
            query = str(parsed.get("query") or "").strip() if isinstance(parsed, dict) else ""
            if query:
                calls.append({"id": str(tool_call.get("id") or ""), "name": name, "query": query})
        elif name == "WebFetch":
            url = str(parsed.get("url") or "").strip() if isinstance(parsed, dict) else ""
            prompt = str(parsed.get("prompt") or "").strip() if isinstance(parsed, dict) else ""
            if url:
                calls.append({"id": str(tool_call.get("id") or ""), "name": name, "url": url, "prompt": prompt})
    return calls


def openai_tool_schema_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    schemas: dict[str, dict[str, Any]] = {}
    for tool in payload.get("tools") or []:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function") or {}
        name = str(function.get("name") or "").strip()
        parameters = function.get("parameters")
        if name and isinstance(parameters, dict):
            schemas[name] = parameters
    return schemas


def parse_tool_arguments(value: Any) -> tuple[dict[str, Any] | None, str]:
    if isinstance(value, dict):
        return value, json.dumps(value, ensure_ascii=False)
    raw = str(value or "").strip()
    if not raw:
        return {}, raw
    try:
        parsed = json.loads(raw)
    except Exception:
        return None, raw
    if not isinstance(parsed, dict):
        return None, raw
    return parsed, raw


def tool_calls_from_openai_message(data: dict[str, Any]) -> list[dict[str, Any]]:
    choice = ((data.get("choices") or [{}]) or [{}])[0]
    message = choice.get("message") or {}
    if str(choice.get("finish_reason") or "") != "tool_calls":
        return []
    return [item for item in message.get("tool_calls") or [] if isinstance(item, dict)]


def invalid_tool_calls(tool_calls: list[dict[str, Any]], payload: dict[str, Any]) -> list[dict[str, Any]]:
    schemas = openai_tool_schema_map(payload)
    invalids: list[dict[str, Any]] = []
    for index, tool_call in enumerate(tool_calls):
        function = tool_call.get("function") or {}
        name = str(function.get("name") or "").strip()
        call_id = str(tool_call.get("id") or f"call_{uuid.uuid4().hex[:10]}")
        arguments, raw_arguments = parse_tool_arguments(function.get("arguments"))
        if arguments is None:
            invalids.append(
                {
                    "id": call_id,
                    "index": index,
                    "name": name,
                    "missing": [],
                    "raw_arguments": raw_arguments,
                    "message": "arguments must be a JSON object",
                }
            )
            continue
        schema = schemas.get(name) or {}
        required = schema.get("required") if isinstance(schema, dict) else []
        if not isinstance(required, list):
            required = []
        required_fields = [str(item) for item in required if isinstance(item, str)]
        missing = [
            field
            for field in required_fields
            if field not in arguments or arguments.get(field) is None or (isinstance(arguments.get(field), str) and not arguments.get(field).strip())
        ]
        if missing:
            invalids.append(
                {
                    "id": call_id,
                    "index": index,
                    "name": name,
                    "missing": missing,
                    "raw_arguments": raw_arguments,
                    "message": "missing required fields",
                }
            )
    return invalids


def invalid_tool_calls_from_openai(data: dict[str, Any], payload: dict[str, Any]) -> list[dict[str, Any]]:
    return invalid_tool_calls(tool_calls_from_openai_message(data), payload)


def format_invalid_tool_result(invalid: dict[str, Any]) -> str:
    name = str(invalid.get("name") or "unknown")
    missing = [str(item) for item in invalid.get("missing") or []]
    missing_text = ", ".join(missing) if missing else "valid JSON object"
    raw_arguments = str(invalid.get("raw_arguments") or "")
    return (
        "Tool call validation failed before client execution. "
        f"Tool `{name}` was called with invalid input: {invalid.get('message')}; required: {missing_text}. "
        f"Received arguments: {raw_arguments or '{}'}\n"
        "Call the same tool again with a valid JSON object that satisfies the schema. "
        "Do not explain this validation issue to the user; just make the corrected tool call."
    )


def append_invalid_tool_results(payload: dict[str, Any], data: dict[str, Any], invalids: list[dict[str, Any]]) -> dict[str, Any]:
    next_payload = deepcopy(payload)
    messages = next_payload.setdefault("messages", [])
    if not isinstance(messages, list):
        messages = []
        next_payload["messages"] = messages
    choice = ((data.get("choices") or [{}]) or [{}])[0]
    message = deepcopy(choice.get("message") or {})
    message.setdefault("role", "assistant")
    message.setdefault("content", "")
    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list):
        for invalid in invalids:
            index = safe_int(invalid.get("index"), -1)
            if 0 <= index < len(tool_calls) and isinstance(tool_calls[index], dict) and not tool_calls[index].get("id"):
                tool_calls[index]["id"] = str(invalid.get("id") or f"call_{uuid.uuid4().hex[:10]}")
    messages.append(message)
    for invalid in invalids:
        messages.append(
            {
                "role": "tool",
                "tool_call_id": str(invalid.get("id") or f"call_{uuid.uuid4().hex[:10]}"),
                "content": format_invalid_tool_result(invalid),
            }
        )
    next_payload["stream"] = bool(payload.get("stream"))
    return next_payload


def openai_has_visible_output(data: dict[str, Any]) -> bool:
    choice = ((data.get("choices") or [{}]) or [{}])[0]
    message = choice.get("message") or {}
    if message.get("tool_calls"):
        return True
    content = message.get("content")
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        return any(text_from_content(item).strip() for item in content)
    return False


def append_empty_output_repair(payload: dict[str, Any]) -> dict[str, Any]:
    next_payload = deepcopy(payload)
    messages = next_payload.setdefault("messages", [])
    if not isinstance(messages, list):
        messages = []
        next_payload["messages"] = messages
    messages.append({"role": "assistant", "content": ""})
    messages.append(
        {
            "role": "user",
            "content": (
                "Your previous assistant turn produced only hidden reasoning and no visible answer or tool call. "
                "Continue now by either calling the appropriate tool with valid JSON input or answering visibly. "
                "If the user asked to create or update an artifact, you must call the file tool before marking the task complete. "
                "Todo updates alone are not a deliverable. "
                "Do not return another reasoning-only response."
            ),
        }
    )
    next_payload["stream"] = bool(payload.get("stream"))
    return next_payload


def synthetic_tool_validation_response(payload: dict[str, Any], invalids: list[dict[str, Any]]) -> "JsonResponseShim":
    details = "; ".join(format_invalid_tool_result(item).splitlines()[0] for item in invalids)
    return JsonResponseShim(
        {
            "id": f"chatcmpl_{uuid.uuid4().hex}",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": f"A chamada de ferramenta veio invalida repetidas vezes e foi bloqueada pelo proxy para evitar loop. {details}",
                    },
                }
            ],
            "usage": {"prompt_tokens": estimate_openai_tokens(payload), "completion_tokens": 0},
        }
    )


def synthetic_empty_output_response(payload: dict[str, Any]) -> "JsonResponseShim":
    return JsonResponseShim(
        {
            "id": f"chatcmpl_{uuid.uuid4().hex}",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": "A resposta do modelo veio vazia depois das tentativas internas de reparo. O proxy bloqueou a conclusao silenciosa para evitar marcar a tarefa como pronta sem entregar nada.",
                    },
                }
            ],
            "usage": {"prompt_tokens": estimate_openai_tokens(payload), "completion_tokens": 0},
        }
    )


def empty_output_warning_text(status_code: int | None = None) -> str:
    suffix = f" Upstream status: {status_code}." if status_code else ""
    return (
        "A resposta do modelo veio sem resultado visivel nem chamada de ferramenta. "
        "O proxy bloqueou a conclusao silenciosa para evitar marcar a tarefa como pronta sem entregar nada."
        f"{suffix}"
    )


def todo_only_warning_text(status_code: int | None = None) -> str:
    suffix = f" Upstream status: {status_code}." if status_code else ""
    return (
        "A resposta do modelo parou apos atualizar o todo e descrever o plano, sem executar a acao concreta no workspace. "
        "O proxy bloqueou a conclusao silenciosa para evitar marcar a tarefa como pronta sem entrega real."
        f"{suffix}"
    )


def payload_tool_names(payload: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for tool in payload.get("tools") or []:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function") if isinstance(tool.get("function"), dict) else tool
        name = str(function.get("name") or "").strip().lower()
        if name:
            names.add(name)
    return names


def last_user_text_from_openai_messages(payload: dict[str, Any]) -> str:
    for message in reversed(payload.get("messages") or []):
        if not isinstance(message, dict):
            continue
        if str(message.get("role") or "").strip() != "user":
            continue
        text = text_from_content(message.get("content"))
        if text.strip():
            return text.strip().lower()
    return ""


def has_recent_todo_without_workspace_action(payload: dict[str, Any]) -> bool:
    messages = payload.get("messages") or []
    last_user_index = -1
    for index, message in enumerate(messages):
        if isinstance(message, dict) and str(message.get("role") or "").strip() == "user":
            last_user_index = index
    segment = messages[last_user_index + 1 :] if last_user_index >= 0 else messages
    tool_name_by_id: dict[str, str] = {}
    saw_todo = False
    saw_non_todo_action = False
    for message in segment:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "").strip()
        if role == "assistant":
            for tool_call in message.get("tool_calls") or []:
                if not isinstance(tool_call, dict):
                    continue
                function = tool_call.get("function") or {}
                tool_call_id = str(tool_call.get("id") or "").strip()
                tool_name = str(function.get("name") or "").strip().lower()
                if tool_call_id and tool_name:
                    tool_name_by_id[tool_call_id] = tool_name
        elif role == "tool":
            tool_name = tool_name_by_id.get(str(message.get("tool_call_id") or "").strip(), "")
            if tool_name == "todowrite":
                saw_todo = True
            elif tool_name and tool_name not in {"todoread"}:
                saw_non_todo_action = True
    return saw_todo and not saw_non_todo_action


def request_likely_requires_workspace_action(payload: dict[str, Any]) -> bool:
    if not payload_tool_names(payload).intersection({"write", "edit", "multiedit", "notebookedit", "bash"}):
        return False
    text = last_user_text_from_openai_messages(payload)
    if not text:
        return False
    keywords = (
        "crie",
        "criar",
        "faca",
        "fazer",
        "construa",
        "implemente",
        "editar",
        "edite",
        "atualize",
        "corrija",
        "gera",
        "gere",
        "site",
        "pagina",
        "landing page",
        "portfolio",
        "html",
        "css",
        "js",
        "arquivo",
        "componente",
        "component",
        "create",
        "build",
        "make",
        "write",
        "edit",
        "update",
        "fix",
        "implement",
        "generate",
        "file",
        "page",
    )
    return any(keyword in text for keyword in keywords)


def should_retry_todo_only_completion(payload: dict[str, Any], visible_text: str) -> bool:
    return bool(visible_text and request_likely_requires_workspace_action(payload) and has_recent_todo_without_workspace_action(payload))


def append_todo_only_repair(payload: dict[str, Any], assistant_content: str) -> dict[str, Any]:
    next_payload = deepcopy(payload)
    messages = next_payload.setdefault("messages", [])
    if not isinstance(messages, list):
        messages = []
        next_payload["messages"] = messages
    messages.append({"role": "assistant", "content": assistant_content})
    messages.append(
        {
            "role": "user",
            "content": (
                "Your previous assistant turn updated the todo list or described intended work, "
                "but did not actually execute a non-todo workspace action. "
                "Continue now by taking the next concrete step. "
                "If the request requires creating or editing files, call a non-todo tool such as Write, Edit, MultiEdit, NotebookEdit, or Bash before stopping. "
                "Do not stop after TodoWrite alone."
            ),
        }
    )
    next_payload["stream"] = bool(payload.get("stream"))
    return next_payload


def append_internal_tool_results(payload: dict[str, Any], data: dict[str, Any], calls: list[dict[str, Any]]) -> dict[str, Any]:
    next_payload = deepcopy(payload)
    choice = ((data.get("choices") or [{}]) or [{}])[0]
    message = deepcopy(choice.get("message") or {})
    message.setdefault("role", "assistant")
    message.setdefault("content", "")
    next_payload.setdefault("messages", []).append(message)
    for call in calls:
        if call["name"] == "WebSearch":
            query = call["query"]
            results = red_search(query)
            content = format_red_search_results(query, results) if results else f'Web search results for query: "{query}"\n\nNo results found by RED Search/SearXNG.'
        elif call["name"] == "WebFetch":
            content = red_fetch(call["url"], call.get("prompt", ""))
        else:
            continue
        next_payload["messages"].append(
            {
                "role": "tool",
                "tool_call_id": call["id"],
                "content": content,
            }
        )
    next_payload["stream"] = bool(payload.get("stream"))
    return next_payload


def sse_event(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=True)}\n\n"


def fake_thinking_signature(text: str, salt: str = "") -> str:
    digest = hashlib.sha256(f"{FAKE_THINKING_SIGNATURE_PREFIX}:{salt}:{text}".encode("utf-8", "replace")).hexdigest()
    return f"{FAKE_THINKING_SIGNATURE_PREFIX}:{digest}"


def openai_tool_calls_from_stream_state(tool_state: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for index in sorted(tool_state):
        state = tool_state[index]
        name = str(state.get("name") or "")
        arguments = "".join(state.get("arguments") or [])
        calls.append(
            {
                "id": str(state.get("id") or f"call_{uuid.uuid4().hex[:10]}"),
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": arguments,
                },
            }
        )
    return calls


def internal_calls_from_stream_tool_state(tool_state: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    if not tool_state:
        return []
    data = {
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": openai_tool_calls_from_stream_state(tool_state),
                },
            }
        ]
    }
    calls = internal_tool_calls_from_openai(data)
    return calls if len(calls) == len(tool_state) else []


def anthropic_sse_from_openai_stream_with_internal_tools(
    initial_response: requests.Response,
    *,
    payload: dict[str, Any],
    alias: dict[str, Any],
    model_name: str,
    context_window: int,
    input_tokens: int,
    metrics: dict[str, Any] | None = None,
):
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

    current_payload = deepcopy(payload)
    current_response = initial_response
    usage_payload = {"input_tokens": 0, "output_tokens": 0}
    block_index = 0
    final_stop_reason = "end_turn"
    metrics_prompt_tokens = 0
    metrics_completion_tokens = 0
    metrics_has_prompt_tokens = False
    metrics_has_completion_tokens = False
    metrics_text_parts: list[str] = []

    max_internal_rounds = max(WEBSEARCH_INTERNAL_MAX_ROUNDS, TOOL_REPAIR_MAX_ROUNDS, EMPTY_OUTPUT_REPAIR_MAX_ROUNDS)
    for round_index in range(max_internal_rounds + 1):
        thinking_open = False
        thinking_parts: list[str] = []
        thinking_index: int | None = None
        text_open = False
        text_index: int | None = None
        text_parts: list[str] = []
        tool_state: dict[int, dict[str, Any]] = {}
        finish_reason = ""
        round_usage: dict[str, Any] = {}

        for raw_line in current_response.iter_lines(decode_unicode=False, chunk_size=STREAM_CHUNK_SIZE):
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
                round_usage = usage
                usage_payload["input_tokens"] = int(usage.get("prompt_tokens") or usage_payload["input_tokens"])
                usage_payload["output_tokens"] += int(usage.get("completion_tokens") or 0)

            reasoning_delta = delta.get("reasoning_content")
            if EXPERIMENTAL_THINKING_BLOCKS and isinstance(reasoning_delta, str) and reasoning_delta:
                if text_open:
                    yield sse_event("content_block_stop", {"type": "content_block_stop", "index": text_index})
                    text_open = False
                    block_index += 1
                if not thinking_open:
                    thinking_open = True
                    thinking_index = block_index
                    yield sse_event(
                        "content_block_start",
                        {
                            "type": "content_block_start",
                            "index": thinking_index,
                            "content_block": {"type": "thinking", "thinking": ""},
                        },
                    )
                thinking_parts.append(reasoning_delta)
                yield sse_event(
                    "content_block_delta",
                    {"type": "content_block_delta", "index": thinking_index, "delta": {"type": "thinking_delta", "thinking": reasoning_delta}},
                )

            text_delta = delta.get("content")
            if isinstance(text_delta, str) and text_delta:
                metrics_text_parts.append(text_delta)
                if thinking_open:
                    signature = fake_thinking_signature("".join(thinking_parts), f"{message_id}:{round_index}:{thinking_index}")
                    yield sse_event(
                        "content_block_delta",
                        {"type": "content_block_delta", "index": thinking_index, "delta": {"type": "signature_delta", "signature": signature}},
                    )
                    yield sse_event("content_block_stop", {"type": "content_block_stop", "index": thinking_index})
                    thinking_open = False
                    block_index += 1
                if not text_open:
                    text_open = True
                    text_index = block_index
                    yield sse_event(
                        "content_block_start",
                        {"type": "content_block_start", "index": text_index, "content_block": {"type": "text", "text": ""}},
                    )
                text_parts.append(text_delta)
                yield sse_event(
                    "content_block_delta",
                    {"type": "content_block_delta", "index": text_index, "delta": {"type": "text_delta", "text": text_delta}},
                )

            tool_deltas = delta.get("tool_calls") or []
            if tool_deltas:
                if thinking_open:
                    signature = fake_thinking_signature("".join(thinking_parts), f"{message_id}:{round_index}:{thinking_index}")
                    yield sse_event(
                        "content_block_delta",
                        {"type": "content_block_delta", "index": thinking_index, "delta": {"type": "signature_delta", "signature": signature}},
                    )
                    yield sse_event("content_block_stop", {"type": "content_block_stop", "index": thinking_index})
                    thinking_open = False
                    block_index += 1
                if text_open:
                    yield sse_event("content_block_stop", {"type": "content_block_stop", "index": text_index})
                    text_open = False
                    block_index += 1

            for tool_delta in tool_deltas:
                try:
                    index = int(tool_delta.get("index", 0))
                except Exception:
                    index = 0
                state = tool_state.setdefault(
                    index,
                    {
                        "id": str(tool_delta.get("id") or f"call_{uuid.uuid4().hex[:10]}"),
                        "name": "",
                        "arguments": [],
                    },
                )
                if tool_delta.get("id"):
                    state["id"] = str(tool_delta["id"])
                function = tool_delta.get("function") or {}
                if function.get("name"):
                    state["name"] = str(function["name"])
                if function.get("arguments") is not None:
                    state["arguments"].append(str(function.get("arguments") or ""))

            if choice.get("finish_reason"):
                finish_reason = str(choice.get("finish_reason") or "")

        if round_usage:
            prompt_value, prompt_exact = first_positive_int(round_usage.get("prompt_tokens"), round_usage.get("input_tokens"))
            completion_value, completion_exact = first_positive_int(round_usage.get("completion_tokens"), round_usage.get("output_tokens"))
            if prompt_exact:
                metrics_prompt_tokens += prompt_value
                metrics_has_prompt_tokens = True
            if completion_exact:
                metrics_completion_tokens += completion_value
                metrics_has_completion_tokens = True

        if thinking_open:
            signature = fake_thinking_signature("".join(thinking_parts), f"{message_id}:{round_index}:{thinking_index}")
            yield sse_event(
                "content_block_delta",
                {"type": "content_block_delta", "index": thinking_index, "delta": {"type": "signature_delta", "signature": signature}},
            )
            yield sse_event("content_block_stop", {"type": "content_block_stop", "index": thinking_index})
            block_index += 1
        if text_open:
            yield sse_event("content_block_stop", {"type": "content_block_stop", "index": text_index})
            block_index += 1

        stream_tool_calls = openai_tool_calls_from_stream_state(tool_state)
        invalids = invalid_tool_calls(stream_tool_calls, current_payload)
        if finish_reason == "tool_calls" and invalids:
            assistant_message = {
                "role": "assistant",
                "content": "".join(text_parts),
                "tool_calls": stream_tool_calls,
            }
            data = {"choices": [{"finish_reason": "tool_calls", "message": assistant_message}]}
            if round_index < TOOL_REPAIR_MAX_ROUNDS:
                current_payload = append_invalid_tool_results(current_payload, data, invalids)
                current_payload["stream"] = True
                input_tokens = estimate_openai_tokens(current_payload)
                current_response = proxy_openai_chat_with_context_retry(
                    current_payload,
                    alias=alias,
                    stream=True,
                    context_window=context_window,
                    input_tokens=input_tokens,
                )
                if current_response.status_code >= 400:
                    final_stop_reason = "end_turn"
                    break
                continue
            warning = "A chamada de ferramenta veio invalida repetidas vezes e foi bloqueada pelo proxy para evitar loop."
            metrics_text_parts.append(warning)
            yield sse_event(
                "content_block_start",
                {"type": "content_block_start", "index": block_index, "content_block": {"type": "text", "text": ""}},
            )
            yield sse_event(
                "content_block_delta",
                {"type": "content_block_delta", "index": block_index, "delta": {"type": "text_delta", "text": warning}},
            )
            yield sse_event("content_block_stop", {"type": "content_block_stop", "index": block_index})
            final_stop_reason = "end_turn"
            break

        internal_calls = internal_calls_from_stream_tool_state(tool_state)
        if finish_reason == "tool_calls" and internal_calls and round_index < WEBSEARCH_INTERNAL_MAX_ROUNDS:
            assistant_message = {
                "role": "assistant",
                "content": "".join(text_parts),
                    "tool_calls": stream_tool_calls,
            }
            data = {"choices": [{"finish_reason": "tool_calls", "message": assistant_message}]}
            current_payload = append_internal_tool_results(current_payload, data, internal_calls)
            current_payload["stream"] = True
            input_tokens = estimate_openai_tokens(current_payload)
            print(f"[redalibabaclaude] internal-tool-repair round={round_index + 1} calls={len(internal_calls)}", flush=True)
            current_response = proxy_openai_chat_with_context_retry(
                current_payload,
                alias=alias,
                stream=True,
                context_window=context_window,
                input_tokens=input_tokens,
            )
            if current_response.status_code >= 400:
                warning = empty_output_warning_text(current_response.status_code)
                metrics_text_parts.append(warning)
                yield sse_event(
                    "content_block_start",
                    {"type": "content_block_start", "index": block_index, "content_block": {"type": "text", "text": ""}},
                )
                yield sse_event(
                    "content_block_delta",
                    {"type": "content_block_delta", "index": block_index, "delta": {"type": "text_delta", "text": warning}},
                )
                yield sse_event("content_block_stop", {"type": "content_block_stop", "index": block_index})
                final_stop_reason = "end_turn"
                break
            continue

        if finish_reason == "tool_calls" and tool_state:
            for offset, tool_call in enumerate(stream_tool_calls):
                function = tool_call.get("function") or {}
                arguments = function.get("arguments") or "{}"
                yield sse_event(
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": block_index + offset,
                        "content_block": {
                            "type": "tool_use",
                            "id": tool_call.get("id") or f"toolu_{uuid.uuid4().hex[:10]}",
                            "name": function.get("name") or "",
                            "input": {},
                        },
                    },
                )
                if arguments:
                    yield sse_event(
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": block_index + offset,
                            "delta": {"type": "input_json_delta", "partial_json": arguments},
                        },
                    )
                yield sse_event("content_block_stop", {"type": "content_block_stop", "index": block_index + offset})
            final_stop_reason = "tool_use"
            break

        visible_text = "".join(text_parts).strip()
        empty_visible_output = not visible_text and not tool_state and finish_reason != "length"
        if empty_visible_output:
            if round_index < EMPTY_OUTPUT_REPAIR_MAX_ROUNDS:
                current_payload = append_empty_output_repair(current_payload)
                current_payload["stream"] = True
                input_tokens = estimate_openai_tokens(current_payload)
                print(f"[redalibabaclaude] empty-output-repair round={round_index + 1} finish_reason={finish_reason or 'none'}", flush=True)
                current_response = proxy_openai_chat_with_context_retry(
                    current_payload,
                    alias=alias,
                    stream=True,
                    context_window=context_window,
                    input_tokens=input_tokens,
                )
                if current_response.status_code >= 400:
                    warning = empty_output_warning_text(current_response.status_code)
                    metrics_text_parts.append(warning)
                    yield sse_event(
                        "content_block_start",
                        {"type": "content_block_start", "index": block_index, "content_block": {"type": "text", "text": ""}},
                    )
                    yield sse_event(
                        "content_block_delta",
                        {"type": "content_block_delta", "index": block_index, "delta": {"type": "text_delta", "text": warning}},
                    )
                    yield sse_event("content_block_stop", {"type": "content_block_stop", "index": block_index})
                    final_stop_reason = "end_turn"
                    break
                continue
            warning = empty_output_warning_text()
            metrics_text_parts.append(warning)
            yield sse_event(
                "content_block_start",
                {"type": "content_block_start", "index": block_index, "content_block": {"type": "text", "text": ""}},
            )
            yield sse_event(
                "content_block_delta",
                {"type": "content_block_delta", "index": block_index, "delta": {"type": "text_delta", "text": warning}},
            )
            yield sse_event("content_block_stop", {"type": "content_block_stop", "index": block_index})
            final_stop_reason = "end_turn"
            break

        todo_only_completion = not tool_state and finish_reason != "length" and should_retry_todo_only_completion(current_payload, visible_text)
        if todo_only_completion:
            if round_index < TODO_ONLY_REPAIR_MAX_ROUNDS:
                current_payload = append_todo_only_repair(current_payload, "".join(text_parts))
                current_payload["stream"] = True
                input_tokens = estimate_openai_tokens(current_payload)
                print(f"[redalibabaclaude] todo-only-repair round={round_index + 1}", flush=True)
                current_response = proxy_openai_chat_with_context_retry(
                    current_payload,
                    alias=alias,
                    stream=True,
                    context_window=context_window,
                    input_tokens=input_tokens,
                )
                if current_response.status_code >= 400:
                    warning = todo_only_warning_text(current_response.status_code)
                    metrics_text_parts.append(warning)
                    yield sse_event(
                        "content_block_start",
                        {"type": "content_block_start", "index": block_index, "content_block": {"type": "text", "text": ""}},
                    )
                    yield sse_event(
                        "content_block_delta",
                        {"type": "content_block_delta", "index": block_index, "delta": {"type": "text_delta", "text": warning}},
                    )
                    yield sse_event("content_block_stop", {"type": "content_block_stop", "index": block_index})
                    final_stop_reason = "end_turn"
                    break
                continue
            warning = todo_only_warning_text()
            metrics_text_parts.append(warning)
            yield sse_event(
                "content_block_start",
                {"type": "content_block_start", "index": block_index, "content_block": {"type": "text", "text": ""}},
            )
            yield sse_event(
                "content_block_delta",
                {"type": "content_block_delta", "index": block_index, "delta": {"type": "text_delta", "text": warning}},
            )
            yield sse_event("content_block_stop", {"type": "content_block_stop", "index": block_index})
            final_stop_reason = "end_turn"
            break

        if finish_reason == "length":
            final_stop_reason = "max_tokens"
        else:
            final_stop_reason = "end_turn"
        break

    metrics_usage: dict[str, Any] = {}
    if metrics_has_prompt_tokens:
        metrics_usage["prompt_tokens"] = metrics_prompt_tokens
    if metrics_has_completion_tokens:
        metrics_usage["completion_tokens"] = metrics_completion_tokens
    record_token_usage(
        metrics,
        usage=metrics_usage,
        status_code=200,
        success=True,
        output_tokens_estimate=estimate_output_tokens_from_text("".join(metrics_text_parts)),
        stop_reason=final_stop_reason,
    )
    yield sse_event("message_delta", {"type": "message_delta", "delta": {"stop_reason": final_stop_reason, "stop_sequence": None}, "usage": usage_payload})
    yield sse_event("message_stop", {"type": "message_stop"})


def anthropic_sse_from_openai_stream(response: requests.Response, model_name: str, metrics: dict[str, Any] | None = None):
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
    thinking_started = False
    thinking_closed = False
    thinking_parts: list[str] = []
    tool_state: dict[int, dict[str, Any]] = {}
    usage_payload = {"input_tokens": 0, "output_tokens": 0}
    stop_reason = "end_turn"
    metrics_text_parts: list[str] = []

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

        reasoning_delta = delta.get("reasoning_content")
        if EXPERIMENTAL_THINKING_BLOCKS and isinstance(reasoning_delta, str) and reasoning_delta:
            if not thinking_started:
                thinking_started = True
                yield sse_event("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": ""}})
            thinking_parts.append(reasoning_delta)
            yield sse_event("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": reasoning_delta}})

        text_delta = delta.get("content")
        if isinstance(text_delta, str) and text_delta:
            metrics_text_parts.append(text_delta)
            if thinking_started and not thinking_closed:
                signature = fake_thinking_signature("".join(thinking_parts), message_id)
                yield sse_event("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": signature}})
                yield sse_event("content_block_stop", {"type": "content_block_stop", "index": 0})
                thinking_closed = True
            if not text_started:
                text_started = True
                text_index = 1 if thinking_started else 0
                yield sse_event("content_block_start", {"type": "content_block_start", "index": text_index, "content_block": {"type": "text", "text": ""}})
            text_index = 1 if thinking_started else 0
            yield sse_event("content_block_delta", {"type": "content_block_delta", "index": text_index, "delta": {"type": "text_delta", "text": text_delta}})

        tool_deltas = delta.get("tool_calls") or []
        if tool_deltas and thinking_started and not thinking_closed:
            signature = fake_thinking_signature("".join(thinking_parts), message_id)
            yield sse_event("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": signature}})
            yield sse_event("content_block_stop", {"type": "content_block_stop", "index": 0})
            thinking_closed = True

        for tool_delta in tool_deltas:
            try:
                index = int(tool_delta.get("index", 0))
            except Exception:
                index = 0
            block_index = index + (1 if text_started else 0) + (1 if thinking_started else 0)
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

    if thinking_started and not thinking_closed:
        signature = fake_thinking_signature("".join(thinking_parts), message_id)
        yield sse_event("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": signature}})
        yield sse_event("content_block_stop", {"type": "content_block_stop", "index": 0})
        thinking_closed = True
    if text_started and not text_closed:
        text_index = 1 if thinking_started else 0
        yield sse_event("content_block_stop", {"type": "content_block_stop", "index": text_index})
        text_closed = True
    for index in sorted(tool_state):
        block_index = index + (1 if text_started else 0) + (1 if thinking_started else 0)
        yield sse_event("content_block_stop", {"type": "content_block_stop", "index": block_index})

    record_token_usage(
        metrics,
        usage=usage_payload,
        status_code=200,
        success=True,
        output_tokens_estimate=estimate_output_tokens_from_text("".join(metrics_text_parts)),
        stop_reason=stop_reason,
    )
    yield sse_event("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None}, "usage": usage_payload})
    yield sse_event("message_stop", {"type": "message_stop"})


def anthropic_sse_from_openai_json(data: dict[str, Any], model_name: str):
    message = anthropic_message_from_openai(data, model_name)
    message_start = deepcopy(message)
    message_start["content"] = []
    message_start["stop_reason"] = None
    yield sse_event("message_start", {"type": "message_start", "message": message_start})
    for index, block in enumerate(message.get("content") or []):
        block_type = block.get("type")
        if block_type == "thinking":
            thinking = str(block.get("thinking") or "")
            yield sse_event(
                "content_block_start",
                {"type": "content_block_start", "index": index, "content_block": {"type": "thinking", "thinking": ""}},
            )
            if thinking:
                yield sse_event(
                    "content_block_delta",
                    {"type": "content_block_delta", "index": index, "delta": {"type": "thinking_delta", "thinking": thinking}},
                )
            signature = str(block.get("signature") or fake_thinking_signature(thinking, message.get("id") or ""))
            yield sse_event(
                "content_block_delta",
                {"type": "content_block_delta", "index": index, "delta": {"type": "signature_delta", "signature": signature}},
            )
            yield sse_event("content_block_stop", {"type": "content_block_stop", "index": index})
        elif block_type == "text":
            yield sse_event("content_block_start", {"type": "content_block_start", "index": index, "content_block": {"type": "text", "text": ""}})
            text = str(block.get("text") or "")
            if text:
                yield sse_event("content_block_delta", {"type": "content_block_delta", "index": index, "delta": {"type": "text_delta", "text": text}})
            yield sse_event("content_block_stop", {"type": "content_block_stop", "index": index})
        elif block_type == "tool_use":
            start_block = {
                "type": "tool_use",
                "id": block.get("id") or f"toolu_{uuid.uuid4().hex[:10]}",
                "name": block.get("name") or "",
                "input": {},
            }
            yield sse_event("content_block_start", {"type": "content_block_start", "index": index, "content_block": start_block})
            tool_input = block.get("input")
            if tool_input is not None:
                yield sse_event(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": index,
                        "delta": {"type": "input_json_delta", "partial_json": json.dumps(tool_input, ensure_ascii=False)},
                    },
                )
            yield sse_event("content_block_stop", {"type": "content_block_stop", "index": index})
    yield sse_event(
        "message_delta",
        {
            "type": "message_delta",
            "delta": {"stop_reason": message.get("stop_reason") or "end_turn", "stop_sequence": None},
            "usage": message.get("usage") or {"input_tokens": 0, "output_tokens": 0},
        },
    )
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
            "backend": alias["backend"],
            "target": alias["target"],
            "kind": alias["kind"],
            "capabilities": alias["capabilities"],
            "tool_call_tested": bool(alias.get("tool_call_tested")),
        },
    }


def sanitize_openai_message(message: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(message)
    cleaned.pop("reasoning_content", None)
    return cleaned


def sanitize_openai_response_json(data: dict[str, Any]) -> dict[str, Any]:
    cleaned = deepcopy(data)
    for choice in cleaned.get("choices") or []:
        if isinstance(choice, dict) and isinstance(choice.get("message"), dict):
            choice["message"] = sanitize_openai_message(choice["message"])
    return cleaned


def sanitized_openai_stream_chunks(response: requests.Response, metrics: dict[str, Any] | None = None):
    usage_payload: dict[str, Any] = {}
    text_parts: list[str] = []
    finish_reason = ""
    recorded = False
    for raw_line in response.iter_lines(decode_unicode=False, chunk_size=STREAM_CHUNK_SIZE):
        if not raw_line:
            continue
        line = raw_line.decode("utf-8", "replace") if isinstance(raw_line, (bytes, bytearray)) else str(raw_line)
        if not line.startswith("data:"):
            yield f"{line}\n".encode("utf-8")
            continue
        data_text = line[5:].strip()
        if data_text == "[DONE]":
            record_token_usage(
                metrics,
                usage=usage_payload,
                status_code=200,
                success=True,
                output_tokens_estimate=estimate_output_tokens_from_text("".join(text_parts)),
                stop_reason=finish_reason,
            )
            recorded = True
            yield b"data: [DONE]\n\n"
            continue
        try:
            data = json.loads(data_text)
        except Exception:
            yield f"{line}\n".encode("utf-8")
            continue
        usage = data.get("usage") or {}
        if usage:
            usage_payload = usage
        changed = False
        for choice in data.get("choices") or []:
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta")
            if isinstance(delta, dict) and isinstance(delta.get("content"), str):
                text_parts.append(delta.get("content") or "")
            if choice.get("finish_reason"):
                finish_reason = str(choice.get("finish_reason") or "")
            if isinstance(delta, dict) and "reasoning_content" in delta:
                delta = dict(delta)
                delta.pop("reasoning_content", None)
                if not delta:
                    choice["delta"] = {}
                else:
                    choice["delta"] = delta
                changed = True
        if changed:
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")
        else:
            yield f"{line}\n\n".encode("utf-8")
    if not recorded:
        record_token_usage(
            metrics,
            usage=usage_payload,
            status_code=200,
            success=True,
            output_tokens_estimate=estimate_output_tokens_from_text("".join(text_parts)),
            stop_reason=finish_reason,
        )


@app.after_request
def add_cors_headers(response: Response) -> Response:
    response.headers.setdefault("Access-Control-Allow-Origin", "*")
    response.headers.setdefault("Access-Control-Allow-Headers", "Authorization, Content-Type, Accept, Anthropic-Version, Anthropic-Beta")
    response.headers.setdefault("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    response.headers.setdefault("X-Request-Id", request_id())
    return response


@app.route("/", methods=["GET"])
def root() -> Response:
    return response_json(
        {
            "service": SERVICE_NAME,
            "ok": True,
            "endpoints": [
                "/healthz",
                "/admin/tokens",
                "/v1/models",
                "/v1/messages",
                "/v1/messages/count_tokens",
                "/v1/chat/completions",
            ],
        }
    )


@app.route("/healthz", methods=["GET"])
def healthz() -> Response:
    return response_json(
        {
            "status": "ok",
            "service": SERVICE_NAME,
            "models": len(MODELS),
            "backends": {
                backend_id: {
                    "base_url": cfg["base_url"],
                    "configured_keys": len(cfg["keys"]),
                }
                for backend_id, cfg in BACKENDS.items()
            },
        }
    )


@app.route("/admin/tokens", methods=["GET"])
def admin_tokens() -> Response:
    auth_error = authorize()
    if auth_error is not None:
        return auth_error
    limit = max(10, min(safe_int(request.args.get("limit"), TOKEN_METRICS_RECENT_LIMIT), 500))
    payload = token_metrics_store.summary(recent_limit=limit)
    payload["service"] = SERVICE_NAME
    payload["now"] = time.time()
    return response_json(payload)


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
        return error_response("model not available in redalibabaclaude", 404, "model_not_found")
    return response_json({"input_tokens": estimate_tokens(body)})


@app.route("/v1/messages", methods=["POST"])
def anthropic_messages() -> Response:
    auth_error = authorize()
    if auth_error is not None:
        return auth_error
    body, json_error = parse_json_body()
    if json_error is not None:
        return json_error
    alias = resolve_model(body.get("model"))
    if alias is None:
        return error_response("model not available in redalibabaclaude", 404, "model_not_found")
    input_tokens_estimate = estimate_tokens(body)
    started_at = time.time()
    metrics = metrics_context(
        endpoint="/v1/messages",
        alias=alias,
        stream=bool(body.get("stream")),
        input_tokens_estimate=input_tokens_estimate,
        started_at=started_at,
    )
    if not backend_has_keys(alias):
        record_token_usage(metrics, status_code=503, success=False, error_type="configuration_error")
        return error_response("alibaba api key not configured for this backend", 503, "configuration_error")
    payload = anthropic_to_openai_payload(body, alias)
    stream = bool(body.get("stream"))
    upstream, upstream_stream = proxy_anthropic_payload_with_internal_tools(
        payload,
        alias=alias,
        stream=stream,
        context_window=int(alias.get("context_window") or 262144),
        input_tokens=input_tokens_estimate,
    )
    if upstream.status_code >= 400:
        try:
            body_text = upstream.text
        except Exception:
            body_text = ""
        status_code = 502 if upstream.status_code >= 500 else upstream.status_code
        record_token_usage(metrics, status_code=status_code, success=False, error_type="upstream_error")
        return error_response(alibaba_error_message(upstream.status_code, body_text), status_code, "upstream_error")
    if stream and upstream_stream:
        return Response(
            anthropic_sse_from_openai_stream_with_internal_tools(
                upstream,
                payload=payload,
                alias=alias,
                model_name=alias["id"],
                context_window=int(alias.get("context_window") or 262144),
                input_tokens=input_tokens_estimate,
                metrics=metrics,
            ),
            status=200,
            content_type="text/event-stream; charset=utf-8",
        )
    try:
        data = upstream.json()
    except Exception:
        record_token_usage(metrics, status_code=502, success=False, error_type="upstream_error")
        return error_response("invalid upstream JSON", 502, "upstream_error")
    record_token_usage(
        metrics,
        usage=data.get("usage") or {},
        status_code=200,
        success=True,
        output_tokens_estimate=estimate_output_tokens_from_text(openai_response_text(data)),
        stop_reason=openai_stop_reason(data),
    )
    if stream:
        return Response(anthropic_sse_from_openai_json(data, alias["id"]), status=200, content_type="text/event-stream; charset=utf-8")
    return response_json(anthropic_message_from_openai(data, alias["id"]))


@app.route("/v1/chat/completions", methods=["POST"])
def openai_chat_completions() -> Response:
    auth_error = authorize()
    if auth_error is not None:
        return auth_error
    body, json_error = parse_json_body()
    if json_error is not None:
        return json_error
    alias = resolve_model(body.get("model"))
    if alias is None:
        return error_response("model not available in redalibabaclaude", 404, "model_not_found")
    payload = deepcopy(body)
    stream = bool(payload.get("stream"))
    input_tokens_estimate = estimate_openai_tokens(payload)
    metrics = metrics_context(
        endpoint="/v1/chat/completions",
        alias=alias,
        stream=stream,
        input_tokens_estimate=input_tokens_estimate,
        started_at=time.time(),
    )
    if not backend_has_keys(alias):
        record_token_usage(metrics, status_code=503, success=False, error_type="configuration_error")
        return error_response("alibaba api key not configured for this backend", 503, "configuration_error")
    upstream = proxy_openai_chat_with_context_retry(
        payload,
        alias=alias,
        stream=stream,
        context_window=int(alias.get("context_window") or 262144),
        input_tokens=input_tokens_estimate,
    )
    if upstream.status_code >= 400:
        try:
            body_text = upstream.text
        except Exception:
            body_text = ""
        status_code = 502 if upstream.status_code >= 500 else upstream.status_code
        record_token_usage(metrics, status_code=status_code, success=False, error_type="upstream_error")
        return error_response(alibaba_error_message(upstream.status_code, body_text), status_code, "upstream_error")
    if not stream:
        try:
            data = upstream.json()
        except Exception:
            record_token_usage(metrics, status_code=502, success=False, error_type="upstream_error")
            return error_response("invalid upstream JSON", 502, "upstream_error")
        record_token_usage(
            metrics,
            usage=data.get("usage") or {},
            status_code=200,
            success=True,
            output_tokens_estimate=estimate_output_tokens_from_text(openai_response_text(data)),
            stop_reason=openai_stop_reason(data),
        )
        return Response(json.dumps(sanitize_openai_response_json(data), ensure_ascii=False), status=200, content_type="application/json")
    return Response(sanitized_openai_stream_chunks(upstream, metrics=metrics), status=200, content_type="text/event-stream; charset=utf-8")


@app.route("/<path:path>", methods=["OPTIONS"])
def options_passthrough(path: str) -> Response:
    return Response("", status=204)


if __name__ == "__main__":
    ssl_context = None
    if TLS_CERT and TLS_KEY and os.path.exists(TLS_CERT) and os.path.exists(TLS_KEY):
        ssl_context = (TLS_CERT, TLS_KEY)
    app.run(host=HOST, port=PORT, threaded=True, ssl_context=ssl_context)
