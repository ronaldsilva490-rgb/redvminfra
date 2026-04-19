import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .security import (
    clean_scope,
    hash_password,
    new_access_token,
    new_device_code,
    new_session_token,
    new_user_code,
    sanitize_email,
    sha256_hex,
    verify_password,
)


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.migrate()
        self.bootstrap_provider_configs()

    def migrate(self) -> None:
        with self.lock, self.conn:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                  id TEXT PRIMARY KEY,
                  email TEXT NOT NULL UNIQUE,
                  password_hash TEXT NOT NULL,
                  name TEXT NOT NULL,
                  cpf TEXT NOT NULL DEFAULT '',
                  is_active INTEGER NOT NULL DEFAULT 1,
                  created_at REAL NOT NULL,
                  updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS user_sessions (
                  id TEXT PRIMARY KEY,
                  user_id TEXT NOT NULL,
                  kind TEXT NOT NULL,
                  token_hash TEXT NOT NULL UNIQUE,
                  created_at REAL NOT NULL,
                  expires_at REAL NOT NULL,
                  user_agent TEXT NOT NULL DEFAULT '',
                  remote_ip TEXT NOT NULL DEFAULT '',
                  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions(user_id, kind);

                CREATE TABLE IF NOT EXISTS access_tokens (
                  id TEXT PRIMARY KEY,
                  user_id TEXT NOT NULL,
                  token_hash TEXT NOT NULL UNIQUE,
                  scope TEXT NOT NULL DEFAULT '',
                  created_at REAL NOT NULL,
                  expires_at REAL NOT NULL,
                  last_used_at REAL,
                  revoked_at REAL,
                  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS device_codes (
                  device_code TEXT PRIMARY KEY,
                  user_code TEXT NOT NULL UNIQUE,
                  user_id TEXT,
                  status TEXT NOT NULL,
                  client_name TEXT NOT NULL,
                  scope TEXT NOT NULL DEFAULT '',
                  created_at REAL NOT NULL,
                  expires_at REAL NOT NULL,
                  approved_at REAL,
                  denied_at REAL,
                  consumed_at REAL,
                  access_token_id TEXT,
                  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL,
                  FOREIGN KEY(access_token_id) REFERENCES access_tokens(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS wallets (
                  user_id TEXT PRIMARY KEY,
                  balance_cents INTEGER NOT NULL DEFAULT 0,
                  updated_at REAL NOT NULL,
                  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS wallet_ledger (
                  id TEXT PRIMARY KEY,
                  user_id TEXT NOT NULL,
                  direction TEXT NOT NULL,
                  kind TEXT NOT NULL,
                  amount_cents INTEGER NOT NULL,
                  balance_after_cents INTEGER NOT NULL,
                  status TEXT NOT NULL,
                  ref_type TEXT NOT NULL DEFAULT '',
                  ref_id TEXT NOT NULL DEFAULT '',
                  description TEXT NOT NULL DEFAULT '',
                  metadata_json TEXT NOT NULL DEFAULT '{}',
                  created_at REAL NOT NULL,
                  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_wallet_ledger_user ON wallet_ledger(user_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS provider_configs (
                  code TEXT PRIMARY KEY,
                  display_name TEXT NOT NULL,
                  enabled INTEGER NOT NULL DEFAULT 0,
                  settings_json TEXT NOT NULL DEFAULT '{}',
                  updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS provider_customers (
                  id TEXT PRIMARY KEY,
                  user_id TEXT NOT NULL,
                  provider_code TEXT NOT NULL,
                  external_customer_id TEXT NOT NULL,
                  data_json TEXT NOT NULL DEFAULT '{}',
                  created_at REAL NOT NULL,
                  updated_at REAL NOT NULL,
                  UNIQUE(user_id, provider_code),
                  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS payment_charges (
                  id TEXT PRIMARY KEY,
                  user_id TEXT NOT NULL,
                  provider_code TEXT NOT NULL,
                  provider_charge_id TEXT NOT NULL DEFAULT '',
                  method TEXT NOT NULL DEFAULT 'pix',
                  status TEXT NOT NULL,
                  amount_cents INTEGER NOT NULL,
                  currency TEXT NOT NULL DEFAULT 'BRL',
                  description TEXT NOT NULL DEFAULT '',
                  external_reference TEXT NOT NULL DEFAULT '',
                  qr_code TEXT NOT NULL DEFAULT '',
                  qr_code_base64 TEXT NOT NULL DEFAULT '',
                  payment_url TEXT NOT NULL DEFAULT '',
                  expires_at REAL,
                  paid_at REAL,
                  credited_at REAL,
                  payload_json TEXT NOT NULL DEFAULT '{}',
                  created_at REAL NOT NULL,
                  updated_at REAL NOT NULL,
                  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_payment_charges_user ON payment_charges(user_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_payment_charges_provider ON payment_charges(provider_code, provider_charge_id);

                CREATE TABLE IF NOT EXISTS payment_webhook_events (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  provider_code TEXT NOT NULL,
                  external_event_id TEXT NOT NULL DEFAULT '',
                  event_type TEXT NOT NULL,
                  payload_json TEXT NOT NULL DEFAULT '{}',
                  created_at REAL NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_webhooks_unique ON payment_webhook_events(provider_code, external_event_id);

                CREATE TABLE IF NOT EXISTS usage_reservations (
                  id TEXT PRIMARY KEY,
                  user_id TEXT NOT NULL,
                  status TEXT NOT NULL,
                  reserved_cents INTEGER NOT NULL,
                  settled_cents INTEGER NOT NULL DEFAULT 0,
                  description TEXT NOT NULL DEFAULT '',
                  metadata_json TEXT NOT NULL DEFAULT '{}',
                  created_at REAL NOT NULL,
                  updated_at REAL NOT NULL,
                  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_usage_reservations_user ON usage_reservations(user_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS client_sessions (
                  id TEXT PRIMARY KEY,
                  user_id TEXT NOT NULL,
                  status TEXT NOT NULL,
                  device_name TEXT NOT NULL DEFAULT '',
                  client_version TEXT NOT NULL DEFAULT '',
                  exam_ref TEXT NOT NULL DEFAULT '',
                  metadata_json TEXT NOT NULL DEFAULT '{}',
                  started_at REAL NOT NULL,
                  last_seen_at REAL NOT NULL,
                  ended_at REAL,
                  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_client_sessions_user ON client_sessions(user_id, started_at DESC);

                CREATE TABLE IF NOT EXISTS events (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  ts REAL NOT NULL,
                  kind TEXT NOT NULL,
                  message TEXT NOT NULL,
                  data_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts DESC);
                """
            )

    def bootstrap_provider_configs(self) -> None:
        defaults = {
            "sandbox_pix": {"display_name": "Sandbox PIX", "enabled": 1, "settings": {"auto_credit": False}},
            "manual_pix": {"display_name": "PIX Manual", "enabled": 0, "settings": {}},
            "asaas": {"display_name": "Asaas", "enabled": 0, "settings": {"environment": "sandbox"}},
            "efi_pix": {"display_name": "Efí Bank PIX", "enabled": 0, "settings": {"environment": "homolog"}},
            "mercadopago_pix": {"display_name": "Mercado Pago PIX", "enabled": 0, "settings": {"environment": "sandbox"}},
            "pagarme_pix": {"display_name": "Pagar.me PIX", "enabled": 0, "settings": {}},
            "pagseguro_pix": {"display_name": "PagBank / PagSeguro PIX", "enabled": 0, "settings": {}},
        }
        now = time.time()
        with self.lock, self.conn:
            for code, payload in defaults.items():
                self.conn.execute(
                    """
                    INSERT INTO provider_configs(code, display_name, enabled, settings_json, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(code) DO NOTHING
                    """,
                    (
                        code,
                        payload["display_name"],
                        payload["enabled"],
                        json.dumps(payload["settings"], ensure_ascii=False),
                        now,
                    ),
                )

    def add_event(self, kind: str, message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        ts = time.time()
        payload = json.dumps(data or {}, ensure_ascii=False)
        with self.lock, self.conn:
            cur = self.conn.execute(
                "INSERT INTO events(ts, kind, message, data_json) VALUES (?, ?, ?, ?)",
                (ts, kind, message, payload),
            )
        return {"id": int(cur.lastrowid), "ts": ts, "kind": kind, "message": message, "data": data or {}}

    def list_events(self, limit: int = 120) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.conn.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["data"] = self._json_load(item.pop("data_json", "{}"))
            result.append(item)
        return result

    def create_user(self, *, email: str, password: str, name: str, cpf: str = "") -> dict[str, Any]:
        now = time.time()
        user_id = uuid.uuid4().hex
        clean_email = sanitize_email(email)
        with self.lock, self.conn:
            self.conn.execute(
                """
                INSERT INTO users(id, email, password_hash, name, cpf, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, clean_email, hash_password(password), name.strip(), cpf.strip(), now, now),
            )
            self.conn.execute(
                "INSERT INTO wallets(user_id, balance_cents, updated_at) VALUES (?, 0, ?)",
                (user_id, now),
            )
        return self.get_user(user_id)

    def authenticate_user(self, email: str, password: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.conn.execute("SELECT * FROM users WHERE email = ?", (sanitize_email(email),)).fetchone()
        if not row or not row["is_active"]:
            return None
        if not verify_password(password, row["password_hash"]):
            return None
        return self._user_row_to_public(row)

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return None
        return self._user_row_to_public(row)

    def list_users(self) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
        return [self._user_row_to_public(row, with_wallet=True) for row in rows]

    def create_cookie_session(
        self,
        *,
        user_id: str,
        kind: str,
        user_agent: str = "",
        remote_ip: str = "",
        ttl_seconds: int = 60 * 60 * 24 * 30,
    ) -> str:
        token = new_session_token()
        now = time.time()
        with self.lock, self.conn:
            self.conn.execute(
                """
                INSERT INTO user_sessions(id, user_id, kind, token_hash, created_at, expires_at, user_agent, remote_ip)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid.uuid4().hex,
                    user_id,
                    kind,
                    sha256_hex(token),
                    now,
                    now + ttl_seconds,
                    user_agent,
                    remote_ip,
                ),
            )
        return token

    def get_session_user(self, token: str, kind: str) -> dict[str, Any] | None:
        now = time.time()
        with self.lock:
            row = self.conn.execute(
                """
                SELECT u.* FROM user_sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = ? AND s.kind = ? AND s.expires_at > ? AND u.is_active = 1
                """,
                (sha256_hex(token), kind, now),
            ).fetchone()
        if not row:
            return None
        return self._user_row_to_public(row)

    def revoke_cookie_session(self, token: str, kind: str) -> None:
        with self.lock, self.conn:
            self.conn.execute("DELETE FROM user_sessions WHERE token_hash = ? AND kind = ?", (sha256_hex(token), kind))

    def create_access_token(self, user_id: str, scope: str, ttl_seconds: int) -> dict[str, Any]:
        now = time.time()
        token = new_access_token()
        token_id = uuid.uuid4().hex
        with self.lock, self.conn:
            self.conn.execute(
                """
                INSERT INTO access_tokens(id, user_id, token_hash, scope, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (token_id, user_id, sha256_hex(token), clean_scope(scope), now, now + ttl_seconds),
            )
        return {"id": token_id, "token": token, "expires_at": now + ttl_seconds, "scope": clean_scope(scope)}

    def get_access_token(self, token: str) -> dict[str, Any] | None:
        now = time.time()
        token_hash = sha256_hex(token)
        with self.lock, self.conn:
            row = self.conn.execute(
                """
                SELECT t.*, u.email, u.name, u.cpf, u.is_active
                FROM access_tokens t
                JOIN users u ON u.id = t.user_id
                WHERE t.token_hash = ? AND t.revoked_at IS NULL AND t.expires_at > ? AND u.is_active = 1
                """,
                (token_hash, now),
            ).fetchone()
            if row:
                self.conn.execute("UPDATE access_tokens SET last_used_at = ? WHERE id = ?", (now, row["id"]))
        if not row:
            return None
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "scope": row["scope"],
            "expires_at": row["expires_at"],
            "user": {"id": row["user_id"], "email": row["email"], "name": row["name"], "cpf": row["cpf"]},
        }

    def revoke_access_token(self, token: str) -> None:
        with self.lock, self.conn:
            self.conn.execute(
                "UPDATE access_tokens SET revoked_at = ? WHERE token_hash = ?",
                (time.time(), sha256_hex(token)),
            )

    def create_device_code(self, client_name: str, scope: str, ttl_seconds: int) -> dict[str, Any]:
        now = time.time()
        payload = {
            "device_code": new_device_code(),
            "user_code": new_user_code(),
            "client_name": client_name.strip() or "RED CLI",
            "scope": clean_scope(scope or "red.runtime"),
            "created_at": now,
            "expires_at": now + ttl_seconds,
            "status": "pending",
        }
        with self.lock, self.conn:
            self.conn.execute(
                """
                INSERT INTO device_codes(device_code, user_code, status, client_name, scope, created_at, expires_at)
                VALUES (?, ?, 'pending', ?, ?, ?, ?)
                """,
                (
                    payload["device_code"],
                    payload["user_code"],
                    payload["client_name"],
                    payload["scope"],
                    payload["created_at"],
                    payload["expires_at"],
                ),
            )
        return payload

    def get_device_code_by_user_code(self, user_code: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.conn.execute("SELECT * FROM device_codes WHERE user_code = ?", (user_code.strip().upper(),)).fetchone()
        return dict(row) if row else None

    def approve_device_code(self, user_code: str, user_id: str, ttl_seconds: int) -> dict[str, Any] | None:
        user_code = user_code.strip().upper()
        now = time.time()
        with self.lock, self.conn:
            row = self.conn.execute(
                "SELECT * FROM device_codes WHERE user_code = ? AND expires_at > ?",
                (user_code, now),
            ).fetchone()
            if not row:
                return None
            self.conn.execute(
                """
                UPDATE device_codes
                SET status = 'approved', user_id = ?, approved_at = ?
                WHERE device_code = ?
                """,
                (user_id, now, row["device_code"]),
            )
        return {"device_code": row["device_code"], "user_code": row["user_code"], "expires_at": row["expires_at"]}

    def deny_device_code(self, user_code: str) -> None:
        with self.lock, self.conn:
            self.conn.execute(
                "UPDATE device_codes SET status = 'denied', denied_at = ? WHERE user_code = ?",
                (time.time(), user_code.strip().upper()),
            )

    def poll_device_code(self, device_code: str) -> dict[str, Any] | None:
        now = time.time()
        with self.lock, self.conn:
            row = self.conn.execute("SELECT * FROM device_codes WHERE device_code = ?", (device_code,)).fetchone()
            if not row:
                return None
            item = dict(row)
            if row["status"] == "approved" and not row["consumed_at"]:
                token_bundle = self.create_access_token(row["user_id"], row["scope"], int(row["expires_at"] - row["created_at"]))
                self.conn.execute(
                    "UPDATE device_codes SET consumed_at = ?, access_token_id = ? WHERE device_code = ?",
                    (now, token_bundle["id"], device_code),
                )
                item["access_token"] = token_bundle["token"]
                item["token_expires_at"] = token_bundle["expires_at"]
            return item

    def list_provider_configs(self) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.conn.execute("SELECT * FROM provider_configs ORDER BY display_name").fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["enabled"] = bool(item["enabled"])
            item["settings"] = self._json_load(item.pop("settings_json", "{}"))
            out.append(item)
        return out

    def get_provider_config(self, code: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.conn.execute("SELECT * FROM provider_configs WHERE code = ?", (code,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["enabled"] = bool(item["enabled"])
        item["settings"] = self._json_load(item.pop("settings_json", "{}"))
        return item

    def upsert_provider_config(self, code: str, display_name: str, enabled: bool, settings: dict[str, Any]) -> None:
        with self.lock, self.conn:
            self.conn.execute(
                """
                INSERT INTO provider_configs(code, display_name, enabled, settings_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                  display_name = excluded.display_name,
                  enabled = excluded.enabled,
                  settings_json = excluded.settings_json,
                  updated_at = excluded.updated_at
                """,
                (code, display_name, 1 if enabled else 0, json.dumps(settings, ensure_ascii=False), time.time()),
            )

    def get_provider_customer(self, user_id: str, provider_code: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT * FROM provider_customers WHERE user_id = ? AND provider_code = ?",
                (user_id, provider_code),
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["data"] = self._json_load(item.pop("data_json", "{}"))
        return item

    def upsert_provider_customer(self, user_id: str, provider_code: str, external_customer_id: str, data: dict[str, Any]) -> None:
        now = time.time()
        with self.lock, self.conn:
            self.conn.execute(
                """
                INSERT INTO provider_customers(id, user_id, provider_code, external_customer_id, data_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, provider_code) DO UPDATE SET
                  external_customer_id = excluded.external_customer_id,
                  data_json = excluded.data_json,
                  updated_at = excluded.updated_at
                """,
                (
                    uuid.uuid4().hex,
                    user_id,
                    provider_code,
                    external_customer_id,
                    json.dumps(data, ensure_ascii=False),
                    now,
                    now,
                ),
            )

    def create_charge(self, *, user_id: str, provider_code: str, method: str, amount_cents: int, description: str) -> dict[str, Any]:
        charge_id = uuid.uuid4().hex
        now = time.time()
        payload = {
            "id": charge_id,
            "user_id": user_id,
            "provider_code": provider_code,
            "method": method,
            "status": "pending",
            "amount_cents": amount_cents,
            "currency": "BRL",
            "description": description,
            "created_at": now,
            "updated_at": now,
        }
        with self.lock, self.conn:
            self.conn.execute(
                """
                INSERT INTO payment_charges(
                  id, user_id, provider_code, method, status, amount_cents, currency, description, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'pending', ?, 'BRL', ?, ?, ?)
                """,
                (
                    payload["id"],
                    payload["user_id"],
                    payload["provider_code"],
                    payload["method"],
                    payload["amount_cents"],
                    payload["description"],
                    now,
                    now,
                ),
            )
        return self.get_charge(charge_id)

    def get_charge(self, charge_id: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.conn.execute("SELECT * FROM payment_charges WHERE id = ?", (charge_id,)).fetchone()
        if not row:
            return None
        return self._charge_row_to_dict(row)

    def find_charge_by_provider(self, provider_code: str, provider_charge_id: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.conn.execute(
                """
                SELECT * FROM payment_charges
                WHERE provider_code = ? AND provider_charge_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (provider_code, provider_charge_id),
            ).fetchone()
        if not row:
            return None
        return self._charge_row_to_dict(row)

    def find_charge_by_external_reference(self, provider_code: str, external_reference: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.conn.execute(
                """
                SELECT * FROM payment_charges
                WHERE provider_code = ? AND external_reference = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (provider_code, external_reference),
            ).fetchone()
        if not row:
            return None
        return self._charge_row_to_dict(row)

    def list_charges(self, *, user_id: str | None = None, limit: int = 120) -> list[dict[str, Any]]:
        with self.lock:
            if user_id:
                rows = self.conn.execute(
                    "SELECT * FROM payment_charges WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                    (user_id, int(limit)),
                ).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT * FROM payment_charges ORDER BY created_at DESC LIMIT ?",
                    (int(limit),),
                ).fetchall()
        return [self._charge_row_to_dict(row) for row in rows]

    def update_charge_provider_payload(self, charge_id: str, data: dict[str, Any]) -> dict[str, Any]:
        charge = self.get_charge(charge_id)
        if not charge:
            raise KeyError(charge_id)
        payload = {**(charge.get("payload") or {}), **(data.get("payload") or {})}
        now = time.time()
        status = data.get("status", charge["status"])
        paid_at = data.get("paid_at", charge.get("paid_at"))
        with self.lock, self.conn:
            self.conn.execute(
                """
                UPDATE payment_charges
                SET provider_charge_id = ?,
                    status = ?,
                    external_reference = ?,
                    qr_code = ?,
                    qr_code_base64 = ?,
                    payment_url = ?,
                    expires_at = ?,
                    paid_at = ?,
                    payload_json = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    str(data.get("provider_charge_id") or charge.get("provider_charge_id") or ""),
                    str(status),
                    str(data.get("external_reference") or charge.get("external_reference") or ""),
                    str(data.get("qr_code") or charge.get("qr_code") or ""),
                    str(data.get("qr_code_base64") or charge.get("qr_code_base64") or ""),
                    str(data.get("payment_url") or charge.get("payment_url") or ""),
                    data.get("expires_at", charge.get("expires_at")),
                    paid_at,
                    json.dumps(payload, ensure_ascii=False),
                    now,
                    charge_id,
                ),
            )
        if status in {"paid", "confirmed", "received"}:
            self.credit_charge_if_needed(charge_id, paid_at or now)
        return self.get_charge(charge_id)

    def credit_charge_if_needed(self, charge_id: str, paid_at: float) -> None:
        with self.lock, self.conn:
            row = self.conn.execute("SELECT * FROM payment_charges WHERE id = ?", (charge_id,)).fetchone()
            if not row or row["credited_at"]:
                return
            balance = self.conn.execute(
                "SELECT balance_cents FROM wallets WHERE user_id = ?",
                (row["user_id"],),
            ).fetchone()
            balance_cents = int(balance["balance_cents"]) if balance else 0
            new_balance = balance_cents + int(row["amount_cents"])
            ts = time.time()
            self.conn.execute(
                "UPDATE wallets SET balance_cents = ?, updated_at = ? WHERE user_id = ?",
                (new_balance, ts, row["user_id"]),
            )
            self.conn.execute(
                """
                INSERT INTO wallet_ledger(
                  id, user_id, direction, kind, amount_cents, balance_after_cents, status, ref_type, ref_id, description, created_at
                ) VALUES (?, ?, 'credit', 'topup', ?, ?, 'posted', 'charge', ?, ?, ?)
                """,
                (
                    uuid.uuid4().hex,
                    row["user_id"],
                    int(row["amount_cents"]),
                    new_balance,
                    charge_id,
                    f"Credito confirmado via {row['provider_code']}",
                    ts,
                ),
            )
            self.conn.execute(
                "UPDATE payment_charges SET credited_at = ?, paid_at = COALESCE(paid_at, ?), status = 'paid', updated_at = ? WHERE id = ?",
                (ts, paid_at, ts, charge_id),
            )

    def record_webhook_event(self, provider_code: str, external_event_id: str, event_type: str, payload: dict[str, Any]) -> bool:
        try:
            with self.lock, self.conn:
                self.conn.execute(
                    """
                    INSERT INTO payment_webhook_events(provider_code, external_event_id, event_type, payload_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (provider_code, external_event_id or "", event_type, json.dumps(payload, ensure_ascii=False), time.time()),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def get_wallet(self, user_id: str) -> dict[str, Any]:
        with self.lock:
            row = self.conn.execute("SELECT * FROM wallets WHERE user_id = ?", (user_id,)).fetchone()
        balance = int(row["balance_cents"]) if row else 0
        return {"user_id": user_id, "balance_cents": balance, "balance_brl": balance / 100.0}

    def list_wallet_ledger(self, user_id: str, limit: int = 120) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM wallet_ledger WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, int(limit)),
            ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["metadata"] = self._json_load(item.pop("metadata_json", "{}"))
            out.append(item)
        return out

    def create_reservation(self, user_id: str, reserved_cents: int, description: str, metadata: dict[str, Any]) -> dict[str, Any]:
        with self.lock, self.conn:
            wallet = self.conn.execute("SELECT balance_cents FROM wallets WHERE user_id = ?", (user_id,)).fetchone()
            balance = int(wallet["balance_cents"]) if wallet else 0
            if balance < reserved_cents:
                raise ValueError("Saldo insuficiente")
            new_balance = balance - reserved_cents
            ts = time.time()
            reservation_id = uuid.uuid4().hex
            self.conn.execute("UPDATE wallets SET balance_cents = ?, updated_at = ? WHERE user_id = ?", (new_balance, ts, user_id))
            self.conn.execute(
                """
                INSERT INTO wallet_ledger(
                  id, user_id, direction, kind, amount_cents, balance_after_cents, status, ref_type, ref_id, description, metadata_json, created_at
                ) VALUES (?, ?, 'debit', 'hold', ?, ?, 'posted', 'reservation', ?, ?, ?, ?)
                """,
                (
                    uuid.uuid4().hex,
                    user_id,
                    reserved_cents,
                    new_balance,
                    reservation_id,
                    description,
                    json.dumps(metadata, ensure_ascii=False),
                    ts,
                ),
            )
            self.conn.execute(
                """
                INSERT INTO usage_reservations(id, user_id, status, reserved_cents, description, metadata_json, created_at, updated_at)
                VALUES (?, ?, 'reserved', ?, ?, ?, ?, ?)
                """,
                (
                    reservation_id,
                    user_id,
                    reserved_cents,
                    description,
                    json.dumps(metadata, ensure_ascii=False),
                    ts,
                    ts,
                ),
            )
        return self.get_reservation(reservation_id)

    def create_client_session(self, user_id: str, device_name: str, client_version: str, exam_ref: str, metadata: dict[str, Any]) -> dict[str, Any]:
        session_id = uuid.uuid4().hex
        ts = time.time()
        with self.lock, self.conn:
            self.conn.execute(
                """
                INSERT INTO client_sessions(id, user_id, status, device_name, client_version, exam_ref, metadata_json, started_at, last_seen_at)
                VALUES (?, ?, 'online', ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    user_id,
                    device_name,
                    client_version,
                    exam_ref,
                    json.dumps(metadata, ensure_ascii=False),
                    ts,
                    ts,
                ),
            )
        return self.get_client_session(session_id)

    def get_client_session(self, session_id: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.conn.execute("SELECT * FROM client_sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["metadata"] = self._json_load(item.pop("metadata_json", "{}"))
        return item

    def heartbeat_client_session(self, session_id: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        with self.lock, self.conn:
            row = self.conn.execute("SELECT * FROM client_sessions WHERE id = ?", (session_id,)).fetchone()
            if not row:
                raise KeyError(session_id)
            payload = self._json_load(row["metadata_json"])
            if metadata:
                payload.update(metadata)
            self.conn.execute(
                "UPDATE client_sessions SET status = 'online', last_seen_at = ?, metadata_json = ? WHERE id = ?",
                (time.time(), json.dumps(payload, ensure_ascii=False), session_id),
            )
        return self.get_client_session(session_id)

    def stop_client_session(self, session_id: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        with self.lock, self.conn:
            row = self.conn.execute("SELECT * FROM client_sessions WHERE id = ?", (session_id,)).fetchone()
            if not row:
                raise KeyError(session_id)
            payload = self._json_load(row["metadata_json"])
            if metadata:
                payload.update(metadata)
            ts = time.time()
            self.conn.execute(
                "UPDATE client_sessions SET status = 'offline', last_seen_at = ?, ended_at = ?, metadata_json = ? WHERE id = ?",
                (ts, ts, json.dumps(payload, ensure_ascii=False), session_id),
            )
        return self.get_client_session(session_id)

    def list_client_sessions(self, user_id: str | None = None, limit: int = 60) -> list[dict[str, Any]]:
        with self.lock:
            if user_id:
                rows = self.conn.execute(
                    "SELECT * FROM client_sessions WHERE user_id = ? ORDER BY started_at DESC LIMIT ?",
                    (user_id, int(limit)),
                ).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT * FROM client_sessions ORDER BY started_at DESC LIMIT ?",
                    (int(limit),),
                ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["metadata"] = self._json_load(item.pop("metadata_json", "{}"))
            out.append(item)
        return out

    def get_reservation(self, reservation_id: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.conn.execute("SELECT * FROM usage_reservations WHERE id = ?", (reservation_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["metadata"] = self._json_load(item.pop("metadata_json", "{}"))
        return item

    def settle_reservation(self, reservation_id: str, settled_cents: int, metadata: dict[str, Any]) -> dict[str, Any]:
        with self.lock, self.conn:
            row = self.conn.execute("SELECT * FROM usage_reservations WHERE id = ?", (reservation_id,)).fetchone()
            if not row:
                raise KeyError(reservation_id)
            if row["status"] != "reserved":
                return self.get_reservation(reservation_id)
            refund = int(row["reserved_cents"]) - int(settled_cents)
            ts = time.time()
            if refund > 0:
                wallet = self.conn.execute("SELECT balance_cents FROM wallets WHERE user_id = ?", (row["user_id"],)).fetchone()
                current_balance = int(wallet["balance_cents"]) if wallet else 0
                new_balance = current_balance + refund
                self.conn.execute("UPDATE wallets SET balance_cents = ?, updated_at = ? WHERE user_id = ?", (new_balance, ts, row["user_id"]))
                self.conn.execute(
                    """
                    INSERT INTO wallet_ledger(
                      id, user_id, direction, kind, amount_cents, balance_after_cents, status, ref_type, ref_id, description, metadata_json, created_at
                    ) VALUES (?, ?, 'credit', 'refund', ?, ?, 'posted', 'reservation', ?, ?, ?, ?)
                    """,
                    (
                        uuid.uuid4().hex,
                        row["user_id"],
                        refund,
                        new_balance,
                        reservation_id,
                        "Ajuste de uso da IA",
                        json.dumps(metadata, ensure_ascii=False),
                        ts,
                    ),
                )
            self.conn.execute(
                "UPDATE usage_reservations SET status = 'settled', settled_cents = ?, metadata_json = ?, updated_at = ? WHERE id = ?",
                (settled_cents, json.dumps(metadata, ensure_ascii=False), ts, reservation_id),
            )
        return self.get_reservation(reservation_id)

    def release_reservation(self, reservation_id: str, reason: str) -> dict[str, Any]:
        with self.lock, self.conn:
            row = self.conn.execute("SELECT * FROM usage_reservations WHERE id = ?", (reservation_id,)).fetchone()
            if not row:
                raise KeyError(reservation_id)
            if row["status"] != "reserved":
                return self.get_reservation(reservation_id)
            ts = time.time()
            wallet = self.conn.execute("SELECT balance_cents FROM wallets WHERE user_id = ?", (row["user_id"],)).fetchone()
            current_balance = int(wallet["balance_cents"]) if wallet else 0
            new_balance = current_balance + int(row["reserved_cents"])
            self.conn.execute("UPDATE wallets SET balance_cents = ?, updated_at = ? WHERE user_id = ?", (new_balance, ts, row["user_id"]))
            self.conn.execute(
                """
                INSERT INTO wallet_ledger(
                  id, user_id, direction, kind, amount_cents, balance_after_cents, status, ref_type, ref_id, description, metadata_json, created_at
                ) VALUES (?, ?, 'credit', 'release', ?, ?, 'posted', 'reservation', ?, ?, ?, ?)
                """,
                (
                    uuid.uuid4().hex,
                    row["user_id"],
                    int(row["reserved_cents"]),
                    new_balance,
                    reservation_id,
                    reason,
                    json.dumps({"reason": reason}, ensure_ascii=False),
                    ts,
                ),
            )
            self.conn.execute(
                "UPDATE usage_reservations SET status = 'released', metadata_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps({"reason": reason}, ensure_ascii=False), ts, reservation_id),
            )
        return self.get_reservation(reservation_id)

    def stats(self) -> dict[str, Any]:
        with self.lock:
            total_users = int(self.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])
            active_charges = int(
                self.conn.execute("SELECT COUNT(*) FROM payment_charges WHERE status IN ('pending', 'waiting_payment', 'active')").fetchone()[0]
            )
            total_balance = int(self.conn.execute("SELECT COALESCE(SUM(balance_cents), 0) FROM wallets").fetchone()[0])
            paid_charges = int(self.conn.execute("SELECT COUNT(*) FROM payment_charges WHERE credited_at IS NOT NULL").fetchone()[0])
        return {
            "total_users": total_users,
            "active_charges": active_charges,
            "total_balance_cents": total_balance,
            "total_balance_brl": total_balance / 100.0,
            "paid_charges": paid_charges,
        }

    def _user_row_to_public(self, row: sqlite3.Row, with_wallet: bool = False) -> dict[str, Any]:
        item = {
            "id": row["id"],
            "email": row["email"],
            "name": row["name"],
            "cpf": row["cpf"],
            "is_active": bool(row["is_active"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        if with_wallet:
            item["wallet"] = self.get_wallet(row["id"])
        return item

    def _charge_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["payload"] = self._json_load(item.pop("payload_json", "{}"))
        item["amount_brl"] = int(item["amount_cents"]) / 100.0
        return item

    @staticmethod
    def _json_load(raw: str) -> dict[str, Any]:
        try:
            return json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {}
