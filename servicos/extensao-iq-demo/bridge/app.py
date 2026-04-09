from __future__ import annotations

import json
import os
import sqlite3
import time
import base64
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
FRAMES_DIR = DATA_DIR / "frames"
FRAMES_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.getenv("RED_IQ_BRIDGE_DB_PATH", str(DATA_DIR / "iq_vision_bridge.sqlite"))).expanduser()
AUTH_TOKEN = os.getenv("RED_IQ_BRIDGE_TOKEN", "").strip()
CORS_RAW = os.getenv("RED_IQ_BRIDGE_CORS", "*").strip()
ALLOWED_ORIGINS = [item.strip() for item in CORS_RAW.split(",") if item.strip()] or ["*"]


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                received_at REAL NOT NULL,
                session_id TEXT NOT NULL,
                tab_id INTEGER,
                title TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL DEFAULT '',
                asset TEXT NOT NULL DEFAULT '',
                market_type TEXT NOT NULL DEFAULT '',
                mode TEXT NOT NULL DEFAULT '',
                payout_pct REAL,
                current_price REAL,
                countdown TEXT NOT NULL DEFAULT '',
                tick_age_ms REAL,
                buy_window_open INTEGER NOT NULL DEFAULT 0,
                suspended_hint INTEGER NOT NULL DEFAULT 0,
                payload_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS idx_telemetry_ts ON telemetry(ts DESC);
            CREATE INDEX IF NOT EXISTS idx_telemetry_asset ON telemetry(asset);
            CREATE INDEX IF NOT EXISTS idx_telemetry_session ON telemetry(session_id, ts DESC);

            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                level TEXT NOT NULL DEFAULT 'info',
                event TEXT NOT NULL DEFAULT '',
                session_id TEXT NOT NULL DEFAULT '',
                asset TEXT NOT NULL DEFAULT '',
                message TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS idx_logs_ts ON logs(ts DESC);

            CREATE TABLE IF NOT EXISTS commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at REAL NOT NULL,
                session_id TEXT NOT NULL DEFAULT '',
                command TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'pending',
                claimed_at REAL,
                acked_at REAL,
                result_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS idx_commands_status ON commands(status, created_at);

            CREATE TABLE IF NOT EXISTS frames (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                received_at REAL NOT NULL,
                session_id TEXT NOT NULL,
                tab_id INTEGER,
                title TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL DEFAULT '',
                asset TEXT NOT NULL DEFAULT '',
                market_type TEXT NOT NULL DEFAULT '',
                mode TEXT NOT NULL DEFAULT '',
                payout_pct REAL,
                countdown TEXT NOT NULL DEFAULT '',
                width INTEGER,
                height INTEGER,
                image_path TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS idx_frames_ts ON frames(ts DESC);
            """
        )


class PulsePayload(BaseModel):
    slope: float | int | None = 0
    volatility: float | int | None = 0
    impulse: str | None = ""
    direction: str | None = ""


class TelemetryPayload(BaseModel):
    mode: str = "unknown"
    demoAllowed: bool = False
    asset: str = "-"
    marketType: str = "-"
    payoutPct: float | None = None
    countdown: str = "-"
    currentPrice: float | None = None
    tickAgeMs: float | None = None
    buyWindowOpen: bool | None = None
    suspendedHint: bool = False
    entryHint: str = ""
    notes: list[str] = Field(default_factory=list)
    updatedAt: float | int | None = None
    pulse: PulsePayload | dict[str, Any] | None = None
    ticks: list[dict[str, Any]] = Field(default_factory=list)
    pageTitle: str = ""
    href: str = ""
    domFreshnessMs: float | int | None = None
    debug: dict[str, Any] = Field(default_factory=dict)


class TelemetryEnvelope(BaseModel):
    tabId: int | None = None
    title: str = ""
    url: str = ""
    receivedAt: float | int | None = None
    state: TelemetryPayload


class LogPayload(BaseModel):
    level: str = "info"
    event: str = ""
    message: str = ""
    sessionId: str = ""
    asset: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class LogsEnvelope(BaseModel):
    items: list[LogPayload] = Field(default_factory=list)


class CommandPayload(BaseModel):
    sessionId: str = ""
    command: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class CommandAckPayload(BaseModel):
    ok: bool = False
    result: dict[str, Any] = Field(default_factory=dict)


class FrameCanvasPayload(BaseModel):
    id: str = ""
    className: str = ""
    width: int | None = None
    height: int | None = None


class FramePayload(BaseModel):
    asset: str = "-"
    marketType: str = "-"
    mode: str = "unknown"
    payoutPct: float | None = None
    countdown: str = "-"
    canvas: FrameCanvasPayload | dict[str, Any] | None = None
    imageDataUrl: str


class FrameEnvelope(BaseModel):
    tabId: int | None = None
    title: str = ""
    url: str = ""
    receivedAt: float | int | None = None
    frame: FramePayload


app = FastAPI(title="RED IQ Demo Vision Bridge", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()


def require_token(provided: str | None) -> None:
    if AUTH_TOKEN and (provided or "").strip() != AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="invalid_token")


def session_id_from_request(request: Request) -> str:
    return (
        request.headers.get("x-red-session")
        or request.headers.get("x-session-id")
        or request.headers.get("origin")
        or "anonymous"
    )


def safe_session_dir(session_id: str) -> Path:
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "_", session_id).strip("._") or "anonymous"
    target = FRAMES_DIR / slug
    target.mkdir(parents=True, exist_ok=True)
    return target


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    with _db() as conn:
        last = conn.execute("SELECT MAX(ts) AS ts FROM telemetry").fetchone()
    return {
        "ok": True,
        "db_path": str(DB_PATH),
        "last_telemetry_ts": last["ts"] if last else None,
        "auth_enabled": bool(AUTH_TOKEN),
    }


@app.post("/api/telemetry")
async def ingest_telemetry(
    envelope: TelemetryEnvelope,
    request: Request,
    x_red_token: str | None = Header(default=None),
) -> dict[str, Any]:
    require_token(x_red_token)
    session_id = session_id_from_request(request)
    payload = envelope.state.model_dump()
    ts = float(payload.get("updatedAt") or time.time() * 1000) / 1000.0
    received_at = time.time()
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO telemetry (
                ts, received_at, session_id, tab_id, title, url, asset, market_type, mode,
                payout_pct, current_price, countdown, tick_age_ms, buy_window_open,
                suspended_hint, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                received_at,
                session_id,
                envelope.tabId,
                envelope.title or payload.get("pageTitle") or "",
                envelope.url or payload.get("href") or "",
                payload.get("asset") or "",
                payload.get("marketType") or "",
                payload.get("mode") or "unknown",
                payload.get("payoutPct"),
                payload.get("currentPrice"),
                payload.get("countdown") or "",
                payload.get("tickAgeMs"),
                1 if payload.get("buyWindowOpen") else 0,
                1 if payload.get("suspendedHint") else 0,
                json.dumps(payload, ensure_ascii=False),
            ),
        )
    return {"ok": True, "session_id": session_id}


@app.post("/api/log")
async def ingest_log(
    item: LogPayload,
    request: Request,
    x_red_token: str | None = Header(default=None),
) -> dict[str, Any]:
    require_token(x_red_token)
    session_id = item.sessionId or session_id_from_request(request)
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO logs (ts, level, event, session_id, asset, message, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                time.time(),
                item.level,
                item.event,
                session_id,
                item.asset,
                item.message,
                json.dumps(item.payload, ensure_ascii=False),
            ),
        )
    return {"ok": True}


@app.post("/api/logs")
async def ingest_logs(
    envelope: LogsEnvelope,
    request: Request,
    x_red_token: str | None = Header(default=None),
) -> dict[str, Any]:
    require_token(x_red_token)
    session_id = session_id_from_request(request)
    rows = []
    for item in envelope.items:
        rows.append(
            (
                time.time(),
                item.level,
                item.event,
                item.sessionId or session_id,
                item.asset,
                item.message,
                json.dumps(item.payload, ensure_ascii=False),
            )
        )
    if rows:
        with _db() as conn:
            conn.executemany(
                """
                INSERT INTO logs (ts, level, event, session_id, asset, message, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
    return {"ok": True, "count": len(rows)}


@app.post("/api/commands")
async def create_command(
    item: CommandPayload,
    request: Request,
    x_red_token: str | None = Header(default=None),
) -> dict[str, Any]:
    require_token(x_red_token)
    session_id = item.sessionId or session_id_from_request(request)
    with _db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO commands (created_at, session_id, command, payload_json, status)
            VALUES (?, ?, ?, ?, 'pending')
            """,
            (
                time.time(),
                session_id,
                item.command,
                json.dumps(item.payload, ensure_ascii=False),
            ),
        )
    return {"ok": True, "id": cursor.lastrowid}


@app.get("/api/commands/pull")
def pull_commands(
    request: Request,
    x_red_token: str | None = Header(default=None),
) -> dict[str, Any]:
    require_token(x_red_token)
    session_id = session_id_from_request(request)
    with _db() as conn:
        rows = conn.execute(
            """
            SELECT id, created_at, session_id, command, payload_json
            FROM commands
            WHERE status='pending' AND session_id=?
            ORDER BY id ASC
            LIMIT 20
            """,
            (session_id,),
        ).fetchall()
        ids = [row["id"] for row in rows]
        if ids:
            conn.executemany(
                "UPDATE commands SET status='claimed', claimed_at=? WHERE id=?",
                [(time.time(), item_id) for item_id in ids],
            )
    items = []
    for row in rows:
        items.append(
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "session_id": row["session_id"],
                "command": row["command"],
                "payload": json.loads(row["payload_json"] or "{}"),
            }
        )
    return {"ok": True, "items": items}


@app.post("/api/commands/{command_id}/ack")
async def ack_command(
    command_id: int,
    item: CommandAckPayload,
    request: Request,
    x_red_token: str | None = Header(default=None),
) -> dict[str, Any]:
    require_token(x_red_token)
    session_id = session_id_from_request(request)
    with _db() as conn:
        conn.execute(
            """
            UPDATE commands
            SET status=?, acked_at=?, result_json=?
            WHERE id=? AND session_id=?
            """,
            (
                "done" if item.ok else "failed",
                time.time(),
                json.dumps(item.result, ensure_ascii=False),
                command_id,
                session_id,
            ),
        )
    return {"ok": True}


@app.get("/api/commands")
def list_commands(limit: int = 50) -> dict[str, Any]:
    limit = max(1, min(200, int(limit or 50)))
    with _db() as conn:
        rows = conn.execute(
            """
            SELECT id, created_at, session_id, command, status, claimed_at, acked_at, payload_json, result_json
            FROM commands
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    items = []
    for row in rows:
        items.append(
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "session_id": row["session_id"],
                "command": row["command"],
                "status": row["status"],
                "claimed_at": row["claimed_at"],
                "acked_at": row["acked_at"],
                "payload": json.loads(row["payload_json"] or "{}"),
                "result": json.loads(row["result_json"] or "{}"),
            }
        )
    return {"ok": True, "items": items}


@app.post("/api/frame")
async def ingest_frame(
    envelope: FrameEnvelope,
    request: Request,
    x_red_token: str | None = Header(default=None),
) -> dict[str, Any]:
    require_token(x_red_token)
    session_id = session_id_from_request(request)
    frame = envelope.frame.model_dump()
    data_url = frame.get("imageDataUrl") or ""
    if not data_url.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="invalid_image")

    header, _, encoded = data_url.partition(",")
    if not encoded:
        raise HTTPException(status_code=400, detail="invalid_image_data")

    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid_base64") from exc

    ts_ms = float(envelope.receivedAt or time.time() * 1000)
    ts = ts_ms / 1000.0
    filename = f"{int(ts_ms)}.jpg"
    target_dir = safe_session_dir(session_id)
    target_path = target_dir / filename
    target_path.write_bytes(image_bytes)

    canvas = frame.get("canvas") or {}
    with _db() as conn:
      conn.execute(
          """
          INSERT INTO frames (
              ts, received_at, session_id, tab_id, title, url, asset, market_type, mode,
              payout_pct, countdown, width, height, image_path, payload_json
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
          """,
          (
              ts,
              time.time(),
              session_id,
              envelope.tabId,
              envelope.title or "",
              envelope.url or "",
              frame.get("asset") or "",
              frame.get("marketType") or "",
              frame.get("mode") or "unknown",
              frame.get("payoutPct"),
              frame.get("countdown") or "",
              canvas.get("width"),
              canvas.get("height"),
              str(target_path),
              json.dumps(frame, ensure_ascii=False),
          ),
      )
    return {"ok": True, "image_path": str(target_path)}


