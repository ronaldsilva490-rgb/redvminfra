import asyncio
import threading
import time
from typing import Any

from .config import settings
from .market import ema, pct_change, rsi, stdev_returns


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class IQOptionDemoAdapter:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.api: Any | None = None
        self.connected_at = 0.0
        self.frame_cache: dict[str, dict[str, Any]] = {}
        self.stream_cache: dict[str, dict[str, Any]] = {}
        self.history_cursor = 0
        self.binary_status_cache: dict[str, dict[str, Any]] = {}
        self.binary_status_ts = 0.0

    async def close(self) -> None:
        await asyncio.to_thread(self._close_sync)

    async def fetch_symbols(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        return await asyncio.to_thread(self._fetch_symbols_sync, symbols)

    async def buy(self, active: str, action: str, amount: float, expiration_minutes: int) -> dict[str, Any]:
        return await asyncio.to_thread(self._buy_sync, active, action, amount, expiration_minutes)

    async def check_result(
        self,
        order_id: str | int,
        max_wait_seconds: float = 2.5,
        poll_interval: float = 0.2,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(self._check_result_sync, order_id, max_wait_seconds, poll_interval)

    def _ensure_connected(self) -> Any:
        if not settings.iqoption_enabled:
            raise RuntimeError("iqoption_disabled")
        if not settings.iqoption_username or not settings.iqoption_password:
            raise RuntimeError("missing_iqoption_credentials")

        from iqoptionapi.stable_api import IQ_Option

        if self.api is not None:
            try:
                if self.api.get_balance_mode() == "PRACTICE":
                    return self.api
            except Exception:
                self._close_sync()

        api = IQ_Option(settings.iqoption_username, settings.iqoption_password, active_account_type="PRACTICE")
        ok, reason = api.connect()
        if not ok:
            raise RuntimeError(str(reason or "connect_failed")[:180])
        api.change_balance("PRACTICE")
        mode = api.get_balance_mode()
        if mode != "PRACTICE":
            try:
                api.api.close()
            except Exception:
                pass
            raise RuntimeError(f"practice_not_selected:{mode}")
        self.api = api
        self.connected_at = time.time()
        return api

    def _close_sync(self) -> None:
        with self.lock:
            if self.api is None:
                return
            for key in list(self.stream_cache):
                try:
                    symbol, size = key.split(":", 1)
                    self.api.stop_candles_stream(symbol, int(size))
                except Exception:
                    pass
            self.stream_cache.clear()
            try:
                self.api.api.close()
            except Exception:
                pass
            self.api = None
            self.frame_cache.clear()
            self.binary_status_cache.clear()
            self.binary_status_ts = 0.0

    def _fetch_symbols_sync(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        output: dict[str, dict[str, Any]] = {}
        with self.lock:
            api = self._ensure_connected()
            availability_map = self._binary_status_map(api)
            now = time.time()
            stale_symbols = [
                symbol for symbol in symbols
                if now - _float((self.frame_cache.get(symbol) or {}).get("ts")) > 30
            ]
            refresh_target = None
            if stale_symbols:
                refresh_target = stale_symbols[self.history_cursor % len(stale_symbols)]
                self.history_cursor += 1
            for symbol in symbols:
                try:
                    snapshot = self._fetch_symbol_with_retry(
                        api,
                        symbol,
                        refresh_history=symbol == refresh_target,
                        availability=availability_map.get(symbol) or {},
                    )
                    output[symbol] = snapshot
                except Exception as exc:
                    output[symbol] = {"symbol": symbol, "provider": "iqoption_demo", "ts": time.time(), "error": repr(exc)}
        return output

    def _fetch_symbol_with_retry(self, api: Any, symbol: str, refresh_history: bool, availability: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._fetch_symbol_sync(api, symbol, refresh_history=refresh_history, availability=availability)
        except Exception as exc:
            if "reconnect" not in repr(exc).lower() and "closed" not in repr(exc).lower():
                raise
            self._close_sync()
            api = self._ensure_connected()
            availability_map = self._binary_status_map(api)
            return self._fetch_symbol_sync(
                api,
                symbol,
                refresh_history=refresh_history,
                availability=availability_map.get(symbol) or availability,
            )

    def _fetch_symbol_sync(self, api: Any, symbol: str, refresh_history: bool, availability: dict[str, Any]) -> dict[str, Any]:
        now = time.time()
        candles_1s = self._realtime_candles(api, symbol, 1, 600)
        cached_frames = self.frame_cache.get(symbol) or {}
        candles_1m = cached_frames.get("1m") or []
        candles_5m = cached_frames.get("5m") or []
        candles_15m = cached_frames.get("15m") or []
        if refresh_history:
            try:
                candles_1m = self._candles(api.get_candles(symbol, 60, 180, now))
                candles_5m = self._candles(api.get_candles(symbol, 300, 120, now))
                candles_15m = self._candles(api.get_candles(symbol, 900, 120, now))
                self.frame_cache[symbol] = {
                    "ts": now,
                    "1m": candles_1m,
                    "5m": candles_5m,
                    "15m": candles_15m,
                }
            except Exception:
                # Historico multi-timeframe da IQ pode falhar com "need reconnect".
                # O terminal nao deve congelar por isso; mantemos o stream 1s vivo
                # e usamos cache/fallback ate o proximo refresh rotativo.
                pass
        if not candles_1s:
            candles_1s = self._candles(api.get_candles(symbol, 1, 240, now))
        if not candles_1m:
            candles_1m = candles_1s[-180:]
        if not candles_5m:
            candles_5m = candles_1m[-120:] or candles_1s[-120:]
        if not candles_15m:
            candles_15m = candles_5m[-120:] or candles_1m[-120:] or candles_1s[-120:]
        if not candles_1s and not candles_1m:
            raise RuntimeError("empty_iqoption_candles")
        last_series = candles_1s or candles_1m
        last = last_series[-1]["close"]
        snapshot = {
            "symbol": symbol,
            "provider": "iqoption_demo",
            "ts": time.time(),
            "ticker": {
                "last_price": last,
                "price_change_pct_24h": 0.0,
                "volume": 0.0,
                "quote_volume": 0.0,
                "high_price": max(item["high"] for item in last_series),
                "low_price": min(item["low"] for item in last_series),
            },
            "orderbook": {
                "best_bid": last,
                "best_ask": last,
                "spread_pct": 0.0,
                "bid_notional_20": 1.0,
                "ask_notional_20": 1.0,
                "bid_ask_ratio": 1.0,
            },
            "frames": {
                "1s": self._frame_summary(candles_1s),
                "1m": self._frame_summary(candles_1m),
                "5m": self._frame_summary(candles_5m),
                "15m": self._frame_summary(candles_15m),
            },
            "candles": {
                "1s": candles_1s[-600:],
                "1m": candles_1m[-120:],
                "5m": candles_5m[-80:],
                "15m": candles_15m[-80:],
            },
            "binary_availability": availability or {},
        }
        snapshot["features"] = self._features(snapshot)
        return snapshot

    def _binary_status_map(self, api: Any) -> dict[str, dict[str, Any]]:
        now = time.time()
        if self.binary_status_cache and now - self.binary_status_ts < 45:
            return self.binary_status_cache

        output: dict[str, dict[str, Any]] = {}
        payload = api.get_all_init_v2() or {}
        for market in ("turbo", "binary"):
            actives = (payload.get(market) or {}).get("actives") or {}
            for active in actives.values():
                raw_name = str(active.get("name") or "")
                symbol = raw_name.split(".")[-1] if "." in raw_name else raw_name
                enabled = bool(active.get("enabled"))
                suspended = bool(active.get("is_suspended"))
                option = active.get("option") or {}
                profit = option.get("profit") or {}
                row = output.setdefault(symbol, {"symbol": symbol})
                row[f"{market}_open"] = enabled and not suspended
                row[f"{market}_enabled"] = enabled
                row[f"{market}_suspended"] = suspended
                row[f"{market}_commission"] = _float(profit.get("commission"))
                row[f"{market}_payout_pct"] = max(0.0, 100.0 - _float(profit.get("commission")))
                row["minimal_bet"] = _float(active.get("minimal_bet"), row.get("minimal_bet") or 0.0)
                row["maximal_bet"] = _float(active.get("maximal_bet"), row.get("maximal_bet") or 0.0)
                start_time = _float(option.get("start_time"))
                if start_time > 0:
                    row[f"{market}_start_time"] = start_time
                expirations = option.get("expiration_times") or []
                if expirations:
                    row[f"{market}_expiration_times"] = expirations
        for row in output.values():
            row["open"] = bool(row.get("turbo_open") or row.get("binary_open"))
            future_times: list[float] = []
            next_cycle_times: list[float] = []
            for market in ("turbo", "binary"):
                start_time = _float(row.get(f"{market}_start_time"))
                if start_time > now:
                    next_cycle_times.append(start_time)
                    if bool(row.get(f"{market}_enabled")) and not bool(row.get(f"{market}_suspended")):
                        future_times.append(start_time)
            row["next_cycle_ts"] = min(next_cycle_times) if next_cycle_times else 0.0
            row["next_open_ts"] = min(future_times) if future_times else 0.0
            row["next_open_reliable"] = bool(future_times)
        self.binary_status_cache = output
        self.binary_status_ts = now
        return output

    def _realtime_candles(self, api: Any, symbol: str, size: int, maxdict: int) -> list[dict[str, Any]]:
        key = f"{symbol}:{size}"
        stream = self.stream_cache.get(key) or {}
        if not stream:
            try:
                api.start_candles_stream(symbol, size, maxdict)
            except Exception:
                # Some versions need the one-stream subscription first.
                api.start_candles_one_stream(symbol, size)
            self.stream_cache[key] = {"started_at": time.time(), "size": size, "maxdict": maxdict}
            time.sleep(0.25)
        rows = api.get_realtime_candles(symbol, size) or {}
        values = list(rows.values()) if isinstance(rows, dict) else list(rows or [])
        return self._candles(values)

    def _buy_sync(self, active: str, action: str, amount: float, expiration_minutes: int) -> dict[str, Any]:
        action = str(action or "").lower()
        if action not in {"call", "put"}:
            raise ValueError("invalid_iqoption_action")
        if amount <= 0:
            raise ValueError("invalid_iqoption_amount")
        expiration_minutes = max(1, int(expiration_minutes or 1))
        with self.lock:
            api = self._ensure_connected()
            if api.get_balance_mode() != "PRACTICE":
                raise RuntimeError("practice_not_selected")
            availability = self._binary_status_map(api).get(active) or {}
            # A disponibilidade em get_all_init_v2 pode vir atrasada/inconsistente para pares normais.
            # Para o Trader ser fiel ao comportamento real da IQ, tentamos a compra mesmo assim e
            # deixamos a propria API devolver o motivo final em caso de recusa.
            ok, order_id = api.buy(float(amount), active, action, expiration_minutes)
            if not ok:
                raise RuntimeError(f"iqoption_buy_failed:{order_id}")
            return {
                "ok": True,
                "order_id": str(order_id),
                "active": active,
                "action": action,
                "amount": float(amount),
                "expiration_minutes": expiration_minutes,
                "balance_mode": api.get_balance_mode(),
                "balance_after_open": api.get_balance(),
            }

    def _check_result_sync(
        self,
        order_id: str | int,
        max_wait_seconds: float = 2.5,
        poll_interval: float = 0.2,
    ) -> dict[str, Any]:
        target = str(order_id)
        deadline = time.time() + max(0.6, float(max_wait_seconds or 0))
        while time.time() < deadline:
            with self.lock:
                api = self._ensure_connected()
                if api.get_balance_mode() != "PRACTICE":
                    raise RuntimeError("practice_not_selected")
                payload = api.get_optioninfo_v2(100)
                closed = ((payload or {}).get("msg") or {}).get("closed_options") or []
                for item in closed:
                    raw_ids = item.get("id") or []
                    raw_id = raw_ids[0] if isinstance(raw_ids, list) and raw_ids else raw_ids
                    if str(raw_id) != target:
                        continue
                    status = item.get("win") or "unknown"
                    amount = _float(item.get("amount"))
                    win_amount = _float(item.get("win_amount"))
                    profit = 0.0 if status == "equal" else win_amount - amount
                    return {
                        "status": status,
                        "profit": profit,
                        "balance_after_close": api.get_balance(),
                    }
            time.sleep(max(0.05, float(poll_interval or 0.2)))
        raise RuntimeError(f"iqoption_result_not_ready:{target}")

    @staticmethod
    def _candles(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        candles: list[dict[str, Any]] = []
        for row in rows or []:
            candles.append(
                {
                    "time": int(row.get("from") or row.get("at", 0) / 1_000_000_000 or time.time()),
                    "open": _float(row.get("open")),
                    "high": _float(row.get("max")),
                    "low": _float(row.get("min")),
                    "close": _float(row.get("close")),
                    "volume": _float(row.get("volume"), 1.0),
                }
            )
        return sorted(candles, key=lambda item: item["time"])

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
            "binary_turbo_open": bool((snapshot.get("binary_availability") or {}).get("turbo_open")),
            "binary_binary_open": bool((snapshot.get("binary_availability") or {}).get("binary_open")),
            "binary_minimal_bet": _float((snapshot.get("binary_availability") or {}).get("minimal_bet")),
            "binary_turbo_payout_pct": _float((snapshot.get("binary_availability") or {}).get("turbo_payout_pct")),
            "binary_next_open_ts": _float((snapshot.get("binary_availability") or {}).get("next_open_ts")),
        }
