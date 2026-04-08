import json
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "auto_enabled": True,
    "risk_profile": "balanced",
    "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    "tradable_symbols": ["BTCUSDT", "ETHUSDT"],
    "market_provider": "binance_spot",
    "execution_provider": "internal_paper",
    "iqoption_amount": 1.0,
    "iqoption_expiration_minutes": 1,
    "iqoption_gale_enabled": True,
    "iqoption_gale_max_steps": 2,
    "iqoption_gale_multiplier": 2.35,
    "iqoption_gale_payout_pct": 85,
    "iqoption_gale_max_amount": 100,
    "iqoption_stake_mode": "fixed",
    "iqoption_consensus_stakes": {
        "enabled": True,
        "mode": "fixed",
        "min_votes": 2,
        "recovery_min_votes": 3,
        "require_core_unanimous_for_recovery": True,
        "tiers": {
            "2": 10,
            "3": 25,
            "4": 50,
            "5": 100,
        },
        "pct_tiers": {
            "2": 1,
            "3": 2.5,
            "4": 5,
            "5": 10,
        },
    },
    "iqoption_learning": {
        "enabled": True,
        "apply_code_memory": True,
        "use_model_reflection": True,
        "min_new_closed": 5,
        "interval_seconds": 150,
        "recent_limit": 40,
        "max_lessons": 12,
        "model": "qwen/qwen3-next-80b-a3b-instruct (NVIDIA)",
    },
    "iqoption_techniques": {
        "multi_timeframe_confluence": True,
        "momentum_continuation": True,
        "trend_pullback": True,
        "reversal_exhaustion": True,
        "volatility_filter": True,
        "anti_repeat_loss": True,
        "adaptive_recovery": True,
    },
    "market_poll_seconds": 0.25,
    "decision_poll_seconds": 3,
    "news_poll_seconds": 300,
    "cooldown_minutes": 30,
    "max_trades_per_day": 3,
    "max_open_positions": 1,
    "initial_balance_brl": 50.0,
    "position_pct": 20.0,
    "daily_stop_loss_pct": 5.0,
    "daily_target_pct": 3.0,
    "min_technical_score": 75,
    "min_ai_confidence": 72,
    "min_risk_reward": 1.3,
    "max_decision_latency_ms": 8000,
    "max_signal_age_seconds": 4,
    "post_gale2_cooldown_minutes": 6,
    "max_hold_minutes": 60,
    "paper_fee_pct_per_side": 0.1,
    "real_unlock_policy": {
        "enabled": True,
        "min_closed_trades": 30,
        "min_consecutive_wins": 8,
        "min_win_rate_pct": 70,
        "min_profit_factor": 1.5,
        "max_drawdown_pct": 8,
    },
    "models": {
        "fast_filter": "nemotron-3-super",
        "decision": "gemma3:4b",
        "critic": "ministral-3:3b",
        "premium_4": "ministral-3:8b",
        "premium_5": "qwen/qwen3-next-80b-a3b-instruct (NVIDIA)",
        "report": "qwen/qwen3-next-80b-a3b-instruct (NVIDIA)",
    },
    "platforms": {
        "binance_spot": {
            "enabled": True,
            "mode": "market_data_paper",
            "label": "Binance Spot",
        },
        "tastytrade_sandbox": {
            "enabled": True,
            "mode": "sandbox",
            "label": "tastytrade Sandbox",
        },
        "webull_paper": {
            "enabled": True,
            "mode": "paper",
            "label": "Webull Paper",
        },
        "iqoption_experimental": {
            "enabled": True,
            "mode": "demo",
            "label": "IQ Option Demo",
        },
    },
}


