#!/usr/bin/env python3
"""Replay what-if para a sequência de gale 2 da IQ Option demo.

O script reaproveita os prompts salvos em `analyses.prompt_json` perto das
operações reais e pergunta a outros modelos o que eles teriam feito naquele
mesmo ponto. Não usa futuro no prompt; o futuro só entra depois para pontuar
CALL/PUT/WAIT contra o resultado real daquela expiração.
"""

from __future__ import annotations

import itertools
import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


DB_PATH = Path(os.getenv("REDTRADER_DB_PATH", "/opt/redtrader/data/redtrader.sqlite"))
PROXY_URL = os.getenv("REDSYSTEMS_PROXY_URL", "http://redsystems.ddns.net:8080").rstrip("/")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
START_TRADE_ID = int(os.getenv("GALE_BENCH_START", "90"))
END_TRADE_ID = int(os.getenv("GALE_BENCH_END", "94"))
BASE_AMOUNT = float(os.getenv("GALE_BENCH_BASE_AMOUNT", "10"))
PAYOUT = float(os.getenv("GALE_BENCH_PAYOUT", "0.85"))
TIMEOUT = float(os.getenv("GALE_BENCH_TIMEOUT", "55"))

DESIRED_MODELS = [
    "qwen/qwen3-next-80b-a3b-instruct (NVIDIA)",
    "openai/gpt-oss-20b (NVIDIA)",
    "openai/gpt-oss-120b (NVIDIA)",
    "meta/llama-4-maverick-17b-128e-instruct (NVIDIA)",
    "mistralai/devstral-2-123b-instruct-2512 (NVIDIA)",
    "mistralai/mistral-small-4-119b-2603 (NVIDIA)",
    "nvidia/nemotron-3-nano-30b-a3b (NVIDIA)",
    "qwen/qwen3-coder-480b-a35b-instruct (NVIDIA)",
    "qwen3-next:80b",
    "qwen3-coder-next",
    "gpt-oss:20b",
    "gpt-oss:120b",
    "devstral-small-2:24b",
    "nemotron-3-nano:30b",
    "gemma3:4b",
    "ministral-3:14b",
]
if os.getenv("GALE_BENCH_MODELS"):
    DESIRED_MODELS = [item.strip() for item in os.getenv("GALE_BENCH_MODELS", "").split(",") if item.strip()]
EXPLICIT_MODELS = bool(os.getenv("GALE_BENCH_MODELS"))


@dataclass
class ReplayPoint:
    trade_id: int
    opened_at: float
    symbol: str
    actual_side: str
    actual_win: bool
    amount: float
    analysis_id: int
    system_prompt: str
    user_prompt: str
    market_payload: dict[str, Any]


def extract_json(text: str) -> dict[str, Any]:
    clean = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", clean, flags=re.IGNORECASE)
    if fenced:
        clean = fenced.group(1).strip()
    start = clean.find("{")
    end = clean.rfind("}")
    if start >= 0 and end > start:
        clean = clean[start : end + 1]
    return json.loads(clean)


def normalize_decision(value: Any) -> str:
    text = str(value or "WAIT").upper().strip()
    if text in {"CALL", "BUY", "LONG", "ENTER_LONG", "ACIMA"}:
        return "CALL"
    if text in {"PUT", "SELL", "SHORT", "ENTER_SHORT", "ABAIXO"}:
        return "PUT"
    return "WAIT"


def extract_market_payload(user_prompt: str) -> dict[str, Any]:
    marker = "DADOS:"
    if marker not in user_prompt:
        return {}
    raw = user_prompt.split(marker, 1)[1].strip()
    try:
        payload, _ = json.JSONDecoder().raw_decode(raw)
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        return {}


