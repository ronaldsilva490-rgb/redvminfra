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
    tastytrade_base_url = _env("TASTYTRADE_BASE_URL", "https://api.cert.tastyworks.com").rstrip("/")
    tastytrade_username = _env("TASTYTRADE_USERNAME", "")
    tastytrade_password = _env("TASTYTRADE_PASSWORD", "")
    tastytrade_client_id = _env("TASTYTRADE_CLIENT_ID", "")
    tastytrade_client_secret = _env("TASTYTRADE_CLIENT_SECRET", "")
    tastytrade_refresh_token = _env("TASTYTRADE_REFRESH_TOKEN", "")
    tastytrade_account_number = _env("TASTYTRADE_ACCOUNT_NUMBER", "")
    webull_base_url = _env("WEBULL_BASE_URL", "https://openapi.webull.com").rstrip("/")
    webull_app_key = _env("WEBULL_APP_KEY", "")
    webull_app_secret = _env("WEBULL_APP_SECRET", "")
    iqoption_enabled = _env("IQOPTION_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    iqoption_host = _env("IQOPTION_HOST", "iqoption.com")
    iqoption_username = _env("IQOPTION_USERNAME", "")
    iqoption_password = _env("IQOPTION_PASSWORD", "")
    iqoption_force_practice = _env("IQOPTION_FORCE_PRACTICE", "true").lower() in {"1", "true", "yes", "on"}
    iqoption_timeout_seconds = int(_env("IQOPTION_TIMEOUT_SECONDS", "25"))


settings = Settings()
