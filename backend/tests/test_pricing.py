"""Pure portions of TC-06..10. No API, DB or device acceptance claims."""

import unittest
from dataclasses import FrozenInstanceError, replace

from app.services.pricing import (
    DiscountCandidate as Discount,
)
from app.services.pricing import (
    LineSnapshot as Line,
)
from app.services.pricing import (
    calculate,
    require_purchasable,
)
from app.services.validation import MAX_MONEY, ValidationError


class PricingTests(unittest.TestCase):
    def setUp(self):
        self.line = Line(103, 3, 1000, (Discount(1, "RATE", 1000),))

    def test_tc06_member_306(self):
        result = calculate((self.line,), is_member=True)
        self.assertEqual((result.subtotal, result.total), (279, 306))
        item = result.lines[0]
        self.assertEqual((item.actual_discount, item.discount_total), (10, 30))
        self.assertEqual(result.taxes[0].tax, 27)

    def test_tc06_mixed_tax_537(self):
        result = calculate((self.line, Line(107, 1, 800), Line(107, 1, 800)), is_member=True)
        self.assertEqual((result.subtotal, result.total), (493, 537))
        self.assertEqual(
            [(t.rate, t.subtotal, t.tax) for t in result.taxes], [(800, 214, 17), (1000, 279, 27)]
        )

    def test_tc06_non_member_339_and_570(self):
        self.assertEqual(calculate((self.line,), is_member=False).total, 339)
        result = calculate((self.line, Line(107, 1, 800), Line(107, 1, 800)), is_member=False)
        self.assertEqual((result.subtotal, result.total), (523, 570))
        self.assertIsNone(result.lines[0].selected)
        self.assertEqual(result.lines[0].discount_total, 0)

    def test_tc06_maximum_single_discount(self):
        line = Line(103, 1, 0, (Discount(1, "RATE", 1000), Discount(2, "AMOUNT", 20)))
        result = calculate((line,), is_member=True)
        self.assertEqual(result.total, 83)
        self.assertEqual(result.lines[0].selected.condition_id, 2)

    def test_tc06_cap_actual_discount_but_preserve_candidate(self):
        result = calculate((Line(103, 1, 1000, (Discount(1, "AMOUNT", 120),)),), is_member=True)
        item = result.lines[0]
        self.assertEqual((item.candidate_amount, item.actual_discount, result.total), (120, 103, 0))
        require_purchasable(result)

    def test_tc06_tie_uses_numeric_id_not_iteration_order(self):
        candidates = (Discount(10, "AMOUNT", 10), Discount(2, "RATE", 1000))
        for values in (candidates, tuple(reversed(candidates))):
            with self.subTest(order=values):
                result = calculate((Line(103, 1, 0, values),), is_member=True)
                self.assertEqual(result.lines[0].selected.condition_id, 2)

    def test_tc06_select_before_price_cap(self):
        result = calculate(
            (
                Line(
                    103,
                    1,
                    0,
                    (
                        Discount(1, "AMOUNT", 120),
                        Discount(2, "AMOUNT", 130),
                    ),
                ),
            ),
            is_member=True,
        )
        self.assertEqual(result.lines[0].selected.condition_id, 2)

    def test_tc07_pure_snapshot_remains_unchanged(self):
        # Persistence, master reads and transactional snapshotting remain M3 work.
        with self.assertRaises(FrozenInstanceError):
            self.line.unit_price = 999
        changed_quantity = replace(self.line, quantity=2)
        self.assertEqual(calculate((changed_quantity,), is_member=True).total, 204)
        calculate((self.line,), is_member=False)
        self.assertEqual(calculate((self.line,), is_member=True).total, 306)

    def test_tc08_every_stored_aggregate_overflow(self):
        scenarios = {
            "line subtotal": (Line(MAX_MONEY, 2, 0),),
            "line discount": (Line(MAX_MONEY, 2, 0, (Discount(1, "RATE", 10000),)),),
            "tax bucket": (Line(MAX_MONEY, 1, 0), Line(1, 1, 0)),
            "subtotal across rates": (Line(MAX_MONEY, 1, 0), Line(1, 1, 1)),
            "tax inclusive total": (Line(MAX_MONEY, 1, 1),),
        }
        for name, lines in scenarios.items():
            with self.subTest(boundary=name), self.assertRaises(ValidationError):
                calculate(lines, is_member=True)

    def test_tc08_maximum_and_rate_endpoints(self):
        self.assertEqual(calculate((Line(MAX_MONEY, 1, 0),), is_member=False).total, MAX_MONEY)
        self.assertEqual(calculate((Line(10000, 1, 1),), is_member=False).total, 10001)
        self.assertEqual(calculate((Line(1, 1, 10000),), is_member=False).total, 2)

    def test_tc08_invalid_snapshot_inputs(self):
        factories = (
            lambda: Line(103, True, 0),
            lambda: Line(103.0, 1, 0),
            lambda: Line(103, 1, 10001),
            lambda: Discount(True, "AMOUNT", 1),
            lambda: Discount(1, "OTHER", 0),
            lambda: Discount(1, "RATE", 10001),
            lambda: Line(1, 1, 0, [Discount(1, "RATE", 1)]),
            lambda: Line(1, 1, 0, (Discount(1, "RATE", 1), Discount(1, "AMOUNT", 2))),
        )
        for factory in factories:
            with self.subTest(factory=factory), self.assertRaises(ValidationError):
                factory()

    def test_tc10_empty_editable_cart_but_no_purchase(self):
        result = calculate((), is_member=False)
        self.assertEqual(result.total, 0)
        with self.assertRaises(ValidationError):
            require_purchasable(result)

    def test_member_flag_cannot_be_coerced(self):
        for value in (None, "false", 1):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                calculate((self.line,), is_member=value)


if __name__ == "__main__":
    unittest.main()
