#!/usr/bin/env python3
"""Catalogo incremental de modelos do proxy em perdas reais de gale.

Uso principal:
  CATALOG_MODEL="qwen3-coder-next" python scripts/catalog_proxy_model_replay.py

Sem CATALOG_MODEL, o script lista os modelos textuais do proxy e testa todos,
um por vez, imprimindo o placar de cada modelo antes de ir para o proximo.
"""

from __future__ import annotations

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
CATALOG_MODEL = os.getenv("CATALOG_MODEL", "").strip()
CATALOG_MODELS = [item.strip() for item in os.getenv("CATALOG_MODELS", "").split(",") if item.strip()]
MAX_MODELS = int(os.getenv("CATALOG_MAX_MODELS", "0") or "0")
MAX_SEQUENCES = int(os.getenv("CATALOG_MAX_SEQUENCES", "8") or "8")
TIMEOUT = float(os.getenv("CATALOG_TIMEOUT", "20") or "20")
MODEL_TIMEOUT = float(os.getenv("CATALOG_MODEL_TIMEOUT", "240") or "240")
BASE_AMOUNT = float(os.getenv("CATALOG_BASE_AMOUNT", "10") or "10")
PAYOUT = float(os.getenv("CATALOG_PAYOUT", "0.85") or "0.85")
FIXTURE_PATH = os.getenv("CATALOG_FIXTURE", "").strip()
OUTPUT_DIR = Path(os.getenv("CATALOG_OUTPUT_DIR", str(DB_PATH.parent))).expanduser()


@dataclass
class ReplayPoint:
    sequence: str
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


def extract_structured(text: str) -> dict[str, Any]:
    content = (text or "").strip()
    if not content:
        return {"decision": "WAIT", "confidence": 0.0, "reasoning_summary": ""}
    try:
        parsed = extract_json(content)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    stripped = re.sub(r"<think>[\s\S]*?(?:</think>|$)", " ", content, flags=re.IGNORECASE).strip()
    if not stripped:
        stripped = content
    decision_match = re.search(r"\b(CALL|PUT|WAIT)\b", stripped, flags=re.IGNORECASE)
    if not decision_match:
        if re.search(r"\b(AVOID|REJECT|SKIP|NO[_ -]?TRADE)\b", stripped, flags=re.IGNORECASE):
            decision_match = re.search(r"WAIT", "WAIT")
    confidence_match = re.search(r"confidence[^0-9]*([01](?:\.\d+)?|\d{1,3}(?:\.\d+)?)", stripped, flags=re.IGNORECASE)
    confidence = 0.0
    if confidence_match:
        try:
            confidence = float(confidence_match.group(1))
            if confidence > 1:
                confidence = min(1.0, confidence / 100.0)
        except Exception:
            confidence = 0.0
    return {
        "decision": decision_match.group(1).upper() if decision_match else "WAIT",
        "confidence": confidence,
        "reasoning_summary": stripped[:240],
        "risk_flags": ["fallback_parse"],
    }


def normalize_decision(value: Any) -> str:
    text = str(value or "WAIT").upper().strip()
    if text in {"CALL", "BUY", "LONG", "ENTER_LONG", "ACIMA"}:
        return "CALL"
    if text in {"PUT", "SELL", "SHORT", "ENTER_SHORT", "ABAIXO"}:
        return "PUT"
    return "WAIT"


def is_text_model(name: str) -> bool:
    lower = name.lower()
    blocked = [
        "flux",
        "stable-diffusion",
        "sdxl",
        "sd3",
        "image",
        "whisper",
        "tts",
        "asr",
        "parakeet",
        "magpie",
        "canary",
        "vision",
        "vl",
        "vila",
        "neva",
        "paligemma",
        "clip",
        "embed",
        "rerank",
        "guard",
    ]
    return not any(item in lower for item in blocked)


