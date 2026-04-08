import asyncio
import json
import time
from datetime import datetime, time as datetime_time, timedelta, timezone
from typing import Any

import httpx
from zoneinfo import ZoneInfo

from .ai import RedSystemsAI
from .config import settings
from .db import Database
from .iqoption_demo import IQOptionDemoAdapter
from .market import BinanceMarketClient
from .news import NewsClient
from .platforms import PlatformRegistry
from .strategy import (
    DEFAULT_CONFIG,
    RISK_PROFILES,
    available_risk_profiles,
    build_candidates,
    build_critic_prompt,
    build_decision_prompt,
    deep_merge,
    normalize_confidence,
)


BRT_TZ = timezone(timedelta(hours=-3), "BRT")
try:
    BRT_TZ = ZoneInfo("America/Sao_Paulo")
except Exception:
    pass

IQ_GATE_PROFILES: dict[str, dict[str, Any]] = {
    "conservative": {
        "min_votes": 4,
        "recovery_cross": 4,
        "recovery_same": 5,
        "same_side_recovery_min": 5,
        "exhaustion_min": 5,
        "gale2_same_min": 5,
        "same_side_exhausted_min": 5,
        "same_side_loss_min": 5,
        "code_wait_min": 5,
        "code_conflict_min": 5,
        "invalid_block_count": 1,
        "invalid_block_tier": 5,
        "learned_mid_min": 5,
        "learned_high_min": 5,
        "recovery_specialist_guard_min": 1,
        "gale2_guardless_invalid_max": 1,
    },
    "balanced": {
        "min_votes": 3,
        "recovery_cross": 3,
        "recovery_same": 4,
        "same_side_recovery_min": 4,
        "exhaustion_min": 4,
        "gale2_same_min": 5,
        "same_side_exhausted_min": 5,
        "same_side_loss_min": 5,
        "code_wait_min": 4,
        "code_conflict_min": 5,
        "invalid_block_count": 2,
        "invalid_block_tier": 4,
        "learned_mid_min": 4,
        "learned_high_min": 5,
        "recovery_specialist_guard_min": 1,
        "gale2_guardless_invalid_max": 1,
    },
    "aggressive": {
        "min_votes": 2,
        "recovery_cross": 2,
        "recovery_same": 3,
        "same_side_recovery_min": 3,
        "exhaustion_min": 3,
        "gale2_same_min": 4,
        "same_side_exhausted_min": 4,
        "same_side_loss_min": 4,
        "code_wait_min": 3,
        "code_conflict_min": 4,
        "invalid_block_count": 3,
        "invalid_block_tier": 3,
        "learned_mid_min": 3,
        "learned_high_min": 4,
        "recovery_specialist_guard_min": 1,
        "gale2_guardless_invalid_max": 1,
    },
    "full_aggressive": {
        "min_votes": 2,
        "recovery_cross": 2,
        "recovery_same": 2,
        "same_side_recovery_min": 3,
        "exhaustion_min": 3,
        "gale2_same_min": 4,
        "same_side_exhausted_min": 4,
        "same_side_loss_min": 3,
        "code_wait_min": 2,
        "code_conflict_min": 3,
        "invalid_block_count": 4,
        "invalid_block_tier": 2,
        "learned_mid_min": 2,
        "learned_high_min": 3,
        "recovery_specialist_guard_min": 1,
        "gale2_guardless_invalid_max": 1,
    },
}


