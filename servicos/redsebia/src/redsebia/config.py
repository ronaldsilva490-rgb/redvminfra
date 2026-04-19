import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT_DIR / "templates"
STATIC_DIR = ROOT_DIR / "static"


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("REDSEBIA_HOST", "127.0.0.1")
    port: int = _env_int("REDSEBIA_PORT", 3130)
    public_base_url: str = os.getenv("REDSEBIA_PUBLIC_BASE_URL", "http://redsystems.ddns.net/redsebia").rstrip("/")
    data_dir: Path = Path(os.getenv("REDSEBIA_DATA_DIR", str(ROOT_DIR / "data")))
    db_path: Path = Path(os.getenv("REDSEBIA_DB_PATH", str(ROOT_DIR / "data" / "redsebia.db")))
    repo_dir: Path = Path(os.getenv("REDVM_REPO_DIR", str(ROOT_DIR.parent.parent)))
    proxy_url: str = os.getenv("REDSEBIA_PROXY_URL", "http://127.0.0.1:8080").rstrip("/")
    admin_password: str = os.getenv("REDSEBIA_ADMIN_PASSWORD", "2580")
    secret: str = os.getenv("REDSEBIA_SECRET", "change-me-redsebia")
    device_code_ttl_seconds: int = _env_int("REDSEBIA_DEVICE_CODE_TTL_SECONDS", 600)
    runtime_token_ttl_seconds: int = _env_int("REDSEBIA_RUNTIME_TOKEN_TTL_SECONDS", 60 * 60 * 24 * 30)
    min_launch_balance_cents: int = _env_int("REDSEBIA_MIN_LAUNCH_BALANCE_CENTS", 1000)
    default_hold_cents: int = _env_int("REDSEBIA_DEFAULT_HOLD_CENTS", 500)


settings = Settings()