def list_proxy_models(client: httpx.Client) -> list[str]:
    response = client.get(f"{PROXY_URL}/api/tags", timeout=20)
    response.raise_for_status()
    payload = response.json()
    names = sorted(
        {item.get("name") or item.get("model") for item in payload.get("models", []) if item.get("name") or item.get("model")},
        key=lambda value: value.lower(),
    )
    return [name for name in names if is_text_model(name)]


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
    snapshot = candidate.get("snapshot") or {}
    features = candidate.get("features") or snapshot.get("features") or {}
    code_context = candidate.get("code_context") or {}
    recovery_context = candidate.get("recovery_context") or payload.get("recovery_context") or {}
    recent_feedback = candidate.get("recent_trade_feedback") or payload.get("recent_trade_feedback") or []
    learning_context = payload.get("learning_context") or {}
    return {
        "scenario": {
            "symbol": candidate.get("symbol"),
            "price": candidate.get("price"),
            "expiry_minutes": candidate.get("expiration_minutes"),
            "technical_score": candidate.get("technical_score"),
            "risk_reward": candidate.get("risk_reward"),
            "suggested_action": candidate.get("action"),
        },
        "features": {
            "trend_1s": features.get("trend_1s"),
            "trend_1m": features.get("trend_1m"),
            "trend_5m": features.get("trend_5m"),
            "rsi_1s": features.get("rsi_1s"),
            "rsi_1m": features.get("rsi_1m"),
            "rsi_5m": features.get("rsi_5m"),
            "change_1s_5": features.get("change_1s_5"),
            "change_1m_15": features.get("change_1m_15"),
            "change_5m_15": features.get("change_5m_15"),
        },
        "code_context": {
            "preferred_direction": code_context.get("preferred_direction"),
            "up_count": code_context.get("up_count"),
            "down_count": code_context.get("down_count"),
            "put_exhaustion_risk": code_context.get("put_exhaustion_risk"),
            "call_exhaustion_risk": code_context.get("call_exhaustion_risk"),
        },
        "recovery": {
            "stage": recovery_context.get("stage"),
            "loss_total": recovery_context.get("loss_total"),
            "last_side": recovery_context.get("last_side"),
            "same_symbol": recovery_context.get("last_symbol") == candidate.get("symbol"),
        },
        "recent_feedback": [
            f"{item.get('symbol')} {item.get('side')} g{item.get('gale_stage')} pnl={item.get('pnl')}"
            for item in recent_feedback[:2]
            if isinstance(item, dict)
        ],
        "learning": {
            "avoid_patterns": len(learning_context.get("active_avoid_patterns") or []),
            "last_summary": ((learning_context.get("last_reflection") or {}).get("summary") or "")[:120],
        },
    }


def parse_metadata(raw: str) -> dict[str, Any]:
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}


def discover_sequences(conn: sqlite3.Connection) -> list[list[int]]:
    explicit = os.getenv("CATALOG_SEQUENCES", "").strip()
    if explicit:
        sequences: list[list[int]] = []
        for chunk in explicit.split(","):
            if "-" in chunk:
                start, end = [int(x.strip()) for x in chunk.split("-", 1)]
                sequences.append(list(range(start, end + 1)))
            else:
                sequences.append([int(chunk.strip())])
        return sequences

    rows = conn.execute(
        "SELECT id, metadata_json, pnl_brl, status FROM trades WHERE status='CLOSED' ORDER BY id DESC LIMIT 240"
    ).fetchall()
    sequences = []
    seen = set()
    for row in rows:
        meta = parse_metadata(row["metadata_json"])
        if int(meta.get("gale_stage") or 0) != 2 or float(row["pnl_brl"] or 0) >= 0:
            continue
        trade_id = int(row["id"])
        ids = [trade_id - 2, trade_id - 1, trade_id]
        key = tuple(ids)
        if key in seen:
            continue
        prev = conn.execute(
            "SELECT id, metadata_json, status FROM trades WHERE id IN (?, ?, ?) ORDER BY id",
            ids,
        ).fetchall()
        if len(prev) != 3:
            continue
        stages = [int(parse_metadata(item["metadata_json"]).get("gale_stage") or 0) for item in prev]
        if stages == [0, 1, 2]:
            sequences.append(ids)
            seen.add(key)
        if len(sequences) >= MAX_SEQUENCES:
            break
    return list(reversed(sequences))


