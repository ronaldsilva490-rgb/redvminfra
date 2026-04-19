import hashlib
import hmac
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import ROOT_DIR, STATIC_DIR, TEMPLATES_DIR, settings
from .db import Database
from .providers import ChargeRequest, get_provider, provider_definitions
from .security import constant_equals, is_reasonable_password


db = Database(settings.db_path)
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield


app = FastAPI(title="REDSEBIA", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


COOKIE_USER = "redsebia_session"
COOKIE_ADMIN = "redsebia_admin"
ASSET_VERSION = "20260419-redsebia-v2"


def public_path(request: Request, path: str) -> str:
    prefix = str(request.headers.get("x-forwarded-prefix") or "").rstrip("/")
    if not prefix:
        return path
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{prefix}{path}"


def admin_cookie_value() -> str:
    digest = hmac.new(settings.secret.encode("utf-8"), settings.admin_password.encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()


def has_admin_session(request: Request) -> bool:
    return constant_equals(request.cookies.get(COOKIE_ADMIN) or "", admin_cookie_value())


def get_remote_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = request.client
    return client.host if client else ""


def get_current_user(request: Request) -> dict[str, Any] | None:
    token = request.cookies.get(COOKIE_USER) or ""
    if not token:
        return None
    return db.get_session_user(token, "customer")


def require_user(request: Request) -> dict[str, Any]:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Não autenticado")
    return user


def require_admin(request: Request) -> None:
    if not has_admin_session(request):
        raise HTTPException(status_code=401, detail="Não autenticado")


def require_runtime_token(request: Request) -> dict[str, Any]:
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Token ausente")
    token = auth.split(" ", 1)[1].strip()
    session = db.get_access_token(token)
    if not session:
        raise HTTPException(status_code=401, detail="Token inválido")
    return session


def render_template(request: Request, name: str, context: dict[str, Any] | None = None) -> HTMLResponse:
    ctx = {
        "request": request,
        "base_path": public_path(request, ""),
        "public_path": lambda path: public_path(request, path),
        "asset_version": ASSET_VERSION,
        "current_user": get_current_user(request),
        "is_admin": has_admin_session(request),
    }
    if context:
        ctx.update(context)
    return templates.TemplateResponse(request=request, name=name, context=ctx)


def set_user_cookie(response: JSONResponse, token: str) -> None:
    response.set_cookie(COOKIE_USER, token, httponly=True, samesite="lax", secure=False, max_age=60 * 60 * 24 * 30)


def set_admin_cookie(response: JSONResponse) -> None:
    response.set_cookie(COOKIE_ADMIN, admin_cookie_value(), httponly=True, samesite="lax", secure=False, max_age=60 * 60 * 24 * 30)


def clear_user_cookie(response: JSONResponse) -> None:
    response.delete_cookie(COOKIE_USER)


def clear_admin_cookie(response: JSONResponse) -> None:
    response.delete_cookie(COOKIE_ADMIN)


def _provider_admin_view() -> list[dict[str, Any]]:
    configs = {item["code"]: item for item in db.list_provider_configs()}
    result = []
    for meta in provider_definitions():
        config = configs.get(meta["code"], {"enabled": False, "settings": {}, "display_name": meta["name"]})
        item = {**meta, **config}
        item["display_name"] = normalized_provider_display_name(meta["code"], item.get("display_name"))
        redacted = {}
        for field in meta["config_fields"]:
            value = config["settings"].get(field["name"])
            if field["type"] == "password" and value:
                redacted[field["name"]] = "********"
            else:
                redacted[field["name"]] = value
        item["settings_redacted"] = redacted
        item["webhook_url"] = public_path_placeholder(f"/api/payments/webhooks/{meta['code']}")
        result.append(item)
    return result


def public_path_placeholder(path: str) -> str:
    return f"{settings.public_base_url}{path}"


def normalized_provider_display_name(code: str, display_name: str | None) -> str:
    display_name = str(display_name or "").strip()
    if code == "sandbox_pix" and display_name in {"", "Sandbox PIX"}:
        return "PIX instantâneo"
    return display_name or code


async def _fetch_proxy_models() -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(f"{settings.proxy_url}/v1/models")
            resp.raise_for_status()
            payload = resp.json()
    except Exception:
        return []
    models = payload.get("data") or []
    return [item.get("id") for item in models if item.get("id")]


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    return {"ok": True, "service": "redsebia", "db_path": str(settings.db_path)}


@app.get("/favicon.ico")
async def favicon() -> FileResponse:
    return FileResponse(settings.repo_dir / "identidade" / "logo" / "favicon.ico")


@app.get("/brand/logo.png")
async def brand_logo() -> FileResponse:
    return FileResponse(settings.repo_dir / "identidade" / "logo" / "logo.png")


@app.get("/")
async def home(request: Request) -> HTMLResponse:
    if get_current_user(request):
        return RedirectResponse(public_path(request, "/portal"), status_code=303)
    return render_template(request, "home.html")


@app.get("/login")
async def login_page(request: Request) -> HTMLResponse:
    if get_current_user(request):
        return RedirectResponse(public_path(request, "/portal"), status_code=303)
    return render_template(request, "login.html", {"next_path": request.query_params.get("next") or ""})


@app.get("/register")
async def register_page(request: Request) -> HTMLResponse:
    if get_current_user(request):
        return RedirectResponse(public_path(request, "/portal"), status_code=303)
    return render_template(request, "register.html")


@app.get("/portal")
async def portal_page(request: Request) -> HTMLResponse:
    user = get_current_user(request)
    if not user:
        return RedirectResponse(public_path(request, "/login?next=/portal"), status_code=303)
    return render_template(request, "portal.html")


@app.get("/device")
async def device_page(request: Request) -> HTMLResponse:
    user_code = str(request.query_params.get("user_code") or "").strip().upper()
    if not user_code:
        raise HTTPException(status_code=400, detail="user_code ausente")
    if not get_current_user(request):
        return RedirectResponse(public_path(request, f"/login?next=/device?user_code={user_code}"), status_code=303)
    code = db.get_device_code_by_user_code(user_code)
    return render_template(request, "device_authorize.html", {"device_code_row": code, "user_code": user_code})


@app.get("/admin/login")
async def admin_login_page(request: Request) -> HTMLResponse:
    if has_admin_session(request):
        return RedirectResponse(public_path(request, "/admin"), status_code=303)
    return render_template(request, "admin_login.html")


@app.get("/admin")
async def admin_page(request: Request) -> HTMLResponse:
    if not has_admin_session(request):
        return RedirectResponse(public_path(request, "/admin/login"), status_code=303)
    return render_template(request, "admin.html")


@app.post("/api/register")
async def api_register(request: Request) -> JSONResponse:
    payload = await request.json()
    email = str(payload.get("email") or "").strip()
    password = str(payload.get("password") or "")
    name = str(payload.get("name") or "").strip()
    cpf = str(payload.get("cpf") or "").strip()
    if not email or "@" not in email:
        return JSONResponse({"ok": False, "error": "Informe um e-mail válido."}, status_code=400)
    if not name:
        return JSONResponse({"ok": False, "error": "Informe seu nome."}, status_code=400)
    if not is_reasonable_password(password):
        return JSONResponse({"ok": False, "error": "Use uma senha com pelo menos 8 caracteres, letras e números."}, status_code=400)
    try:
        user = db.create_user(email=email, password=password, name=name, cpf=cpf)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": f"Não foi possível criar a conta: {exc}"}, status_code=400)
    token = db.create_cookie_session(
        user_id=user["id"],
        kind="customer",
        user_agent=request.headers.get("user-agent") or "",
        remote_ip=get_remote_ip(request),
    )
    db.add_event("user.registered", "Nova conta criada no REDSEBIA", {"user_id": user["id"], "email": user["email"]})
    response = JSONResponse({"ok": True, "user": user, "redirect": public_path(request, "/portal")})
    set_user_cookie(response, token)
    return response


@app.post("/api/login")
async def api_login(request: Request) -> JSONResponse:
    payload = await request.json()
    user = db.authenticate_user(str(payload.get("email") or ""), str(payload.get("password") or ""))
    if not user:
        return JSONResponse({"ok": False, "error": "Credenciais inválidas."}, status_code=401)
    token = db.create_cookie_session(
        user_id=user["id"],
        kind="customer",
        user_agent=request.headers.get("user-agent") or "",
        remote_ip=get_remote_ip(request),
    )
    db.add_event("user.login", "Usuario autenticado", {"user_id": user["id"], "email": user["email"]})
    response = JSONResponse({"ok": True, "user": user, "redirect": public_path(request, "/portal")})
    set_user_cookie(response, token)
    return response


@app.post("/api/logout")
async def api_logout(request: Request) -> JSONResponse:
    token = request.cookies.get(COOKIE_USER) or ""
    if token:
        db.revoke_cookie_session(token, "customer")
    response = JSONResponse({"ok": True})
    clear_user_cookie(response)
    return response


@app.post("/api/admin/login")
async def api_admin_login(request: Request) -> JSONResponse:
    payload = await request.json()
    password = str(payload.get("password") or "")
    if not constant_equals(password, settings.admin_password):
        return JSONResponse({"ok": False, "error": "Senha inválida."}, status_code=401)
    db.add_event("admin.login", "Operador entrou no painel admin", {"remote_ip": get_remote_ip(request)})
    response = JSONResponse({"ok": True, "redirect": public_path(request, "/admin")})
    set_admin_cookie(response)
    return response


@app.post("/api/admin/logout")
async def api_admin_logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    clear_admin_cookie(response)
    return response


@app.get("/api/bootstrap")
async def api_bootstrap(request: Request) -> dict[str, Any]:
    user = require_user(request)
    return {
        "user": user,
        "wallet": db.get_wallet(user["id"]),
        "charges": db.list_charges(user_id=user["id"], limit=20),
        "ledger": db.list_wallet_ledger(user["id"], limit=20),
        "client_sessions": db.list_client_sessions(user_id=user["id"], limit=12),
        "providers": [
            {
                "code": item["code"],
                "name": normalized_provider_display_name(item["code"], item["display_name"]),
                "supported_methods": next(meta["supported_methods"] for meta in provider_definitions() if meta["code"] == item["code"]),
            }
            for item in db.list_provider_configs()
            if item["enabled"] and next(meta["implemented"] for meta in provider_definitions() if meta["code"] == item["code"])
        ],
        "device_authorize_url": public_path(request, "/device"),
        "red_cli_hint": "red login",
    }


@app.get("/api/admin/bootstrap")
async def api_admin_bootstrap(request: Request) -> dict[str, Any]:
    require_admin(request)
    return {
        "stats": db.stats(),
        "providers": _provider_admin_view(),
        "users": db.list_users()[:80],
        "charges": db.list_charges(limit=80),
        "client_sessions": db.list_client_sessions(limit=80),
        "events": db.list_events(limit=80),
        "public_base_url": settings.public_base_url,
        "webhook_urls": {meta["code"]: public_path_placeholder(f"/api/payments/webhooks/{meta['code']}") for meta in provider_definitions()},
    }


@app.post("/api/topups")
async def api_create_topup(request: Request) -> JSONResponse:
    user = require_user(request)
    payload = await request.json()
    provider_code = str(payload.get("provider_code") or "").strip()
    amount_cents = int(float(payload.get("amount_brl") or 0) * 100)
    if amount_cents < 100:
        return JSONResponse({"ok": False, "error": "O valor mínimo é R$ 1,00."}, status_code=400)
    config = db.get_provider_config(provider_code)
    if not config or not config["enabled"]:
        return JSONResponse({"ok": False, "error": "Método indisponível no momento."}, status_code=400)
    charge = db.create_charge(
        user_id=user["id"],
        provider_code=provider_code,
        method="pix",
        amount_cents=amount_cents,
        description=f"Crédito REDSEBIA para {user['email']}",
    )
    try:
        provider = get_provider(provider_code)
        provider_payload = await provider.create_charge(
            config["settings"],
            ChargeRequest(charge_id=charge["id"], user=user, amount_cents=amount_cents, description=charge["description"], public_base_url=settings.public_base_url),
        )
        charge = db.update_charge_provider_payload(charge["id"], provider_payload)
        if provider_code == "sandbox_pix" and bool(config["settings"].get("auto_credit")):
            charge = db.update_charge_provider_payload(charge["id"], {"status": "paid", "paid_at": time.time()})
    except Exception as exc:
        db.add_event("topup.error", "Falha ao criar cobrança", {"charge_id": charge["id"], "provider_code": provider_code, "error": str(exc)})
        return JSONResponse({"ok": False, "error": str(exc), "charge": charge}, status_code=400)
    db.add_event("topup.created", "Cobrança criada", {"charge_id": charge["id"], "provider_code": provider_code, "user_id": user["id"]})
    return JSONResponse({"ok": True, "charge": charge})


@app.post("/api/topups/{charge_id}/refresh")
async def api_refresh_topup(charge_id: str, request: Request) -> JSONResponse:
    user = require_user(request)
    charge = db.get_charge(charge_id)
    if not charge or charge["user_id"] != user["id"]:
        return JSONResponse({"ok": False, "error": "Cobrança não encontrada."}, status_code=404)
    config = db.get_provider_config(charge["provider_code"]) or {"settings": {}}
    provider = get_provider(charge["provider_code"])
    try:
        payload = await provider.refresh_charge(config["settings"], charge)
        if payload:
            charge = db.update_charge_provider_payload(charge_id, payload)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc), "charge": charge}, status_code=400)
    return JSONResponse({"ok": True, "charge": charge})


