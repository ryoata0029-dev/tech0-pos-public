"""M3 SQL. All writes run inside the caller's explicit transaction."""

import json
from datetime import datetime
from typing import Any

from sqlalchemy import text

from app.repositories.startup import Row, StartupRepository

CART_FIELDS = frozenset(
    "state version member_state member_id pending_member_id active_member_operation_id "
    "active_purchase_operation_id purchase_prepared_version updated_at result_closed_at "
    "subtotal total tax_breakdown".split()
)
LINE_FIELDS = (
    "cart_id line_id product_id line_no code_snapshot name_snapshot quantity "
    "unit_price_snapshot tax_rate_snapshot discount_candidates discount_snapshot "
    "discount_per_unit net_unit_price line_subtotal conditions_fixed_at"
).split()


class BusinessRepository(StartupRepository):
    def rows(self, sql: str, **params: Any) -> list[Row]:
        return [dict(r) for r in self.connection.execute(text(sql), params).mappings()]

    def product_conditions(self, code: str, now: datetime) -> list[Row]:
        # One READ COMMITTED statement: product without candidates survives the LEFT JOIN.
        return self.rows(
            "SELECT p.*,t.rate AS tax_rate,d.condition_id,d.kind,d.rate AS discount_rate,"
            "d.amount,d.valid_from,d.valid_to FROM PRODUCT p "
            "JOIN TAX_RATE t ON t.tax_rate_id=p.tax_rate_id "
            "LEFT JOIN DISCOUNT_CONDITION d ON d.product_id=p.product_id "
            "AND d.valid_from<=:now AND :now<d.valid_to WHERE p.code=:code "
            "ORDER BY d.condition_id",
            code=code,
            now=now,
        )

    def operation(self, cart_id: str, operation_id: str, *, lock: bool) -> Row | None:
        return self.one(
            "SELECT * FROM CART_OPERATION WHERE cart_id=:cart AND operation_id=:op"
            + (" FOR UPDATE" if lock else ""),
            cart=cart_id,
            op=operation_id,
        )

    def insert_operation(self, row: Row) -> None:
        fields = (
            "cart_id operation_id kind request_version request_payload status prepared_version "
            "applied_version result_code result_payload next_cart_id created_at completed_at"
        ).split()
        self.write(
            f"INSERT INTO CART_OPERATION({','.join(fields)}) "
            f"VALUES({','.join(':' + k for k in fields)})",
            **{k: row.get(k) for k in fields},
        )

    def finish_operation(
        self,
        cart_id: str,
        operation_id: str,
        status: str,
        version: int | None,
        code: str | None,
        now: datetime,
    ) -> None:
        self.write(
            "UPDATE CART_OPERATION SET status=:status,applied_version=:version,"
            "result_code=:code,completed_at=:now WHERE cart_id=:cart AND operation_id=:op",
            cart=cart_id,
            op=operation_id,
            status=status,
            version=version,
            code=code,
            now=now,
        )

    def update_cart(self, cart_id: str, values: Row) -> None:
        if not values or not values.keys() <= CART_FIELDS:
            raise ValueError("cart fields")
        self.write(
            "UPDATE CART SET " + ",".join(f"{k}=:{k}" for k in values) + " WHERE cart_id=:id",
            id=cart_id,
            **values,
        )

    def touch(self, context_id: str, now: datetime) -> None:
        self.write(
            "UPDATE BROWSER_CONTEXT SET last_business_at=:now WHERE context_id=:id",
            now=now,
            id=context_id,
        )

    def save_lines(self, cart_id: str, lines: list[Row]) -> None:
        # Keep identities and fixed conditions; no master reads during recalculation.
        retained = {r["line_id"] for r in lines}
        for old in self.lines(cart_id):
            if old["line_id"] not in retained:
                self.write(
                    "DELETE FROM CART_LINE WHERE cart_id=:cart AND line_id=:line",
                    cart=cart_id,
                    line=old["line_id"],
                )
        assignments = ",".join(
            f"{k}=VALUES({k})" for k in LINE_FIELDS if k not in ("cart_id", "line_id")
        )
        for row in lines:
            self.write(
                f"INSERT INTO CART_LINE({','.join(LINE_FIELDS)}) "
                f"VALUES({','.join(':' + k for k in LINE_FIELDS)}) ON DUPLICATE KEY UPDATE "
                + assignments,
                **{k: row[k] for k in LINE_FIELDS},
            )

    def save_purchase(self, cart: Row, now: datetime) -> None:
        self.write(
            "INSERT INTO PURCHASE(cart_id,staff_id,member_id,purchased_at,subtotal,total) "
            "VALUES(:cart_id,:staff_id,:member_id,:now,:subtotal,:total)",
            **{k: cart[k] for k in ("cart_id", "staff_id", "member_id", "subtotal", "total")},
            now=now,
        )
        fields = [
            k
            for k in LINE_FIELDS
            if k not in ("line_id", "discount_candidates", "conditions_fixed_at")
        ]
        self.write(
            f"INSERT INTO PURCHASE_LINE({','.join(fields)}) SELECT {','.join(fields)} "
            "FROM CART_LINE WHERE cart_id=:cart",
            cart=cart["cart_id"],
        )
        for tax in json.loads(cart["tax_breakdown"]):
            self.write(
                "INSERT INTO PURCHASE_TAX(cart_id,tax_rate_snapshot,taxable_subtotal,tax_amount) "
                "VALUES(:cart,:tax_rate,:taxable_subtotal,:tax_amount)",
                cart=cart["cart_id"],
                **tax,
            )

    def purchase_lines(self, cart_id: str) -> list[Row]:
        return self.rows(
            "SELECT * FROM PURCHASE_LINE WHERE cart_id=:id ORDER BY line_no", id=cart_id
        )

    def purchase_taxes(self, cart_id: str) -> list[Row]:
        return self.rows(
            "SELECT * FROM PURCHASE_TAX WHERE cart_id=:id ORDER BY tax_rate_snapshot", id=cart_id
        )
