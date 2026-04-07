from flask import Flask, request, Response, jsonify
import requests
import json
import os
import random
import time
import uuid
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


def normalize_nvidia_model(model_name):
    if not isinstance(model_name, str):
        return None, None
    raw = model_name.strip()
    suffix = NVIDIA_SUFFIX.lower()
    if raw.lower().endswith(suffix):
        model_id = raw[: -len(NVIDIA_SUFFIX)].strip()
        return model_id, NVIDIA_MODEL_MAP.get(model_id.lower())
    return None, None


def is_nvidia_request_body(raw_body):
    try:
        body = json.loads(raw_body.decode("utf-8") if isinstance(raw_body, (bytes, bytearray)) else raw_body)
    except Exception:
        return False, None, None
    model_id, model_info = normalize_nvidia_model(body.get("model"))
    return model_info is not None, body, model_id


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
    payload = {
        "model": model_id,
        "messages": messages,
        "temperature": body.get("temperature", options.get("temperature", 0.4)),
        "max_tokens": int(max_tokens),
        "stream": bool(body.get("stream", False)),
    }
    top_p = body.get("top_p", options.get("top_p"))
    if top_p is not None:
        payload["top_p"] = top_p
    return payload


def nvidia_headers(content_type="application/json"):
    return {
        "Authorization": "Bearer " + NVIDIA_API_KEY,
        "Accept": "application/json",
        "Content-Type": content_type,
    }


def nvidia_chat_request(model_id, body, base_path, source_ip):
    if not NVIDIA_API_KEY:
        return jsonify({"error": "RED_PROXY_NVIDIA_API_KEY not configured"}), 503

    payload = nvidia_chat_payload(body, model_id, base_path)
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
                for line in upstream.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    if line.startswith("data: "):
                        line = line[6:]
                    if line.strip() == "[DONE]":
                        break
                    try:
                        item = json.loads(line)
                        delta = item.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content") or ""
                    except Exception:
                        content = ""
                    if not content:
                        continue
                    if base_path == "/api/generate":
                        chunk = {"model": nvidia_display_name(model_id), "created_at": utc_created_at(), "response": content, "done": False}
                    else:
                        chunk = {"model": nvidia_display_name(model_id), "created_at": utc_created_at(), "message": {"role": "assistant", "content": content}, "done": False}
                    yield json.dumps(chunk, ensure_ascii=False) + "\n"
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
            "cache": cache_stats(),
            "files": {
                "keys_file": KEYS_FILE,
                "logs_file": LOGS_FILE,
            },
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
    )


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
            "models": [
                {
                    "id": model["id"],
                    "name": nvidia_display_name(model["id"]),
                    "kind": model["kind"],
                    "family": model["family"],
                    "note": model.get("note", ""),
                }
                for model in NVIDIA_MODELS
            ],
        }
    )


@app.post("/api/images/generate")
def nvidia_images_generate():
    body = request.get_json(silent=True) or {}
    model_id, model_info = normalize_nvidia_model(body.get("model"))
    if not model_info:
        return jsonify({"error": "modelo NVIDIA invalido; use um nome com sufixo " + NVIDIA_SUFFIX}), 400
    if model_info.get("kind") != "image":
        return jsonify({"error": "modelo NVIDIA nao e de imagem", "kind": model_info.get("kind")}), 400
    return nvidia_image_request(model_id, model_info, body, request.remote_addr)


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

    if request.method == "POST" and base_path in ("/api/chat", "/api/generate") and req_data:
        is_nvidia, nvidia_body, model_id = is_nvidia_request_body(req_data)
        if is_nvidia:
            model_info = NVIDIA_MODEL_MAP.get(model_id.lower())
            if model_info and model_info.get("kind") == "image":
                if base_path == "/api/generate":
                    return nvidia_image_request(model_id, model_info, nvidia_body, source_ip, as_ollama_generate=True)
                return jsonify({"error": "modelo NVIDIA de imagem deve usar /api/generate ou /api/images/generate"}), 400
            return nvidia_chat_request(model_id, nvidia_body, base_path, source_ip)

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