RISK_PROFILES: dict[str, dict[str, Any]] = {
    "conservative": {
        "label": "Conservador",
        "description": "Menos entradas, mais filtros, foco em preservar o saldo paper.",
        "prompt": (
            "Seja seletivo. Prefira WAIT quando houver ambiguidade, noticia de risco, "
            "RSI esticado ou confirmacao tecnica incompleta."
        ),
        "critic_prompt": "Vete entradas com qualquer fragilidade relevante.",
        "settings": {
            "position_pct": 10.0,
            "cooldown_minutes": 2,
            "decision_poll_seconds": 4,
            "market_poll_seconds": 0.5,
            "max_trades_per_day": 60,
            "max_open_positions": 1,
            "daily_stop_loss_pct": 20.0,
            "daily_target_pct": 20.0,
            "min_technical_score": 82,
            "min_ai_confidence": 82,
            "min_risk_reward": 1.6,
            "max_hold_minutes": 45,
        },
    },
    "balanced": {
        "label": "Balanceado",
        "description": "Configuração padrão: seletiva, mas sem travar demais o paper trading.",
        "prompt": (
            "Aprove apenas setups com boa combinacao de tendencia, momentum, liquidez, "
            "volatilidade controlada e risco/retorno aceitavel."
        ),
        "critic_prompt": "Vete se o risco principal estiver subestimado.",
        "settings": {
            "position_pct": 20.0,
            "cooldown_minutes": 1,
            "decision_poll_seconds": 3,
            "market_poll_seconds": 0.35,
            "max_trades_per_day": 160,
            "max_open_positions": 1,
            "daily_stop_loss_pct": 35.0,
            "daily_target_pct": 35.0,
            "min_technical_score": 75,
            "min_ai_confidence": 72,
            "min_risk_reward": 1.3,
            "max_hold_minutes": 60,
        },
    },
    "aggressive": {
        "label": "Agressivo",
        "description": "Mais oportunidades e mais risco no paper, sem alavancagem e com auditoria.",
        "prompt": (
            "Pode aceitar setups de maior variancia se houver momentum, liquidez e plano de saida. "
            "Nao invente dados; responda WAIT se o sinal for fraco."
        ),
        "critic_prompt": "Vete risco estrutural, noticia vermelha, liquidez ruim ou RR incoerente; aceite variancia esperada.",
        "settings": {
            "position_pct": 30.0,
            "cooldown_minutes": 0.5,
            "decision_poll_seconds": 1.5,
            "market_poll_seconds": 0.25,
            "max_trades_per_day": 300,
            "max_open_positions": 1,
            "daily_stop_loss_pct": 60.0,
            "daily_target_pct": 60.0,
            "min_technical_score": 68,
            "min_ai_confidence": 64,
            "min_risk_reward": 1.15,
            "max_hold_minutes": 45,
        },
    },
    "full_aggressive": {
        "label": "Full agressivo",
        "description": "Experimental: busca mais entradas no paper e aceita setups mais arriscados.",
        "prompt": (
            "Perfil experimental. Procure oportunidades de curtissimo prazo com mais apetite a risco, "
            "sem tratar noticia vermelha como veto automatico em conta demo. Noticia vermelha vira risco alto: "
            "so aprove se liquidez, stop, saida e momentum estiverem claros."
        ),
        "critic_prompt": (
            "Vete apenas riscos graves: noticia diretamente destrutiva para o ativo, baixa liquidez, spread alto, "
            "dados incoerentes, ausencia de stop ou risco/retorno absurdo."
        ),
        "settings": {
            "position_pct": 40.0,
            "cooldown_minutes": 0.25,
            "decision_poll_seconds": 1.0,
            "market_poll_seconds": 0.25,
            "max_trades_per_day": 500,
            "max_open_positions": 1,
            "daily_stop_loss_pct": 80.0,
            "daily_target_pct": 80.0,
            "min_technical_score": 55,
            "min_ai_confidence": 55,
            "min_risk_reward": 1.0,
            "max_decision_latency_ms": 8000,
            "max_signal_age_seconds": 4,
            "post_gale2_cooldown_minutes": 6,
            "max_hold_minutes": 0.5,
        },
    },
}


def available_risk_profiles() -> dict[str, dict[str, Any]]:
    return {
        key: {
            "label": value["label"],
            "description": value["description"],
            "settings": value["settings"],
        }
        for key, value in RISK_PROFILES.items()
    }


