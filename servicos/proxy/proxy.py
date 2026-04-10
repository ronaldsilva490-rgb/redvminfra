from flask import Flask, request, Response, jsonify
import requests
import json
import os
import random
import time
import uuid
import base64
from threading import Lock, Thread
from copy import deepcopy

app = Flask(__name__)

DATA_DIR = os.getenv("RED_PROXY_DATA_DIR", "/app/data")
KEYS_FILE = os.path.join(DATA_DIR, "keys.json")
LOGS_FILE = os.path.join(DATA_DIR, "proxy.log")
LOG_MAX_BYTES = 5 * 1024 * 1024  # 5MB - rotaciona o log
OLLAMA_BASE = os.getenv("RED_PROXY_UPSTREAM", "https://ollama.com").rstrip("/")
PROXY_HOST = os.getenv("RED_PROXY_HOST", "127.0.0.1")
PROXY_PORT = int(os.getenv("RED_PROXY_PORT", "8080"))
NVIDIA_API_KEY = os.getenv("RED_PROXY_NVIDIA_API_KEY") or os.getenv("NVIDIA_API_KEY", "")
NVIDIA_CHAT_BASE = os.getenv("RED_PROXY_NVIDIA_CHAT_BASE", "https://integrate.api.nvidia.com/v1").rstrip("/")
NVIDIA_GENAI_BASE = os.getenv("RED_PROXY_NVIDIA_GENAI_BASE", "https://ai.api.nvidia.com/v1/genai").rstrip("/")
NVIDIA_SUFFIX = " (NVIDIA)"
DEFAULT_CHAT_MODEL = (os.getenv("RED_PROXY_DEFAULT_CHAT_MODEL") or "").strip()
DEFAULT_VISION_MODEL = (os.getenv("RED_PROXY_DEFAULT_VISION_MODEL") or "").strip()
DEFAULT_IMAGE_MODEL = (os.getenv("RED_PROXY_DEFAULT_IMAGE_MODEL") or "").strip()
DEFAULT_EMBEDDINGS_MODEL = (os.getenv("RED_PROXY_DEFAULT_EMBEDDINGS_MODEL") or "").strip()
ENABLE_CAPABILITY_FALLBACK = (os.getenv("RED_PROXY_ENABLE_CAPABILITY_FALLBACK", "1").strip().lower() not in ("0", "false", "no", "off"))

os.makedirs(DATA_DIR, exist_ok=True)

# Connection pool - reutiliza conexoes TCP com ollama.com
http_session = requests.Session()
http_session.headers.update({"Accept": "application/json"})


NVIDIA_TEXT_MODELS = [
    {
        "id": "qwen/qwen3-next-80b-a3b-instruct",
        "kind": "chat",
        "family": "nvidia-chat",
        "note": "Melhor default geral para REDIA: contexto, JSON e baixa alucinacao.",
    },
    {
        "id": "meta/llama-4-maverick-17b-128e-instruct",
        "kind": "chat",
        "family": "nvidia-chat",
        "note": "Fallback rapido para papo simples.",
    },
    {
        "id": "openai/gpt-oss-20b",
        "kind": "chat",
        "family": "nvidia-chat",
        "note": "Bom em conversa comum; pode retornar reasoning_content separado.",
    },
    {
        "id": "openai/gpt-oss-120b",
        "kind": "chat",
        "family": "nvidia-chat",
        "note": "Fallback analitico; mais lento e verboso.",
    },
    {
        "id": "mistralai/devstral-2-123b-instruct-2512",
        "kind": "chat",
        "family": "nvidia-chat",
        "note": "Boa nuance em alguns cenarios; observar acentos em PT-BR.",
    },
    {
        "id": "mistralai/mistral-small-4-119b-2603",
        "kind": "chat",
        "family": "nvidia-chat",
        "note": "Muito rapido; nao usar para policy/memoria sem validacao.",
    },
    {
        "id": "nvidia/nemotron-3-nano-30b-a3b",
        "kind": "chat",
        "family": "nvidia-chat",
        "note": "Rapido; pode gastar tokens em reasoning.",
    },
    {
        "id": "qwen/qwen3-coder-480b-a35b-instruct",
        "kind": "chat",
        "family": "nvidia-chat",
        "note": "Coder grande; usar sob demanda.",
    },
    {
        "id": "meta/llama-3.2-90b-vision-instruct",
        "kind": "vision",
        "family": "nvidia-vision",
        "note": "Melhor visao na rodada curta.",
    },
    {
        "id": "meta/llama-3.2-11b-vision-instruct",
        "kind": "vision",
        "family": "nvidia-vision",
        "note": "Visao rapida.",
    },
    {
        "id": "nvidia/nemotron-nano-12b-v2-vl",
        "kind": "vision",
        "family": "nvidia-vision",
        "note": "Visao e avaliador de imagem.",
    },
]


NVIDIA_IMAGE_MODELS = [
    {
        "id": "flux.2-klein-4b",
        "kind": "image",
        "family": "nvidia-image",
        "endpoint": "black-forest-labs/flux.2-klein-4b",
        "schema": "flux2",
        "default_steps": 4,
        "max_steps": 4,
        "default_cfg": None,
        "note": "Melhor geral nos testes de imagem.",
    },
    {
        "id": "flux.1-dev",
        "kind": "image",
        "family": "nvidia-image",
        "endpoint": "black-forest-labs/flux.1-dev",
        "schema": "flux1-dev",
        "default_steps": 8,
        "max_steps": 50,
        "default_cfg": 3,
        "note": "Bom para avatar/arte premium.",
    },
    {
        "id": "flux.1-schnell",
        "kind": "image",
        "family": "nvidia-image",
        "endpoint": "black-forest-labs/flux.1-schnell",
        "schema": "flux1-schnell",
        "default_steps": 4,
        "max_steps": 4,
        "default_cfg": 0,
        "note": "Rascunho rapido.",
    },
    {
        "id": "stable-diffusion-xl",
        "kind": "image",
        "family": "nvidia-image",
        "endpoint": "stabilityai/stable-diffusion-xl",
        "schema": "sdxl",
        "default_steps": 30,
        "max_steps": 50,
        "default_cfg": 6,
        "note": "Classico e estavel.",
    },
    {
        "id": "stable-diffusion-3-medium",
        "kind": "image",
        "family": "nvidia-image",
        "endpoint": "stabilityai/stable-diffusion-3-medium",
        "schema": "sd3",
        "default_steps": 30,
        "max_steps": 50,
        "default_cfg": 5,
        "note": "Alternativa SD3.",
    },
]


NVIDIA_MODELS = NVIDIA_TEXT_MODELS + NVIDIA_IMAGE_MODELS
NVIDIA_MODEL_MAP = {model["id"].lower(): model for model in NVIDIA_MODELS}

# ============ CACHE PARA ENDPOINTS READ-ONLY ============
_cache = {}
_cache_lock = Lock()

CACHEABLE_GETS = {
    "/api/tags": 300,        # 5 min
    "/api/version": 3600,    # 1 hora
}
MODEL_CATALOG_CACHE_KEY = "/__meta/v1/models"


def cache_get(path):
    with _cache_lock:
        entry = _cache.get(path)
        if entry and time.time() < entry["expires"]:
            return entry["body"], entry["content_type"], entry["status"]
    return None, None, None


def cache_set(path, body, content_type, status, ttl):
    with _cache_lock:
        _cache[path] = {
            "body": body,
            "content_type": content_type,
            "status": status,
            "expires": time.time() + ttl,
        }


def cache_stats():
    with _cache_lock:
        now = time.time()
        return {
            "entries": len(_cache),
            "paths": sorted(_cache.keys()),
            "valid_entries": sum(1 for item in _cache.values() if item["expires"] > now),
        }


def utc_created_at():
    return time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime())


def nvidia_display_name(model_id):
    return model_id + NVIDIA_SUFFIX


def extract_model_name(body):
    if not isinstance(body, dict):
        return None
    return body.get("model") or body.get("name")


def normalize_nvidia_model(model_name):
    if not isinstance(model_name, str):
        return None, None
    raw = model_name.strip()
    suffix = NVIDIA_SUFFIX.lower()
    if raw.lower().endswith(suffix):
        model_id = raw[: -len(NVIDIA_SUFFIX)].strip()
        return model_id, NVIDIA_MODEL_MAP.get(model_id.lower())
    model_info = NVIDIA_MODEL_MAP.get(raw.lower())
    if model_info:
        return model_info["id"], model_info
    return None, None


def is_nvidia_request_body(raw_body):
    try:
        body = json.loads(raw_body.decode("utf-8") if isinstance(raw_body, (bytes, bytearray)) else raw_body)
    except Exception:
        return False, None, None
    model_id, model_info = normalize_nvidia_model(extract_model_name(body))
    return model_info is not None, body, model_id


def ordered_unique(values):
    out = []
    seen = set()
    for value in values or []:
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def nvidia_capabilities(model_info):
    kind = model_info.get("kind")
    if kind == "image":
        return ["image_generation"]
    if kind == "vision":
        return ["chat", "vision"]
    return ["chat"]


def infer_upstream_kind_and_capabilities(model_name, item=None):
    lower = str(model_name or "").strip().lower()
    embed_markers = ("embed", "embedding", "nomic-embed", "mxbai", "bge", "gte-", "e5")
    image_markers = ("flux", "stable-diffusion", "sdxl", "sd3", "imagen", "playground", "kolors")
    audio_markers = ("whisper", "tts", "speech", "audio")
    vision_markers = ("vision", "-vl", ":vl", "qwen3-vl", "llava", "moondream", "bakllava", "minicpm-v", "vila")

    if any(marker in lower for marker in embed_markers):
        return "embedding", ["embeddings"]
    if any(marker in lower for marker in image_markers):
        return "image", ["image_generation"]
    if any(marker in lower for marker in audio_markers):
        return "audio", ["audio"]

    capabilities = ["chat"]
    kind = "chat"
    if any(marker in lower for marker in vision_markers):
        capabilities.append("vision")
        kind = "vision"
    return kind, capabilities