@app.post("/api/topups/{charge_id}/sandbox/confirm")
async def api_confirm_sandbox_topup(charge_id: str, request: Request) -> JSONResponse:
    user = require_user(request)
    charge = db.get_charge(charge_id)
    if not charge or charge["user_id"] != user["id"]:
        return JSONResponse({"ok": False, "error": "Cobrança não encontrada."}, status_code=404)
    if charge["provider_code"] != "sandbox_pix":
        return JSONResponse({"ok": False, "error": "Este método não permite confirmação manual por aqui."}, status_code=400)
    charge = db.update_charge_provider_payload(charge_id, {"status": "paid", "paid_at": time.time()})
    db.add_event("topup.sandbox_confirmed", "Pagamento confirmado", {"charge_id": charge_id, "user_id": user["id"]})
    return JSONResponse({"ok": True, "charge": charge, "wallet": db.get_wallet(user["id"])})


@app.post("/api/admin/providers/{provider_code}")
async def api_admin_save_provider(provider_code: str, request: Request) -> JSONResponse:
    require_admin(request)
    payload = await request.json()
    meta = next((item for item in provider_definitions() if item["code"] == provider_code), None)
    if not meta:
        return JSONResponse({"ok": False, "error": "Método não encontrado."}, status_code=404)
    current = db.get_provider_config(provider_code) or {
        "settings": {},
        "display_name": normalized_provider_display_name(provider_code, meta["name"]),
        "enabled": False,
    }
    settings_payload = dict(current["settings"])
    for field in meta["config_fields"]:
        value = payload.get(field["name"])
        if field["type"] == "checkbox":
            settings_payload[field["name"]] = bool(value)
        elif field["type"] == "password":
            if value and value != "********":
                settings_payload[field["name"]] = str(value)
        elif value is not None:
            settings_payload[field["name"]] = value
    enabled = bool(payload.get("enabled"))
    display_name = normalized_provider_display_name(
        provider_code,
        str(payload.get("display_name") or current["display_name"] or meta["name"]).strip(),
    )
    db.upsert_provider_config(provider_code, display_name, enabled, settings_payload)
    db.add_event("admin.provider.updated", "Método atualizado no REDSEBIA", {"provider_code": provider_code, "enabled": enabled})
    return JSONResponse({"ok": True, "provider": next(item for item in _provider_admin_view() if item["code"] == provider_code)})