def load_points() -> list[ReplayPoint]:
    if FIXTURE_PATH:
        payload = json.loads(Path(FIXTURE_PATH).read_text(encoding="utf-8"))
        return [
            ReplayPoint(
                sequence=str(item["sequence"]),
                trade_id=int(item["trade_id"]),
                opened_at=float(item.get("opened_at") or 0),
                symbol=str(item["symbol"]),
                actual_side=normalize_decision(item.get("actual_side")),
                actual_win=bool(item.get("actual_win")),
                amount=float(item.get("amount") or BASE_AMOUNT),
                analysis_id=int(item.get("analysis_id") or 0),
                system_prompt=str(item.get("system_prompt") or ""),
                user_prompt=str(item.get("user_prompt") or ""),
                market_payload=item.get("market_payload") or {},
            )
            for item in payload.get("points", [])
        ]

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    sequences = discover_sequences(conn)
    points: list[ReplayPoint] = []
    for seq in sequences:
        rows = conn.execute(
            f"SELECT * FROM trades WHERE id IN ({','.join('?' for _ in seq)}) ORDER BY id",
            seq,
        ).fetchall()
        label = f"{seq[0]}-{seq[-1]}"
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
                    sequence=label,
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


def call_model(client: httpx.Client, model: str, point: ReplayPoint, timeout: float = TIMEOUT) -> dict[str, Any]:
    started = time.perf_counter()
    snapshot_for_model: Any = compact_payload(point.market_payload) if point.market_payload else {
        "raw_prompt_excerpt": point.user_prompt[:5500],
        "note": "Prompt salvo estava truncado; use apenas o trecho visivel.",
    }
    user = {
        "task": "REPLAY_WHAT_IF_IQ_OPTION_DEMO",
        "instruction": (
            "Avalie esta entrada historica sem saber o futuro. Use apenas os dados fornecidos. "
            "Expiracao de 1 minuto exige timing limpo. Se houver ambiguidade, exaustao, atraso ou estiramento, prefira WAIT. "
            "Responda em JSON de uma linha."
        ),
        "output_schema": {
            "decision": "WAIT|CALL|PUT",
            "confidence": "0..1",
            "reasoning_summary": "frase curta, sem markdown",
            "risk_flags": [],
        },
        "market_snapshot": snapshot_for_model,
    }
    response = client.post(
        f"{PROXY_URL}/api/chat",
        json={
            "model": model,
            "stream": False,
            "messages": [
                {
                    "role": "system",
                    "content": "Voce audita entradas binarias de 1 minuto. Seja curto e conservador no timing. Primeira saida deve ser JSON de uma linha.",
                },
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            "options": {"temperature": 0.02, "num_ctx": 1536, "num_predict": 160},
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    content = (payload.get("message") or {}).get("content") or payload.get("response") or ""
    parsed = extract_structured(content)
    try:
        confidence = float(parsed.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "trade_id": point.trade_id,
        "sequence": point.sequence,
        "decision": normalize_decision(parsed.get("decision")),
        "confidence": confidence,
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "summary": str(parsed.get("reasoning_summary") or parsed.get("reason") or "")[:360],
        "status": response.status_code,
    }


def outcome_for(point: ReplayPoint, decision: str) -> str:
    if decision not in {"CALL", "PUT"}:
        return "WAIT"
    if decision == point.actual_side:
        return "WIN" if point.actual_win else "LOSS"
    return "LOSS" if point.actual_win else "WIN"


def amount_for_stage(stage: int) -> float:
    if stage <= 0:
        return BASE_AMOUNT
    if stage == 1:
        return round((BASE_AMOUNT * 2) / PAYOUT, 2)
    return round(amount_for_stage(1) * 2.35, 2)


def simulate(points: list[ReplayPoint], calls: list[dict[str, Any]]) -> dict[str, Any]:
    call_map = {item["trade_id"]: item["decision"] for item in calls}
    totals: dict[str, Any] = {"pnl": 0.0, "wins": 0, "losses": 0, "wait": 0, "trades": 0, "paths": {}}
    by_sequence: dict[str, list[ReplayPoint]] = {}
    for point in points:
        by_sequence.setdefault(point.sequence, []).append(point)
    for label, seq_points in by_sequence.items():
        stage = 0
        path = []
        for point in seq_points:
            decision = normalize_decision(call_map.get(point.trade_id))
            outcome = outcome_for(point, decision)
            amount = amount_for_stage(stage)
            pnl = 0.0
            if outcome == "WAIT":
                totals["wait"] += 1
            elif outcome == "WIN":
                totals["wins"] += 1
                totals["trades"] += 1
                pnl = round(amount * PAYOUT, 2)
                totals["pnl"] += pnl
                stage = 0
            else:
                totals["losses"] += 1
                totals["trades"] += 1
                pnl = -amount
                totals["pnl"] += pnl
                stage = stage + 1 if stage < 2 else 0
            path.append({"trade_id": point.trade_id, "decision": decision, "outcome": outcome, "pnl": pnl})
        totals["paths"][label] = path
    totals["pnl"] = round(float(totals["pnl"]), 2)
    return totals


def main() -> None:
    print(f"DB={DB_PATH}")
    points = load_points()
    if not points:
        raise SystemExit("Nenhuma sequencia de gale 2 perdida encontrada.")
    sequences = sorted({point.sequence for point in points})
    print(f"Sequencias={', '.join(sequences)} pontos={len(points)}", flush=True)
    with httpx.Client(headers={"User-Agent": "RED-Trader-Model-Catalog/1.0"}) as client:
        if CATALOG_MODEL:
            models = [CATALOG_MODEL]
        elif CATALOG_MODELS:
            models = CATALOG_MODELS
        else:
            models = list_proxy_models(client)
        if MAX_MODELS > 0:
            models = models[:MAX_MODELS]
        print(f"Modelos a testar={len(models)}", flush=True)
        all_results = {}
        for idx, model in enumerate(models, 1):
            print(f"\n[{idx}/{len(models)}] {model}", flush=True)
            model_started = time.perf_counter()
            calls = []
            invalid = 0
            for point in points:
                remaining = MODEL_TIMEOUT - (time.perf_counter() - model_started)
                if remaining <= 3:
                    invalid += 1
                    call = {
                        "trade_id": point.trade_id,
                        "sequence": point.sequence,
                        "decision": "WAIT",
                        "confidence": 0.0,
                        "latency_ms": None,
                        "status": "model_timeout",
                        "summary": f"modelo excedeu {MODEL_TIMEOUT:.0f}s no total",
                    }
                    calls.append(call)
                    print(f"  {point.sequence} #{point.trade_id}: TIMEOUT_MODELO -> WAIT", flush=True)
                    continue
                try:
                    call = call_model(client, model, point, timeout=min(TIMEOUT, max(3.0, remaining)))
                except Exception as exc:
                    invalid += 1
                    call = {
                        "trade_id": point.trade_id,
                        "sequence": point.sequence,
                        "decision": "WAIT",
                        "confidence": 0.0,
                        "latency_ms": None,
                        "status": "error",
                        "summary": repr(exc)[:300],
                    }
                calls.append(call)
                outcome = outcome_for(point, call["decision"])
                print(
                    f"  {point.sequence} #{point.trade_id}: {call['decision']} -> {outcome} "
                    f"conf={call['confidence']} lat={call['latency_ms']} status={call['status']} :: {call['summary'][:120]}",
                    flush=True,
                )
            sim = simulate(points, calls)
            sim["invalid"] = invalid
            sim["avg_latency_ms"] = round(
                sum(item["latency_ms"] or 0 for item in calls if item.get("latency_ms")) / max(1, sum(1 for item in calls if item.get("latency_ms"))),
                1,
            )
            sim["calls"] = calls
            all_results[model] = sim
            print(
                f"  RESULTADO {model}: pnl={sim['pnl']} wins={sim['wins']} losses={sim['losses']} "
                f"wait={sim['wait']} invalid={invalid} avg_latency={sim['avg_latency_ms']}ms",
                flush=True,
            )

    ranking = sorted(all_results.items(), key=lambda item: (item[1]["pnl"], item[1]["wins"], -item[1]["losses"], -item[1]["invalid"]), reverse=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output = OUTPUT_DIR / f"catalog_proxy_model_replay_{int(time.time())}.json"
    output.write_text(json.dumps({"created_at": time.time(), "sequences": sequences, "results": all_results, "ranking": [name for name, _ in ranking]}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nTOP 10:")
    for name, result in ranking[:10]:
        print(f"- {name}: pnl={result['pnl']} wins={result['wins']} losses={result['losses']} wait={result['wait']} invalid={result['invalid']} avg_latency={result['avg_latency_ms']}ms")
    print(f"Relatorio={output}")


if __name__ == "__main__":
    main()
