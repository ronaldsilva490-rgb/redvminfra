import hashlib
import hmac
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .ai import RedSystemsAI
from .config import PUBLIC_DIR, settings
from .db import Database
from .market import BinanceMarketClient
from .news import NewsClient
from .runtime import TraderRuntime


db = Database(settings.db_path)
runtime = TraderRuntime(
    db=db,
    market=BinanceMarketClient(settings.binance_base_url),
    news=NewsClient(),
    ai=RedSystemsAI(settings.proxy_url),
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await runtime.start()
    try:
        yield
    finally:
        await runtime.stop()
        await runtime.iq_extension_adapter.close()
        await runtime.iq_bridge.close()
        await runtime.platforms.close()
        await runtime.market.close()
        await runtime.news_client.close()
        await runtime.ai.close()


app = FastAPI(title="RED Trader Painel", version="0.1.0", lifespan=lifespan)


def session_token() -> str:
    return hmac.new(settings.secret.encode("utf-8"), settings.password.encode("utf-8"), hashlib.sha256).hexdigest()


def has_session(request: Request) -> bool:
    token = request.cookies.get("redtrader_session") or ""
    return hmac.compare_digest(token, session_token())


def public_path(request: Request, path: str) -> str:
    prefix = str(request.headers.get("x-forwarded-prefix") or "").rstrip("/")
    return f"{prefix}{path}" if prefix else path


def websocket_has_session(websocket: WebSocket) -> bool:
    token = websocket.cookies.get("redtrader_session") or ""
    return hmac.compare_digest(token, session_token())


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    public_paths = {"/login", "/api/login", "/healthz", "/favicon.ico", "/assets/logo.png"}
    if path in public_paths:
        return await call_next(request)
    if has_session(request):
        return await call_next(request)
    if path.startswith("/api/"):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return RedirectResponse(public_path(request, "/login"), status_code=303)


app.mount("/assets", StaticFiles(directory=PUBLIC_DIR / "assets"), name="assets")


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    return {"ok": True, "running": runtime.running}


@app.get("/favicon.ico")
async def favicon() -> FileResponse:
    return FileResponse(PUBLIC_DIR / "favicon.ico")


@app.get("/login")
async def login_page(request: Request) -> Response:
    if has_session(request):
        return RedirectResponse(public_path(request, "/"), status_code=303)
    return FileResponse(PUBLIC_DIR / "login.html")


@app.post("/api/login")
async def login(request: Request) -> JSONResponse:
    payload = await request.json()
    if not hmac.compare_digest(str(payload.get("password") or ""), settings.password):
        return JSONResponse({"ok": False, "error": "Senha invalida"}, status_code=401)
    response = JSONResponse({"ok": True})
    response.set_cookie(
        "redtrader_session",
        session_token(),
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=60 * 60 * 24 * 30,
    )
    return response


@app.post("/api/logout")
async def logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.delete_cookie("redtrader_session")
    return response


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(PUBLIC_DIR / "index.html")


@app.get("/styles.css")
async def styles() -> FileResponse:
    return FileResponse(PUBLIC_DIR / "styles.css")


@app.get("/app.js")
async def app_js() -> FileResponse:
    return FileResponse(PUBLIC_DIR / "app.js")


@app.get("/api/status")
async def status() -> dict[str, Any]:
    return runtime.status()


@app.post("/api/config")
async def save_config(request: Request) -> dict[str, Any]:
    payload = await request.json()
    return {"ok": True, "config": runtime.update_config(payload)}


@app.post("/api/paper/reset")
async def reset_paper(request: Request) -> dict[str, Any]:
    payload = await request.json()
    balance = float(payload.get("balance_brl") or runtime.config().get("initial_balance_brl", 50))
    db.reset_paper(balance)
    config = runtime.update_config({"initial_balance_brl": balance})
    runtime.publish("paper:reset", "Saldo paper reiniciado", {"balance_brl": balance})
    return {"ok": True, "wallet": runtime.wallet_summary(), "config": config}


@app.post("/api/run-once")
async def run_once() -> dict[str, Any]:
    await runtime.cycle(reason="manual")
    return {"ok": True, "status": runtime.status()}


@app.get("/api/models")
async def models() -> dict[str, Any]:
    runtime.models = await runtime.ai.list_models()
    return {"models": runtime.models}


@app.post("/api/platforms/refresh")
async def refresh_platforms() -> dict[str, Any]:
    return {"ok": True, "platforms": await runtime.refresh_platforms()}


@app.post("/api/iq-extension/command")
async def iq_extension_command(request: Request) -> dict[str, Any]:
    payload = await request.json()
    result = await runtime.enqueue_iq_extension_command(
        str(payload.get("command") or "").strip(),
        payload.get("payload") or {},
        str(payload.get("session_id") or "").strip(),
    )
    return {"ok": True, "command": result}


@app.websocket("/ws")
async def websocket_events(websocket: WebSocket) -> None:
    if not websocket_has_session(websocket):
        await websocket.close(code=4401)
        return
    await websocket.accept()
    queue = runtime.subscribe()
    try:
        await websocket.send_json({"type": "status", "data": runtime.status()})
        while True:
            event = await queue.get()
            if event.get("_ws_type") == "status":
                await websocket.send_json({"type": "status", "data": event["data"]})
            else:
                await websocket.send_json({"type": "event", "data": event})
    except WebSocketDisconnect:
        pass
    except RuntimeError:
        pass
    finally:
        runtime.unsubscribe(queue)


def main() -> None:
    os.environ.setdefault("PYTHONPATH", str(Path(__file__).resolve().parents[1]))
    uvicorn.run("redtrader.app:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    main()
