import asyncio
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
        num_predict: int = 320,
        num_ctx: int = 3072,
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
            "options": {"temperature": temperature, "num_ctx": num_ctx, "num_predict": num_predict},
        }
        deadline = time.perf_counter() + max(1.0, float(timeout))
        last_error: Exception | None = None
        last_content = ""
        for attempt in range(1, 3):
            remaining = max(1.0, deadline - time.perf_counter())
            try:
                response = await self.client.post(f"{self.proxy_url}/api/chat", json=body, timeout=remaining)
                response.raise_for_status()
                payload = response.json()
                content = (payload.get("message") or {}).get("content") or payload.get("response") or ""
                last_content = content
                parsed = extract_json(content)
                parsed["_model"] = payload.get("model") or model
                parsed["_latency_ms"] = round((time.perf_counter() - started) * 1000)
                parsed["_raw_preview"] = content[:1200]
                parsed["_attempt"] = attempt
                return parsed
            except (json.JSONDecodeError, ValueError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                last_error = exc
                should_retry = False
                if isinstance(exc, httpx.HTTPStatusError):
                    should_retry = exc.response.status_code >= 500
                else:
                    should_retry = True
                if attempt >= 2 or not should_retry or (deadline - time.perf_counter()) < 1.2:
                    break
                await asyncio.sleep(0.15)
        if last_error is not None and last_content:
            try:
                parsed = extract_json(last_content)
                parsed["_model"] = model
                parsed["_latency_ms"] = round((time.perf_counter() - started) * 1000)
                parsed["_raw_preview"] = last_content[:1200]
                parsed["_attempt"] = 2
                return parsed
            except Exception:
                pass
        if last_error is not None:
            raise last_error
        raise RuntimeError("chat_json_failed")
