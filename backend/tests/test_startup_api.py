"""ASGI HTTP tests use an explicit in-memory repository, never a production fallback."""

import asyncio
import copy
import json
import unittest
from contextlib import contextmanager
from http.cookies import SimpleCookie
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from support.startup import MemoryRepository, passwords

from app.infrastructure.settings import Settings
from app.main import create_app
from app.services.errors import unavailable

ORIGIN = "https://pos.example.invalid"
SETTINGS = Settings(
    ORIGIN,
    "test-only-relay-value-not-a-credential",
    "db.example.invalid",
    3306,
    "pos_validation",
    "test",
    "unused",
    "/unused",
)
CONTRACT = json.loads((Path(__file__).resolve().parents[2] / "API契約.openapi.json").read_text())
CONTRACT["$schema"] = "https://json-schema.org/draft/2020-12/schema"
REGISTRY = Registry().with_resource("urn:pos", Resource.from_contents(CONTRACT))


async def http(app, method, path, headers, body=b""):
    sent = []
    delivered = False

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        await asyncio.Future()

    async def send(message):
        sent.append(message)

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1",
            "method": method,
            "scheme": "https",
            "path": path.split("?")[0],
            "raw_path": path.split("?")[0].encode(),
            "query_string": path.partition("?")[2].encode(),
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers],
            "server": ("pos.example.invalid", 443),
            "client": ("127.0.0.1", 1234),
            "root_path": "",
        },
        receive,
        send,
    )
    start = next(x for x in sent if x["type"] == "http.response.start")
    data = b"".join(x.get("body", b"") for x in sent if x["type"] == "http.response.body")
    return start["status"], start["headers"], json.loads(data)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.repo = MemoryRepository()
        self.app = create_app(SETTINGS)
        self.app.state.engine = object()
        self.app.state.passwords = passwords()
        self.jar = {}
        self.commits = 0
        self.break_commit = False

        @contextmanager
        def tx(engine, *, readonly=False):
            before = copy.deepcopy(self.repo.__dict__)
            try:
                yield object()
                if self.break_commit:
                    raise unavailable()
                if not readonly:
                    self.commits += 1
                else:
                    self.assertEqual(before, self.repo.__dict__)
            except Exception:
                self.repo.__dict__ = before
                raise

        self.addCleanup(patch.stopall)
        patch("app.api.startup.transaction", tx).start()
        patch("app.api.startup.BusinessRepository", return_value=self.repo).start()

    def request(self, method, path, body=None, *, change=None, raw=None):
        headers = {
            "x-pos-relay": SETTINGS.relay_secret,
            "origin": ORIGIN,
            "x-pos-request": "1",
            "content-type": "application/json",
        }
        headers["cookie"] = "; ".join(f"{k}={v}" for k, v in self.jar.items())
        for key, value in (change or {}).items():
            if value is None:
                headers.pop(key, None)
            else:
                headers[key] = value
        payload = raw if raw is not None else (b"" if body is None else json.dumps(body).encode())
        result = asyncio.run(http(self.app, method, path, list(headers.items()), payload))
        status, response_headers, data = result
        self.assertIn((b"cache-control", b"no-store"), response_headers)
        for key, value in response_headers:
            if key == b"set-cookie":
                parsed = SimpleCookie(value.decode())
                for name, morsel in parsed.items():
                    self.jar[name] = morsel.value
                    self.assertTrue(morsel["secure"])
                    self.assertTrue(morsel["httponly"])
                    self.assertEqual("lax", morsel["samesite"])
                    self.assertEqual("/", morsel["path"])
                    self.assertEqual("", morsel["domain"])
        if status >= 400:
            self.validate(data, "Error")
        return result

    def validate(self, value, schema):
        Draft202012Validator(
            {"$ref": f"urn:pos#/components/schemas/{schema}"}, registry=REGISTRY
        ).validate(value)

    def login(self):
        result = self.request(
            "POST", "/api/login", {"staff_id": "STAFF_A", "password": "test-only-input"}
        )
        self.assertEqual(200, result[0])
        self.validate(result[2], "Auth")
        return result

    def test_full_initial_http_flow_matches_openapi(self):
        self.login()
        self.assertEqual(
            200,
            self.request("GET", "/api/auth/status", change={"origin": None, "x-pos-request": None})[
                0
            ],
        )
        for path in ["start", "confirm", "confirm"]:
            status, headers, body = self.request("POST", f"/api/register/{path}")
            self.assertEqual(200, status)
            self.validate(body, "Register")
        first = self.request("POST", "/api/carts")
        second = self.request("POST", "/api/carts")
        self.assertEqual(first[2], second[2])
        self.validate(first[2], "CartResult")
        self.assertEqual(first[2], self.request("GET", "/api/resume")[2])
        self.assertEqual(1, len(self.repo.carts))
        self.assertFalse(any(k == b"set-cookie" for k, v in second[1]))

    def test_origin_and_relay_rejection_precedes_any_write(self):
        for path in [
            "/api/login",
            "/api/reauth",
            "/api/register/start",
            "/api/register/confirm",
            "/api/carts",
        ]:
            for key, value in [
                ("origin", None),
                ("origin", "null"),
                ("origin", ORIGIN + "/"),
                ("origin", "https://evil.invalid"),
                ("x-pos-request", None),
                ("x-pos-request", "0"),
                ("x-pos-relay", None),
                ("x-pos-relay", "untrusted"),
            ]:
                result = self.request("POST", path, change={key: value})
                self.assertEqual(403, result[0], (path, key, value))
        self.assertEqual(0, self.commits)
        self.assertEqual({}, self.repo.limits)

    def test_input_errors_do_not_reflect_password_or_coerce_staff(self):
        for value in [None, 4, True, "", "a\n", "full width Ａ"]:
            result = self.request("POST", "/api/login", {"staff_id": value, "password": "PRIVATE"})
            self.assertEqual(422, result[0])
            self.assertNotIn("PRIVATE", str(result))
        for body in [
            {"staff_id": "A"},
            {"staff_id": "A", "password": None},
            {"staff_id": "A", "password": "PRIVATE", "price": 10},
        ]:
            self.assertEqual(422, self.request("POST", "/api/login", body)[0])
        self.assertEqual(422, self.request("POST", "/api/carts", {})[0])
        self.assertEqual(422, self.request("GET", "/api/auth/status?staff_id=A")[0])
        self.assertEqual(0, self.commits)

    def test_failed_login_commits_limit_then_returns_401_without_cookie_changes(self):
        self.login()
        jar = self.jar.copy()
        before = self.commits
        result = self.request("POST", "/api/reauth", {"staff_id": "STAFF_A", "password": "wrong"})
        self.assertEqual(401, result[0])
        self.assertEqual(before + 1, self.commits)
        self.assertEqual(1, len(json.loads(self.repo.limits["STAFF_A"]["failure_times"])))
        self.assertEqual(jar, self.jar)

    def test_commit_failure_is_503_not_auth_failure_and_never_sets_cookie(self):
        self.break_commit = True
        result = self.request(
            "POST", "/api/login", {"staff_id": "STAFF_A", "password": "test-only-input"}
        )
        self.assertEqual(503, result[0])
        self.assertEqual({}, self.jar)
        self.assertEqual({}, self.repo.sessions)
        self.assertEqual({}, self.repo.limits)

    def test_unauthenticated_read_and_write_protected(self):
        for method, path in [
            ("GET", "/api/auth/status"),
            ("GET", "/api/products/0001"),
            ("GET", "/api/members/A"),
            ("GET", "/api/resume"),
            ("POST", "/api/register/start"),
            ("POST", "/api/carts"),
        ]:
            self.assertEqual(401, self.request(method, path)[0])
        self.assertEqual({}, self.repo.contexts)

    def test_unknown_error_sanitized_and_missing_configuration_closed(self):
        self.app.state.engine = None
        result = self.request("GET", "/api/auth/status")
        self.assertEqual(503, result[0])
        self.app.state.settings = None
        self.assertEqual(503, self.request("GET", "/api/auth/status")[0])
