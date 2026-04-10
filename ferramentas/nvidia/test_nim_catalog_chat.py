#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import paramiko
import requests


sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ROOT / "artefatos" / "catalogos" / "nvidia"
DEFAULT_LIVE_JSON = CATALOG_DIR / "nvidia_nim_models_live.json"
DEFAULT_LIVE_TXT = CATALOG_DIR / "nvidia_nim_models_live.txt"
DEFAULT_RESULTS_JSON = CATALOG_DIR / "nvidia_nim_chat_probe_results.json"
DEFAULT_RESULTS_JSONL = CATALOG_DIR / "nvidia_nim_chat_probe_results.jsonl"
NVIDIA_MODELS_URL = "https://integrate.api.nvidia.com/v1/models"
NVIDIA_CHAT_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
REMOTE_ENV_FILE = "/etc/red-ollama-proxy.env"
PROMPT = "Responda apenas OK."


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def ssh_env(name: str, default: str = "") -> str:
    return env(name, default)


def fetch_api_key_from_remote(args: argparse.Namespace) -> str:
    host = args.ssh_host or ssh_env("REDSYSTEMS_HOST")
    user = args.ssh_user or ssh_env("REDSYSTEMS_SSH_USER", "root")
    password = args.ssh_password or ssh_env("REDSYSTEMS_SSH_PASSWORD")
    port = int(args.ssh_port or ssh_env("REDSYSTEMS_SSH_PORT", "22") or "22")
    timeout = int(args.ssh_timeout or 30)
    if not host or not user or not password:
        raise SystemExit("Credenciais SSH ausentes para buscar a key do proxy na VM.")

    remote_cmd = (
        "bash -lc 'set -a; source "
        + REMOTE_ENV_FILE
        + "; set +a; python3 - <<\"PY\"\n"
        + "import os\n"
        + "print((os.environ.get(\"RED_PROXY_NVIDIA_API_KEY\") or os.environ.get(\"NVIDIA_API_KEY\") or \"\").strip())\n"
        + "PY'"
    )
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, port=port, username=user, password=password, timeout=timeout)
    try:
        _stdin, stdout, stderr = client.exec_command(remote_cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace").strip()
        err = stderr.read().decode("utf-8", errors="replace").strip()
        code = stdout.channel.recv_exit_status()
    finally:
        client.close()
    if code != 0 or not out:
        raise SystemExit("Nao consegui obter a key NVIDIA da VM. " + (err or "sem saida util"))
    return out


def resolve_api_key(args: argparse.Namespace) -> str:
    key = args.api_key or env("RED_PROXY_NVIDIA_API_KEY") or env("NVIDIA_API_KEY")
    if key:
        return key
    return fetch_api_key_from_remote(args)


def fetch_live_catalog(api_key: str) -> list[str]:
    headers = {"Authorization": "Bearer " + api_key, "Accept": "application/json"}
    response = requests.get(NVIDIA_MODELS_URL, headers=headers, timeout=120)
    response.raise_for_status()
    payload = response.json()
    raw_models = payload.get("data") or payload.get("models") or []
    models = sorted(
        {(item.get("id") or item.get("name") or "").strip() for item in raw_models if (item.get("id") or item.get("name"))},
        key=str.lower,
    )
    return [item for item in models if item]


def save_catalog(models: list[str]) -> None:
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_LIVE_JSON.write_text(json.dumps({"count": len(models), "models": models}, ensure_ascii=False, indent=2), encoding="utf-8")
    DEFAULT_LIVE_TXT.write_text("\n".join(models) + "\n", encoding="utf-8")


def load_catalog(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [str(item).strip() for item in (payload.get("models") or []) if str(item).strip()]


def probe_chat_model(api_key: str, model: str, *, prompt: str, max_tokens: int, timeout: int) -> dict[str, Any]:
    started = time.perf_counter()
    headers = {"Authorization": "Bearer " + api_key, "Content-Type": "application/json", "Accept": "application/json"}
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "top_p": 1,
        "max_tokens": max_tokens,
        "stream": False,
    }
    try:
        response = requests.post(NVIDIA_CHAT_URL, headers=headers, json=body, timeout=timeout)
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        raw_text = response.text
        if response.status_code >= 400:
            return {
                "model": model,
                "ok": False,
                "status_code": response.status_code,
                "latency_ms": latency_ms,
                "error": raw_text[:500].strip(),
            }
        payload = response.json()
        content = (
            (((payload.get("choices") or [{}])[0].get("message") or {}).get("content"))
            or (((payload.get("choices") or [{}])[0].get("delta") or {}).get("content"))
            or ""
        )
        return {
            "model": model,
            "ok": bool(str(content).strip()),
            "status_code": response.status_code,
            "latency_ms": latency_ms,
            "response": str(content).strip(),
            "raw_finish_reason": ((payload.get("choices") or [{}])[0] or {}).get("finish_reason"),
        }
    except requests.RequestException as exc:
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        return {
            "model": model,
            "ok": False,
            "status_code": 0,
            "latency_ms": latency_ms,
            "error": f"{type(exc).__name__}: {exc}",
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Baixa o catalogo atual da NVIDIA NIM e testa resposta de chat modelo por modelo.")
    parser.add_argument("--api-key", default="", help="Key NVIDIA direta. Se omitida, tenta env local e depois a VM.")
    parser.add_argument("--ssh-host", default="", help="Host da VM para buscar a key do proxy.")
    parser.add_argument("--ssh-port", default="", help="Porta SSH da VM.")
    parser.add_argument("--ssh-user", default="", help="Usuario SSH da VM.")
    parser.add_argument("--ssh-password", default="", help="Senha SSH da VM.")
    parser.add_argument("--ssh-timeout", default="30", help="Timeout SSH em segundos.")
    parser.add_argument("--prompt", default=PROMPT, help="Pergunta simples usada no probe.")
    parser.add_argument("--max-tokens", type=int, default=16, help="max_tokens do teste.")
    parser.add_argument("--timeout", type=int, default=60, help="Timeout HTTP do teste por modelo.")
    parser.add_argument("--start", type=int, default=1, help="Indice 1-based para comecar o teste.")
    parser.add_argument("--limit", type=int, default=0, help="Limite de modelos a testar nesta execucao.")
    parser.add_argument("--only", default="", help="Testa so um modelo especifico.")
    parser.add_argument("--refresh-catalog", action="store_true", help="Forca baixar a lista viva atual da NVIDIA.")
    parser.add_argument("--catalog", default=str(DEFAULT_LIVE_JSON), help="Arquivo json do catalogo.")
    return parser.parse_args()


def select_models(models: list[str], args: argparse.Namespace) -> list[str]:
    if args.only:
        return [args.only]
    start = max(1, args.start)
    subset = models[start - 1 :]
    if args.limit and args.limit > 0:
        subset = subset[: args.limit]
    return subset


def main() -> int:
    args = parse_args()
    api_key = resolve_api_key(args)

    catalog_path = Path(args.catalog)
    if args.refresh_catalog or not catalog_path.exists():
        models = fetch_live_catalog(api_key)
        save_catalog(models)
    else:
        models = load_catalog(catalog_path)
    models = sorted(models, key=str.lower)
    selected = select_models(models, args)
    if not selected:
        raise SystemExit("Nenhum modelo selecionado para teste.")

    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    with DEFAULT_RESULTS_JSONL.open("a", encoding="utf-8") as jsonl:
        for index, model in enumerate(selected, start=1):
            result = probe_chat_model(api_key, model, prompt=args.prompt, max_tokens=args.max_tokens, timeout=args.timeout)
            result["sequence"] = index
            result["catalog_position"] = models.index(model) + 1 if model in models else None
            results.append(result)
            jsonl.write(json.dumps(result, ensure_ascii=False) + "\n")
            jsonl.flush()
            if result.get("ok"):
                print(f"[{result['catalog_position']:03d}] OK   {model} :: {result.get('latency_ms')}ms :: {result.get('response','')[:120]}")
            else:
                print(f"[{result['catalog_position']:03d}] FAIL {model} :: {result.get('latency_ms')}ms :: {result.get('status_code')} :: {result.get('error','')[:160]}")

    summary = {
        "count_catalog": len(models),
        "count_tested": len(results),
        "count_ok": sum(1 for item in results if item.get("ok")),
        "count_fail": sum(1 for item in results if not item.get("ok")),
        "prompt": args.prompt,
        "tested_models": selected,
        "results": results,
    }
    DEFAULT_RESULTS_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nResumo:")
    print(json.dumps({k: summary[k] for k in ("count_catalog", "count_tested", "count_ok", "count_fail")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
