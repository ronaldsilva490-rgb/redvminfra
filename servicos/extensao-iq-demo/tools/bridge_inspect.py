from __future__ import annotations

import argparse
import json
import io
import sys
from typing import Any

import requests


DEFAULT_BASE = "http://redsystems2.ddns.net:3115"
DEFAULT_SESSION = "chrome-extension:peimfeacggmdcmjfookmdadjjaebmfig"

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def get_json(url: str, **params: Any) -> dict[str, Any]:
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def summarize_telemetry(item: dict[str, Any]) -> dict[str, Any]:
    payload = item.get("payload") or {}
    debug = payload.get("debug") or {}
    ids = debug.get("ids") or {}
    return {
        "id": item.get("id"),
        "asset": item.get("asset"),
        "market_type": item.get("market_type"),
        "current_price": item.get("current_price"),
        "payout_pct": item.get("payout_pct"),
        "selected": ids.get("selectedAssetId"),
        "quote": ids.get("quoteActiveId"),
        "live": ids.get("liveActiveId"),
        "resolution": debug.get("resolution"),
        "live_price": debug.get("livePrice"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspeciona o RED IQ bridge.")
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--session", default=DEFAULT_SESSION)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--asset", default="")
    parser.add_argument("--event", default="")
    parser.add_argument("--contains", default="")
    parser.add_argument("--telemetry", action="store_true")
    parser.add_argument("--logs", action="store_true")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    if not args.telemetry and not args.logs:
        args.telemetry = True
        args.logs = True

    if args.telemetry:
        data = get_json(
            f"{args.base.rstrip('/')}/api/telemetry/recent",
            limit=args.limit,
            asset=args.asset,
            session_id=args.session,
        )
        if args.summary:
            print_json([summarize_telemetry(item) for item in data.get("items", [])])
        else:
            print_json(data)

    if args.logs:
        data = get_json(
            f"{args.base.rstrip('/')}/api/logs/recent",
            limit=args.limit,
            event=args.event,
            contains=args.contains,
            asset=args.asset,
            session_id=args.session,
        )
        print_json(data)


if __name__ == "__main__":
    main()
