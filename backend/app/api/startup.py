"""M2 routes. Blocking DB/hash work stays in FastAPI's synchronous worker handlers."""

import math
import time
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.infrastructure.database import transaction
from app.repositories.business import BusinessRepository
from app.services.business import BusinessService
from app.services.errors import PosError, unauthenticated, unavailable
from app.services.startup import Result, StartupService

router = APIRouter()
Code = Annotated[str, Field(strict=True, pattern=r"^[A-Za-z0-9_-]{1,32}$")]
UUID = Annotated[
    str,
    Field(
        strict=True,
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    ),
]


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    staff_id: Code
    password: str = Field(repr=False)


def respond(result: Result) -> JSONResponse:
    response = JSONResponse(result.body, headers={"Cache-Control": "no-store"})
    for name, value, max_age in (
        (
            "__Host-pos_session",
            result.auth_cookie,
            max(0, math.floor(result.auth_max_age - (time.monotonic() - result.issued_at))),
        ),
        ("__Host-pos_resume", result.resume_cookie, 2592000),
    ):
        if value is not None:
            response.set_cookie(
                name, value, max_age=max_age, secure=True, httponly=True, samesite="lax", path="/"
            )
    return response


def run(
    request: Request, action: Callable[[StartupService], Result | None], *, readonly: bool = False
) -> JSONResponse:
    if request.app.state.engine is None:
        raise unavailable()
    with transaction(request.app.state.engine, readonly=readonly) as connection:
        service = BusinessService(BusinessRepository(connection), request.app.state.passwords)
        result = action(service)
    # COMMIT must succeed first, including a credential failure's rate-limit record.
    if result is None:
        raise unauthenticated()
    return respond(result)


def cookies(request: Request) -> tuple[str | None, str | None]:
    return request.cookies.get("__Host-pos_session"), request.cookies.get("__Host-pos_resume")


@router.post("/api/login")
@router.post("/api/reauth")
def login(request: Request, body: Credentials) -> JSONResponse:
    return run(request, lambda s: s.login(body.staff_id, body.password, cookies(request)[1]))


@router.get("/api/auth/status")
def auth_status(request: Request) -> JSONResponse:
    return run(request, lambda s: s.status(cookies(request)[0]), readonly=True)


@router.get("/api/register/status")
def register_status(request: Request) -> JSONResponse:
    return run(request, lambda s: s.inspect_register(*cookies(request)), readonly=True)


@router.post("/api/register/start")
def start(request: Request) -> JSONResponse:
    return run(request, lambda s: s.start(*cookies(request)))


@router.post("/api/register/confirm")
def confirm(request: Request) -> JSONResponse:
    return run(request, lambda s: s.confirm(*cookies(request)))


@router.post("/api/carts")
def create_cart(request: Request) -> JSONResponse:
    return run(request, lambda s: s.get_cart(*cookies(request), create=True))


@router.get("/api/resume")
def resume(request: Request) -> JSONResponse:
    return run(request, lambda s: s.get_cart(*cookies(request)), readonly=True)


@router.get("/api/products/{code}")
def product(request: Request, code: Code) -> JSONResponse:
    def action(service: StartupService) -> Result:
        register = service.register(lock=False)
        session = service.authenticate(register, cookies(request)[0], service.repo.now())
        service.context(register, session["staff_id"], cookies(request)[1], service.repo.now())
        row = service.repo.product(code)
        if row is None:
            raise PosError(404, "PRODUCT_NOT_FOUND", "商品が登録されていません。")
        return Result(
            {"code": row["code"], "name": row["name"], "unit_price": str(row["unit_price"])}
        )

    return run(request, action, readonly=True)


@router.get("/api/members/{code}")
def member(request: Request, code: Code) -> JSONResponse:
    def action(service: StartupService) -> Result:
        register = service.register(lock=False)
        session = service.authenticate(register, cookies(request)[0], service.repo.now())
        service.context(register, session["staff_id"], cookies(request)[1], service.repo.now())
        row = service.repo.member(code)
        if row is None:
            raise PosError(404, "MEMBER_NOT_FOUND", "会員が登録されていません。")
        return Result({"member_id": row["member_id"], "confirmed": True})

    return run(request, action, readonly=True)
