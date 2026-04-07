import asyncio
import time
from typing import Any

from .ai import RedSystemsAI
from .db import Database
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


class TraderRuntime:
    def __init__(self, db: Database, market: BinanceMarketClient, news: NewsClient, ai: RedSystemsAI):
        self.db = db
        self.market = market
        self.news_client = news
        self.ai = ai
        self.task: asyncio.Task | None = None
        self.running = False
        self.latest_snapshots: dict[str, dict[str, Any]] = {}
        self.latest_news: dict[str, Any] = {}
        self.platforms = PlatformRegistry()
        self.platform_statuses: list[dict[str, Any]] = []
        self.last_platforms_at = 0.0
        self.models: list[str] = []
        self.last_news_at = 0.0
        self.last_trade_at = float(self.db.get_kv("last_trade_at", 0) or 0)
        self.last_wait_event_at = 0.0
        self.queues: set[asyncio.Queue] = set()
        self.cycle_lock = asyncio.Lock()
        if self.db.get_kv("config") is None:
            self.db.set_kv("config", DEFAULT_CONFIG)
        if self.db.get_kv("wallet") is None:
            self.db.set_kv("wallet", {"initial_balance_brl": DEFAULT_CONFIG["initial_balance_brl"]})

    def config(self) -> dict[str, Any]:
        return deep_merge(DEFAULT_CONFIG, self.db.get_kv("config", {}) or {})

    def update_config(self, patch: dict[str, Any]) -> dict[str, Any]:
        merged = deep_merge(self.config(), patch)
        if merged.get("risk_profile") not in RISK_PROFILES:
            merged["risk_profile"] = DEFAULT_CONFIG["risk_profile"]
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
        self.publish("runtime", "RED Trader iniciado", {})

    async def stop(self) -> None:
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        self.publish("runtime", "RED Trader parado", {})

    async def loop(self) -> None:
        while self.running:
            started = time.time()
            try:
                await self.cycle(reason="loop")
            except Exception as exc:
                self.publish("error", "Falha no ciclo principal", {"error": repr(exc)})
            elapsed = time.time() - started
            await asyncio.sleep(max(3, float(self.config().get("market_poll_seconds", 20)) - elapsed))

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

            symbols = config.get("symbols") or DEFAULT_CONFIG["symbols"]
            snapshots = await self.market.fetch_symbols(symbols)
            self.latest_snapshots = snapshots
            for symbol, snapshot in snapshots.items():
                self.db.save_snapshot(symbol, snapshot)
            self.publish("market", "Mercado atualizado", {"symbols": list(snapshots.keys()), "reason": reason})
            await self.handle_exits(config)
            await self.maybe_enter(config)

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

    async def handle_exits(self, config: dict[str, Any]) -> None:
        open_trades = self.db.open_trades()
        if not open_trades:
            return
        max_hold_seconds = float(config.get("max_hold_minutes", 60)) * 60
        fee_pct = float(config.get("paper_fee_pct_per_side", 0.1))
        for trade in open_trades:
            snapshot = self.latest_snapshots.get(trade["symbol"]) or {}
            price = ((snapshot.get("features") or {}).get("last_price")) or ((snapshot.get("ticker") or {}).get("last_price"))
            if not price:
                continue
            entry = float(trade["entry_price"])
            change_pct = (float(price) / entry - 1) * 100
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
        guard = self.risk_guard(config)
        if not guard["ok"]:
            self.publish("risk:blocked", guard["reason"], guard)
            return
        candidates = build_candidates(self.latest_snapshots, config, self.latest_news)
        min_score = float(config.get("min_technical_score", 75))
        candidates = [item for item in candidates if item["technical_score"] >= min_score]
        if not candidates:
            if time.time() - self.last_wait_event_at > 300:
                self.last_wait_event_at = time.time()
                self.publish("strategy:wait", "Nenhum candidato passou nos gates tecnicos", {"min_score": min_score})
            return
        candidate = candidates[0]
        self.publish(
            "strategy:candidate",
            f"Candidato tecnico encontrado em {candidate['symbol']}",
            {"symbol": candidate["symbol"], "technical_score": candidate["technical_score"], "checks": candidate["checks"]},
        )
        decision = await self.run_ai_committee(candidate, config)
        if not decision.get("approved"):
            self.publish("trade:skipped", "Comite vetou a entrada", decision)
            return
        position_brl = max(1.0, self.wallet_summary()["equity_brl"] * float(decision["position_pct"]) / 100)
        trade_id = self.db.open_trade(
            candidate["symbol"],
            "LONG",
            float(candidate["price"]),
            position_brl,
            float(decision["stop_loss_pct"]),
            float(decision["take_profit_pct"]),
            decision.get("reasoning_summary", ""),
            metadata={"decision": decision, "candidate": candidate},
        )
        self.last_trade_at = time.time()
        self.db.set_kv("last_trade_at", self.last_trade_at)
        self.publish(
            "trade:opened",
            f"Paper trade aberto em {candidate['symbol']}",
            {"trade_id": trade_id, "symbol": candidate["symbol"], "position_brl": position_brl, "entry_price": candidate["price"]},
        )

    def risk_guard(self, config: dict[str, Any]) -> dict[str, Any]:
        now = time.time()
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

    async def run_ai_committee(self, candidate: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        system, prompt = build_decision_prompt(candidate, self.latest_news, config)
        fast_model = config["models"].get("fast_filter")
        decision_model = config["models"].get("decision")
        critic_model = config["models"].get("critic")
        fast = {}
        if fast_model:
            fast = await self.safe_ai_call("fast_filter", fast_model, candidate["symbol"], system, prompt, timeout=25)
        final = await self.safe_ai_call("decision", decision_model, candidate["symbol"], system, prompt, timeout=70)
        if not final.get("ok"):
            return {"approved": False, "reason": "Modelo decisor falhou", "fast": fast, "final": final}
        response = final["response"]
        confidence = normalize_confidence(response.get("confidence"))
        decision = str(response.get("decision", "")).upper()
        risk_reward = _num(response.get("risk_reward"))
        position_pct = min(float(config.get("position_pct", 20)), _num(response.get("position_pct")) or float(config.get("position_pct", 20)))
        stop_loss_pct = _num(response.get("stop_loss_pct")) or candidate["stop_loss_pct"]
        take_profit_pct = _num(response.get("take_profit_pct")) or candidate["take_profit_pct"]
        final_ok = (
            decision == "ENTER_LONG"
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
        critic = await self.safe_ai_call("critic", critic_model, candidate["symbol"], critic_system, critic_prompt, timeout=70)
        critic_response = critic.get("response") or {}
        if critic.get("ok") and (critic_response.get("veto") is True or critic_response.get("risk_level") == "red"):
            return {"approved": False, "reason": "Critico vetou a entrada", "decision": response, "critic": critic_response, "fast": fast}
        return {
            "approved": True,
            "symbol": candidate["symbol"],
            "confidence": confidence,
            "position_pct": position_pct,
            "stop_loss_pct": stop_loss_pct,
            "take_profit_pct": take_profit_pct,
            "risk_reward": risk_reward,
            "reasoning_summary": response.get("reasoning_summary", ""),
            "decision": response,
            "critic": critic_response,
            "fast": fast.get("response", {}),
        }

    async def safe_ai_call(
        self,
        role: str,
        model: str | None,
        symbol: str,
        system: str,
        prompt: str,
        timeout: int,
    ) -> dict[str, Any]:
        if not model:
            return {"ok": False, "error": "modelo nao configurado"}
        try:
            self.publish("ai:start", f"{role} analisando {symbol}", {"role": role, "model": model, "symbol": symbol})
            response = await self.ai.chat_json(model, system, prompt, timeout=timeout)
            decision = str(response.get("decision") or response.get("risk_level") or "unknown")
            confidence = normalize_confidence(response.get("confidence"))
            summary = response.get("reasoning_summary") or response.get("reason") or ""
            self.db.add_analysis(
                symbol=symbol,
                role=role,
                model=model,
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
                {"role": role, "model": model, "symbol": symbol, "latency_ms": response.get("_latency_ms"), "response": response},
            )
            return {"ok": True, "response": response}
        except Exception as exc:
            self.publish("ai:error", f"{role} falhou", {"role": role, "model": model, "symbol": symbol, "error": repr(exc)})
            return {"ok": False, "error": repr(exc)}

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
        return {
            "running": self.running,
            "config": self.config(),
            "risk_profiles": available_risk_profiles(),
            "wallet": self.wallet_summary(),
            "demo_audit": self.demo_audit_summary(),
            "platforms": self.platform_statuses,
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


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
