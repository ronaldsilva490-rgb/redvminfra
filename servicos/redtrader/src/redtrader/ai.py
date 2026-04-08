import json
import re
import time
from typing import Any

import httpx


def extract_json(text: str) -> dict[str, Any]:
    clean = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", clean, flags=re.IGNORECASE)
    if fenced:
        clean = fenced.group(1).strip()
    start = clean.find("{")
    end = clean.rfind("}")
    if start >= 0 and end > start:
        clean = clean[start : end + 1]
    return json.loads(clean)


class RedSystemsAI:
    def __init__(self, proxy_url: str):
        self.proxy_url = proxy_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=90, headers={"User-Agent": "RED-Trader/0.1"})

    async def close(self) -> None:
        await self.client.aclose()

    async def list_models(self) -> list[str]:
        response = await self.client.get(f"{self.proxy_url}/api/tags")
        response.raise_for_status()
        payload = response.json()
        models = [item.get("name") or item.get("model") for item in payload.get("models", [])]
        return sorted([model for model in models if model], key=lambda item: item.lower())

    async def chat_json(
        self,
        model: str,
        system: str,
        user: str,
        temperature: float = 0.05,
        timeout: float = 60,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        body = {
            "model": model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "format": "json",
            "options": {"temperature": temperature, "num_ctx": 4096, "num_predict": 512},
        }
        response = await self.client.post(f"{self.proxy_url}/api/chat", json=body, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        content = (payload.get("message") or {}).get("content") or payload.get("response") or ""
        parsed = extract_json(content)
        parsed["_model"] = payload.get("model") or model
        parsed["_latency_ms"] = round((time.perf_counter() - started) * 1000)
        parsed["_raw_preview"] = content[:1200]
        return parsed
