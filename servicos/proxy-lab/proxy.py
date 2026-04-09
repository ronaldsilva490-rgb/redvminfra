from __future__ import annotations

import json
import os
import random
import time
import uuid
from copy import deepcopy
from dataclasses import dataclass
from threading import Lock, Thread
from typing import Any

import requests
from flask import Flask, Response, jsonify, request


app = Flask(__name__)


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def env_int(name: str, default: int) -> int:
    try:
        return int(env(name, str(default)) or default)
    except Exception:
        return default


DATA_DIR = env("RED_LAB_PROXY_DATA_DIR", "/app/data")
LOGS_FILE = os.path.join(DATA_DIR, "proxy-lab.log")
LOG_MAX_BYTES = 5 * 1024 * 1024
PROXY_HOST = env("RED_LAB_PROXY_HOST", "127.0.0.1")
PROXY_PORT = env_int("RED_LAB_PROXY_PORT", 8090)
MAX_RETRIES = env_int("RED_LAB_PROXY_MAX_RETRIES", 2)
DEFAULT_TIMEOUT_SECONDS = float(env("RED_LAB_PROXY_TIMEOUT_SECONDS", "45"))
DISCOVERY_FILE = os.path.join(DATA_DIR, "discovered_models.json")
ENABLE_AUTODISCOVERY = env("RED_LAB_PROXY_AUTODISCOVER", "true").lower() not in {"0", "false", "no"}

os.makedirs(DATA_DIR, exist_ok=True)

http_session = requests.Session()
http_session.headers.update({"Accept": "application/json"})


