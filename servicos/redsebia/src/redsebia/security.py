import base64
import hashlib
import hmac
import os
import secrets
import string
from typing import Iterable


PBKDF2_ITERATIONS = 240_000
USER_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def constant_equals(left: str, right: str) -> bool:
    return hmac.compare_digest(left or "", right or "")


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt_raw, digest_raw = password_hash.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        base64.urlsafe_b64decode(salt_raw.encode("ascii")),
        int(iterations_raw),
    )
    expected = base64.urlsafe_b64decode(digest_raw.encode("ascii"))
    return hmac.compare_digest(digest, expected)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def new_access_token() -> str:
    return "rsb_" + secrets.token_urlsafe(40)


def new_device_code() -> str:
    return "device_" + secrets.token_urlsafe(24)


def new_user_code(length: int = 8) -> str:
    return "".join(secrets.choice(USER_CODE_ALPHABET) for _ in range(length))


def clean_scope(scope: str | Iterable[str] | None) -> str:
    if not scope:
        return ""
    if isinstance(scope, str):
        return " ".join(part.strip() for part in scope.split() if part.strip())
    return " ".join(str(part).strip() for part in scope if str(part).strip())


def sanitize_email(email: str) -> str:
    return email.strip().lower()


def is_reasonable_password(password: str) -> bool:
    if len(password) < 8:
        return False
    has_alpha = any(ch.isalpha() for ch in password)
    has_digit = any(ch.isdigit() for ch in password)
    return has_alpha and has_digit