def compact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    candidate = payload.get("candidate") or {}
    snapshot = candidate.get("snapshot") or payload.get("snapshot") or {}
    features = candidate.get("features") or snapshot.get("features") or {}
    keep_features = [
        "last_price",
        "trend_1m",
        "trend_5m",
        "trend_15m",
        "rsi_1m",
        "rsi_5m",
        "rsi_15m",
        "change_1m_15",
        "change_5m_15",
        "change_15m_15",
        "ret_std_1m_30",
        "ret_std_5m_30",
        "volume_1m_vs_avg30",
        "volume_5m_vs_avg30",
        "spread_pct",
        "bid_ask_ratio",
    ]
    return {
        "mode": payload.get("mode", "iqoption_demo_binary_only"),
        "risk_profile": payload.get("risk_profile"),
        "constraints": payload.get("constraints"),
        "candidate": {
            "symbol": candidate.get("symbol"),
            "price": candidate.get("price"),
            "technical_score": candidate.get("technical_score"),
            "checks": candidate.get("checks"),
            "trade_type": candidate.get("trade_type"),
            "suggested_action": candidate.get("action"),
            "expiration_minutes": candidate.get("expiration_minutes"),
            "risk_reward": candidate.get("risk_reward"),
            "features": {key: features.get(key) for key in keep_features if key in features},
        },
        "recovery_context": candidate.get("recovery_context") or payload.get("recovery_context"),
        "recent_trade_feedback": candidate.get("recent_trade_feedback") or payload.get("recent_trade_feedback"),
    }


def amount_for_stage(stage: int) -> float:
    if stage <= 0:
        return BASE_AMOUNT
    if stage == 1:
        return round((BASE_AMOUNT * 2) / PAYOUT, 2)
    return round(amount_for_stage(1) * 2.35, 2)


