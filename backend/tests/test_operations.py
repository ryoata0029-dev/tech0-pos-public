"""Missing or unsafe offline evidence must never be treated as acceptance."""

import asyncio
import copy
import json
import logging
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from test_startup_api import http
from tools.operations.check_config import validate  # noqa: E402
from tools.operations.check_evidence import TABLES, performance, restore  # noqa: E402

from app.infrastructure.diagnostics import context, database_error, event
from app.main import create_app


class EvidenceTests(unittest.TestCase):
    def samples(self):
        value = {
            "environment": "AZURE",
            "samples": [
                {
                    "device": device,
                    "operation": operation,
                    "mode": mode,
                    "start_ms": 100,
                    "display_ms": 2100,
                    "confirmed": True,
                    "idle_ms": 1800000 if mode == "IDLE" else 0,
                    "no_access_confirmed": mode == "IDLE",
                    "conditions_id": "SAME_DATA_NETWORK",
                }
                for device in ("MAC_CHROME", "IPHONE_CHROME")
                for operation in ("PRODUCT", "MEMBER", "PURCHASE")
                for mode in ("NORMAL", "IDLE")
                for _ in range(10 if mode == "NORMAL" else 1)
            ],
        }

        for index, sample in enumerate(value["samples"]):
            sample["start_ms"] = index * 10000
            sample["display_ms"] = index * 10000 + 2000
        return value

    def test_performance_individual_limit_complete_devices_and_each_idle(self):
        value = self.samples()
        self.assertTrue(performance(value)["passed"])
        value["samples"][0]["display_ms"] += 1
        self.assertFalse(performance(value)["passed"])
        value = self.samples()
        value["samples"][-1]["idle_ms"] = 1799999
        with self.assertRaises(ValueError):
            performance(value)
        value = self.samples()
        value["samples"].pop()
        with self.assertRaises(ValueError):
            performance(value)
        value = self.samples()
        value["samples"][0]["confirmed"] = False
        with self.assertRaises(ValueError):
            performance(value)

    def test_performance_duplicate_record_is_not_ten_separate_measurements(self):
        value = self.samples()
        value["samples"][1] = copy.deepcopy(value["samples"][0])
        with self.assertRaises(ValueError):
            performance(value)

    def test_restore_checks_all_tables_and_preserves_missing_differences(self):
        source = {
            "snapshot_at": "2026-10-01T00:00:00+00:00",
            "consistent_read": True,
            "tables": {name: [] for name in TABLES},
        }
        target = copy.deepcopy(source)
        self.assertTrue(restore(source, target)["equal"])
        source["tables"]["PURCHASE"] = ["a" * 64]
        self.assertEqual(1, restore(source, target)["differences"]["PURCHASE"]["source_only"])
        del target["tables"]["CART_OPERATION"]
        with self.assertRaises(ValueError):
            restore(source, target)

    def test_config_disallows_open_networks_invalid_origins_and_missing_values(self):
        value = {
            "frontend_outbound_cidrs": ["8.8.8.8/32"],
            "backend_outbound_ips": ["8.8.4.4"],
            "operator_cidrs": ["1.1.1.1/32"],
            "frontend_origin": "https://front.invalid",
            "backend_url": "https://back.invalid",
            "deployment_version": "v1",
            "log_retention_days": 7,
            "log_quota_mb": 100,
        }
        validate(value)
        for field, invalid in (
            ("operator_cidrs", ["0.0.0.0/0"]),
            ("backend_outbound_ips", ["0.0.0.0"]),
            ("frontend_origin", "https://front.invalid/path"),
            ("frontend_outbound_cidrs", []),
        ):
            with self.assertRaises(ValueError):
                validate(value | {field: invalid})

    def test_logs_classify_numeric_errno_without_exception_text_or_secret_version(self):
        state = {}
        token = context.set(state)
        try:

            class Error(Exception):
                orig = Exception(1213, "PRIVATE SQL PASSWORD")

            database_error(Error())
            self.assertEqual("DEADLOCK", state["db_error"])
            with patch.dict("os.environ", {"POS_DEPLOYMENT_VERSION": "SECRET\nPRIVATE"}):
                with patch.object(logging.getLogger("pos.events"), "log") as output:
                    event(
                        request_id="test",
                        route="/api/members/{code}",
                        elapsed_ms=1,
                        status=503,
                        state=state,
                    )
                serialized = output.call_args.args[1]
                self.assertNotIn("PRIVATE", serialized)
                self.assertEqual("INVALID", json.loads(serialized)["deployment_version"])
            with patch.object(logging.getLogger("pos.events"), "log", side_effect=OSError):
                event(request_id="test", route="UNKNOWN_ROUTE", elapsed_ms=1, status=200, state={})
        finally:
            context.reset(token)

    def test_health_reads_no_database_and_does_not_log_success(self):
        app = create_app()
        with patch("app.main.event") as output:
            response = asyncio.run(http(app, "GET", "/health", []))
            self.assertEqual(200, response[0])
            self.assertEqual({"status": "alive"}, response[2])
            output.assert_not_called()
        with patch("app.main.event") as output:
            response = asyncio.run(http(app, "GET", "/unknown/PRIVATE", []))
            self.assertEqual(404, response[0])
            self.assertEqual("UNKNOWN_ROUTE", output.call_args.kwargs["route"])
