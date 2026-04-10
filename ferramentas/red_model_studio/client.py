from __future__ import annotations

import base64
import json
import re
import socket
import time
from dataclasses import dataclass, field
from html import escape
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

import requests


THINK_BLOCK_RE = re.compile(r"<think>(.*?)</think>", re.IGNORECASE | re.DOTALL)


def normalize_base_url(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "http://redsystems.ddns.net/ollama"
    if not re.match(r"^https?://", text, re.IGNORECASE):
        text = "http://" + text
    return text.rstrip("/")


def join_url(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def safe_json(response: requests.Response) -> Any:
    try:
        return response.json()
    except Exception as exc:
        raise RuntimeError(f"Resposta invalida do proxy: {exc}") from exc


def first_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                item_type = item.get("type")
                if item_type in {"text", "output_text", "input_text"}:
                    parts.append(str(item.get("text") or ""))
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        if "text" in value:
            return str(value.get("text") or "")
    return str(value)


def split_reasoning(answer_text: str, reasoning_text: str) -> tuple[str, str]:
    reasoning = str(reasoning_text or "").strip()
    answer = str(answer_text or "").strip()
    if reasoning:
        return reasoning, answer
    if not answer:
        return "", ""
    matches = list(THINK_BLOCK_RE.finditer(answer))
    if not matches:
        return "", answer
    thoughts = [match.group(1).strip() for match in matches if match.group(1).strip()]
    visible = THINK_BLOCK_RE.sub("", answer).strip()
    return "\n\n".join(thoughts).strip(), visible


@dataclass(slots=True)
class ModelInfo:
    id: str
    provider: str = ""
    kind: str = ""
    capabilities: list[str] = field(default_factory=list)
    route_model: str = ""
    note: str = ""
    owned_by: str = ""

    @property
    def supports_chat(self) -> bool:
        return "chat" in self.capabilities

    @property
    def supports_image(self) -> bool:
        return "image_generation" in self.capabilities

    @property
    def supports_vision(self) -> bool:
        return "vision" in self.capabilities


@dataclass(slots=True)
class ChatMetrics:
    total_ms: int = 0
    first_token_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    tokens_per_second: float | None = None
    finish_reason: str = ""
    response_model: str = ""


@dataclass(slots=True)
class ChatResult:
    answer: str
    thinking: str
    metrics: ChatMetrics
    raw_chunks: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class ImageResult:
    model: str
    mime_type: str
    image_bytes: bytes
    duration_ms: int
    seed: str
    width: int
    height: int


class RedProxyClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = normalize_base_url(base_url)
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def endpoint(self, path: str) -> str:
        return join_url(self.base_url, path)

    def ping_latency_ms(self, timeout: float = 3.0) -> float:
        parsed = urlparse(self.base_url)
        host = parsed.hostname or "redsystems.ddns.net"
        if parsed.port:
            port = parsed.port
        elif parsed.scheme == "https":
            port = 443
        else:
            port = 80
        started = time.perf_counter()
        with socket.create_connection((host, port), timeout=timeout):
            return (time.perf_counter() - started) * 1000.0

    def fetch_models(self) -> list[ModelInfo]:
        response = self.session.get(self.endpoint("/v1/models"), timeout=20)
        response.raise_for_status()
        payload = safe_json(response)
        models: list[ModelInfo] = []
        for item in payload.get("data") or []:
            red = item.get("red") or {}
            models.append(
                ModelInfo(
                    id=str(item.get("id") or "").strip(),
                    provider=str(red.get("provider") or item.get("owned_by") or "").strip(),
                    kind=str(red.get("kind") or "").strip(),
                    capabilities=list(red.get("capabilities") or []),
                    route_model=str(red.get("route_model") or "").strip(),
                    note=str(red.get("note") or "").strip(),
                    owned_by=str(item.get("owned_by") or "").strip(),
                )
            )
        models.sort(key=lambda model: model.id.lower())
        return models

    def chat_stream(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        system_prompt: str = "",
        on_delta: Callable[[dict[str, Any]], None] | None = None,
    ) -> ChatResult:
        request_messages = []
        if system_prompt.strip():
            request_messages.append({"role": "system", "content": system_prompt.strip()})
        request_messages.extend(messages)

        payload = {
            "model": model,
            "messages": request_messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        started = time.perf_counter()
        response = self.session.post(
            self.endpoint("/v1/chat/completions"),
            json=payload,
            timeout=(10, 180),
            stream=True,
        )
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")
        raw_chunks: list[dict[str, Any]] = []
        response_model = model
        finish_reason = ""
        usage: dict[str, Any] = {}
        raw_answer = ""
        raw_reasoning = ""
        first_token_ms: int | None = None

        def emit_update() -> None:
            if on_delta is None:
                return
            thinking, answer = split_reasoning(raw_answer, raw_reasoning)
            on_delta(
                {
                    "answer": answer,
                    "thinking": thinking,
                    "response_model": response_model,
                    "first_token_ms": first_token_ms,
                }
            )

        if "text/event-stream" not in content_type.lower():
            data = safe_json(response)
            raw_chunks.append(data if isinstance(data, dict) else {"raw": data})
            choice = (data.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            response_model = str(data.get("model") or model)
            raw_answer = first_text(message.get("content"))
            raw_reasoning = first_text(message.get("reasoning_content") or message.get("reasoning"))
            usage = data.get("usage") or {}
            finish_reason = str(choice.get("finish_reason") or "")
            total_ms = max(1, round((time.perf_counter() - started) * 1000))
            thinking, answer = split_reasoning(raw_answer, raw_reasoning)
            metrics = self._build_metrics(
                total_ms=total_ms,
                first_token_ms=first_token_ms or total_ms,
                usage=usage,
                finish_reason=finish_reason,
                response_model=response_model,
            )
            return ChatResult(answer=answer, thinking=thinking, metrics=metrics, raw_chunks=raw_chunks)

        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            line = raw_line.strip()
            if line.startswith("data:"):
                line = line[5:].strip()
            if not line:
                continue
            if line == "[DONE]":
                break
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            raw_chunks.append(item)
            response_model = str(item.get("model") or response_model or model)
            if item.get("usage"):
                usage = item.get("usage") or usage
            choice = (item.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
            finish_reason = str(choice.get("finish_reason") or finish_reason)
            content_piece = first_text(delta.get("content"))
            reasoning_piece = first_text(delta.get("reasoning_content") or delta.get("reasoning"))
            if content_piece or reasoning_piece:
                if first_token_ms is None:
                    first_token_ms = max(1, round((time.perf_counter() - started) * 1000))
                raw_answer += content_piece
                raw_reasoning += reasoning_piece
                emit_update()

        total_ms = max(1, round((time.perf_counter() - started) * 1000))
        thinking, answer = split_reasoning(raw_answer, raw_reasoning)
        metrics = self._build_metrics(
            total_ms=total_ms,
            first_token_ms=first_token_ms,
            usage=usage,
            finish_reason=finish_reason,
            response_model=response_model,
        )
        return ChatResult(answer=answer, thinking=thinking, metrics=metrics, raw_chunks=raw_chunks)

    def generate_image(
        self,
        *,
        model: str,
        prompt: str,
        width: int,
        height: int,
        steps: int,
        seed: str = "",
    ) -> ImageResult:
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt.strip(),
            "width": int(width),
            "height": int(height),
            "steps": int(steps),
        }
        if str(seed).strip():
            payload["seed"] = int(seed)

        response = self.session.post(
            self.endpoint("/api/images/generate"),
            json=payload,
            timeout=180,
        )
        if response.status_code >= 400:
            try:
                data = response.json()
                message = data.get("error") or data.get("message") or json.dumps(data, ensure_ascii=False)
            except Exception:
                message = response.text or f"HTTP {response.status_code}"
            raise RuntimeError(message)

        data = safe_json(response)
        images = data.get("images") or []
        if not images:
            raise RuntimeError("O proxy respondeu sem imagem.")
        first = images[0] or {}
        encoded = str(first.get("base64") or "").strip()
        if not encoded:
            raise RuntimeError("O proxy respondeu sem base64.")
        mime_type = str(first.get("mime_type") or "image/jpeg").strip()
        image_bytes = base64.b64decode(encoded)
        return ImageResult(
            model=str(data.get("model") or model),
            mime_type=mime_type,
            image_bytes=image_bytes,
            duration_ms=int(data.get("duration_ms") or 0),
            seed=str(data.get("seed") or payload.get("seed") or ""),
            width=int(width),
            height=int(height),
        )

    def _build_metrics(
        self,
        *,
        total_ms: int,
        first_token_ms: int | None,
        usage: dict[str, Any],
        finish_reason: str,
        response_model: str,
    ) -> ChatMetrics:
        prompt_tokens = self._safe_int(usage.get("prompt_tokens"))
        completion_tokens = self._safe_int(usage.get("completion_tokens"))
        total_tokens = self._safe_int(usage.get("total_tokens"))
        tokens_per_second = None
        if completion_tokens and total_ms > 0:
            tokens_per_second = completion_tokens / max(total_ms / 1000.0, 0.001)
        return ChatMetrics(
            total_ms=total_ms,
            first_token_ms=first_token_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            tokens_per_second=tokens_per_second,
            finish_reason=finish_reason or "stop",
            response_model=response_model,
        )

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            if value is None:
                return None
            return int(value)
        except Exception:
            return None


def format_model_capabilities(model: ModelInfo) -> str:
    if not model.capabilities:
        return "chat"
    return " | ".join(model.capabilities)


def rich_text_block(text: str) -> str:
    safe = escape(str(text or ""))
    safe = safe.replace("\n", "<br>")
    return f"<div style='white-space:pre-wrap'>{safe}</div>"
