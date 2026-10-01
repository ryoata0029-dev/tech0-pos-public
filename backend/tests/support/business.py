"""Transaction-aware tests snapshot this repository; no claim about MySQL locking."""

import copy
import json
from decimal import Decimal

from app.repositories.business import BusinessRepository
from support.startup import MemoryRepository


class BusinessMemory(MemoryRepository, BusinessRepository):
    def __init__(self):
        super().__init__()
        self.items = {}
        self.ops = {}
        self.sales = {}
        self.sale_lines = {}
        self.sale_taxes = {}
        self.members = {"MEM_A", "MEM_B"}
        self.masters = {
            "0001": [
                dict(
                    product_id=1,
                    code="0001",
                    name="演習商品",
                    unit_price=Decimal("103"),
                    tax_rate=Decimal("0.1000"),
                    condition_id=1,
                    kind="RATE",
                    discount_rate=Decimal("0.1000"),
                    amount=None,
                    valid_from=self.clock,
                    valid_to=self.clock.replace(year=2027),
                )
            ],
            "0002": [
                dict(
                    product_id=2,
                    code="0002",
                    name="軽減税率商品",
                    unit_price=Decimal("107"),
                    tax_rate=Decimal("0.0800"),
                    condition_id=None,
                )
            ],
            "0003": [
                dict(
                    product_id=3,
                    code="0003",
                    name="軽減税率商品2",
                    unit_price=Decimal("107"),
                    tax_rate=Decimal("0.0800"),
                    condition_id=None,
                )
            ],
        }

    def lines(self, cart_id):
        return copy.deepcopy(self.items.get(cart_id, []))

    def purchase(self, cart_id):
        return copy.deepcopy(self.sales.get(cart_id))

    def purchase_lines(self, cart_id):
        return copy.deepcopy(self.sale_lines.get(cart_id, []))

    def purchase_taxes(self, cart_id):
        return copy.deepcopy(self.sale_taxes.get(cart_id, []))

    def member(self, code):
        return {"member_id": code} if code in self.members else None

    def product(self, code):
        rows = self.masters.get(code)
        return {k: rows[0][k] for k in ("code", "name", "unit_price")} if rows else None

    def product_conditions(self, code, now):
        rows = copy.deepcopy(self.masters.get(code, []))
        if rows and rows[0]["condition_id"] is not None:
            rows = [r for r in rows if r["valid_from"] <= now < r["valid_to"]]
            if not rows:
                row = copy.deepcopy(self.masters[code][0])
                row["condition_id"] = None
                rows = [row]
        return rows

    def operation(self, cart_id, operation_id, *, lock):
        return copy.deepcopy(self.ops.get((cart_id, operation_id)))

    def insert_operation(self, row):
        key = (row["cart_id"], row["operation_id"])
        if key in self.ops:
            raise ValueError("duplicate operation")
        self.ops[key] = copy.deepcopy(row)

    def finish_operation(self, cart_id, operation_id, status, version, code, now):
        self.ops[(cart_id, operation_id)].update(
            status=status, applied_version=version, result_code=code, completed_at=now
        )

    def update_cart(self, cart_id, values):
        self.carts[cart_id].update(copy.deepcopy(values))

    def touch(self, context_id, now):
        self.contexts[context_id]["last_business_at"] = now

    def save_lines(self, cart_id, lines):
        self.items[cart_id] = copy.deepcopy(lines)

    def save_purchase(self, cart, now):
        if cart["cart_id"] in self.sales:
            raise ValueError("duplicate sale")
        self.sales[cart["cart_id"]] = {
            k: cart[k] for k in ("cart_id", "staff_id", "member_id", "subtotal", "total")
        }
        self.sales[cart["cart_id"]]["purchased_at"] = now
        self.sale_lines[cart["cart_id"]] = self.lines(cart["cart_id"])
        self.sale_taxes[cart["cart_id"]] = [
            dict(
                tax_rate_snapshot=t["tax_rate"],
                taxable_subtotal=t["taxable_subtotal"],
                tax_amount=t["tax_amount"],
            )
            for t in json.loads(cart["tax_breakdown"])
        ]
