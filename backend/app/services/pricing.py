"""M1 pricing for server-owned line snapshots (design 4.1 / 4.3).

This module neither reads current masters nor writes a cart. The repository
must obtain and persist the snapshot atomically when a line is first added.
Member confirmation and purchase state are enforced by the caller in M2-M4.
"""

from dataclasses import dataclass
from typing import Literal

from .validation import (
    MAX_INTERNAL_ID,
    RATE_SCALE,
    ValidationError,
    bounded_integer,
    money,
    quantity,
)


@dataclass(frozen=True)
class DiscountCandidate:
    condition_id: int
    kind: Literal["RATE", "AMOUNT"]
    value: int  # basis points for RATE; yen for AMOUNT

    def __post_init__(self) -> None:
        bounded_integer(self.condition_id, 1, MAX_INTERNAL_ID)
        if self.kind == "RATE":
            bounded_integer(self.value, 0, RATE_SCALE)
        elif self.kind == "AMOUNT":
            money(self.value)
        else:
            raise ValidationError("値引きの種類が不正です")


@dataclass(frozen=True)
class LineSnapshot:
    unit_price: int
    quantity: int
    tax_rate: int  # basis points
    candidates: tuple[DiscountCandidate, ...] = ()

    def __post_init__(self) -> None:
        money(self.unit_price)
        quantity(self.quantity)
        bounded_integer(self.tax_rate, 0, RATE_SCALE)
        if type(self.candidates) is not tuple or any(
            not isinstance(candidate, DiscountCandidate) for candidate in self.candidates
        ):
            raise ValidationError("保持候補は不変の候補列で指定してください")
        ids = [candidate.condition_id for candidate in self.candidates]
        if len(set(ids)) != len(ids):
            raise ValidationError("値引き条件IDが重複しています")


@dataclass(frozen=True)
class PricedLine:
    snapshot: LineSnapshot
    selected: DiscountCandidate | None
    candidate_amount: int
    actual_discount: int
    discounted_unit_price: int
    discount_total: int
    subtotal: int


@dataclass(frozen=True)
class TaxTotal:
    rate: int
    subtotal: int
    tax: int


@dataclass(frozen=True)
class PricingResult:
    lines: tuple[PricedLine, ...]
    taxes: tuple[TaxTotal, ...]
    subtotal: int
    total: int


def calculate(lines: tuple[LineSnapshot, ...], *, is_member: bool) -> PricingResult:
    """Calculate all results before returning; an overflow returns no partial result.

    Empty editable carts have zero totals. Call require_purchasable before
    purchase; the API layer will map that failure to 409 STATE_CONFLICT.
    """
    if type(is_member) is not bool:
        raise ValidationError("確認済みの会員判定が必要です")
    priced = []
    buckets: dict[int, int] = {}
    for line in lines:
        selected = None
        candidate_amount = 0
        if is_member and line.candidates:
            amounts = [
                (
                    candidate,
                    line.unit_price * candidate.value // RATE_SCALE
                    if candidate.kind == "RATE"
                    else candidate.value,
                )
                for candidate in line.candidates
            ]
            selected, candidate_amount = min(
                amounts, key=lambda item: (-item[1], item[0].condition_id)
            )
        actual_discount = min(line.unit_price, candidate_amount)
        discounted = line.unit_price - actual_discount
        subtotal = money(discounted * line.quantity)
        discount_total = money(actual_discount * line.quantity)
        priced.append(
            PricedLine(
                line,
                selected,
                candidate_amount,
                actual_discount,
                discounted,
                discount_total,
                subtotal,
            )
        )
        buckets[line.tax_rate] = money(buckets.get(line.tax_rate, 0) + subtotal)
    taxes = tuple(
        TaxTotal(rate, subtotal, money(subtotal * rate // RATE_SCALE))
        for rate, subtotal in sorted(buckets.items())
    )
    subtotal = money(sum(item.subtotal for item in taxes))
    total = money(subtotal + sum(item.tax for item in taxes))
    return PricingResult(tuple(priced), taxes, subtotal, total)


def require_purchasable(result: PricingResult) -> None:
    if not result.lines:
        raise ValidationError("空の購入リストでは購入できません")
