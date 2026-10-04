"""Bounded API omissions and offline verification guards; no real MySQL evidence."""

import asyncio
import copy
import importlib.util
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import test_business as business_tests
from jsonschema import ValidationError

SCRIPT = Path(__file__).resolve().parents[2] / "tools/oct05_api_verify.py"
MODULE = importlib.util.spec_from_file_location("oct05_api_verifier_test", SCRIPT)
verifier = importlib.util.module_from_spec(MODULE)
MODULE.loader.exec_module(verifier)


class AggregateApiTests(unittest.TestCase):
    setUp = business_tests.BusinessApiTests.setUp
    request = business_tests.BusinessApiTests.request
    validate = business_tests.BusinessApiTests.validate
    login = business_tests.BusinessApiTests.login
    start = business_tests.BusinessApiTests.start
    operation = business_tests.BusinessApiTests.operation
    call = business_tests.BusinessApiTests.call
    add = business_tests.BusinessApiTests.add

    def stable_state(self):
        return copy.deepcopy({k: v for k, v in self.repo.__dict__.items() if k != "ops"})

    def test_valid_individual_rows_reject_transaction_sum_and_same_request_retry(self):
        self.start()
        self.repo.masters["0001"][0].update(
            unit_price=Decimal(600000000000), tax_rate=Decimal(0), condition_id=None
        )
        self.repo.masters["0002"][0].update(unit_price=Decimal(500000000000), tax_rate=Decimal(0))
        self.add()
        before, ops = self.stable_state(), len(self.repo.ops)
        request = self.operation(code="0002")
        first = self.call("POST", "lines", request)
        self.assertEqual((422, "AMOUNT_INVALID"), (first[0], first[2]["code"]))
        self.assertEqual(before, self.stable_state())
        self.assertEqual(ops + 1, len(self.repo.ops))
        op = self.repo.ops[(self.cart_id, request["operation_id"])]
        self.assertEqual(("REJECTED", None), (op["status"], op["applied_version"]))
        retry = self.call("POST", "lines", request)
        self.assertEqual((first[0], first[2]), (retry[0], retry[2]))
        self.assertEqual(before, self.stable_state())
        self.assertEqual(ops + 1, len(self.repo.ops))

    def test_subtotal_within_limit_but_tax_inclusive_total_overflows(self):
        self.start()
        self.repo.masters["0001"][0].update(unit_price=Decimal(999999999999))
        before = self.stable_state()
        request = self.operation(code="0001")
        status, headers, value = self.call("POST", "lines", request)
        self.assertEqual((422, "AMOUNT_INVALID"), (status, value["code"]))
        self.assertFalse(any(k == b"set-cookie" for k, _ in headers))
        self.assertEqual(before, self.stable_state())
        self.assertEqual([], self.repo.items.get(self.cart_id, []))
        self.assertEqual({}, self.repo.sales)

    def test_actual_unrecorded_operation_response_resolves_nested_oneof_refs_strictly(self):
        self.start()
        before = copy.deepcopy(self.repo.__dict__)
        operation = str(uuid4())
        status, _, value = self.request("GET", f"/api/carts/{self.cart_id}/operations/{operation}")
        self.assertEqual(200, status)
        self.assertEqual(
            ("NOT_FOUND", None, None),
            (value["operation_status"], value["applied_version"], value["new_cart_id"]),
        )
        verifier.validate_response("getOperation", status, value)
        self.assertEqual(before, self.repo.__dict__)
        invalid = copy.deepcopy(value)
        invalid["applied_version"] = 7
        with self.assertRaises(ValidationError):
            verifier.validate_response("getOperation", status, invalid)