def load_points() -> list[ReplayPoint]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT * FROM trades
        WHERE id BETWEEN ? AND ?
        ORDER BY id
        """,
        (START_TRADE_ID, END_TRADE_ID),
    ).fetchall()
    points: list[ReplayPoint] = []
    for trade in rows:
        analysis = conn.execute(
            """
            SELECT * FROM analyses
            WHERE symbol = ? AND role = 'decision' AND ts <= ?
            ORDER BY ts DESC
            LIMIT 1
            """,
            (trade["symbol"], trade["opened_at"]),
        ).fetchone()
        if not analysis:
            continue
        prompt = json.loads(analysis["prompt_json"] or "{}")
        market_payload = extract_market_payload(str(prompt.get("user") or ""))
        points.append(
            ReplayPoint(
                trade_id=int(trade["id"]),
                opened_at=float(trade["opened_at"]),
                symbol=str(trade["symbol"]),
                actual_side=normalize_decision(trade["side"]),
                actual_win=float(trade["pnl_brl"] or 0) > 0,
                amount=float(trade["position_brl"] or 0),
                analysis_id=int(analysis["id"]),
                system_prompt=str(prompt.get("system") or ""),
                user_prompt=str(prompt.get("user") or ""),
                market_payload=market_payload,
            )
        )
    return points


def list_available_models(client: httpx.Client) -> set[str]:
    response = client.get(f"{PROXY_URL}/api/tags", timeout=20)
    response.raise_for_status()
    payload = response.json()
    models = {item.get("name") or item.get("model") for item in payload.get("models", []) if item.get("name") or item.get("model")}
    if GROQ_API_KEY:
        groq = client.get(
            f"{GROQ_BASE_URL}/models",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            timeout=20,
        )
        groq.raise_for_status()
        for item in groq.json().get("data", []):
            if item.get("id"):
                models.add(f"{item['id']} (GROQ)")
    return models


def call_model(client: httpx.Client, model: str, point: ReplayPoint) -> dict[str, Any]:
    started = time.perf_counter()
    snapshot_for_model: Any = compact_payload(point.market_payload) if point.market_payload else {
        "raw_prompt_excerpt": point.user_prompt[:5500],
        "note": "O prompt salvo no banco foi truncado antes do JSON completo; use os dados tecnicos visiveis neste trecho.",
    }
    user = json.dumps(
        {
            "task": "REPLAY_WHAT_IF_IQ_OPTION_DEMO",
            "instruction": (
                "Voce esta avaliando uma entrada historica sem saber o futuro. "
                "Use apenas os dados em market_snapshot. Decida CALL, PUT ou WAIT. "
                "CALL ganha se o preco fechar acima; PUT ganha se fechar abaixo. "
                "Se houver sobrecompra extrema com momentum curto fraco, considere reversao PUT. "
                "Se a leitura estiver ambigua, WAIT. Responda somente JSON valido."
            ),
            "output_schema": {
                "decision": "WAIT|CALL|PUT",
                "confidence": 0,
                "reasoning_summary": "frase curta",
                "risk_flags": [],
            },
            "market_snapshot": snapshot_for_model,
        },
        ensure_ascii=False,
    )
    clean_model = model.removesuffix(" (GROQ)")
    body = {
        "model": clean_model if model.endswith(" (GROQ)") else model,
        "stream": False,
        "messages": [
            {"role": "system", "content": "Voce e um auditor quantitativo de operacoes binarias DEMO/PRACTICE. Nunca prometa lucro. Responda somente JSON valido, sem markdown."},
            {"role": "user", "content": user},
        ],
        "temperature": 0.03,
    }
    if model.endswith(" (GROQ)"):
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY ausente")
        body["max_completion_tokens"] = 650
        for attempt in range(3):
            response = client.post(
                f"{GROQ_BASE_URL}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                timeout=TIMEOUT,
            )
            if response.status_code != 429:
                break
            wait = float(response.headers.get("retry-after") or (2 + attempt * 3))
            time.sleep(min(12, wait))
    else:
        body["options"] = {"temperature": 0.03, "num_ctx": 4096, "num_predict": 650}
        body.pop("temperature", None)
        response = client.post(f"{PROXY_URL}/api/chat", json=body, timeout=TIMEOUT)
    response.raise_for_status()
    payload = response.json()
    if model.endswith(" (GROQ)"):
        choices = payload.get("choices") or []
        content = ((choices[0].get("message") or {}).get("content") if choices else "") or ""
    else:
        content = (payload.get("message") or {}).get("content") or payload.get("response") or ""
    parsed = extract_json(content)
    decision = normalize_decision(parsed.get("decision"))
    confidence = parsed.get("confidence")
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "trade_id": point.trade_id,
        "analysis_id": point.analysis_id,
        "decision": decision,
        "confidence": confidence,
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "summary": str(parsed.get("reasoning_summary") or parsed.get("reason") or "")[:420],
    }


def outcome_for(point: ReplayPoint, decision: str) -> str:
    if decision not in {"CALL", "PUT"}:
        return "WAIT"
    same = decision == point.actual_side
    if same and point.actual_win:
        return "WIN"
    if same and not point.actual_win:
        return "LOSS"
    if not same and point.actual_win:
        return "LOSS"
    return "WIN"


def simulate_sequence(points: list[ReplayPoint], decisions: dict[int, str]) -> dict[str, Any]:
    stage = 0
    pnl = 0.0
    wins = losses = skipped = trades = 0
    path = []
    for point in points:
        decision = normalize_decision(decisions.get(point.trade_id))
        outcome = outcome_for(point, decision)
        amount = amount_for_stage(stage)
        item = {"trade_id": point.trade_id, "decision": decision, "stage": stage, "amount": amount, "outcome": outcome}
        if outcome == "WAIT":
            skipped += 1
            item["pnl"] = 0.0
        elif outcome == "WIN":
            trades += 1
            wins += 1
            profit = round(amount * PAYOUT, 2)
            pnl += profit
            item["pnl"] = profit
            stage = 0
        else:
            trades += 1
            losses += 1
            pnl -= amount
            item["pnl"] = -amount
            stage = stage + 1 if stage < 2 else 0
        path.append(item)
    return {
        "pnl": round(pnl, 2),
        "wins": wins,
        "losses": losses,
        "skipped": skipped,
        "trades": trades,
        "recovered": pnl >= 0,
        "path": path,
    }


def main() -> None:
    print(f"DB: {DB_PATH}")
    points = load_points()
    if not points:
        raise SystemExit("Nenhum ponto de replay encontrado.")
    print(f"Replay: trades {points[0].trade_id}-{points[-1].trade_id}, pontos={len(points)}")
    actual = simulate_sequence(points, {point.trade_id: point.actual_side for point in points})
    print(f"Baseline real: pnl={actual['pnl']} wins={actual['wins']} losses={actual['losses']} path={[(x['trade_id'], x['decision'], x['outcome'], x['pnl']) for x in actual['path']]}")

    results: dict[str, dict[str, Any]] = {}
    with httpx.Client(headers={"User-Agent": "RED-Trader-Gale2-Benchmark/1.0"}) as client:
        if EXPLICIT_MODELS:
            models = DESIRED_MODELS
        else:
            available = list_available_models(client)
            models = [model for model in DESIRED_MODELS if model in available]
        print("Modelos:", len(models), "->", ", ".join(models), flush=True)
        for model in models:
            print(f"\n== {model}", flush=True)
            decisions: dict[int, str] = {}
            calls = []
            invalid = 0
            for point in points:
                try:
                    call = call_model(client, model, point)
                except Exception as exc:
                    invalid += 1
                    call = {
                        "trade_id": point.trade_id,
                        "analysis_id": point.analysis_id,
                        "decision": "WAIT",
                        "confidence": 0,
                        "latency_ms": None,
                        "summary": f"erro: {exc!r}"[:420],
                    }
                decisions[point.trade_id] = call["decision"]
                calls.append(call)
                print(f"  #{point.trade_id}: {call['decision']} conf={call['confidence']} lat={call['latency_ms']}ms :: {call['summary'][:120]}", flush=True)
            sim = simulate_sequence(points, decisions)
            sim["invalid"] = invalid
            sim["calls"] = calls
            results[model] = sim
            print(f"  => pnl={sim['pnl']} wins={sim['wins']} losses={sim['losses']} skipped={sim['skipped']} recovered={sim['recovered']}", flush=True)

    ensembles: dict[str, dict[str, Any]] = {}
    model_names = list(results)
    for a, b in itertools.combinations(model_names, 2):
        decisions = {}
        for point in points:
            da = next(call for call in results[a]["calls"] if call["trade_id"] == point.trade_id)["decision"]
            db = next(call for call in results[b]["calls"] if call["trade_id"] == point.trade_id)["decision"]
            decisions[point.trade_id] = da if da == db and da in {"CALL", "PUT"} else "WAIT"
        sim = simulate_sequence(points, decisions)
        if sim["trades"]:
            ensembles[f"{a} + {b}"] = sim
    for names in itertools.combinations(model_names, 3):
        decisions = {}
        for point in points:
            votes = []
            for name in names:
                votes.append(next(call for call in results[name]["calls"] if call["trade_id"] == point.trade_id)["decision"])
            call_votes = sum(1 for vote in votes if vote == "CALL")
            put_votes = sum(1 for vote in votes if vote == "PUT")
            if call_votes >= 2:
                decisions[point.trade_id] = "CALL"
            elif put_votes >= 2:
                decisions[point.trade_id] = "PUT"
            else:
                decisions[point.trade_id] = "WAIT"
        sim = simulate_sequence(points, decisions)
        if sim["trades"]:
            ensembles[" + ".join(names)] = sim

    ranked_models = sorted(results.items(), key=lambda item: (item[1]["pnl"], item[1]["wins"], -item[1]["losses"]), reverse=True)
    ranked_ensembles = sorted(ensembles.items(), key=lambda item: (item[1]["pnl"], item[1]["wins"], -item[1]["losses"]), reverse=True)
    report = {
        "created_at": time.time(),
        "proxy_url": PROXY_URL,
        "trade_range": [START_TRADE_ID, END_TRADE_ID],
        "baseline": actual,
        "results": results,
        "ensembles_top": dict(ranked_ensembles[:30]),
        "ranking_models": [{"name": name, **{k: v for k, v in sim.items() if k not in {"calls", "path"}}} for name, sim in ranked_models],
        "ranking_ensembles": [{"name": name, **{k: v for k, v in sim.items() if k != "path"}} for name, sim in ranked_ensembles[:30]],
    }
    output = Path("/opt/redtrader/data") / f"gale2_model_benchmark_{int(time.time())}.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nTOP modelos:")
    for name, sim in ranked_models[:10]:
        print(f"- {name}: pnl={sim['pnl']} wins={sim['wins']} losses={sim['losses']} skipped={sim['skipped']} invalid={sim['invalid']}")
    print("\nTOP combos agree-only:")
    for name, sim in ranked_ensembles[:10]:
        print(f"- {name}: pnl={sim['pnl']} wins={sim['wins']} losses={sim['losses']} skipped={sim['skipped']}")
    print(f"\nRelatorio: {output}")


if __name__ == "__main__":
    main()
