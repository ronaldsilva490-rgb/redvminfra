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

    async def close(self) -> None:
        await asyncio.to_thread(self._close_sync)

    async def fetch_symbols(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        return await asyncio.to_thread(self._fetch_symbols_sync, symbols)

    async def buy(self, active: str, action: str, amount: float, expiration_minutes: int) -> dict[str, Any]:
        return await asyncio.to_thread(self._buy_sync, active, action, amount, expiration_minutes)

    async def check_result(self, order_id: str | int) -> dict[str, Any]:
        return await asyncio.to_thread(self._check_result_sync, order_id)

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
            try:
                self.api.api.close()
            except Exception:
                pass
            self.api = None

    def _fetch_symbols_sync(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        output: dict[str, dict[str, Any]] = {}
        with self.lock:
            api = self._ensure_connected()
            for symbol in symbols:
                try:
                    snapshot = self._fetch_symbol_sync(api, symbol)
                    output[symbol] = snapshot
                except Exception as exc:
                    output[symbol] = {"symbol": symbol, "provider": "iqoption_demo", "ts": time.time(), "error": repr(exc)}
        return output

    def _fetch_symbol_sync(self, api: Any, symbol: str) -> dict[str, Any]:
        now = time.time()
        candles_1m = self._candles(api.get_candles(symbol, 60, 180, now))
        cached_frames = self.frame_cache.get(symbol) or {}
        if now - _float(cached_frames.get("ts")) > 20:
            candles_5m = self._candles(api.get_candles(symbol, 300, 120, now))
            candles_15m = self._candles(api.get_candles(symbol, 900, 120, now))
            self.frame_cache[symbol] = {
                "ts": now,
                "5m": candles_5m,
                "15m": candles_15m,
            }
        else:
            candles_5m = cached_frames.get("5m") or []
            candles_15m = cached_frames.get("15m") or []
        if not candles_1m:
            raise RuntimeError("empty_iqoption_candles")
        last = candles_1m[-1]["close"]
        snapshot = {
            "symbol": symbol,
            "provider": "iqoption_demo",
            "ts": time.time(),
            "ticker": {
                "last_price": last,
                "price_change_pct_24h": 0.0,
                "volume": 0.0,
                "quote_volume": 0.0,
                "high_price": max(item["high"] for item in candles_1m),
                "low_price": min(item["low"] for item in candles_1m),
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
                "1m": self._frame_summary(candles_1m),
                "5m": self._frame_summary(candles_5m),
                "15m": self._frame_summary(candles_15m),
            },
            "candles": {
                "1m": candles_1m[-120:],
                "5m": candles_5m[-80:],
                "15m": candles_15m[-80:],
            },
        }
        snapshot["features"] = self._features(snapshot)
        return snapshot

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

    def _check_result_sync(self, order_id: str | int) -> dict[str, Any]:
        target = str(order_id)
        deadline = time.time() + 25
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
            time.sleep(1)
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
        f1 = snapshot["frames"]["1m"]
        f5 = snapshot["frames"]["5m"]
        f15 = snapshot["frames"]["15m"]
        return {
            "last_price": snapshot["ticker"]["last_price"],
            "change_24h_pct": 0.0,
            "trend_1m": "up" if (f1["ema9"] or 0) > (f1["ema21"] or 0) else "down",
            "trend_5m": "up" if (f5["ema9"] or 0) > (f5["ema21"] or 0) else "down",
            "trend_15m": "up" if (f15["ema9"] or 0) > (f15["ema21"] or 0) else "down",
            "rsi_1m": f1["rsi14"],
            "rsi_5m": f5["rsi14"],
            "rsi_15m": f15["rsi14"],
            "change_1m_15": f1["change_15"],
            "change_5m_15": f5["change_15"],
            "change_15m_15": f15["change_15"],
            "ret_std_1m_30": f1["ret_std_30"],
            "ret_std_5m_30": f5["ret_std_30"],
            "volume_1m_vs_avg30": f1["volume_last_vs_avg30"] or 1.0,
            "volume_5m_vs_avg30": f5["volume_last_vs_avg30"] or 1.0,
            "spread_pct": 0.0,
            "bid_ask_ratio": 1.0,
        }