class VerifierGuards(unittest.TestCase):
    def test_retry_uses_new_schema_for_effective_connection_and_actual_asgi_settings(self):
        captured = []

        class Cursor:
            def __init__(self, database):
                self.database = database
                self.sql = ""

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def execute(self, sql):
                self.sql = sql

            def fetchone(self):
                if self.sql.startswith("SHOW SESSION"):
                    return {"Value": "fake cipher"}
                return dict(db=self.database, ver="8.4.0", host="fixed", tls=1, gl=0, sl=0)

        def fake_connect(**kwargs):
            captured.append(kwargs)
            return SimpleNamespace(cursor=lambda: Cursor(kwargs["database"]), close=lambda: None)

        class CapturedSettings(Exception):
            pass

        def capture_settings(settings):
            self.assertEqual("pos_oct05_api_retry", settings.db_name)
            self.assertEqual("pos_oct05_api_retry_app", settings.db_user)
            raise CapturedSettings

        secrets = {"root": "fake", "pos_app": "fake", "relay": "fake"}
        initial = {"projection_sha256": "fresh"}
        data = {
            "REGISTER": [{"start_state": "UNSTARTED"}],
            "CART": [],
            "PRODUCT": [{"code": code} for code in verifier.PRODUCTS],
        }
        with (
            patch.object(verifier, "DB", "pos_oct05_api_retry"),
            patch.object(verifier, "HOSTNAME", "fixed"),
            patch.object(verifier, "secrets", return_value=secrets),
            patch.dict(
                sys.modules,
                {
                    "pymysql": SimpleNamespace(
                        connect=fake_connect, cursors=SimpleNamespace(DictCursor=object)
                    )
                },
            ),
            patch.object(verifier, "snapshot", return_value=initial),
            patch.dict(verifier.EVIDENCE, {"snapshots": {"fresh": {"data": data}}}),
            patch("app.main.create_app", side_effect=capture_settings),
        ):
            verifier.connect()
            verifier.connect(None)
            with self.assertRaises(CapturedSettings):
                asyncio.run(verifier.run())
        self.assertEqual(["pos_oct05_api_retry", None], [v["database"] for v in captured])
        self.assertTrue(all(v["ssl_verify_cert"] and v["ssl_verify_identity"] for v in captured))

    def test_offline_plan_never_reads_secrets_docker_or_db_and_has_unique_ids(self):
        # Importlib-loaded modules need registration for patch(__name__ + ...).
        import sys

        with patch.dict(sys.modules, {verifier.__name__: verifier}):
            with (
                patch.object(verifier, "connect", side_effect=AssertionError("DB forbidden")),
                patch.object(verifier, "secrets", side_effect=AssertionError("Secret forbidden")),
                patch.object(
                    verifier.subprocess, "run", side_effect=AssertionError("Docker forbidden")
                ),
            ):
                planned = asyncio.run(verifier.planned_tc11())
        self.assertEqual(len(planned), len(set(planned)))
        for op, _, _ in verifier.OPS:
            self.assertIn("TC11-" + op + "-normal", planned)

    def test_business_refusal_proof_detects_partial_line_mutation(self):
        old = {"CART": [{"version": "7"}], "CART_LINE": [{"quantity": 1}], "CART_OPERATION": []}
        new = copy.deepcopy(old)
        new["CART_OPERATION"] = [{"status": "REJECTED", "applied_version": None}]
        observations = {"old": {"data": old}, "new": {"data": new}}
        with patch.dict(verifier.EVIDENCE, {"snapshots": observations}):
            verifier.compare_business({"projection_sha256": "old"}, {"projection_sha256": "new"})
            new["CART_LINE"][0]["quantity"] = 2
            with self.assertRaises(ValueError):
                verifier.compare_business(
                    {"projection_sha256": "old"}, {"projection_sha256": "new"}
                )

    def test_failed_refusal_is_not_appended_as_passed_evidence(self):
        async def exercise():
            suite = verifier.Suite(None)

            async def request(*args, **kwargs):
                return {"code": "INVALID_INPUT"}, {"status": 422}

            values = [
                {"projection_sha256": "old", "connection_id": 1},
                {"projection_sha256": "changed", "connection_id": 2},
            ]
            with (
                patch.object(suite, "request", request),
                patch.object(verifier, "snapshot", side_effect=values),
                patch.dict(verifier.EVIDENCE, {"cases": []}),
            ):
                with self.assertRaises(ValueError):
                    await suite.check("probe", "addLine", "/api/test", unchanged=True)
                self.assertEqual([], verifier.EVIDENCE["cases"])

        asyncio.run(exercise())