DEFAULT_GROQ_MODELS = [
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "qwen/qwen3-32b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]

DEFAULT_MISTRAL_MODELS = [
    "mistral-small-latest",
    "mistral-medium-latest",
    "mistral-large-latest",
    "ministral-8b-latest",
    "ministral-3b-latest",
]


@dataclass(frozen=True)
class ProviderSpec:
    key: str
    display: str
    suffix: str
    base_url: str
    keys_file: str
    timeout_seconds: float
    default_models: list[str]


PROVIDERS: dict[str, ProviderSpec] = {
    "groq": ProviderSpec(
        key="groq",
        display="Groq",
        suffix=" (GROQ)",
        base_url=env("RED_LAB_GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/"),
        keys_file=env("RED_LAB_GROQ_KEYS_FILE", os.path.join(DATA_DIR, "groq_keys.json")),
        timeout_seconds=float(env("RED_LAB_GROQ_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))),
        default_models=[
            item.strip()
            for item in env("RED_LAB_GROQ_MODELS", ",".join(DEFAULT_GROQ_MODELS)).split(",")
            if item.strip()
        ],
    ),
    "mistral": ProviderSpec(
        key="mistral",
        display="Mistral",
        suffix=" (MISTRAL)",
        base_url=env("RED_LAB_MISTRAL_BASE_URL", "https://api.mistral.ai/v1").rstrip("/"),
        keys_file=env("RED_LAB_MISTRAL_KEYS_FILE", os.path.join(DATA_DIR, "mistral_keys.json")),
        timeout_seconds=float(env("RED_LAB_MISTRAL_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))),
        default_models=[
            item.strip()
            for item in env("RED_LAB_MISTRAL_MODELS", ",".join(DEFAULT_MISTRAL_MODELS)).split(",")
            if item.strip()
        ],
    ),
}


def utc_created_at() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime())


def rotate_log_if_needed() -> None:
    try:
        if os.path.exists(LOGS_FILE) and os.path.getsize(LOGS_FILE) > LOG_MAX_BYTES:
            backup = LOGS_FILE + ".1"
            if os.path.exists(backup):
                os.remove(backup)
            os.rename(LOGS_FILE, backup)
    except Exception:
        pass


def log_message(level: str, message: str, provider: str = "N/A", key_id: str = "N/A", endpoint: str = "N/A", latency: float = 0.0, status_code: int = 0) -> None:
    line = json.dumps(
        {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "level": level,
            "provider": provider,
            "key_id": key_id,
            "endpoint": endpoint,
            "latency_ms": int(latency * 1000),
            "status": status_code,
            "message": message,
        },
        ensure_ascii=False,
    )
    try:
        rotate_log_if_needed()
        with open(LOGS_FILE, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        pass


class KeyPool:
    def __init__(self, provider: ProviderSpec):
        self.provider = provider
        self._lock = Lock()
        self._keys: list[dict[str, Any]] = []
        self._file_mtime = 0.0
        self._dirty = False
        self._load_from_disk()
        thread = Thread(target=self._flush_loop, daemon=True)
        thread.start()

    def _normalize_entry(self, entry: Any, index: int) -> dict[str, Any] | None:
        if isinstance(entry, str):
            entry = {"key": entry}
        if not isinstance(entry, dict):
            return None
        api_key = str(entry.get("key", "")).strip()
        if not api_key:
            return None
        return {
            "id": str(entry.get("id") or f"{self.provider.key}-{index + 1}"),
            "key": api_key,
            "active": bool(entry.get("active", True)),
            "total_requests": int(entry.get("total_requests", 0) or 0),
            "successes": int(entry.get("successes", 0) or 0),
            "failures": int(entry.get("failures", 0) or 0),
            "cooldown_until": float(entry.get("cooldown_until", 0) or 0),
            "last_error": str(entry.get("last_error", "")),
            "label": str(entry.get("label", "")),
        }

    def _load_from_disk(self) -> None:
        os.makedirs(os.path.dirname(self.provider.keys_file), exist_ok=True)
        if not os.path.exists(self.provider.keys_file):
            self._keys = []
            self._file_mtime = 0.0
            return
        try:
            with open(self.provider.keys_file, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, dict):
                payload = payload.get("keys", [])
            normalized = []
            for index, entry in enumerate(payload if isinstance(payload, list) else []):
                item = self._normalize_entry(entry, index)
                if item:
                    normalized.append(item)
            self._keys = normalized
            self._file_mtime = os.path.getmtime(self.provider.keys_file)
            log_message("INFO", f"Carregadas {len(self._keys)} keys", self.provider.key)
        except Exception as exc:
            log_message("ERROR", f"Falha ao carregar keys: {exc!r}", self.provider.key)
            self._keys = []

    def _save_to_disk(self) -> None:
        os.makedirs(os.path.dirname(self.provider.keys_file), exist_ok=True)
        with open(self.provider.keys_file, "w", encoding="utf-8") as handle:
            json.dump({"keys": self._keys}, handle, ensure_ascii=False, indent=2)
        self._file_mtime = os.path.getmtime(self.provider.keys_file)
        self._dirty = False

    def _check_reload(self) -> None:
        if not os.path.exists(self.provider.keys_file):
            return
        try:
            current_mtime = os.path.getmtime(self.provider.keys_file)
        except Exception:
            return
        if current_mtime > self._file_mtime:
            self._load_from_disk()

    def _flush_loop(self) -> None:
        while True:
            time.sleep(30)
            with self._lock:
                if self._dirty:
                    try:
                        self._save_to_disk()
                    except Exception:
                        pass

    def force_reload(self) -> None:
        with self._lock:
            self._load_from_disk()

    def get_stats(self) -> list[dict[str, Any]]:
        with self._lock:
            self._check_reload()
            return deepcopy(self._keys)

    def get_key(self) -> tuple[str | None, str | None]:
        with self._lock:
            self._check_reload()
            now = time.time()
            available = [item for item in self._keys if item.get("active") and now > item.get("cooldown_until", 0)]
            if not available:
                for item in self._keys:
                    if item.get("active"):
                        item["cooldown_until"] = 0
                available = [item for item in self._keys if item.get("active")]
            if not available:
                return None, None
            item = random.choice(available)
            item["total_requests"] = int(item.get("total_requests", 0) or 0) + 1
            self._dirty = True
            return item["id"], item["key"]

    def report_success(self, key_id: str) -> None:
        with self._lock:
            for item in self._keys:
                if item["id"] == key_id:
                    item["successes"] = int(item.get("successes", 0) or 0) + 1
                    item["failures"] = 0
                    item["last_error"] = ""
                    self._dirty = True
                    break

    def report_failure(self, key_id: str, *, is_rate_limit: bool, error_text: str = "") -> None:
        with self._lock:
            for item in self._keys:
                if item["id"] == key_id:
                    item["failures"] = int(item.get("failures", 0) or 0) + 1
                    item["cooldown_until"] = time.time() + (60 if is_rate_limit else 15)
                    item["last_error"] = error_text[:240]
                    self._dirty = True
                    break


class ModelRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._discovered: dict[str, list[str]] = {provider_key: [] for provider_key in PROVIDERS}
        self._load_discovered()

    def _load_discovered(self) -> None:
        if not os.path.exists(DISCOVERY_FILE):
            return
        try:
            with open(DISCOVERY_FILE, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, dict):
                for provider_key in PROVIDERS:
                    models = payload.get(provider_key)
                    if isinstance(models, list):
                        self._discovered[provider_key] = [str(item).strip() for item in models if str(item).strip()]
        except Exception as exc:
            log_message("WARN", f"Falha ao carregar modelos descobertos: {exc!r}", "registry")

    def _save_discovered(self) -> None:
        with open(DISCOVERY_FILE, "w", encoding="utf-8") as handle:
            json.dump(self._discovered, handle, ensure_ascii=False, indent=2)

    def refresh_from_providers(self, pools: dict[str, KeyPool]) -> dict[str, Any]:
        refreshed: dict[str, Any] = {}
        with self._lock:
            for provider_key, provider in PROVIDERS.items():
                models = []
                pool = pools[provider_key]
                key_id, api_key = pool.get_key()
                if not api_key:
                    refreshed[provider_key] = {"status": "skipped", "reason": "sem key ativa"}
                    continue
                start = time.time()
                try:
                    response = http_session.get(
                        provider.base_url + "/models",
                        headers={"Authorization": "Bearer " + api_key},
                        timeout=provider.timeout_seconds,
                    )
                    latency = time.time() - start
                    if response.status_code == 200:
                        payload = response.json()
                        for item in payload.get("data", []):
                            model_id = str(item.get("id", "")).strip()
                            if model_id:
                                models.append(model_id)
                        models = sorted(set(models))
                        self._discovered[provider_key] = models
                        self._save_discovered()
                        pool.report_success(key_id)
                        refreshed[provider_key] = {"status": "ok", "count": len(models)}
                        log_message("INFO", f"Discovery OK ({len(models)} modelos)", provider_key, key_id, "/models", latency, 200)
                    else:
                        text = response.text[:180]
                        pool.report_failure(key_id, is_rate_limit=response.status_code == 429, error_text=text)
                        refreshed[provider_key] = {"status": "error", "http_status": response.status_code, "body": text}
                        log_message("WARN", f"Discovery falhou ({response.status_code})", provider_key, key_id, "/models", latency, response.status_code)
                except Exception as exc:
                    latency = time.time() - start
                    pool.report_failure(key_id, is_rate_limit=False, error_text=repr(exc))
                    refreshed[provider_key] = {"status": "error", "error": repr(exc)}
                    log_message("ERROR", f"Discovery exception: {exc!r}", provider_key, key_id, "/models", latency, 0)
            return refreshed

    def list_models(self) -> list[dict[str, Any]]:
        with self._lock:
            items: list[dict[str, Any]] = []
            for provider_key, provider in PROVIDERS.items():
                candidates = self._discovered.get(provider_key) or provider.default_models
                seen: set[str] = set()
                for model_id in candidates:
                    clean = str(model_id).strip()
                    if not clean or clean.lower() in seen:
                        continue
                    seen.add(clean.lower())
                    items.append(
                        {
                            "provider": provider_key,
                            "id": clean,
                            "name": clean + provider.suffix,
                            "suffix": provider.suffix,
                            "base_url": provider.base_url,
                        }
                    )
            items.sort(key=lambda item: item["name"].lower())
            return items


key_pools = {provider_key: KeyPool(provider) for provider_key, provider in PROVIDERS.items()}
model_registry = ModelRegistry()

if ENABLE_AUTODISCOVERY:
    try:
        model_registry.refresh_from_providers(key_pools)
    except Exception:
        pass


def summarize_keys(keys: list[dict[str, Any]]) -> dict[str, Any]:
    now = time.time()
    return {
        "total": len(keys),
        "active": sum(1 for item in keys if item.get("active")),
        "cooldown": sum(1 for item in keys if item.get("cooldown_until", 0) > now),
        "total_requests": sum(int(item.get("total_requests", 0) or 0) for item in keys),
        "successes": sum(int(item.get("successes", 0) or 0) for item in keys),
        "failures": sum(int(item.get("failures", 0) or 0) for item in keys),
    }


def normalize_model_name(raw_name: str | None) -> tuple[ProviderSpec | None, str | None]:
    if not raw_name:
        return None, None
    raw = raw_name.strip()
    all_models = model_registry.list_models()
    for item in all_models:
        if raw.lower() == item["name"].lower():
            return PROVIDERS[item["provider"]], item["id"]
    exact_matches = [item for item in all_models if raw.lower() == item["id"].lower()]
    if len(exact_matches) == 1:
        item = exact_matches[0]
        return PROVIDERS[item["provider"]], item["id"]
    return None, None


def provider_model_info(provider: ProviderSpec, model_id: str) -> dict[str, Any]:
    name = model_id + provider.suffix
    return {
        "name": name,
        "model": name,
        "modified_at": utc_created_at(),
        "size": 0,
        "digest": f"{provider.key}-{uuid.uuid5(uuid.NAMESPACE_URL, provider.key + ':' + model_id).hex}",
        "details": {
            "parent_model": "",
            "format": provider.key,
            "family": provider.key,
            "families": [provider.key],
            "parameter_size": "",
            "quantization_level": "",
        },
    }


def extract_error_text(response: requests.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                message = error.get("message")
                if message:
                    return str(message)
            if error:
                return str(error)
            message = payload.get("message")
            if message:
                return str(message)
    except Exception:
        pass
    return response.text[:240]


def proxy_to_provider(provider: ProviderSpec, path: str, payload: dict[str, Any], *, stream: bool) -> tuple[requests.Response | None, str | None, str | None, float, Response | None]:
    pool = key_pools[provider.key]
    last_error = None
    last_key_id = None
    last_latency = 0.0
    for attempt in range(MAX_RETRIES + 1):
        key_id, api_key = pool.get_key()
        if not api_key:
            return None, None, None, 0.0, (jsonify({"error": f"nenhuma key ativa para {provider.display}"}), 503)
        start = time.time()
        try:
            response = http_session.post(
                provider.base_url + path,
                headers={
                    "Authorization": "Bearer " + api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
                stream=stream,
                timeout=provider.timeout_seconds,
            )
            latency = time.time() - start
            last_key_id = key_id
            last_latency = latency
            if response.status_code == 429 and attempt < MAX_RETRIES:
                pool.report_failure(key_id, is_rate_limit=True, error_text=extract_error_text(response))
                log_message("WARN", f"429 -> retry {attempt + 1}", provider.key, key_id, path, latency, 429)
                continue
            if response.status_code >= 500 and attempt < MAX_RETRIES:
                pool.report_failure(key_id, is_rate_limit=False, error_text=extract_error_text(response))
                log_message("WARN", f"{response.status_code} -> retry {attempt + 1}", provider.key, key_id, path, latency, response.status_code)
                continue
            if response.status_code < 400:
                pool.report_success(key_id)
            else:
                pool.report_failure(key_id, is_rate_limit=response.status_code == 429, error_text=extract_error_text(response))
            log_message("INFO", f"{path} -> HTTP {response.status_code}", provider.key, key_id, path, latency, response.status_code)
            return response, key_id, api_key, latency, None
        except Exception as exc:
            latency = time.time() - start
            last_error = repr(exc)
            last_key_id = key_id
            last_latency = latency
            pool.report_failure(key_id, is_rate_limit=False, error_text=last_error)
            if attempt < MAX_RETRIES:
                log_message("WARN", f"Exception -> retry {attempt + 1}", provider.key, key_id, path, latency, 0)
                continue
    return None, last_key_id, None, last_latency, (jsonify({"error": last_error or "max retries exceeded"}), 502)


def ollama_messages_from_chat_body(body: dict[str, Any]) -> list[dict[str, Any]]:
    messages = body.get("messages")
    if isinstance(messages, list) and messages:
        return messages
    prompt = body.get("prompt")
    if prompt:
        return [{"role": "user", "content": str(prompt)}]
    return [{"role": "user", "content": ""}]


def build_openai_payload(model_id: str, body: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model_id,
        "messages": ollama_messages_from_chat_body(body),
        "stream": bool(body.get("stream", True)),
    }
    options = body.get("options") if isinstance(body.get("options"), dict) else {}
    if "temperature" in body:
        payload["temperature"] = body["temperature"]
    elif "temperature" in options:
        payload["temperature"] = options["temperature"]
    if "top_p" in body:
        payload["top_p"] = body["top_p"]
    elif "top_p" in options:
        payload["top_p"] = options["top_p"]
    if "max_tokens" in body:
        payload["max_tokens"] = body["max_tokens"]
    elif "num_predict" in body:
        payload["max_tokens"] = body["num_predict"]
    elif "num_predict" in options:
        payload["max_tokens"] = options["num_predict"]
    if "response_format" in body:
        payload["response_format"] = body["response_format"]
    if "format" in body and body["format"] == "json":
        payload["response_format"] = {"type": "json_object"}
    if isinstance(body.get("tools"), list):
        payload["tools"] = body["tools"]
    if body.get("tool_choice") is not None:
        payload["tool_choice"] = body["tool_choice"]
    if body.get("seed") is not None:
        payload["seed"] = body["seed"]
    return payload


def extract_message_content(message: Any) -> str:
    if isinstance(message, str):
        return message
    if isinstance(message, list):
        parts = []
        for item in message:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return "".join(parts)
    if isinstance(message, dict):
        if "content" in message:
            return extract_message_content(message["content"])
    return ""


def openai_json_to_ollama_chat(provider: ProviderSpec, model_id: str, payload: dict[str, Any], latency: float) -> Response:
    choice = (payload.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = extract_message_content(message.get("content"))
    body = {
        "model": model_id + provider.suffix,
        "created_at": utc_created_at(),
        "message": {
            "role": message.get("role", "assistant"),
            "content": content,
        },
        "done_reason": choice.get("finish_reason", "stop"),
        "done": True,
        "total_duration": int(latency * 1_000_000_000),
    }
    return jsonify(body)


def openai_json_to_ollama_generate(provider: ProviderSpec, model_id: str, payload: dict[str, Any], latency: float) -> Response:
    choice = (payload.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = extract_message_content(message.get("content"))
    body = {
        "model": model_id + provider.suffix,
        "created_at": utc_created_at(),
        "response": content,
        "done": True,
        "done_reason": choice.get("finish_reason", "stop"),
        "total_duration": int(latency * 1_000_000_000),
    }
    return jsonify(body)


def sse_to_ollama_ndjson(provider: ProviderSpec, model_id: str, response: requests.Response, *, generate_mode: bool):
    created_at = utc_created_at()
    for raw_line in response.iter_lines(decode_unicode=True):
        if not raw_line:
            continue
        line = raw_line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            final_obj = {
                "model": model_id + provider.suffix,
                "created_at": created_at,
                "done": True,
                "done_reason": "stop",
            }
            if generate_mode:
                final_obj["response"] = ""
            else:
                final_obj["message"] = {"role": "assistant", "content": ""}
            yield json.dumps(final_obj, ensure_ascii=False) + "\n"
            break
        try:
            payload = json.loads(data)
        except Exception:
            continue
        choice = (payload.get("choices") or [{}])[0]
        delta = choice.get("delta") or {}
        content = extract_message_content(delta.get("content", ""))
        if not content and choice.get("finish_reason") is None:
            continue
        item = {
            "model": model_id + provider.suffix,
            "created_at": created_at,
            "done": bool(choice.get("finish_reason")),
            "done_reason": choice.get("finish_reason") or "",
        }
        if generate_mode:
            item["response"] = content
        else:
            item["message"] = {"role": delta.get("role", "assistant"), "content": content}
        yield json.dumps(item, ensure_ascii=False) + "\n"


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok", "service": "proxy-lab", "providers": list(PROVIDERS.keys())})


@app.get("/admin/stats")
def admin_stats():
    payload = {
        "status": "ok",
        "service": "proxy-lab",
        "host": PROXY_HOST,
        "port": PROXY_PORT,
        "providers": {},
        "models": model_registry.list_models(),
    }
    for provider_key, provider in PROVIDERS.items():
        keys = key_pools[provider_key].get_stats()
        payload["providers"][provider_key] = {
            "display": provider.display,
            "base_url": provider.base_url,
            "keys_file": provider.keys_file,
            "summary": summarize_keys(keys),
            "keys": keys,
        }
    return jsonify(payload)


@app.post("/admin/reload")
def admin_reload():
    for pool in key_pools.values():
        pool.force_reload()
    return jsonify({"status": "ok", "message": "keys recarregadas"})


@app.post("/admin/discover-models")
def admin_discover_models():
    payload = model_registry.refresh_from_providers(key_pools)
    return jsonify({"status": "ok", "providers": payload, "models": model_registry.list_models()})


@app.get("/api/tags")
def api_tags():
    return jsonify({"models": [provider_model_info(PROVIDERS[item["provider"]], item["id"]) for item in model_registry.list_models()]})


@app.get("/v1/models")
def v1_models():
    return jsonify(
        {
            "object": "list",
            "data": [
                {
                    "id": item["name"],
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": item["provider"],
                }
                for item in model_registry.list_models()
            ],
        }
    )


@app.post("/api/show")
def api_show():
    body = request.get_json(silent=True) or {}
    raw_model = str(body.get("model") or body.get("name") or "")
    provider, model_id = normalize_model_name(raw_model)
    if not provider or not model_id:
        return jsonify({"error": "modelo do laboratorio nao reconhecido"}), 404
    info = provider_model_info(provider, model_id)
    return jsonify(
        {
            "license": f"{provider.display} routed by RED lab proxy.",
            "modelfile": f"FROM {model_id}\nPARAMETER provider {provider.key}\n",
            "parameters": "",
            "template": "{{ .Prompt }}",
            "details": info["details"],
            "model_info": {
                "red.provider": provider.key,
                "red.model": model_id,
                "red.lab": True,
            },
            "modified_at": info["modified_at"],
        }
    )


@app.post("/api/chat")
def api_chat():
    body = request.get_json(silent=True) or {}
    raw_model = str(body.get("model") or "")
    provider, model_id = normalize_model_name(raw_model)
    if not provider or not model_id:
        return jsonify({"error": "modelo do laboratorio nao reconhecido"}), 404
    payload = build_openai_payload(model_id, body)
    stream = bool(body.get("stream", True))
    response, _key_id, _api_key, latency, error_response = proxy_to_provider(provider, "/chat/completions", payload, stream=stream)
    if error_response:
        return error_response
    if response is None:
        return jsonify({"error": "falha interna"}), 500
    if response.status_code >= 400:
        return Response(response.content, status=response.status_code, content_type=response.headers.get("Content-Type", "application/json"))
    if stream:
        return Response(sse_to_ollama_ndjson(provider, model_id, response, generate_mode=False), content_type="application/x-ndjson")
    return openai_json_to_ollama_chat(provider, model_id, response.json(), latency)


@app.post("/api/generate")
def api_generate():
    body = request.get_json(silent=True) or {}
    raw_model = str(body.get("model") or "")
    provider, model_id = normalize_model_name(raw_model)
    if not provider or not model_id:
        return jsonify({"error": "modelo do laboratorio nao reconhecido"}), 404
    payload = build_openai_payload(model_id, body)
    stream = bool(body.get("stream", True))
    response, _key_id, _api_key, latency, error_response = proxy_to_provider(provider, "/chat/completions", payload, stream=stream)
    if error_response:
        return error_response
    if response is None:
        return jsonify({"error": "falha interna"}), 500
    if response.status_code >= 400:
        return Response(response.content, status=response.status_code, content_type=response.headers.get("Content-Type", "application/json"))
    if stream:
        return Response(sse_to_ollama_ndjson(provider, model_id, response, generate_mode=True), content_type="application/x-ndjson")
    return openai_json_to_ollama_generate(provider, model_id, response.json(), latency)


@app.post("/v1/chat/completions")
def v1_chat_completions():
    body = request.get_json(silent=True) or {}
    raw_model = str(body.get("model") or "")
    provider, model_id = normalize_model_name(raw_model)
    if not provider or not model_id:
        return jsonify({"error": "modelo do laboratorio nao reconhecido"}), 404
    payload = dict(body)
    payload["model"] = model_id
    stream = bool(body.get("stream", False))
    response, _key_id, _api_key, _latency, error_response = proxy_to_provider(provider, "/chat/completions", payload, stream=stream)
    if error_response:
        return error_response
    if response is None:
        return jsonify({"error": "falha interna"}), 500
    headers = {}
    if "Content-Type" in response.headers:
        headers["Content-Type"] = response.headers["Content-Type"]
    if stream:
        def generate():
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk
        return Response(generate(), status=response.status_code, headers=headers)
    try:
        payload = response.json()
        if isinstance(payload, dict):
            payload["model"] = raw_model or (model_id + provider.suffix)
        return jsonify(payload), response.status_code
    except Exception:
        return Response(response.content, status=response.status_code, headers=headers)


if __name__ == "__main__":
    log_message("INFO", "PROXY LAB INICIANDO", "system")
    app.run(host=PROXY_HOST, port=PROXY_PORT, threaded=True)
