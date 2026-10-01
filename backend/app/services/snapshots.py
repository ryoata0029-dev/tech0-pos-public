"""Validate persisted snapshots, calculate with M1, serialize exact wire values."""

import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.repositories.startup import Row
from app.services.pricing import DiscountCandidate, LineSnapshot, calculate
from app.services.startup import timestamp
from app.services.validation import (
    ValidationError,
    active_period,
    parse_internal_id,
    parse_money,
    parse_rate,
)

CANDIDATE_KEYS = {"condition_id", "kind", "rate", "amount", "valid_from", "valid_to"}


def rate(value: int) -> str:
    return f"{value // 10000}.{value % 10000:04d}"


def candidate(value: Any) -> DiscountCandidate:
    if not isinstance(value, dict) or value.keys() != CANDIDATE_KEYS:
        raise ValidationError("保持候補の構造が不正です")
    start = datetime.fromisoformat(value["valid_from"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(value["valid_to"].replace("Z", "+00:00"))
    active_period(start, end, start)
    if value["kind"] == "RATE" and value["amount"] is None:
        amount = parse_rate(value["rate"])
    elif value["kind"] == "AMOUNT" and value["rate"] is None:
        amount = parse_money(value["amount"])
    else:
        raise ValidationError("保持候補の種類が不正です")
    return DiscountCandidate(parse_internal_id(value["condition_id"]), value["kind"], amount)


def snapshot(row: Row) -> LineSnapshot:
    values = json.loads(row["discount_candidates"])
    if not isinstance(values, list):
        raise ValidationError("候補配列が必要です")
    return LineSnapshot(
        parse_money(str(row["unit_price_snapshot"])),
        row["quantity"],
        parse_rate(str(row["tax_rate_snapshot"])),
        tuple(candidate(v) for v in values),
    )


def reprice(cart: Row, lines: list[Row]) -> None:
    result = calculate(
        tuple(snapshot(row) for row in lines), is_member=cart["member_state"] == "CONFIRMED"
    )
    for row, priced in zip(lines, result.lines, strict=True):
        discount = None
        if priced.selected is not None:
            discount = next(
                v
                for v in json.loads(row["discount_candidates"])
                if v["condition_id"] == str(priced.selected.condition_id)
            ).copy()
            discount.update(
                candidate_amount=str(priced.candidate_amount),
                actual_discount=str(priced.actual_discount),
            )
        row.update(
            discount_snapshot=json.dumps(discount) if discount is not None else None,
            discount_per_unit=priced.actual_discount,
            net_unit_price=priced.discounted_unit_price,
            line_subtotal=priced.subtotal,
        )
    cart.update(
        subtotal=result.subtotal,
        total=result.total,
        tax_breakdown=json.dumps(
            [
                {
                    "tax_rate": rate(t.rate),
                    "taxable_subtotal": str(t.subtotal),
                    "tax_amount": str(t.tax),
                }
                for t in result.taxes
            ]
        ),
    )


def line_body(row: Row, *, purchase: bool = False) -> Row:
    discount = (
        json.loads(row["discount_snapshot"]) if row["discount_snapshot"] is not None else None
    )
    if discount is not None:
        if not isinstance(discount, dict) or discount.keys() != CANDIDATE_KEYS | {
            "candidate_amount",
            "actual_discount",
        }:
            raise ValidationError("適用条件が不正です")
        candidate({k: discount[k] for k in CANDIDATE_KEYS})
        parse_money(discount["candidate_amount"])
        parse_money(discount["actual_discount"])
    body = {
        "line_no": row["line_no"],
        "code": row["code_snapshot"],
        "name": row["name_snapshot"],
        "quantity": row["quantity"],
        "unit_price": str(row["unit_price_snapshot"]),
        "tax_rate": str(row["tax_rate_snapshot"]),
        "discount": discount,
        "discount_per_unit": str(row["discount_per_unit"]),
        "net_unit_price": str(row["net_unit_price"]),
        "line_subtotal": str(row["line_subtotal"]),
    }
    if not purchase:
        body["line_id"] = row["line_id"]
    return body


def new_line(rows: list[Row], cart_id: str, line_no: int, line_id: str, now: datetime) -> Row:
    first = rows[0]
    values = []
    for row in rows:
        if row["condition_id"] is not None:
            values.append(
                {
                    "condition_id": str(row["condition_id"]),
                    "kind": row["kind"],
                    "rate": str(row["discount_rate"]) if row["discount_rate"] is not None else None,
                    "amount": str(row["amount"]) if row["amount"] is not None else None,
                    "valid_from": timestamp(row["valid_from"]),
                    "valid_to": timestamp(row["valid_to"]),
                }
            )
    return dict(
        cart_id=cart_id,
        line_id=line_id,
        line_no=line_no,
        product_id=first["product_id"],
        code_snapshot=first["code"],
        name_snapshot=first["name"],
        quantity=1,
        unit_price_snapshot=first["unit_price"],
        tax_rate_snapshot=Decimal(str(first["tax_rate"])),
        discount_candidates=json.dumps(values),
        conditions_fixed_at=now,
    )