@app.post("/api/admin/charges/{charge_id}/mark-paid")
async def api_admin_mark_paid(charge_id: str, request: Request) -> JSONResponse:
    require_admin(request)
    charge = db.get_charge(charge_id)
    if not charge:
        return JSONResponse({"ok": False, "error": "Cobrança não encontrada."}, status_code=404)
    charge = db.update_charge_provider_payload(charge_id, {"status": "paid", "paid_at": time.time()})
    db.add_event("admin.charge.paid", "Cobrança marcada como paga", {"charge_id": charge_id})
    return JSONResponse({"ok": True, "charge": charge})


@app.post("/api/admin/charges/{charge_id}/expire")
async def api_admin_expire_charge(charge_id: str, request: Request) -> JSONResponse:
    require_admin(request)
    charge = db.get_charge(charge_id)
    if not charge:
        return JSONResponse({"ok": False, "error": "Cobrança não encontrada."}, status_code=404)
    charge = db.update_charge_provider_payload(charge_id, {"status": "expired"})
    db.add_event("admin.charge.expired", "Cobrança encerrada manualmente", {"charge_id": charge_id})
    return JSONResponse({"ok": True, "charge": charge})


@app.post("/api/device/start")
async def api_device_start(request: Request) -> dict[str, Any]:
    payload = await request.json()
    device = db.create_device_code(
        client_name=str(payload.get("client_name") or "RED CLI"),
        scope=str(payload.get("scope") or "red.runtime"),
        ttl_seconds=settings.device_code_ttl_seconds,
    )
    return {
        **device,
        "verification_url": public_path_placeholder("/device"),
        "verification_uri_complete": f"{public_path_placeholder('/device')}?user_code={device['user_code']}",
        "interval": 3,
    }


