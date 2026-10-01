"""Explicit SQL against the approved DDL; no create_all, migrations or repair on boot."""

from datetime import datetime
from typing import Any

from sqlalchemy import Connection, text

Row = dict[str, Any]


class StartupRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def one(self, sql: str, **params: Any) -> Row | None:
        row = self.connection.execute(text(sql), params).mappings().one_or_none()
        return dict(row) if row is not None else None

    def write(self, sql: str, **params: Any) -> None:
        self.connection.execute(text(sql), params)

    def now(self) -> datetime:
        return self.connection.execute(text("SELECT UTC_TIMESTAMP(6)")).scalar_one()  # type: ignore[no-any-return]

    def register(self, *, lock: bool) -> Row | None:
        return self.one(
            "SELECT * FROM REGISTER WHERE register_id=1" + (" FOR UPDATE" if lock else "")
        )

    def limit(self, staff_id: str) -> Row:
        row = self.one(
            "SELECT * FROM AUTH_LOGIN_LIMIT WHERE staff_id=:staff FOR UPDATE", staff=staff_id
        )
        if row is None:
            self.write(
                "INSERT INTO AUTH_LOGIN_LIMIT(staff_id,failure_times) VALUES(:staff,'[]')",
                staff=staff_id,
            )
            return {"failure_times": "[]", "locked_until": None}
        return row

    def save_limit(self, staff_id: str, failures: str, until: datetime | None) -> None:
        self.write(
            "UPDATE AUTH_LOGIN_LIMIT SET failure_times=:failures,locked_until=:until "
            "WHERE staff_id=:staff",
            staff=staff_id,
            failures=failures,
            until=until,
        )

    def password(self, staff_id: str) -> str | None:
        row = self.one("SELECT password_hash FROM STAFF WHERE staff_id=:staff", staff=staff_id)
        return str(row["password_hash"]) if row else None

    def session(self, token_hash: bytes) -> Row | None:
        return self.one("SELECT * FROM AUTH_SESSION WHERE token_hash=:token", token=token_hash)

    def rotate_session(
        self, staff_id: str, token: bytes, old: bytes | None, now: datetime, expires: datetime
    ) -> None:
        if old is not None:
            self.write(
                "UPDATE AUTH_SESSION SET revoked_at=:now WHERE token_hash=:old "
                "AND revoked_at IS NULL",
                now=now,
                old=old,
            )
        self.write(
            "INSERT INTO AUTH_SESSION(token_hash,staff_id,register_id,created_at,expires_at) "
            "VALUES(:token,:staff,1,:now,:expires)",
            token=token,
            staff=staff_id,
            now=now,
            expires=expires,
        )
        self.write(
            "UPDATE REGISTER SET active_session_hash=:token WHERE register_id=1", token=token
        )

    def context(self, context_id: str) -> Row | None:
        return self.one("SELECT * FROM BROWSER_CONTEXT WHERE context_id=:id", id=context_id)

    def start(self, context_id: str, staff_id: str, token: bytes, now: datetime) -> None:
        self.write(
            "INSERT INTO BROWSER_CONTEXT(context_id,register_id,starting_staff_id,"
            "token_hash,created_at) VALUES(:id,1,:staff,:token,:now)",
            id=context_id,
            staff=staff_id,
            token=token,
            now=now,
        )
        self.write(
            "UPDATE REGISTER SET start_state='COOKIE_PENDING',active_context_id=:id "
            "WHERE register_id=1",
            id=context_id,
        )

    def confirm(self, context_id: str, now: datetime) -> None:
        self.write(
            "UPDATE BROWSER_CONTEXT SET confirmed_at=:now WHERE context_id=:id",
            id=context_id,
            now=now,
        )
        self.write("UPDATE REGISTER SET start_state='READY' WHERE register_id=1")

    def cart(self, cart_id: str, *, lock: bool = False) -> Row | None:
        return self.one(
            "SELECT * FROM CART WHERE cart_id=:id" + (" FOR UPDATE" if lock else ""), id=cart_id
        )

    def create_cart(self, cart_id: str, context_id: str, staff_id: str, now: datetime) -> None:
        self.write(
            "INSERT INTO CART(cart_id,register_id,context_id,staff_id,state,version,"
            "member_state,created_at,updated_at,subtotal,total,tax_breakdown) "
            "VALUES(:id,1,:context,:staff,'EDITING',1,'UNSPECIFIED',:now,:now,0,0,'[]')",
            id=cart_id,
            context=context_id,
            staff=staff_id,
            now=now,
        )
        self.write("UPDATE REGISTER SET current_cart_id=:id WHERE register_id=1", id=cart_id)
        self.write(
            "UPDATE BROWSER_CONTEXT SET last_business_at=:now WHERE context_id=:context",
            now=now,
            context=context_id,
        )

    def lines(self, cart_id: str) -> list[Row]:
        rows = self.connection.execute(
            text("SELECT * FROM CART_LINE WHERE cart_id=:id ORDER BY line_no"), {"id": cart_id}
        ).mappings()
        return [dict(row) for row in rows]

    def purchase(self, cart_id: str) -> Row | None:
        return self.one("SELECT * FROM PURCHASE WHERE cart_id=:id", id=cart_id)

    def product(self, code: str) -> Row | None:
        return self.one("SELECT code,name,unit_price FROM PRODUCT WHERE code=:code", code=code)

    def member(self, code: str) -> Row | None:
        return self.one("SELECT member_id FROM MEMBER WHERE member_id=:code", code=code)
