#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import shlex
import sys
import time
from pathlib import Path
from urllib import request as urllib_request

import paramiko


sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


PROXY_PUBLIC_BASE = "http://redsystems.ddns.net/proxy"
DEFAULT_TARGET = "+558589098018"
TEXT_MODEL = "NIM - meta/llama-4-maverick-17b-128e-instruct"
VISION_MODEL = "NIM - nvidia/nemotron-nano-12b-v2-vl"
IMAGE_MODEL = "NIM - stable-diffusion-3-medium"
TTS_VOICE = "pt-BR-ThalitaMultilingualNeural"
REMOTE_OUTBOUND_DIR = "/home/openclaw/.openclaw/workspace/outbound"
OPENCLAW_JSON = "/home/openclaw/.openclaw/openclaw.json"


def http_json(url: str, payload: dict, timeout: int = 240) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib_request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib_request.urlopen(req, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8", errors="replace"))


def ssh_connect(host: str, port: int, user: str, password: str) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, port=port, username=user, password=password, timeout=30)
    return client


def run_remote(client: paramiko.SSHClient, command: str, timeout: int = 300) -> tuple[int, str, str]:
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    return stdout.channel.recv_exit_status(), out, err


def bash_quote(value: str) -> str:
    return shlex.quote(value)


def send_whatsapp_message(
    client: paramiko.SSHClient,
    target: str,
    message: str | None = None,
    media: str | None = None,
) -> dict:
    cmd = [
        "sudo",
        "-u",
        "openclaw",
        "env",
        "HOME=/home/openclaw",
        "PATH=/opt/red-openclaw/node/bin:/opt/red-openclaw/npm/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "/opt/red-openclaw/npm/bin/openclaw",
        "message",
        "send",
        "--channel",
        "whatsapp",
        "--target",
        target,
        "--json",
    ]
    if message:
        cmd.extend(["--message", message])
    if media:
        cmd.extend(["--media", media])
    started = time.perf_counter()
    code, out, err = run_remote(client, " ".join(bash_quote(part) for part in cmd), timeout=300)
    return {
        "elapsed_s": round(time.perf_counter() - started, 3),
        "code": code,
        "stdout": out.strip(),
        "stderr": err.strip(),
    }


def remote_file_bytes(client: paramiko.SSHClient, remote_path: str) -> bytes:
    sftp = client.open_sftp()
    try:
        with sftp.open(remote_path, "rb") as handle:
            return handle.read()
    finally:
        sftp.close()


def latest_inbound_image_path(client: paramiko.SSHClient) -> str:
    cmd = "bash -lc " + bash_quote(
        "latest=$(find /home/openclaw/.openclaw/media/inbound -type f \\( -name '*.jpg' -o -name '*.jpeg' -o -name '*.png' -o -name '*.webp' \\) -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -n 1 | cut -d' ' -f2-); "
        "if [ -n \"$latest\" ]; then printf '%s' \"$latest\"; else printf '/home/openclaw/.openclaw/workspace/cat.jpg'; fi"
    )
    code, out, err = run_remote(client, cmd, timeout=120)
    path = out.strip()
    if code != 0 or not path:
        raise RuntimeError(f"failed to resolve inbound image: {err or out}")
    return path


def ensure_remote_outbound_dir(client: paramiko.SSHClient) -> None:
    code, out, err = run_remote(
        client,
        "bash -lc " + bash_quote(
            f"mkdir -p {REMOTE_OUTBOUND_DIR} && chown -R openclaw:openclaw {REMOTE_OUTBOUND_DIR}"
        ),
        timeout=120,
    )
    if code != 0:
        raise RuntimeError(err or out or "failed to prepare outbound directory")


def build_data_uri(image_bytes: bytes, remote_path: str) -> str:
    suffix = Path(remote_path).suffix.lower()
    mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(suffix, "image/jpeg")
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def format_status_message(raw_status: str) -> str:
    payload = {
        "model": TEXT_MODEL,
        "temperature": 0.1,
        "max_tokens": 180,
        "messages": [
            {
                "role": "system",
                "content": "Responda em pt-BR, objetivo, em no máximo 5 linhas, como um relatório de status da VM para WhatsApp. Não use markdown pesado.",
            },
            {
                "role": "user",
                "content": "Com base nestes dados reais da VM, gere um relatório curto.\n\n" + raw_status,
            },
        ],
    }
    body = http_json(PROXY_PUBLIC_BASE + "/v1/chat/completions", payload)
    return body["choices"][0]["message"]["content"].strip()


