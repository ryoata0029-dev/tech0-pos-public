"""M2 authentication and initial startup; the caller commits before issuing cookies."""

import json
import secrets
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.repositories.startup import Row, StartupRepository
from app.security.credentials import Passwords, new_token, token_hash
from app.services.errors import conflict, forbidden, unauthenticated, unavailable
from app.services.login_limit import LoginLimit


@dataclass
class Result:
    body: dict[str, Any]
    auth_cookie: str | None = field(default=None, repr=False)
    resume_cookie: str | None = field(default=None, repr=False)
    auth_max_age: int = 28800
    continue_member: bool = False
    issued_at: float = field(default_factory=time.monotonic, repr=False)


def timestamp(value: datetime) -> str:
    return value.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")


def auth_body(row: Row) -> dict[str, Any]:
    return {
        "authenticated": True,
        "staff_id": row["staff_id"],
        "expires_at": timestamp(row["expires_at"]),
    }


class StartupService:
    def __init__(self, repo: StartupRepository, passwords: Passwords) -> None:
        self.repo = repo
        self.passwords = passwords

    def register(self, *, lock: bool) -> Row:
        row = self.repo.register(lock=lock)
        if row is None or row["start_state"] not in ("UNSTARTED", "COOKIE_PENDING", "READY"):
            raise unavailable()
        if row["start_state"] == "UNSTARTED":
            if row["active_context_id"] is not None or row["current_cart_id"] is not None:
                raise unavailable()
        elif row["active_context_id"] is None:
            raise unavailable()
        return row

    def authenticate(self, register: Row, cookie: str | None, now: datetime) -> Row:
        hashed = token_hash(cookie)
        if hashed is None or register["active_session_hash"] != hashed:
            raise unauthenticated()
        row = self.repo.session(hashed)
        if (
            row is None
            or row["register_id"] != 1
            or row["revoked_at"] is not None
            or not row["created_at"] <= now < row["expires_at"]
        ):
            raise unauthenticated()
        return row

    def context(self, register: Row, staff_id: str, cookie: str | None, now: datetime) -> Row:
        context_id = register["active_context_id"]
        hashed = token_hash(cookie)
        if context_id is None or hashed is None:
            raise forbidden()
        row = self.repo.context(context_id)
        if row is None:
            raise unavailable()
        if (
            row["register_id"] != 1
            or row["starting_staff_id"] != staff_id
            or row["invalidated_at"] is not None
            or not secrets.compare_digest(row["token_hash"], hashed)
        ):
            raise forbidden()
        if register["start_state"] == "READY" and row["confirmed_at"] is None:
            raise unavailable()
        if register["start_state"] == "COOKIE_PENDING" and (
            row["confirmed_at"] is not None or register["current_cart_id"] is not None
        ):
            raise unavailable()
        if register["current_cart_id"] is not None:
            if row["last_business_at"] is None:
                raise unavailable()
            base = max(
                t for t in (row["last_business_at"], row["manual_released_at"]) if t is not None
            )
            if now >= base + timedelta(hours=24):
                raise conflict("RESUME_EXPIRED")
            cart = self.repo.cart(register["current_cart_id"])
            if cart is None:
                raise unavailable()
            self.check_cart(cart, row, staff_id)
        elif row["last_business_at"] is not None:
            # A lost current-cart pointer is not permission to create a replacement.
            raise unavailable()
        return row

    @staticmethod
    def check_cart(cart: Row, context: Row, staff_id: str) -> None:
        if (
            cart["register_id"] != 1
            or cart["context_id"] != context["context_id"]
            or cart["staff_id"] != staff_id
        ):
            raise forbidden()
        if cart["state"] == "CLOSED":
            raise unavailable()

    def login(self, staff_id: str, password: str, resume: str | None) -> Result | None:
        register = self.register(lock=True)
        row = self.repo.limit(staff_id)
        now = self.repo.now()  # After both locks, including concurrent waits.
        limit = LoginLimit.parse(row["failure_times"], row["locked_until"]).at(now)
        if limit.locked_until is not None:
            return None
        try:
            matched = self.passwords.verify(password, self.repo.password(staff_id))
        except Exception:
            raise unavailable() from None
        if not matched:
            limit = limit.failed(now)
            self.repo.save_limit(staff_id, limit.json(), limit.locked_until)
            return None  # Caller commits the failure record, then emits common 401.
        if register["start_state"] != "UNSTARTED":
            self.context(register, staff_id, resume, now)
        elif resume is not None:
            raise forbidden()
        self.repo.save_limit(staff_id, limit.json(), None)
        # Account for time spent persisting/committing the session before issuing the cookie.
        issued_at = time.monotonic()
        # Hash verification can be slow. Start the fixed 8h period after successful verification.
        now = self.repo.now()
        expires = now + timedelta(hours=8)
        token = new_token()
        hashed = token_hash(token)
        assert hashed is not None
        self.repo.rotate_session(staff_id, hashed, register["active_session_hash"], now, expires)
        return Result(
            auth_body({"staff_id": staff_id, "expires_at": expires}),
            auth_cookie=token,
            issued_at=issued_at,
        )

    def status(self, auth: str | None) -> Result:
        register = self.register(lock=False)
        return Result(auth_body(self.authenticate(register, auth, self.repo.now())))

    def inspect_register(self, auth: str | None, resume: str | None) -> Result:
        register = self.register(lock=False)
        now = self.repo.now()
        session = self.authenticate(register, auth, now)
        if register["start_state"] != "UNSTARTED":
            self.context(register, session["staff_id"], resume, now)
        elif resume is not None:
            raise forbidden()
        return Result(self.register_body(register, "ABSENT" if resume is None else "MATCH"))

    @staticmethod
    def register_body(register: Row, cookie_status: str) -> dict[str, Any]:
        return {
            "start_state": register["start_state"],
            "cookie_status": cookie_status,
            "available": register["start_state"] == "READY" and not register["maintenance_hold"],
            "maintenance_hold": bool(register["maintenance_hold"]),
        }

    @staticmethod
    def writable(register: Row) -> None:
        if register["maintenance_hold"]:
            raise conflict("MAINTENANCE_HOLD")

    def start(self, auth: str | None, resume: str | None) -> Result:
        register = self.register(lock=True)
        now = self.repo.now()
        session = self.authenticate(register, auth, now)
        self.writable(register)
        if register["start_state"] != "UNSTARTED":
            raise conflict()
        if resume is not None:
            raise forbidden()
        token = new_token()
        hashed = token_hash(token)
        assert hashed is not None
        self.repo.start(str(uuid4()), session["staff_id"], hashed, now)
        register["start_state"] = "COOKIE_PENDING"
        return Result(self.register_body(register, "ABSENT"), resume_cookie=token)

    def confirm(self, auth: str | None, resume: str | None) -> Result:
        register = self.register(lock=True)
        now = self.repo.now()
        session = self.authenticate(register, auth, now)
        self.writable(register)
        context = self.context(register, session["staff_id"], resume, now)
        if register["start_state"] == "COOKIE_PENDING":
            self.repo.confirm(context["context_id"], now)
            register["start_state"] = "READY"
        return Result(self.register_body(register, "MATCH"))

    def get_cart(
        self,
        auth: str | None,
        resume: str | None,
        *,
        create: bool = False,
        cart_id: str | None = None,
    ) -> Result:
        register = self.register(lock=create)
        now = self.repo.now()
        session = self.authenticate(register, auth, now)
        context = self.context(register, session["staff_id"], resume, now)
        if create:
            self.writable(register)
        if register["start_state"] != "READY":
            raise conflict()
        current_id = register["current_cart_id"]
        if cart_id is not None and cart_id != current_id:
            raise forbidden()
        created = current_id is None and create
        if created:
            current_id = str(uuid4())
            self.repo.create_cart(current_id, context["context_id"], session["staff_id"], now)
        if current_id is None:
            from app.services.errors import PosError

            raise PosError(404, "CART_NOT_CREATED", "初回カートはまだ作成されていません。")
        cart = self.repo.cart(current_id, lock=create)
        if cart is None:
            raise unavailable()
        self.check_cart(cart, context, session["staff_id"])
        return Result(self.cart_body(cart), resume_cookie=resume if created else None)

    def cart_body(self, cart: Row) -> dict[str, Any]:
        # M2 supports the initial empty cart. Fail closed for later milestones' records,
        # rather than fabricating empty lines or interpreting saved/unknown as unsaved.
        if (
            cart["state"] != "EDITING"
            or cart["member_state"] != "UNSPECIFIED"
            or cart["member_id"] is not None
            or cart["pending_member_id"] is not None
            or cart["active_member_operation_id"] is not None
            or cart["active_purchase_operation_id"] is not None
            or cart["purchase_prepared_version"] is not None
            or self.repo.lines(cart["cart_id"])
            or self.repo.purchase(cart["cart_id"]) is not None
            or cart["subtotal"] != 0
            or cart["total"] != 0
            or json.loads(cart["tax_breakdown"]) != []
        ):
            raise conflict("MILESTONE_NOT_IMPLEMENTED")
        return {
            "cart": {
                "cart_id": cart["cart_id"],
                "version": str(cart["version"]),
                "state": cart["state"],
                "staff_id": cart["staff_id"],
                "member_state": cart["member_state"],
                "member_id": None,
                "pending_member_id": None,
                "lines": [],
                "subtotal": "0",
                "total": "0",
                "taxes": [],
                "amounts_are_reference": False,
            },
            "purchase_status": "NOT_REQUESTED",
            "purchase": None,
        }
