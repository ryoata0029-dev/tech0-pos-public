"""Fail-closed startup: no schema creation and no implicit development credentials."""

import re
import secrets
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.responses import Response

from app.api.business import router as business_router
from app.api.startup import router
from app.infrastructure.database import create_database
from app.infrastructure.diagnostics import context, event
from app.infrastructure.settings import Settings
from app.security.credentials import Passwords
from app.services.errors import PosError, forbidden, unavailable


def error_response(error: PosError) -> JSONResponse:
    return JSONResponse(
        {"code": error.code, "message": error.message},
        status_code=error.status,
        headers={"Cache-Control": "no-store"},
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        try:
            configured = settings or Settings.from_env()
            application.state.settings = configured
            application.state.engine = create_database(configured)
            application.state.passwords = Passwords()
        except (ValueError, OSError):
            # A missing configuration never enables an unprotected development mode.
            application.state.engine = None
        try:
            yield
        finally:
            if application.state.engine is not None:
                application.state.engine.dispose()

    app = FastAPI(
        title="Tech0 POS", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
    )
    app.state.settings = settings
    app.state.engine = None
    app.state.passwords = None

    @app.exception_handler(PosError)
    async def domain_error(request: Request, exc: PosError) -> JSONResponse:
        state = context.get()
        if state is not None:
            state["result_code"] = exc.code
        return error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, exc: RequestValidationError) -> JSONResponse:
        state = context.get()
        if state is not None:
            state["result_code"] = "INVALID_INPUT"
        # Do not serialize Pydantic's input/context, which can include passwords.
        return error_response(PosError(422, "INVALID_INPUT", "入力形式を確認してください。"))

    @app.middleware("http")
    async def guard(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        try:
            if request.url.path.startswith("/api/"):
                configured = app.state.settings
                if configured is None:
                    return error_response(unavailable())
                relay = request.headers.getlist("x-pos-relay")
                if (
                    len(relay) != 1
                    or not relay[0].isascii()
                    or not secrets.compare_digest(relay[0], configured.relay_secret)
                ):
                    return error_response(forbidden())
                if request.method not in ("GET", "HEAD", "OPTIONS"):
                    if request.headers.getlist("origin") != [
                        configured.origin
                    ] or request.headers.getlist("x-pos-request") != ["1"]:
                        return error_response(forbidden())
                # All current GET and bodyless POST operations reject hidden inputs.
                if request.query_params and request.method != "DELETE":
                    return error_response(PosError(422, "INVALID_INPUT", "未定義の入力です。"))
                if request.method == "DELETE":
                    if (
                        set(request.query_params) != {"operation_id", "version"}
                        or len(request.query_params.multi_items()) != 2
                        or await request.body()
                    ):
                        return error_response(
                            PosError(422, "INVALID_INPUT", "削除の入力形式を確認してください。")
                        )
                if request.method in ("GET", "HEAD") or request.url.path in (
                    "/api/register/start",
                    "/api/register/confirm",
                    "/api/carts",
                ):
                    if await request.body():
                        return error_response(
                            PosError(422, "INVALID_INPUT", "本文は指定できません。")
                        )
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            return response
        except Exception:
            # A sanitized response also suppresses SQL/parameters in default exception logs.
            return error_response(unavailable())

    @app.get("/health", include_in_schema=False)
    @app.get("/", include_in_schema=False)
    async def health() -> JSONResponse:
        # Always On and platform probes never access DB or extend business deadlines.
        return JSONResponse({"status": "alive"}, headers={"Cache-Control": "no-store"})

    @app.middleware("http")
    async def diagnostics(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        state: dict[str, str] = {}
        token = context.set(state)
        request_id = str(uuid4())
        started = time.monotonic()
        status = 503
        try:
            if request.url.path.startswith("/api/"):
                # Read only the correlation identifier; never log body or parse errors.
                try:
                    candidate = (
                        request.query_params.get("operation_id")
                        if request.method == "DELETE"
                        else (await request.json()).get("operation_id")
                    )
                    if isinstance(candidate, str) and re.fullmatch(
                        r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
                        candidate,
                    ):
                        state["operation_id"] = candidate
                except Exception:
                    pass
            response = await call_next(request)
            status = response.status_code
            response.headers["X-POS-Request-ID"] = request_id
            return response
        finally:
            route = getattr(request.scope.get("route"), "path", "UNKNOWN_ROUTE")
            candidate = request.path_params.get("operation_id")
            if isinstance(candidate, str) and re.fullmatch(
                r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", candidate
            ):
                state["operation_id"] = candidate
            if route not in ("/health", "/") or status >= 400:
                event(
                    request_id=request_id,
                    route=route,
                    elapsed_ms=(time.monotonic() - started) * 1000,
                    status=status,
                    state=state,
                )
            context.reset(token)

    app.include_router(router)
    app.include_router(business_router)
    return app


app = create_app()
