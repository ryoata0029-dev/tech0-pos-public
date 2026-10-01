"""M3 cart operations, two-phase member/purchase and atomic next transaction."""

import copy
import json
from datetime import datetime
from uuid import uuid4

from app.repositories.business import BusinessRepository
from app.repositories.startup import Row
from app.services.errors import conflict, forbidden, unavailable
from app.services.snapshots import line_body, new_line, reprice, snapshot
from app.services.startup import Result, StartupService, timestamp
from app.services.validation import MAX_INTERNAL_ID, ValidationError, quantity


class BusinessService(StartupService):
    repo: BusinessRepository

    def access(
        self, auth: str | None, resume: str | None, cart_id: str, *, lock: bool
    ) -> tuple[Row, datetime]:
        register = self.register(lock=lock)
        # REGISTER serializes all business writes. CART precedes operation locks.
        cart = self.repo.cart(cart_id, lock=lock)
        now = self.repo.now()
        session = self.authenticate(register, auth, now)
        context = self.context(register, session["staff_id"], resume, now)
        if cart is None:
            raise forbidden()
        if (
            cart["register_id"] != 1
            or cart["context_id"] != context["context_id"]
            or cart["staff_id"] != session["staff_id"]
        ):
            raise forbidden()
        if register["start_state"] != "READY":
            raise conflict()
        if lock:
            self.writable(register)
        return cart, now

    def cart_body(self, cart: Row) -> Row:
        lines = self.repo.lines(cart["cart_id"])
        for row in lines:
            snapshot(row)  # Invalid persisted candidates never silently fall back to masters.
        checked_cart = copy.deepcopy(cart)
        checked_lines = copy.deepcopy(lines)
        if checked_cart["member_state"] == "PENDING":
            checked_cart["member_state"] = (
                "CONFIRMED" if checked_cart["member_id"] is not None else "UNSPECIFIED"
            )
        reprice(checked_cart, checked_lines)
        if any(str(checked_cart[k]) != str(cart[k]) for k in ("subtotal", "total")) or json.loads(
            checked_cart["tax_breakdown"]
        ) != json.loads(cart["tax_breakdown"]):
            raise unavailable()
        for actual, checked in zip(lines, checked_lines, strict=True):
            if line_body(actual) != line_body(checked):
                raise unavailable()
        purchase = self.repo.purchase(cart["cart_id"])
        status = {
            "EDITING": "NOT_REQUESTED",
            "SAVING": "UNKNOWN",
            "UNSAVED": "UNSAVED",
            "SAVED": "SAVED",
            "CLOSED": "SAVED",
        }[cart["state"]]
        if (status == "SAVED") != (purchase is not None):
            raise unavailable()
        saved = None
        if purchase is not None:
            saved_lines = self.repo.purchase_lines(cart["cart_id"])
            saved_taxes = self.repo.purchase_taxes(cart["cart_id"])
            if not saved_lines or not saved_taxes or purchase["staff_id"] != cart["staff_id"]:
                raise unavailable()
            saved = {k: purchase[k] for k in ("cart_id", "staff_id", "member_id")}
            saved.update(
                purchased_at=timestamp(purchase["purchased_at"]),
                subtotal=str(purchase["subtotal"]),
                total=str(purchase["total"]),
                lines=[line_body(row, purchase=True) for row in saved_lines],
                taxes=[
                    {
                        "tax_rate": str(t["tax_rate_snapshot"]),
                        "taxable_subtotal": str(t["taxable_subtotal"]),
                        "tax_amount": str(t["tax_amount"]),
                    }
                    for t in saved_taxes
                ],
            )
        if saved is not None and (
            saved["subtotal"] != str(cart["subtotal"])
            or saved["total"] != str(cart["total"])
            or saved["member_id"] != cart["member_id"]
            or saved["taxes"] != json.loads(cart["tax_breakdown"])
            or saved["lines"] != [line_body(row, purchase=True) for row in lines]
        ):
            raise unavailable()
        return {
            "cart": {
                **{
                    k: cart[k]
                    for k in ("cart_id", "state", "staff_id", "member_state", "pending_member_id")
                },
                "version": str(cart["version"]),
                "member_id": None if cart["member_state"] == "PENDING" else cart["member_id"],
                "lines": [line_body(row) for row in lines],
                "subtotal": str(cart["subtotal"]),
                "total": str(cart["total"]),
                "taxes": json.loads(cart["tax_breakdown"]),
                "amounts_are_reference": cart["member_state"] == "PENDING",
            },
            "purchase_status": status,
            "purchase": saved,
        }

    def read(
        self, auth: str | None, resume: str | None, cart_id: str, operation_id: str | None = None
    ) -> Result:
        cart, _ = self.access(auth, resume, cart_id, lock=False)
        if operation_id is None:
            return Result(self.cart_body(cart))
        op = self.repo.operation(cart_id, operation_id, lock=False)
        body = self.operation_body(cart, op, operation_id)
        body["new_cart_id"] = op["next_cart_id"] if op else None
        return Result(body)

    def operation_body(self, cart: Row, op: Row | None, operation_id: str) -> Row:
        return {
            **self.cart_body(cart),
            "operation_id": operation_id,
            "operation_status": op["status"] if op else "NOT_FOUND",
            "applied_version": str(op["applied_version"])
            if op and op["applied_version"] is not None
            else None,
            "code": op["result_code"] if op else None,
        }

    def existing(self, cart: Row, operation_id: str, kind: str, payload: Row) -> Row | None:
        locked = {}
        ids = {operation_id} | {
            v
            for v in (cart["active_member_operation_id"], cart["active_purchase_operation_id"])
            if v is not None
        }
        for identifier in sorted(ids):
            locked[identifier] = self.repo.operation(cart["cart_id"], identifier, lock=True)
        op = locked[operation_id]
        if op is not None and (op["kind"] != kind or json.loads(op["request_payload"]) != payload):
            raise conflict("OPERATION_MISMATCH")
        return op

    def record(
        self,
        cart: Row,
        operation_id: str,
        kind: str,
        payload: Row,
        now: datetime,
        *,
        status: str = "APPLIED",
        code: str | None = None,
        next_id: str | None = None,
    ) -> Row:
        op = dict(
            cart_id=cart["cart_id"],
            operation_id=operation_id,
            kind=kind,
            request_version=int(payload["version"]),
            request_payload=json.dumps(payload, sort_keys=True),
            status=status,
            prepared_version=cart["version"] if status == "PREPARED" else None,
            applied_version=cart["version"] if status == "APPLIED" else None,
            result_code=code,
            result_payload=None,
            next_cart_id=next_id,
            created_at=now,
            completed_at=None if status == "PREPARED" else now,
        )
        self.repo.insert_operation(op)
        return op

    @staticmethod
    def expected(cart: Row, version: str, *, increments: int = 1) -> None:
        if cart["version"] != int(version):
            raise conflict("VERSION_CONFLICT")
        if cart["version"] > MAX_INTERNAL_ID - increments:
            raise conflict("VERSION_LIMIT")

    def current(self, cart: Row) -> None:
        if self.register(lock=False)["current_cart_id"] != cart["cart_id"]:
            raise conflict()

    def persist(
        self, cart: Row, lines: list[Row] | None, now: datetime, *, business: bool = True
    ) -> None:
        cart["version"] += 1
        cart["updated_at"] = now
        fields = (
            "state version member_state member_id pending_member_id active_member_operation_id "
            "active_purchase_operation_id purchase_prepared_version updated_at result_closed_at "
            "subtotal total tax_breakdown"
        ).split()
        self.repo.update_cart(cart["cart_id"], {k: cart.get(k) for k in fields})
        if lines is not None:
            self.repo.save_lines(cart["cart_id"], lines)
        if business:
            self.repo.touch(cart["context_id"], now)

    def reject(
        self, cart: Row, operation_id: str, kind: str, payload: Row, now: datetime, code: str
    ) -> Result:
        op = self.record(cart, operation_id, kind, payload, now, status="REJECTED", code=code)
        return Result(self.operation_body(cart, op, operation_id))

    def edit(
        self,
        auth: str | None,
        resume: str | None,
        cart_id: str,
        operation_id: str,
        kind: str,
        payload: Row,
    ) -> Result:
        cart, now = self.access(auth, resume, cart_id, lock=True)
        op = self.existing(cart, operation_id, kind, payload)
        if op is not None:
            return Result(self.operation_body(cart, op, operation_id))
        self.current(cart)
        self.expected(cart, payload["version"])
        if cart["state"] != "EDITING" or cart["member_state"] == "PENDING":
            raise conflict()
        lines = self.repo.lines(cart_id)
        if kind == "ADD_LINE":
            row = next((r for r in lines if r["code_snapshot"] == payload["code"]), None)
            if row is not None:
                if row["quantity"] == 99:
                    return self.reject(cart, operation_id, kind, payload, now, "QUANTITY_LIMIT")
                row["quantity"] += 1
            else:
                conditions = self.repo.product_conditions(payload["code"], now)
                if not conditions:
                    return self.reject(cart, operation_id, kind, payload, now, "PRODUCT_NOT_FOUND")
                number = max((r["line_no"] for r in lines), default=0) + 1
                if number > 4294967295:
                    raise conflict("LINE_LIMIT")
                lines.append(new_line(conditions, cart_id, number, str(uuid4()), now))
        elif kind in ("SET_QUANTITY", "DELETE_LINE"):
            row = next((r for r in lines if r["line_id"] == payload["line_id"]), None)
            if row is None:
                return self.reject(cart, operation_id, kind, payload, now, "LINE_NOT_FOUND")
            if kind == "SET_QUANTITY":
                row["quantity"] = quantity(payload["quantity"])
            else:
                lines.remove(row)
        elif kind != "SYNC":
            raise ValueError("kind")
        try:
            reprice(cart, lines)
        except ValidationError:
            return self.reject(cart, operation_id, kind, payload, now, "AMOUNT_INVALID")
        self.persist(cart, lines if kind != "SYNC" else None, now, business=kind != "SYNC")
        op = self.record(cart, operation_id, kind, payload, now)
        return Result(
            self.operation_body(cart, op, operation_id),
            resume_cookie=resume if kind != "SYNC" else None,
        )

    def prepare_member(
        self, auth: str | None, resume: str | None, cart_id: str, operation_id: str, payload: Row
    ) -> Result:
        cart, now = self.access(auth, resume, cart_id, lock=True)
        op = self.existing(cart, operation_id, "SET_MEMBER", payload)
        if op is not None:
            return Result(self.operation_body(cart, op, operation_id))
        self.current(cart)
        self.expected(
            cart, payload["version"], increments=2 if payload["member_id"] is not None else 1
        )
        if cart["state"] != "EDITING":
            raise conflict()
        if cart["active_member_operation_id"] is not None:
            old = self.repo.operation(cart_id, cart["active_member_operation_id"], lock=True)
            if old is None:
                raise unavailable()
            if old["status"] == "PREPARED":
                self.repo.finish_operation(
                    cart_id, old["operation_id"], "REJECTED", None, "MEMBER_LOOKUP_SUPERSEDED", now
                )
        if payload["member_id"] is None:
            cart.update(
                member_state="NON_MEMBER",
                member_id=None,
                pending_member_id=None,
                active_member_operation_id=None,
            )
            lines = self.repo.lines(cart_id)
            reprice(cart, lines)
            self.persist(cart, lines, now)
            status = "APPLIED"
        else:
            cart.update(
                member_state="PENDING",
                pending_member_id=payload["member_id"],
                active_member_operation_id=operation_id,
            )
            self.persist(cart, None, now)
            status = "PREPARED"
        op = self.record(cart, operation_id, "SET_MEMBER", payload, now, status=status)
        return Result(
            self.operation_body(cart, op, operation_id),
            resume_cookie=resume,
            continue_member=status == "PREPARED",
        )

    def finish_member(
        self,
        auth: str | None,
        resume: str | None,
        cart_id: str,
        operation_id: str,
        payload: Row,
        found: bool,
    ) -> Result:
        cart, now = self.access(auth, resume, cart_id, lock=True)
        op = self.existing(cart, operation_id, "SET_MEMBER", payload)
        if op is None:
            raise unavailable()
        if op["status"] != "PREPARED":
            return Result(self.operation_body(cart, op, operation_id))
        self.current(cart)
        if (
            cart["state"] != "EDITING"
            or cart["member_state"] != "PENDING"
            or cart["active_member_operation_id"] != operation_id
            or cart["version"] != op["prepared_version"]
        ):
            raise conflict()
        self.expected(cart, str(cart["version"]))
        if not found:
            self.repo.finish_operation(
                cart_id, operation_id, "REJECTED", None, "MEMBER_NOT_FOUND", now
            )
            op.update(status="REJECTED", result_code="MEMBER_NOT_FOUND")
            return Result(self.operation_body(cart, op, operation_id))
        cart.update(
            member_state="CONFIRMED",
            member_id=payload["member_id"],
            pending_member_id=None,
            active_member_operation_id=None,
        )
        lines = self.repo.lines(cart_id)
        try:
            reprice(cart, lines)
        except ValidationError:
            raise conflict("AMOUNT_INVALID") from None
        self.persist(cart, lines, now)
        self.repo.finish_operation(cart_id, operation_id, "APPLIED", cart["version"], None, now)
        op.update(status="APPLIED", applied_version=cart["version"])
        return Result(self.operation_body(cart, op, operation_id), resume_cookie=resume)

    def prepare_purchase(
        self, auth: str | None, resume: str | None, cart_id: str, operation_id: str, payload: Row
    ) -> Result:
        cart, now = self.access(auth, resume, cart_id, lock=True)
        op = self.existing(cart, operation_id, "PURCHASE", payload)
        if op is not None:
            return Result(self.operation_body(cart, op, operation_id))
        if self.repo.purchase(cart_id) is not None:
            op = self.record(cart, operation_id, "PURCHASE", payload, now)
            return Result(self.operation_body(cart, op, operation_id))
        self.current(cart)
        self.expected(cart, payload["version"], increments=2)
        lines = self.repo.lines(cart_id)
        if (
            cart["state"] not in ("EDITING", "UNSAVED")
            or cart["member_state"] == "PENDING"
            or not lines
        ):
            raise conflict()
        reprice(cart, lines)
        cart.update(
            state="SAVING",
            active_purchase_operation_id=operation_id,
            purchase_prepared_version=int(payload["version"]),
        )
        self.persist(cart, lines, now)
        op = self.record(cart, operation_id, "PURCHASE", payload, now, status="PREPARED")
        return Result(self.operation_body(cart, op, operation_id), resume_cookie=resume)

    def finish_purchase(
        self, auth: str | None, resume: str | None, cart_id: str, operation_id: str, payload: Row
    ) -> Result:
        cart, now = self.access(auth, resume, cart_id, lock=True)
        op = self.existing(cart, operation_id, "PURCHASE", payload)
        if op is None:
            raise unavailable()
        if op["status"] != "PREPARED":
            return Result(self.operation_body(cart, op, operation_id))
        self.current(cart)
        if (
            cart["state"] != "SAVING"
            or cart["active_purchase_operation_id"] != operation_id
            or cart["purchase_prepared_version"] != int(payload["version"])
            or cart["version"] != op["prepared_version"]
            or cart["member_state"] == "PENDING"
        ):
            raise conflict()
        self.expected(cart, str(cart["version"]))
        lines = self.repo.lines(cart_id)
        if not lines:
            raise unavailable()
        reprice(cart, lines)
        self.repo.save_lines(cart_id, lines)
        self.repo.save_purchase(cart, now)
        cart["state"] = "SAVED"
        self.persist(cart, None, now)
        self.repo.finish_operation(cart_id, operation_id, "APPLIED", cart["version"], None, now)
        op.update(status="APPLIED", applied_version=cart["version"])
        return Result(self.operation_body(cart, op, operation_id), resume_cookie=resume)

    def next_cart(
        self, auth: str | None, resume: str | None, cart_id: str, operation_id: str, payload: Row
    ) -> Result:
        cart, now = self.access(auth, resume, cart_id, lock=True)
        op = self.existing(cart, operation_id, "NEXT", payload)
        if op is None:
            self.current(cart)
            self.expected(cart, payload["version"])
            if cart["state"] != "SAVED" or self.repo.purchase(cart_id) is None:
                raise conflict()
            next_id = str(uuid4())
            cart.update(state="CLOSED", result_closed_at=now)
            self.persist(cart, None, now)
            self.repo.create_cart(next_id, cart["context_id"], cart["staff_id"], now)
            op = self.record(cart, operation_id, "NEXT", payload, now, next_id=next_id)
            cookie = resume
        else:
            cookie = None
        next_cart = self.repo.cart(op["next_cart_id"])
        if next_cart is None:
            raise unavailable()
        body = self.operation_body(next_cart, op, operation_id)
        body["new_cart_id"] = op["next_cart_id"]
        return Result(body, resume_cookie=cookie)

    def resolve_purchase(
        self, auth: str | None, resume: str | None, cart_id: str, operation_id: str, payload: Row
    ) -> Result:
        cart, now = self.access(auth, resume, cart_id, lock=True)
        op = self.existing(cart, operation_id, "RESOLVE_PURCHASE", payload)
        if op is not None:
            return Result(self.operation_body(cart, op, operation_id))
        if self.repo.purchase(cart_id) is not None:
            op = self.record(cart, operation_id, "RESOLVE_PURCHASE", payload, now)
            return Result(self.operation_body(cart, op, operation_id))
        self.current(cart)
        self.expected(cart, payload["version"])
        if cart["state"] not in ("EDITING", "SAVING", "UNSAVED"):
            raise conflict()
        purchase_op = None
        if cart["active_purchase_operation_id"] is not None:
            purchase_op = self.repo.operation(
                cart_id, cart["active_purchase_operation_id"], lock=True
            )
            if purchase_op is None or purchase_op["kind"] != "PURCHASE":
                raise unavailable()
        if cart["state"] == "SAVING":
            if (
                purchase_op is None
                or purchase_op["status"] != "PREPARED"
                or purchase_op["prepared_version"] != cart["version"]
                or purchase_op["request_version"] != cart["purchase_prepared_version"]
            ):
                raise unavailable()
            self.repo.finish_operation(
                cart_id,
                purchase_op["operation_id"],
                "REJECTED",
                None,
                "PURCHASE_ATTEMPT_CLOSED",
                now,
            )
        elif purchase_op is not None and purchase_op["status"] == "PREPARED":
            raise unavailable()
        pending = cart["state"] == "EDITING" and cart["member_state"] == "PENDING"
        if pending:
            member_op = self.repo.operation(cart_id, cart["active_member_operation_id"], lock=True)
            if member_op is None or member_op["kind"] != "SET_MEMBER":
                raise unavailable()
            if member_op["status"] == "PREPARED":
                self.repo.finish_operation(
                    cart_id,
                    member_op["operation_id"],
                    "REJECTED",
                    None,
                    "MEMBER_LOOKUP_SUPERSEDED",
                    now,
                )
            elif member_op["status"] != "REJECTED":
                raise unavailable()
            code = "PURCHASE_FENCED_MEMBER_PENDING"
        else:
            cart.update(
                state="UNSAVED", active_purchase_operation_id=None, purchase_prepared_version=None
            )
            code = None
        self.persist(cart, None, now, business=not pending)
        op = self.record(cart, operation_id, "RESOLVE_PURCHASE", payload, now, code=code)
        return Result(
            self.operation_body(cart, op, operation_id), resume_cookie=None if pending else resume
        )

    def reopen(
        self, auth: str | None, resume: str | None, cart_id: str, operation_id: str, payload: Row
    ) -> Result:
        cart, now = self.access(auth, resume, cart_id, lock=True)
        op = self.existing(cart, operation_id, "REOPEN", payload)
        if op is not None:
            return Result(self.operation_body(cart, op, operation_id))
        self.current(cart)
        self.expected(cart, payload["version"])
        if cart["state"] != "UNSAVED" or self.repo.purchase(cart_id) is not None:
            raise conflict()
        cart.update(
            state="EDITING", active_purchase_operation_id=None, purchase_prepared_version=None
        )
        self.persist(cart, None, now)
        op = self.record(cart, operation_id, "REOPEN", payload, now)
        return Result(self.operation_body(cart, op, operation_id), resume_cookie=resume)