@app.get("/api/latest")
def latest(limit: int = 50) -> dict[str, Any]:
    limit = max(1, min(500, int(limit or 50)))
    with _db() as conn:
        rows = conn.execute(
            """
            SELECT id, ts, received_at, session_id, tab_id, title, url, asset, market_type, mode,
                   payout_pct, current_price, countdown, tick_age_ms, buy_window_open,
                   suspended_hint, payload_json
            FROM telemetry
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    items = []
    for row in rows:
      item = dict(row)
      try:
          item["payload"] = json.loads(item.pop("payload_json"))
      except Exception:
          item["payload"] = {}
      items.append(item)
    return {"ok": True, "items": items}


@app.get("/api/telemetry/recent")
def telemetry_recent(limit: int = 50, asset: str = "", session_id: str = "") -> dict[str, Any]:
    limit = max(1, min(500, int(limit or 50)))
    clauses: list[str] = []
    params: list[Any] = []
    if asset:
        clauses.append("asset LIKE ?")
        params.append(f"%{asset}%")
    if session_id:
        clauses.append("session_id = ?")
        params.append(session_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _db() as conn:
        rows = conn.execute(
            f"""
            SELECT id, ts, received_at, session_id, tab_id, title, url, asset, market_type, mode,
                   payout_pct, current_price, countdown, tick_age_ms, buy_window_open,
                   suspended_hint, payload_json
            FROM telemetry
            {where}
            ORDER BY id DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        try:
            item["payload"] = json.loads(item.pop("payload_json"))
        except Exception:
            item["payload"] = {}
        items.append(item)
    return {"ok": True, "items": items}


@app.get("/api/logs/recent")
def logs_recent(limit: int = 100, event: str = "", contains: str = "", asset: str = "", session_id: str = "") -> dict[str, Any]:
    limit = max(1, min(1000, int(limit or 100)))
    clauses: list[str] = []
    params: list[Any] = []
    if event:
        clauses.append("event LIKE ?")
        params.append(f"%{event}%")
    if contains:
        clauses.append("(payload_json LIKE ? OR message LIKE ?)")
        params.extend([f"%{contains}%", f"%{contains}%"])
    if asset:
        clauses.append("asset LIKE ?")
        params.append(f"%{asset}%")
    if session_id:
        clauses.append("session_id = ?")
        params.append(session_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _db() as conn:
        rows = conn.execute(
            f"""
            SELECT id, ts, level, event, session_id, asset, message, payload_json
            FROM logs
            {where}
            ORDER BY id DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        try:
            item["payload"] = json.loads(item.pop("payload_json"))
        except Exception:
            item["payload"] = {}
        items.append(item)
    return {"ok": True, "items": items}


@app.get("/api/summary")
def summary() -> dict[str, Any]:
    with _db() as conn:
        last = conn.execute(
            """
            SELECT id, ts, session_id, asset, market_type, mode, buy_window_open,
                   suspended_hint, tick_age_ms, payload_json
            FROM telemetry
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        totals = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN mode='demo' THEN 1 ELSE 0 END) AS demo_reads,
                SUM(CASE WHEN suspended_hint=1 THEN 1 ELSE 0 END) AS suspended_reads,
                SUM(CASE WHEN buy_window_open=1 THEN 1 ELSE 0 END) AS buy_window_open_reads
            FROM telemetry
            """
        ).fetchone()
        asset_counts = conn.execute(
            """
            SELECT asset, COUNT(*) AS total
            FROM telemetry
            WHERE asset != ''
            GROUP BY asset
            ORDER BY total DESC
            LIMIT 8
            """
        ).fetchall()
    last_payload = {}
    if last:
        try:
            last_payload = json.loads(last["payload_json"])
        except Exception:
            last_payload = {}
    return {
        "ok": True,
        "totals": dict(totals) if totals else {},
        "top_assets": [dict(row) for row in asset_counts],
        "latest": {
            "id": last["id"],
            "ts": last["ts"],
            "session_id": last["session_id"],
            "asset": last["asset"],
            "market_type": last["market_type"],
            "mode": last["mode"],
            "buy_window_open": bool(last["buy_window_open"]),
            "suspended_hint": bool(last["suspended_hint"]),
            "tick_age_ms": last["tick_age_ms"],
            "payload": last_payload,
        } if last else None,
    }


@app.get("/api/latest-frame")
def latest_frame() -> dict[str, Any]:
    with _db() as conn:
        row = conn.execute(
            """
            SELECT id, ts, session_id, tab_id, title, url, asset, market_type, mode,
                   payout_pct, countdown, width, height, image_path, payload_json
            FROM frames
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
    if not row:
        return {"ok": True, "item": None}
    item = dict(row)
    try:
        item["payload"] = json.loads(item.pop("payload_json"))
    except Exception:
        item["payload"] = {}
    return {"ok": True, "item": item}