@app.post("/api/device/poll")
async def api_device_poll(request: Request) -> JSONResponse:
    payload = await request.json()
    device_code = str(payload.get("device_code") or "").strip()
    if not device_code:
        return JSONResponse({"ok": False, "error": "device_code ausente"}, status_code=400)
    row = db.poll_device_code(device_code)
    if not row:
        return JSONResponse({"ok": False, "error": "invalid_device_code"}, status_code=404)
    if row["expires_at"] <= time.time():
        return JSONResponse({"ok": False, "status": "expired"}, status_code=400)
    if row["status"] == "pending":
        return JSONResponse({"ok": True, "status": "pending"})
    if row["status"] == "denied":
        return JSONResponse({"ok": True, "status": "denied"})
    if row["status"] == "approved" and row.get("access_token"):
        user = db.get_user(row["user_id"])
        return JSONResponse(
            {
                "ok": True,
                "status": "approved",
                "access_token": row["access_token"],
                "token_type": "bearer",
                "expires_at": row.get("token_expires_at"),
                "user": user,
                "wallet": db.get_wallet(row["user_id"]),
            }
        )
    return JSONResponse({"ok": True, "status": "consumed"})


@app.post("/api/device/approve")
async def api_device_approve(request: Request) -> JSONResponse:
    user = require_user(request)
    payload = await request.json()
    user_code = str(payload.get("user_code") or "").strip().upper()
    approved = db.approve_device_code(user_code, user["id"], settings.runtime_token_ttl_seconds)
    if not approved:
        return JSONResponse({"ok": False, "error": "Código inválido ou expirado."}, status_code=404)
    db.add_event("device.approved", "Login via dispositivo aprovado", {"user_id": user["id"], "user_code": user_code})
    return JSONResponse({"ok": True, "status": "approved"})


