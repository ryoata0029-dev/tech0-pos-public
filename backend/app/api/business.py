"""M3 authenticated routes. Each phase commits before the next transaction."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.startup import UUID, Code, cookies, respond
from app.infrastructure.database import transaction
from app.infrastructure.diagnostics import context
from app.repositories.business import BusinessRepository
from app.services.business import BusinessService
from app.services.errors import PosError, unavailable
from app.services.startup import Result
from app.services.validation import parse_internal_id

router = APIRouter()
Version = Annotated[str, Field(strict=True, pattern=r"^[1-9][0-9]{0,19}$")]


class OperationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    operation_id: UUID
    version: Version

    @field_validator("version")
    @classmethod
    def valid_version(cls, value: str) -> str:
        parse_internal_id(value)
        return value


class AddLine(OperationInput):
    code: Code


class SetQuantity(OperationInput):
    quantity: int = Field(strict=True, ge=1, le=99)


class SetMember(OperationInput):
    member_id: Code | None


class PurchaseInput(OperationInput):
    cart_id: UUID


def phase(
    request: Request, action: Callable[[BusinessService], Result], *, readonly: bool = False
) -> Result:
    if request.app.state.engine is None:
        raise unavailable()
    with transaction(request.app.state.engine, readonly=readonly) as connection:
        result = action(
            BusinessService(BusinessRepository(connection), request.app.state.passwords)
        )
    state = context.get()
    if state is not None:
        state["result_code"] = result.body.get("code") or result.body.get("operation_status", "OK")
    return result


def response(result: Result) -> JSONResponse:
    if result.body.get("operation_status") == "REJECTED":
        code = result.body["code"]
        status = (
            404
            if code in ("PRODUCT_NOT_FOUND", "MEMBER_NOT_FOUND", "LINE_NOT_FOUND")
            else 422
            if code in ("QUANTITY_LIMIT", "AMOUNT_INVALID")
            else 409
        )
        # Rejection is emitted after the operation record COMMIT, never inside its TX.
        raise PosError(
            status,
            code,
            {
                "PRODUCT_NOT_FOUND": "商品が登録されていません。",
                "MEMBER_NOT_FOUND": "会員が見つかりません。再入力または非会員を選択してください。",
                "QUANTITY_LIMIT": "数量は99個までです。",
            }.get(code, "操作を停止しました。状態を確認してください。"),
        )
    reply = respond(result)
    if result.body.get("operation_status") == "PREPARED":
        reply.status_code = 202
    return reply


def payload(body: OperationInput, **extra: str) -> dict[str, object]:
    return {k: v for k, v in body.model_dump().items() if k != "operation_id"} | extra


@router.post("/api/carts/{cart_id}/lines")
def add_line(request: Request, cart_id: UUID, body: AddLine) -> JSONResponse:
    return response(
        phase(
            request,
            lambda s: s.edit(
                *cookies(request), cart_id, body.operation_id, "ADD_LINE", payload(body)
            ),
        )
    )


@router.patch("/api/carts/{cart_id}/lines/{line_id}")
def set_quantity(request: Request, cart_id: UUID, line_id: UUID, body: SetQuantity) -> JSONResponse:
    return response(
        phase(
            request,
            lambda s: s.edit(
                *cookies(request),
                cart_id,
                body.operation_id,
                "SET_QUANTITY",
                payload(body, line_id=line_id),
            ),
        )
    )


@router.delete("/api/carts/{cart_id}/lines/{line_id}")
def delete_line(
    request: Request,
    cart_id: UUID,
    line_id: UUID,
    operation_id: Annotated[UUID, Query()],
    version: Annotated[Version, Query()],
) -> JSONResponse:
    try:
        body = OperationInput(operation_id=operation_id, version=version)
    except ValueError:
        raise PosError(422, "INVALID_INPUT", "入力形式を確認してください。") from None
    return response(
        phase(
            request,
            lambda s: s.edit(
                *cookies(request),
                cart_id,
                operation_id,
                "DELETE_LINE",
                payload(body, line_id=line_id),
            ),
        )
    )


@router.post("/api/carts/{cart_id}/sync")
def sync(request: Request, cart_id: UUID, body: OperationInput) -> JSONResponse:
    return response(
        phase(
            request,
            lambda s: s.edit(*cookies(request), cart_id, body.operation_id, "SYNC", payload(body)),
        )
    )


@router.put("/api/carts/{cart_id}/member")
def set_member(request: Request, cart_id: UUID, body: SetMember) -> JSONResponse:
    value = payload(body)
    result = phase(
        request, lambda s: s.prepare_member(*cookies(request), cart_id, body.operation_id, value)
    )
    if result.continue_member:
        # Lookup is outside update locks and cannot itself confirm the cart member.
        found = phase(
            request, lambda s: lookup_member(s, request, cart_id, body.member_id), readonly=True
        ).body["found"]
        result = phase(
            request,
            lambda s: s.finish_member(*cookies(request), cart_id, body.operation_id, value, found),
        )
    return response(result)


def lookup_member(
    service: BusinessService, request: Request, cart_id: str, member_id: str | None
) -> Result:
    service.access(*cookies(request), cart_id, lock=False)
    return Result({"found": member_id is not None and service.repo.member(member_id) is not None})


@router.post("/api/purchases")
def purchase(request: Request, body: PurchaseInput) -> JSONResponse:
    value = payload(body)
    result = phase(
        request,
        lambda s: s.prepare_purchase(*cookies(request), body.cart_id, body.operation_id, value),
    )
    if result.body["operation_status"] == "PREPARED":
        result = phase(
            request,
            lambda s: s.finish_purchase(*cookies(request), body.cart_id, body.operation_id, value),
        )
    return response(result)


@router.post("/api/carts/{cart_id}/next")
def next_cart(request: Request, cart_id: UUID, body: OperationInput) -> JSONResponse:
    return response(
        phase(
            request,
            lambda s: s.next_cart(*cookies(request), cart_id, body.operation_id, payload(body)),
        )
    )


@router.get("/api/carts/{cart_id}")
@router.get("/api/carts/{cart_id}/purchase")
def get_cart(request: Request, cart_id: UUID) -> JSONResponse:
    return respond(phase(request, lambda s: s.read(*cookies(request), cart_id), readonly=True))


@router.get("/api/carts/{cart_id}/operations/{operation_id}")
def get_operation(request: Request, cart_id: UUID, operation_id: UUID) -> JSONResponse:
    return respond(
        phase(request, lambda s: s.read(*cookies(request), cart_id, operation_id), readonly=True)
    )


@router.post("/api/carts/{cart_id}/resolve-purchase")
def resolve_purchase(request: Request, cart_id: UUID, body: OperationInput) -> JSONResponse:
    return response(
        phase(
            request,
            lambda s: s.resolve_purchase(
                *cookies(request), cart_id, body.operation_id, payload(body)
            ),
        )
    )


@router.post("/api/carts/{cart_id}/reopen")
def reopen(request: Request, cart_id: UUID, body: OperationInput) -> JSONResponse:
    return response(
        phase(
            request,
            lambda s: s.reopen(*cookies(request), cart_id, body.operation_id, payload(body)),
        )
    )
