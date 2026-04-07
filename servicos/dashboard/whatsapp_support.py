from __future__ import annotations

import copy
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_config() -> dict[str, Any]:
    return {
        "enabled": False,
        "base_url": "",
        "api_key": "",
        "instance_name": "red-whatsapp-ai",
        "instance_token": "",
        "bot_number": "",
        "webhook_secret": "",
        "default_model": "",
        "fallback_models": [],
        "group_prefix": "red,",
        "system_prompt": (
            "Voce e o assistente operacional RED Whatsapp A.I. "
            "Responda sempre em portugues do Brasil. "
            "Use o contexto da VM e da conversa. "
            "Se algo exigir risco operacional, destaque o risco antes da acao."
        ),
        "mark_as_read": True,
        "typing_presence": True,
        "auto_sync_targets": True,
        "context": {
            "max_messages": 28,
            "max_chars": 14000,
            "summary_trigger_messages": 20,
            "summary_keep_recent": 10,
            "summary_target_chars": 2200,
        },
        "targets": [],
    }


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def ensure_storage(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "conversations").mkdir(parents=True, exist_ok=True)


def config_path(root: Path) -> Path:
    return root / "config.json"


def conversations_dir(root: Path) -> Path:
    return root / "conversations"


def log_path(root: Path) -> Path:
    return root / "events.log"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return copy.deepcopy(default)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return copy.deepcopy(default)
    return data


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_config(root: Path) -> dict[str, Any]:
    ensure_storage(root)
    stored = read_json(config_path(root), default_config())
    if not isinstance(stored, dict):
        stored = {}
    config = deep_merge(default_config(), stored)
    config["targets"] = [normalize_target(item) for item in (config.get("targets") or []) if isinstance(item, dict)]
    return config


def write_config(root: Path, config: dict[str, Any]) -> None:
    ensure_storage(root)
    payload = deep_merge(default_config(), config or {})
    payload["targets"] = [normalize_target(item) for item in (payload.get("targets") or []) if isinstance(item, dict)]
    write_json(config_path(root), payload)


def mask_secret(value: str, *, head: int = 6, tail: int = 4) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= head + tail:
        return "*" * len(text)
    return f"{text[:head]}...{text[-tail:]}"


def slug_chat_id(chat_id: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9]+", "-", chat_id).strip("-").lower()
    if not clean:
        clean = "chat"
    digest = hashlib.sha1(chat_id.encode("utf-8")).hexdigest()[:10]
    return f"{clean[:48]}-{digest}"


def conversation_path(root: Path, chat_id: str) -> Path:
    ensure_storage(root)
    return conversations_dir(root) / f"{slug_chat_id(chat_id)}.json"


def default_conversation(chat_id: str, *, kind: str = "private", name: str = "") -> dict[str, Any]:
    return {
        "chat_id": chat_id,
        "kind": kind,
        "name": name,
        "model": "",
        "summary": "",
        "summary_updated_at": "",
        "summary_message_count": 0,
        "pending_model_selection": False,
        "pending_model_options": [],
        "messages": [],
        "updated_at": utc_now_iso(),
        "last_message_at": "",
    }


def read_conversation(root: Path, chat_id: str, *, kind: str = "private", name: str = "") -> dict[str, Any]:
    path = conversation_path(root, chat_id)
    stored = read_json(path, default_conversation(chat_id, kind=kind, name=name))
    if not isinstance(stored, dict):
        stored = {}
    conversation = deep_merge(default_conversation(chat_id, kind=kind, name=name), stored)
    if name and not conversation.get("name"):
        conversation["name"] = name
    if kind:
        conversation["kind"] = kind
    return conversation


def write_conversation(root: Path, conversation: dict[str, Any]) -> None:
    chat_id = str(conversation.get("chat_id", "") or "").strip()
    if not chat_id:
        raise ValueError("chat_id is required")
    payload = dict(conversation)
    payload["updated_at"] = utc_now_iso()
    write_json(conversation_path(root, chat_id), payload)