def model_descriptor(model_name, item=None):
    model_id, model_info = normalize_nvidia_model(model_name)
    if model_info:
        return {
            "id": nvidia_display_name(model_id),
            "route_model": model_id,
            "provider": "nvidia",
            "kind": model_info.get("kind") or "chat",
            "family": model_info.get("family") or "nvidia",
            "capabilities": ordered_unique(nvidia_capabilities(model_info)),
            "note": model_info.get("note", ""),
            "owned_by": "nvidia",
            "created": 1775520000,
        }

    item = item or {}
    canonical_id = str(item.get("id") or item.get("name") or model_name or "").strip()
    kind, capabilities = infer_upstream_kind_and_capabilities(canonical_id, item)
    return {
        "id": canonical_id,
        "route_model": canonical_id,
        "provider": "upstream",
        "kind": kind,
        "family": str((item.get("owned_by") or "upstream")).strip() or "upstream",
        "capabilities": ordered_unique(capabilities),
        "note": str(item.get("description") or ""),
        "owned_by": item.get("owned_by") or "upstream",
        "created": item.get("created") or 1775520000,
    }


def clone_body_with_model(body, model_name):
    payload = deepcopy(body or {})
    if isinstance(payload, dict):
        payload["model"] = model_name
        if "name" in payload:
            payload["name"] = model_name
    return payload


def text_payload_needs_vision(value):
    if isinstance(value, dict):
        value_type = str(value.get("type") or "").lower()
        if value_type in ("image", "image_url", "input_image"):
            return True
        if value.get("images"):
            return True
        if value.get("image_url") or value.get("url") or value.get("source"):
            source = value.get("source") or {}
            if isinstance(source, dict) and (source.get("type") in ("base64", "url") or source.get("data") or source.get("url")):
                return True
        for nested in value.values():
            if text_payload_needs_vision(nested):
                return True
        return False
    if isinstance(value, list):
        return any(text_payload_needs_vision(item) for item in value)
    return False


def required_capability_for_request(endpoint_name, body):
    if endpoint_name in ("/v1/embeddings", "/api/embed", "/api/embeddings"):
        return "embeddings"
    if endpoint_name == "/api/images/generate":
        return "image_generation"
    if endpoint_name in ("/v1/chat/completions", "/v1/messages", "/v1/responses", "/api/chat"):
        return "vision" if text_payload_needs_vision((body or {}).get("messages") or (body or {}).get("input")) else "chat"
    if endpoint_name == "/api/generate":
        return "image_generation" if str(extract_model_name(body) or "").strip().lower().startswith(("flux", "stable-diffusion")) else "chat"
    return "chat"


