import asyncio
import json
import re
import time
from typing import Any

import httpx


def _strip_fences(text: str) -> str:
    clean = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", clean, flags=re.IGNORECASE)
    if fenced:
        clean = fenced.group(1).strip()
    return clean


def _extract_first_json_blob(text: str) -> str:
    clean = _strip_fences(text)
    start = clean.find("{")
    end = clean.rfind("}")
    if start >= 0 and end > start:
        return clean[start : end + 1]
    if start >= 0:
        return clean[start:]
    return clean


def _json_load_first_object(text: str) -> dict[str, Any]:
    clean = _extract_first_json_blob(text)
    decoder = json.JSONDecoder()
    start = clean.find("{")
    if start >= 0:
        obj, _end = decoder.raw_decode(clean[start:])
        if isinstance(obj, dict):
            return obj
    parsed = json.loads(clean)
    if isinstance(parsed, dict):
        return parsed
    raise json.JSONDecodeError("Root JSON is not an object", clean, 0)


def _search_str(text: str, field: str) -> str | None:
    match = re.search(rf'"{re.escape(field)}"\s*:\s*"([^"]*)', text, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def _search_num(text: str, field: str) -> float | int | None:
    match = re.search(rf'"{re.escape(field)}"\s*:\s*(-?\d+(?:\.\d+)?)', text, flags=re.IGNORECASE)
    if not match:
        return None
    raw = match.group(1)
    if "." in raw:
        return float(raw)
    return int(raw)


def _search_bool(text: str, field: str) -> bool | None:
    match = re.search(rf'"{re.escape(field)}"\s*:\s*(true|false)', text, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).lower() == "true"


def _salvage_checks(text: str) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    checks_match = re.search(r'"checks"\s*:\s*\{([\s\S]*?)\}', text, flags=re.IGNORECASE)
    if not checks_match:
        return checks
    block = checks_match.group(1)
    for key in ["trend", "momentum", "volatility", "liquidity", "news_risk", "risk_reward", "code_edge"]:
        value = _search_str(block, key)
        if value is not None:
            checks[key] = value
    return checks


def _salvage_partial_json(text: str) -> dict[str, Any]:
    clean = _extract_first_json_blob(text)
    partial: dict[str, Any] = {}
    for key in ["decision", "preferred_decision", "symbol", "risk_level", "invalidation", "reasoning_summary", "reason"]:
        value = _search_str(clean, key)
        if value is not None:
            partial[key] = value
    for key in ["confidence", "position_pct", "time_horizon_min", "stop_loss_pct", "take_profit_pct", "risk_reward", "next_review_minutes"]:
        value = _search_num(clean, key)
        if value is not None:
            partial[key] = value
    veto = _search_bool(clean, "veto")
    if veto is not None:
        partial["veto"] = veto
    checks = _salvage_checks(clean)
    if checks:
        partial["checks"] = checks
    if not partial:
        raise json.JSONDecodeError("Could not salvage partial JSON", clean, 0)
    return partial


def extract_json(text: str) -> dict[str, Any]:
    try:
        return _json_load_first_object(text)
    except json.JSONDecodeError:
        return _salvage_partial_json(text)


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
        max_attempts: int = 2,
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
        max_attempts = max(1, int(max_attempts))
        for attempt in range(1, max_attempts + 1):
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
                if attempt >= max_attempts or not should_retry or (deadline - time.perf_counter()) < 1.2:
                    break
                await asyncio.sleep(0.15)
        if last_error is not None and last_content:
            try:
                parsed = extract_json(last_content)
                parsed["_model"] = model
                parsed["_latency_ms"] = round((time.perf_counter() - started) * 1000)
                parsed["_raw_preview"] = last_content[:1200]
                parsed["_attempt"] = max_attempts
                return parsed
            except Exception:
                pass
        if last_error is not None:
            raise last_error
        raise RuntimeError("chat_json_failed")
