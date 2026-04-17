from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import requests


PROXY_BASE = "http://redsystems.ddns.net/ollama"
BRIDGE_BASE = "http://redsystems.ddns.net/iq-bridge"
OUTPUT_DIR = Path("artefatos/iq_vision_benchmark")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


PROMPT = """Leia esta captura da IQ Option e responda APENAS em JSON.

Extraia exatamente estes campos:
{
  "asset": "string",
  "market": "string",
  "payout_pct": number|null,
  "countdown": "string|null",
  "invest_amount": "string|null",
  "expiry": "string|null",
  "call_label": "string|null",
  "put_label": "string|null",
  "new_option_visible": boolean|null,
  "confidence": number
}

Regras:
- Se nao tiver certeza, use null no campo.
- payout_pct deve ser o percentual visivel na tela principal de negociacao.
- asset deve refletir exatamente o ativo selecionado na tela.
- market deve ser algo como Binaria, Blitz, Digital.
- confidence vai de 0 a 100.
"""


@dataclass
class BenchResult:
    model: str
    route_model: str
    provider: str
    latency_ms: float
    ok: bool
    asset: str | None
    market: str | None
    payout_pct: float | None
    countdown: str | None
    invest_amount: str | None
    expiry: str | None
    call_label: str | None
    put_label: str | None
    new_option_visible: bool | None
    confidence: float | None
    raw_text: str
    error: str


def extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except Exception:
        return {}


def get_latest_frame() -> dict[str, Any]:
    resp = requests.get(f"{BRIDGE_BASE}/api/latest-frame", timeout=30)
    resp.raise_for_status()
    data = resp.json()
    item = data.get("item")
    if not item:
        raise RuntimeError("Bridge ainda nao tem frame salvo. Recarregue a extensao e troque de ativo.")
    payload = item.get("payload") or {}
    image_data_url = payload.get("imageDataUrl")
    if not image_data_url:
        raise RuntimeError("Ultimo frame nao tem imageDataUrl no payload.")
    return {"item": item, "image_data_url": image_data_url}


def get_vision_models() -> list[dict[str, Any]]:
    resp = requests.get(f"{PROXY_BASE}/v1/models", timeout=30)
    resp.raise_for_status()
    models = resp.json().get("data") or []
    vision = [m for m in models if "vision" in ((m.get("red") or {}).get("capabilities") or [])]
    vision.sort(key=lambda item: str(item.get("id") or "").lower())
    return vision


def run_model(model: dict[str, Any], image_data_url: str) -> BenchResult:
    model_id = str(model.get("id") or "")
    red = model.get("red") or {}
    body = {
        "model": model_id,
        "stream": False,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            }
        ],
    }
    started = time.perf_counter()
    try:
        resp = requests.post(f"{PROXY_BASE}/v1/chat/completions", json=body, timeout=90)
        latency_ms = (time.perf_counter() - started) * 1000
        resp.raise_for_status()
        data = resp.json()
        message = (((data.get("choices") or [{}])[0]).get("message") or {})
        content = message.get("content") or ""
        parsed = extract_json(content)
        return BenchResult(
            model=model_id,
            route_model=str(red.get("route_model") or ""),
            provider=str(red.get("provider") or ""),
            latency_ms=round(latency_ms, 1),
            ok=True,
            asset=parsed.get("asset"),
            market=parsed.get("market"),
            payout_pct=parsed.get("payout_pct"),
            countdown=parsed.get("countdown"),
            invest_amount=parsed.get("invest_amount"),
            expiry=parsed.get("expiry"),
            call_label=parsed.get("call_label"),
            put_label=parsed.get("put_label"),
            new_option_visible=parsed.get("new_option_visible"),
            confidence=parsed.get("confidence"),
            raw_text=content,
            error="",
        )
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000
        return BenchResult(
            model=model_id,
            route_model=str(red.get("route_model") or ""),
            provider=str(red.get("provider") or ""),
            latency_ms=round(latency_ms, 1),
            ok=False,
            asset=None,
            market=None,
            payout_pct=None,
            countdown=None,
            invest_amount=None,
            expiry=None,
            call_label=None,
            put_label=None,
            new_option_visible=None,
            confidence=None,
            raw_text="",
            error=str(exc),
        )


def main() -> None:
    latest = get_latest_frame()
    models = get_vision_models()
    print(f"Frame: {latest['item'].get('asset')} | modelos vision: {len(models)}")
    results: list[BenchResult] = []
    for index, model in enumerate(models, start=1):
        result = run_model(model, latest["image_data_url"])
        results.append(result)
        status = "OK" if result.ok else "ERR"
        summary = f"{result.asset or '-'} | {result.market or '-'} | payout={result.payout_pct!s}"
        print(f"[{index:02d}/{len(models):02d}] {status} {result.model} | {result.latency_ms:.1f}ms | {summary or result.error}")

    stamp = int(time.time())
    output = {
        "created_at": stamp,
        "frame": latest["item"],
        "results": [asdict(item) for item in results],
    }
    target = OUTPUT_DIR / f"latest_frame_benchmark_{stamp}.json"
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSalvo em: {target}")


if __name__ == "__main__":
    main()