def list_conversations(root: Path) -> list[dict[str, Any]]:
    ensure_storage(root)
    rows: list[dict[str, Any]] = []
    for item in conversations_dir(root).glob("*.json"):
        data = read_json(item, {})
        if isinstance(data, dict) and data.get("chat_id"):
            rows.append(data)
    rows.sort(key=lambda row: str(row.get("updated_at", "") or row.get("last_message_at", "")), reverse=True)
    return rows


def delete_conversation(root: Path, chat_id: str) -> bool:
    path = conversation_path(root, chat_id)
    if not path.exists():
        return False
    path.unlink()
    return True


def message_preview(message: dict[str, Any]) -> str:
    text = normalize_text_content(message.get("text", "")).strip()
    if not text:
        text = str(message.get("content_type", "") or "mensagem")
    text = re.sub(r"\s+", " ", text)
    return text[:160]


def conversation_preview(conversation: dict[str, Any]) -> dict[str, Any]:
    messages = conversation.get("messages") or []
    last = messages[-1] if messages else {}
    return {
        "chat_id": conversation.get("chat_id", ""),
        "kind": conversation.get("kind", "private"),
        "name": conversation.get("name", ""),
        "model": conversation.get("model", ""),
        "summary": conversation.get("summary", ""),
        "pending_model_selection": bool(conversation.get("pending_model_selection")),
        "message_count": len(messages),
        "last_message_at": conversation.get("last_message_at", ""),
        "updated_at": conversation.get("updated_at", ""),
        "last_message_preview": message_preview(last) if isinstance(last, dict) else "",
    }


def normalize_target(payload: dict[str, Any]) -> dict[str, Any]:
    chat_id = str(payload.get("chat_id", "") or payload.get("id", "") or "").strip()
    kind = str(payload.get("kind", "") or ("group" if chat_id.endswith("@g.us") else "private")).strip()
    respond_mode = str(payload.get("respond_mode", "") or ("prefix_or_mention" if kind == "group" else "always")).strip()
    return {
        "chat_id": chat_id,
        "name": str(payload.get("name", "") or "").strip(),
        "kind": kind,
        "alerts_enabled": bool(payload.get("alerts_enabled", False)),
        "ai_enabled": bool(payload.get("ai_enabled", True)),
        "shell_enabled": bool(payload.get("shell_enabled", False)),
        "admin": bool(payload.get("admin", False)),
        "muted": bool(payload.get("muted", False)),
        "respond_mode": respond_mode,
        "prefix_override": str(payload.get("prefix_override", "") or "").strip(),
        "model": str(payload.get("model", "") or "").strip(),
        "updated_at": str(payload.get("updated_at", "") or utc_now_iso()),
    }


def explicit_target_fields(payload: dict[str, Any]) -> set[str]:
    fields: set[str] = set()
    for key in (payload or {}).keys():
        if key == "id":
            fields.add("chat_id")
        elif key in {
            "chat_id",
            "name",
            "kind",
            "alerts_enabled",
            "ai_enabled",
            "shell_enabled",
            "admin",
            "muted",
            "respond_mode",
            "prefix_override",
            "model",
        }:
            fields.add(str(key))
    return fields


