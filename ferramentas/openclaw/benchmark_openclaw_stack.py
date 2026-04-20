#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path

import paramiko


def run_remote(client: paramiko.SSHClient, command: str, timeout: int = 1200) -> tuple[int, str, str]:
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    return code, out, err


def run_remote_python(client: paramiko.SSHClient, script: str, timeout: int = 1200) -> dict:
    encoded = base64.b64encode(script.encode("utf-8")).decode("ascii")
    command = (
        "python3 - <<'PY'\n"
        "import base64, subprocess, sys\n"
        f"script = base64.b64decode('{encoded}').decode('utf-8')\n"
        "ns = {}\n"
        "exec(compile(script, '<benchmark>', 'exec'), ns, ns)\n"
        "PY"
    )
    code, out, err = run_remote(client, command, timeout=timeout)
    if code != 0:
        raise RuntimeError(f"remote python failed ({code})\nSTDOUT:\n{out}\nSTDERR:\n{err}")
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid json from remote script\nSTDOUT:\n{out}\nSTDERR:\n{err}") from exc


REMOTE_BENCHMARK_SCRIPT = r"""
import base64
import json
import os
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib import request as urllib_request


PROXY_BASE = "http://127.0.0.1:8080"
TTS_BIN = "/opt/red-openclaw/npm/bin/openclaw"
TTS_ENV = {
    "HOME": "/home/openclaw",
    "PATH": "/opt/red-openclaw/node/bin:/opt/red-openclaw/npm/bin:" + os.environ.get("PATH", ""),
}


def http_json(url: str, payload: dict | None = None, timeout: int = 240) -> dict:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib_request.Request(url, data=data, headers=headers, method="POST" if payload is not None else "GET")
    with urllib_request.urlopen(req, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8", errors="replace"))


def post_raw(url: str, payload: dict, timeout: int = 240) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib_request.Request(
        url,
        data=data,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    with urllib_request.urlopen(req, timeout=timeout) as response:  # noqa: S310
        body = response.read().decode("utf-8", errors="replace")
        elapsed = time.perf_counter() - started
        return response.status, {"elapsed": elapsed, "body": json.loads(body)}


def refusalish(text: str) -> bool:
    lowered = (text or "").lower()
    bad = [
        "não posso",
        "nao posso",
        "desculpe",
        "sorry",
        "i can't",
        "i cannot",
        "não tenho",
        "nao tenho",
    ]
    return any(token in lowered for token in bad)


def latest_inbound_image() -> str:
    inbound = Path("/home/openclaw/.openclaw/media/inbound")
    candidates = sorted(
        [p for p in inbound.glob("*") if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if candidates:
        return str(candidates[0])
    return "/home/openclaw/.openclaw/workspace/cat.jpg"


def image_data_uri(path: str) -> str:
    p = Path(path)
    suffix = p.suffix.lower()
    mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(suffix, "image/jpeg")
    encoded = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


MODELS = http_json(PROXY_BASE + "/v1/models")["data"]
CHAT_MODELS = [m["id"] for m in MODELS if "chat" in (m.get("red", {}).get("capabilities") or []) and m.get("red", {}).get("kind") == "chat"]
VISION_MODELS = [m["id"] for m in MODELS if "vision" in (m.get("red", {}).get("capabilities") or [])]
IMAGE_MODELS = [m["id"] for m in MODELS if "image_generation" in (m.get("red", {}).get("capabilities") or [])]
IMAGE_PATH = latest_inbound_image()
IMAGE_URI = image_data_uri(IMAGE_PATH)


def bench_text_model(model_id: str) -> dict:
    payload = {
        "model": model_id,
        "temperature": 0.2,
        "max_tokens": 120,
        "messages": [
            {"role": "system", "content": "Responda em pt-BR, de forma objetiva, em no máximo 4 linhas e sem markdown."},
            {
                "role": "user",
                "content": "Resuma este status operacional: CPU 0.10, memória 17%, disco 17%, SSH ativo, OpenClaw conectado.",
            },
        ],
    }
    result = {"model": model_id, "task": "text", "ok": False}
    try:
        status, response = post_raw(PROXY_BASE + "/v1/chat/completions", payload, timeout=180)
        body = response["body"]
        text = ((body.get("choices") or [{}])[0].get("message") or {}).get("content", "")
        usage = body.get("usage") or {}
        completion_tokens = int(usage.get("completion_tokens") or 0)
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        elapsed = float(response["elapsed"])
        result.update(
            {
                "ok": status == 200 and bool(text.strip()) and not refusalish(text),
                "status": status,
                "elapsed_s": round(elapsed, 3),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "completion_tps": round(completion_tokens / elapsed, 3) if completion_tokens and elapsed > 0 else 0.0,
                "total_tps": round((prompt_tokens + completion_tokens) / elapsed, 3) if (prompt_tokens + completion_tokens) and elapsed > 0 else 0.0,
                "preview": text[:220],
                "refusalish": refusalish(text),
            }
        )
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    return result


def bench_vision_model(model_id: str) -> dict:
    payload = {
        "model": model_id,
        "temperature": 0.2,
        "max_tokens": 220,
        "messages": [
            {"role": "system", "content": "Descreva a imagem em pt-BR, de forma objetiva, em no máximo 5 linhas."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Descreva exatamente o que aparece nesta imagem."},
                    {"type": "image_url", "image_url": {"url": IMAGE_URI}},
                ],
            },
        ],
    }
    result = {"model": model_id, "task": "vision", "ok": False}
    try:
        status, response = post_raw(PROXY_BASE + "/v1/chat/completions", payload, timeout=240)
        body = response["body"]
        text = ((body.get("choices") or [{}])[0].get("message") or {}).get("content", "")
        usage = body.get("usage") or {}
        completion_tokens = int(usage.get("completion_tokens") or 0)
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        elapsed = float(response["elapsed"])
        result.update(
            {
                "ok": status == 200 and bool(text.strip()) and not refusalish(text),
                "status": status,
                "elapsed_s": round(elapsed, 3),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "completion_tps": round(completion_tokens / elapsed, 3) if completion_tokens and elapsed > 0 else 0.0,
                "total_tps": round((prompt_tokens + completion_tokens) / elapsed, 3) if (prompt_tokens + completion_tokens) and elapsed > 0 else 0.0,
                "preview": text[:220],
                "refusalish": refusalish(text),
                "image_path": IMAGE_PATH,
            }
        )
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
        result["image_path"] = IMAGE_PATH
    return result


def bench_image_model(model_id: str) -> dict:
    payload = {
        "model": model_id,
        "prompt": "um submarino vermelho navegando no oceano, arte limpa, luz cinematográfica, composição nítida",
        "width": 1024,
        "height": 1024,
        "steps": 4,
    }
    result = {"model": model_id, "task": "image_generation", "ok": False}
    try:
        status, response = post_raw(PROXY_BASE + "/api/images/generate", payload, timeout=480)
        body = response["body"]
        images = body.get("images") or []
        first = images[0] if images else {}
        elapsed = float(response["elapsed"])
        base64_size = len(first.get("base64") or "")
        result.update(
            {
                "ok": status == 200 and bool(base64_size),
                "status": status,
                "elapsed_s": round(elapsed, 3),
                "duration_ms": body.get("duration_ms"),
                "seed": body.get("seed"),
                "base64_size": base64_size,
            }
        )
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    return result


def bench_tts_voice(voice_id: str) -> dict:
    output = f"/tmp/{voice_id.replace('/', '_')}.wav"
    command = [
        "sudo",
        "-u",
        "openclaw",
        "env",
        f"PATH={TTS_ENV['PATH']}",
        f"HOME={TTS_ENV['HOME']}",
        TTS_BIN,
        "infer",
        "tts",
        "convert",
        "--text",
        "Olá Ronald",
        "--voice",
        voice_id,
        "--output",
        output,
        "--json",
    ]
    started = time.perf_counter()
    result = {"voice": voice_id, "task": "tts", "ok": False}
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=240, check=False)
        elapsed = time.perf_counter() - started
        payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
        file_size = Path(output).stat().st_size if Path(output).exists() else 0
        result.update(
            {
                "ok": proc.returncode == 0 and file_size > 0,
                "returncode": proc.returncode,
                "elapsed_s": round(elapsed, 3),
                "output_path": output,
                "file_size": file_size,
                "preview": payload,
                "stderr": proc.stderr[-300:] if proc.stderr else "",
            }
        )
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    return result


def run_pool(items, fn, workers: int = 4) -> list[dict]:
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {pool.submit(fn, item): item for item in items}
        for future in as_completed(future_map):
            results.append(future.result())
    return results


text_results = run_pool(CHAT_MODELS, bench_text_model, workers=4)
vision_results = run_pool(VISION_MODELS, bench_vision_model, workers=3)
image_results = run_pool(IMAGE_MODELS, bench_image_model, workers=2)
tts_voices = ["pt-BR-FranciscaNeural", "pt-BR-AntonioNeural", "pt-BR-ThalitaMultilingualNeural"]
tts_results = [bench_tts_voice(voice) for voice in tts_voices]

def rank(results, key):
    good = [r for r in results if r.get("ok")]
    return sorted(good, key=key)

payload = {
    "image_path": IMAGE_PATH,
    "counts": {
        "text_models": len(CHAT_MODELS),
        "vision_models": len(VISION_MODELS),
        "image_models": len(IMAGE_MODELS),
        "tts_voices": len(tts_voices),
    },
    "text_results": text_results,
    "vision_results": vision_results,
    "image_results": image_results,
    "tts_results": tts_results,
    "best": {
        "text_fastest_tps": sorted(
            [r for r in text_results if r.get("ok")],
            key=lambda r: (-r.get("completion_tps", 0.0), r.get("elapsed_s", 9999.0))
        )[:10],
        "vision_fastest_tps": sorted(
            [r for r in vision_results if r.get("ok")],
            key=lambda r: (-r.get("completion_tps", 0.0), r.get("elapsed_s", 9999.0))
        )[:10],
        "image_fastest_latency": sorted(
            [r for r in image_results if r.get("ok")],
            key=lambda r: (r.get("elapsed_s", 9999.0), -r.get("base64_size", 0))
        )[:10],
        "tts_fastest_latency": sorted(
            [r for r in tts_results if r.get("ok")],
            key=lambda r: (r.get("elapsed_s", 9999.0), -r.get("file_size", 0))
        )[:10],
    },
}
print(json.dumps(payload, ensure_ascii=False))
"""


def connect(host: str, user: str, password: str, port: int) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, port=port, username=user, password=password, timeout=30)
    return client


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark OpenClaw/proxy models on the RED VM.")
    parser.add_argument("--host", default="redsystems.ddns.net")
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default=os.environ.get("REDSYSTEMS_SSH_PASSWORD", "2580"))
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    client = connect(args.host, args.user, args.password, args.port)
    try:
        result = run_remote_python(client, REMOTE_BENCHMARK_SCRIPT, timeout=5400)
    finally:
        client.close()

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        out_path = Path(args.output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
