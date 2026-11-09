"""
server/app.py — FastAPI-приложение.

Запуск:
    uvicorn server.app:app --host 0.0.0.0 --port 8000
Swagger UI:
    http://localhost:8000/docs
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.errors import ApiAuthError, ApiRateLimitError
from server.deps import get_state
from server.routes import batch, characters, history, meta, recipes

log = logging.getLogger("stalcraft.api")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Stalcraft Crafting Calculator API",
        version="1.0.0",
        description=(
            "HTTP-обёртка над CLI-калькулятором крафта. "
            "Эндпоинты повторяют команды `main.py recipe|batch|history|character|exclusions`."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],   # для dev; в продакшене сузить
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(meta.router, prefix="/api")
    app.include_router(recipes.router, prefix="/api")
    app.include_router(batch.router, prefix="/api")
    app.include_router(history.router, prefix="/api")
    app.include_router(characters.router, prefix="/api")

    @app.exception_handler(ApiAuthError)
    async def _auth_err(_req: Request, exc: ApiAuthError):
        # токен протух — сбрасываем, следующий запрос получит новый
        get_state().invalidate_token()
        return JSONResponse(status_code=401, content={"error": str(exc)})

    @app.exception_handler(ApiRateLimitError)
    async def _rate_err(_req: Request, exc: ApiRateLimitError):
        return JSONResponse(status_code=429, content={"error": str(exc)})

    @app.on_event("shutdown")
    def _shutdown():
        get_state().shutdown()

    return app


app = create_app()