from __future__ import annotations

import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKUP_DB = ROOT.parents[1] / ".privado" / "backups" / "redtrader-reset-backup-1775686362.sqlite"
OUTPUT = ROOT / "fixtures" / "loss_sequences_fixture.json"
SEQUENCES = [
    [305, 306, 307],
    [318, 319, 320],
    [325, 326, 327],
    [328, 329, 330],
]


def normalize_side(value: str) -> str:
    text = str(value or "").upper().strip()
    if text in {"CALL", "ACIMA", "BUY", "LONG"}:
        return "CALL"
    if text in {"PUT", "ABAIXO", "SELL", "SHORT"}:
        return "PUT"
    return "WAIT"


def main() -> int:
    if not BACKUP_DB.exists():
        raise SystemExit(f"Backup nao encontrado: {BACKUP_DB}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(BACKUP_DB)
    conn.row_factory = sqlite3.Row
    points = []
    for seq in SEQUENCES:
        label = f"{seq[0]}-{seq[-1]}"
        rows = conn.execute(
            f"SELECT id, symbol, side, opened_at, position_brl, pnl_brl, metadata_json FROM trades WHERE id IN ({','.join('?' for _ in seq)}) ORDER BY id",
            seq,
        ).fetchall()
        for row in rows:
            meta = json.loads(row["metadata_json"] or "{}")
            candidate = meta.get("candidate") or {}
            payload = {
                "mode": "iqoption_demo_binary_only",
                "candidate": candidate,
                "recovery_context": meta.get("recovery_context"),
                "recent_trade_feedback": meta.get("recent_trade_feedback"),
                "learning_context": meta.get("learning_context"),
            }
            points.append(
                {
                    "sequence": label,
                    "trade_id": int(row["id"]),
                    "opened_at": float(row["opened_at"] or 0),
                    "symbol": str(row["symbol"]),
                    "actual_side": normalize_side(row["side"]),
                    "actual_win": float(row["pnl_brl"] or 0) > 0,
                    "amount": float(row["position_brl"] or 0),
                    "analysis_id": 0,
                    "system_prompt": "",
                    "user_prompt": "",
                    "market_payload": payload,
                }
            )
    conn.close()
    OUTPUT.write_text(json.dumps({"points": points}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(OUTPUT)
    print(f"points={len(points)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
