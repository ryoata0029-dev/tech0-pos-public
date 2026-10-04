"""Remaining TC06..17 API flows; memory transactions are not MySQL evidence."""

import copy
import unittest
from datetime import timedelta
from decimal import Decimal

import test_business as business_tests


class RemainingApiTests(unittest.TestCase):
    # Reuse setup/helpers, without inheriting or collecting existing test methods again.
    setUp = business_tests.BusinessApiTests.setUp
    request = business_tests.BusinessApiTests.request
    validate = business_tests.BusinessApiTests.validate
    login = business_tests.BusinessApiTests.login
    start = business_tests.BusinessApiTests.start
    operation = business_tests.BusinessApiTests.operation
    call = business_tests.BusinessApiTests.call
    add = business_tests.BusinessApiTests.add
    buy = business_tests.BusinessApiTests.buy

    def member(self, member_id="MEM_A"):
        result = self.call("PUT", "member", self.operation(member_id=member_id))
        self.assertEqual(200, result[0], result)
        return result[2]

    def delete(self, line_id):
        operation = self.operation()
        path = (
            f"/api/carts/{self.cart_id}/lines/{line_id}"
            f"?operation_id={operation['operation_id']}&version={operation['version']}"
        )
        result = self.request("DELETE", path)
        self.assertEqual(200, result[0], result)
        self.validate(result[2], "OperationResult")
        return result[2]

    def next(self):
        result = self.call("POST", "next", self.operation())
        self.assertEqual(200, result[0], result)
        self.cart_id = result[2]["new_cart_id"]

    def test_tc06_numeric_tie_survives_api_and_save_in_both_input_orders(self):
        self.start()
        original = self.repo.masters["0001"][0]
        candidates = [
            dict(original, condition_id=10, kind="AMOUNT", discount_rate=None, amount=Decimal(10)),
            dict(original, condition_id=2),
        ]
        for rows in (candidates, list(reversed(candidates))):
            with self.subTest(order=[row["condition_id"] for row in rows]):
                self.repo.masters["0001"] = copy.deepcopy(rows)
                self.add()
                self.member()
                saved = self.buy()[2]["purchase"]
                discount = saved["lines"][0]["discount"]
                self.assertEqual(
                    ("2", "RATE", "10", "10"),
                    tuple(
                        discount[key]
                        for key in ("condition_id", "kind", "candidate_amount", "actual_discount")
                    ),
                )
                self.assertEqual(
                    ("93", "9", "102"),
                    (saved["subtotal"], saved["taxes"][0]["tax_amount"], saved["total"]),
                )
                self.next()

    def test_tc06_select_uncapped_candidate_and_keep_zero_sale_details(self):
        self.start()
        original = self.repo.masters["0001"][0]
        self.repo.masters["0001"] = [
            dict(original, condition_id=2, kind="AMOUNT", discount_rate=None, amount=Decimal(120)),
            dict(original, condition_id=10, kind="AMOUNT", discount_rate=None, amount=Decimal(130)),
        ]
        self.add()
        self.member()
        request = self.operation(cart_id=self.cart_id)
        saved = self.buy(request)[2]["purchase"]
        line = saved["lines"][0]
        self.assertEqual(
            ("10", "130", "103"),
            tuple(
                line["discount"][key]
                for key in ("condition_id", "candidate_amount", "actual_discount")
            ),
        )
        self.assertEqual(
            ("103", "0", "0"),
            (line["discount_per_unit"], line["net_unit_price"], line["line_subtotal"]),
        )
        self.assertEqual(
            [{"tax_rate": "0.1000", "taxable_subtotal": "0", "tax_amount": "0"}], saved["taxes"]
        )
        self.assertEqual(("0", "0"), (saved["subtotal"], saved["total"]))
        self.assertEqual(saved, self.buy(request)[2]["purchase"])
        self.assertEqual(
            (1, 1, 1),
            (
                len(self.repo.sales),
                len(self.repo.sale_lines[self.cart_id]),
                len(self.repo.sale_taxes[self.cart_id]),
            ),
        )

    def test_tc07_tc09_expired_candidates_survive_late_member_purchase_and_reads(self):
        self.start()
        master = self.repo.masters["0001"][0]
        master["valid_to"] = self.repo.clock + timedelta(minutes=1)
        added = self.add()["cart"]["lines"][0]
        fixed = copy.deepcopy(self.repo.items[self.cart_id][0])
        self.repo.clock += timedelta(minutes=2)
        master.update(
            unit_price=Decimal(500), tax_rate=Decimal("0.0800"), discount_rate=Decimal("0.5000")
        )
        self.add()
        result = self.call("PATCH", f"lines/{added['line_id']}", self.operation(quantity=3))
        self.assertEqual(200, result[0])
        confirmed = self.member()["cart"]
        self.assertEqual(("279", "306"), (confirmed["subtotal"], confirmed["total"]))
        retained = self.repo.items[self.cart_id][0]
        for key in (
            "line_id",
            "unit_price_snapshot",
            "tax_rate_snapshot",
            "discount_candidates",
            "conditions_fixed_at",
        ):
            self.assertEqual(fixed[key], retained[key], key)
        request = self.operation(cart_id=self.cart_id)
        saved = self.buy(request)[2]["purchase"]
        self.assertEqual(
            ("STAFF_A", "MEM_A", "103", "0.1000", 3, "10", "279", "306"),
            (
                saved["staff_id"],
                saved["member_id"],
                saved["lines"][0]["unit_price"],
                saved["lines"][0]["tax_rate"],
                saved["lines"][0]["quantity"],
                saved["lines"][0]["discount_per_unit"],
                saved["subtotal"],
                saved["total"],
            ),
        )
        self.repo.clock += timedelta(minutes=5)
        master.update(name="変更後の架空名", unit_price=Decimal(900))
        self.assertEqual(
            saved, self.request("GET", f"/api/carts/{self.cart_id}/purchase")[2]["purchase"]
        )
        self.assertEqual(saved, self.buy(request)[2]["purchase"])
        self.assertEqual("演習商品", saved["lines"][0]["name"])

    def test_tc08_max_money_quantity_overflow_is_atomic_and_rejection_is_final(self):
        self.start()
        self.repo.masters["0001"][0].update(
            unit_price=Decimal("999999999999"), tax_rate=Decimal(0), condition_id=None
        )
        line = self.add()["cart"]["lines"][0]
        self.assertEqual("999999999999", line["line_subtotal"])
        before_cart = copy.deepcopy(self.repo.carts[self.cart_id])
        before_lines = copy.deepcopy(self.repo.items[self.cart_id])
        before_contexts = copy.deepcopy(self.repo.contexts)
        self.repo.clock += timedelta(minutes=1)
        operation = self.operation(quantity=2)
        result = self.call("PATCH", f"lines/{line['line_id']}", operation)
        self.assertEqual((422, "AMOUNT_INVALID"), (result[0], result[2]["code"]))
        self.assertEqual(before_cart, self.repo.carts[self.cart_id])
        self.assertEqual(before_lines, self.repo.items[self.cart_id])
        self.assertEqual(before_contexts, self.repo.contexts)
        self.assertFalse(any(key == b"set-cookie" for key, _ in result[1]))
        self.repo.masters["0001"][0]["unit_price"] = Decimal(1)
        self.assertEqual(result[2], self.call("PATCH", f"lines/{line['line_id']}", operation)[2])
        self.assertEqual(1, self.repo.items[self.cart_id][0]["quantity"])
        saved = self.buy()[2]["purchase"]
        self.assertEqual("999999999999", saved["total"])
        self.assertEqual(1, len(saved["lines"]))

    def test_tc12_precise_versions_and_purchase_increment_headroom(self):
        self.start()
        self.add()
        for version in (9007199254740991, 9007199254740992, 9007199254740993):
            with self.subTest(version=version):
                self.repo.carts[self.cart_id]["version"] = version
                read = self.request("GET", f"/api/carts/{self.cart_id}")[2]
                self.validate(read, "CartResult")
                self.assertEqual(str(version), read["cart"]["version"])
                result = self.call("POST", "sync", self.operation())[2]
                self.assertEqual(str(version + 1), result["cart"]["version"])
                self.assertEqual(str(version + 1), result["applied_version"])
        self.repo.carts[self.cart_id]["version"] = 18446744073709551613
        request = self.operation(cart_id=self.cart_id)
        saved = self.buy(request)
        self.assertEqual(200, saved[0])
        self.assertEqual("18446744073709551615", saved[2]["cart"]["version"])
        self.assertEqual("18446744073709551615", saved[2]["applied_version"])
        self.assertEqual(saved[2], self.buy(request)[2])
        before = copy.deepcopy(self.repo.__dict__)
        refused = self.call("POST", "next", self.operation())
        self.assertEqual((409, "VERSION_LIMIT"), (refused[0], refused[2]["code"]))
        self.assertEqual(before, self.repo.__dict__)

    def test_tc13_tc14_inconsistent_saved_purchase_stops_read_without_repair(self):
        self.start()
        self.add()
        self.add("0002")
        self.member()
        self.buy()
        baseline = copy.deepcopy(self.repo.__dict__)
        mutations = {
            "missing lines": lambda: self.repo.sale_lines[self.cart_id].clear(),
            "missing tax bucket": lambda: self.repo.sale_taxes[self.cart_id].pop(),
            "extra tax bucket": lambda: self.repo.sale_taxes[self.cart_id].append(
                dict(tax_rate_snapshot="0.0000", taxable_subtotal="0", tax_amount="0")
            ),
            "wrong total": lambda: self.repo.sales[self.cart_id].update(total=999),
            "wrong staff": lambda: self.repo.sales[self.cart_id].update(staff_id="STAFF_B"),
            "wrong member": lambda: self.repo.sales[self.cart_id].update(member_id="MEM_B"),
            "wrong saved quantity": lambda: self.repo.sale_lines[self.cart_id][0].update(
                quantity=2
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(inconsistency=name):
                self.repo.__dict__ = copy.deepcopy(baseline)
                mutate()
                corrupt = copy.deepcopy(self.repo.__dict__)
                for path in (
                    f"/api/carts/{self.cart_id}",
                    f"/api/carts/{self.cart_id}/purchase",
                    "/api/resume",
                ):
                    self.assertEqual(503, self.request("GET", path)[0], (name, path))
                    self.assertEqual(corrupt, self.repo.__dict__)

    def test_tc17_reopen_all_edit_types_saves_only_new_content(self):
        self.start()
        first = self.add()["cart"]["lines"][0]
        self.call("PATCH", f"lines/{first['line_id']}", self.operation(quantity=3))
        self.add("0002")
        deleted = self.add("0003")["cart"]["lines"][2]
        initial = self.member()["cart"]
        self.assertEqual("537", initial["total"])
        fixed = copy.deepcopy(self.repo.items[self.cart_id][0])
        old_purchase = self.operation(cart_id=self.cart_id)
        self.fail_phase = self.phase_count + 2
        self.assertEqual(503, self.buy(old_purchase)[0])
        self.fail_phase = None
        self.assertEqual({}, self.repo.sales)
        resolved = self.call("POST", "resolve-purchase", self.operation())[2]
        self.assertEqual("UNSAVED", resolved["cart"]["state"])
        reopened = self.call("POST", "reopen", self.operation())[2]
        self.assertEqual("EDITING", reopened["cart"]["state"])
        self.assertEqual(initial["lines"], reopened["cart"]["lines"])
        self.assertEqual(initial["total"], reopened["cart"]["total"])
        self.assertEqual(409, self.buy(old_purchase)[0])
        self.assertEqual({}, self.repo.sales)
        self.repo.masters["0001"][0].update(unit_price=Decimal(999), tax_rate=Decimal(0))
        self.repo.masters["0003"][0].update(unit_price=Decimal(500), tax_rate=Decimal(0))
        self.call("PATCH", f"lines/{first['line_id']}", self.operation(quantity=2))
        self.delete(deleted["line_id"])
        readded = self.add("0003")["cart"]["lines"][2]
        self.assertNotEqual(deleted["line_id"], readded["line_id"])
        self.assertEqual("500", readded["unit_price"])
        self.member(None)
        for key in (
            "line_id",
            "unit_price_snapshot",
            "tax_rate_snapshot",
            "discount_candidates",
            "conditions_fixed_at",
        ):
            self.assertEqual(fixed[key], self.repo.items[self.cart_id][0][key], key)
        self.assertEqual({}, self.repo.sales)
        self.request("GET", "/api/resume")
        self.assertEqual({}, self.repo.sales)
        new_purchase = self.operation(cart_id=self.cart_id)
        saved = self.buy(new_purchase)[2]["purchase"]
        self.assertIsNone(saved["member_id"])
        self.assertEqual(("813", "841"), (saved["subtotal"], saved["total"]))
        self.assertEqual(
            [("0001", 2, "103"), ("0002", 1, "107"), ("0003", 1, "500")],
            [(line["code"], line["quantity"], line["unit_price"]) for line in saved["lines"]],
        )
        self.assertEqual(saved, self.buy(new_purchase)[2]["purchase"])
        self.assertEqual(409, self.buy(old_purchase)[0])
        self.assertEqual(1, len(self.repo.sales))
        self.assertEqual(
            "REJECTED", self.repo.ops[(self.cart_id, old_purchase["operation_id"])]["status"]
        )


if __name__ == "__main__":
    unittest.main()