@app.post("/api/device/deny")
async def api_device_deny(request: Request) -> JSONResponse:
    require_user(request)
    payload = await request.json()
    user_code = str(payload.get("user_code") or "").strip().upper()
    db.deny_device_code(user_code)
    return JSONResponse({"ok": True, "status": "denied"})


@app.post("/api/payments/webhooks/{provider_code}")
async def api_provider_webhook(provider_code: str, request: Request) -> JSONResponse:
    payload = await request.json()
    provider = get_provider(provider_code)
    config = db.get_provider_config(provider_code) or {"settings": {}}
    event_id = str((payload.get("id") or (payload.get("data") or {}).get("id") or payload.get("txid") or "")).strip()
    db.record_webhook_event(provider_code, event_id or f"event-{time.time()}", "webhook", payload)
    try:
        result = await provider.handle_webhook(config["settings"], payload)
    except Exception as exc:
        db.add_event("webhook.error", "Falha ao processar webhook", {"provider_code": provider_code, "error": str(exc)})
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    if result:
        charge = None
        if result.get("provider_charge_id"):
            charge = db.find_charge_by_provider(provider_code, str(result["provider_charge_id"]))
        if not charge and result.get("external_reference"):
            charge = db.find_charge_by_external_reference(provider_code, str(result["external_reference"]))
        if charge:
            charge = db.update_charge_provider_payload(charge["id"], result)
            db.add_event("webhook.charge.updated", "Webhook atualizou cobrança", {"provider_code": provider_code, "charge_id": charge["id"]})
    return JSONResponse({"ok": True})


