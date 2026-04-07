import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
PUBLIC_DIR = ROOT_DIR / "public"
DATA_DIR = ROOT_DIR / "data"


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


class Settings:
    host = _env("REDTRADER_HOST", "0.0.0.0")
    port = int(_env("REDTRADER_PORT", "3100"))
    password = _env("REDTRADER_PASSWORD", "change-me")
    secret = _env("REDTRADER_SECRET", "redtrader-local-secret-change-me")
    db_path = Path(_env("REDTRADER_DB_PATH", str(DATA_DIR / "redtrader.sqlite")))
    proxy_url = _env("REDSYSTEMS_PROXY_URL", "http://redsystems.ddns.net:8080").rstrip("/")
    binance_base_url = _env("BINANCE_BASE_URL", "https://api.binance.com").rstrip("/")


settings = Settings()