def upsert_target(config: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    target = normalize_target(payload)
    if not target["chat_id"]:
        raise ValueError("chat_id is required")
    targets = [normalize_target(item) for item in (config.get("targets") or []) if isinstance(item, dict)]
    explicit_fields = explicit_target_fields(payload)
    updated = False
    for index, item in enumerate(targets):
        if item["chat_id"] == target["chat_id"]:
            merged = dict(item)
            for field in explicit_fields:
                if field == "chat_id":
                    continue
                merged[field] = target[field]
            merged["updated_at"] = utc_now_iso()
            targets[index] = merged
            updated = True
            target = merged
            break
    if not updated:
        target["updated_at"] = utc_now_iso()
        targets.append(target)
    targets.sort(key=lambda item: ((item.get("kind") != "group"), str(item.get("name", "")).lower(), item.get("chat_id", "")))
    config["targets"] = targets
    return target


def find_target(config: dict[str, Any], chat_id: str) -> dict[str, Any] | None:
    for item in config.get("targets", []) or []:
        if str(item.get("chat_id", "")) == chat_id:
            return normalize_target(item)
    return None


def append_message(conversation: dict[str, Any], message: dict[str, Any]) -> bool:
    messages = conversation.setdefault("messages", [])
    message_id = str(message.get("id", "") or "").strip()
    if message_id and any(str(item.get("id", "")) == message_id for item in messages[-80:]):
        return False
    item = dict(message)
    item.setdefault("at", utc_now_iso())
    item["text"] = normalize_text_content(item.get("text", ""))
    if item.get("quoted_text"):
        item["quoted_text"] = normalize_text_content(item.get("quoted_text", ""))
    if item.get("quoted_name"):
        item["quoted_name"] = normalize_text_content(item.get("quoted_name", ""))
    messages.append(item)
    conversation["last_message_at"] = item.get("at", utc_now_iso())
    conversation["updated_at"] = utc_now_iso()
    return True


def jid_to_destination(chat_id: str) -> str:
    chat_id = str(chat_id or "").strip()
    if chat_id.endswith("@g.us"):
        return chat_id
    return re.sub(r"\D+", "", chat_id)


def build_context_messages(
    conversation: dict[str, Any],
    *,
    max_messages: int,
    max_chars: int,
) -> list[dict[str, str]]:
    messages = [item for item in (conversation.get("messages") or []) if isinstance(item, dict)]
    cursor = int(conversation.get("summary_message_count", 0) or 0)
    selected = messages[cursor:]
    selected = selected[-max_messages:]

    rows: list[dict[str, str]] = []
    total_chars = 0
    for item in reversed(selected):
        role = str(item.get("role", "") or "")
        text = str(item.get("text", "") or "").strip()
        if role not in {"user", "assistant", "system"} or not text:
            continue
        quoted_text = str(item.get("quoted_text", "") or "").strip()
        if quoted_text:
            quoted_role = str(item.get("quoted_role", "") or "").strip().lower()
            quoted_name = str(item.get("quoted_name", "") or "").strip()
            if not quoted_name:
                quoted_name = "assistente" if quoted_role == "assistant" else "usuario"
            quoted_excerpt = re.sub(r"\s+", " ", quoted_text)[:600]
            text = f"[Em resposta a {quoted_name}: {quoted_excerpt}]\n{text}"
        total_chars += len(text)
        if total_chars > max_chars and rows:
            break
        rows.append({"role": role, "content": text})
    rows.reverse()
    return rows


def normalize_text_content(content: Any) -> str:
    text = unicodedata.normalize("NFC", str(content or ""))
    text = text.replace("\ufeff", "").replace("\u200b", "")
    return text


def format_markdown_for_whatsapp(content: str) -> str:
    text = normalize_text_content(content).replace("\r\n", "\n")
    text = re.sub(r"```(\w+)?\n", "```\n", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.*?)\*\*", r"*\1*", text)
    text = re.sub(r"__(.*?)__", r"_\1_", text)
    text = re.sub(r"~~(.*?)~~", r"~\1~", text)
    text = re.sub(r"\[(.*?)\]\((https?://[^\s)]+)\)", r"\1: \2", text)
    text = text.replace("â€¢", "- ")
    text = text.replace("• ", "- ")
    text = re.sub(r"^\s*[-*]\s+", "- ", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[•●▪◦]\s+", "- ", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "- ", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_whatsapp_text(content: str, *, max_chars: int = 3500) -> list[str]:
    text = normalize_text_content(content).strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    blocks = text.split("\n\n")
    chunks: list[str] = []
    current = ""
    for block in blocks:
        candidate = f"{current}\n\n{block}".strip() if current else block
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(block) <= max_chars:
            current = block
            continue
        start = 0
        while start < len(block):
            part = block[start : start + max_chars]
            chunks.append(part)
            start += max_chars
        current = ""
    if current:
        chunks.append(current)
    return [chunk.strip() for chunk in chunks if chunk.strip()]