@app.get("/api/runtime/me")
async def api_runtime_me(request: Request) -> dict[str, Any]:
    session = require_runtime_token(request)
    return {"user": session["user"], "wallet": db.get_wallet(session["user_id"])}


@app.get("/api/runtime/models")
async def api_runtime_models(request: Request) -> dict[str, Any]:
    require_runtime_token(request)
    return {"models": await _fetch_proxy_models()}


@app.get("/api/runtime/client-sessions")
async def api_runtime_list_client_sessions(request: Request) -> dict[str, Any]:
    session = require_runtime_token(request)
    return {"sessions": db.list_client_sessions(user_id=session["user_id"], limit=40)}


@app.post("/api/runtime/client-sessions/start")
async def api_runtime_client_start(request: Request) -> JSONResponse:
    session = require_runtime_token(request)
    payload = await request.json()
    row = db.create_client_session(
        session["user_id"],
        str(payload.get("device_name") or "Aplicativo REDSEBIA"),
        str(payload.get("client_version") or ""),
        str(payload.get("exam_ref") or ""),
        payload.get("metadata") or {},
    )
    db.add_event("runtime.client.start", "Sessão do cliente iniciada", {"user_id": session["user_id"], "client_session_id": row["id"]})
    return JSONResponse({"ok": True, "session": row})


@app.post("/api/runtime/client-sessions/{client_session_id}/heartbeat")
async def api_runtime_client_heartbeat(client_session_id: str, request: Request) -> JSONResponse:
    session = require_runtime_token(request)
    payload = await request.json()
    row = db.heartbeat_client_session(client_session_id, payload.get("metadata") or {})
    if row["user_id"] != session["user_id"]:
        raise HTTPException(status_code=403, detail="Sessão não pertence ao usuário")
    return JSONResponse({"ok": True, "session": row})


