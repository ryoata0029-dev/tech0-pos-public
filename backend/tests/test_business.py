"""M3 business/API contracts and phase rollback; MySQL/device proof is separate."""

import copy
import unittest
from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import test_startup_api as startup_tests
from support.business import BusinessMemory

from app.services.business import BusinessService
from app.services.errors import unavailable


class BusinessApiTests(unittest.TestCase):
    request = startup_tests.ApiTests.request
    validate = startup_tests.ApiTests.validate
    login = startup_tests.ApiTests.login

    def setUp(self):
        startup_tests.ApiTests.setUp(self)
        self.repo = BusinessMemory()
        patch("app.api.startup.BusinessRepository", return_value=self.repo).start()
        self.phase_count = 0
        self.fail_phase = None

        @contextmanager
        def tx(engine, *, readonly=False):
            before = copy.deepcopy(self.repo.__dict__)
            self.phase_count += 1
            try:
                yield object()
                if self.phase_count == self.fail_phase:
                    raise unavailable()
                if readonly:
                    self.assertEqual(before, self.repo.__dict__)
            except Exception:
                self.repo.__dict__ = before
                raise

        patch("app.api.business.transaction", tx).start()
        patch("app.api.business.BusinessRepository", return_value=self.repo).start()

    def start(self):
        self.login()
        self.request("POST", "/api/register/start")
        self.request("POST", "/api/register/confirm")
        self.cart_id = self.request("POST", "/api/carts")[2]["cart"]["cart_id"]
        return self.cart_id

    def operation(self, **extra):
        return {
            "operation_id": str(uuid4()),
            "version": str(self.repo.carts[self.cart_id]["version"]),
            **extra,
        }

    def call(self, method, suffix, body):
        response = self.request(method, f"/api/carts/{self.cart_id}/{suffix}", body)
        if response[0] < 400:
            self.validate(response[2], "NextResult" if suffix == "next" else "OperationResult")
        return response

    def add(self, code="0001"):
        result = self.call("POST", "lines", self.operation(code=code))
        self.assertEqual(200, result[0], result)
        return result[2]

    def buy(self, body=None):
        result = self.request(
            "POST", "/api/purchases", body or self.operation(cart_id=self.cart_id)
        )
        if result[0] < 400:
            self.validate(result[2], "OperationResult")
        return result

    def test_member_nonmember_save_and_next(self):
        self.start()
        added = self.add()
        line = added["cart"]["lines"][0]["line_id"]
        self.assertEqual(200, self.call("PATCH", f"lines/{line}", self.operation(quantity=3))[0])
        self.assertEqual(200, self.call("PUT", "member", self.operation(member_id="MEM_A"))[0])
        self.assertEqual("306", self.repo.carts[self.cart_id]["total"].__str__())
        self.add("0002")
        self.add("0003")
        request = self.operation(cart_id=self.cart_id)
        saved = self.buy(request)
        self.assertEqual(200, saved[0])
        self.assertEqual("537", saved[2]["purchase"]["total"])
        self.assertEqual(saved[2], self.buy(request)[2])
        self.assertEqual(1, len(self.repo.sales))
        self.assertEqual(3, len(self.repo.sale_lines[self.cart_id]))
        self.assertEqual(2, len(self.repo.sale_taxes[self.cart_id]))
        next_request = self.operation()
        result = self.call("POST", "next", next_request)
        self.assertEqual(200, result[0])
        self.assertEqual("1", result[2]["cart"]["version"])
        self.assertEqual([], result[2]["cart"]["lines"])
        self.assertEqual("UNSPECIFIED", result[2]["cart"]["member_state"])
        self.assertEqual(result[2], self.call("POST", "next", next_request)[2])
        self.assertEqual(2, len(self.repo.carts))
        self.assertEqual(409, self.call("POST", "next", self.operation())[0])
        self.cart_id = result[2]["new_cart_id"]
        self.add()
        self.assertEqual("113", self.buy()[2]["purchase"]["total"])

    def test_snapshot_retained_and_delete_readd_refreshes(self):
        self.start()
        self.add()
        self.repo.masters["0001"][0].update(
            unit_price=Decimal("500"), tax_rate=Decimal("0.0800"), discount_rate=Decimal("0.5000")
        )
        self.add()
        member = self.call("PUT", "member", self.operation(member_id="MEM_A"))[2]
        self.assertEqual("103", member["cart"]["lines"][0]["unit_price"])
        self.assertEqual("204", member["cart"]["total"])
        line = member["cart"]["lines"][0]["line_id"]
        op = self.operation()
        path = (
            f"/api/carts/{self.cart_id}/lines/{line}?operation_id={op['operation_id']}"
            f"&version={op['version']}"
        )
        self.assertEqual(200, self.request("DELETE", path)[0])
        self.assertEqual(200, self.request("DELETE", path)[0])
        refreshed = self.add()["cart"]["lines"][0]
        self.assertEqual("500", refreshed["unit_price"])
        self.assertNotEqual(line, refreshed["line_id"])

    def test_idempotency_mismatch_old_version_and_recorded_rejections(self):
        self.start()
        op = self.operation(code="0001")
        first = self.call("POST", "lines", op)
        self.add("0002")
        duplicate = self.call("POST", "lines", op)
        self.assertEqual(1, duplicate[2]["cart"]["lines"][0]["quantity"])
        self.assertNotEqual(first[2]["cart"]["version"], duplicate[2]["cart"]["version"])
        self.assertEqual(409, self.call("POST", "lines", op | {"code": "0002"})[0])
        self.assertEqual(
            409, self.call("POST", "lines", self.operation(code="0001") | {"version": "1"})[0]
        )
        missing = self.operation(code="MISSING")
        self.assertEqual(404, self.call("POST", "lines", missing)[0])
        self.repo.masters["MISSING"] = copy.deepcopy(self.repo.masters["0001"])
        self.assertEqual(404, self.call("POST", "lines", missing)[0])

    def test_member_pending_blocks_all_edits_and_late_lookup_cannot_overwrite(self):
        self.start()
        self.add()
        self.call("PUT", "member", self.operation(member_id="MEM_A"))
        missing = self.call("PUT", "member", self.operation(member_id="MISSING"))
        self.assertEqual(404, missing[0])
        pending = self.request("GET", "/api/resume")[2]
        self.assertTrue(pending["cart"]["amounts_are_reference"])
        self.assertIsNone(pending["cart"]["member_id"])
        self.assertEqual("102", pending["cart"]["total"])
        line = pending["cart"]["lines"][0]["line_id"]
        for method, suffix, extra in [
            ("POST", "lines", {"code": "0001"}),
            ("PATCH", f"lines/{line}", {"quantity": 2}),
        ]:
            self.assertEqual(409, self.call(method, suffix, self.operation(**extra))[0])
        self.assertEqual(409, self.buy()[0])
        self.assertEqual(200, self.call("PUT", "member", self.operation(member_id=None))[0])
        self.assertEqual("113", self.request("GET", "/api/resume")[2]["cart"]["total"])
        service = BusinessService(self.repo, self.app.state.passwords)
        auth = self.jar["__Host-pos_session"]
        resume = self.jar["__Host-pos_resume"]
        op = self.operation(member_id="MEM_A")
        payload = {k: v for k, v in op.items() if k != "operation_id"}
        service.prepare_member(auth, resume, self.cart_id, op["operation_id"], payload)
        self.call("PUT", "member", self.operation(member_id="MEM_B"))
        result = service.finish_member(
            auth, resume, self.cart_id, op["operation_id"], payload, True
        )
        self.assertEqual("REJECTED", result.body["operation_status"])
        self.assertEqual("MEM_B", result.body["cart"]["member_id"])

    def test_empty_rejected_zero_purchase_allowed_and_version_headroom(self):
        self.start()
        self.assertEqual(409, self.buy()[0])
        self.assertEqual({}, self.repo.sales)
        self.assertEqual("EDITING", self.repo.carts[self.cart_id]["state"])
        self.repo.masters["0001"][0].update(
            kind="AMOUNT", discount_rate=None, amount=Decimal("120")
        )
        self.add()
        self.call("PUT", "member", self.operation(member_id="MEM_A"))
        result = self.buy()
        self.assertEqual("0", result[2]["purchase"]["total"])
        discount = result[2]["purchase"]["lines"][0]["discount"]
        self.assertEqual("120", discount["candidate_amount"])
        self.assertEqual("103", discount["actual_discount"])

    def test_failed_save_phase_rolls_back_sale_but_keeps_prepared_no_get_save(self):
        self.start()
        self.add()
        body = self.operation(cart_id=self.cart_id)
        self.fail_phase = self.phase_count + 2
        result = self.buy(body)
        self.assertEqual(503, result[0])
        self.assertEqual({}, self.repo.sales)
        self.assertEqual({}, self.repo.sale_lines)
        self.assertEqual("SAVING", self.repo.carts[self.cart_id]["state"])
        state = self.request("GET", "/api/resume")[2]
        self.assertEqual("UNKNOWN", state["purchase_status"])
        self.assertEqual({}, self.repo.sales)
        self.assertEqual(409, self.call("POST", "lines", self.operation(code="0002"))[0])
        self.fail_phase = None
        self.assertEqual("SAVED", self.buy(body)[2]["purchase_status"])
        self.assertEqual(1, len(self.repo.sales))

    def test_untrusted_input_delete_query_and_overflow(self):
        self.start()
        self.add()
        line = self.repo.items[self.cart_id][0]["line_id"]
        for value in [0, 100, True, 1.5, "2", None]:
            self.assertEqual(
                422, self.call("PATCH", f"lines/{line}", self.operation(quantity=value))[0]
            )
        self.assertEqual(
            422, self.call("POST", "lines", self.operation(code="0001", unit_price="1"))[0]
        )
        self.assertEqual(422, self.buy(self.operation(cart_id=self.cart_id, staff_id="STAFF_B"))[0])
        self.assertEqual(
            422, self.request("DELETE", f"/api/carts/{self.cart_id}/lines/{line}?version=1")[0]
        )
        self.repo.carts[self.cart_id]["version"] = 18446744073709551614
        self.assertEqual(409, self.buy()[0])
        self.assertEqual({}, self.repo.sales)
        self.assertEqual(
            422,
            self.call(
                "POST", "lines", self.operation(code="0001") | {"version": "18446744073709551616"}
            )[0],
        )

    def test_saved_other_operation_returns_original_before_version_check(self):
        self.start()
        self.add()
        saved = self.buy()[2]["purchase"]
        result = self.buy(self.operation(cart_id=self.cart_id) | {"version": "1"})
        self.assertEqual(200, result[0])
        self.assertEqual(saved, result[2]["purchase"])
        self.assertEqual(1, len(self.repo.sales))

    def test_quantity_limit_sync_no_business_touch_and_closed_operation_get(self):
        self.start()
        added = self.add()
        line = added["cart"]["lines"][0]["line_id"]
        self.call("PATCH", f"lines/{line}", self.operation(quantity=99))
        rejected = self.operation(code="0001")
        self.assertEqual(422, self.call("POST", "lines", rejected)[0])
        self.assertEqual(99, self.repo.items[self.cart_id][0]["quantity"])
        base = self.repo.contexts[self.repo.reg["active_context_id"]]["last_business_at"]
        self.repo.clock = self.repo.clock.replace(hour=1)
        self.assertEqual(200, self.call("POST", "sync", self.operation())[0])
        self.assertEqual(
            base, self.repo.contexts[self.repo.reg["active_context_id"]]["last_business_at"]
        )
        self.buy()
        op = self.operation()
        next_result = self.call("POST", "next", op)[2]
        result = self.request("GET", f"/api/carts/{self.cart_id}/operations/{op['operation_id']}")
        self.assertEqual(200, result[0])
        self.validate(result[2], "OperationResult")
        self.assertEqual("CLOSED", result[2]["cart"]["state"])
        self.assertEqual(next_result["new_cart_id"], result[2]["new_cart_id"])

    def test_cookie_auth_maintenance_and_pending_do_not_allow_writes(self):
        self.start()
        self.add()
        op = self.operation(code="0002")
        before = copy.deepcopy(self.repo.__dict__)
        for headers, expected in [
            ({"cookie": ""}, 401),
            ({"cookie": "__Host-pos_session=" + self.jar["__Host-pos_session"]}, 403),
            ({"origin": "https://evil.invalid"}, 403),
        ]:
            status = self.request("POST", f"/api/carts/{self.cart_id}/lines", op, change=headers)[0]
            self.assertEqual(expected, status)
            self.assertEqual(before, self.repo.__dict__)
        self.repo.reg["maintenance_hold"] = True
        self.assertEqual(409, self.call("POST", "lines", op)[0])
        self.assertEqual(200, self.request("GET", "/api/resume")[0])
        self.assertEqual(409, self.call("POST", "sync", self.operation())[0])

    def test_corrupt_persisted_snapshot_stops_and_amount_overflow_is_atomic(self):
        self.start()
        self.add()
        self.repo.masters["0002"][0]["unit_price"] = Decimal("999999999999")
        before = copy.deepcopy(self.repo.items)
        op = self.operation(code="0002")
        self.assertEqual(422, self.call("POST", "lines", op)[0])
        self.assertEqual(before, self.repo.items)
        self.assertEqual(422, self.call("POST", "lines", op)[0])
        self.repo.items[self.cart_id][0]["discount_candidates"] = '[{"extra":true}]'
        self.assertEqual(503, self.request("GET", "/api/resume")[0])
        self.assertEqual(503, self.buy()[0])
        self.assertEqual({}, self.repo.sales)

    def test_prepared_member_retry_does_not_lookup_or_clear_pending(self):
        self.start()
        self.add()
        service = BusinessService(self.repo, self.app.state.passwords)
        auth, resume = self.jar["__Host-pos_session"], self.jar["__Host-pos_resume"]
        op = self.operation(member_id="MEM_A")
        payload = {k: v for k, v in op.items() if k != "operation_id"}
        service.prepare_member(auth, resume, self.cart_id, op["operation_id"], payload)
        with patch.object(self.repo, "member", side_effect=AssertionError("no lookup")):
            result = self.call("PUT", "member", op)
        self.assertEqual(202, result[0])
        self.assertEqual("PENDING", result[2]["cart"]["member_state"])
        self.assertEqual("PREPARED", result[2]["operation_status"])

    def test_next_failure_rolls_back_pointer_closed_and_new_cart_together(self):
        self.start()
        self.add()
        self.buy()
        op = self.operation()
        before = copy.deepcopy(self.repo.__dict__)
        self.fail_phase = self.phase_count + 1
        self.assertEqual(503, self.call("POST", "next", op)[0])
        self.assertEqual(before, self.repo.__dict__)
        self.fail_phase = None
        self.assertEqual(200, self.call("POST", "next", op)[0])
        self.assertEqual(2, len(self.repo.carts))

    def test_resolve_fences_prepared_purchase_and_reopen_is_explicit(self):
        self.start()
        self.add()
        purchase = self.operation(cart_id=self.cart_id)
        self.fail_phase = self.phase_count + 2
        self.assertEqual(503, self.buy(purchase)[0])
        self.fail_phase = None
        request = self.operation()
        resolved = self.call("POST", "resolve-purchase", request)
        self.assertEqual(200, resolved[0])
        self.assertEqual("UNSAVED", resolved[2]["purchase_status"])
        self.assertEqual(
            "REJECTED", self.repo.ops[(self.cart_id, purchase["operation_id"])]["status"]
        )
        self.assertEqual(resolved[2], self.call("POST", "resolve-purchase", request)[2])
        self.assertEqual(409, self.buy(purchase)[0])
        self.assertEqual({}, self.repo.sales)
        self.assertEqual(409, self.call("POST", "lines", self.operation(code="0002"))[0])
        reopen = self.operation()
        self.assertEqual("EDITING", self.call("POST", "reopen", reopen)[2]["cart"]["state"])
        self.assertEqual(200, self.call("POST", "reopen", reopen)[0])
        self.add("0002")
        self.assertEqual("SAVED", self.buy()[2]["purchase_status"])

    def test_resolve_before_delayed_purchase_and_saved_wins(self):
        self.start()
        self.add()
        delayed = self.operation(cart_id=self.cart_id)
        first = self.call("POST", "resolve-purchase", self.operation())
        self.assertEqual("UNSAVED", first[2]["cart"]["state"])
        self.assertEqual(409, self.buy(delayed)[0])
        saved = self.buy()[2]
        result = self.call("POST", "resolve-purchase", self.operation() | {"version": "1"})
        self.assertEqual(saved["purchase"], result[2]["purchase"])
        self.assertEqual(saved["cart"]["version"], result[2]["cart"]["version"])
        self.assertEqual(409, self.call("POST", "reopen", self.operation())[0])

    def test_pending_resolve_preserves_reference_and_invalidates_late_member(self):
        self.start()
        self.add()
        self.call("PUT", "member", self.operation(member_id="MEM_A"))
        service = BusinessService(self.repo, self.app.state.passwords)
        auth, resume = self.jar["__Host-pos_session"], self.jar["__Host-pos_resume"]
        request = self.operation(member_id="MEM_B")
        payload = {k: v for k, v in request.items() if k != "operation_id"}
        service.prepare_member(auth, resume, self.cart_id, request["operation_id"], payload)
        before = self.request("GET", "/api/resume")[2]
        timestamp = self.repo.contexts[self.repo.reg["active_context_id"]]["last_business_at"]
        result = self.call("POST", "resolve-purchase", self.operation())
        self.assertEqual("PURCHASE_FENCED_MEMBER_PENDING", result[2]["code"])
        self.assertEqual("PENDING", result[2]["cart"]["member_state"])
        self.assertEqual(before["cart"]["total"], result[2]["cart"]["total"])
        self.assertFalse(any(name.lower() == "set-cookie" for name, _ in result[1]))
        self.assertEqual(
            timestamp, self.repo.contexts[self.repo.reg["active_context_id"]]["last_business_at"]
        )
        late = service.finish_member(
            auth, resume, self.cart_id, request["operation_id"], payload, True
        )
        self.assertEqual("REJECTED", late.body["operation_status"])
        self.assertEqual("PENDING", late.body["cart"]["member_state"])
        self.assertEqual(409, self.buy()[0])
        self.assertEqual(200, self.call("PUT", "member", self.operation(member_id=None))[0])

    def test_resolve_failure_rolls_back_fence_and_operation_together(self):
        self.start()
        self.add()
        request = self.operation()
        before = copy.deepcopy(self.repo.__dict__)
        self.fail_phase = self.phase_count + 1
        self.assertEqual(503, self.call("POST", "resolve-purchase", request)[0])
        self.assertEqual(before, self.repo.__dict__)
        self.fail_phase = None
        self.assertEqual(
            "UNSAVED", self.call("POST", "resolve-purchase", request)[2]["purchase_status"]
        )
