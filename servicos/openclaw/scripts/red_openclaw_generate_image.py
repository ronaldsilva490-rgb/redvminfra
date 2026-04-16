#!/usr/bin/env python3
"""Gera imagem via proxy RED e opcionalmente envia no WhatsApp pelo OpenClaw."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import subprocess
import sys
from pathlib import Path
from urllib import request as urllib_request


DEFAULT_PROXY_URL = "http://127.0.0.1:8080/api/images/generate"
DEFAULT_MODEL = "NIM - flux.2-klein-4b"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gera uma imagem no proxy RED e salva em disco. Opcionalmente envia via OpenClaw/WhatsApp."
    )
    parser.add_argument("--prompt", required=True, help="Prompt da imagem.")
    parser.add_argument("--output", required=True, help="Arquivo de saida.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Modelo de imagem do proxy RED.")
    parser.add_argument("--size", default="1024x1024", help="Tamanho alvo, ex.: 1024x1024.")
    parser.add_argument("--steps", type=int, default=4, help="Steps de inferencia.")
    parser.add_argument("--proxy-url", default=DEFAULT_PROXY_URL, help="Endpoint de imagem do proxy.")
    parser.add_argument("--caption", default="", help="Legenda para envio.")
    parser.add_argument(
        "--send-whatsapp",
        default="",
        help="Numero E.164 para enviar a imagem pelo OpenClaw/WhatsApp.",
    )
    parser.add_argument(
        "--openclaw-bin",
        default="/opt/red-openclaw/npm/bin/openclaw",
        help="Binario do OpenClaw para envio opcional.",
    )
    parser.add_argument("--json", action="store_true", help="Imprime saida em JSON.")
    return parser.parse_args()


def parse_size(size_text: str) -> tuple[int, int]:
    try:
        width_text, height_text = size_text.lower().split("x", 1)
        width = int(width_text.strip())
        height = int(height_text.strip())
        if width <= 0 or height <= 0:
            raise ValueError
        return width, height
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"Tamanho invalido: {size_text}") from exc


def generate_image(args: argparse.Namespace) -> dict:
    width, height = parse_size(args.size)
    payload = {
        "model": args.model,
        "prompt": args.prompt,
        "width": width,
        "height": height,
        "steps": args.steps,
    }
    req = urllib_request.Request(
        args.proxy_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib_request.urlopen(req, timeout=240) as response:  # noqa: S310
        body = response.read().decode("utf-8", errors="replace")
    data = json.loads(body)
    images = data.get("images") or []
    if not images:
        raise SystemExit("O proxy nao retornou imagem.")
    image = images[0]
    encoded = image.get("base64")
    if not encoded:
        raise SystemExit("Imagem retornada sem base64.")
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(base64.b64decode(encoded))
    mime_type = image.get("mime_type") or mimetypes.guess_type(str(output_path))[0] or "image/jpeg"
    return {
        "path": str(output_path),
        "model": data.get("model") or args.model,
        "seed": data.get("seed"),
        "duration_ms": data.get("duration_ms"),
        "mime_type": mime_type,
    }


def send_whatsapp(openclaw_bin: str, target: str, media_path: str, caption: str) -> None:
    base_command = [
        openclaw_bin,
        "message",
        "send",
        "--channel",
        "whatsapp",
        "--target",
        target,
        "--media",
        media_path,
    ]
    if caption:
        base_command.extend(["--message", caption])
    env = os.environ.copy()
    env["PATH"] = "/opt/red-openclaw/node/bin:/opt/red-openclaw/npm/bin:" + env.get("PATH", "")
    env["HOME"] = "/home/openclaw"
    if os.geteuid() == 0:
        command = ["sudo", "-u", "openclaw", "env", f"PATH={env['PATH']}", "HOME=/home/openclaw", *base_command]
    else:
        command = base_command
    subprocess.run(command, check=True, env=env)  # noqa: S603


def main() -> int:
    args = parse_args()
    result = generate_image(args)
    if args.send_whatsapp:
        send_whatsapp(args.openclaw_bin, args.send_whatsapp, result["path"], args.caption)
        result["sent_whatsapp"] = args.send_whatsapp
    if args.json:
        sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    else:
        sys.stdout.write(f"Imagem salva em {result['path']}\n")
        if result.get("sent_whatsapp"):
            sys.stdout.write(f"Enviada para {result['sent_whatsapp']}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