@app.post("/api/runtime/client-sessions/{client_session_id}/stop")
async def api_runtime_client_stop(client_session_id: str, request: Request) -> JSONResponse:
    session = require_runtime_token(request)
    payload = await request.json()
    row = db.stop_client_session(client_session_id, payload.get("metadata") or {})
    if row["user_id"] != session["user_id"]:
        raise HTTPException(status_code=403, detail="Sessão não pertence ao usuário")
    db.add_event("runtime.client.stop", "Sessão do cliente finalizada", {"user_id": session["user_id"], "client_session_id": row["id"]})
    return JSONResponse({"ok": True, "session": row})


@app.post("/api/runtime/launch/authorize")
async def api_runtime_launch_authorize(request: Request) -> dict[str, Any]:
    session = require_runtime_token(request)
    wallet = db.get_wallet(session["user_id"])
    allowed = wallet["balance_cents"] >= settings.min_launch_balance_cents
    return {
        "ok": True,
        "allowed": allowed,
        "wallet": wallet,
        "min_balance_cents": settings.min_launch_balance_cents,
        "runtime": {
            "reserve_url": public_path_placeholder("/api/runtime/analysis/reserve"),
            "settle_url": public_path_placeholder("/api/runtime/analysis/settle"),
            "release_url": public_path_placeholder("/api/runtime/analysis/release"),
            "me_url": public_path_placeholder("/api/runtime/me"),
        },
    }


@app.post("/api/runtime/analysis/reserve")
async def api_runtime_reserve(request: Request) -> JSONResponse:
    session = require_runtime_token(request)
    payload = await request.json()
    reserved_cents = int(payload.get("reserved_cents") or settings.default_hold_cents)
    if reserved_cents <= 0:
        return JSONResponse({"ok": False, "error": "reserved_cents inválido"}, status_code=400)
    description = str(payload.get("description") or "Reserva para analise REDSEBIA")
    metadata = payload.get("metadata") or {}
    try:
        reservation = db.create_reservation(session["user_id"], reserved_cents, description, metadata)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc), "wallet": db.get_wallet(session["user_id"])}, status_code=400)
    db.add_event("runtime.reserve", "Reserva criada para analise", {"user_id": session["user_id"], "reservation_id": reservation["id"], "reserved_cents": reserved_cents})
    return JSONResponse({"ok": True, "reservation": reservation, "wallet": db.get_wallet(session["user_id"])})


@app.post("/api/runtime/analysis/settle")
async def api_runtime_settle(request: Request) -> JSONResponse:
    session = require_runtime_token(request)
    payload = await request.json()
    reservation_id = str(payload.get("reservation_id") or "").strip()
    settled_cents = int(payload.get("settled_cents") or 0)
    if not reservation_id:
        return JSONResponse({"ok": False, "error": "reservation_id ausente"}, status_code=400)
    reservation = db.settle_reservation(reservation_id, settled_cents, payload.get("metadata") or {})
    db.add_event("runtime.settle", "Reserva liquidada", {"user_id": session["user_id"], "reservation_id": reservation_id, "settled_cents": settled_cents})
    return JSONResponse({"ok": True, "reservation": reservation, "wallet": db.get_wallet(session["user_id"])})


@app.post("/api/runtime/analysis/release")
async def api_runtime_release(request: Request) -> JSONResponse:
    session = require_runtime_token(request)
    payload = await request.json()
    reservation_id = str(payload.get("reservation_id") or "").strip()
    if not reservation_id:
        return JSONResponse({"ok": False, "error": "reservation_id ausente"}, status_code=400)
    reservation = db.release_reservation(reservation_id, str(payload.get("reason") or "Liberado pelo runtime"))
    db.add_event("runtime.release", "Reserva liberada", {"user_id": session["user_id"], "reservation_id": reservation_id})
    return JSONResponse({"ok": True, "reservation": reservation, "wallet": db.get_wallet(session["user_id"])})


def _normalize_checkbox(value: Any) -> bool:
    return bool(value) and str(value).lower() not in {"false", "0", "off", "no"}


def main() -> None:
    os.environ.setdefault("PYTHONPATH", str(Path(__file__).resolve().parents[1]))
    uvicorn.run("redsebia.app:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    main()
