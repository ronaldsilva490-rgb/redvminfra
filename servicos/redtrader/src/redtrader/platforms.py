import time
from dataclasses import dataclass
from typing import Any

import httpx

from .config import settings


@dataclass(frozen=True)
class PlatformDefinition:
    id: str
    label: str
    kind: str
    mode: str
    data_scope: str
    execution_scope: str
    docs_note: str


PLATFORM_DEFINITIONS: dict[str, PlatformDefinition] = {
    "binance_spot": PlatformDefinition(
        id="binance_spot",
        label="Binance Spot",
        kind="crypto_spot",
        mode="market_data_paper",
        data_scope="market_data",
        execution_scope="internal_paper_ledger",
        docs_note="Dados reais Spot; trades continuam no paper ledger interno.",
    ),
    "tastytrade_sandbox": PlatformDefinition(
        id="tastytrade_sandbox",
        label="tastytrade Sandbox",
        kind="brokerage_sandbox",
        mode="sandbox",
        data_scope="requires_credentials",
        execution_scope="sandbox_adapter",
        docs_note="Sandbox oficial; exige credenciais antes de qualquer teste de conta/ordem.",
    ),
    "webull_paper": PlatformDefinition(
        id="webull_paper",
        label="Webull Paper",
        kind="brokerage_paper",
        mode="paper",
        data_scope="requires_openapi_app",
        execution_scope="paper_adapter",
        docs_note="OpenAPI/Paper; exige app key/secret e escopo liberado.",
    ),
    "iqoption_experimental": PlatformDefinition(
        id="iqoption_experimental",
        label="IQ Option Experimental",
        kind="unofficial_experimental",
        mode="experimental_demo",
        data_scope="unofficial_adapter",
        execution_scope="demo_only_when_enabled",
        docs_note="Isolado do core; usar apenas em demo e com adapter separado.",
    ),
}


class PlatformRegistry:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(timeout=8, headers={"User-Agent": "RED-Trader/0.1"})

    async def close(self) -> None:
        await self.client.aclose()

    async def status(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        platforms = config.get("platforms") or {}
        rows = []
        for platform_id, definition in PLATFORM_DEFINITIONS.items():
            platform_config = platforms.get(platform_id) or {}
            enabled = bool(platform_config.get("enabled", platform_id == "binance_spot"))
            if platform_id == "binance_spot":
                rows.append(await self._binance_status(definition, platform_config, enabled))
            elif platform_id == "tastytrade_sandbox":
                rows.append(self._credential_status(
                    definition,
                    platform_config,
                    enabled,
                    configured=bool(settings.tastytrade_username and settings.tastytrade_password),
                    base_url=settings.tastytrade_base_url,
                    missing="Configure TASTYTRADE_USERNAME e TASTYTRADE_PASSWORD no ambiente.",
                ))
            elif platform_id == "webull_paper":
                rows.append(self._credential_status(
                    definition,
                    platform_config,
                    enabled,
                    configured=bool(settings.webull_app_key and settings.webull_app_secret),
                    base_url=settings.webull_base_url,
                    missing="Configure WEBULL_APP_KEY e WEBULL_APP_SECRET no ambiente.",
                ))
            elif platform_id == "iqoption_experimental":
                rows.append(self._credential_status(
                    definition,
                    platform_config,
                    enabled and settings.iqoption_enabled,
                    configured=bool(settings.iqoption_username and settings.iqoption_password and settings.iqoption_enabled),
                    base_url="unofficial/local-adapter",
                    missing="Defina IQOPTION_ENABLED=true e credenciais somente se aceitar o modo experimental demo.",
                ))
        return rows

    async def _binance_status(self, definition: PlatformDefinition, platform_config: dict[str, Any], enabled: bool) -> dict[str, Any]:
        started = time.perf_counter()
        if not enabled:
            return self._base_row(definition, platform_config, enabled, "disabled", False, "Desativado na configuração.")
        try:
            response = await self.client.get(f"{settings.binance_base_url}/api/v3/time")
            response.raise_for_status()
            latency_ms = int((time.perf_counter() - started) * 1000)
            server_time = response.json().get("serverTime")
            row = self._base_row(
                definition,
                platform_config,
                enabled,
                "connected",
                True,
                "Market data real conectado; execução continua em paper interno.",
            )
            row.update({
                "latency_ms": latency_ms,
                "base_url": settings.binance_base_url,
                "server_time": server_time,
                "symbols": platform_config.get("symbols") or [],
            })
            return row
        except Exception as exc:
            row = self._base_row(definition, platform_config, enabled, "error", False, "Falha ao consultar Binance Spot.")
            row.update({"base_url": settings.binance_base_url, "error": repr(exc)})
            return row

    def _credential_status(
        self,
        definition: PlatformDefinition,
        platform_config: dict[str, Any],
        enabled: bool,
        configured: bool,
        base_url: str,
        missing: str,
    ) -> dict[str, Any]:
        if not enabled:
            return self._base_row(definition, platform_config, enabled, "disabled", False, "Desativado na configuração.")
        if not configured:
            row = self._base_row(definition, platform_config, enabled, "needs_config", False, missing)
            row["base_url"] = base_url
            return row
        row = self._base_row(
            definition,
            platform_config,
            enabled,
            "configured",
            False,
            "Credenciais encontradas. Próxima etapa: handshake/autenticação do adapter sem operar dinheiro real.",
        )
        row["base_url"] = base_url
        return row

    @staticmethod
    def _base_row(
        definition: PlatformDefinition,
        platform_config: dict[str, Any],
        enabled: bool,
        status: str,
        connected: bool,
        message: str,
    ) -> dict[str, Any]:
        return {
            "id": definition.id,
            "label": platform_config.get("label") or definition.label,
            "kind": definition.kind,
            "mode": platform_config.get("mode") or definition.mode,
            "enabled": enabled,
            "connected": connected,
            "status": status,
            "message": message,
            "data_scope": definition.data_scope,
            "execution_scope": definition.execution_scope,
            "docs_note": definition.docs_note,
            "paper_only": True,
            "last_checked_at": time.time(),
        }
