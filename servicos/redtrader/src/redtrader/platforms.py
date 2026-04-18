import asyncio
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
        label="IQ Browser Demo",
        kind="binary_options_demo",
        mode="demo",
        data_scope="market_data_and_demo_account",
        execution_scope="extension_bridge_only",
        docs_note="Conta demo via extensao Chrome + bridge local; o RED Trader bloqueia uso em conta real.",
    ),
}


class PlatformRegistry:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(timeout=8, headers={"User-Agent": "RED-Trader/0.1"})

    async def close(self) -> None:
        await self.client.aclose()

    async def status(self, config: dict[str, Any], iq_extension: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        platforms = config.get("platforms") or {}
        rows = []
        for platform_id, definition in PLATFORM_DEFINITIONS.items():
            platform_config = platforms.get(platform_id) or {}
            enabled = bool(platform_config.get("enabled", platform_id == "binance_spot"))
            if platform_id == "binance_spot":
                rows.append(await self._binance_status(definition, platform_config, enabled))
            elif platform_id == "tastytrade_sandbox":
                rows.append(await self._tastytrade_status(definition, platform_config, enabled))
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
                rows.append(await self._iqoption_status(definition, platform_config, enabled, iq_extension or {}))
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

    async def _tastytrade_status(self, definition: PlatformDefinition, platform_config: dict[str, Any], enabled: bool) -> dict[str, Any]:
        started = time.perf_counter()
        if not enabled:
            return self._base_row(definition, platform_config, enabled, "disabled", False, "Desativado na configuração.")

        has_oauth = bool(settings.tastytrade_client_secret and settings.tastytrade_refresh_token)
        has_legacy_session = bool(settings.tastytrade_username and settings.tastytrade_password)
        if not has_oauth and not has_legacy_session:
            row = self._base_row(
                definition,
                platform_config,
                enabled,
                "needs_config",
                False,
                "Configure OAuth: TASTYTRADE_CLIENT_SECRET e TASTYTRADE_REFRESH_TOKEN no ambiente.",
            )
            row["base_url"] = settings.tastytrade_base_url
            return row

        try:
            authorization = await self._tastytrade_authorization(has_oauth)
            accounts_response = await self.client.get(
                f"{settings.tastytrade_base_url}/customers/me/accounts",
                headers={"Authorization": authorization},
            )
            accounts_response.raise_for_status()
            accounts = (accounts_response.json().get("data") or {}).get("items") or []
            account_numbers = [
                (item.get("account") or {}).get("account-number")
                for item in accounts
                if (item.get("account") or {}).get("account-number")
            ]
            configured_account = settings.tastytrade_account_number
            if configured_account and configured_account not in account_numbers:
                row = self._base_row(
                    definition,
                    platform_config,
                    enabled,
                    "error",
                    False,
                    "OAuth validou, mas a conta configurada não apareceu na lista do sandbox.",
                )
                row.update({
                    "base_url": settings.tastytrade_base_url,
                    "accounts_count": len(account_numbers),
                    "account_number": configured_account,
                })
                return row

            latency_ms = int((time.perf_counter() - started) * 1000)
            row = self._base_row(
                definition,
                platform_config,
                enabled,
                "connected",
                True,
                "OAuth sandbox conectado; contas sandbox visíveis. Execução segue em modo demo/paper.",
            )
            row.update({
                "latency_ms": latency_ms,
                "base_url": settings.tastytrade_base_url,
                "accounts_count": len(account_numbers),
                "account_number": configured_account or (account_numbers[0] if account_numbers else ""),
                "auth_mode": "oauth_refresh_token" if has_oauth else "legacy_session",
            })
            return row
        except httpx.HTTPStatusError as exc:
            row = self._base_row(definition, platform_config, enabled, "error", False, "Falha no handshake da tastytrade Sandbox.")
            row.update({
                "base_url": settings.tastytrade_base_url,
                "error": f"HTTP {exc.response.status_code}",
            })
            return row
        except Exception as exc:
            row = self._base_row(definition, platform_config, enabled, "error", False, "Falha no handshake da tastytrade Sandbox.")
            row.update({"base_url": settings.tastytrade_base_url, "error": type(exc).__name__})
            return row

    async def _tastytrade_authorization(self, use_oauth: bool) -> str:
        if use_oauth:
            token_payload = {
                "grant_type": "refresh_token",
                "refresh_token": settings.tastytrade_refresh_token,
                "client_secret": settings.tastytrade_client_secret,
            }
            if settings.tastytrade_client_id:
                token_payload["client_id"] = settings.tastytrade_client_id
            response = await self.client.post(
                f"{settings.tastytrade_base_url}/oauth/token",
                data=token_payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            token = response.json().get("access_token")
            if not token:
                raise ValueError("missing_access_token")
            return f"Bearer {token}"

        response = await self.client.post(
            f"{settings.tastytrade_base_url}/sessions",
            json={
                "login": settings.tastytrade_username,
                "password": settings.tastytrade_password,
                "remember-me": False,
            },
        )
        response.raise_for_status()
        token = (response.json().get("data") or {}).get("session-token")
        if not token:
            raise ValueError("missing_session_token")
        return str(token)

    async def _iqoption_status(
        self,
        definition: PlatformDefinition,
        platform_config: dict[str, Any],
        enabled: bool,
        iq_extension: dict[str, Any],
    ) -> dict[str, Any]:
        started = time.perf_counter()
        effective_enabled = bool(enabled)
        if not effective_enabled:
            return self._base_row(definition, platform_config, effective_enabled, "disabled", False, "Desativado na configuracao.")
        if not iq_extension or not iq_extension.get("connected"):
            row = self._base_row(
                definition,
                platform_config,
                effective_enabled,
                "waiting_extension",
                False,
                "Aguardando a extensao IQ enviar estado vivo para o bridge.",
            )
            row["base_url"] = settings.iq_bridge_url
            return row

        latency_ms = int((time.perf_counter() - started) * 1000)
        row = self._base_row(
            definition,
            platform_config,
            effective_enabled,
            "connected",
            True,
            "IQ conectada via extensao Chrome; mercado e execucao passam pelo bridge local.",
        )
        row.update({
            "base_url": settings.iq_bridge_url,
            "latency_ms": latency_ms,
            "paper_only": True,
            "demo_mode": True,
            "session_id": iq_extension.get("session_id"),
            "asset": iq_extension.get("asset"),
            "market_type": iq_extension.get("market_type"),
            "active_id": iq_extension.get("active_id"),
            "buy_window_open": iq_extension.get("buy_window_open"),
            "payout_pct": iq_extension.get("payout_pct"),
            "practice_balance": iq_extension.get("balance"),
            "practice_selected": True,
        })
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