class TraderRuntime:
    def __init__(self, db: Database, market: BinanceMarketClient, news: NewsClient, ai: RedSystemsAI):
        self.db = db
        self.market = market
        self.news_client = news
        self.ai = ai
        self.iqoption = IQOptionDemoAdapter()
        self.task: asyncio.Task | None = None
        self.market_task: asyncio.Task | None = None
        self.running = False
        self.latest_snapshots: dict[str, dict[str, Any]] = {}
        self.latest_news: dict[str, Any] = {}
        self.platforms = PlatformRegistry()
        self.platform_statuses: list[dict[str, Any]] = []
        self.last_platforms_at = 0.0
        self.committee_state: dict[str, Any] = {}
        self.committee_cycle_seq = 0
        self.models: list[str] = []
        self.last_news_at = 0.0
        self.last_trade_at = float(self.db.get_kv("last_trade_at", 0) or 0)
        self.last_decision_at = 0.0
        self.last_wait_event_at = 0.0
        self.last_learning_at = 0.0
        self.learning_task: asyncio.Task | None = None
        self.asset_cooldowns: dict[str, float] = {}
        self.queues: set[asyncio.Queue] = set()
        self.cycle_lock = asyncio.Lock()
        self.market_lock = asyncio.Lock()
        if self.db.get_kv("config") is None:
            self.db.set_kv("config", DEFAULT_CONFIG)
        if self.db.get_kv("wallet") is None:
            self.db.set_kv("wallet", {"initial_balance_brl": DEFAULT_CONFIG["initial_balance_brl"]})

    def config(self) -> dict[str, Any]:
        return deep_merge(DEFAULT_CONFIG, self.db.get_kv("config", {}) or {})

    def update_config(self, patch: dict[str, Any]) -> dict[str, Any]:
        current = self.config()
        old_profile = current.get("risk_profile")
        merged = deep_merge(current, patch)
        if merged.get("risk_profile") not in RISK_PROFILES:
            merged["risk_profile"] = DEFAULT_CONFIG["risk_profile"]
        if "risk_profile" in patch and merged.get("risk_profile") != old_profile:
            merged = deep_merge(merged, RISK_PROFILES[merged["risk_profile"]]["settings"])
        merged["symbols"] = [str(item).upper() for item in merged.get("symbols", []) if str(item).strip()]
        merged["tradable_symbols"] = [str(item).upper() for item in merged.get("tradable_symbols", []) if str(item).strip()]
        self.db.set_kv("config", merged)
        self.publish("config", "Configuracao atualizada", {"config": merged})
        return merged

    async def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.task = asyncio.create_task(self.loop())
        self.market_task = asyncio.create_task(self.market_loop())
        self.publish("runtime", "RED Trader iniciado", {})

    async def stop(self) -> None:
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        if self.market_task:
            self.market_task.cancel()
            try:
                await self.market_task
            except asyncio.CancelledError:
                pass
        self.publish("runtime", "RED Trader parado", {})

    async def market_loop(self) -> None:
        while self.running:
            started = time.time()
            config = self.config()
            try:
                await self.refresh_market(config, reason="market_loop")
            except Exception as exc:
                self.publish("market:error", "Falha ao atualizar mercado rapido", {"error": repr(exc)})
            elapsed = time.time() - started
            min_sleep = 0.35 if config.get("market_provider") == "iqoption_demo" else 3
            await asyncio.sleep(max(min_sleep, float(config.get("market_poll_seconds", 20)) - elapsed))

    async def loop(self) -> None:
        while self.running:
            started = time.time()
            try:
                await self.cycle(reason="loop")
            except Exception as exc:
                self.publish("error", "Falha no ciclo principal", {"error": repr(exc)})
            elapsed = time.time() - started
            config = self.config()
            min_sleep = 1 if config.get("market_provider") == "iqoption_demo" else 10
            await asyncio.sleep(max(min_sleep, float(config.get("decision_poll_seconds", 5)) - elapsed))

    async def cycle(self, reason: str = "manual") -> None:
        async with self.cycle_lock:
            config = self.config()
            if not self.models:
                try:
                    self.models = await self.ai.list_models()
                except Exception as exc:
                    self.publish("ai:error", "Nao consegui carregar modelos do proxy", {"error": repr(exc)})

            now = time.time()
            if now - self.last_news_at > float(config.get("news_poll_seconds", 300)):
                await self.refresh_news()
            if now - self.last_platforms_at > 60:
                await self.refresh_platforms(config)

            await self.refresh_market(config, reason=reason)
            await self.handle_exits(config)
            await self.maybe_send_trade_summaries(config)
            await self.maybe_learn_from_iq_history(config)
            await self.maybe_enter(config)

    async def refresh_market(self, config: dict[str, Any], reason: str = "loop") -> dict[str, dict[str, Any]]:
        async with self.market_lock:
            symbols = config.get("symbols") or DEFAULT_CONFIG["symbols"]
            if config.get("market_provider") == "iqoption_demo":
                snapshots = await self.iqoption.fetch_symbols(symbols)
            else:
                snapshots = await self.market.fetch_symbols(symbols)
            self.latest_snapshots = snapshots
            for symbol, snapshot in snapshots.items():
                self.db.save_snapshot(symbol, snapshot)
            if reason == "market_loop":
                self.broadcast_status()
            else:
                self.publish("market", "Mercado atualizado", {"symbols": list(snapshots.keys()), "reason": reason})
            return snapshots

    async def refresh_news(self) -> None:
        try:
            self.latest_news = await self.news_client.fetch()
            self.last_news_at = time.time()
            self.publish("news", "Noticias e sentimento atualizados", self.latest_news)
        except Exception as exc:
            self.publish("news:error", "Falha ao buscar noticias", {"error": repr(exc)})

    async def refresh_platforms(self, config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        try:
            config = config or self.config()
            self.platform_statuses = await self.platforms.status(config)
            self.last_platforms_at = time.time()
            connected = [row["id"] for row in self.platform_statuses if row.get("connected")]
            self.publish(
                "platforms",
                "Plataformas sincronizadas",
                {"connected": connected, "total": len(self.platform_statuses)},
            )
        except Exception as exc:
            self.publish("platforms:error", "Falha ao sincronizar plataformas", {"error": repr(exc)})
        return self.platform_statuses

    @staticmethod
    def _committee_roles() -> list[str]:
        return ["fast_filter", "decision", "critic", "premium_4", "premium_5"]

    def _committee_progress(self) -> dict[str, Any]:
        roles = self.committee_state.get("roles") or {}
        total = sum(1 for item in roles.values() if item.get("counts_for_progress", True))
        completed = sum(
            1
            for item in roles.values()
            if item.get("counts_for_progress", True) and item.get("status") in {"done", "error", "timeout", "reused", "missing"}
        )
        running = sum(
            1
            for item in roles.values()
            if item.get("counts_for_progress", True) and item.get("status") == "running"
        )
        queued = max(0, total - completed - running)
        percent = round((completed / total) * 100, 1) if total else 100.0
        return {
            "total": total,
            "completed": completed,
            "running": running,
            "queued": queued,
            "percent": percent,
        }

    def begin_committee_cycle(self, candidate: dict[str, Any], models: dict[str, Any], gate_profile: dict[str, Any]) -> int:
        self.committee_cycle_seq += 1
        cycle_id = self.committee_cycle_seq
        symbol = str(candidate.get("symbol") or "-")
        seen: set[str] = set()
        roles: dict[str, Any] = {}
        for role in self._committee_roles():
            model = str(models.get(role) or "").strip()
            status = "queued"
            summary = "Na fila para analisar este par."
            counts_for_progress = True
            if not model:
                status = "missing"
                summary = "Modelo nao configurado para este papel."
            elif model in seen:
                status = "reused"
                summary = "Mesmo modelo ja esta cobrindo outro papel deste ciclo."
                counts_for_progress = False
            else:
                seen.add(model)
            roles[role] = {
                "role": role,
                "model": model,
                "symbol": symbol,
                "status": status,
                "decision": "WAIT",
                "confidence": 0.0,
                "latency_ms": None,
                "summary": summary,
                "error": None,
                "updated_at": time.time(),
                "counts_for_progress": counts_for_progress,
            }
        self.committee_state = {
            "id": cycle_id,
            "active": True,
            "symbol": symbol,
            "started_at": time.time(),
            "finished_at": None,
            "profile": str(gate_profile.get("key") or ""),
            "candidate": {
                "symbol": symbol,
                "direction": candidate.get("action"),
                "technical_score": candidate.get("score"),
                "risk_reward": candidate.get("risk_reward"),
                "recovery_stage": ((candidate.get("recovery_context") or {}).get("stage") or 0),
            },
            "roles": roles,
            "progress": {},
            "result": None,
        }
        self.committee_state["progress"] = self._committee_progress()
        self.broadcast_status()
        return cycle_id

    def update_committee_role(self, cycle_id: int, role: str, status: str, **extra: Any) -> None:
        if not self.committee_state or self.committee_state.get("id") != cycle_id:
            return
        role_state = (self.committee_state.get("roles") or {}).get(role)
        if not role_state:
            return
        role_state.update(extra)
        role_state["status"] = status
        role_state["updated_at"] = time.time()
        self.committee_state["progress"] = self._committee_progress()
        self.broadcast_status()

    def finalize_committee_cycle(
        self,
        cycle_id: int,
        *,
        approved: bool,
        reason: str,
        consensus: dict[str, Any] | None = None,
        action: str | None = None,
    ) -> None:
        if not self.committee_state or self.committee_state.get("id") != cycle_id:
            return
        self.committee_state["active"] = False
        self.committee_state["finished_at"] = time.time()
        votes = (consensus or {}).get("votes") or []
        valid_votes = [vote for vote in votes if vote.get("valid") and vote.get("direction") in {"CALL", "PUT"}]
        self.committee_state["result"] = {
            "approved": approved,
            "reason": reason,
            "direction": action or (consensus or {}).get("direction"),
            "tier": int((consensus or {}).get("tier") or len(valid_votes)),
            "valid_votes": len(valid_votes),
            "invalid_votes": int((consensus or {}).get("invalid_vote_count") or max(0, len(votes) - len(valid_votes))),
            "min_votes": int(
                (consensus or {}).get("required_recovery_votes")
                or (consensus or {}).get("min_votes")
                or 0
            ),
            "votes": votes,
        }
        self.committee_state["progress"] = self._committee_progress()
        self.broadcast_status()

    def _notify_enabled(self) -> bool:
        return bool(settings.redia_notify_url and settings.redia_notify_token and settings.redia_notify_to)

    @staticmethod
    def _money(value: Any) -> str:
        try:
            return f"${float(value):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
        except (TypeError, ValueError):
            return "$0,00"

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(BRT_TZ).strftime("%d/%m/%Y %H:%M:%S BRT")

    @staticmethod
    def _timestamp_from_epoch(value: Any) -> str:
        try:
            return datetime.fromtimestamp(float(value), BRT_TZ).strftime("%d/%m/%Y %H:%M:%S BRT")
        except (TypeError, ValueError, OSError):
            return "-"

    @staticmethod
    def _trade_outcome(pnl_brl: Any, status: str | None = None) -> str:
        try:
            pnl = float(pnl_brl or 0)
        except (TypeError, ValueError):
            pnl = 0.0
        if pnl > 0:
            return "WIN"
        if pnl < 0:
            return "LOSS"
        return str(status or "EMPATE").replace("iqoption_demo:", "").upper()

    @staticmethod
    def _profit_factor(gross_profit: float, gross_loss: float) -> str:
        if abs(gross_loss) < 0.000001:
            return "∞" if gross_profit > 0 else "0,00"
        return f"{gross_profit / abs(gross_loss):.2f}".replace(".", ",")

    def _closed_iq_trades(self, limit: int = 5000) -> list[dict[str, Any]]:
        rows = []
        for trade in self.db.list_trades(limit=limit):
            metadata = trade.get("metadata") or {}
            if trade.get("status") == "CLOSED" and metadata.get("execution_provider") == "iqoption_demo":
                rows.append(trade)
        rows.sort(key=lambda item: int(item.get("id") or 0))
        return rows

    def _build_trade_summary_payload(
        self,
        trades: list[dict[str, Any]],
        title: str,
        period_label: str,
    ) -> dict[str, Any]:
        total = len(trades)
        wins = losses = neutral = 0
        gross_profit = 0.0
        gross_loss = 0.0
        pnl_total = 0.0
        stake_total = 0.0
        gales = 0
        symbols: dict[str, dict[str, Any]] = {}
        operations: list[dict[str, Any]] = []

        for trade in trades[-24:]:
            metadata = trade.get("metadata") or {}
            pnl = float(trade.get("pnl_brl") or 0)
            stake = float(trade.get("position_brl") or 0)
            gale_stage = int(metadata.get("gale_stage") or 0)
            symbol = str(trade.get("symbol") or "-")
            outcome = self._trade_outcome(pnl, str(trade.get("exit_reason") or ""))
            pnl_total += pnl
            stake_total += stake
            if gale_stage > 0:
                gales += 1
            if pnl > 0:
                wins += 1
                gross_profit += pnl
            elif pnl < 0:
                losses += 1
                gross_loss += pnl
            else:
                neutral += 1

            bucket = symbols.setdefault(symbol, {"symbol": symbol, "count": 0, "wins": 0, "losses": 0, "neutral": 0, "pnl": 0.0})
            bucket["count"] += 1
            bucket["pnl"] += pnl
            if outcome == "WIN":
                bucket["wins"] += 1
            elif outcome == "LOSS":
                bucket["losses"] += 1
            else:
                bucket["neutral"] += 1

            operations.append({
                "id": trade.get("id"),
                "symbol": symbol,
                "direction": str(trade.get("side") or "").upper(),
                "stake": self._money(stake),
                "result": outcome,
                "pnl": self._money(pnl),
                "pnl_raw": pnl,
                "gale_stage": gale_stage,
                "opened_at": self._timestamp_from_epoch(trade.get("opened_at")),
                "closed_at": self._timestamp_from_epoch(trade.get("closed_at") or trade.get("opened_at")),
                "exit_reason": str(trade.get("exit_reason") or "").replace("iqoption_demo:", ""),
            })

        win_rate = (wins / total * 100) if total else 0.0
        avg_stake = (stake_total / total) if total else 0.0
        best_trade = max(operations, key=lambda item: float(item["pnl_raw"]), default=None)
        worst_trade = min(operations, key=lambda item: float(item["pnl_raw"]), default=None)
        symbol_rows = sorted(symbols.values(), key=lambda item: abs(float(item["pnl"])), reverse=True)

        return {
            "title": title,
            "timestamp": self._timestamp(),
            "period": period_label,
            "market": "IQ Option Demo / OTC",
            "total": total,
            "wins": wins,
            "losses": losses,
            "neutral": neutral,
            "win_rate": f"{win_rate:.1f}%",
            "pnl_total": self._money(pnl_total),
            "pnl_total_raw": pnl_total,
            "gross_profit": self._money(gross_profit),
            "gross_loss": self._money(gross_loss),
            "profit_factor": self._profit_factor(gross_profit, gross_loss),
            "stake_total": self._money(stake_total),
            "avg_stake": self._money(avg_stake),
            "gales": gales,
            "symbols": [
                {
                    **item,
                    "pnl": self._money(item["pnl"]),
                }
                for item in symbol_rows[:8]
            ],
            "operations": operations,
            "best_trade": best_trade,
            "worst_trade": worst_trade,
            "balance": self._money(self.wallet_summary().get("equity_brl")),
        }

    def _summary_fallback_text(self, payload: dict[str, Any], *, daily: bool = False) -> str:
        pnl_raw = float(payload.get("pnl_total_raw") or 0)
        pnl_icon = "✅" if pnl_raw > 0 else ("❌" if pnl_raw < 0 else "➖")
        title_icon = "🌙" if daily else "📊"
        symbol_lines = []
        for item in payload.get("symbols") or []:
            symbol_lines.append(
                f"• *{item['symbol']}*: {item['count']} ops · {item['wins']}W/{item['losses']}L · P/L *{item['pnl']}*"
            )
        operations = payload.get("operations") or []
        operation_lines = []
        shown_operations = operations[-10:] if daily else operations
        for item in shown_operations:
            icon = "✅" if item["result"] == "WIN" else ("❌" if item["result"] == "LOSS" else "➖")
            gale = f" · G{item['gale_stage']}" if int(item.get("gale_stage") or 0) else ""
            operation_lines.append(
                f"• {icon} *#{item['id']}* {item['symbol']} {item['direction']} · {item['stake']}{gale} · {item['pnl']}"
            )
        if daily and len(operations) > len(shown_operations):
            operation_lines.append(f"• _+{len(operations) - len(shown_operations)} operações anteriores no período_")

        if not symbol_lines:
            symbol_lines.append("• _Sem ativos no período._")
        if not operation_lines:
            operation_lines.append("• _Sem operações fechadas no período._")

        header = [
            f"{title_icon} *RED Trader | {payload['title']}*",
            f"🕒 {payload['timestamp']}",
            f"🏛 Mercado: *{payload['market']}*",
            f"📌 Período: {payload['period']}",
            "",
            f"{pnl_icon} Resultado: *{payload['pnl_total']}*",
            f"🎯 Win rate: *{payload['win_rate']}* · {payload['wins']}W/{payload['losses']}L/{payload['neutral']}N",
            f"⚖️ Profit factor: *{payload['profit_factor']}*",
            f"💵 Volume: *{payload['stake_total']}* · Média: *{payload['avg_stake']}*",
            f"🧬 Gales usados: *{payload['gales']}*",
            f"🏦 Banca IQ: *{payload['balance']}*",
            "",
            "🪙 *Ativos:*",
            "\n".join(symbol_lines),
            "",
            "📋 *Operações:*",
            "\n".join(operation_lines),
        ]
        return "\n".join(header)

    async def send_trade_summary(
        self,
        config: dict[str, Any],
        event: str,
        trades: list[dict[str, Any]],
        title: str,
        period_label: str,
        *,
        daily: bool = False,
    ) -> None:
        payload = self._build_trade_summary_payload(trades, title, period_label)
        fallback = self._summary_fallback_text(payload, daily=daily)
        operations = payload.get("operations") or []
        ai_payload = {
            **payload,
            "operations": operations[-10:] if daily else operations,
            "operation_count": len(operations),
            "omitted_operations": max(0, len(operations) - (10 if daily else len(operations))),
        }
        text = await self.polish_trade_notification(config, event, ai_payload, fallback)
        await self.send_whatsapp_notification(
            text,
            {
                "event": event,
                "trade_ids": [item.get("id") for item in trades],
                "period": period_label,
                "daily": daily,
            },
        )

    async def maybe_send_trade_summaries(self, config: dict[str, Any]) -> None:
        if not self._notify_enabled():
            return
        state = self.db.get_kv("whatsapp_trade_summary_state", {}) or {}
        closed_trades = self._closed_iq_trades()

        latest_id = int(closed_trades[-1].get("id") or 0) if closed_trades else 0
        state_changed = False
        if "last_batch_trade_id" not in state:
            state["last_batch_trade_id"] = latest_id
            state_changed = True
            self.publish(
                "whatsapp:summary_state_initialized",
                "Resumo de 5 operacoes inicializado sem backfill",
                {"last_batch_trade_id": latest_id},
            )
        else:
            last_batch_id = int(state.get("last_batch_trade_id") or 0)
            pending = [item for item in closed_trades if int(item.get("id") or 0) > last_batch_id]
            if len(pending) >= 5:
                batch = pending[:5]
                state["last_batch_trade_id"] = int(batch[-1].get("id") or last_batch_id)
                state_changed = True
                period = f"{batch[0].get('id')} até {batch[-1].get('id')} · {self._timestamp_from_epoch(batch[0].get('closed_at'))} -> {self._timestamp_from_epoch(batch[-1].get('closed_at'))}"
                asyncio.create_task(
                    self.send_trade_summary(
                        config,
                        "summary_5_trades",
                        batch,
                        "Resumo das últimas 5 operações",
                        period,
                        daily=False,
                    )
                )
                self.publish(
                    "whatsapp:summary_scheduled",
                    "Resumo das ultimas 5 operacoes agendado",
                    {"trade_ids": [item.get("id") for item in batch], "last_batch_trade_id": state["last_batch_trade_id"]},
                )

        now_brt = datetime.now(BRT_TZ)
        if now_brt.hour > 0 or (now_brt.hour == 0 and now_brt.minute >= 1):
            target_day = (now_brt.date() - timedelta(days=1))
            target_key = target_day.isoformat()
            if "last_daily_date" not in state:
                state["last_daily_date"] = target_key
                state_changed = True
                self.publish(
                    "whatsapp:daily_summary_initialized",
                    "Resumo diario inicializado sem backfill",
                    {"last_daily_date": target_key},
                )
            elif state.get("last_daily_date") != target_key:
                start = datetime.combine(target_day, datetime_time(hour=0, minute=1), tzinfo=BRT_TZ).timestamp()
                end = datetime.combine(target_day, datetime_time(hour=23, minute=59, second=59), tzinfo=BRT_TZ).timestamp()
                daily_trades = [
                    item for item in closed_trades
                    if start <= float(item.get("closed_at") or item.get("opened_at") or 0) <= end
                ]
                state["last_daily_date"] = target_key
                state_changed = True
                asyncio.create_task(
                    self.send_trade_summary(
                        config,
                        "daily_summary",
                        daily_trades,
                        "Fechamento diário",
                        f"{target_day.strftime('%d/%m/%Y')} · 00:01 até 23:59 BRT",
                        daily=True,
                    )
                )
                self.publish(
                    "whatsapp:daily_summary_scheduled",
                    "Resumo diario de operacoes agendado",
                    {"date": target_key, "trades": len(daily_trades)},
                )

        if state_changed:
            self.db.set_kv("whatsapp_trade_summary_state", state)

    def iq_learning_state(self) -> dict[str, Any]:
        state = self.db.get_kv("iqoption_learning_state", {}) or {}
        return {
            "last_code_trade_id": int(state.get("last_code_trade_id") or 0),
            "last_model_trade_id": int(state.get("last_model_trade_id") or 0),
            "updated_at": float(state.get("updated_at") or 0),
            "model_updated_at": float(state.get("model_updated_at") or 0),
            "lessons": list(state.get("lessons") or [])[-20:],
            "avoid_patterns": list(state.get("avoid_patterns") or [])[-30:],
            "symbol_direction_stats": dict(state.get("symbol_direction_stats") or {}),
            "recovery_rules": list(state.get("recovery_rules") or [])[-12:],
            "last_reflection": dict(state.get("last_reflection") or {}),
        }

    def set_iq_learning_state(self, state: dict[str, Any]) -> None:
        clean = {
            **state,
            "lessons": list(state.get("lessons") or [])[-20:],
            "avoid_patterns": list(state.get("avoid_patterns") or [])[-30:],
            "recovery_rules": list(state.get("recovery_rules") or [])[-12:],
            "updated_at": time.time(),
        }
        self.db.set_kv("iqoption_learning_state", clean)

    async def maybe_learn_from_iq_history(self, config: dict[str, Any]) -> None:
        learning = config.get("iqoption_learning") or {}
        if not learning.get("enabled", True):
            return
        closed = self._closed_iq_trades(limit=max(200, int(learning.get("recent_limit") or 40) * 4))
        if not closed:
            return

        state = self.iq_learning_state()
        updated_state = self.update_code_learning_state(config, closed, state)
        if updated_state != state:
            state = updated_state
            self.set_iq_learning_state(state)

        if not learning.get("use_model_reflection", True):
            return
        if self.learning_task and not self.learning_task.done():
            return
        if self.db.open_trades():
            return
        now = time.time()
        if now - self.last_learning_at < float(learning.get("interval_seconds") or 150):
            return
        last_model_trade_id = int(state.get("last_model_trade_id") or 0)
        new_trades = [item for item in closed if int(item.get("id") or 0) > last_model_trade_id]
        if len(new_trades) < int(learning.get("min_new_closed") or 5):
            return
        self.last_learning_at = now
        recent_limit = int(learning.get("recent_limit") or 40)
        batch = closed[-recent_limit:]
        self.learning_task = asyncio.create_task(self.reflect_iq_learning(config, batch, state))
        self.publish(
            "learning:scheduled",
            "Aprendizado operacional agendado",
            {"trades": len(batch), "new_trades": len(new_trades), "last_trade_id": closed[-1].get("id")},
        )

    def update_code_learning_state(
        self,
        config: dict[str, Any],
        closed: list[dict[str, Any]],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        latest_id = int(closed[-1].get("id") or 0)
        if latest_id <= int(state.get("last_code_trade_id") or 0):
            return state
        techniques = config.get("iqoption_techniques") or {}
        stats: dict[str, dict[str, Any]] = {}
        avoid_patterns = [item for item in list(state.get("avoid_patterns") or []) if float(item.get("expires_at") or 0) > time.time()]
        lessons = list(state.get("lessons") or [])

        for trade in closed[-80:]:
            metadata = trade.get("metadata") or {}
            side = _binary_direction(trade.get("side")) or str(trade.get("side") or "WAIT").upper()
            symbol = str(trade.get("symbol") or "-")
            key = f"{symbol}:{side}"
            pnl = float(trade.get("pnl_brl") or 0)
            row = stats.setdefault(key, {"symbol": symbol, "direction": side, "trades": 0, "wins": 0, "losses": 0, "pnl": 0.0, "last_ids": []})
            row["trades"] += 1
            row["pnl"] += pnl
            row["last_ids"].append(trade.get("id"))
            row["last_ids"] = row["last_ids"][-5:]
            if pnl > 0:
                row["wins"] += 1
            elif pnl < 0:
                row["losses"] += 1

            candidate = metadata.get("candidate") or {}
            code_context = candidate.get("code_context") or {}
            traps = set(code_context.get("traps") or [])
            gale_stage = int(metadata.get("gale_stage") or 0)
            if pnl < 0 and techniques.get("anti_repeat_loss", True):
                severity = 0.45 + min(0.35, gale_stage * 0.12)
                if _direction_exhausted(side, code_context):
                    severity += 0.2
                avoid_patterns.append({
                    "key": key,
                    "symbol": symbol,
                    "direction": side,
                    "reason": "loss recente com exaustao" if traps else "loss recente",
                    "severity": round(min(1.0, severity), 2),
                    "expires_at": time.time() + (240 + gale_stage * 120),
                    "trade_id": trade.get("id"),
                    "gale_stage": gale_stage,
                    "traps": list(traps),
                })

        for key, row in stats.items():
            if row["trades"] >= 5:
                win_rate = row["wins"] / max(1, row["trades"]) * 100
                row["win_rate"] = round(win_rate, 1)
                if row["losses"] >= 3 and win_rate < 45 and techniques.get("anti_repeat_loss", True):
                    lessons.append(
                        f"{key}: win rate baixo ({win_rate:.1f}%) nas ultimas amostras; exigir consenso maior ou procurar setup oposto."
                    )

        dedup_lessons = []
        seen = set()
        for lesson in lessons:
            if lesson in seen:
                continue
            seen.add(lesson)
            dedup_lessons.append(str(lesson)[:260])

        return {
            **state,
            "last_code_trade_id": latest_id,
            "symbol_direction_stats": stats,
            "avoid_patterns": avoid_patterns[-30:],
            "lessons": dedup_lessons[-20:],
            "updated_at": time.time(),
        }

    async def reflect_iq_learning(self, config: dict[str, Any], trades: list[dict[str, Any]], state: dict[str, Any]) -> None:
        learning = config.get("iqoption_learning") or {}
        model = str(learning.get("model") or (config.get("models") or {}).get("report") or "qwen/qwen3-next-80b-a3b-instruct (NVIDIA)")
        compact_trades = []
        for trade in trades:
            metadata = trade.get("metadata") or {}
            candidate = metadata.get("candidate") or {}
            decision = metadata.get("decision") or {}
            consensus = decision.get("consensus") or metadata.get("consensus") or {}
            compact_trades.append({
                "id": trade.get("id"),
                "symbol": trade.get("symbol"),
                "side": trade.get("side"),
                "pnl": trade.get("pnl_brl"),
                "stake": trade.get("position_brl"),
                "gale_stage": metadata.get("gale_stage", 0),
                "exit_reason": trade.get("exit_reason"),
                "technical_score": candidate.get("technical_score"),
                "checks": candidate.get("checks"),
                "code_context": candidate.get("code_context"),
                "consensus_tier": consensus.get("tier"),
                "votes": [
                    {
                        "role": vote.get("role"),
                        "model": vote.get("model"),
                        "direction": vote.get("direction"),
                        "valid": vote.get("valid"),
                        "confidence": vote.get("confidence"),
                        "latency_ms": vote.get("latency_ms"),
                    }
                    for vote in (consensus.get("votes") or [])[:5]
                ],
            })
        system = (
            "Voce e um especialista de pesquisa em trading DEMO, analise tecnica, opcoes binarias e gestao de risco. "
            "Seu papel e aprender com erros sem prometer lucro. Gere regras praticas, curtas e testaveis para o RED Trader."
        )
        user = (
            "Analise as operacoes IQ Option DEMO abaixo. Identifique padroes de loss, setups que devem exigir mais consenso, "
            "tecnicas de recuperacao que parecem ruins e filtros tecnicos que o codigo deve aplicar. "
            "Nao diga que e infalivel. Responda SOMENTE JSON valido, compacto, sem markdown, neste formato: "
            '{"lessons":["curto"],"avoid_patterns":[{"symbol":"EURUSD-OTC|*","direction":"CALL|PUT|*","reason":"curto","severity":0.0,"cooldown_minutes":3}],'
            '"recovery_rules":["curto"],"technique_suggestions":["curto"]}'
            f"\n\nESTADO_ATUAL:\n{json.dumps(state, ensure_ascii=False)[:2500]}"
            f"\n\nOPERACOES:\n{json.dumps(compact_trades, ensure_ascii=False)}"
        )
        try:
            result = await self.ai.chat_json(
                model,
                system,
                user,
                temperature=0.1,
                timeout=28,
                num_predict=900,
                num_ctx=8192,
            )
            latest_id = int(trades[-1].get("id") or 0) if trades else int(state.get("last_model_trade_id") or 0)
            current = self.iq_learning_state()
            now = time.time()
            new_lessons = [str(item)[:260] for item in result.get("lessons", []) if str(item).strip()]
            new_rules = [str(item)[:260] for item in result.get("recovery_rules", []) if str(item).strip()]
            avoid_patterns = list(current.get("avoid_patterns") or [])
            for item in result.get("avoid_patterns", []) or []:
                direction = str(item.get("direction") or "*").upper()
                symbol = str(item.get("symbol") or "*").upper()
                avoid_patterns.append({
                    "key": f"{symbol}:{direction}",
                    "symbol": symbol,
                    "direction": direction,
                    "reason": str(item.get("reason") or "reflexao de aprendizado")[:180],
                    "severity": max(0.0, min(1.0, _num(item.get("severity")) or 0.5)),
                    "expires_at": now + max(60, _num(item.get("cooldown_minutes")) * 60 or 240),
                    "source": "model_reflection",
                })
            merged = {
                **current,
                "last_model_trade_id": latest_id,
                "model_updated_at": now,
                "lessons": _dedup_tail(list(current.get("lessons") or []) + new_lessons, 20),
                "recovery_rules": _dedup_tail(list(current.get("recovery_rules") or []) + new_rules, 12),
                "avoid_patterns": avoid_patterns[-30:],
                "last_reflection": {
                    "model": model,
                    "trade_id": latest_id,
                    "technique_suggestions": [str(item)[:140] for item in (result.get("technique_suggestions", []) or [])[:6]],
                    "summary": "; ".join([str(item)[:120] for item in new_lessons[:3]])[:360],
                },
            }
            self.set_iq_learning_state(merged)
            self.db.add_analysis(
                symbol="IQ-LEARNING",
                role="learning",
                model=model,
                decision="LESSONS",
                confidence=None,
                latency_ms=result.get("_latency_ms"),
                summary="; ".join(new_lessons[:3])[:500],
                response=result,
                prompt={"system": system, "user": user[:6000]},
            )
            self.publish(
                "learning:updated",
                "Aprendizado operacional atualizado",
                {"model": model, "trade_id": latest_id, "lessons": new_lessons[:5], "recovery_rules": new_rules[:5]},
            )
        except Exception as exc:
            self.publish("learning:error", "Falha no aprendizado operacional", {"model": model, "error": repr(exc)})

    def learning_context_for_candidate(self, candidate: dict[str, Any]) -> dict[str, Any]:
        state = self.iq_learning_state()
        symbol = str(candidate.get("symbol") or "")
        direction = _binary_direction(candidate.get("action"))
        now = time.time()
        relevant_avoid = []
        for item in state.get("avoid_patterns") or []:
            if float(item.get("expires_at") or 0) <= now:
                continue
            if not _pattern_matches(item.get("symbol") or "*", symbol):
                continue
            if direction and not _pattern_matches(item.get("direction") or "*", direction):
                continue
            relevant_avoid.append(item)
        key = f"{symbol}:{direction}" if direction else symbol
        return {
            "active_avoid_patterns": relevant_avoid[:6],
            "lessons": list(state.get("lessons") or [])[-8:],
            "recovery_rules": list(state.get("recovery_rules") or [])[-6:],
            "stats_for_direction": (state.get("symbol_direction_stats") or {}).get(key),
            "last_reflection": {
                "model": (state.get("last_reflection") or {}).get("model"),
                "trade_id": (state.get("last_reflection") or {}).get("trade_id"),
                "technique_suggestions": list(((state.get("last_reflection") or {}).get("technique_suggestions") or []))[:4],
                "summary": str(((state.get("last_reflection") or {}).get("summary") or ""))[:360],
            },
        }

    def apply_iq_learning_to_candidates(self, candidates: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
        if not (config.get("iqoption_learning") or {}).get("enabled", True):
            return candidates
        techniques = config.get("iqoption_techniques") or {}
        adjusted = []
        for candidate in candidates:
            if candidate.get("trade_type") != "binary_options":
                adjusted.append(candidate)
                continue
            learned = self.learning_context_for_candidate(candidate)
            features = candidate.get("features") or {}
            code_context = candidate.get("code_context") or {}
            action = _binary_direction(candidate.get("action"))
            penalty = 0.0
            bonus = 0.0
            notes = []

            if techniques.get("anti_repeat_loss", True):
                for item in learned.get("active_avoid_patterns") or []:
                    severity = max(0.1, _num(item.get("severity")) or 0.4)
                    penalty += 18 * severity
                    notes.append(f"memoria evita {item.get('symbol')} {item.get('direction')}: {item.get('reason')}")

            trend_1m = features.get("trend_1m")
            trend_5m = features.get("trend_5m")
            trend_15m = features.get("trend_15m")
            rsi_1s = _num(features.get("rsi_1s"))
            rsi_1m = _num(features.get("rsi_1m"))
            rsi_5m = _num(features.get("rsi_5m"))
            change_1s_15 = _num(features.get("change_1s_15"))
            change_1m_15 = _num(features.get("change_1m_15"))
            vol_1m = _num(features.get("ret_std_1m_30"))

            if techniques.get("multi_timeframe_confluence", True):
                if action == "CALL" and trend_1m == trend_5m == trend_15m == "up":
                    bonus += 8
                    notes.append("confluencia multi-timeframe CALL")
                elif action == "PUT" and trend_1m == trend_5m == trend_15m == "down":
                    bonus += 8
                    notes.append("confluencia multi-timeframe PUT")
                elif action in {"CALL", "PUT"}:
                    penalty += 5
                    notes.append("timeframes mistos")

            if techniques.get("momentum_continuation", True):
                if action == "CALL" and change_1s_15 > 0 and change_1m_15 > 0 and rsi_1m < 76:
                    bonus += 6
                elif action == "PUT" and change_1s_15 < 0 and change_1m_15 < 0 and rsi_1m > 24:
                    bonus += 6
                else:
                    penalty += 3

            if techniques.get("reversal_exhaustion", True):
                if action == "CALL" and _direction_exhausted("CALL", code_context):
                    penalty += 18
                    notes.append("CALL em exaustao")
                if action == "PUT" and _direction_exhausted("PUT", code_context):
                    penalty += 18
                    notes.append("PUT em exaustao")
                if action == "PUT" and (rsi_1s >= 74 or rsi_1m >= 72) and rsi_5m >= 62:
                    bonus += 5
                if action == "CALL" and 0 < rsi_1s <= 26 and 0 < rsi_1m <= 38 and 0 < rsi_5m <= 44:
                    bonus += 5

            if techniques.get("trend_pullback", True):
                if action == "CALL" and trend_15m == "up" and change_1s_15 < 0 and 28 <= rsi_1s <= 48:
                    bonus += 5
                    notes.append("pullback em tendencia de alta")
                if action == "PUT" and trend_15m == "down" and change_1s_15 > 0 and 52 <= rsi_1s <= 72:
                    bonus += 5
                    notes.append("pullback em tendencia de baixa")

            if techniques.get("volatility_filter", True):
                if not (0.002 <= vol_1m <= 0.32):
                    penalty += 8
                    notes.append("volatilidade fora do regime bom")

            candidate = {
                **candidate,
                "technical_score": round(float(candidate.get("technical_score") or 0) + bonus - penalty, 2),
                "learning_context": learned,
                "learning_adjustment": {
                    "bonus": round(bonus, 2),
                    "penalty": round(penalty, 2),
                    "notes": notes[:8],
                    "active_techniques": [key for key, value in techniques.items() if value],
                },
            }
            adjusted.append(candidate)
        return sorted(adjusted, key=lambda item: item["technical_score"], reverse=True)

    async def polish_trade_notification(self, config: dict[str, Any], event: str, payload: dict[str, Any], fallback: str) -> str:
        default_notification_model = (
            "qwen/qwen3-next-80b-a3b-instruct (NVIDIA)"
            if "summary" in event
            else "mistralai/mistral-small-4-119b-2603 (NVIDIA)"
        )
        model = (
            (config.get("models") or {}).get("notification")
            or default_notification_model
        )
        system = (
            "Voce formata notificacoes do RED Trader para um grupo de WhatsApp. "
            "Use portugues do Brasil, markdown do WhatsApp e emojis. "
            "Seja bonito, curto, claro e auditavel. Nao prometa lucro e deixe claro que e DEMO quando fizer sentido. "
            "Responda SOMENTE JSON valido no formato {\"text\":\"...\"}."
        )
        user = (
            "Reescreva a notificacao abaixo para WhatsApp, mantendo TODOS os numeros importantes. "
            "Limite: 900 caracteres. Sem conselho financeiro, sem texto extra fora do JSON.\n\n"
            f"EVENTO: {event}\n"
            f"DADOS: {json.dumps(payload, ensure_ascii=False)}\n"
            f"FALLBACK: {fallback}"
        )
        try:
            result = await asyncio.wait_for(
                self.ai.chat_json(model, system, user, temperature=0.25, timeout=10),
                timeout=12,
            )
            text = str(result.get("text") or "").strip()
            if 20 <= len(text) <= 1200:
                return text
        except Exception as exc:
            self.publish("whatsapp:notify_format_fallback", "IA nao formatou notificacao; usando template", {"event": event, "error": repr(exc)})
        return fallback

    async def send_whatsapp_notification(self, text: str, metadata: dict[str, Any]) -> None:
        if not self._notify_enabled():
            return
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                response = await client.post(
                    settings.redia_notify_url,
                    headers={"Authorization": f"Bearer {settings.redia_notify_token}"},
                    json={
                        "to": settings.redia_notify_to,
                        "text": text,
                        "source": "redtrader",
                        "metadata": metadata,
                    },
                )
                response.raise_for_status()
        except Exception as exc:
            self.publish("whatsapp:notify_error", "Falha ao notificar trade no WhatsApp", {"error": repr(exc), "metadata": metadata})

    async def notify_whatsapp_trade_opened(
        self,
        config: dict[str, Any],
        trade_id: int,
        candidate: dict[str, Any],
        decision: dict[str, Any],
        amount: float,
        metadata: dict[str, Any],
    ) -> None:
        order = metadata.get("iqoption_order") or {}
        consensus = decision.get("consensus") or {}
        gale_stage = int(metadata.get("gale_stage") or 0)
        balance = order.get("balance_after_open") or self.wallet_summary().get("equity_brl")
        reason = str(decision.get("reasoning_summary") or "").strip()
        if len(reason) > 220:
            reason = reason[:217].rstrip() + "..."
        payload = {
            "timestamp": self._timestamp(),
            "trade_id": trade_id,
            "symbol": candidate.get("symbol"),
            "direction": str(decision.get("action") or candidate.get("action") or "").upper(),
            "amount": self._money(amount),
            "expiration_min": int(config.get("iqoption_expiration_minutes", 1)),
            "gale_stage": gale_stage,
            "consensus_tier": consensus.get("tier", "-"),
            "stake_source": metadata.get("stake_source") or decision.get("stake_source") or "base",
            "balance_after_open": self._money(balance),
            "ai_reading": reason,
        }
        lines = [
            "🚀 *RED Trader | ENTRADA DEMO*",
            f"🕒 {payload['timestamp']}",
            f"🎯 *#{trade_id}* · *{payload['symbol']}* · *{payload['direction']}*",
            f"💵 Entrada: *{payload['amount']}*",
            f"⏱ Expiração: *{payload['expiration_min']} min* · Gale: *{gale_stage}*",
            f"🧠 Consenso: *{payload['consensus_tier']} votos* · `{payload['stake_source']}`",
            f"🏦 Banca IQ: *{payload['balance_after_open']}*",
        ]
        if reason:
            lines.append(f"📌 _Leitura IA:_ {reason}")
        fallback = "\n".join(lines)
        text = await self.polish_trade_notification(config, "trade_opened", payload, fallback)
        await self.send_whatsapp_notification(text, {"event": "trade_opened", "trade_id": trade_id})

    async def notify_whatsapp_trade_closed(
        self,
        config: dict[str, Any],
        trade: dict[str, Any],
        status: str,
        pnl_brl: float,
        result: dict[str, Any],
    ) -> None:
        metadata = trade.get("metadata") or {}
        balance = result.get("balance_after_close") or self.wallet_summary().get("equity_brl")
        outcome = "WIN" if pnl_brl > 0 else ("LOSS" if pnl_brl < 0 else str(status or "EMPATE").upper())
        icon = "✅" if pnl_brl > 0 else ("❌" if pnl_brl < 0 else "➖")
        payload = {
            "timestamp": self._timestamp(),
            "trade_id": trade.get("id"),
            "symbol": trade.get("symbol"),
            "direction": str(trade.get("side") or "").upper(),
            "amount": self._money(trade.get("position_brl")),
            "result": outcome,
            "raw_status": status,
            "pnl": self._money(pnl_brl),
            "gale_stage": metadata.get("gale_stage", 0),
            "balance_after_close": self._money(balance),
        }
        fallback = "\n".join([
            f"{icon} *RED Trader | FECHAMENTO DEMO*",
            f"🕒 {payload['timestamp']}",
            f"🎯 *#{payload['trade_id']}* · *{payload['symbol']}* · *{payload['direction']}*",
            f"💵 Entrada: *{payload['amount']}* · Gale: *{payload['gale_stage']}*",
            f"{icon} Resultado: *{outcome}* (`{status}`)",
            f"💰 P/L: *{payload['pnl']}*",
            f"🏦 Banca IQ: *{payload['balance_after_close']}*",
        ])
        text = await self.polish_trade_notification(config, "trade_closed", payload, fallback)
        await self.send_whatsapp_notification(text, {"event": "trade_closed", "trade_id": trade.get("id"), "status": status})

    async def handle_exits(self, config: dict[str, Any]) -> None:
        open_trades = self.db.open_trades()
        if not open_trades:
            return
        max_hold_seconds = float(config.get("max_hold_minutes", 60)) * 60
        fee_pct = float(config.get("paper_fee_pct_per_side", 0.1))
        for trade in open_trades:
            metadata = trade.get("metadata") or {}
            snapshot = self.latest_snapshots.get(trade["symbol"]) or {}
            price = ((snapshot.get("features") or {}).get("last_price")) or ((snapshot.get("ticker") or {}).get("last_price"))
            if not price:
                price = float(trade["entry_price"])
            if metadata.get("execution_provider") == "iqoption_demo":
                expiry_seconds = float(metadata.get("expiry_seconds") or 60)
                held = time.time() - float(trade["opened_at"])
                if held < expiry_seconds + 1:
                    continue
                try:
                    result = await self.iqoption.check_result(metadata["iqoption_order_id"])
                    self.set_iqoption_balance(result.get("balance_after_close"))
                    pnl_brl = float(result.get("profit") or 0)
                    pnl_pct = pnl_brl / max(float(trade["position_brl"]), 1) * 100
                    status = result.get("status") or "unknown"
                    self.store_trade_snapshot(int(trade["id"]), trade["symbol"], "close")
                    self.db.close_trade(int(trade["id"]), float(price), pnl_brl, pnl_pct, f"iqoption_demo:{status}")
                    self.update_iq_recovery_after_close(config, trade, pnl_brl, status)
                    self.publish(
                        "trade:closed",
                        f"IQ Option demo fechou {trade['symbol']}: {status}",
                        {"trade_id": trade["id"], "provider": "iqoption_demo", "result": result, "pnl_brl": pnl_brl},
                    )
                    asyncio.create_task(self.notify_whatsapp_trade_closed(config, trade, status, pnl_brl, result))
                except Exception as exc:
                    if "iqoption_result_not_ready" in repr(exc) and held > expiry_seconds + 240:
                        self.db.close_trade(int(trade["id"]), float(price), 0.0, 0.0, "iqoption_demo:unknown_timeout")
                        self.publish(
                            "trade:closed",
                            f"IQ Option demo expirou sem retorno auditavel em {trade['symbol']}",
                            {"trade_id": trade["id"], "provider": "iqoption_demo", "error": repr(exc)},
                        )
                        asyncio.create_task(self.notify_whatsapp_trade_closed(config, trade, "unknown_timeout", 0.0, {"error": repr(exc)}))
                        continue
                    self.publish("trade:error", "Falha ao checar resultado IQ Option demo", {"trade_id": trade["id"], "error": repr(exc)})
                continue
            entry = float(trade["entry_price"])
            direction = -1 if str(trade.get("side") or "").upper() == "PUT" else 1
            change_pct = ((float(price) / entry - 1) * 100) * direction
            held = time.time() - float(trade["opened_at"])
            reason = None
            if change_pct <= -float(trade["stop_loss_pct"]):
                reason = "stop_loss"
            elif change_pct >= float(trade["take_profit_pct"]):
                reason = "take_profit"
            elif held >= max_hold_seconds:
                reason = "max_hold"
            if reason:
                pnl_pct = change_pct - (fee_pct * 2)
                pnl_brl = float(trade["position_brl"]) * pnl_pct / 100
                self.db.close_trade(int(trade["id"]), float(price), pnl_brl, pnl_pct, reason)
                self.publish(
                    "trade:closed",
                    f"Trade {trade['symbol']} encerrado por {reason}",
                    {"trade_id": trade["id"], "exit_price": price, "pnl_brl": pnl_brl, "pnl_pct": pnl_pct},
                )

    async def maybe_enter(self, config: dict[str, Any]) -> None:
        if not config.get("auto_enabled", True):
            return
        if len(self.db.open_trades()) >= int(config.get("max_open_positions", 1)):
            return
        decision_cooldown_seconds = max(1.0, float(config.get("cooldown_minutes", 30)) * 60)
        if time.time() - self.last_decision_at < decision_cooldown_seconds:
            return
        guard = self.risk_guard(config)
        if not guard["ok"]:
            self.publish("risk:blocked", guard["reason"], guard)
            return
        candidates = build_candidates(self.latest_snapshots, config, self.latest_news)
        min_score = float(config.get("min_technical_score", 75))
        now = time.time()
        max_age = float(config.get("max_signal_age_seconds", 4))
        candidates = [
            item for item in candidates
            if item["technical_score"] >= min_score
            and now - float(((item.get("snapshot") or {}).get("ts") or now)) <= max_age
            and float(self.asset_cooldowns.get(item["symbol"], 0) or 0) <= now
        ]
        candidates = [
            item for item in self.apply_iq_learning_to_candidates(candidates, config)
            if item["technical_score"] >= min_score
        ]
        if not candidates:
            if time.time() - self.last_wait_event_at > 300:
                self.last_wait_event_at = time.time()
                self.publish("strategy:wait", "Nenhum candidato passou nos gates tecnicos", {"min_score": min_score})
            return
        candidate = candidates[0]
        candidate["recovery_context"] = self.iq_recovery_state()
        candidate["recent_trade_feedback"] = self.recent_iq_feedback()
        self.publish(
            "strategy:candidate",
            f"Candidato tecnico encontrado em {candidate['symbol']}",
            {"symbol": candidate["symbol"], "technical_score": candidate["technical_score"], "checks": candidate["checks"]},
        )
        self.last_decision_at = time.time()
        decision = await self.run_ai_committee(candidate, config)
        if not decision.get("approved"):
            self.publish("trade:skipped", "Comite vetou a entrada", decision)
            return
        execution_provider = config.get("execution_provider") or "internal_paper"
        side = str(decision.get("action") or candidate.get("action") or "ENTER_LONG").upper()
        position_brl = max(1.0, self.wallet_summary()["equity_brl"] * float(decision["position_pct"]) / 100)
        metadata = {"decision": decision, "candidate": candidate, "execution_provider": execution_provider}
        if execution_provider == "iqoption_demo":
            amount, recovery_state = self.next_iq_amount(config, decision)
            expiration_minutes = max(1, int(config.get("iqoption_expiration_minutes", 1)))
            iq_action = "put" if side == "PUT" else "call"
            try:
                order = await self.iqoption.buy(candidate["symbol"], iq_action, amount, expiration_minutes)
            except Exception as exc:
                error_text = repr(exc)
                cooldown_seconds = 180 if "not available" in error_text or "Cannot purchase" in error_text else 25
                self.asset_cooldowns[candidate["symbol"]] = time.time() + cooldown_seconds
                self.publish(
                    "trade:error",
                    "IQ Option demo recusou a abertura agora",
                    {
                        "symbol": candidate["symbol"],
                        "action": iq_action,
                        "error": error_text,
                        "asset_cooldown_seconds": cooldown_seconds,
                    },
                )
                return
            self.set_iqoption_balance(order.get("balance_after_open"))
            position_brl = amount
            metadata.update({
                "iqoption_order_id": order["order_id"],
                "iqoption_action": iq_action,
                "iqoption_order": order,
                "expiry_seconds": expiration_minutes * 60,
                "gale_stage": int(recovery_state.get("stage") or 0),
                "recovery_loss_total": float(recovery_state.get("loss_total") or 0),
                "base_amount": float(config.get("iqoption_amount", 1)),
                "consensus": decision.get("consensus") or {},
                "stake_source": decision.get("stake_source") or "base",
            })
        trade_id = self.db.open_trade(
            candidate["symbol"],
            side,
            float(candidate["price"]),
            position_brl,
            float(decision["stop_loss_pct"]),
            float(decision["take_profit_pct"]),
            decision.get("reasoning_summary", ""),
            metadata=metadata,
        )
        self.last_trade_at = time.time()
        self.db.set_kv("last_trade_at", self.last_trade_at)
        self.store_trade_snapshot(trade_id, candidate["symbol"], "open")
        self.publish(
            "trade:opened",
            f"{'IQ Option demo' if execution_provider == 'iqoption_demo' else 'Paper'} trade aberto em {candidate['symbol']}",
            {"trade_id": trade_id, "symbol": candidate["symbol"], "side": side, "position_brl": position_brl, "entry_price": candidate["price"], "provider": execution_provider},
        )
        if execution_provider == "iqoption_demo":
            asyncio.create_task(self.notify_whatsapp_trade_opened(config, trade_id, candidate, decision, position_brl, metadata))

    def store_trade_snapshot(self, trade_id: int, symbol: str, phase: str) -> None:
        history = self.db.get_kv("trade_market_history", {}) or {}
        snapshot = self.latest_snapshots.get(symbol) or {}
        item = history.get(str(trade_id), {"trade_id": trade_id, "symbol": symbol, "samples": []})
        item["samples"].append({
            "phase": phase,
            "ts": time.time(),
            "features": snapshot.get("features") or {},
            "frames": snapshot.get("frames") or {},
            "candles_1s": (snapshot.get("candles") or {}).get("1s", [])[-180:],
            "candles_1m": (snapshot.get("candles") or {}).get("1m", [])[-60:],
        })
        item["samples"] = item["samples"][-8:]
        history[str(trade_id)] = item
        if len(history) > 120:
            history = dict(list(history.items())[-120:])
        self.db.set_kv("trade_market_history", history)

    def risk_guard(self, config: dict[str, Any]) -> dict[str, Any]:
        now = time.time()
        recovery = self.iq_recovery_state()
        if recovery.get("last_result") == "loss_reset" and float(recovery.get("blocked_until") or 0) > now:
            return {
                "ok": False,
                "reason": "Cooldown pos-gale 2 perdido",
                "seconds_left": round(float(recovery.get("blocked_until") or 0) - now),
                "blocked_symbol": recovery.get("blocked_symbol"),
                "blocked_side": recovery.get("blocked_side"),
            }
        cooldown_seconds = float(config.get("cooldown_minutes", 30)) * 60
        if now - self.last_trade_at < cooldown_seconds:
            return {
                "ok": False,
                "reason": "Cooldown ativo",
                "seconds_left": round(cooldown_seconds - (now - self.last_trade_at)),
            }
        trades_today = self.db.closed_trades_today()
        if len(trades_today) >= int(config.get("max_trades_per_day", 3)):
            return {"ok": False, "reason": "Limite diario de trades atingido"}
        initial = float(self.wallet_summary()["initial_balance_brl"] or 1)
        daily_pnl_brl = sum(float(item["pnl_brl"]) for item in trades_today if item["status"] == "CLOSED")
        daily_pnl_pct = daily_pnl_brl / initial * 100
        if daily_pnl_pct <= -float(config.get("daily_stop_loss_pct", 5)):
            return {"ok": False, "reason": "Stop diario atingido", "daily_pnl_pct": daily_pnl_pct}
        if daily_pnl_pct >= float(config.get("daily_target_pct", 3)):
            return {"ok": False, "reason": "Meta diaria atingida", "daily_pnl_pct": daily_pnl_pct}
        return {"ok": True}

    def iq_recovery_state(self) -> dict[str, Any]:
        state = self.db.get_kv("iqoption_recovery_state", {}) or {}
        if not state.get("last_symbol") and state.get("last_trade_id"):
            try:
                last_trade_id = int(state.get("last_trade_id"))
                for trade in self.db.list_trades(200):
                    if int(trade.get("id") or 0) == last_trade_id:
                        state = {**state, "last_symbol": trade.get("symbol")}
                        break
            except Exception:
                pass
        return {
            "stage": int(state.get("stage") or 0),
            "loss_total": float(state.get("loss_total") or 0),
            "last_result": state.get("last_result") or "neutral",
            "last_trade_id": state.get("last_trade_id"),
            "last_side": state.get("last_side"),
            "last_symbol": state.get("last_symbol"),
            "blocked_until": float(state.get("blocked_until") or 0),
            "blocked_symbol": state.get("blocked_symbol"),
            "blocked_side": state.get("blocked_side"),
            "updated_at": state.get("updated_at") or 0,
            "note": state.get("note") or "sem recuperacao ativa",
        }

    def set_iq_recovery_state(self, state: dict[str, Any]) -> None:
        state = {**state, "updated_at": time.time()}
        self.db.set_kv("iqoption_recovery_state", state)
        self.publish("gale:state", "Estado de recuperacao IQ atualizado", state)

    def update_iq_recovery_after_close(self, config: dict[str, Any], trade: dict[str, Any], pnl_brl: float, result_status: str) -> None:
        if not config.get("iqoption_gale_enabled", True):
            self.set_iq_recovery_state({
                "stage": 0,
                "loss_total": 0.0,
                "last_result": result_status,
                "last_trade_id": trade["id"],
                "last_side": trade.get("side"),
                "last_symbol": trade.get("symbol"),
                "note": "gale desligado",
            })
            return
        metadata = trade.get("metadata") or {}
        stage = int(metadata.get("gale_stage") or 0)
        max_steps = int(config.get("iqoption_gale_max_steps", 2))
        if pnl_brl > 0:
            self.set_iq_recovery_state({
                "stage": 0,
                "loss_total": 0.0,
                "last_result": "win",
                "last_trade_id": trade["id"],
                "last_side": trade.get("side"),
                "last_symbol": trade.get("symbol"),
                "note": f"win no gale {stage}; mindset resetado",
            })
            return
        if pnl_brl < 0:
            current = self.iq_recovery_state()
            loss_total = float(current.get("loss_total") or 0) + abs(float(pnl_brl))
            if stage >= max_steps:
                self.set_iq_recovery_state({
                    "stage": 0,
                    "loss_total": 0.0,
                    "last_result": "loss_reset",
                    "last_trade_id": trade["id"],
                    "last_side": trade.get("side"),
                    "last_symbol": trade.get("symbol"),
                    "last_loss_total": loss_total,
                    "blocked_until": time.time() + float(config.get("post_gale2_cooldown_minutes", 6)) * 60,
                    "blocked_symbol": trade.get("symbol"),
                    "blocked_side": trade.get("side"),
                    "note": f"loss no gale {stage}; limite atingido, resetar mindset",
                })
                return
            self.set_iq_recovery_state({
                "stage": stage + 1,
                "loss_total": loss_total,
                "last_result": "loss",
                "last_trade_id": trade["id"],
                "last_side": trade.get("side"),
                "last_symbol": trade.get("symbol"),
                "note": f"loss detectado; proxima operacao e gale {stage + 1} com reanalise completa",
            })
            return
        self.set_iq_recovery_state({
            "stage": 0,
            "loss_total": 0.0,
            "last_result": "equal",
            "last_trade_id": trade["id"],
            "last_side": trade.get("side"),
            "last_symbol": trade.get("symbol"),
            "note": "empate; sem recuperacao ativa",
        })

    def next_iq_amount(self, config: dict[str, Any], decision: dict[str, Any] | None = None) -> tuple[float, dict[str, Any]]:
        state = self.iq_recovery_state()
        base = max(1.0, float(config.get("iqoption_amount", 1)))
        preferred_base = max(base, _num((decision or {}).get("stake_amount")) or base)
        if not config.get("iqoption_gale_enabled", True):
            return preferred_base, state
        stage = max(0, int(state.get("stage") or 0))
        if stage <= 0:
            return preferred_base, state
        payout = max(0.1, float(config.get("iqoption_gale_payout_pct", 85)) / 100)
        loss_total = max(0.0, float(state.get("loss_total") or 0))
        multiplier = max(1.0, float(config.get("iqoption_gale_multiplier", 2.35)))
        max_amount = max(base, float(config.get("iqoption_gale_max_amount", 100)))
        target_profit = preferred_base
        recovery_amount = (loss_total + target_profit) / payout
        multiplier_amount = preferred_base * (multiplier ** stage)
        amount = min(max(recovery_amount, multiplier_amount, preferred_base), max_amount)
        return round(amount, 2), state

    def recent_iq_feedback(self, limit: int = 4) -> list[dict[str, Any]]:
        feedback = []
        for trade in self.db.list_trades(80):
            metadata = trade.get("metadata") or {}
            if metadata.get("execution_provider") != "iqoption_demo":
                continue
            feedback.append({
                "id": trade.get("id"),
                "side": trade.get("side"),
                "symbol": trade.get("symbol"),
                "status": trade.get("status"),
                "gale_stage": metadata.get("gale_stage", 0),
                "amount": trade.get("position_brl"),
                "pnl": trade.get("pnl_brl"),
                "exit_reason": trade.get("exit_reason"),
                "opened_at": trade.get("opened_at"),
                "reasoning": str(trade.get("entry_reason") or "")[:240],
            })
            if len(feedback) >= limit:
                break
        return feedback

    async def run_ai_committee(self, candidate: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        system, prompt = build_decision_prompt(candidate, self.latest_news, config)
        models = config.get("models") or {}
        if candidate.get("trade_type") == "binary_options":
            return await self.run_binary_committee(candidate, config, system, prompt, models)
        fast_model = models.get("fast_filter")
        decision_model = models.get("decision")
        critic_model = models.get("critic")
        fast_task = (
            asyncio.create_task(self.safe_ai_call("fast_filter", fast_model, candidate["symbol"], system, prompt, timeout=18))
            if fast_model else None
        )
        final_task = asyncio.create_task(self.safe_ai_call("decision", decision_model, candidate["symbol"], system, prompt, timeout=42))
        final = await final_task
        fast = await fast_task if fast_task else {}
        if not final.get("ok"):
            return {"approved": False, "reason": "Modelo decisor falhou", "fast": fast, "final": final}
        response = final["response"]
        final_latency = int(response.get("_latency_ms") or 0)
        max_decision_latency = int(config.get("max_decision_latency_ms", 8000) or 8000)
        if final_latency and final_latency > max_decision_latency:
            return {
                "approved": False,
                "reason": f"Decisao ficou velha ({final_latency}ms)",
                "fast": fast,
                "final": final,
                "latency_ms": final_latency,
                "max_latency_ms": max_decision_latency,
            }
        confidence = normalize_confidence(response.get("confidence"))
        decision = str(response.get("decision", "")).upper()
        risk_reward = _num(response.get("risk_reward"))
        position_pct = min(float(config.get("position_pct", 20)), _num(response.get("position_pct")) or float(config.get("position_pct", 20)))
        stop_loss_pct = _num(response.get("stop_loss_pct")) or candidate["stop_loss_pct"]
        take_profit_pct = _num(response.get("take_profit_pct")) or candidate["take_profit_pct"]
        allowed_decision = str(candidate.get("action") or "ENTER_LONG").upper()
        is_binary = candidate.get("trade_type") == "binary_options"
        direction_ok = decision in {"CALL", "PUT"} if is_binary else decision == allowed_decision
        final_ok = (
            direction_ok
            and confidence >= float(config.get("min_ai_confidence", 72))
            and risk_reward >= float(config.get("min_risk_reward", 1.3))
        )
        if not final_ok:
            return {
                "approved": False,
                "reason": "Decisor nao aprovou entrada",
                "decision": response,
                "fast": fast,
                "confidence": confidence,
            }
        critic_system, critic_prompt = build_critic_prompt(candidate, response, self.latest_news, config)
        critic = await self.safe_ai_call("critic", critic_model, candidate["symbol"], critic_system, critic_prompt, timeout=42)
        critic_response = critic.get("response") or {}
        if critic.get("ok") and (critic_response.get("veto") is True or critic_response.get("risk_level") == "red"):
            return {"approved": False, "reason": "Critico vetou a entrada", "decision": response, "critic": critic_response, "fast": fast}
        consensus = {
            "enabled": False,
            "tier": 1,
            "stake_amount": max(1.0, float(config.get("iqoption_amount", 1))),
            "stake_source": "base",
            "votes": [],
        }
        if is_binary:
            fast_response = fast.get("response") or {}
            final_direction = _binary_direction(decision)
            fast_direction = _binary_direction(fast_response.get("decision"))
            critic_direction = _binary_direction(critic_response.get("preferred_decision") or critic_response.get("decision"))
            recovery = candidate.get("recovery_context") or {}
            recovery_stage = int(recovery.get("stage") or 0)
            core_votes = [
                _vote("fast_filter", fast_model, fast_direction, fast_response, fast),
                _vote("decision", decision_model, final_direction, response, final),
                _vote("critic", critic_model, critic_direction, critic_response, critic),
            ]
            core_agreement = sum(1 for item in core_votes if item.get("direction") == final_direction)
            consensus_config = config.get("iqoption_consensus_stakes") or {}
            min_votes = int(consensus_config.get("min_votes", 2))
            recovery_min_votes = int(consensus_config.get("recovery_min_votes", 3))
            consensus = {
                "enabled": bool(consensus_config.get("enabled", True)),
                "direction": final_direction,
                "tier": core_agreement,
                "core_agreement": core_agreement,
                "recovery_stage": recovery_stage,
                "votes": core_votes,
                "stake_amount": max(1.0, float(config.get("iqoption_amount", 1))),
                "stake_source": "base",
            }
            if core_agreement < min_votes:
                return {
                    "approved": False,
                    "reason": "Consenso minimo nao confirmado",
                    "decision": response,
                    "critic": critic_response,
                    "fast": fast_response,
                    "consensus": consensus,
                }
            if fast_direction and fast_direction != final_direction and critic_direction and critic_direction != final_direction:
                return {
                    "approved": False,
                    "reason": "Trio da morte divergente",
                    "decision": response,
                    "critic": critic_response,
                    "fast": fast_response,
                    "consensus": consensus,
                }
            extra_votes: list[dict[str, Any]] = []
            if core_agreement >= 3:
                extra_votes = await self.extra_premium_votes(models, candidate, system, prompt, final_direction)
                consensus["votes"] = core_votes + extra_votes
            tier = core_agreement
            if core_agreement >= 3:
                for item in extra_votes:
                    if item.get("direction") == final_direction:
                        tier += 1
                    else:
                        break
            code_context = candidate.get("code_context") or {}
            last_side = _binary_direction(recovery.get("last_side"))
            same_symbol_recovery = recovery_stage > 0 and str(recovery.get("last_symbol") or "") == str(candidate["symbol"])
            same_side_recovery = same_symbol_recovery and last_side == final_direction
            required_recovery_votes = recovery_min_votes if same_symbol_recovery else min(recovery_min_votes, min_votes)
            if recovery_stage > 0 and core_agreement < required_recovery_votes:
                consensus["required_recovery_votes"] = required_recovery_votes
                consensus["same_symbol_recovery"] = same_symbol_recovery
                return {
                    "approved": False,
                    "reason": f"Trio da morte exige {required_recovery_votes} votos no gale",
                    "decision": response,
                    "critic": critic_response,
                    "fast": fast_response,
                    "consensus": consensus,
                }
            same_side_loss_streak = _same_side_loss_streak(
                candidate.get("recent_trade_feedback") or [],
                candidate["symbol"],
                final_direction,
            )
            direction_exhausted = _direction_exhausted(final_direction, code_context)
            if same_side_recovery and direction_exhausted and tier < 4:
                consensus.update({
                    "tier": tier,
                    "same_symbol_recovery": same_symbol_recovery,
                    "same_side_recovery": True,
                    "same_side_loss_streak": same_side_loss_streak,
                    "code_context": code_context,
                })
                return {
                    "approved": False,
                    "reason": "Gale na mesma direcao em zona de exaustao; premium nao confirmou",
                    "decision": response,
                    "critic": critic_response,
                    "fast": fast_response,
                    "consensus": consensus,
                    "code_context": code_context,
                }
            if same_side_loss_streak >= 2 and tier < 4:
                consensus.update({
                    "tier": tier,
                    "same_symbol_recovery": same_symbol_recovery,
                    "same_side_recovery": same_side_recovery,
                    "same_side_loss_streak": same_side_loss_streak,
                    "code_context": code_context,
                })
                return {
                    "approved": False,
                    "reason": "Sequencia recente perdeu na mesma direcao; exige voto premium",
                    "decision": response,
                    "critic": critic_response,
                    "fast": fast_response,
                    "consensus": consensus,
                    "code_context": code_context,
                }
            stake_amount = self.consensus_stake_amount(config, tier)
            consensus.update({
                "tier": tier,
                "stake_amount": stake_amount,
                "stake_source": f"consensus_{tier}_votes",
                "same_symbol_recovery": same_symbol_recovery,
                "same_side_recovery": same_side_recovery,
                "same_side_loss_streak": same_side_loss_streak,
                "code_context": code_context,
            })
        return {
            "approved": True,
            "symbol": candidate["symbol"],
            "action": decision if is_binary else allowed_decision,
            "confidence": confidence,
            "position_pct": position_pct,
            "stop_loss_pct": stop_loss_pct,
            "take_profit_pct": take_profit_pct,
            "risk_reward": risk_reward,
            "reasoning_summary": response.get("reasoning_summary", ""),
            "decision": response,
            "critic": critic_response,
            "fast": fast.get("response", {}),
            "consensus": consensus,
            "stake_amount": consensus.get("stake_amount") if is_binary else None,
            "stake_source": consensus.get("stake_source") if is_binary else "position_pct",
            "trio": {
                "fast": _binary_direction((fast.get("response") or {}).get("decision")) if is_binary else None,
                "final": _binary_direction(decision) if is_binary else None,
                "critic": _binary_direction(critic_response.get("preferred_decision") or critic_response.get("decision")) if is_binary else None,
            },
        }

    async def run_binary_committee(
        self,
        candidate: dict[str, Any],
        config: dict[str, Any],
        system: str,
        prompt: str,
        models: dict[str, Any],
    ) -> dict[str, Any]:
        max_decision_latency = int(config.get("max_decision_latency_ms", 8000) or 8000)
        call_timeout = max(3.0, min(8.0, max_decision_latency / 1000))
        roles = ["fast_filter", "decision", "critic", "premium_4", "premium_5"]
        gate_profile = _iq_gate_profile(config)
        cycle_id = self.begin_committee_cycle(candidate, models, gate_profile)
        tasks: list[tuple[str, str, asyncio.Task]] = []
        seen: set[str] = set()
        for role in roles:
            model = str(models.get(role) or "").strip()
            if not model or model in seen:
                continue
            seen.add(model)
            tasks.append(
                (
                    role,
                    model,
                    asyncio.create_task(
                        self.bounded_ai_call(
                            role,
                            model,
                            candidate["symbol"],
                            system,
                            prompt,
                            timeout=call_timeout,
                            committee_id=cycle_id,
                        )
                    ),
                )
            )
        if not tasks:
            reason = "Nenhum modelo configurado para IQ demo"
            self.finalize_committee_cycle(cycle_id, approved=False, reason=reason)
            return {"approved": False, "reason": reason}

        results: list[tuple[str, str, dict[str, Any]]] = []
        task_meta = {task: (role, model) for role, model, task in tasks}
        pending = set(task_meta)

        def _partial_valid_counts(items: list[tuple[str, str, dict[str, Any]]]) -> dict[str, int]:
            counts = {"CALL": 0, "PUT": 0}
            for _role, _model, result in items:
                response = result.get("response") or {}
                direction = _binary_direction(response.get("decision") or response.get("preferred_decision"))
                rr = _num(response.get("risk_reward")) or float(candidate.get("risk_reward") or 0)
                valid = (
                    bool(result.get("ok"))
                    and direction in {"CALL", "PUT"}
                    and normalize_confidence(response.get("confidence")) >= float(config.get("min_ai_confidence", 72))
                    and rr >= float(config.get("min_risk_reward", 1.3))
                )
                if valid and direction:
                    counts[direction] += 1
            return counts

        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                role, model = task_meta[task]
                try:
                    result = task.result()
                except asyncio.CancelledError:
                    continue
                results.append((role, model, result))

            partial_counts = _partial_valid_counts(results)
            remaining_slots = len(pending)
            if max(partial_counts["CALL"] + remaining_slots, partial_counts["PUT"] + remaining_slots) < int(gate_profile["min_votes"]):
                self.publish(
                    "committee:abort",
                    "Comite abortado cedo: consenso minimo ficou impossivel",
                    {
                        "symbol": candidate["symbol"],
                        "partial_counts": partial_counts,
                        "remaining_slots": remaining_slots,
                        "min_votes": int(gate_profile["min_votes"]),
                    },
                )
                for task in list(pending):
                    task.cancel()
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
                pending.clear()
                break

        min_confidence = float(config.get("min_ai_confidence", 72))
        min_rr = float(config.get("min_risk_reward", 1.3))
        votes: list[dict[str, Any]] = []
        valid_votes: list[dict[str, Any]] = []
        for role, model, result in results:
            response = result.get("response") or {}
            direction = _binary_direction(response.get("decision") or response.get("preferred_decision"))
            vote = _vote(role, model, direction, response, result)
            rr = _num(response.get("risk_reward")) or float(candidate.get("risk_reward") or 0)
            vote["risk_reward"] = rr
            vote["valid"] = (
                bool(result.get("ok"))
                and direction in {"CALL", "PUT"}
                and normalize_confidence(response.get("confidence")) >= min_confidence
                and rr >= min_rr
            )
            votes.append(vote)
            if vote["valid"]:
                valid_votes.append({**vote, "response": response})

        counts = {
            "CALL": sum(1 for item in valid_votes if item.get("direction") == "CALL"),
            "PUT": sum(1 for item in valid_votes if item.get("direction") == "PUT"),
        }
        invalid_vote_count = max(0, len(votes) - len(valid_votes))
        vote_by_role = {str(item.get("role") or ""): item for item in votes}
        role_direction_map = {
            role: _binary_direction((vote_by_role.get(role) or {}).get("direction"))
            for role in roles
        }
        role_valid_map = {
            role: bool((vote_by_role.get(role) or {}).get("valid"))
            for role in roles
        }
        if counts["CALL"] == counts["PUT"]:
            final_direction = None
        else:
            final_direction = "CALL" if counts["CALL"] > counts["PUT"] else "PUT"
        tier = counts.get(final_direction or "", 0)
        recovery = candidate.get("recovery_context") or {}
        recovery_stage = int(recovery.get("stage") or 0)
        consensus_config = config.get("iqoption_consensus_stakes") or {}
        min_votes = int(gate_profile["min_votes"])
        code_context = candidate.get("code_context") or {}
        code_preferred = code_context.get("preferred_direction")
        techniques = config.get("iqoption_techniques") or {}
        learning_context = candidate.get("learning_context") or {}
        learning_adjustment = candidate.get("learning_adjustment") or {}
        same_symbol_recovery = recovery_stage > 0 and str(recovery.get("last_symbol") or "") == str(candidate["symbol"])
        same_side_recovery = same_symbol_recovery and _binary_direction(recovery.get("last_side")) == final_direction
        repeated_side_recovery = recovery_stage > 0 and _binary_direction(recovery.get("last_side")) == final_direction
        same_side_loss_streak = _same_side_loss_streak(
            candidate.get("recent_trade_feedback") or [],
            candidate["symbol"],
            final_direction,
        )
        direction_exhausted = _direction_exhausted(final_direction, code_context)
        core_roles = ("fast_filter", "decision")
        guard_roles = ("critic", "premium_4")
        specialist_role = "premium_5"
        core_confirm_count = sum(
            1 for role in core_roles
            if role_valid_map.get(role) and role_direction_map.get(role) == final_direction
        )
        guard_confirm_count = sum(
            1 for role in guard_roles
            if role_valid_map.get(role) and role_direction_map.get(role) == final_direction
        )
        guard_wait_count = sum(
            1 for role in guard_roles
            if not role_valid_map.get(role) or role_direction_map.get(role) not in {"CALL", "PUT"}
        )
        lead_guard_direction = role_direction_map.get("critic")
        lead_guard_confirm = bool(role_valid_map.get("critic")) and lead_guard_direction == final_direction
        specialist_direction = role_direction_map.get(specialist_role)
        specialist_raw_decision = str((vote_by_role.get(specialist_role) or {}).get("raw_decision") or "")
        specialist_opposes = (
            bool(role_valid_map.get(specialist_role))
            and specialist_direction in {"CALL", "PUT"}
            and specialist_direction != final_direction
        )
        specialist_cautions = (
            bool(vote_by_role.get(specialist_role))
            and not role_valid_map.get(specialist_role)
            and _is_caution_signal(specialist_raw_decision)
        )
        consensus = {
            "enabled": bool(consensus_config.get("enabled", True)),
            "direction": final_direction,
            "tier": tier,
            "core_agreement": tier,
            "recovery_stage": recovery_stage,
            "votes": votes,
            "counts": counts,
            "invalid_vote_count": invalid_vote_count,
            "min_votes": min_votes,
            "profile_gate": gate_profile,
            "stake_amount": max(1.0, float(config.get("iqoption_amount", 1))),
            "stake_source": "base",
            "same_symbol_recovery": same_symbol_recovery,
            "same_side_recovery": same_side_recovery,
            "repeated_side_recovery": repeated_side_recovery,
            "same_side_loss_streak": same_side_loss_streak,
            "code_context": code_context,
            "learning_adjustment": learning_adjustment,
            "role_directions": role_direction_map,
            "role_valid_map": role_valid_map,
            "core_confirm_count": core_confirm_count,
            "guard_confirm_count": guard_confirm_count,
            "guard_wait_count": guard_wait_count,
            "lead_guard_confirm": lead_guard_confirm,
            "specialist_direction": specialist_direction,
            "specialist_raw_decision": specialist_raw_decision,
            "specialist_opposes": specialist_opposes,
            "specialist_cautions": specialist_cautions,
        }
        if not final_direction:
            reason = "Comite empatou ou nao confirmou direcao"
            self.finalize_committee_cycle(cycle_id, approved=False, reason=reason, consensus=consensus)
            return {
                "approved": False,
                "reason": reason,
                "consensus": consensus,
                "decision": {},
                "critic": {},
                "fast": {},
            }
        if tier < min_votes:
            reason = "Consenso minimo nao confirmado"
            self.finalize_committee_cycle(cycle_id, approved=False, reason=reason, consensus=consensus)
            return {
                "approved": False,
                "reason": reason,
                "consensus": consensus,
                "decision": {},
                "critic": {},
                "fast": {},
            }
        if (
            techniques.get("adaptive_recovery", True)
            and invalid_vote_count >= int(gate_profile["invalid_block_count"])
            and tier < int(gate_profile["invalid_block_tier"])
        ):
            reason = f"Aprendizado bloqueou no perfil {gate_profile['key']}: muitos votos nulos exigem {gate_profile['invalid_block_tier']}/5"
            self.finalize_committee_cycle(cycle_id, approved=False, reason=reason, consensus=consensus)
            return {
                "approved": False,
                "reason": reason,
                "consensus": consensus,
                "decision": {},
                "critic": {},
                "fast": {},
            }
        required_recovery_votes = min_votes
        if recovery_stage > 0:
            required_recovery_votes = int(gate_profile["recovery_same"] if same_symbol_recovery else gate_profile["recovery_cross"])
        if recovery_stage > 0 and techniques.get("adaptive_recovery", True):
            active_avoids = learning_context.get("active_avoid_patterns") or []
            relevant_avoids = [
                item for item in active_avoids
                if str(item.get("direction") or "*").upper() in {"*", final_direction}
            ]
            max_learned_severity = max([_num(item.get("severity")) for item in relevant_avoids] or [0.0])
            learning_penalty = _num(learning_adjustment.get("penalty"))
            consensus["adaptive_recovery"] = {
                "active_avoid_patterns": relevant_avoids[:4],
                "max_severity": round(max_learned_severity, 2),
                "learning_penalty": round(learning_penalty, 2),
            }
            if max_learned_severity >= 0.75 or learning_penalty >= 22:
                required_recovery_votes = max(required_recovery_votes, int(gate_profile["learned_high_min"]))
            elif max_learned_severity >= 0.45 or learning_penalty >= 14:
                required_recovery_votes = max(required_recovery_votes, int(gate_profile["learned_mid_min"]))
        consensus["required_recovery_votes"] = required_recovery_votes
        if recovery_stage > 0 and tier < required_recovery_votes:
            reason = f"Recuperacao exige pelo menos {required_recovery_votes} votos validos"
            self.finalize_committee_cycle(cycle_id, approved=False, reason=reason, consensus=consensus)
            return {
                "approved": False,
                "reason": reason,
                "consensus": consensus,
                "decision": {},
                "critic": {},
                "fast": {},
            }
        specialist_guard_min = int(gate_profile.get("recovery_specialist_guard_min", 1))
        if (
            recovery_stage > 0
            and core_confirm_count >= 2
            and (specialist_opposes or specialist_cautions)
            and guard_confirm_count < specialist_guard_min
        ):
            reason = (
                "Especialista sinalizou cautela contra o nucleo sem confirmacao dos guardioes"
            )
            self.finalize_committee_cycle(cycle_id, approved=False, reason=reason, consensus=consensus)
            return {
                "approved": False,
                "reason": reason,
                "consensus": consensus,
                "decision": {},
                "critic": {},
                "fast": {},
            }
        if recovery_stage > 0 and repeated_side_recovery and (specialist_opposes or specialist_cautions) and not lead_guard_confirm:
            reason = (
                "Recuperacao repetindo a mesma direcao foi bloqueada: especialista pediu cautela e o critico nao confirmou"
            )
            self.finalize_committee_cycle(cycle_id, approved=False, reason=reason, consensus=consensus)
            return {
                "approved": False,
                "reason": reason,
                "consensus": consensus,
                "decision": {},
                "critic": {},
                "fast": {},
            }
        same_side_recovery_min = int(gate_profile["same_side_recovery_min"])
        if recovery_stage > 0 and same_side_recovery and tier < same_side_recovery_min:
            reason = f"Gale repetindo direcao do loss exige {same_side_recovery_min}/5 no perfil {gate_profile['key']}"
            self.finalize_committee_cycle(cycle_id, approved=False, reason=reason, consensus=consensus)
            return {
                "approved": False,
                "reason": reason,
                "consensus": consensus,
                "decision": {},
                "critic": {},
                "fast": {},
            }
        exhaustion_min = int(gate_profile["exhaustion_min"])
        if direction_exhausted and tier < exhaustion_min:
            reason = f"Zona de exaustao exige pelo menos {exhaustion_min}/5 no perfil {gate_profile['key']}"
            self.finalize_committee_cycle(cycle_id, approved=False, reason=reason, consensus=consensus)
            return {
                "approved": False,
                "reason": reason,
                "consensus": consensus,
                "decision": {},
                "critic": {},
                "fast": {},
            }
        gale2_same_min = int(gate_profile["gale2_same_min"])
        if recovery_stage >= 2 and same_side_recovery and tier < gale2_same_min:
            reason = f"Gale 2 na mesma direcao exige {gale2_same_min}/5 no perfil {gate_profile['key']}"
            self.finalize_committee_cycle(cycle_id, approved=False, reason=reason, consensus=consensus)
            return {
                "approved": False,
                "reason": reason,
                "consensus": consensus,
                "decision": {},
                "critic": {},
                "fast": {},
            }
        gale2_guardless_invalid_max = int(gate_profile.get("gale2_guardless_invalid_max", 1))
        if (
            recovery_stage >= 2
            and guard_confirm_count <= 0
            and invalid_vote_count > gale2_guardless_invalid_max
        ):
            reason = (
                "Gale 2 sem guardiao confirmado e com votos nulos demais foi bloqueado"
            )
            self.finalize_committee_cycle(cycle_id, approved=False, reason=reason, consensus=consensus)
            return {
                "approved": False,
                "reason": reason,
                "consensus": consensus,
                "decision": {},
                "critic": {},
                "fast": {},
            }
        same_side_exhausted_min = int(gate_profile["same_side_exhausted_min"])
        if same_side_recovery and direction_exhausted and tier < same_side_exhausted_min:
            reason = f"Gale na mesma direcao em zona de exaustao exige {same_side_exhausted_min}/5"
            self.finalize_committee_cycle(cycle_id, approved=False, reason=reason, consensus=consensus)
            return {
                "approved": False,
                "reason": reason,
                "consensus": consensus,
                "decision": {},
                "critic": {},
                "fast": {},
            }
        same_side_loss_min = int(gate_profile["same_side_loss_min"])
        if same_side_loss_streak >= 2 and tier < same_side_loss_min:
            reason = f"Sequencia recente perdeu na mesma direcao; exige {same_side_loss_min}/5"
            self.finalize_committee_cycle(cycle_id, approved=False, reason=reason, consensus=consensus)
            return {
                "approved": False,
                "reason": reason,
                "consensus": consensus,
                "decision": {},
                "critic": {},
                "fast": {},
            }
        code_wait_min = int(gate_profile["code_wait_min"])
        if code_preferred == "WAIT" and tier < code_wait_min:
            reason = f"Codigo quantitativo pediu WAIT; perfil {gate_profile['key']} exige {code_wait_min}/5 para contrariar"
            self.finalize_committee_cycle(cycle_id, approved=False, reason=reason, consensus=consensus)
            return {
                "approved": False,
                "reason": reason,
                "consensus": consensus,
                "decision": {},
                "critic": {},
                "fast": {},
            }
        code_conflict_min = int(gate_profile["code_conflict_min"])
        if code_preferred in {"CALL", "PUT"} and code_preferred != final_direction and tier < code_conflict_min:
            reason = f"Modelos contrariaram o codigo; perfil {gate_profile['key']} exige {code_conflict_min}/5"
            self.finalize_committee_cycle(cycle_id, approved=False, reason=reason, consensus=consensus)
            return {
                "approved": False,
                "reason": reason,
                "consensus": consensus,
                "decision": {},
                "critic": {},
                "fast": {},
            }

        selected = max(
            [item for item in valid_votes if item.get("direction") == final_direction],
            key=lambda item: (item.get("confidence") or 0, -(item.get("latency_ms") or 999999)),
        )
        response = selected.get("response") or {}
        stake_amount = self.consensus_stake_amount(config, tier)
        consensus.update({
            "stake_amount": stake_amount,
            "stake_source": f"consensus_{tier}_votes",
        })
        role_map = {role: result.get("response") or {} for role, _model, result in results}
        confidence = normalize_confidence(response.get("confidence"))
        self.finalize_committee_cycle(
            cycle_id,
            approved=True,
            reason=response.get("reasoning_summary", "") or "Consenso aprovado",
            consensus=consensus,
            action=final_direction,
        )
        return {
            "approved": True,
            "symbol": candidate["symbol"],
            "action": final_direction,
            "confidence": confidence,
            "position_pct": min(float(config.get("position_pct", 20)), _num(response.get("position_pct")) or float(config.get("position_pct", 20))),
            "stop_loss_pct": _num(response.get("stop_loss_pct")) or candidate["stop_loss_pct"],
            "take_profit_pct": _num(response.get("take_profit_pct")) or candidate["take_profit_pct"],
            "risk_reward": _num(response.get("risk_reward")) or candidate["risk_reward"],
            "reasoning_summary": response.get("reasoning_summary", ""),
            "decision": response,
            "critic": role_map.get("critic", {}),
            "fast": role_map.get("fast_filter", {}),
            "consensus": consensus,
            "stake_amount": stake_amount,
            "stake_source": consensus.get("stake_source"),
            "trio": {
                "fast": _binary_direction(role_map.get("fast_filter", {}).get("decision")),
                "final": _binary_direction(role_map.get("decision", {}).get("decision")),
                "critic": _binary_direction(role_map.get("critic", {}).get("decision") or role_map.get("critic", {}).get("preferred_decision")),
            },
        }

    async def bounded_ai_call(
        self,
        role: str,
        model: str,
        symbol: str,
        system: str,
        prompt: str,
        timeout: float,
        committee_id: int | None = None,
    ) -> dict[str, Any]:
        chain = self.model_fallback_chain(role, model)
        fallback_extra = max(0.0, (len(chain) - 1) * 4.5)
        overall_timeout = timeout + fallback_extra + 0.75
        try:
            return await asyncio.wait_for(
                self.safe_ai_call(
                    role,
                    model,
                    symbol,
                    system,
                    prompt,
                    timeout=max(3, int(timeout)),
                    committee_id=committee_id,
                ),
                timeout=overall_timeout,
            )
        except asyncio.TimeoutError:
            if committee_id is not None:
                self.update_committee_role(
                    committee_id,
                    role,
                    "timeout",
                    symbol=symbol,
                    decision="WAIT",
                    summary=f"Sem resposta util em {timeout:.2f}s.",
                    error=f"timeout>{timeout:.2f}s",
                    latency_ms=int(timeout * 1000),
                )
            self.publish(
                "ai:error",
                f"{role} excedeu limite de latencia",
                {"role": role, "model": model, "symbol": symbol, "timeout_seconds": timeout},
            )
            return {"ok": False, "error": f"timeout>{timeout:.2f}s"}

    @staticmethod
    def model_fallback_chain(role: str, model: str | None) -> list[str]:
        primary = str(model or "").strip()
        if not primary:
            return []
        chain = [primary]
        if role == "fast_filter" and primary == "nemotron-3-super":
            chain.append("gemma3:4b")
        if role == "fast_filter" and primary == "meta/llama-4-maverick-17b-128e-instruct (NVIDIA)":
            chain.append("gemma3:4b")
        if role == "decision" and primary == "gemma3:4b":
            chain.append("qwen/qwen3-next-80b-a3b-instruct (NVIDIA)")
        if role == "critic" and primary == "ministral-3:3b":
            chain.append("gemma3:4b")
        if role == "critic" and primary == "mistralai/mistral-small-4-119b-2603 (NVIDIA)":
            chain.append("ministral-3:8b")
        if role == "premium_4" and primary == "ministral-3:8b":
            chain.append("qwen3-coder-next")
        if role == "premium_5" and primary == "ministral-3:3b":
            chain.append("qwen3-coder-next")
        if role == "decision" and primary == "qwen/qwen3-next-80b-a3b-instruct (NVIDIA)":
            chain.append("meta/llama-4-maverick-17b-128e-instruct (NVIDIA)")
        elif primary == "qwen/qwen3-next-80b-a3b-instruct (NVIDIA)":
            chain.append("qwen3-coder-next")
        elif primary == "qwen3-coder-next":
            chain.append("qwen/qwen3-next-80b-a3b-instruct (NVIDIA)")
        deduped: list[str] = []
        for item in chain:
            if item and item not in deduped:
                deduped.append(item)
        return deduped

    @staticmethod
    def model_chat_options(role: str, model: str) -> dict[str, Any]:
        lowered = str(model or "").lower()
        options: dict[str, Any] = {
            "temperature": 0.03,
            "num_ctx": 2560,
            "num_predict": 260,
        }
        if role == "decision":
            options["num_predict"] = 280
        elif role == "premium_5":
            options["num_predict"] = 300
        elif role == "premium_4":
            options["num_predict"] = 280
        if "qwen" in lowered:
            options["num_ctx"] = 3072
            options["num_predict"] = max(int(options["num_predict"]), 300)
        if "gemma3:4b" in lowered:
            options["num_ctx"] = 2048
            options["num_predict"] = min(int(options["num_predict"]), 240)
        return options

    async def extra_premium_votes(
        self,
        models: dict[str, Any],
        candidate: dict[str, Any],
        system: str,
        prompt: str,
        final_direction: str | None,
    ) -> list[dict[str, Any]]:
        votes: list[dict[str, Any]] = []
        seen = {
            str(models.get("fast_filter") or ""),
            str(models.get("decision") or ""),
            str(models.get("critic") or ""),
        }
        tasks: list[tuple[str, str, asyncio.Task]] = []
        for role in ["premium_4", "premium_5"]:
            model = str(models.get(role) or "").strip()
            if not model or model in seen:
                continue
            seen.add(model)
            tasks.append((role, model, asyncio.create_task(self.safe_ai_call(role, model, candidate["symbol"], system, prompt, timeout=32))))
        for role, model, task in tasks:
            result = await task
            response = result.get("response") or {}
            votes.append(_vote(role, model, _binary_direction(response.get("decision")), response, result))
            if final_direction and votes[-1].get("direction") != final_direction:
                # Premium tiers are chained: if the fourth voter fails, we do not wait
                # for a higher tier to compensate the disagreement.
                continue
        return votes

    def consensus_stake_amount(self, config: dict[str, Any], tier: int) -> float:
        base = max(1.0, float(config.get("iqoption_amount", 1)))
        consensus_config = config.get("iqoption_consensus_stakes") or {}
        if not consensus_config.get("enabled", True):
            return base
        mode = str(consensus_config.get("mode") or config.get("iqoption_stake_mode") or "fixed").lower()
        if mode in {"balance_pct", "percent", "pct", "percentage"}:
            pct_tiers = consensus_config.get("pct_tiers") or {}
            pct_value = None
            for key in [str(int(tier)), "2"]:
                if key in pct_tiers:
                    pct_value = _num(pct_tiers[key])
                    break
            if pct_value and pct_value > 0:
                equity = max(1.0, float(self.wallet_summary().get("equity_brl") or base))
                return round(max(1.0, equity * pct_value / 100), 2)
            return base
        tiers = consensus_config.get("tiers") or {}
        for key in [str(int(tier)), "2"]:
            if key in tiers:
                return round(max(1.0, float(tiers[key])), 2)
        return base

    async def safe_ai_call(
        self,
        role: str,
        model: str | None,
        symbol: str,
        system: str,
        prompt: str,
        timeout: int,
        committee_id: int | None = None,
    ) -> dict[str, Any]:
        if not model:
            return {"ok": False, "error": "modelo nao configurado"}
        chain = self.model_fallback_chain(role, model)
        errors: list[dict[str, Any]] = []
        total = len(chain)
        for index, current_model in enumerate(chain, start=1):
            try:
                attempt_timeout = float(timeout)
                if total > 1:
                    attempt_timeout = min(attempt_timeout, 6.0 if index == 1 else 6.5)
                chat_options = self.model_chat_options(role, current_model)
                if committee_id is not None:
                    self.update_committee_role(
                        committee_id,
                        role,
                        "running",
                        model=current_model,
                        symbol=symbol,
                        summary="Analisando o par agora." if index == 1 else f"Fallback {index}/{total} em andamento.",
                    )
                self.publish(
                    "ai:start",
                    f"{role} analisando {symbol}",
                    {
                        "role": role,
                        "model": current_model,
                        "symbol": symbol,
                        "attempt": index,
                        "total_attempts": total,
                        "attempt_timeout": attempt_timeout,
                        "num_predict": chat_options["num_predict"],
                    },
                )
                response = await self.ai.chat_json(
                    current_model,
                    system,
                    prompt,
                    timeout=attempt_timeout,
                    temperature=float(chat_options["temperature"]),
                    num_ctx=int(chat_options["num_ctx"]),
                    num_predict=int(chat_options["num_predict"]),
                    max_attempts=1,
                )
                effective_model = str(response.get("_model") or current_model)
                decision = str(response.get("decision") or response.get("risk_level") or "unknown")
                confidence = normalize_confidence(response.get("confidence"))
                summary = response.get("reasoning_summary") or response.get("reason") or ""
                self.db.add_analysis(
                    symbol=symbol,
                    role=role,
                    model=effective_model,
                    decision=decision,
                    confidence=confidence,
                    latency_ms=response.get("_latency_ms"),
                    summary=str(summary),
                    response=response,
                    prompt={"system": system, "user": prompt[:6000]},
                )
                self.publish(
                    "ai:done",
                    f"{role} terminou: {decision}",
                    {
                        "role": role,
                        "model": effective_model,
                        "symbol": symbol,
                        "latency_ms": response.get("_latency_ms"),
                        "response": response,
                        "attempt": index,
                        "fallback_from": model if index > 1 else None,
                    },
                )
                if committee_id is not None:
                    summary_text = str(summary)[:280] or "Resposta recebida."
                    if index > 1:
                        summary_text = f"[fallback] {summary_text}"
                    self.update_committee_role(
                        committee_id,
                        role,
                        "done",
                        model=effective_model,
                        symbol=symbol,
                        decision=_binary_direction(response.get("decision") or response.get("preferred_decision")) or "WAIT",
                        confidence=confidence,
                        latency_ms=response.get("_latency_ms"),
                        summary=summary_text,
                        error=None,
                    )
                return {"ok": True, "response": response, "model_used": effective_model, "attempt": index}
            except asyncio.CancelledError:
                if committee_id is not None:
                    self.update_committee_role(
                        committee_id,
                        role,
                        "error",
                        model=current_model,
                        symbol=symbol,
                        decision="WAIT",
                        summary="Cancelado porque o ciclo ficou invalido.",
                        error="cancelled",
                    )
                self.publish(
                    "ai:cancelled",
                    f"{role} cancelado",
                    {"role": role, "model": current_model, "symbol": symbol, "attempt": index},
                )
                raise
            except Exception as exc:
                errors.append({"model": current_model, "error": repr(exc)})
                if index < total:
                    self.publish(
                        "ai:fallback",
                        f"{role} trocando de rota",
                        {"role": role, "symbol": symbol, "failed_model": current_model, "next_model": chain[index], "error": repr(exc)},
                    )
                    continue
                final_error = errors[-1]["error"]
                if committee_id is not None:
                    self.update_committee_role(
                        committee_id,
                        role,
                        "error",
                        model=current_model,
                        symbol=symbol,
                        decision="WAIT",
                        summary="Falhou neste ciclo.",
                        error=final_error,
                    )
                self.publish(
                    "ai:error",
                    f"{role} falhou",
                    {"role": role, "model": current_model, "symbol": symbol, "error": final_error, "attempts": errors},
                )
                return {"ok": False, "error": final_error, "attempts": errors}
        return {"ok": False, "error": "no_model_attempt"}

    def wallet_summary(self) -> dict[str, Any]:
        wallet = self.db.get_kv("wallet", {}) or {}
        config = self.config()
        initial = float(wallet.get("initial_balance_brl") or config.get("initial_balance_brl", 50))
        trades = self.db.list_trades(limit=1000)
        realized = sum(float(item["pnl_brl"]) for item in trades if item["status"] == "CLOSED")
        open_unrealized = 0.0
        wins = 0
        losses = 0
        for item in trades:
            if item["status"] == "CLOSED":
                if float(item["pnl_brl"]) > 0:
                    wins += 1
                else:
                    losses += 1
            elif item["status"] == "OPEN":
                snapshot = self.latest_snapshots.get(item["symbol"]) or {}
                price = ((snapshot.get("features") or {}).get("last_price")) or float(item["entry_price"])
                change_pct = (float(price) / float(item["entry_price"]) - 1) * 100
                open_unrealized += float(item["position_brl"]) * change_pct / 100
        closed_count = wins + losses
        iq_balance = self.iqoption_balance()
        if config.get("execution_provider") == "iqoption_demo" and iq_balance is not None:
            return {
                "initial_balance_brl": initial,
                "realized_pnl_brl": realized,
                "unrealized_pnl_brl": 0.0,
                "equity_brl": iq_balance,
                "closed_trades": closed_count,
                "wins": wins,
                "losses": losses,
                "win_rate_pct": (wins / closed_count * 100) if closed_count else 0,
                "last_trade_at": self.last_trade_at,
                "source": "iqoption_practice_balance",
            }
        return {
            "initial_balance_brl": initial,
            "realized_pnl_brl": realized,
            "unrealized_pnl_brl": open_unrealized,
            "equity_brl": initial + realized + open_unrealized,
            "closed_trades": closed_count,
            "wins": wins,
            "losses": losses,
            "win_rate_pct": (wins / closed_count * 100) if closed_count else 0,
            "last_trade_at": self.last_trade_at,
        }

    def iqoption_balance(self) -> float | None:
        for row in self.platform_statuses:
            if row.get("id") == "iqoption_experimental" and row.get("practice_balance") is not None:
                try:
                    return float(row["practice_balance"])
                except (TypeError, ValueError):
                    return None
        return None

    def set_iqoption_balance(self, balance: Any) -> None:
        try:
            value = float(balance)
        except (TypeError, ValueError):
            return
        for row in self.platform_statuses:
            if row.get("id") == "iqoption_experimental":
                row["practice_balance"] = value
                row["practice_selected"] = True
                row["connected"] = True
                row["status"] = "connected"
                return

    def demo_audit_summary(self) -> dict[str, Any]:
        config = self.config()
        policy = config.get("real_unlock_policy") or {}
        wallet = self.wallet_summary()
        initial = float(wallet.get("initial_balance_brl") or 1)
        closed = [
            item for item in self.db.list_trades(limit=2000)
            if item.get("status") == "CLOSED"
        ]
        closed.sort(key=lambda item: float(item.get("closed_at") or item.get("opened_at") or 0))
        wins = [item for item in closed if float(item.get("pnl_brl") or 0) > 0]
        losses = [item for item in closed if float(item.get("pnl_brl") or 0) <= 0]
        gross_profit = sum(float(item.get("pnl_brl") or 0) for item in wins)
        gross_loss = abs(sum(float(item.get("pnl_brl") or 0) for item in losses))
        profit_factor = gross_profit / gross_loss if gross_loss else (gross_profit if gross_profit > 0 else 0)
        streak = 0
        for item in reversed(closed):
            if float(item.get("pnl_brl") or 0) > 0:
                streak += 1
            else:
                break

        equity = initial
        peak = initial
        max_drawdown_pct = 0.0
        for item in closed:
            equity += float(item.get("pnl_brl") or 0)
            peak = max(peak, equity)
            if peak > 0:
                max_drawdown_pct = max(max_drawdown_pct, (peak - equity) / peak * 100)

        closed_count = len(closed)
        win_rate_pct = (len(wins) / closed_count * 100) if closed_count else 0.0
        xp = max(0, int(len(wins) * 120 + streak * 80 + max(wallet.get("realized_pnl_brl") or 0, 0) * 4 - len(losses) * 90 - max_drawdown_pct * 15))
        level = min(20, xp // 500)
        requirements = {
            "min_closed_trades": int(policy.get("min_closed_trades", 30)),
            "min_consecutive_wins": int(policy.get("min_consecutive_wins", 8)),
            "min_win_rate_pct": float(policy.get("min_win_rate_pct", 70)),
            "min_profit_factor": float(policy.get("min_profit_factor", 1.5)),
            "max_drawdown_pct": float(policy.get("max_drawdown_pct", 8)),
        }
        checks = {
            "closed_trades": closed_count >= requirements["min_closed_trades"],
            "consecutive_wins": streak >= requirements["min_consecutive_wins"],
            "win_rate": win_rate_pct >= requirements["min_win_rate_pct"],
            "profit_factor": profit_factor >= requirements["min_profit_factor"],
            "drawdown": max_drawdown_pct <= requirements["max_drawdown_pct"] if closed_count else False,
        }
        eligible = bool(policy.get("enabled", True)) and all(checks.values())
        return {
            "xp": xp,
            "level": level,
            "status": "eligible" if eligible else "locked",
            "eligible_for_real_review": eligible,
            "closed_trades": closed_count,
            "wins": len(wins),
            "losses": len(losses),
            "consecutive_wins": streak,
            "win_rate_pct": win_rate_pct,
            "profit_factor": profit_factor,
            "max_drawdown_pct": max_drawdown_pct,
            "requirements": requirements,
            "checks": checks,
            "note": "Conta real so libera depois de revisao manual e limites separados." if eligible else "Ainda em auditoria demo.",
        }

    def status(self) -> dict[str, Any]:
        config = self.config()
        next_iq_amount, recovery_state = self.next_iq_amount(config)
        recovery_state = {**recovery_state, "next_amount": next_iq_amount}
        return {
            "running": self.running,
            "config": config,
            "risk_profiles": available_risk_profiles(),
            "iq_gate_profiles": IQ_GATE_PROFILES,
            "wallet": self.wallet_summary(),
            "demo_audit": self.demo_audit_summary(),
            "iq_recovery": recovery_state,
            "platforms": self.platform_statuses,
            "iq_learning": self.iq_learning_state(),
            "committee": self.committee_state,
            "models": self.models,
            "news": self.latest_news,
            "snapshots": self.latest_snapshots or self.db.list_snapshots(),
            "trades": self.db.list_trades(80),
            "analyses": self.db.list_analyses(50),
            "events": self.db.list_events(120),
        }

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self.queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self.queues.discard(queue)

    def publish(self, event_type: str, message: str, data: dict[str, Any] | None = None) -> None:
        event = self.db.add_event(event_type, message, data or {})
        for queue in list(self.queues):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def broadcast_status(self) -> None:
        item = {"_ws_type": "status", "data": self.status()}
        for queue in list(self.queues):
            try:
                queue.put_nowait(item)
            except asyncio.QueueFull:
                pass


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _binary_direction(value: Any) -> str | None:
    text = str(value or "").upper().strip()
    if text in {"CALL", "BUY", "LONG", "ENTER_LONG", "ACIMA"}:
        return "CALL"
    if text in {"PUT", "SELL", "SHORT", "ENTER_SHORT", "ABAIXO"}:
        return "PUT"
    return None


def _is_caution_signal(value: Any) -> bool:
    text = str(value or "").upper().strip()
    return text in {"WAIT", "AVOID", "BLOCK", "VETO", "NO_TRADE", "SKIP"}


def _vote(role: str, model: Any, direction: str | None, response: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": role,
        "model": str(model or ""),
        "ok": bool(result.get("ok")),
        "direction": direction,
        "raw_decision": str(response.get("decision") or response.get("preferred_decision") or "").upper().strip(),
        "confidence": normalize_confidence(response.get("confidence")),
        "risk_level": response.get("risk_level"),
        "latency_ms": response.get("_latency_ms"),
        "summary": str(response.get("reasoning_summary") or response.get("reason") or "")[:280],
        "error": result.get("error"),
    }


def _direction_exhausted(direction: str | None, code_context: dict[str, Any]) -> bool:
    if direction == "PUT":
        return bool(code_context.get("put_exhaustion_risk") or code_context.get("put_overextended"))
    if direction == "CALL":
        return bool(code_context.get("call_exhaustion_risk") or code_context.get("call_overextended"))
    return False


def _same_side_loss_streak(feedback: list[dict[str, Any]], symbol: str, direction: str | None) -> int:
    if not direction:
        return 0
    streak = 0
    for item in feedback:
        if item.get("status") != "CLOSED":
            continue
        if item.get("symbol") != symbol or _binary_direction(item.get("side")) != direction:
            break
        if float(item.get("pnl") or 0) < 0:
            streak += 1
            continue
        break
    return streak


def _dedup_tail(items: list[Any], limit: int) -> list[str]:
    out: list[str] = []
    seen = set()
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text[:260])
    return out[-limit:]


def _pattern_matches(pattern: Any, value: Any) -> bool:
    clean_value = str(value or "").upper()
    parts = [part.strip().upper() for part in str(pattern or "*").split("|") if part.strip()]
    if not parts or "*" in parts:
        return True
    return clean_value in parts


def _iq_gate_profile(config: dict[str, Any]) -> dict[str, Any]:
    key = str(config.get("risk_profile") or "balanced")
    if key not in IQ_GATE_PROFILES:
        key = "balanced"
    return {"key": key, **IQ_GATE_PROFILES[key]}
