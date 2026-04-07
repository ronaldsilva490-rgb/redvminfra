import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.migrate()

    def migrate(self) -> None:
        with self.lock, self.conn:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS kv (
                  key TEXT PRIMARY KEY,
                  value_json TEXT NOT NULL,
                  updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS events (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  ts REAL NOT NULL,
                  type TEXT NOT NULL,
                  message TEXT NOT NULL,
                  data_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS snapshots (
                  symbol TEXT PRIMARY KEY,
                  ts REAL NOT NULL,
                  data_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS analyses (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  ts REAL NOT NULL,
                  symbol TEXT NOT NULL,
                  role TEXT NOT NULL,
                  model TEXT NOT NULL,
                  decision TEXT NOT NULL,
                  confidence REAL,
                  latency_ms INTEGER,
                  summary TEXT,
                  response_json TEXT NOT NULL,
                  prompt_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS trades (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  opened_at REAL NOT NULL,
                  closed_at REAL,
                  symbol TEXT NOT NULL,
                  side TEXT NOT NULL,
                  status TEXT NOT NULL,
                  entry_price REAL NOT NULL,
                  exit_price REAL,
                  position_brl REAL NOT NULL,
                  stop_loss_pct REAL NOT NULL,
                  take_profit_pct REAL NOT NULL,
                  pnl_brl REAL NOT NULL DEFAULT 0,
                  pnl_pct REAL NOT NULL DEFAULT 0,
                  entry_reason TEXT NOT NULL DEFAULT '',
                  exit_reason TEXT NOT NULL DEFAULT '',
                  metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts DESC);
                CREATE INDEX IF NOT EXISTS idx_analyses_ts ON analyses(ts DESC);
                CREATE INDEX IF NOT EXISTS idx_trades_opened_at ON trades(opened_at DESC);
                """
            )

    def get_kv(self, key: str, default: Any = None) -> Any:
        with self.lock:
            row = self.conn.execute("SELECT value_json FROM kv WHERE key = ?", (key,)).fetchone()
            if not row:
                return default
            try:
                return json.loads(row["value_json"])
            except json.JSONDecodeError:
                return default

    def set_kv(self, key: str, value: Any) -> None:
        payload = json.dumps(value, ensure_ascii=False)
        with self.lock, self.conn:
            self.conn.execute(
                """
                INSERT INTO kv(key, value_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at
                """,
                (key, payload, time.time()),
            )

    def add_event(self, event_type: str, message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        ts = time.time()
        payload = json.dumps(data or {}, ensure_ascii=False)
        with self.lock, self.conn:
            cur = self.conn.execute(
                "INSERT INTO events(ts, type, message, data_json) VALUES (?, ?, ?, ?)",
                (ts, event_type, message, payload),
            )
            event_id = int(cur.lastrowid)
        return {"id": event_id, "ts": ts, "type": event_type, "message": message, "data": data or {}}

    def list_events(self, limit: int = 120) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?", (int(limit),)
            ).fetchall()
        return [self._row_with_json(row, "data_json", "data") for row in reversed(rows)]

    def save_snapshot(self, symbol: str, payload: dict[str, Any]) -> None:
        with self.lock, self.conn:
            self.conn.execute(
                """
                INSERT INTO snapshots(symbol, ts, data_json)
                VALUES (?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET ts = excluded.ts, data_json = excluded.data_json
                """,
                (symbol, time.time(), json.dumps(payload, ensure_ascii=False)),
            )

    def list_snapshots(self) -> dict[str, Any]:
        with self.lock:
            rows = self.conn.execute("SELECT * FROM snapshots").fetchall()
        out = {}
        for row in rows:
            try:
                out[row["symbol"]] = json.loads(row["data_json"])
            except json.JSONDecodeError:
                out[row["symbol"]] = {}
        return out

    def add_analysis(
        self,
        symbol: str,
        role: str,
        model: str,
        decision: str,
        confidence: float | None,
        latency_ms: int | None,
        summary: str,
        response: dict[str, Any],
        prompt: dict[str, Any],
    ) -> None:
        with self.lock, self.conn:
            self.conn.execute(
                """
                INSERT INTO analyses(ts, symbol, role, model, decision, confidence, latency_ms, summary, response_json, prompt_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    time.time(),
                    symbol,
                    role,
                    model,
                    decision,
                    confidence,
                    latency_ms,
                    summary,
                    json.dumps(response, ensure_ascii=False),
                    json.dumps(prompt, ensure_ascii=False),
                ),
            )

    def list_analyses(self, limit: int = 60) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM analyses ORDER BY id DESC LIMIT ?", (int(limit),)
            ).fetchall()
        return [self._row_with_json(row, "response_json", "response") for row in rows]

    def open_trade(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        position_brl: float,
        stop_loss_pct: float,
        take_profit_pct: float,
        entry_reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        with self.lock, self.conn:
            cur = self.conn.execute(
                """
                INSERT INTO trades(opened_at, symbol, side, status, entry_price, position_brl, stop_loss_pct, take_profit_pct, entry_reason, metadata_json)
                VALUES (?, ?, ?, 'OPEN', ?, ?, ?, ?, ?, ?)
                """,
                (
                    time.time(),
                    symbol,
                    side,
                    entry_price,
                    position_brl,
                    stop_loss_pct,
                    take_profit_pct,
                    entry_reason,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
            return int(cur.lastrowid)

    def close_trade(self, trade_id: int, exit_price: float, pnl_brl: float, pnl_pct: float, exit_reason: str) -> None:
        with self.lock, self.conn:
            self.conn.execute(
                """
                UPDATE trades
                SET status = 'CLOSED', closed_at = ?, exit_price = ?, pnl_brl = ?, pnl_pct = ?, exit_reason = ?
                WHERE id = ? AND status = 'OPEN'
                """,
                (time.time(), exit_price, pnl_brl, pnl_pct, exit_reason, trade_id),
            )

    def list_trades(self, limit: int = 120) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM trades ORDER BY id DESC LIMIT ?", (int(limit),)
            ).fetchall()
        return [self._row_with_json(row, "metadata_json", "metadata") for row in rows]

    def open_trades(self) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.conn.execute("SELECT * FROM trades WHERE status = 'OPEN' ORDER BY id").fetchall()
        return [self._row_with_json(row, "metadata_json", "metadata") for row in rows]

    def closed_trades_today(self) -> list[dict[str, Any]]:
        start = time.time() - (time.time() % 86400)
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM trades WHERE opened_at >= ? ORDER BY id DESC", (start,)
            ).fetchall()
        return [self._row_with_json(row, "metadata_json", "metadata") for row in rows]

    def reset_paper(self, balance_brl: float) -> None:
        with self.lock, self.conn:
            self.conn.execute("DELETE FROM trades")
            self.conn.execute("DELETE FROM analyses")
            self.conn.execute("DELETE FROM events")
        self.set_kv("wallet", {"initial_balance_brl": balance_brl, "realized_pnl_brl": 0})

    @staticmethod
    def _row_with_json(row: sqlite3.Row, json_col: str, output_key: str) -> dict[str, Any]:
        item = dict(row)
        try:
            item[output_key] = json.loads(item.get(json_col) or "{}")
        except json.JSONDecodeError:
            item[output_key] = {}
        item.pop(json_col, None)
        return item
