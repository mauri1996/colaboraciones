"""Punto de entrada: panel y bot de Telegram."""

from contextlib import asynccontextmanager
import logging

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from telegram.ext import Application

from app.bot import build_application, start_polling, stop_polling
from app.config import get_settings
from app.db import init_db, ping_db
from app.models import Base
from app.services.household import seed_household
from app.web.routes import router as web_router

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await seed_household()
    app.state.bot_running = False
    bot_app: Application | None = None
    if settings.enable_bot and settings.telegram_configured:
        bot_app = build_application()
        await start_polling(bot_app)
        app.state.bot_running = True
    yield
    if bot_app is not None:
        await stop_polling(bot_app)
        app.state.bot_running = False


app = FastAPI(title="Contabilizador", lifespan=lifespan)
app.include_router(web_router)


def _checks(db_ok: bool, bot_running: bool) -> dict:
    return {
        "app": True,
        "database": db_ok,
        "telegram_token": settings.telegram_configured,
        "gemini_key": settings.gemini_configured,
        "bot_enabled": settings.enable_bot,
        "bot_running": bot_running,
        "tables": sorted(Base.metadata.tables.keys()),
    }


@app.get("/health")
async def health(request: Request) -> JSONResponse:
    db_ok = False
    try:
        db_ok = await ping_db()
    except Exception:
        db_ok = False
    bot_running = bool(getattr(request.app.state, "bot_running", False))
    checks = _checks(db_ok, bot_running)
    status = "ok" if db_ok else "degraded"
    return JSONResponse(
        {
            "status": status,
            "phase": 11,
            "bot": settings.telegram_bot_username,
            "checks": checks,
        }
    )


def run() -> None:
    uvicorn.run(
        "app.main:app",
        host=settings.web_host,
        port=settings.web_port,
        reload=False,
    )


if __name__ == "__main__":
    run()
