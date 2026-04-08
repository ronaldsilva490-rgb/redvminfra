import asyncio
import time
from typing import Any

from .ai import RedSystemsAI
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
        self.models: list[str] = []
        self.last_news_at = 0.0
        self.last_trade_at = float(self.db.get_kv("last_trade_at", 0) or 0)
        self.last_decision_at = 0.0
        self.last_wait_event_at = 0.0
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
            min_sleep = 0.6 if config.get("market_provider") == "iqoption_demo" else 3
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
            min_sleep = 3 if config.get("market_provider") == "iqoption_demo" else 10
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
                if held < expiry_seconds + 5:
                    continue
                try:
                    result = await self.iqoption.check_result(metadata["iqoption_order_id"])
                    self.set_iqoption_balance(result.get("balance_after_close"))
                    pnl_brl = float(result.get("profit") or 0)
                    pnl_pct = pnl_brl / max(float(trade["position_brl"]), 1) * 100
                    status = result.get("status") or "unknown"
                    self.db.close_trade(int(trade["id"]), float(price), pnl_brl, pnl_pct, f"iqoption_demo:{status}")
                    self.update_iq_recovery_after_close(config, trade, pnl_brl, status)
                    self.publish(
                        "trade:closed",
                        f"IQ Option demo fechou {trade['symbol']}: {status}",
                        {"trade_id": trade["id"], "provider": "iqoption_demo", "result": result, "pnl_brl": pnl_brl},
                    )
                except Exception as exc:
                    if "iqoption_result_not_ready" in repr(exc) and held > expiry_seconds + 240:
                        self.db.close_trade(int(trade["id"]), float(price), 0.0, 0.0, "iqoption_demo:unknown_timeout")
                        self.publish(
                            "trade:closed",
                            f"IQ Option demo expirou sem retorno auditavel em {trade['symbol']}",
                            {"trade_id": trade["id"], "provider": "iqoption_demo", "error": repr(exc)},
                        )
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
        candidates = [item for item in candidates if item["technical_score"] >= min_score]
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
            amount, recovery_state = self.next_iq_amount(config)
            expiration_minutes = max(1, int(config.get("iqoption_expiration_minutes", 1)))
            iq_action = "put" if side == "PUT" else "call"
            try:
                order = await self.iqoption.buy(candidate["symbol"], iq_action, amount, expiration_minutes)
            except Exception as exc:
                self.publish(
                    "trade:error",
                    "IQ Option demo recusou a abertura agora",
                    {"symbol": candidate["symbol"], "action": iq_action, "error": repr(exc)},
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
        self.publish(
            "trade:opened",
            f"{'IQ Option demo' if execution_provider == 'iqoption_demo' else 'Paper'} trade aberto em {candidate['symbol']}",
            {"trade_id": trade_id, "symbol": candidate["symbol"], "side": side, "position_brl": position_brl, "entry_price": candidate["price"], "provider": execution_provider},
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

    def iq_recovery_state(self) -> dict[str, Any]:
        state = self.db.get_kv("iqoption_recovery_state", {}) or {}
        return {
            "stage": int(state.get("stage") or 0),
            "loss_total": float(state.get("loss_total") or 0),
            "last_result": state.get("last_result") or "neutral",
            "last_trade_id": state.get("last_trade_id"),
            "last_side": state.get("last_side"),
            "updated_at": state.get("updated_at") or 0,
            "note": state.get("note") or "sem recuperacao ativa",
        }

    def set_iq_recovery_state(self, state: dict[str, Any]) -> None:
        state = {**state, "updated_at": time.time()}
        self.db.set_kv("iqoption_recovery_state", state)
        self.publish("gale:state", "Estado de recuperacao IQ atualizado", state)

    def update_iq_recovery_after_close(self, config: dict[str, Any], trade: dict[str, Any], pnl_brl: float, result_status: str) -> None:
        if not config.get("iqoption_gale_enabled", True):
            self.set_iq_recovery_state({"stage": 0, "loss_total": 0.0, "last_result": result_status, "last_trade_id": trade["id"], "note": "gale desligado"})
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
                    "last_loss_total": loss_total,
                    "note": f"loss no gale {stage}; limite atingido, resetar mindset",
                })
                return
            self.set_iq_recovery_state({
                "stage": stage + 1,
                "loss_total": loss_total,
                "last_result": "loss",
                "last_trade_id": trade["id"],
                "last_side": trade.get("side"),
                "note": f"loss detectado; proxima operacao e gale {stage + 1} com reanalise completa",
            })
            return
        self.set_iq_recovery_state({
            "stage": 0,
            "loss_total": 0.0,
            "last_result": "equal",
            "last_trade_id": trade["id"],
            "last_side": trade.get("side"),
            "note": "empate; sem recuperacao ativa",
        })

    def next_iq_amount(self, config: dict[str, Any]) -> tuple[float, dict[str, Any]]:
        state = self.iq_recovery_state()
        base = max(1.0, float(config.get("iqoption_amount", 1)))
        if not config.get("iqoption_gale_enabled", True):
            return base, state
        stage = max(0, int(state.get("stage") or 0))
        if stage <= 0:
            return base, state
        payout = max(0.1, float(config.get("iqoption_gale_payout_pct", 85)) / 100)
        loss_total = max(0.0, float(state.get("loss_total") or 0))
        multiplier = max(1.0, float(config.get("iqoption_gale_multiplier", 2.35)))
        max_amount = max(base, float(config.get("iqoption_gale_max_amount", 100)))
        target_profit = base
        recovery_amount = (loss_total + target_profit) / payout
        multiplier_amount = base * (multiplier ** stage)
        amount = min(max(recovery_amount, multiplier_amount, base), max_amount)
        return round(amount, 2), state

    def recent_iq_feedback(self, limit: int = 8) -> list[dict[str, Any]]:
        feedback = []
        for trade in self.db.list_trades(80):
            metadata = trade.get("metadata") or {}
            if metadata.get("execution_provider") != "iqoption_demo":
                continue
            feedback.append({
                "id": trade.get("id"),
                "side": trade.get("side"),
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
        critic = await self.safe_ai_call("critic", critic_model, candidate["symbol"], critic_system, critic_prompt, timeout=70)
        critic_response = critic.get("response") or {}
        if critic.get("ok") and (critic_response.get("veto") is True or critic_response.get("risk_level") == "red"):
            return {"approved": False, "reason": "Critico vetou a entrada", "decision": response, "critic": critic_response, "fast": fast}
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
            "wallet": self.wallet_summary(),
            "demo_audit": self.demo_audit_summary(),
            "iq_recovery": recovery_state,
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
