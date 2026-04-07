import asyncio
import statistics
import time
from typing import Any

import httpx


def ema(values: list[float], period: int) -> float | None:
    if not values:
        return None
    alpha = 2 / (period + 1)
    current = values[0]
    for value in values[1:]:
        current = alpha * value + (1 - alpha) * current
    return current


def rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) <= period:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    relative = avg_gain / avg_loss
    return 100 - (100 / (1 + relative))


def pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return (current / previous - 1) * 100


def stdev_returns(closes: list[float]) -> float:
    returns = [pct_change(closes[i], closes[i - 1]) for i in range(1, len(closes)) if closes[i - 1] != 0]
    if not returns:
        return 0.0
    return statistics.pstdev(returns)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class BinanceMarketClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=15, headers={"User-Agent": "RED-Trader/0.1"})

    async def close(self) -> None:
        await self.client.aclose()

    async def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response = await self.client.get(f"{self.base_url}{path}", params=params)
        response.raise_for_status()
        return response.json()

    async def fetch_symbol(self, symbol: str) -> dict[str, Any]:
        ticker_task = self.get_json("/api/v3/ticker/24hr", {"symbol": symbol})
        depth_task = self.get_json("/api/v3/depth", {"symbol": symbol, "limit": 20})
        klines_1m_task = self.get_json("/api/v3/klines", {"symbol": symbol, "interval": "1m", "limit": 180})
        klines_5m_task = self.get_json("/api/v3/klines", {"symbol": symbol, "interval": "5m", "limit": 120})
        klines_15m_task = self.get_json("/api/v3/klines", {"symbol": symbol, "interval": "15m", "limit": 120})
        ticker, depth, klines_1m, klines_5m, klines_15m = await asyncio.gather(
            ticker_task,
            depth_task,
            klines_1m_task,
            klines_5m_task,
            klines_15m_task,
        )
        snapshot = {
            "symbol": symbol,
            "ts": time.time(),
            "ticker": self._normalize_ticker(ticker),
            "orderbook": self._orderbook_summary(depth),
            "frames": {
                "1m": self._frame_summary(klines_1m),
                "5m": self._frame_summary(klines_5m),
                "15m": self._frame_summary(klines_15m),
            },
            "candles": {
                "1m": self._candles(klines_1m[-120:]),
                "5m": self._candles(klines_5m[-80:]),
                "15m": self._candles(klines_15m[-80:]),
            },
        }
        snapshot["features"] = self._features(snapshot)
        return snapshot

    async def fetch_symbols(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        results = await asyncio.gather(*(self.fetch_symbol(symbol) for symbol in symbols), return_exceptions=True)
        output: dict[str, dict[str, Any]] = {}
        for symbol, result in zip(symbols, results):
            if isinstance(result, Exception):
                output[symbol] = {"symbol": symbol, "ts": time.time(), "error": repr(result)}
            else:
                output[symbol] = result
        return output

    async def fetch_usdt_brl(self) -> float:
        try:
            payload = await self.get_json("/api/v3/ticker/price", {"symbol": "USDTBRL"})
            return _float(payload.get("price"), 5.0)
        except Exception:
            return 5.0

    @staticmethod
    def _normalize_ticker(ticker: dict[str, Any]) -> dict[str, Any]:
        return {
            "last_price": _float(ticker.get("lastPrice")),
            "price_change_pct_24h": _float(ticker.get("priceChangePercent")),
            "volume": _float(ticker.get("volume")),
            "quote_volume": _float(ticker.get("quoteVolume")),
            "high_price": _float(ticker.get("highPrice")),
            "low_price": _float(ticker.get("lowPrice")),
        }

    @staticmethod
    def _orderbook_summary(depth: dict[str, Any]) -> dict[str, Any]:
        bids = [(_float(price), _float(qty)) for price, qty in depth.get("bids", [])]
        asks = [(_float(price), _float(qty)) for price, qty in depth.get("asks", [])]
        best_bid = bids[0][0] if bids else 0.0
        best_ask = asks[0][0] if asks else 0.0
        mid = (best_bid + best_ask) / 2 if best_bid and best_ask else 0.0
        bid_notional = sum(price * qty for price, qty in bids)
        ask_notional = sum(price * qty for price, qty in asks)
        return {
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread_pct": ((best_ask - best_bid) / mid * 100) if mid else 0.0,
            "bid_notional_20": bid_notional,
            "ask_notional_20": ask_notional,
            "bid_ask_ratio": bid_notional / ask_notional if ask_notional else 0.0,
        }

    @staticmethod
    def _candles(rows: list[list[Any]]) -> list[dict[str, Any]]:
        candles: list[dict[str, Any]] = []
        for row in rows:
            candles.append(
                {
                    "time": int(row[0] / 1000),
                    "open": _float(row[1]),
                    "high": _float(row[2]),
                    "low": _float(row[3]),
                    "close": _float(row[4]),
                    "volume": _float(row[5]),
                }
            )
        return candles

    @staticmethod
    def _frame_summary(rows: list[list[Any]]) -> dict[str, Any]:
        candles = BinanceMarketClient._candles(rows)
        closes = [item["close"] for item in candles]
        volumes = [item["volume"] for item in candles]
        last_close = closes[-1] if closes else 0.0
        avg_vol_30 = sum(volumes[-31:-1]) / min(30, max(len(volumes) - 1, 1)) if len(volumes) > 1 else 0.0
        return {
            "last_close": last_close,
            "change_5": pct_change(last_close, closes[-6]) if len(closes) > 6 else 0.0,
            "change_15": pct_change(last_close, closes[-16]) if len(closes) > 16 else 0.0,
            "change_60": pct_change(last_close, closes[-61]) if len(closes) > 61 else 0.0,
            "ema9": ema(closes[-80:], 9),
            "ema21": ema(closes[-100:], 21),
            "rsi14": rsi(closes, 14),
            "ret_std_30": stdev_returns(closes[-31:]),
            "volume_last": volumes[-1] if volumes else 0.0,
            "volume_avg_30": avg_vol_30,
            "volume_last_vs_avg30": (volumes[-1] / avg_vol_30) if avg_vol_30 else 0.0,
        }

    @staticmethod
    def _features(snapshot: dict[str, Any]) -> dict[str, Any]:
        f1 = snapshot["frames"]["1m"]
        f5 = snapshot["frames"]["5m"]
        f15 = snapshot["frames"]["15m"]
        orderbook = snapshot["orderbook"]
        ticker = snapshot["ticker"]
        return {
            "last_price": ticker["last_price"],
            "change_24h_pct": ticker["price_change_pct_24h"],
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
            "volume_1m_vs_avg30": f1["volume_last_vs_avg30"],
            "volume_5m_vs_avg30": f5["volume_last_vs_avg30"],
            "spread_pct": orderbook["spread_pct"],
            "bid_ask_ratio": orderbook["bid_ask_ratio"],
        }