def fetch_remote_image_as_data_url(url, source_ip, endpoint_name):
    url = str(url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        return url
    started = time.time()
    try:
        resp = http_session.get(url, timeout=20, stream=False)
        latency = time.time() - started
        content_type = str(resp.headers.get("Content-Type") or "image/jpeg").split(";")[0].strip() or "image/jpeg"
        if resp.status_code >= 400:
            log_message("WARN", "Falha ao buscar image_url remoto -> HTTP " + str(resp.status_code), "router", source_ip, endpoint_name, latency, resp.status_code)
            return url
        if not content_type.startswith("image/"):
            log_message("WARN", "image_url remoto sem content-type de imagem: " + content_type, "router", source_ip, endpoint_name, latency, 200)
            return url
        content = resp.content or b""
        if len(content) > 8 * 1024 * 1024:
            log_message("WARN", "image_url remoto excede 8MB; mantendo URL original", "router", source_ip, endpoint_name, latency, 200)
            return url
        encoded = base64.b64encode(content).decode("ascii")
        return "data:" + content_type + ";base64," + encoded
    except Exception as e:
        latency = time.time() - started
        log_message("WARN", "Falha ao converter image_url remoto: " + str(e)[:100], "router", source_ip, endpoint_name, latency, 0)
        return url


def normalize_image_urls_for_upstream(payload, source_ip, endpoint_name):
    body = deepcopy(payload or {})

    def visit(node):
        if isinstance(node, dict):
            node_type = str(node.get("type") or "").lower()
            if node.get("images") and isinstance(node.get("images"), list):
                converted = []
                for image in node.get("images") or []:
                    normalized = fetch_remote_image_as_data_url(image, source_ip, endpoint_name)
                    if isinstance(normalized, str) and normalized.startswith("data:") and ";base64," in normalized:
                        normalized = normalized.split(";base64,", 1)[1]
                    converted.append(normalized)
                node["images"] = converted
            if node_type in ("image_url", "input_image"):
                image_url = node.get("image_url") or node.get("url")
                if isinstance(image_url, dict):
                    image_url = image_url.get("url")
                normalized = fetch_remote_image_as_data_url(image_url, source_ip, endpoint_name)
                if "image_url" in node:
                    if isinstance(node["image_url"], dict):
                        node["image_url"]["url"] = normalized
                    else:
                        node["image_url"] = {"url": normalized}
                elif "url" in node:
                    node["url"] = normalized
            if "source" in node and isinstance(node["source"], dict):
                source = node["source"]
                if source.get("type") == "url" and source.get("url"):
                    normalized = fetch_remote_image_as_data_url(source.get("url"), source_ip, endpoint_name)
                    if normalized.startswith("data:") and ";base64," in normalized:
                        media_type, encoded = normalized[5:].split(";base64,", 1)
                        source["type"] = "base64"
                        source["media_type"] = media_type
                        source["data"] = encoded
                        source.pop("url", None)
            for key, value in list(node.items()):
                if isinstance(value, (dict, list)):
                    node[key] = visit(value)
            return node
        if isinstance(node, list):
            return [visit(item) for item in node]
        return node

    return visit(body)


def augment_tags_body(raw_body):
    try:
        data = json.loads(raw_body.decode("utf-8") if isinstance(raw_body, (bytes, bytearray)) else raw_body)
        models = data.get("models")
        if not isinstance(models, list):
            models = []
            data["models"] = models
        existing = {str(item.get("name", "")).lower() for item in models if isinstance(item, dict)}
        for model in NVIDIA_MODELS:
            name = nvidia_display_name(model["id"])
            if name.lower() in existing:
                continue
            models.append(
                {
                    "name": name,
                    "model": name,
                    "modified_at": "2026-04-07T00:00:00Z",
                    "size": 0,
                    "digest": "nvidia-" + uuid.uuid5(uuid.NAMESPACE_URL, model["id"]).hex,
                    "details": {
                        "parent_model": "",
                        "format": "nvidia",
                        "family": model["family"],
                        "families": ["nvidia", model["kind"]],
                        "parameter_size": "",
                        "quantization_level": "",
                    },
                }
            )
        return json.dumps(data, ensure_ascii=False).encode("utf-8")
    except Exception as e:
        log_message("WARN", "Falha ao anexar modelos NVIDIA: " + str(e)[:120])
        return raw_body


def nvidia_model_details(model_id, model_info):
    descriptor = model_descriptor(model_id, {"id": nvidia_display_name(model_id), "owned_by": "nvidia"})
    family = model_info["family"]
    kind = model_info["kind"]
    return {
        "license": "NVIDIA NIM routed by RED Systems proxy.",
        "modelfile": "FROM " + model_id + "\nPARAMETER provider nvidia\n",
        "parameters": "",
        "template": "{{ .Prompt }}",
        "details": {
            "parent_model": "",
            "format": "nvidia",
            "family": family,
            "families": ["nvidia", kind],
            "parameter_size": "",
            "quantization_level": "",
        },
        "model_info": {
            "red.provider": "nvidia",
            "red.model": model_id,
            "red.kind": kind,
            "red.family": family,
            "red.route_model": descriptor["route_model"],
            "red.capabilities": descriptor["capabilities"],
            "red.note": model_info.get("note", ""),
        },
        "capabilities": descriptor["capabilities"],
        "modified_at": "2026-04-07T00:00:00Z",
    }


def nvidia_show_request(model_id, model_info, source_ip):
    log_message("INFO", "NVIDIA show " + model_id, "nvidia", source_ip, "/api/show", 0, 200)
    return jsonify(nvidia_model_details(model_id, model_info))


def ollama_to_nvidia_messages(messages):
    converted = []
    for message in messages or []:
        role = message.get("role", "user")
        content = message.get("content", "")
        images = message.get("images") or []
        if images:
            parts = []
            if content:
                parts.append({"type": "text", "text": content})
            for image in images:
                if not image:
                    continue
                image_url = image if str(image).startswith("data:") else "data:image/jpeg;base64," + str(image)
                parts.append({"type": "image_url", "image_url": {"url": image_url}})
            content = parts
        converted.append({"role": role, "content": content})
    return converted


def nvidia_chat_payload(body, model_id, base_path):
    options = body.get("options") or {}
    if base_path == "/api/generate":
        messages = [{"role": "user", "content": body.get("prompt", "")}]
    else:
        messages = ollama_to_nvidia_messages(body.get("messages") or [])
    max_tokens = body.get("max_tokens") or options.get("num_predict") or options.get("max_tokens") or 512
    try:
        max_tokens = int(max_tokens)
    except Exception:
        max_tokens = 512
    if max_tokens <= 0:
        max_tokens = 512
    stream_value = body.get("stream", True)
    if isinstance(stream_value, str):
        stream_value = stream_value.strip().lower() not in ("0", "false", "no", "off")
    payload = {
        "model": model_id,
        "messages": messages,
        "temperature": body.get("temperature", options.get("temperature", 0.4)),
        "max_tokens": max_tokens,
        "stream": bool(stream_value),
    }
    top_p = body.get("top_p", options.get("top_p"))
    if top_p is not None:
        payload["top_p"] = top_p
    return payload


def compact_chat_debug(body, payload, model_id, base_path):
    raw_messages = body.get("messages") or []
    last_content = ""
    last_type = "none"
    if raw_messages:
        last_content = raw_messages[-1].get("content", "")
        last_type = type(last_content).__name__
    if isinstance(last_content, str):
        last_len = len(last_content)
    else:
        try:
            last_len = len(json.dumps(last_content, ensure_ascii=False))
        except Exception:
            last_len = 0
    options = body.get("options") or {}
    return {
        "provider": "nvidia",
        "model": model_id,
        "endpoint": base_path,
        "stream": bool(payload.get("stream")),
        "message_count": len(raw_messages),
        "last_content_type": last_type,
        "last_content_len": last_len,
        "max_tokens": payload.get("max_tokens"),
        "temperature": payload.get("temperature"),
        "format": body.get("format"),
        "num_predict": options.get("num_predict"),
    }


def nvidia_headers(content_type="application/json"):
    return {
        "Authorization": "Bearer " + NVIDIA_API_KEY,
        "Accept": "application/json",
        "Content-Type": content_type,
    }


def proxy_error_response(message, status=500, error_type="red_proxy_error"):
    return jsonify({"error": {"message": message, "type": error_type}}), status


def response_headers_subset(headers):
    selected = {}
    for h in ("Content-Type", "Content-Length", "Transfer-Encoding", "X-Request-Id"):
        if h in headers:
            selected[h] = headers[h]
    return selected


def proxy_response_from_upstream(resp):
    if resp is None:
        return Response('{"error":"upstream unavailable"}', status=502, content_type="application/json")

    if not getattr(resp, "raw", None) and not getattr(resp, "headers", None):
        return Response(str(resp), status=502, content_type="text/plain")

    if resp.request.method == "GET":
        return Response(resp.content, status=resp.status_code, headers=response_headers_subset(resp.headers))

    content_type = resp.headers.get("Content-Type", "application/json")
    if "text/event-stream" in content_type.lower():
        def generate():
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk
        return Response(generate(), status=resp.status_code, headers=response_headers_subset(resp.headers))
    return Response(resp.content, status=resp.status_code, headers=response_headers_subset(resp.headers))


def upstream_request(method, path, source_ip, *, json_body=None, raw_data=None, timeout=180, stream=False, extra_headers=None):
    req_path = path
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        key_id, api_key = key_pool.get_key()
        if not api_key:
            return None, Response('{"error":"No keys available"}', status=503, content_type="application/json")

        started = time.time()
        try:
            headers = {"Authorization": "Bearer " + api_key, "Accept": "application/json"}
            if json_body is not None:
                headers["Content-Type"] = "application/json"
            if extra_headers:
                headers.update(extra_headers)

            if attempt == 0:
                log_message("INFO", method + " " + req_path, key_id, source_ip, req_path, 0, 0)

            resp = http_session.request(
                method=method,
                url=OLLAMA_BASE + req_path,
                headers=headers,
                json=json_body,
                data=raw_data,
                timeout=timeout,
                stream=stream,
                allow_redirects=False,
            )
            latency = time.time() - started

            if resp.status_code == 429 and attempt < MAX_RETRIES:
                key_pool.report_failure(key_id, is_rate_limit=True)
                log_message("WARN", "429 key " + str(key_id) + " -> retry " + str(attempt + 1), key_id, source_ip, req_path, latency, 429)
                continue
            if resp.status_code == 404 and attempt < MAX_RETRIES:
                key_pool.report_failure(key_id, is_rate_limit=False)
                log_message("WARN", "404 key " + str(key_id) + " (sem acesso?) -> retry " + str(attempt + 1), key_id, source_ip, req_path, latency, 404)
                continue
            if resp.status_code >= 500 and attempt < MAX_RETRIES:
                key_pool.report_failure(key_id, is_rate_limit=False)
                log_message("WARN", str(resp.status_code) + " key " + str(key_id) + " -> retry " + str(attempt + 1), key_id, source_ip, req_path, latency, resp.status_code)
                continue

            if resp.status_code < 400:
                key_pool.report_success(key_id)
            else:
                key_pool.report_failure(key_id, resp.status_code == 429)

            log_message("INFO", method + " " + req_path + " -> HTTP " + str(resp.status_code), key_id, source_ip, req_path, latency, resp.status_code)
            return resp, None
        except Exception as e:
            latency = time.time() - started
            last_error = str(e)
            key_pool.report_failure(key_id, is_rate_limit=False)
            if attempt < MAX_RETRIES:
                log_message("WARN", "Exception key " + str(key_id) + " -> retry " + str(attempt + 1), key_id, source_ip, req_path, latency, 0)
                continue
            log_message("ERROR", method + " " + req_path + " -> " + last_error[:80], key_id, source_ip, req_path, latency, 500)
            return None, Response(json.dumps({"error": last_error}), status=500, content_type="application/json")

    return None, Response(json.dumps({"error": last_error or "Max retries exceeded"}), status=502, content_type="application/json")


def upstream_json_request(method, path, source_ip, *, body=None, timeout=180):
    resp, error_response = upstream_request(method, path, source_ip, json_body=body, timeout=timeout, stream=False)
    if error_response is not None:
        return None, error_response
    if resp is None:
        return None, Response('{"error":"upstream unavailable"}', status=502, content_type="application/json")
    if resp.status_code >= 400:
        return None, Response(resp.content, status=resp.status_code, content_type=resp.headers.get("Content-Type", "application/json"))
    try:
        return resp.json(), None
    except Exception:
        return None, Response(resp.content, status=502, content_type=resp.headers.get("Content-Type", "application/json"))


def upstream_model_entries(source_ip):
    cached_body, _cached_ct, _cached_status = cache_get(MODEL_CATALOG_CACHE_KEY)
    if cached_body is not None:
        try:
            return json.loads(cached_body.decode("utf-8")).get("data") or []
        except Exception:
            pass

    upstream_entries = []
    data, error_response = upstream_json_request("GET", "/v1/models", source_ip)
    if error_response is None and isinstance(data, dict):
        upstream_entries = list(data.get("data") or [])
    else:
        tags_data, tags_error = upstream_json_request("GET", "/api/tags", source_ip)
        if tags_error is None and isinstance(tags_data, dict):
            for item in tags_data.get("models") or []:
                if not isinstance(item, dict):
                    continue
                model_name = str(item.get("name") or item.get("model") or "").strip()
                if not model_name:
                    continue
                upstream_entries.append(
                    {
                        "id": model_name,
                        "object": "model",
                        "created": 1775520000,
                        "owned_by": "upstream",
                    }
                )

    merged = []
    seen = set()
    for item in upstream_entries:
        if not isinstance(item, dict):
            continue
        model_name = str(item.get("id") or item.get("name") or "").strip()
        if not model_name:
            continue
        key = model_name.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized = dict(item)
        normalized["id"] = model_name
        normalized.setdefault("object", "model")
        normalized.setdefault("created", 1775520000)
        normalized.setdefault("owned_by", "upstream")
        merged.append(normalized)

    for model in NVIDIA_MODELS:
        model_name = nvidia_display_name(model["id"])
        if model_name.lower() in seen:
            continue
        seen.add(model_name.lower())
        merged.append(
            {
                "id": model_name,
                "object": "model",
                "created": 1775520000,
                "owned_by": "nvidia",
            }
        )

    payload = {"object": "list", "data": merged}
    cache_set(MODEL_CATALOG_CACHE_KEY, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json", 200, 300)
    return merged


def model_descriptors(source_ip):
    return [model_descriptor(item.get("id") or item.get("name"), item) for item in upstream_model_entries(source_ip)]


def find_model_descriptor(model_name, source_ip):
    if not isinstance(model_name, str) or not model_name.strip():
        return None
    key = model_name.strip().lower()
    for descriptor in model_descriptors(source_ip):
        if descriptor["id"].lower() == key:
            return descriptor
        if descriptor["route_model"].lower() == key:
            return descriptor
    model_id, model_info = normalize_nvidia_model(model_name)
    if model_info:
        return model_descriptor(model_id, {"id": nvidia_display_name(model_id), "owned_by": "nvidia"})
    return None


def fallback_env_model_for_capability(capability):
    if capability == "chat":
        return DEFAULT_CHAT_MODEL
    if capability == "vision":
        return DEFAULT_VISION_MODEL or DEFAULT_CHAT_MODEL
    if capability == "image_generation":
        return DEFAULT_IMAGE_MODEL
    if capability == "embeddings":
        return DEFAULT_EMBEDDINGS_MODEL
    return ""


def choose_fallback_model(capability, source_ip, preferred_provider=None):
    descriptors = model_descriptors(source_ip)
    explicit = fallback_env_model_for_capability(capability)
    if explicit:
        explicit_descriptor = find_model_descriptor(explicit, source_ip)
        if explicit_descriptor and capability in explicit_descriptor.get("capabilities", []):
            return explicit_descriptor

    if preferred_provider:
        same_provider = [item for item in descriptors if item.get("provider") == preferred_provider and capability in item.get("capabilities", [])]
        if same_provider:
            return same_provider[0]

    compatible = [item for item in descriptors if capability in item.get("capabilities", [])]
    if compatible:
        return compatible[0]
    return None


def resolve_model_for_capability(model_name, capability, source_ip):
    requested = find_model_descriptor(model_name, source_ip) if model_name else None
    if requested and capability in requested.get("capabilities", []):
        return requested, requested, None
    if not ENABLE_CAPABILITY_FALLBACK:
        return None, requested, proxy_error_response("modelo nao suporta capability " + capability + " e fallback esta desativado", 400, "invalid_request_error")

    preferred_provider = requested.get("provider") if requested else None
    fallback = choose_fallback_model(capability, source_ip, preferred_provider=preferred_provider)
    if fallback:
        return fallback, requested, None

    if requested:
        return None, requested, proxy_error_response("modelo " + requested["id"] + " nao suporta capability " + capability + " e nao existe fallback compativel", 400, "invalid_request_error")
    return None, None, proxy_error_response("nenhum modelo compativel para capability " + capability, 400, "invalid_request_error")


def routing_meta(requested, resolved, capability):
    requested_id = requested["id"] if requested else ""
    resolved_id = resolved["id"] if resolved else ""
    return {
        "capability": capability,
        "requested_model": requested_id,
        "resolved_model": resolved_id,
        "fallback_used": bool(requested_id and resolved_id and requested_id.lower() != resolved_id.lower()),
        "requested_provider": requested.get("provider") if requested else "",
        "resolved_provider": resolved.get("provider") if resolved else "",
    }


def route_json_body(body, endpoint_name, source_ip):
    capability = required_capability_for_request(endpoint_name, body)
    resolved, requested, error_response = resolve_model_for_capability(extract_model_name(body), capability, source_ip)
    if error_response is not None:
        return None, None, error_response
    return clone_body_with_model(body, resolved["id"]), routing_meta(requested, resolved, capability), None


def public_model_entry(descriptor):
    return {
        "id": descriptor["id"],
        "object": "model",
        "created": descriptor.get("created") or 1775520000,
        "owned_by": descriptor.get("owned_by") or descriptor.get("provider") or "upstream",
        "red": {
            "provider": descriptor.get("provider"),
            "kind": descriptor.get("kind"),
            "family": descriptor.get("family"),
            "capabilities": descriptor.get("capabilities") or [],
            "route_model": descriptor.get("route_model"),
            "note": descriptor.get("note") or "",
        },
    }


def completion_prompt_to_text(prompt):
    if isinstance(prompt, str):
        return prompt
    if isinstance(prompt, list):
        parts = []
        for item in prompt:
            if isinstance(item, str):
                parts.append(item)
            elif item is None:
                continue
            else:
                parts.append(str(item))
        return "\n".join(parts)
    if prompt is None:
        return ""
    return str(prompt)


def coerce_int(value, default):
    try:
        return int(value)
    except Exception:
        return int(default)


def extract_message_text(message):
    if not isinstance(message, dict):
        return "" if message is None else str(message)
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                item_type = item.get("type")
                if item_type in ("text", "output_text", "input_text"):
                    parts.append(str(item.get("text") or ""))
        return "\n".join(part for part in parts if part)
    return ""


def openai_completion_to_chat_payload(body):
    payload = {
        "model": extract_model_name(body),
        "messages": [{"role": "user", "content": completion_prompt_to_text(body.get("prompt"))}],
        "stream": False,
        "max_tokens": coerce_int(body.get("max_tokens") or 256, 256),
    }
    for key in ("temperature", "top_p", "presence_penalty", "frequency_penalty", "stop", "n"):
        if body.get(key) is not None:
            payload[key] = body.get(key)
    return payload


def openai_completion_from_chat(data, model_name):
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    text = extract_message_text(message)
    return {
        "id": data.get("id") or ("cmpl_" + uuid.uuid4().hex),
        "object": "text_completion",
        "created": data.get("created") or int(time.time()),
        "model": model_name or data.get("model"),
        "choices": [
            {
                "text": text,
                "index": 0,
                "logprobs": None,
                "finish_reason": choice.get("finish_reason") or "stop",
            }
        ],
        "usage": data.get("usage") or {},
    }


def openai_completion_sse_from_chat(data, model_name):
    completion = openai_completion_from_chat(data, model_name)
    chunk_id = completion["id"]
    created = completion["created"]
    model = completion["model"]
    text = completion["choices"][0]["text"]
    yield "data: " + json.dumps(
        {
            "id": chunk_id,
            "object": "text_completion",
            "created": created,
            "model": model,
            "choices": [{"text": text, "index": 0, "logprobs": None, "finish_reason": None}],
        },
        ensure_ascii=False,
    ) + "\n\n"
    yield "data: " + json.dumps(
        {
            "id": chunk_id,
            "object": "text_completion",
            "created": created,
            "model": model,
            "choices": [{"text": "", "index": 0, "logprobs": None, "finish_reason": completion["choices"][0]["finish_reason"]}],
        },
        ensure_ascii=False,
    ) + "\n\n"
    yield "data: [DONE]\n\n"


def response_input_item_to_openai_message(item):
    if isinstance(item, str):
        return {"role": "user", "content": item}
    if not isinstance(item, dict):
        return {"role": "user", "content": "" if item is None else str(item)}

    role = item.get("role") or item.get("type") or "user"
    content = item.get("content")
    if isinstance(content, str):
        return {"role": role, "content": content}
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type in ("input_text", "text", "output_text"):
                parts.append({"type": "text", "text": str(block.get("text") or "")})
            elif block_type in ("input_image", "image_url"):
                image_url = block.get("image_url") or block.get("url")
                if isinstance(image_url, dict):
                    image_url = image_url.get("url")
                if image_url:
                    parts.append({"type": "image_url", "image_url": {"url": str(image_url)}})
        return {"role": role, "content": parts or ""}
    if item.get("input_text"):
        return {"role": role, "content": str(item.get("input_text"))}
    return {"role": role, "content": "" if content is None else str(content)}


def responses_to_chat_payload(body):
    messages = []
    instructions = body.get("instructions")
    if instructions:
        messages.append({"role": "system", "content": str(instructions)})

    input_value = body.get("input")
    if isinstance(input_value, list):
        for item in input_value:
            messages.append(response_input_item_to_openai_message(item))
    elif input_value is not None:
        messages.append(response_input_item_to_openai_message(input_value))

    payload = {
        "model": extract_model_name(body),
        "messages": messages or [{"role": "user", "content": ""}],
        "stream": False,
        "max_tokens": coerce_int(body.get("max_output_tokens") or body.get("max_tokens") or 512, 512),
    }
    for key in ("temperature", "top_p", "tools", "tool_choice"):
        if body.get(key) is not None:
            payload[key] = body.get(key)
    return payload


def responses_from_chat(data, model_name):
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    text = extract_message_text(message)
    item_id = "msg_" + uuid.uuid4().hex
    created = data.get("created") or int(time.time())
    usage = data.get("usage") or {}
    output_content = []
    if text:
        output_content.append({"type": "output_text", "text": text, "annotations": []})
    return {
        "id": "resp_" + uuid.uuid4().hex,
        "object": "response",
        "created_at": created,
        "status": "completed",
        "model": model_name or data.get("model"),
        "output": [
            {
                "id": item_id,
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": output_content,
            }
        ],
        "output_text": text,
        "error": None,
        "incomplete_details": None,
        "parallel_tool_calls": False,
        "usage": {
            "input_tokens": usage.get("prompt_tokens") or 0,
            "output_tokens": usage.get("completion_tokens") or 0,
            "total_tokens": usage.get("total_tokens") or ((usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0)),
        },
    }


def responses_sse_from_chat(data, model_name):
    response_obj = responses_from_chat(data, model_name)
    base = dict(response_obj)
    base["output"] = []
    base["output_text"] = ""
    text = response_obj.get("output_text") or ""
    item = (response_obj.get("output") or [{}])[0]
    item_id = item.get("id") or ("msg_" + uuid.uuid4().hex)
    yield "event: response.created\n"
    yield "data: " + json.dumps({"type": "response.created", "response": base}, ensure_ascii=False) + "\n\n"
    if text:
        yield "event: response.output_text.delta\n"
        yield "data: " + json.dumps({"type": "response.output_text.delta", "delta": text, "item_id": item_id, "output_index": 0, "content_index": 0}, ensure_ascii=False) + "\n\n"
    yield "event: response.completed\n"
    yield "data: " + json.dumps({"type": "response.completed", "response": response_obj}, ensure_ascii=False) + "\n\n"


def nvidia_openai_chat_json(model_id, model_info, body, source_ip, endpoint_name):
    if not NVIDIA_API_KEY:
        return None, proxy_error_response("RED_PROXY_NVIDIA_API_KEY not configured", 503)
    if model_info.get("kind") == "image":
        return None, proxy_error_response("modelo NVIDIA de imagem nao suporta " + endpoint_name, 400, "invalid_request_error")

    payload = deepcopy(body)
    payload["model"] = model_id
    payload["stream"] = False
    started = time.time()
    url = NVIDIA_CHAT_BASE + "/chat/completions"
    try:
        upstream = http_session.post(url, headers=nvidia_headers(), json=payload, timeout=180)
        latency = time.time() - started
        log_message("INFO", "NVIDIA sync " + model_id + " -> HTTP " + str(upstream.status_code), "nvidia", source_ip, endpoint_name, latency, upstream.status_code)
        if upstream.status_code >= 400:
            return None, Response(upstream.content, status=upstream.status_code, content_type=upstream.headers.get("Content-Type", "application/json"))
        return upstream.json(), None
    except Exception as e:
        latency = time.time() - started
        log_message("ERROR", "NVIDIA sync " + model_id + " -> " + str(e)[:100], "nvidia", source_ip, endpoint_name, latency, 500)
        return None, proxy_error_response(str(e), 500)


def universal_openai_chat_json(body, source_ip, endpoint_name):
    model_id, model_info = normalize_nvidia_model(extract_model_name(body))
    if model_info:
        data, error_response = nvidia_openai_chat_json(model_id, model_info, body, source_ip, endpoint_name)
        model_name = nvidia_display_name(model_id) if data is not None else None
        return model_name, data, error_response

    normalized_body = normalize_image_urls_for_upstream(body, source_ip, endpoint_name)
    data, error_response = upstream_json_request("POST", "/v1/chat/completions", source_ip, body=normalized_body)
    if error_response is not None:
        return None, None, error_response
    return extract_model_name(normalized_body), data, None


def openai_embeddings_to_ollama_payload(body):
    payload = {
        "model": extract_model_name(body),
        "input": body.get("input"),
    }
    if body.get("truncate") is not None:
        payload["truncate"] = body.get("truncate")
    if body.get("options") is not None:
        payload["options"] = body.get("options")
    return payload


def openai_embeddings_from_ollama(data, model_name):
    embeddings = data.get("embeddings")
    if embeddings is None:
        single = data.get("embedding")
        embeddings = [single] if single is not None else []
    if embeddings and not isinstance(embeddings, list):
        embeddings = [embeddings]
    if embeddings and isinstance(embeddings[0], (int, float)):
        embeddings = [embeddings]
    return {
        "object": "list",
        "data": [
            {
                "object": "embedding",
                "index": index,
                "embedding": vector,
            }
            for index, vector in enumerate(embeddings or [])
        ],
        "model": model_name,
        "usage": {
            "prompt_tokens": (data.get("prompt_eval_count") or 0),
            "total_tokens": (data.get("prompt_eval_count") or 0),
        },
    }


def universal_embeddings_json(body, source_ip):
    model_id, model_info = normalize_nvidia_model(extract_model_name(body))
    if model_info:
        return None, proxy_error_response("modelos NVIDIA configurados neste proxy nao suportam embeddings", 400, "invalid_request_error")

    payload = openai_embeddings_to_ollama_payload(body)
    resp, error_response = upstream_request("POST", "/api/embed", source_ip, json_body=payload, timeout=180, stream=False)
    if error_response is not None:
        return None, error_response
    if resp is None:
        return None, proxy_error_response("upstream unavailable", 502)
    if resp.status_code in (404, 405):
        legacy_payload = {
            "model": extract_model_name(body),
            "prompt": completion_prompt_to_text(body.get("input")),
        }
        legacy_resp, legacy_error = upstream_request("POST", "/api/embeddings", source_ip, json_body=legacy_payload, timeout=180, stream=False)
        if legacy_error is not None:
            return None, legacy_error
        resp = legacy_resp
    if resp is None:
        return None, proxy_error_response("upstream unavailable", 502)
    if resp.status_code >= 400:
        return None, Response(resp.content, status=resp.status_code, content_type=resp.headers.get("Content-Type", "application/json"))
    try:
        return resp.json(), None
    except Exception:
        return None, Response(resp.content, status=502, content_type=resp.headers.get("Content-Type", "application/json"))


def nvidia_openai_chat_request(model_id, model_info, body, source_ip):
    if not NVIDIA_API_KEY:
        return jsonify({"error": "RED_PROXY_NVIDIA_API_KEY not configured"}), 503
    if model_info.get("kind") == "image":
        return jsonify({"error": "modelo NVIDIA de imagem nao suporta /v1/chat/completions"}), 400

    payload = deepcopy(body)
    payload["model"] = model_id
    started = time.time()
    url = NVIDIA_CHAT_BASE + "/chat/completions"
    debug = {
        "provider": "nvidia",
        "model": model_id,
        "endpoint": "/v1/chat/completions",
        "stream": bool(payload.get("stream", False)),
        "message_count": len(payload.get("messages") or []),
        "tools": bool(payload.get("tools")),
        "tool_choice": payload.get("tool_choice"),
        "max_tokens": payload.get("max_tokens"),
        "temperature": payload.get("temperature"),
    }
    log_message("INFO", "NVIDIA openai request " + json.dumps(debug, ensure_ascii=False), "nvidia", source_ip, "/v1/chat/completions", 0, 0)

    try:
        upstream = http_session.post(
            url,
            headers=nvidia_headers(),
            json=payload,
            stream=bool(payload.get("stream", False)),
            timeout=180,
        )
        latency = time.time() - started
        log_message("INFO", "NVIDIA openai " + model_id + " -> HTTP " + str(upstream.status_code), "nvidia", source_ip, "/v1/chat/completions", latency, upstream.status_code)
        if upstream.status_code >= 400:
            return Response(upstream.content, status=upstream.status_code, content_type=upstream.headers.get("Content-Type", "application/json"))

        if payload.get("stream"):
            def generate_openai_stream():
                for chunk in upstream.iter_content(chunk_size=8192):
                    if chunk:
                        yield chunk

            response_headers = {}
            content_type = upstream.headers.get("Content-Type", "text/event-stream")
            for h in ("Cache-Control", "X-Request-Id"):
                if h in upstream.headers:
                    response_headers[h] = upstream.headers[h]
            return Response(generate_openai_stream(), status=200, headers=response_headers, content_type=content_type)

        return Response(upstream.content, status=200, content_type=upstream.headers.get("Content-Type", "application/json"))
    except Exception as e:
        latency = time.time() - started
        log_message("ERROR", "NVIDIA openai " + model_id + " -> " + str(e)[:100], "nvidia", source_ip, "/v1/chat/completions", latency, 500)
        return jsonify({"error": {"message": str(e), "type": "red_proxy_error"}}), 500


def anthropic_text_from_content(content):
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return "" if content is None else str(content)
    parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
    return "\n".join(part for part in parts if part)


def anthropic_system_messages(system):
    text = anthropic_text_from_content(system)
    return [{"role": "system", "content": text}] if text else []


def anthropic_message_to_openai(message):
    role = message.get("role", "user")
    content = message.get("content", "")
    if isinstance(content, str):
        return [{"role": role, "content": content}]
    if not isinstance(content, list):
        return [{"role": role, "content": "" if content is None else str(content)}]

    out = []
    text_parts = []
    openai_parts = []
    assistant_tool_calls = []

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
                openai_parts.append({"type": "image_url", "image_url": {"url": "data:" + media_type + ";base64," + source["data"]}})
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


def anthropic_tools_to_openai(tools):
    converted = []
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


def anthropic_tool_choice_to_openai(tool_choice):
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


def anthropic_to_openai_payload(body, model_id):
    messages = []
    messages.extend(anthropic_system_messages(body.get("system")))
    for message in body.get("messages") or []:
        messages.extend(anthropic_message_to_openai(message))

    payload = {
        "model": model_id,
        "messages": messages,
        "stream": False,
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


def anthropic_response_from_openai(data, model_name):
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content_blocks = []
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
    return {
        "id": data.get("id") or ("msg_" + uuid.uuid4().hex),
        "type": "message",
        "role": "assistant",
        "model": model_name,
        "content": content_blocks,
        "stop_reason": "tool_use" if finish_reason == "tool_calls" else "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("prompt_tokens") or 0,
            "output_tokens": usage.get("completion_tokens") or 0,
        },
    }


def anthropic_sse_from_message(message):
    yield "event: message_start\n"
    start_message = dict(message)
    start_message["content"] = []
    yield "data: " + json.dumps({"type": "message_start", "message": start_message}, ensure_ascii=False) + "\n\n"

    for index, block in enumerate(message.get("content") or []):
        yield "event: content_block_start\n"
        empty_block = dict(block)
        if empty_block.get("type") == "text":
            text = empty_block.pop("text", "")
        elif empty_block.get("type") == "tool_use":
            tool_input = empty_block.pop("input", {})
        else:
            text = ""
            tool_input = {}
        yield "data: " + json.dumps({"type": "content_block_start", "index": index, "content_block": empty_block}, ensure_ascii=False) + "\n\n"

        if block.get("type") == "text":
            yield "event: content_block_delta\n"
            yield "data: " + json.dumps({"type": "content_block_delta", "index": index, "delta": {"type": "text_delta", "text": text}}, ensure_ascii=False) + "\n\n"
        elif block.get("type") == "tool_use":
            yield "event: content_block_delta\n"
            yield "data: " + json.dumps({"type": "content_block_delta", "index": index, "delta": {"type": "input_json_delta", "partial_json": json.dumps(tool_input, ensure_ascii=False)}}, ensure_ascii=False) + "\n\n"

        yield "event: content_block_stop\n"
        yield "data: " + json.dumps({"type": "content_block_stop", "index": index}, ensure_ascii=False) + "\n\n"

    yield "event: message_delta\n"
    yield "data: " + json.dumps({"type": "message_delta", "delta": {"stop_reason": message.get("stop_reason"), "stop_sequence": None}, "usage": message.get("usage") or {}}, ensure_ascii=False) + "\n\n"
    yield "event: message_stop\n"
    yield "data: " + json.dumps({"type": "message_stop"}, ensure_ascii=False) + "\n\n"


def nvidia_anthropic_messages_request(model_id, model_info, body, source_ip):
    if not NVIDIA_API_KEY:
        return jsonify({"error": {"message": "RED_PROXY_NVIDIA_API_KEY not configured", "type": "red_proxy_error"}}), 503
    if model_info.get("kind") == "image":
        return jsonify({"error": {"message": "modelo NVIDIA de imagem nao suporta /v1/messages", "type": "invalid_request_error"}}), 400

    payload = anthropic_to_openai_payload(body, model_id)
    started = time.time()
    url = NVIDIA_CHAT_BASE + "/chat/completions"
    debug = {
        "provider": "nvidia",
        "model": model_id,
        "endpoint": "/v1/messages",
        "stream": bool(body.get("stream", False)),
        "message_count": len(body.get("messages") or []),
        "openai_message_count": len(payload.get("messages") or []),
        "tools": bool(payload.get("tools")),
        "max_tokens": payload.get("max_tokens"),
    }
    log_message("INFO", "NVIDIA anthropic request " + json.dumps(debug, ensure_ascii=False), "nvidia", source_ip, "/v1/messages", 0, 0)

    try:
        upstream = http_session.post(url, headers=nvidia_headers(), json=payload, timeout=180)
        latency = time.time() - started
        log_message("INFO", "NVIDIA anthropic " + model_id + " -> HTTP " + str(upstream.status_code), "nvidia", source_ip, "/v1/messages", latency, upstream.status_code)
        if upstream.status_code >= 400:
            return Response(upstream.content, status=upstream.status_code, content_type=upstream.headers.get("Content-Type", "application/json"))

        message = anthropic_response_from_openai(upstream.json(), nvidia_display_name(model_id))
        if body.get("stream"):
            return Response(anthropic_sse_from_message(message), status=200, content_type="text/event-stream")
        return jsonify(message)
    except Exception as e:
        latency = time.time() - started
        log_message("ERROR", "NVIDIA anthropic " + model_id + " -> " + str(e)[:100], "nvidia", source_ip, "/v1/messages", latency, 500)
        return jsonify({"error": {"message": str(e), "type": "red_proxy_error"}}), 500


def nvidia_chat_request(model_id, body, base_path, source_ip):
    if not NVIDIA_API_KEY:
        return jsonify({"error": "RED_PROXY_NVIDIA_API_KEY not configured"}), 503

    payload = nvidia_chat_payload(body, model_id, base_path)
    log_message("INFO", "NVIDIA request " + json.dumps(compact_chat_debug(body, payload, model_id, base_path), ensure_ascii=False), "nvidia", source_ip, base_path, 0, 0)
    started = time.time()
    url = NVIDIA_CHAT_BASE + "/chat/completions"

    try:
        if payload["stream"]:
            upstream = http_session.post(url, headers=nvidia_headers(), json=payload, stream=True, timeout=120)
            latency = time.time() - started
            log_message("INFO", "NVIDIA stream " + model_id + " -> HTTP " + str(upstream.status_code), "nvidia", source_ip, base_path, latency, upstream.status_code)
            if upstream.status_code >= 400:
                return Response(upstream.text, status=upstream.status_code, content_type=upstream.headers.get("Content-Type", "application/json"))

            def generate_chat_stream():
                chunk_count = 0
                content_len = 0
                finish_reason = None
                for line in upstream.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    if line.startswith("data: "):
                        line = line[6:]
                    if line.strip() == "[DONE]":
                        break
                    try:
                        item = json.loads(line)
                        choice = item.get("choices", [{}])[0]
                        finish_reason = choice.get("finish_reason") or finish_reason
                        delta = choice.get("delta", {})
                        content = delta.get("content") or ""
                    except Exception:
                        content = ""
                    if not content:
                        continue
                    chunk_count += 1
                    content_len += len(content)
                    if base_path == "/api/generate":
                        chunk = {"model": nvidia_display_name(model_id), "created_at": utc_created_at(), "response": content, "done": False}
                    else:
                        chunk = {"model": nvidia_display_name(model_id), "created_at": utc_created_at(), "message": {"role": "assistant", "content": content}, "done": False}
                    yield json.dumps(chunk, ensure_ascii=False) + "\n"
                stream_debug = {
                    "model": model_id,
                    "finish_reason": finish_reason,
                    "chunks": chunk_count,
                    "content_len": content_len,
                }
                log_message("INFO", "NVIDIA stream response " + json.dumps(stream_debug, ensure_ascii=False), "nvidia", source_ip, base_path, latency, upstream.status_code)
                final = {"model": nvidia_display_name(model_id), "created_at": utc_created_at(), "done": True}
                yield json.dumps(final, ensure_ascii=False) + "\n"

            return Response(generate_chat_stream(), status=200, content_type="application/x-ndjson")

        upstream = http_session.post(url, headers=nvidia_headers(), json=payload, timeout=120)
        latency = time.time() - started
        log_message("INFO", "NVIDIA " + model_id + " -> HTTP " + str(upstream.status_code), "nvidia", source_ip, base_path, latency, upstream.status_code)
        if upstream.status_code >= 400:
            return Response(upstream.content, status=upstream.status_code, content_type=upstream.headers.get("Content-Type", "application/json"))

        data = upstream.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        response_debug = {
            "model": model_id,
            "finish_reason": choice.get("finish_reason"),
            "message_keys": sorted(message.keys()),
            "content_len": len(content),
        }
        log_message("INFO", "NVIDIA response " + json.dumps(response_debug, ensure_ascii=False), "nvidia", source_ip, base_path, latency, upstream.status_code)
        usage = data.get("usage") or {}
        total_duration = int(latency * 1_000_000_000)
        if base_path == "/api/generate":
            result = {
                "model": nvidia_display_name(model_id),
                "created_at": utc_created_at(),
                "response": content,
                "done": True,
                "done_reason": choice.get("finish_reason") or "stop",
                "total_duration": total_duration,
                "prompt_eval_count": usage.get("prompt_tokens"),
                "eval_count": usage.get("completion_tokens"),
            }
        else:
            result = {
                "model": nvidia_display_name(model_id),
                "created_at": utc_created_at(),
                "message": {"role": "assistant", "content": content},
                "done": True,
                "done_reason": choice.get("finish_reason") or "stop",
                "total_duration": total_duration,
                "prompt_eval_count": usage.get("prompt_tokens"),
                "eval_count": usage.get("completion_tokens"),
            }
        return jsonify(result)
    except Exception as e:
        latency = time.time() - started
        log_message("ERROR", "NVIDIA " + model_id + " -> " + str(e)[:100], "nvidia", source_ip, base_path, latency, 500)
        return jsonify({"error": str(e)}), 500


def image_payload_for_model(model_info, body):
    prompt = body.get("prompt") or body.get("safe_prompt") or body.get("text") or ""
    if not prompt:
        raise ValueError("prompt is required")
    width = int(body.get("width") or 1024)
    height = int(body.get("height") or 1024)
    seed = int(body.get("seed") if body.get("seed") is not None else random.randint(0, 2_147_483_647))
    steps = int(body.get("steps") or model_info["default_steps"])
    steps = min(steps, model_info["max_steps"])
    cfg_scale = body.get("cfg_scale", body.get("cfg", model_info.get("default_cfg")))
    schema = model_info["schema"]

    if schema in ("flux1-schnell", "flux2"):
        return {
            "prompt": prompt,
            "height": height,
            "width": width,
            "samples": int(body.get("samples") or 1),
            "seed": seed,
            "steps": steps,
            **({} if cfg_scale is None else {"cfg_scale": cfg_scale}),
        }
    if schema == "flux1-dev":
        return {
            "prompt": prompt,
            "height": height,
            "width": width,
            "cfg_scale": cfg_scale if cfg_scale is not None else 3,
            "samples": int(body.get("samples") or 1),
            "seed": seed,
            "steps": max(5, steps),
            "mode": body.get("mode") or "base",
        }
    if schema == "sdxl":
        steps = max(5, steps)
        return {
            "text_prompts": [{"text": prompt, "weight": 1}],
            "height": max(1024, height),
            "width": max(1024, width),
            "cfg_scale": cfg_scale if cfg_scale is not None else 6,
            "samples": int(body.get("samples") or 1),
            "seed": seed,
            "steps": steps,
        }
    if schema == "sd3":
        steps = max(5, steps)
        return {
            "prompt": prompt,
            "cfg_scale": cfg_scale if cfg_scale is not None else 5,
            "seed": seed,
            "steps": steps,
        }
    raise ValueError("unsupported image schema")


def nvidia_image_request(model_id, model_info, body, source_ip, as_ollama_generate=False):
    if not NVIDIA_API_KEY:
        return jsonify({"error": "RED_PROXY_NVIDIA_API_KEY not configured"}), 503
    started = time.time()
    try:
        payload = image_payload_for_model(model_info, body)
        url = NVIDIA_GENAI_BASE + "/" + model_info["endpoint"]
        headers = nvidia_headers()
        headers["NVCF-POLL-SECONDS"] = str(int(body.get("poll_seconds") or 120))
        upstream = http_session.post(url, headers=headers, json=payload, timeout=180)
        latency = time.time() - started
        log_message("INFO", "NVIDIA image " + model_id + " -> HTTP " + str(upstream.status_code), "nvidia", source_ip, "/api/images/generate", latency, upstream.status_code)
        if upstream.status_code >= 400:
            return Response(upstream.content, status=upstream.status_code, content_type=upstream.headers.get("Content-Type", "application/json"))
        data = upstream.json()
        artifacts = data.get("artifacts") or []
        images = []
        for artifact in artifacts:
            encoded = artifact.get("base64") if isinstance(artifact, dict) else None
            if encoded:
                images.append({"mime_type": "image/jpeg", "base64": encoded})
        if data.get("image"):
            images.append({"mime_type": "image/jpeg", "base64": data["image"]})
        if as_ollama_generate:
            return jsonify(
                {
                    "model": nvidia_display_name(model_id),
                    "created_at": utc_created_at(),
                    "response": "",
                    "images": [image["base64"] for image in images],
                    "done": True,
                    "total_duration": int(latency * 1_000_000_000),
                }
            )
        return jsonify(
            {
                "model": nvidia_display_name(model_id),
                "created_at": utc_created_at(),
                "images": images,
                "duration_ms": int(latency * 1000),
                "raw_finish_reason": data.get("finish_reason"),
                "seed": data.get("seed") or payload.get("seed"),
            }
        )
    except Exception as e:
        latency = time.time() - started
        log_message("ERROR", "NVIDIA image " + model_id + " -> " + str(e)[:100], "nvidia", source_ip, "/api/images/generate", latency, 500)
        return jsonify({"error": str(e)}), 500


def forward_to_upstream(full_path=None):
    full_path = full_path or request.path or "/"
    source_ip = request.remote_addr
    req_path = full_path
    if request.query_string:
        req_path += "?" + request.query_string.decode("utf-8")

    req_data = None
    if request.method in ("POST", "PUT", "PATCH"):
        req_data = request.get_data()

    base_path = full_path.split("?")[0]
    ttl = CACHEABLE_GETS.get(base_path) if request.method == "GET" else None
    last_error = None

    for attempt in range(MAX_RETRIES + 1):
        key_id, api_key = key_pool.get_key()
        if not api_key:
            return '{"error": "No keys available"}', 503

        start = time.time()
        try:
            headers = {"Authorization": "Bearer " + api_key}
            for h in ("Content-Type", "Accept", "Accept-Encoding"):
                if h in request.headers:
                    headers[h] = request.headers[h]

            if attempt == 0:
                log_message("INFO", request.method + " " + req_path, key_id, source_ip, req_path, 0, 0)

            resp = http_session.request(
                method=request.method,
                url=OLLAMA_BASE + req_path,
                headers=headers,
                data=req_data,
                stream=(ttl is None),
                timeout=120,
                allow_redirects=False,
            )
            latency = time.time() - start

            if resp.status_code == 429 and attempt < MAX_RETRIES:
                key_pool.report_failure(key_id, is_rate_limit=True)
                log_message("WARN", "429 key " + str(key_id) + " -> retry " + str(attempt + 1), key_id, source_ip, req_path, latency, 429)
                continue
            if resp.status_code == 404 and attempt < MAX_RETRIES:
                key_pool.report_failure(key_id, is_rate_limit=False)
                log_message("WARN", "404 key " + str(key_id) + " (sem acesso?) -> retry " + str(attempt + 1), key_id, source_ip, req_path, latency, 404)
                continue
            if resp.status_code >= 500 and attempt < MAX_RETRIES:
                key_pool.report_failure(key_id, is_rate_limit=False)
                log_message("WARN", str(resp.status_code) + " key " + str(key_id) + " -> retry " + str(attempt + 1), key_id, source_ip, req_path, latency, resp.status_code)
                continue

            if resp.status_code < 400:
                key_pool.report_success(key_id)
            else:
                key_pool.report_failure(key_id, resp.status_code == 429)

            log_message("INFO", request.method + " " + req_path + " -> HTTP " + str(resp.status_code), key_id, source_ip, req_path, latency, resp.status_code)

            if ttl and resp.status_code == 200:
                body = resp.content
                ct = resp.headers.get("Content-Type", "application/json")
                if base_path == "/api/tags":
                    body = augment_tags_body(body)
                    ct = "application/json"
                cache_set(base_path, body, ct, 200, ttl)
                return Response(body, status=200, content_type=ct)

            def generate():
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        yield chunk

            response_headers = {}
            for h in ("Content-Type", "Content-Length", "Transfer-Encoding", "X-Request-Id"):
                if h in resp.headers:
                    response_headers[h] = resp.headers[h]

            return Response(generate(), status=resp.status_code, headers=response_headers)
        except Exception as e:
            latency = time.time() - start
            last_error = str(e)
            key_pool.report_failure(key_id, is_rate_limit=False)
            if attempt < MAX_RETRIES:
                log_message("WARN", "Exception key " + str(key_id) + " -> retry " + str(attempt + 1), key_id, source_ip, req_path, latency, 0)
                continue
            log_message("ERROR", request.method + " " + req_path + " -> " + last_error[:80], key_id, source_ip, req_path, latency, 500)
            return json.dumps({"error": last_error}), 500

    return json.dumps({"error": last_error or "Max retries exceeded"}), 502


# ============ LOGGING COM ROTACAO ============
_log_lock = Lock()


def log_message(level, message, key_id="N/A", source_ip="N/A", endpoint="N/A", latency=0, status_code=0):
    try:
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "level": level,
            "message": message,
            "key_id": key_id,
            "source_ip": source_ip,
            "endpoint": endpoint,
            "latency": round(latency, 2),
            "status_code": status_code
        }
        with _log_lock:
            # Rotacao: se passou do limite, renomeia pra .old e comeca novo
            try:
                if os.path.exists(LOGS_FILE) and os.path.getsize(LOGS_FILE) > LOG_MAX_BYTES:
                    old = LOGS_FILE + ".old"
                    if os.path.exists(old):
                        os.remove(old)
                    os.rename(LOGS_FILE, old)
            except:
                pass
            with open(LOGS_FILE, "a") as f:
                f.write(json.dumps(log_entry) + "\n")
    except:
        pass


# ============ KEY MANAGEMENT (IN-MEMORY) ============
class KeyPool:
    """
    Keys ficam em memoria. Disco so e lido no startup ou quando o dashboard
    altera o keys.json (detectado via mtime). Contadores sao periodicamente
    flushed pro disco em background - nunca no hot path do request.
    """

    def __init__(self):
        self._lock = Lock()
        self._keys = []
        self._next_id = 1
        self._file_mtime = 0
        self._dirty = False
        self._load_from_disk()
        # Flush contadores pro disco a cada 30s
        t = Thread(target=self._flush_loop, daemon=True)
        t.start()

    def _load_from_disk(self):
        try:
            mtime = os.path.getmtime(KEYS_FILE)
            with open(KEYS_FILE, "r") as f:
                data = json.load(f)
            self._keys = data.get("keys", [])
            self._next_id = data.get("next_id", 1)
            self._file_mtime = mtime
            log_message("INFO", "Carregadas " + str(len(self._keys)) + " keys")
        except:
            self._keys = []
            self._next_id = 1

    def _check_reload(self):
        """Rele do disco se o dashboard alterou o keys.json"""
        try:
            mtime = os.path.getmtime(KEYS_FILE)
            if mtime != self._file_mtime:
                self._load_from_disk()
        except:
            pass

    def _save_to_disk(self):
        try:
            data = {"keys": deepcopy(self._keys), "next_id": self._next_id}
            with open(KEYS_FILE, "w") as f:
                json.dump(data, f, indent=2)
                f.flush()
            self._file_mtime = os.path.getmtime(KEYS_FILE)
            self._dirty = False
        except:
            pass

    def _flush_loop(self):
        """Flush contadores pro disco periodicamente"""
        while True:
            time.sleep(30)
            with self._lock:
                if self._dirty:
                    self._save_to_disk()

    def get_key(self):
        """Retorna (key_id, api_key) de uma key disponivel. Incrementa contador in-memory."""
        with self._lock:
            self._check_reload()
            now = time.time()
            available = [k for k in self._keys if k.get("active") and now > k.get("cooldown_until", 0)]
            if not available:
                # Se todas estao em cooldown, reseta cooldowns
                for k in self._keys:
                    if k.get("active"):
                        k["cooldown_until"] = 0
                available = [k for k in self._keys if k.get("active")]
            if not available:
                return None, None
            key = random.choice(available)
            key["total_requests"] = key.get("total_requests", 0) + 1
            self._dirty = True
            return key["id"], key["key"]

    def report_success(self, key_id):
        with self._lock:
            for k in self._keys:
                if k["id"] == key_id:
                    k["successes"] = k.get("successes", 0) + 1
                    k["failures"] = 0
                    self._dirty = True
                    break

    def report_failure(self, key_id, is_rate_limit=False):
        with self._lock:
            for k in self._keys:
                if k["id"] == key_id:
                    k["failures"] = k.get("failures", 0) + 1
                    cooldown = 60 if is_rate_limit else 15
                    k["cooldown_until"] = time.time() + cooldown
                    self._dirty = True
                    break

    def get_stats(self):
        with self._lock:
            self._check_reload()
            return deepcopy(self._keys)

    def force_reload(self):
        with self._lock:
            self._load_from_disk()


def summarize_keys(keys):
    now = time.time()
    return {
        "total": len(keys),
        "active": sum(1 for key in keys if key.get("active")),
        "cooldown": sum(1 for key in keys if key.get("cooldown_until", 0) > now),
        "total_requests": sum(int(key.get("total_requests", 0) or 0) for key in keys),
        "successes": sum(int(key.get("successes", 0) or 0) for key in keys),
        "failures": sum(int(key.get("failures", 0) or 0) for key in keys),
    }


key_pool = KeyPool()

# ============ PROXY COM RETRY ============
MAX_RETRIES = 2  # Tenta ate 2 keys diferentes em caso de 429/404/5xx


@app.get("/admin/stats")
def admin_stats():
    keys = key_pool.get_stats()
    descriptors = model_descriptors(request.remote_addr)
    return jsonify(
        {
            "status": "ok",
            "upstream": OLLAMA_BASE,
            "nvidia": {
                "configured": bool(NVIDIA_API_KEY),
                "chat_base": NVIDIA_CHAT_BASE,
                "genai_base": NVIDIA_GENAI_BASE,
                "models": [nvidia_display_name(model["id"]) for model in NVIDIA_MODELS],
            },
            "host": PROXY_HOST,
            "port": PROXY_PORT,
            "keys": keys,
            "summary": summarize_keys(keys),
            "router": {
                "fallback_enabled": ENABLE_CAPABILITY_FALLBACK,
                "defaults": {
                    "chat": DEFAULT_CHAT_MODEL,
                    "vision": DEFAULT_VISION_MODEL,
                    "image_generation": DEFAULT_IMAGE_MODEL,
                    "embeddings": DEFAULT_EMBEDDINGS_MODEL,
                },
                "catalog_size": len(descriptors),
                "capabilities": {
                    "chat": sum(1 for descriptor in descriptors if "chat" in descriptor.get("capabilities", [])),
                    "vision": sum(1 for descriptor in descriptors if "vision" in descriptor.get("capabilities", [])),
                    "image_generation": sum(1 for descriptor in descriptors if "image_generation" in descriptor.get("capabilities", [])),
                    "embeddings": sum(1 for descriptor in descriptors if "embeddings" in descriptor.get("capabilities", [])),
                },
            },
            "cache": cache_stats(),
            "files": {
                "keys_file": KEYS_FILE,
                "logs_file": LOGS_FILE,
            },
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
    )


@app.get("/api/router/models")
def router_models():
    return jsonify(
        {
            "status": "ok",
            "fallback_enabled": ENABLE_CAPABILITY_FALLBACK,
            "defaults": {
                "chat": DEFAULT_CHAT_MODEL,
                "vision": DEFAULT_VISION_MODEL,
                "image_generation": DEFAULT_IMAGE_MODEL,
                "embeddings": DEFAULT_EMBEDDINGS_MODEL,
            },
            "models": model_descriptors(request.remote_addr),
        }
    )


@app.post("/api/router/resolve")
def router_resolve():
    body = request.get_json(silent=True) or {}
    capability = str(body.get("capability") or "chat").strip() or "chat"
    model_name = extract_model_name(body) or body.get("requested_model")
    resolved, requested, error_response = resolve_model_for_capability(model_name, capability, request.remote_addr)
    if error_response is not None:
        return error_response
    return jsonify({"status": "ok", "routing": routing_meta(requested, resolved, capability), "resolved": resolved, "requested": requested})


@app.post("/admin/reload")
def admin_reload():
    key_pool.force_reload()
    keys = key_pool.get_stats()
    return jsonify(
        {
            "status": "ok",
            "message": "reload concluido",
            "summary": summarize_keys(keys),
        }
    )


@app.get("/api/nvidia/models")
def nvidia_models():
    return jsonify(
        {
            "status": "ok",
            "configured": bool(NVIDIA_API_KEY),
            "suffix": NVIDIA_SUFFIX,
            "models": [model_descriptor(model["id"], {"id": nvidia_display_name(model["id"]), "owned_by": "nvidia"}) for model in NVIDIA_MODELS],
        }
    )


@app.get("/v1/models")
def openai_models():
    return jsonify({"object": "list", "data": [public_model_entry(descriptor) for descriptor in model_descriptors(request.remote_addr)]})


@app.post("/v1/chat/completions")
def openai_chat_completions():
    body = request.get_json(silent=True) or {}
    routed_body, _routing, error_response = route_json_body(body, "/v1/chat/completions", request.remote_addr)
    if error_response is not None:
        return error_response
    model_id, model_info = normalize_nvidia_model(extract_model_name(routed_body))
    if model_info:
        return nvidia_openai_chat_request(model_id, model_info, routed_body, request.remote_addr)
    routed_body = normalize_image_urls_for_upstream(routed_body, request.remote_addr, "/v1/chat/completions")
    upstream, error_response = upstream_request(
        "POST",
        "/v1/chat/completions",
        request.remote_addr,
        json_body=routed_body,
        timeout=180,
        stream=bool(routed_body.get("stream")),
    )
    if error_response is not None:
        return error_response
    return proxy_response_from_upstream(upstream)


@app.post("/v1/messages")
def anthropic_messages():
    body = request.get_json(silent=True) or {}
    routed_body, _routing, error_response = route_json_body(body, "/v1/messages", request.remote_addr)
    if error_response is not None:
        return error_response
    model_id, model_info = normalize_nvidia_model(extract_model_name(routed_body))
    if model_info:
        return nvidia_anthropic_messages_request(model_id, model_info, routed_body, request.remote_addr)
    model_name, data, error_response = universal_openai_chat_json(anthropic_to_openai_payload(routed_body, extract_model_name(routed_body)), request.remote_addr, "/v1/messages")
    if error_response is not None:
        return error_response
    message = anthropic_response_from_openai(data, model_name)
    if routed_body.get("stream"):
        return Response(anthropic_sse_from_message(message), status=200, content_type="text/event-stream")
    return jsonify(message)


@app.post("/v1/completions")
def openai_completions():
    body = request.get_json(silent=True) or {}
    routed_body, _routing, error_response = route_json_body(body, "/v1/completions", request.remote_addr)
    if error_response is not None:
        return error_response
    chat_payload = openai_completion_to_chat_payload(routed_body)
    model_name, data, error_response = universal_openai_chat_json(chat_payload, request.remote_addr, "/v1/completions")
    if error_response is not None:
        return error_response
    completion = openai_completion_from_chat(data, model_name)
    original_max = coerce_int(chat_payload.get("max_tokens") or 0, 0)
    if not completion["choices"][0]["text"] and 0 < original_max < 256:
        retry_steps = []
        for candidate in (64, 128, 256):
            if candidate > original_max:
                retry_steps.append(candidate)
        for candidate in retry_steps:
            retry_payload = deepcopy(chat_payload)
            retry_payload["max_tokens"] = candidate
            retry_model_name, retry_data, retry_error = universal_openai_chat_json(retry_payload, request.remote_addr, "/v1/completions.retry")
            if retry_error is not None:
                break
            retry_completion = openai_completion_from_chat(retry_data, retry_model_name)
            model_name, data, completion = retry_model_name, retry_data, retry_completion
            if retry_completion["choices"][0]["text"]:
                break
    if routed_body.get("stream"):
        return Response(openai_completion_sse_from_chat(data, model_name), status=200, content_type="text/event-stream")
    return jsonify(completion)


@app.post("/v1/responses")
def openai_responses():
    body = request.get_json(silent=True) or {}
    routed_body, _routing, error_response = route_json_body(body, "/v1/responses", request.remote_addr)
    if error_response is not None:
        return error_response
    chat_payload = responses_to_chat_payload(routed_body)
    model_name, data, error_response = universal_openai_chat_json(chat_payload, request.remote_addr, "/v1/responses")
    if error_response is not None:
        return error_response
    if routed_body.get("stream"):
        return Response(responses_sse_from_chat(data, model_name), status=200, content_type="text/event-stream")
    return jsonify(responses_from_chat(data, model_name))


@app.post("/v1/embeddings")
def openai_embeddings():
    body = request.get_json(silent=True) or {}
    routed_body, _routing, error_response = route_json_body(body, "/v1/embeddings", request.remote_addr)
    if error_response is not None:
        return error_response
    model_name = extract_model_name(routed_body)
    data, error_response = universal_embeddings_json(routed_body, request.remote_addr)
    if error_response is not None:
        return error_response
    return jsonify(openai_embeddings_from_ollama(data, model_name))


@app.post("/api/embed")
@app.post("/api/embeddings")
def ollama_embeddings():
    body = request.get_json(silent=True) or {}
    routed_body, _routing, error_response = route_json_body(body, "/api/embed", request.remote_addr)
    if error_response is not None:
        return error_response
    model_id, model_info = normalize_nvidia_model(extract_model_name(routed_body))
    if model_info:
        return jsonify({"error": "modelos NVIDIA configurados neste proxy nao suportam embeddings"}), 400
    resp, error_response = upstream_request("POST", "/api/embed", request.remote_addr, json_body=routed_body, timeout=180, stream=False)
    if error_response is not None:
        return error_response
    if resp is not None and resp.status_code not in (404, 405):
        return Response(resp.content, status=resp.status_code, content_type=resp.headers.get("Content-Type", "application/json"))
    legacy_resp, legacy_error = upstream_request("POST", "/api/embeddings", request.remote_addr, json_body=routed_body, timeout=180, stream=False)
    if legacy_error is not None:
        return legacy_error
    return Response(legacy_resp.content, status=legacy_resp.status_code, content_type=legacy_resp.headers.get("Content-Type", "application/json"))


@app.post("/api/images/generate")
def nvidia_images_generate():
    body = request.get_json(silent=True) or {}
    routed_body, _routing, error_response = route_json_body(body, "/api/images/generate", request.remote_addr)
    if error_response is not None:
        return error_response
    model_id, model_info = normalize_nvidia_model(extract_model_name(routed_body))
    if not model_info:
        return jsonify({"error": "modelo NVIDIA invalido; use um nome com sufixo " + NVIDIA_SUFFIX}), 400
    if model_info.get("kind") != "image":
        return jsonify({"error": "modelo NVIDIA nao e de imagem", "kind": model_info.get("kind")}), 400
    return nvidia_image_request(model_id, model_info, routed_body, request.remote_addr)


@app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'])
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'])
def catch_all(path):
    full_path = "/" + path if path else "/"
    source_ip = request.remote_addr

    # --- Cache hit para GETs read-only ---
    if request.method == "GET" and full_path in CACHEABLE_GETS:
        body, ct, status = cache_get(full_path)
        if body is not None:
            log_message("INFO", "GET " + full_path + " -> CACHE HIT", "cache", source_ip, full_path, 0, status)
            return Response(body, status=status, content_type=ct)

    # --- Preparar request ---
    req_path = full_path
    if request.query_string:
        req_path += "?" + request.query_string.decode('utf-8')

    req_data = None
    if request.method in ('POST', 'PUT', 'PATCH'):
        req_data = request.get_data()

    base_path = full_path.split("?")[0]
    ttl = CACHEABLE_GETS.get(base_path) if request.method == "GET" else None

    if request.method == "POST" and base_path in ("/api/show", "/api/chat", "/api/generate") and req_data:
        try:
            incoming_body = json.loads(req_data.decode("utf-8") if isinstance(req_data, (bytes, bytearray)) else req_data)
        except Exception:
            incoming_body = None

        if isinstance(incoming_body, dict):
            if base_path == "/api/show":
                descriptor = find_model_descriptor(extract_model_name(incoming_body), source_ip)
                if descriptor and descriptor.get("provider") == "nvidia":
                    model_id, model_info = normalize_nvidia_model(descriptor["id"])
                    return nvidia_show_request(model_id, model_info, source_ip)
                if descriptor:
                    incoming_body = clone_body_with_model(incoming_body, descriptor["id"])
                    req_data = json.dumps(incoming_body, ensure_ascii=False).encode("utf-8")
            else:
                capability = required_capability_for_request(base_path, incoming_body)
                resolved, _requested, error_response = resolve_model_for_capability(extract_model_name(incoming_body), capability, source_ip)
                if error_response is not None:
                    return error_response
                incoming_body = clone_body_with_model(incoming_body, resolved["id"])
                if resolved.get("provider") == "nvidia":
                    model_id, model_info = normalize_nvidia_model(resolved["id"])
                    if model_info and model_info.get("kind") == "image":
                        if base_path == "/api/generate":
                            return nvidia_image_request(model_id, model_info, incoming_body, source_ip, as_ollama_generate=True)
                        return jsonify({"error": "modelo NVIDIA de imagem deve usar /api/generate ou /api/images/generate"}), 400
                    return nvidia_chat_request(model_id, incoming_body, base_path, source_ip)
                if base_path == "/api/chat":
                    incoming_body = normalize_image_urls_for_upstream(incoming_body, source_ip, base_path)
                req_data = json.dumps(incoming_body, ensure_ascii=False).encode("utf-8")

    # --- Request com retry ---
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        key_id, api_key = key_pool.get_key()
        if not api_key:
            return '{"error": "No keys available"}', 503

        start = time.time()

        try:
            headers = {"Authorization": "Bearer " + api_key}
            for h in ('Content-Type', 'Accept', 'Accept-Encoding'):
                if h in request.headers:
                    headers[h] = request.headers[h]

            if attempt == 0:
                log_message("INFO", request.method + " " + req_path, key_id, source_ip, req_path, 0, 0)

            resp = http_session.request(
                method=request.method,
                url=OLLAMA_BASE + req_path,
                headers=headers,
                data=req_data,
                stream=(ttl is None),
                timeout=120,
                allow_redirects=False
            )

            latency = time.time() - start

            # Rate limited - retry com outra key
            if resp.status_code == 429 and attempt < MAX_RETRIES:
                key_pool.report_failure(key_id, is_rate_limit=True)
                log_message("WARN", "429 key " + str(key_id) + " -> retry " + str(attempt + 1), key_id, source_ip, req_path, latency, 429)
                continue

            # 404 - key pode nao ter acesso ao modelo/endpoint - retry com outra key
            if resp.status_code == 404 and attempt < MAX_RETRIES:
                key_pool.report_failure(key_id, is_rate_limit=False)
                log_message("WARN", "404 key " + str(key_id) + " (sem acesso?) -> retry " + str(attempt + 1), key_id, source_ip, req_path, latency, 404)
                continue

            # Server error - retry com outra key
            if resp.status_code >= 500 and attempt < MAX_RETRIES:
                key_pool.report_failure(key_id, is_rate_limit=False)
                log_message("WARN", str(resp.status_code) + " key " + str(key_id) + " -> retry " + str(attempt + 1), key_id, source_ip, req_path, latency, resp.status_code)
                continue

            # Sucesso ou erro final
            if resp.status_code < 400:
                key_pool.report_success(key_id)
            else:
                key_pool.report_failure(key_id, resp.status_code == 429)

            log_message("INFO", request.method + " " + req_path + " -> HTTP " + str(resp.status_code), key_id, source_ip, req_path, latency, resp.status_code)

            # Cachear se aplicavel
            if ttl and resp.status_code == 200:
                body = resp.content
                ct = resp.headers.get("Content-Type", "application/json")
                if base_path == "/api/tags":
                    body = augment_tags_body(body)
                    ct = "application/json"
                cache_set(base_path, body, ct, 200, ttl)
                return Response(body, status=200, content_type=ct)

            # Stream
            def generate():
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        yield chunk

            response_headers = {}
            for h in ('Content-Type', 'Content-Length', 'Transfer-Encoding', 'X-Request-Id'):
                if h in resp.headers:
                    response_headers[h] = resp.headers[h]

            return Response(generate(), status=resp.status_code, headers=response_headers)

        except Exception as e:
            latency = time.time() - start
            last_error = str(e)
            key_pool.report_failure(key_id, is_rate_limit=False)
            if attempt < MAX_RETRIES:
                log_message("WARN", "Exception key " + str(key_id) + " -> retry " + str(attempt + 1), key_id, source_ip, req_path, latency, 0)
                continue
            log_message("ERROR", request.method + " " + req_path + " -> " + last_error[:80], key_id, source_ip, req_path, latency, 500)
            return json.dumps({"error": last_error}), 500

    return json.dumps({"error": last_error or "Max retries exceeded"}), 502


if __name__ == "__main__":
    log_message("INFO", "PROXY v3 INICIANDO - " + str(len(key_pool.get_stats())) + " keys")
    app.run(host=PROXY_HOST, port=PROXY_PORT, threaded=True)
