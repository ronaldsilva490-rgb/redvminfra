from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import requests


DEFAULT_BASE = "http://redsystems.ddns.net/iq-bridge"


def parse_json(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"json invalido: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit("o JSON precisa ser um objeto")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Le e atualiza a config remota do motor lab da IQ.")
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--channel", default="spy")
    parser.add_argument("--token", default="")
    parser.add_argument("--get", action="store_true")
    parser.add_argument("--set-json", help="JSON completo da config")
    args = parser.parse_args()

    headers = {"content-type": "application/json"}
    if args.token:
        headers["x-red-token"] = args.token

    base = args.base.rstrip("/")
    if args.get or not args.set_json:
        response = requests.get(
            f"{base}/api/motor/config/current",
            params={"channel": args.channel},
            timeout=20,
        )
        response.raise_for_status()
        print(json.dumps(response.json(), ensure_ascii=False, indent=2))
        return

    config = parse_json(args.set_json)
    response = requests.put(
        f"{base}/api/motor/config/current",
        headers=headers,
        json={"channel": args.channel, "config": config},
        timeout=20,
    )
    response.raise_for_status()
    print(json.dumps(response.json(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as exc:
        raise SystemExit(f"erro http: {exc}") from exc