def describe_image(remote_path: str, image_bytes: bytes) -> str:
    data_uri = build_data_uri(image_bytes, remote_path)
    payload = {
        "model": VISION_MODEL,
        "temperature": 0.1,
        "max_tokens": 220,
        "messages": [
            {
                "role": "system",
                "content": "Descreva a imagem em pt-BR de forma objetiva para WhatsApp, em até 5 linhas.",
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Analise esta imagem como se tivesse chegado pelo WhatsApp e gere um relatório curto."},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            },
        ],
    }
    body = http_json(PROXY_PUBLIC_BASE + "/v1/chat/completions", payload, timeout=300)
    return body["choices"][0]["message"]["content"].strip()


def current_primary_model(client: paramiko.SSHClient) -> str:
    code, out, err = run_remote(
        client,
        "python3 - <<'PY'\n"
        "import json\n"
        f"cfg=json.load(open('{OPENCLAW_JSON}','r',encoding='utf-8'))\n"
        "print(cfg.get('agents',{}).get('defaults',{}).get('model',{}).get('primary',''))\n"
        "PY",
        timeout=120,
    )
    if code != 0:
        raise RuntimeError(err or out or "failed to read current primary model")
    return out.strip()


def set_primary_model(client: paramiko.SSHClient, model_name: str) -> None:
    encoded = json.dumps(model_name, ensure_ascii=False)
    code, out, err = run_remote(
        client,
        "python3 - <<'PY'\n"
        "import json\n"
        f"path='{OPENCLAW_JSON}'\n"
        "with open(path,'r',encoding='utf-8') as fh:\n"
        "    cfg=json.load(fh)\n"
        f"cfg.setdefault('agents',{{}}).setdefault('defaults',{{}}).setdefault('model',{{}})['primary'] = {encoded}\n"
        "with open(path,'w',encoding='utf-8') as fh:\n"
        "    json.dump(cfg, fh, ensure_ascii=False, indent=2)\n"
        "    fh.write('\\n')\n"
        "PY",
        timeout=120,
    )
    if code != 0:
        raise RuntimeError(err or out or f"failed to set primary model to {model_name}")


def run_status_via_agent(client: paramiko.SSHClient, target: str) -> dict:
    session_id = f"bench-status-{int(time.time())}"
    cmd = [
        "sudo",
        "-u",
        "openclaw",
        "env",
        "HOME=/home/openclaw",
        "PATH=/opt/red-openclaw/node/bin:/opt/red-openclaw/npm/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "/opt/red-openclaw/npm/bin/openclaw",
        "agent",
        "--to",
        target,
        "--session-id",
        session_id,
        "--message",
        "Verifique o status atual da VM usando as tools e envie no WhatsApp um resumo objetivo em pt-BR, em no máximo 5 linhas.",
        "--thinking",
        "minimal",
        "--timeout",
        "180",
        "--deliver",
        "--json",
    ]
    started = time.perf_counter()
    code, out, err = run_remote(client, " ".join(bash_quote(part) for part in cmd), timeout=300)
    return {
        "elapsed_s": round(time.perf_counter() - started, 3),
        "code": code,
        "stdout": out.strip(),
        "stderr": err.strip(),
        "session_id": session_id,
    }


def transcode_mp3_to_ogg(client: paramiko.SSHClient, source_path: str, target_path: str) -> dict:
    cmd = " ".join(
        [
            "ffmpeg",
            "-y",
            "-i",
            bash_quote(source_path),
            "-c:a",
            "libopus",
            "-b:a",
            "48k",
            bash_quote(target_path),
        ]
    )
    started = time.perf_counter()
    code, out, err = run_remote(client, cmd, timeout=600)
    return {
        "elapsed_s": round(time.perf_counter() - started, 3),
        "code": code,
        "stdout": out.strip(),
        "stderr": err.strip(),
        "output_path": target_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Roda a bateria final de testes do OpenClaw/WhatsApp.")
    parser.add_argument("--host", default="redsystems.ddns.net")
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default=os.environ.get("REDSYSTEMS_SSH_PASSWORD", "2580"))
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument("--output", default=r"C:\Projetos\redvm\.privado\openclaw_whatsapp_tests_2026-04-20.json")
    args = parser.parse_args()

    client = ssh_connect(args.host, args.port, args.user, args.password)
    original_primary = ""
    try:
        ensure_remote_outbound_dir(client)
        original_primary = current_primary_model(client)
        set_primary_model(client, TEXT_MODEL)

        code, status_raw, status_err = run_remote(
            client,
            "bash -lc " + bash_quote("uptime; cat /proc/loadavg; free -h; df -h /; systemctl is-active ssh"),
            timeout=120,
        )
        if code != 0:
            raise RuntimeError(status_err or status_raw)

        status_message = format_status_message(status_raw)
        result_status = run_status_via_agent(client, args.target)

        inbound_path = latest_inbound_image_path(client)
        inbound_bytes = remote_file_bytes(client, inbound_path)
        vision_message = describe_image(inbound_path, inbound_bytes)
        result_vision = send_whatsapp_message(client, args.target, "Teste 2/4 - análise de imagem\n" + vision_message)

        image_output = REMOTE_OUTBOUND_DIR + "/submarino-red-test.jpg"
        image_cmd = " ".join(
            [
                "python3",
                bash_quote("/opt/red-openclaw/helpers/red_openclaw_generate_image.py"),
                "--prompt",
                bash_quote("um submarino vermelho navegando no oceano, arte limpa, luz cinematográfica, composição nítida"),
                "--output",
                bash_quote(image_output),
                "--model",
                bash_quote(IMAGE_MODEL),
                "--caption",
                bash_quote("Teste 3/4 - imagem gerada: submarino"),
                "--send-whatsapp",
                bash_quote(args.target),
                "--json",
            ]
        )
        started = time.perf_counter()
        code3, out3, err3 = run_remote(client, image_cmd, timeout=600)
        result_image = {
            "elapsed_s": round(time.perf_counter() - started, 3),
            "code": code3,
            "stdout": out3.strip(),
            "stderr": err3.strip(),
        }

        audio_output = REMOTE_OUTBOUND_DIR + "/ola-ronald-thalita.mp3"
        audio_send_output = REMOTE_OUTBOUND_DIR + "/ola-ronald-thalita.ogg"
        tts_cmd = " ".join(
            [
                "sudo",
                "-u",
                "openclaw",
                "env",
                "HOME=/home/openclaw",
                "PATH=/opt/red-openclaw/node/bin:/opt/red-openclaw/npm/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "/opt/red-openclaw/npm/bin/openclaw",
                "infer",
                "tts",
                "convert",
                "--text",
                bash_quote("Olá Ronald"),
                "--voice",
                bash_quote(TTS_VOICE),
                "--output",
                bash_quote(audio_output),
                "--json",
            ]
        )
        started = time.perf_counter()
        code4a, out4a, err4a = run_remote(client, tts_cmd, timeout=600)
        result_tts_convert = {
            "elapsed_s": round(time.perf_counter() - started, 3),
            "code": code4a,
            "stdout": out4a.strip(),
            "stderr": err4a.strip(),
        }
        result_tts_transcode = transcode_mp3_to_ogg(client, audio_output, audio_send_output)
        result_tts_send = send_whatsapp_message(
            client,
            args.target,
            "Teste 4/4 - áudio gerado dizendo Olá Ronald",
            media=audio_send_output,
        )

        payload = {
            "winners": {
                "text_tooling_candidate": TEXT_MODEL,
                "vision": VISION_MODEL,
                "image_generation": IMAGE_MODEL,
                "tts_voice": TTS_VOICE,
            },
            "status_preview": status_message,
            "vision_preview": vision_message,
            "inbound_image_path": inbound_path,
            "results": {
                "status_send": result_status,
                "vision_send": result_vision,
                "image_generate_and_send": result_image,
                "tts_convert": result_tts_convert,
                "tts_transcode": result_tts_transcode,
                "tts_send": result_tts_send,
            },
        }

        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    finally:
        if original_primary:
            try:
                set_primary_model(client, original_primary)
            except Exception:
                pass
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
