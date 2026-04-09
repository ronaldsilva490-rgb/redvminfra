from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

import requests

sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)


DEFAULT_BASE = "http://redsystems2.ddns.net:3115"
DEFAULT_SESSION = "chrome-extension:peimfeacggmdcmjfookmdadjjaebmfig"


def parse_payload(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"payload JSON invalido: {exc}") from exc


def create_command(base: str, session_id: str, command: str, payload: dict[str, Any]) -> int:
    response = requests.post(
        f"{base.rstrip('/')}/api/commands",
        json={
            "sessionId": session_id,
            "command": command,
            "payload": payload,
        },
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    return int(data["id"])


def list_commands(base: str, limit: int) -> list[dict[str, Any]]:
    response = requests.get(f"{base.rstrip('/')}/api/commands", params={"limit": limit}, timeout=20)
    response.raise_for_status()
    return response.json().get("items", [])


def wait_for_command(base: str, command_id: int, timeout_s: float, interval_s: float) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        items = list_commands(base, 100)
        for item in items:
            if int(item["id"]) != int(command_id):
                continue
            if item["status"] in {"done", "failed"}:
                return item
        time.sleep(interval_s)
    raise SystemExit(f"timeout esperando comando #{command_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Dispara comandos para a RED IQ Demo Vision via bridge.")
    parser.add_argument("command", nargs="?", help="Comando remoto, ex: dump_transport, list_targets, click_text")
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--session", default=DEFAULT_SESSION)
    parser.add_argument("--payload", help="JSON do payload")
    parser.add_argument("--wait", action="store_true", help="Espera o resultado do comando")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--list", action="store_true", help="Lista comandos recentes e sai")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    if args.list:
        items = list_commands(args.base, args.limit)
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return

    if not args.command:
        raise SystemExit("informe um comando ou use --list")

    payload = parse_payload(args.payload)
    command_id = create_command(args.base, args.session, args.command, payload)
    print(json.dumps({"ok": True, "id": command_id}, ensure_ascii=False))

    if args.wait:
        item = wait_for_command(args.base, command_id, args.timeout, args.interval)
        print(json.dumps(item, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as exc:
        raise SystemExit(f"erro HTTP: {exc}") from exc
