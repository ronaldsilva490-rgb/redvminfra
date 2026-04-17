from __future__ import annotations

import json
import time
from typing import Any

import httpx

STALE_EXTENSION_AGE_MS = 180_000


def _num(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not number == number:
        return None
    return number


class IQExtensionBridgeClient:
    def __init__(self, base_url: str, token: str = "", preferred_session_id: str = "", timeout_seconds: float = 2.5):
        self.base_url = str(base_url or "").rstrip("/")
        self.token = str(token or "").strip()
        self.preferred_session_id = str(preferred_session_id or "").strip()
        self.client = httpx.AsyncClient(timeout=timeout_seconds)

    async def close(self) -> None:
        await self.client.aclose()

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["x-red-token"] = self.token
        return headers

    def _score_item(self, item: dict[str, Any]) -> float:
        payload = item.get("payload") or {}
        score = 0.0
        if item.get("session_id") == self.preferred_session_id and self.preferred_session_id:
            score += 100.0
        if str(payload.get("href") or item.get("url") or "").find("/traderoom") >= 0:
            score += 20.0
        if str(payload.get("asset") or item.get("asset") or "").strip() and str(payload.get("asset") or item.get("asset") or "").strip() != "-":
            score += 18.0
        if _num(payload.get("currentPrice")) is not None or _num(item.get("current_price")) is not None:
            score += 18.0
        if _num(payload.get("payoutPct")) is not None or _num(item.get("payout_pct")) is not None:
            score += 14.0
        if _num(payload.get("selectedAmount")) is not None:
            score += 8.0
        if str(payload.get("selectedExpiry") or "").strip() and str(payload.get("selectedExpiry") or "").strip() != "-":
            score += 8.0
        if isinstance(payload.get("buyWindowOpen"), bool):
            score += 6.0
        if isinstance(payload.get("uiFlags"), dict) and payload["uiFlags"].get("tradeSurfaceReady"):
            score += 12.0
        if isinstance(payload.get("healthFlags"), dict) and payload["healthFlags"].get("readyToTrade"):
            score += 8.0
        age = max(0.0, time.time() - float(item.get("received_at") or time.time()))
        score += max(0.0, 12.0 - min(age, 12.0))
        return score

    def _normalize_item(self, item: dict[str, Any] | None) -> dict[str, Any]:
        payload = (item or {}).get("payload") or {}
        received_at = float((item or {}).get("received_at") or 0.0)
        age_ms = max(0, int((time.time() - received_at) * 1000)) if received_at else None
        asset = str(payload.get("asset") or (item or {}).get("asset") or "").strip() or "-"
        market_type = str(payload.get("marketType") or (item or {}).get("market_type") or "").strip() or "-"
        connected = bool(item)
        error = ""
        if connected and age_ms is not None and age_ms > STALE_EXTENSION_AGE_MS:
            connected = False
            error = "iq_bridge_stale_extension_state"
        state = {
            "connected": connected,
            "source": "iq_bridge",
            "session_id": (item or {}).get("session_id") or "",
            "tab_id": (item or {}).get("tab_id"),
            "received_at": received_at,
            "updated_at": payload.get("updatedAt") or (item or {}).get("ts"),
            "age_ms": age_ms,
            "asset": asset,
            "market_type": market_type,
            "mode": str(payload.get("mode") or (item or {}).get("mode") or "unknown"),
            "active_id": payload.get("activeId"),
            "price": _num(payload.get("currentPrice") if payload.get("currentPrice") is not None else (item or {}).get("current_price")),
            "payout_pct": _num(payload.get("payoutPct") if payload.get("payoutPct") is not None else (item or {}).get("payout_pct")),
            "countdown": str(payload.get("countdown") or (item or {}).get("countdown") or "").strip() or "-",
            "tick_age_ms": _num(payload.get("tickAgeMs") if payload.get("tickAgeMs") is not None else (item or {}).get("tick_age_ms")),
            "buy_window_open": payload.get("buyWindowOpen") if isinstance(payload.get("buyWindowOpen"), bool) else bool((item or {}).get("buy_window_open")),
            "suspended_hint": bool(payload.get("suspendedHint") if payload.get("suspendedHint") is not None else (item or {}).get("suspended_hint")),
            "selected_amount": _num(payload.get("selectedAmount")),
            "selected_expiry": str(payload.get("selectedExpiry") or "").strip() or "-",
            "entry_hint": str(payload.get("entryHint") or "").strip(),
            "notes": list(payload.get("notes") or [])[:6],
            "ui_flags": payload.get("uiFlags") or {},
            "health_flags": payload.get("healthFlags") or {},
            "pulse": payload.get("pulse") or {},
            "debug": payload.get("debug") or {},
            "href": str(payload.get("href") or (item or {}).get("url") or ""),
            "page_title": str(payload.get("pageTitle") or (item or {}).get("title") or ""),
        }
        if error:
            state["error"] = error
        return state

    async def fetch_live_state(self) -> dict[str, Any]:
        if not self.base_url:
            return {
                "connected": False,
                "source": "iq_bridge",
                "error": "iq_bridge_disabled",
            }
        if self.preferred_session_id:
            response = await self.client.get(
                f"{self.base_url}/api/state/current",
                params={"session_id": self.preferred_session_id},
                headers=self._headers(),
            )
            response.raise_for_status()
            payload = response.json()
            item = payload.get("item")
            state = self._normalize_item(item)
            if item:
                state["selection"] = "preferred_session"
            return state

        response = await self.client.get(
            f"{self.base_url}/api/telemetry/recent",
            params={"limit": 12},
            headers=self._headers(),
        )
        response.raise_for_status()
        payload = response.json()
        items = list(payload.get("items") or [])
        if not items:
            return {
                "connected": False,
                "source": "iq_bridge",
                "error": "iq_bridge_no_telemetry",
            }
        items.sort(key=self._score_item, reverse=True)
        state = self._normalize_item(items[0])
        state["selection"] = "best_recent"
        state["selection_score"] = self._score_item(items[0])
        return state

    async def enqueue_command(self, session_id: str, command: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.base_url:
            raise RuntimeError("iq_bridge_disabled")
        target_session = str(session_id or self.preferred_session_id or "").strip()
        if not target_session:
            raise RuntimeError("iq_bridge_missing_session")
        response = await self.client.post(
            f"{self.base_url}/api/commands",
            headers=self._headers(),
            content=json.dumps({
                "sessionId": target_session,
                "command": str(command or "").strip(),
                "payload": payload or {},
            }, ensure_ascii=False),
        )
        response.raise_for_status()
        body = response.json()
        return {
            "ok": True,
            "id": body.get("id"),
            "session_id": target_session,
            "command": command,
        }

    async def list_commands(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.base_url:
            return []
        response = await self.client.get(
            f"{self.base_url}/api/commands",
            params={"limit": max(1, min(200, int(limit or 50)))},
            headers=self._headers(),
        )
        response.raise_for_status()
        return list((response.json() or {}).get("items") or [])

    async def wait_command(self, command_id: int, timeout_seconds: float = 8.0) -> dict[str, Any]:
        deadline = time.time() + max(0.2, float(timeout_seconds or 0))
        while time.time() < deadline:
            items = await self.list_commands(limit=100)
            for item in items:
                if int(item.get("id") or 0) != int(command_id):
                    continue
                if item.get("status") in {"done", "failed"}:
                    return item
            await self._sleep_brief()
        raise RuntimeError(f"iq_bridge_command_timeout:{command_id}")

    async def run_command(
        self,
        session_id: str,
        command: str,
        payload: dict[str, Any] | None = None,
        timeout_seconds: float = 8.0,
    ) -> dict[str, Any]:
        queued = await self.enqueue_command(session_id, command, payload or {})
        item = await self.wait_command(int(queued["id"]), timeout_seconds=timeout_seconds)
        if item.get("status") == "failed":
            raise RuntimeError(str((item.get("result") or {}).get("error") or f"iq_bridge_command_failed:{command}"))
        return item

    async def fetch_logs_recent(
        self,
        *,
        limit: int = 100,
        event: str = "",
        contains: str = "",
        asset: str = "",
        session_id: str = "",
    ) -> list[dict[str, Any]]:
        if not self.base_url:
            return []
        response = await self.client.get(
            f"{self.base_url}/api/logs/recent",
            params={
                "limit": max(1, min(1000, int(limit or 100))),
                "event": event,
                "contains": contains,
                "asset": asset,
                "session_id": session_id,
            },
            headers=self._headers(),
        )
        response.raise_for_status()
        return list((response.json() or {}).get("items") or [])

    async def _sleep_brief(self) -> None:
        import asyncio

        await asyncio.sleep(0.15)