def risk_profile_context(config: dict[str, Any]) -> dict[str, Any]:
    key = str(config.get("risk_profile") or "balanced")
    profile = RISK_PROFILES.get(key) or RISK_PROFILES["balanced"]
    return {
        "key": key if key in RISK_PROFILES else "balanced",
        "label": profile["label"],
        "description": profile["description"],
        "prompt": profile["prompt"],
        "critic_prompt": profile["critic_prompt"],
        "settings": profile["settings"],
    }


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def normalize_confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if 0 < number <= 1:
        return number * 100
    return max(0.0, min(100.0, number))


def compact_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": snapshot.get("symbol"),
        "ts": snapshot.get("ts"),
        "ticker": snapshot.get("ticker", {}),
        "orderbook": snapshot.get("orderbook", {}),
        "features": snapshot.get("features", {}),
        "frames": snapshot.get("frames", {}),
    }


def build_candidates(
    snapshots: dict[str, dict[str, Any]],
    config: dict[str, Any],
    news: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    candidates = []
    tradable = set(config.get("tradable_symbols") or [])
    news_risk = ((news or {}).get("risk_hint") or {}).get("level", "neutral")
    for symbol, snapshot in snapshots.items():
        if snapshot.get("error") or symbol not in tradable:
            continue
        effective_news_risk = "neutral" if snapshot.get("provider") == "iqoption_demo" else news_risk
        candidate = score_snapshot(snapshot, config, effective_news_risk)
        if candidate:
            candidates.append(candidate)
    return sorted(candidates, key=lambda item: item["technical_score"], reverse=True)


def iq_direction_context(features: dict[str, Any]) -> dict[str, Any]:
    rsi_1s = _num(features.get("rsi_1s"))
    rsi_1m = _num(features.get("rsi_1m"))
    rsi_5m = _num(features.get("rsi_5m"))
    rsi_15m = _num(features.get("rsi_15m"))
    change_1s_5 = _num(features.get("change_1s_5"))
    change_1s_15 = _num(features.get("change_1s_15"))
    change_1m_15 = _num(features.get("change_1m_15"))
    change_5m_15 = _num(features.get("change_5m_15"))
    trend_1s = features.get("trend_1s")
    trend_1m = features.get("trend_1m")
    trend_5m = features.get("trend_5m")
    trend_15m = features.get("trend_15m")
    up_count = sum(1 for item in [trend_1s, trend_1m, trend_5m, trend_15m] if item == "up")
    down_count = sum(1 for item in [trend_1s, trend_1m, trend_5m, trend_15m] if item == "down")

    call_score = 0.0
    put_score = 0.0
    wait_score = 0.0
    notes: list[str] = []
    traps: list[str] = []

    if up_count >= 3:
        call_score += 20
    if down_count >= 3:
        put_score += 20
    if change_1m_15 > 0.04:
        call_score += 10
    if change_1m_15 < -0.04:
        put_score += 10
    if change_5m_15 > 0.12:
        call_score += 8
    if change_5m_15 < -0.12:
        put_score += 8

    # RSI extremo de 15m foi o padrao dos gales perdidos: ele favorece
    # reversao, mas so quando o microtempo nao esta gritando o contrario.
    if rsi_15m >= 86:
        put_score += 26
        call_score -= 12
        notes.append("15m sobrecomprado: procurar PUT/reversao ou WAIT")
        traps.append("call_overextended")
    elif rsi_15m <= 18 and rsi_15m > 0:
        call_score += 26
        put_score -= 12
        notes.append("15m sobrevendido: procurar CALL/reversao ou WAIT")
        traps.append("put_overextended")

    if rsi_1m >= 70 and rsi_5m >= 64:
        put_score += 16
        call_score -= 18
        traps.append("call_exhaustion_risk")
    if 0 < rsi_1m <= 36 and 0 < rsi_5m <= 40:
        call_score += 16
        put_score -= 18
        traps.append("put_exhaustion_risk")
    if rsi_1s >= 76:
        put_score += 8
        call_score -= 12
        wait_score += 8
        traps.append("call_exhaustion_risk")
        notes.append("microtempo sobrecomprado: CALL precisa de mais votos")
    if 0 < rsi_1s <= 24:
        call_score += 8
        put_score -= 12
        wait_score += 8
        traps.append("put_exhaustion_risk")
        notes.append("microtempo sobrevendido: PUT precisa de mais votos")
    if trend_15m == "up" and down_count >= 3 and 0 < rsi_1s <= 28:
        put_score -= 10
        wait_score += 12
        traps.append("put_exhaustion_risk")
        notes.append("queda curta contra 15m de alta; risco de pullback acabar")
    if trend_15m == "down" and up_count >= 3 and rsi_1s >= 72:
        call_score -= 10
        wait_score += 12
        traps.append("call_exhaustion_risk")
        notes.append("alta curta contra 15m de baixa; risco de pullback acabar")

    if change_1s_5 > 0.015 and change_1s_15 > 0.02:
        call_score += 7
    if change_1s_5 < -0.015 and change_1s_15 < -0.02:
        put_score += 7

    if abs(call_score - put_score) < 8:
        wait_score += 18
        notes.append("placar direcional apertado")
    if max(call_score, put_score) < 18:
        wait_score += 18
        notes.append("sem edge tecnico forte")

    preferred = "CALL" if call_score > put_score else "PUT"
    if wait_score >= max(call_score, put_score):
        preferred = "WAIT"

    return {
        "preferred_direction": preferred,
        "scores": {
            "CALL": round(call_score, 2),
            "PUT": round(put_score, 2),
            "WAIT": round(wait_score, 2),
        },
        "up_count": up_count,
        "down_count": down_count,
        "traps": traps,
        "notes": notes,
        "put_exhaustion_risk": "put_exhaustion_risk" in traps,
        "call_exhaustion_risk": "call_exhaustion_risk" in traps,
        "call_overextended": "call_overextended" in traps,
        "put_overextended": "put_overextended" in traps,
    }


def score_snapshot(snapshot: dict[str, Any], config: dict[str, Any], news_risk: str) -> dict[str, Any] | None:
    features = snapshot.get("features") or {}
    symbol = snapshot.get("symbol")
    price = _num(features.get("last_price"))
    if not price:
        return None

    checks: dict[str, str] = {}
    score = 0

    is_binary = snapshot.get("provider") == "iqoption_demo"
    code_context = iq_direction_context(features) if is_binary else {}
    up_count = sum(1 for key in ["trend_1m", "trend_5m", "trend_15m"] if features.get(key) == "up")
    down_count = sum(1 for key in ["trend_1m", "trend_5m", "trend_15m"] if features.get(key) == "down")
    action = "CALL" if is_binary else "ENTER_LONG"
    if is_binary and code_context.get("preferred_direction") in {"CALL", "PUT"}:
        action = str(code_context["preferred_direction"])
    if is_binary and down_count >= 2:
        action = str(code_context.get("preferred_direction") or "PUT") if code_context.get("preferred_direction") != "WAIT" else "PUT"
        checks["trend"] = "pass"
        score += 22
    elif up_count >= 2:
        action = str(code_context.get("preferred_direction") or "CALL") if is_binary and code_context.get("preferred_direction") != "WAIT" else ("CALL" if is_binary else "ENTER_LONG")
        checks["trend"] = "pass"
        score += 22
    elif up_count == 1 or (is_binary and down_count == 1):
        action = "PUT" if is_binary and down_count > up_count else action
        checks["trend"] = "neutral"
        score += 8
    else:
        checks["trend"] = "fail"

    change_1m_15 = _num(features.get("change_1m_15"))
    change_5m_15 = _num(features.get("change_5m_15"))
    rsi_1m = _num(features.get("rsi_1m"))
    rsi_5m = _num(features.get("rsi_5m"))
    if action == "PUT":
        momentum_pass = change_1m_15 < -0.04 and change_5m_15 < 0.05 and 28 <= rsi_1m <= 58 and 26 <= rsi_5m <= 62
        momentum_neutral = change_1m_15 < 0 and rsi_1m > 20
    else:
        momentum_pass = change_1m_15 > 0.04 and change_5m_15 > -0.05 and 45 <= rsi_1m <= 72 and 42 <= rsi_5m <= 74
        momentum_neutral = change_1m_15 > 0 and rsi_1m < 78

    if momentum_pass:
        checks["momentum"] = "pass"
        score += 22
    elif momentum_neutral:
        checks["momentum"] = "neutral"
        score += 10
    else:
        checks["momentum"] = "fail"

    vol_1m = _num(features.get("ret_std_1m_30"))
    if 0.025 <= vol_1m <= 0.25:
        checks["volatility"] = "pass"
        score += 15
    elif 0 < vol_1m <= 0.35:
        checks["volatility"] = "neutral"
        score += 7
    else:
        checks["volatility"] = "fail"

    spread = _num(features.get("spread_pct"))
    volume_ratio = _num(features.get("volume_1m_vs_avg30"))
    if spread <= 0.03 and volume_ratio >= 0.6:
        checks["liquidity"] = "pass"
        score += 16
    elif spread <= 0.06:
        checks["liquidity"] = "neutral"
        score += 6
    else:
        checks["liquidity"] = "fail"

    if news_risk == "red":
        checks["news_risk"] = "fail"
    elif news_risk == "yellow":
        checks["news_risk"] = "neutral"
        score += 5
    else:
        checks["news_risk"] = "pass"
        score += 10

    if is_binary:
        scores = code_context.get("scores") or {}
        edge = max(_num(scores.get("CALL")), _num(scores.get("PUT"))) - _num(scores.get("WAIT"))
        if edge >= 16:
            checks["code_edge"] = "pass"
            score += 14
        elif edge >= 5:
            checks["code_edge"] = "neutral"
            score += 6
        else:
            checks["code_edge"] = "fail"

    stop_loss_pct = round(max(0.25, min(0.9, vol_1m * 3.2)), 3)
    take_profit_pct = round(stop_loss_pct * 1.55, 3)
    risk_reward = round(take_profit_pct / stop_loss_pct, 2) if stop_loss_pct else 0
    if risk_reward >= float(config.get("min_risk_reward", 1.3)):
        checks["risk_reward"] = "pass"
        score += 15
    else:
        checks["risk_reward"] = "fail"

    return {
        "symbol": symbol,
        "price": price,
        "technical_score": score,
        "checks": checks,
        "stop_loss_pct": stop_loss_pct,
        "take_profit_pct": take_profit_pct,
        "risk_reward": risk_reward,
        "position_pct": float(config.get("position_pct", 20)),
        "trade_type": "binary_options" if is_binary else "spot_long",
        "action": action,
        "expiration_minutes": int(config.get("iqoption_expiration_minutes", 1)) if is_binary else None,
        "code_context": code_context,
        "features": features,
        "snapshot": compact_snapshot(snapshot),
    }


def _limit_text(value: Any, limit: int = 180) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _compact_features(features: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "last_price",
        "trend_1s",
        "trend_1m",
        "trend_5m",
        "trend_15m",
        "rsi_1s",
        "rsi_1m",
        "rsi_5m",
        "rsi_15m",
        "change_1s_5",
        "change_1s_15",
        "change_1m_15",
        "change_5m_15",
        "ret_std_1m_30",
        "spread_pct",
        "volume_1m_vs_avg30",
    ]
    return {key: features.get(key) for key in keys if key in features}


def _compact_code_context(code_context: dict[str, Any]) -> dict[str, Any]:
    if not code_context:
        return {}
    return {
        "preferred_direction": code_context.get("preferred_direction"),
        "scores": code_context.get("scores"),
        "up_count": code_context.get("up_count"),
        "down_count": code_context.get("down_count"),
        "traps": list(code_context.get("traps") or [])[:4],
        "notes": [_limit_text(item, 120) for item in list(code_context.get("notes") or [])[:4]],
        "call_exhaustion_risk": bool(code_context.get("call_exhaustion_risk")),
        "put_exhaustion_risk": bool(code_context.get("put_exhaustion_risk")),
        "call_overextended": bool(code_context.get("call_overextended")),
        "put_overextended": bool(code_context.get("put_overextended")),
    }


def _compact_learning_context(learning_context: dict[str, Any]) -> dict[str, Any]:
    if not learning_context:
        return {}
    avoids = []
    for item in list(learning_context.get("active_avoid_patterns") or [])[:4]:
        avoids.append(
            {
                "symbol": item.get("symbol"),
                "direction": item.get("direction"),
                "severity": item.get("severity"),
                "reason": _limit_text(item.get("reason"), 120),
            }
        )
    last_reflection = learning_context.get("last_reflection") or {}
    return {
        "active_avoid_patterns": avoids,
        "lessons": [_limit_text(item, 140) for item in list(learning_context.get("lessons") or [])[-4:]],
        "recovery_rules": [_limit_text(item, 140) for item in list(learning_context.get("recovery_rules") or [])[-4:]],
        "stats_for_direction": learning_context.get("stats_for_direction"),
        "last_reflection": {
            "model": last_reflection.get("model"),
            "trade_id": last_reflection.get("trade_id"),
            "technique_suggestions": [_limit_text(item, 120) for item in list(last_reflection.get("technique_suggestions") or [])[:4]],
        },
    }


def _compact_recent_trade_feedback(feedback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for item in feedback[:3]:
        pnl = _num(item.get("pnl"))
        out.append(
            {
                "id": item.get("id"),
                "symbol": item.get("symbol"),
                "side": item.get("side"),
                "status": item.get("status"),
                "gale_stage": item.get("gale_stage", 0),
                "amount": item.get("amount"),
                "pnl": item.get("pnl"),
                "outcome": "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "DRAW"),
                "reasoning": _limit_text(item.get("reasoning"), 120),
            }
        )
    return out


def _compact_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    snapshot = candidate.get("snapshot") or {}
    return {
        "symbol": candidate.get("symbol"),
        "trade_type": candidate.get("trade_type"),
        "action": candidate.get("action"),
        "price": candidate.get("price"),
        "technical_score": candidate.get("technical_score"),
        "checks": candidate.get("checks"),
        "risk_reward": candidate.get("risk_reward"),
        "stop_loss_pct": candidate.get("stop_loss_pct"),
        "take_profit_pct": candidate.get("take_profit_pct"),
        "position_pct": candidate.get("position_pct"),
        "expiration_minutes": candidate.get("expiration_minutes"),
        "provider": snapshot.get("provider"),
        "snapshot_ts": snapshot.get("ts"),
        "features": _compact_features(candidate.get("features") or {}),
        "code_context": _compact_code_context(candidate.get("code_context") or {}),
    }


def build_decision_prompt(candidate: dict[str, Any], news: dict[str, Any] | None, config: dict[str, Any]) -> tuple[str, str]:
    profile = risk_profile_context(config)
    is_binary = candidate.get("trade_type") == "binary_options"
    allowed_decisions = ["WAIT", "AVOID", "CALL", "PUT"] if is_binary else ["WAIT", "AVOID", "ENTER_LONG"]
    decision_schema = "|".join(allowed_decisions)
    market_scope = (
        "operacoes binarias DEMO/PRACTICE na IQ Option, com ativos OTC permitidos e expiracao curta"
        if is_binary
        else "paper trading cripto spot, sem alavancagem"
    )
    mode = "iqoption_demo_binary_only" if is_binary else "paper_trading_only"
    if profile["key"] == "full_aggressive":
        news_rule = (
            "No perfil full agressivo, news_risk=fail significa risco alto, nao veto automatico. "
            "Pode aprovar SOMENTE em demo se o setup tecnico, liquidez, stop, alvo e saida estiverem claros. "
            "Se aprovar com noticia vermelha, reduza position_pct e explique a invalidacao."
        )
    else:
        news_rule = (
            "Nunca aprove entrada sem stop, sem plano de saida, com noticia vermelha "
            "ou com dados contraditorios."
        )
    system = (
        f"Voce e um comite de risco para {market_scope}. "
        f"Perfil operacional paper: {profile['label']}. {profile['prompt']} "
        "Seu trabalho e decidir com base nos dados, sem prometer lucro e sem inventar informacao. "
        "Responda SOMENTE JSON valido, sem markdown."
    )
    recovery_context = candidate.get("recovery_context") or {}
    recovery_stage = int(recovery_context.get("stage") or 0)
    recovery_same_symbol = recovery_stage > 0 and str(recovery_context.get("last_symbol") or "") == str(candidate.get("symbol") or "")
    recovery_guidance = {
        "scope": "same_symbol" if recovery_same_symbol else ("cross_symbol" if recovery_stage > 0 else "none"),
        "rule": (
            "mesmo ativo do loss: repetir direcao exige evidencia muito mais forte"
            if recovery_same_symbol
            else (
                "recuperacao em outro ativo: nao trate como repeticao do mesmo setup; aprove se o setup atual for claro"
                if recovery_stage > 0
                else "sem recuperacao ativa"
            )
        ),
    }
    payload = {
        "mode": mode,
        "risk_profile": {
            "key": profile["key"],
            "label": profile["label"],
            "description": profile["description"],
        },
        "balance_brl": config.get("initial_balance_brl", 50),
        "constraints": {
            "min_confidence": config.get("min_ai_confidence"),
            "min_risk_reward": config.get("min_risk_reward"),
            "max_position_pct": config.get("position_pct"),
            "daily_stop_loss_pct": config.get("daily_stop_loss_pct"),
            "cooldown_minutes": config.get("cooldown_minutes"),
            "allowed_decisions": allowed_decisions,
        },
        "candidate": _compact_candidate(candidate),
        "recovery_context": {
            "stage": recovery_context.get("stage"),
            "last_symbol": recovery_context.get("last_symbol"),
            "last_side": recovery_context.get("last_side"),
            "loss_total": recovery_context.get("loss_total"),
            "next_amount": recovery_context.get("next_amount"),
        },
        "recovery_guidance": recovery_guidance,
        "learning_context": _compact_learning_context(candidate.get("learning_context") or {}),
        "learning_adjustment": candidate.get("learning_adjustment") or {},
        "recent_trade_feedback": _compact_recent_trade_feedback(candidate.get("recent_trade_feedback") or []),
        "news": (
            {
                "risk_hint": {
                    "level": "neutral",
                    "reason": "feed de noticias cripto ignorado para OTC demo da IQ",
                },
                "headlines": [],
            }
            if is_binary
            else news or {}
        ),
    }
    user = (
        "Analise o candidato abaixo respeitando o perfil operacional informado. "
        "Se o modo for iqoption_demo_binary_only, ativos OTC como EURUSD-OTC sao permitidos e devem ser avaliados como CALL/PUT demo. "
        "Use code_context como pre-leitura quantitativa: se ele apontar exaustao/armadilha, trate como alerta forte. "
        "Use learning_context como memoria operacional: evite repetir padroes marcados como loss recente, mas permita excecao somente com consenso forte. "
        "Use learning_adjustment para entender bonus/penalidades que o codigo aplicou ao score antes de chamar os modelos. "
        "Em gale/recuperacao, repetir a mesma direcao do loss anterior exige evidencia muito mais forte SOMENTE se for o mesmo ativo do loss. "
        "Se recovery_guidance.scope for cross_symbol, nao trate como repeticao do mesmo setup: decida pelo candidato atual com agressividade demo. "
        f"{news_rule} Se estiver ambiguo demais, responda WAIT.\n\n"
        "Retorne JSON exatamente neste formato:\n"
        "{"
        f'"decision":"{decision_schema}",'
        '"symbol":"ATIVO_DO_CANDIDATO|NONE",'
        '"confidence":0,'
        '"position_pct":0,'
        '"time_horizon_min":0,'
        '"stop_loss_pct":0,'
        '"take_profit_pct":0,'
        '"risk_reward":0,'
        '"checks":{"trend":"pass|fail|neutral","momentum":"pass|fail|neutral","volatility":"pass|fail|neutral","liquidity":"pass|fail|neutral","news_risk":"pass|fail|neutral","risk_reward":"pass|fail|neutral"},'
        '"invalidation":"frase curta",'
        '"reasoning_summary":"ate 700 caracteres",'
        '"next_review_minutes":0'
        "}\n\n"
        f"DADOS:\n{json.dumps(payload, ensure_ascii=False)}"
    )
    return system, user


def build_critic_prompt(
    candidate: dict[str, Any],
    decision: dict[str, Any],
    news: dict[str, Any] | None,
    config: dict[str, Any],
) -> tuple[str, str]:
    profile = risk_profile_context(config)
    is_binary = candidate.get("trade_type") == "binary_options"
    market_scope = (
        "operacoes binarias DEMO/PRACTICE na IQ Option, com ativos OTC permitidos"
        if is_binary
        else "paper trading cripto spot"
    )
    if profile["key"] == "full_aggressive":
        critic_rule = (
            "No full agressivo, noticia vermelha so deve vetar se for diretamente destrutiva para o ativo "
            "ou se vier junto de liquidez/spread/volatilidade ruins."
        )
    else:
        critic_rule = "Se houver risco relevante, vete."
    system = (
        f"Voce e o critico de risco. Tente vetar entradas ruins em {market_scope}. "
        f"Perfil operacional paper: {profile['label']}. {profile['critic_prompt']} "
        "Responda SOMENTE JSON valido."
    )
    recovery_context = candidate.get("recovery_context") or {}
    recovery_stage = int(recovery_context.get("stage") or 0)
    recovery_same_symbol = recovery_stage > 0 and str(recovery_context.get("last_symbol") or "") == str(candidate.get("symbol") or "")
    recovery_guidance = {
        "scope": "same_symbol" if recovery_same_symbol else ("cross_symbol" if recovery_stage > 0 else "none"),
        "rule": (
            "vete repeticao se mesmo ativo + mesma direcao + exaustao"
            if recovery_same_symbol
            else (
                "outro ativo: critique o setup atual, nao puna automaticamente por repetir CALL/PUT do ativo anterior"
                if recovery_stage > 0
                else "sem recuperacao ativa"
            )
        ),
    }
    payload = {
        "risk_profile": {
            "key": profile["key"],
            "label": profile["label"],
            "description": profile["description"],
        },
        "candidate": _compact_candidate(candidate),
        "decision": decision,
        "recovery_context": {
            "stage": recovery_context.get("stage"),
            "last_symbol": recovery_context.get("last_symbol"),
            "last_side": recovery_context.get("last_side"),
            "loss_total": recovery_context.get("loss_total"),
            "next_amount": recovery_context.get("next_amount"),
        },
        "recovery_guidance": recovery_guidance,
        "learning_context": _compact_learning_context(candidate.get("learning_context") or {}),
        "learning_adjustment": candidate.get("learning_adjustment") or {},
        "news": (
            {
                "risk_hint": {
                    "level": "neutral",
                    "reason": "feed de noticias cripto ignorado para OTC demo da IQ",
                },
                "headlines": [],
            }
            if is_binary
            else news or {}
        ),
    }
    user = (
        "Procure falhas, armadilhas, RSI esticado, volatilidade ruim, liquidez fraca, noticia de risco e RR falso. "
        "Leve em conta learning_context e learning_adjustment: eles representam erros recentes e penalidades do codigo. "
        "Se recovery_guidance.scope for same_symbol e a decisao repetir a direcao do ultimo loss enquanto code_context apontar exaustao, prefira vetar ou WAIT. "
        "Se recovery_guidance.scope for cross_symbol, nao vete apenas por repetir CALL/PUT do ativo anterior; critique o setup atual. "
        "Para operacoes binarias demo, tambem diga qual direcao voce preferiria agora: CALL, PUT ou WAIT. "
        f"{critic_rule} Retorne JSON exatamente assim: "
        '{"veto":false,"risk_level":"green|yellow|red","preferred_decision":"WAIT|CALL|PUT","reason":"curto","must_wait_minutes":0}'
        f"\n\nDADOS:\n{json.dumps(payload, ensure_ascii=False)}"
    )
    return system, user


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
