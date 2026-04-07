import time
import xml.etree.ElementTree as ET
from typing import Any

import httpx


class NewsClient:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=15, headers={"User-Agent": "RED-Trader/0.1"})

    async def close(self) -> None:
        await self.client.aclose()

    async def fetch(self) -> dict[str, Any]:
        headlines = []
        errors = []
        for source, url in [
            ("Cointelegraph", "https://cointelegraph.com/rss"),
            ("Cointelegraph Markets", "https://cointelegraph.com/tags/market-analysis/rss"),
        ]:
            try:
                headlines.extend(await self._rss(source, url))
            except Exception as exc:
                errors.append(f"{source}: {exc!r}")
        try:
            fear_greed = await self._fear_greed()
        except Exception as exc:
            fear_greed = {"error": repr(exc)}
        return {
            "ts": time.time(),
            "headlines": headlines[:12],
            "fear_greed": fear_greed,
            "errors": errors,
            "risk_hint": self._risk_hint(fear_greed, headlines),
        }

    async def _rss(self, source: str, url: str) -> list[dict[str, str]]:
        response = await self.client.get(url)
        response.raise_for_status()
        root = ET.fromstring(response.text)
        output = []
        for item in root.findall(".//item")[:8]:
            title = (item.findtext("title") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            if title:
                output.append({"source": source, "title": title[:240], "pubDate": pub_date})
        return output

    async def _fear_greed(self) -> dict[str, Any]:
        response = await self.client.get("https://api.alternative.me/fng/", params={"limit": 1, "format": "json"})
        response.raise_for_status()
        payload = response.json()
        data = (payload.get("data") or [{}])[0]
        return {
            "value": int(data.get("value", 0) or 0),
            "classification": data.get("value_classification") or "unknown",
            "timestamp": data.get("timestamp"),
        }

    @staticmethod
    def _risk_hint(fear_greed: dict[str, Any], headlines: list[dict[str, str]]) -> dict[str, Any]:
        value = fear_greed.get("value")
        level = "neutral"
        reasons: list[str] = []
        if isinstance(value, int):
            if value <= 15:
                level = "red"
                reasons.append("Fear & Greed em medo extremo")
            elif value <= 30:
                level = "yellow"
                reasons.append("Fear & Greed em medo")
        text = " ".join(item["title"].lower() for item in headlines)
        red_terms = ["hack", "exploit", "lawsuit", "sec", "ban", "liquidation", "crash", "outage"]
        if any(term in text for term in red_terms):
            level = "red"
            reasons.append("Manchetes contem termos de risco")
        return {"level": level, "reasons": reasons}
