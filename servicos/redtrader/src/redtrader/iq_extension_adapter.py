from __future__ import annotations

import time
from typing import Any

from .iq_bridge import IQExtensionBridgeClient
from .market import ema, pct_change, rsi, stdev_returns


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_symbol(value: Any) -> str:
    text = str(value or "").upper().strip()
    text = text.replace("(OTC)", "-OTC").replace("_OTC", "-OTC")
    text = text.replace("/", "").replace(" ", "")
    text = text.replace("--", "-")
    return text


class IQExtensionAdapter:
    def __init__(self, bridge: IQExtensionBridgeClient) -> None:
        self.bridge = bridge
        self.session_id = ""
        self.asset_map: dict[int, str] = {}
        self.asset_meta: dict[int, dict[str, Any]] = {}
        self.market_cache: dict[int, dict[str, Any]] = {}
        self.live_book: dict[int, dict[str, Any]] = {}
        self.tick_history: dict[int, list[dict[str, Any]]] = {}
        self.last_state: dict[str, Any] = {}
        self.last_catalog_at = 0.0
        self.last_resolution_at = 0.0

    async def close(self) -> None:
        return None

    async def fetch_symbols(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        await self.refresh(force_resolution=True)
        output: dict[str, dict[str, Any]] = {}
        for raw_symbol in symbols:
            symbol = str(raw_symbol or "").upper().strip()
            active_id = self.resolve_symbol(symbol)
            if not active_id:
                output[symbol] = {
                    "symbol": symbol,
                    "provider": "iq_extension",
                    "ts": time.time(),
                    "error": "iq_extension_symbol_unmapped",
                }
                continue
            snapshot = self._build_snapshot(symbol, active_id)
            output[symbol] = snapshot
        return output

    async def buy(self, active: str, action: str, amount: float, expiration_minutes: int) -> dict[str, Any]:
        await self.refresh(force_resolution=True)
        symbol = str(active or "").upper().strip()
        active_id = self.resolve_symbol(symbol)
        if not active_id:
            raise RuntimeError(f"iq_extension_symbol_unmapped:{symbol}")

        # Alinha o foco interno da IQ com o ativo antes da ordem.
        await self.bridge.run_command(
            self.session_id,
            "native_select_asset",
            {"activeId": active_id},
            timeout_seconds=5.0,
        )
        await self.refresh(force_resolution=True)

        command = "trade_put" if str(action or "").lower() == "put" else "trade_call"
        expired = self._compute_expiration(active_id, expiration_minutes)
        result = await self.bridge.run_command(
            self.session_id,
            command,
            {
                "activeId": active_id,
                "amount": float(amount),
                "expired": expired,
            },
            timeout_seconds=8.0,
        )
        payload = result.get("result") or {}
        socket_result = payload.get("socketResult") or {}
        socket_payload = ((socket_result.get("payload") or {}).get("msg") or {})
        status = int(socket_result.get("status") or ((socket_result.get("payload") or {}).get("status") or 0) or 0)
        trade_evidence = payload.get("tradeEvidence") or {}
        if status != 2000:
            message = str(socket_result.get("message") or trade_evidence.get("note") or payload.get("error") or "iq_extension_trade_failed")
            raise RuntimeError(message)

        payout_pct = _float(
            payload.get("current", {}).get("payoutPct")
            or self.live_book.get(active_id, {}).get("payoutPct")
            or self.market_cache.get(active_id, {}).get("payoutPct"),
            0.0,
        )
        order_id = str(socket_payload.get("id") or "")
        created_at = _float(socket_payload.get("created"))
        expiration_ts = _float(socket_payload.get("exp") or expired)
        return {
            "ok": True,
            "provider": "iq_extension",
            "order_id": order_id,
            "active": symbol,
            "active_id": active_id,
            "action": command.replace("trade_", ""),
            "amount": float(amount),
            "expiration_minutes": int(expiration_minutes),
            "expiration_ts": int(expiration_ts),
            "opened_at": created_at or time.time(),
            "open_quote": _float(socket_payload.get("value")),
            "payout_pct": payout_pct,
            "trade_evidence": trade_evidence,
            "command_result": payload,
        }

    async def check_result(self, trade: dict[str, Any], snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
        metadata = trade.get("metadata") or {}
        active_id = int(
            metadata.get("active_id")
            or metadata.get("iq_extension_order", {}).get("active_id")
            or metadata.get("iqoption_order", {}).get("active_id")
            or 0
        )
        if not active_id:
            raise RuntimeError("iq_extension_missing_active_id")
        open_quote = _float(
            metadata.get("open_quote")
            or metadata.get("iq_extension_order", {}).get("open_quote")
            or metadata.get("iqoption_order", {}).get("open_quote")
            or trade.get("entry_price")
        )
        if not open_quote:
            raise RuntimeError("iq_extension_missing_open_quote")
        expiration_ts = _float(
            metadata.get("expiration_ts")
            or metadata.get("iq_extension_order", {}).get("expiration_ts")
            or metadata.get("iqoption_order", {}).get("expiration_ts")
        )
        if not expiration_ts:
            expiration_ts = float(trade.get("opened_at") or 0) + float(metadata.get("expiry_seconds") or 60)
        payout_pct = _float(
            metadata.get("payout_pct")
            or metadata.get("iq_extension_order", {}).get("payout_pct")
            or metadata.get("iqoption_order", {}).get("payout_pct"),
            0.0,
        )
        amount = _float(trade.get("position_brl"))
        direction = str(metadata.get("iqoption_action") or metadata.get("iq_extension_action") or trade.get("side") or "").lower()
        if direction not in {"call", "put"}:
            raise RuntimeError("iq_extension_missing_direction")

        await self.refresh(force_resolution=True)
        closing_tick = self._find_closing_tick(active_id, expiration_ts)
        if not closing_tick:
            raise RuntimeError(f"iq_extension_result_not_ready:{active_id}:{int(expiration_ts)}")
        close_quote = _float(closing_tick.get("price"))
        if not close_quote:
            raise RuntimeError("iq_extension_missing_close_quote")

        if close_quote == open_quote:
            status = "equal"
            profit = 0.0
        else:
            win = (direction == "call" and close_quote > open_quote) or (direction == "put" and close_quote < open_quote)
            status = "win" if win else "loose"
            profit = amount * (payout_pct / 100.0) if win else -amount
        return {
            "status": status,
            "profit": profit,
            "open_quote": open_quote,
            "close_quote": close_quote,
            "tick": closing_tick,
        }

    async def refresh(self, *, force_catalog: bool = False, force_resolution: bool = False) -> None:
        state = await self.bridge.fetch_live_state()
        self.last_state = state
        self.session_id = str(state.get("session_id") or self.session_id or "").strip()
        self._merge_state(state)
        if not state.get("connected") or not self.session_id:
            raise RuntimeError(str(state.get("error") or "iq_bridge_unavailable"))
        now = time.time()

        if self.session_id and (force_catalog or not self.asset_map or (now - self.last_catalog_at) > 30):
            command = await self.bridge.run_command(self.session_id, "dump_catalog", {}, timeout_seconds=6.0)
            self.last_catalog_at = now
            self._merge_command_result((command or {}).get("result") or {})

        if self.session_id and (force_resolution or (now - self.last_resolution_at) > 2):
            command = await self.bridge.run_command(self.session_id, "dump_resolution", {}, timeout_seconds=6.0)
            self.last_resolution_at = now
            self._merge_command_result((command or {}).get("result") or {})

    def resolve_symbol(self, symbol: str) -> int | None:
        wanted = _normalize_symbol(symbol)
        best_id = None
        best_score = -1.0
        for active_id, raw_label in self.asset_map.items():
            meta = self.asset_meta.get(int(active_id)) or {}
            labels = {
                _normalize_symbol(symbol),
                _normalize_symbol(raw_label),
                _normalize_symbol(meta.get("base")),
                _normalize_symbol(meta.get("lastLabel")),
            }
            if wanted not in labels:
                continue
            score = float(meta.get("confidence") or 0.0)
            if score > best_score:
                best_id = int(active_id)
                best_score = score
        return best_id

    def _merge_state(self, state: dict[str, Any]) -> None:
        payload = state
        active_id = payload.get("active_id")
        price = payload.get("price")
        if isinstance(payload.get("debug"), dict):
            live_payout = payload["debug"].get("livePayout") or {}
            if active_id and _float(live_payout.get("value")):
                self.market_cache[int(active_id)] = {
                    **(self.market_cache.get(int(active_id)) or {}),
                    "payoutPct": _float(live_payout.get("value")),
                    "payoutSource": live_payout.get("source") or "",
                    "updatedAt": time.time() * 1000,
                }
        if active_id and price:
            self.live_book[int(active_id)] = {
                **(self.live_book.get(int(active_id)) or {}),
                "activeId": int(active_id),
                "currentPrice": _float(price),
                "payoutPct": _float(payload.get("payout_pct")) if payload.get("payout_pct") is not None else self.live_book.get(int(active_id), {}).get("payoutPct"),
                "marketType": payload.get("market_type") or "",
                "countdownLabel": payload.get("countdown") or "",
                "nextExpiration": None,
                "suspendedHint": bool(payload.get("suspended_hint")),
                "updatedAt": time.time() * 1000,
            }
        ticks = ((payload.get("debug") or {}).get("ticks") if isinstance(payload.get("debug"), dict) else None) or payload.get("ticks") or []
        if active_id and ticks:
            self._merge_ticks(int(active_id), ticks)

    def _merge_command_result(self, result: dict[str, Any]) -> None:
        for raw_key, value in (result.get("assetMap") or {}).items():
            try:
                self.asset_map[int(raw_key)] = str(value or "")
            except (TypeError, ValueError):
                continue
        for raw_key, value in (result.get("assetMeta") or {}).items():
            try:
                self.asset_meta[int(raw_key)] = dict(value or {})
            except (TypeError, ValueError):
                continue
        for raw_key, value in (result.get("marketCache") or {}).items():
            try:
                self.market_cache[int(raw_key)] = dict(value or {})
            except (TypeError, ValueError):
                continue
        for raw_key, value in (result.get("liveBook") or {}).items():
            try:
                self.live_book[int(raw_key)] = dict(value or {})
            except (TypeError, ValueError):
                continue
        for raw_key, ticks in (result.get("ticksByActiveId") or {}).items():
            try:
                self._merge_ticks(int(raw_key), ticks or [])
            except (TypeError, ValueError):
                continue

    def _merge_ticks(self, active_id: int, ticks: list[dict[str, Any]]) -> None:
        if not ticks:
            return
        current = self.tick_history.setdefault(active_id, [])
        seen = {(int(item.get("ts") or 0), round(_float(item.get("price")), 12)) for item in current}
        for item in ticks:
            ts = int(item.get("ts") or 0)
            price = _float(item.get("price"))
            if not ts or not price:
                continue
            key = (ts, round(price, 12))
            if key in seen:
                continue
            current.append({"ts": ts, "price": price})
            seen.add(key)
        current.sort(key=lambda item: item["ts"])
        if len(current) > 4000:
            del current[:-4000]

    def _build_snapshot(self, symbol: str, active_id: int) -> dict[str, Any]:
        live = self.live_book.get(active_id) or {}
        ticks = list(self.tick_history.get(active_id) or [])
        if not ticks and _float(live.get("currentPrice")):
            ticks = [{"ts": int(time.time() * 1000), "price": _float(live.get("currentPrice"))}]
        if not ticks:
            return {
                "symbol": symbol,
                "provider": "iq_extension",
                "ts": time.time(),
                "error": "iq_extension_no_ticks",
                "binary_availability": {
                    "open": bool(not live.get("suspendedHint")),
                    "next_open_ts": _float(live.get("nextExpiration")),
                    "next_open_reliable": False,
                },
            }

        candles_1s = self._aggregate_ticks(ticks, 1)[-600:]
        candles_1m = self._aggregate_candles(candles_1s, 60)[-180:]
        candles_5m = self._aggregate_candles(candles_1s, 300)[-120:]
        candles_15m = self._aggregate_candles(candles_1s, 900)[-120:]
        last_price = ticks[-1]["price"]
        snapshot = {
            "symbol": symbol,
            "provider": "iq_extension",
            "ts": time.time(),
            "ticker": {
                "last_price": last_price,
                "price_change_pct_24h": 0.0,
                "volume": 0.0,
                "quote_volume": 0.0,
                "high_price": max(item["high"] for item in candles_1s),
                "low_price": min(item["low"] for item in candles_1s),
            },
            "orderbook": {
                "best_bid": last_price,
                "best_ask": last_price,
                "spread_pct": 0.0,
                "bid_notional_20": 1.0,
                "ask_notional_20": 1.0,
                "bid_ask_ratio": 1.0,
            },
            "frames": {
                "1s": self._frame_summary(candles_1s),
                "1m": self._frame_summary(candles_1m or candles_1s),
                "5m": self._frame_summary(candles_5m or candles_1m or candles_1s),
                "15m": self._frame_summary(candles_15m or candles_5m or candles_1m or candles_1s),
            },
            "candles": {
                "1s": candles_1s[-600:],
                "1m": (candles_1m or candles_1s)[-120:],
                "5m": (candles_5m or candles_1m or candles_1s)[-80:],
                "15m": (candles_15m or candles_5m or candles_1m or candles_1s)[-80:],
            },
            "binary_availability": {
                "open": bool(
                    (active_id == int(self.last_state.get("active_id") or 0) and bool(self.last_state.get("buy_window_open")))
                    or (not bool(live.get("suspendedHint")) and _float(live.get("payoutPct")) > 0)
                ),
                "next_open_ts": _float(live.get("nextExpiration")),
                "next_open_reliable": bool(_float(live.get("nextExpiration")) > 0),
                "turbo_open": True,
                "binary_open": True,
                "turbo_payout_pct": _float(live.get("payoutPct")),
                "binary_payout_pct": _float(live.get("payoutPct")),
            },
        }
        snapshot["features"] = self._features(snapshot)
        return snapshot

    def _compute_expiration(self, active_id: int, expiration_minutes: int) -> int:
        live = self.live_book.get(active_id) or {}
        now_sec = int(time.time())
        server_ms = _float((self.last_state.get("debug") or {}).get("serverTimeMs"))
        if server_ms > 0:
            now_sec = int(server_ms / 1000)
        target = int(_float(live.get("nextExpiration")))
        if target <= now_sec + 5:
            target = ((now_sec + 59) // 60) * 60
            if (target - now_sec) < 8:
                target += 60
        extra_minutes = max(1, int(expiration_minutes or 1)) - 1
        return int(target + (extra_minutes * 60))

    def _find_closing_tick(self, active_id: int, expiration_ts: float) -> dict[str, Any] | None:
        ticks = list(self.tick_history.get(active_id) or [])
        if not ticks:
            return None
        expiry_ms = int(expiration_ts * 1000)
        after = [item for item in ticks if int(item.get("ts") or 0) >= expiry_ms]
        if after:
            return after[0]
        before = [item for item in ticks if int(item.get("ts") or 0) <= expiry_ms]
        if before and time.time() > (expiration_ts + 2):
            return before[-1]
        return None

    @staticmethod
    def _aggregate_ticks(ticks: list[dict[str, Any]], interval_seconds: int) -> list[dict[str, Any]]:
        buckets: dict[int, dict[str, Any]] = {}
        for item in ticks:
            ts_ms = int(item.get("ts") or 0)
            price = _float(item.get("price"))
            if not ts_ms or not price:
                continue
            bucket_ts = (ts_ms // (interval_seconds * 1000)) * interval_seconds
            entry = buckets.get(bucket_ts)
            if not entry:
                buckets[bucket_ts] = {
                    "time": bucket_ts,
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "volume": 1.0,
                }
                continue
            entry["high"] = max(entry["high"], price)
            entry["low"] = min(entry["low"], price)
            entry["close"] = price
            entry["volume"] += 1.0
        return [buckets[key] for key in sorted(buckets)]

    @staticmethod
    def _aggregate_candles(candles: list[dict[str, Any]], interval_seconds: int) -> list[dict[str, Any]]:
        buckets: dict[int, dict[str, Any]] = {}
        for item in candles:
            ts = int(item.get("time") or 0)
            price = _float(item.get("close"))
            if not ts or not price:
                continue
            bucket_ts = (ts // interval_seconds) * interval_seconds
            entry = buckets.get(bucket_ts)
            if not entry:
                buckets[bucket_ts] = {
                    "time": bucket_ts,
                    "open": _float(item.get("open"), price),
                    "high": _float(item.get("high"), price),
                    "low": _float(item.get("low"), price),
                    "close": price,
                    "volume": _float(item.get("volume"), 1.0),
                }
                continue
            entry["high"] = max(entry["high"], _float(item.get("high"), price))
            entry["low"] = min(entry["low"], _float(item.get("low"), price))
            entry["close"] = price
            entry["volume"] += _float(item.get("volume"), 1.0)
        return [buckets[key] for key in sorted(buckets)]

    @staticmethod
    def _frame_summary(candles: list[dict[str, Any]]) -> dict[str, Any]:
        closes = [item["close"] for item in candles]
        volumes = [item["volume"] for item in candles]
        last_close = closes[-1] if closes else 0.0
        avg_vol_30 = sum(volumes[-31:-1]) / min(30, max(len(volumes) - 1, 1)) if len(volumes) > 1 else 1.0
        return {
            "last_close": last_close,
            "change_5": pct_change(last_close, closes[-6]) if len(closes) > 6 else 0.0,
            "change_15": pct_change(last_close, closes[-16]) if len(closes) > 16 else 0.0,
            "change_60": pct_change(last_close, closes[-61]) if len(closes) > 61 else 0.0,
            "ema9": ema(closes[-80:], 9),
            "ema21": ema(closes[-100:], 21),
            "rsi14": rsi(closes, 14),
            "ret_std_30": stdev_returns(closes[-31:]),
            "volume_last": volumes[-1] if volumes else 1.0,
            "volume_avg_30": avg_vol_30,
            "volume_last_vs_avg30": (volumes[-1] / avg_vol_30) if avg_vol_30 else 1.0,
        }

    @staticmethod
    def _features(snapshot: dict[str, Any]) -> dict[str, Any]:
        f0 = snapshot["frames"].get("1s") or snapshot["frames"]["1m"]
        f1 = snapshot["frames"]["1m"]
        f5 = snapshot["frames"]["5m"]
        f15 = snapshot["frames"]["15m"]
        return {
            "last_price": snapshot["ticker"]["last_price"],
            "change_24h_pct": 0.0,
            "trend_1s": "up" if (f0["ema9"] or 0) > (f0["ema21"] or 0) else "down",
            "trend_1m": "up" if (f1["ema9"] or 0) > (f1["ema21"] or 0) else "down",
            "trend_5m": "up" if (f5["ema9"] or 0) > (f5["ema21"] or 0) else "down",
            "trend_15m": "up" if (f15["ema9"] or 0) > (f15["ema21"] or 0) else "down",
            "rsi_1s": f0["rsi14"],
            "rsi_1m": f1["rsi14"],
            "rsi_5m": f5["rsi14"],
            "rsi_15m": f15["rsi14"],
            "change_1s_5": f0["change_5"],
            "change_1s_15": f0["change_15"],
            "change_1m_15": f1["change_15"],
            "change_5m_15": f5["change_15"],
            "change_15m_15": f15["change_15"],
            "ret_std_1s_30": f0["ret_std_30"],
            "ret_std_1m_30": f1["ret_std_30"],
            "ret_std_5m_30": f5["ret_std_30"],
            "volume_1s_vs_avg30": f0["volume_last_vs_avg30"] or 1.0,
            "volume_1m_vs_avg30": f1["volume_last_vs_avg30"] or 1.0,
            "volume_5m_vs_avg30": f5["volume_last_vs_avg30"] or 1.0,
            "spread_pct": 0.0,
            "bid_ask_ratio": 1.0,
            "binary_open": bool((snapshot.get("binary_availability") or {}).get("open")),
        }
