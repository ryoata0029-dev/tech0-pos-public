"""Oct05 fixed-schema ASGI/API verification. Offline by default; root runs DB actions."""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import traceback
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlencode
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".oct05-mac-local"
OUT = ROOT / "docs/implementation/evidence/oct05-mac"
PROFILE = "oct05-mac"
NAME = "tech0-pos-oct05-mac-mysql"
DB = "pos_oct05_api"
ORIGIN = "https://localhost:8463"
PORT = 3327
STAFF = "STAFF_API_A"
MEMBER = "MEM_API"
MAX_VERSION = 18446744073709551615
USERS = {"root": "root", "pos_oct05_api_app": "pos_app"}
USERS.update(pos_oct05_api_master="pos_master", pos_oct05_api_schema="pos_schema")
PRODUCTS = {"P103": (103, "0.10"), "MAX_A": (600000000000, "0")}
PRODUCTS.update(MAX_B=(500000000000, "0"), GROSS_MAX=(999999999999, "0.10"))
PRODUCTS.update({"A" * 32: (1, "0"), "Case_a": (2, "0"), "case_a": (3, "0")})
OPS = (
    ("login", "POST", "/api/login"),
    ("reauth", "POST", "/api/reauth"),
    ("authStatus", "GET", "/api/auth/status"),
    ("product", "GET", "/api/products/{code}"),
    ("member", "GET", "/api/members/{id}"),
    ("registerStart", "POST", "/api/register/start"),
    ("registerStatus", "GET", "/api/register/status"),
    ("registerConfirm", "POST", "/api/register/confirm"),
    ("createCart", "POST", "/api/carts"),
    ("resume", "GET", "/api/resume"),
    ("getCart", "GET", "/api/carts/{id}"),
    ("syncCart", "POST", "/api/carts/{id}/sync"),
    ("addLine", "POST", "/api/carts/{id}/lines"),
    ("setQuantity", "PATCH", "/api/carts/{id}/lines/{line_id}"),
    ("deleteLine", "DELETE", "/api/carts/{id}/lines/{line_id}"),
    ("setMember", "PUT", "/api/carts/{id}/member"),
    ("purchase", "POST", "/api/purchases"),
    ("getPurchase", "GET", "/api/carts/{id}/purchase"),
    ("resolvePurchase", "POST", "/api/carts/{id}/resolve-purchase"),
    ("reopen", "POST", "/api/carts/{id}/reopen"),
    ("next", "POST", "/api/carts/{id}/next"),
    ("getOperation", "GET", "/api/carts/{id}/operations/{operation_id}"),
)
SPEC = json.loads((ROOT / "API契約.openapi.json").read_text())
EVIDENCE = {"transport": "actual ASGI + TLS MySQL; no HTTPS/browser", "schema": DB}
EVIDENCE.update(cases=[], snapshots={}, completed=False)
HOSTNAME = None
STAGE = "offline"
_CURRENT_DB = object()


def require(value, message):
    if not value:
        raise ValueError(message)


def encode(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC).isoformat()
    raise TypeError("Unsupported evidence value")


def statements(path):
    return [s.strip() for s in re.sub(r"--[^\n]*", "", path.read_text()).split(";") if s.strip()]


def absolute_refs(value):
    """Keep nested oneOf/anyOf references anchored to the complete contract resource."""
    if isinstance(value, list):
        return [absolute_refs(item) for item in value]
    if isinstance(value, dict):
        return {
            key: "urn:pos" + item if key == "$ref" and item.startswith("#") else absolute_refs(item)
            for key, item in value.items()
        }
    return value


def validate_response(op, status, payload):
    from jsonschema import Draft202012Validator, FormatChecker
    from referencing import Registry, Resource

    method, template = next((m, p) for key, m, p in OPS if key == op)
    response_spec = SPEC["paths"][template][method.lower()]["responses"].get(str(status))
    require(response_spec is not None, "Response code not in operation contract")
    if "$ref" in response_spec:
        response_spec = SPEC["components"]["responses"][response_spec["$ref"].rsplit("/", 1)[1]]
    schema = absolute_refs(response_spec["content"]["application/json"]["schema"])
    document = dict(SPEC, **{"$schema": "https://json-schema.org/draft/2020-12/schema"})
    registry = Registry().with_resource("urn:pos", Resource.from_contents(document))
    Draft202012Validator(schema, registry=registry, format_checker=FormatChecker()).validate(
        payload
    )


def replay_original():
    """Read only already recorded public responses; never contact/recover the original DB."""
    p = OUT / "api-run.json"
    require(p.exists() and not p.is_symlink(), "Original evidence required")
    data = json.loads(p.read_text())
    require(
        data["schema"] == "pos_oct05_api" and data["status"] == "stopped",
        "Original stopped evidence required",
    )
    for case in data["cases"]:
        validate_response(case["operation"], case["result"]["status"], case["response"])
    return {
        "offline_replayed_responses": len(data["cases"]),
        "original_source_sha256": data["source_sha256"],
        "original_evidence_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        "original_evidence_modified": False,
    }


def secrets():
    p = LOCAL / "secrets.json"
    require(not p.is_symlink() and p.stat().st_mode & 0o077 == 0, "Private file required")
    data = json.loads(p.read_text())
    require(
        all(
            isinstance(data.get(k), str) and data[k]
            for k in (*USERS.values(), "STAFF_A", "STAFF_B", "relay")
        ),
        "Fresh secret shape incomplete",
    )
    return data


def guard():
    global HOSTNAME
    require(os.environ.get("M2_LOCAL_PROFILE") == PROFILE, "Fixed oct05 profile required")
    require(LOCAL.resolve() == LOCAL and OUT.resolve() == OUT, "Symlink resource refused")
    result = subprocess.run(["docker", "inspect", NAME], capture_output=True, text=True, check=True)
    rows = json.loads(result.stdout)
    require(len(rows) == 1, "Single fixed container required")
    row = rows[0]
    initial_path = OUT / "mysql-environment.json"
    require(
        initial_path.exists() and not initial_path.is_symlink(), "Fresh environment evidence absent"
    )
    initial = json.loads(initial_path.read_text())
    require(row["Id"] == initial.get("container_id"), "Container replaced since fresh setup")
    require(row["Name"] == "/" + NAME and row["State"]["Running"], "Fresh container not running")
    require(
        row["NetworkSettings"]["Ports"].get("3306/tcp")
        == [{"HostIp": "127.0.0.1", "HostPort": str(PORT)}],
        "Wrong fixed port",
    )
    require(
        any(
            m.get("Name") == NAME + "-data" and m["Destination"] == "/var/lib/mysql"
            for m in row["Mounts"]
        ),
        "Wrong fixed volume",
    )
    HOSTNAME = row["Config"]["Hostname"]
    EVIDENCE["container_id"] = row["Id"]


def connect(database=_CURRENT_DB, *, readonly=False):
    import pymysql

    if database is _CURRENT_DB:
        database = DB
    c = pymysql.connect(
        host="127.0.0.1",
        port=PORT,
        user="root",
        password=secrets()["root"],
        database=database,
        charset="utf8mb4",
        autocommit=False,
        ssl_ca=str(LOCAL / "tls/ca.crt"),
        ssl_verify_cert=True,
        ssl_verify_identity=True,
        connect_timeout=3,
        read_timeout=5,
        write_timeout=5,
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with c.cursor() as q:
            q.execute("SET SESSION time_zone='+00:00'")
            q.execute(
                "SET SESSION sql_mode='STRICT_ALL_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,"
                "ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION'"
            )
            q.execute("SET SESSION innodb_lock_wait_timeout=1")
            q.execute("SHOW SESSION STATUS LIKE 'Ssl_cipher'")
            require(bool(q.fetchone()["Value"]), "TLS missing")
            q.execute(
                "SELECT DATABASE() db,VERSION() ver,@@hostname host,@@require_secure_transport tls,"
                "@@global.general_log gl,@@global.slow_query_log sl"
            )
            identity = q.fetchone()
            require(
                identity["db"] == database
                and identity["ver"].startswith("8.4.")
                and identity["host"] == HOSTNAME
                and identity["tls"]
                and not identity["gl"]
                and not identity["sl"],
                "Wrong TLS DB identity/logging",
            )
            if readonly:
                q.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                q.execute("START TRANSACTION READ ONLY")
        return c
    except BaseException:
        c.close()
        raise


def prepare():
    from app.security.credentials import Passwords

    with connect(None) as c, c.cursor() as q:
        q.execute("SHOW DATABASES LIKE %s", (DB,))
        require(q.fetchone() is None, "Schema exists; no reset")
        for user in USERS:
            if user != "root":
                q.execute("SELECT COUNT(*) n FROM mysql.user WHERE User=%s", (user,))
                require(q.fetchone()["n"] == 0, "Account exists; no reuse")
        require(DB in ("pos_oct05_api", "pos_oct05_api_retry"), "Schema allowlist required")
        q.execute("CREATE DATABASE `" + DB + "` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin")
        for user, key in USERS.items():
            if user != "root":
                q.execute(
                    "CREATE USER %s@'%%' IDENTIFIED BY %s REQUIRE SSL", (user, secrets()[key])
                )
        c.commit()
    with connect() as c, c.cursor() as q:
        for sql in statements(ROOT / "設計スキーマ.sql"):
            require(sql.startswith(("CREATE TABLE ", "ALTER TABLE ")), "Unexpected DDL")
            q.execute(sql)
        for sql in statements(ROOT / "backend/sql/m2_grants.sql"):
            if sql.startswith("SHOW GRANTS"):
                continue
            require(sql.startswith("GRANT "), "Unexpected grant")
            sql = sql.replace("`pos_validation`", "`" + DB + "`")
            for old in ("pos_app", "pos_master", "pos_schema"):
                sql = sql.replace("'" + old + "'", "'" + DB + "_" + old[4:] + "'")
            q.execute(sql)
        q.execute("INSERT INTO REGISTER(register_id,start_state) VALUES(1,'UNSTARTED')")
        for staff, key in ((STAFF, "STAFF_A"), ("STAFF_API_B", "STAFF_B")):
            q.execute(
                "INSERT INTO STAFF(staff_id,password_hash) VALUES(%s,%s)",
                (staff, Passwords().hash(secrets()[key])),
            )
        q.execute(
            "INSERT INTO MEMBER(member_id,name,phone,address,gender,age) "
            "VALUES(%s,'架空会員','TEST','TEST','TEST',0)",
            (MEMBER,),
        )
        taxes = {}
        for rate in ("0", "0.10"):
            q.execute("INSERT INTO TAX_RATE(rate) VALUES(%s)", (rate,))
            taxes[rate] = q.lastrowid
        for code, (price, rate) in PRODUCTS.items():
            q.execute(
                "INSERT INTO PRODUCT(code,name,unit_price,tax_rate_id) VALUES(%s,%s,%s,%s)",
                (code, "架空商品 " + code, price, taxes[rate]),
            )
            product = q.lastrowid
            q.execute(
                "INSERT INTO PRICE_HISTORY(product_id,old_price,new_price,changed_at) "
                "VALUES(%s,NULL,%s,UTC_TIMESTAMP(6))",
                (product, price),
            )
            if code == "P103":
                q.execute(
                    "INSERT INTO DISCOUNT_CONDITION(product_id,valid_from,valid_to,kind,rate) "
                    "VALUES(%s,'2020-01-01','2099-01-01','RATE',0.10)",
                    (product,),
                )
        c.commit()
        for sql in statements(ROOT / "backend/sql/m2_revoke_initial.sql"):
            if sql.startswith("SHOW GRANTS"):
                continue
            require(sql.startswith("REVOKE "), "Unexpected revoke")
            q.execute(
                sql.replace("`pos_validation`", "`" + DB + "`").replace(
                    "'pos_master'", "'" + DB + "_master'"
                )
            )
        c.commit()
    return {"fresh_schema_created": True, "codes": list(PRODUCTS), "accounts": list(USERS)[1:]}


def snapshot():
    # Export only non-secret projections; all business rows are dedicated synthetic data.
    data = {}
    with connect(readonly=True) as c, c.cursor() as q:
        q.execute("SELECT CONNECTION_ID() id,UTC_TIMESTAMP(6) at_utc")
        meta = q.fetchone()
        columns = {
            "REGISTER": (
                "register_id,start_state,maintenance_hold,active_context_id,current_cart_id"
            ),
            "AUTH_SESSION": "staff_id,register_id,created_at,expires_at,revoked_at",
            "BROWSER_CONTEXT": "context_id,register_id,starting_staff_id,created_at,confirmed_at,"
            "last_business_at,manual_released_at,invalidated_at",
        }
        for table in (
            "REGISTER",
            "AUTH_SESSION",
            "AUTH_LOGIN_LIMIT",
            "BROWSER_CONTEXT",
            "CART",
            "CART_LINE",
            "CART_OPERATION",
            "PURCHASE",
            "PURCHASE_LINE",
            "PURCHASE_TAX",
            "PRODUCT",
            "PRICE_HISTORY",
            "DISCOUNT_CONDITION",
            "TAX_RATE",
        ):
            q.execute("SELECT " + columns.get(table, "*") + " FROM " + table)
            rows = q.fetchall()
            data[table] = sorted(rows, key=lambda r: json.dumps(r, default=encode, sort_keys=True))
    encoded = json.dumps(data, default=encode, sort_keys=True, ensure_ascii=False)
    key = hashlib.sha256(encoded.encode()).hexdigest()
    EVIDENCE["snapshots"].setdefault(key, {"data": json.loads(encoded)})
    return {"projection_sha256": key, "connection_id": meta["id"], "at_utc": meta["at_utc"]}


def variants(op, body):
    """Single invalid variable per request; identity values are fixed after planning."""
    if body is None:
        yield "hidden-body", {"body": {}}
        if op != "deleteLine":
            yield "unknown-query", {"query": "unexpected=1"}
        return
    yield "body-absent", {"raw": b""}
    yield "malformed-json", {"raw": b"{"}
    for field, value in body.items():
        missing = dict(body)
        del missing[field]
        yield "missing-" + field, {"body": missing}
        if field != "member_id":
            yield "null-" + field, {"body": dict(body, **{field: None})}
        wrong = True if isinstance(value, int) else 7
        yield "type-" + field, {"body": dict(body, **{field: wrong})}
        if field in ("operation_id", "cart_id"):
            for tag, invalid in (
                ("bad", "bad"),
                ("uppercase", "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"),
                ("v1", "aaaaaaaa-aaaa-1aaa-8aaa-aaaaaaaaaaaa"),
            ):
                yield tag + "-" + field, {"body": dict(body, **{field: invalid})}
    yield "unknown-field", {"body": dict(body, unexpected=1)}
    yield "unknown-query", {"query": "unexpected=1"}
    if "version" in body:
        for value in ("0", "01", str(MAX_VERSION + 1)):
            yield "version-" + value, {"body": dict(body, version=value)}
    if op in ("addLine", "setQuantity", "setMember", "purchase"):
        for field in ("unit_price", "tax_rate", "total", "staff_id"):
            yield "untrusted-" + field, {"body": dict(body, **{field: "1"})}


class Suite:
    def __init__(self, app):
        self.app = app
        self.cookies = {}
        self.cart = None
        self.normal = set()

    def operation(self, **extra):
        return {"operation_id": str(uuid4()), "version": self.cart["version"], **extra}

    async def request(
        self,
        op,
        path,
        *,
        body=None,
        raw=None,
        query="",
        headers=None,
        cookie_changes=None,
        expected=200,
        retain=True,
    ):
        method = next(m for key, m, _ in OPS if key == op)
        data = raw if raw is not None else json.dumps(body).encode() if body is not None else b""
        jar = self.cookies | (cookie_changes or {})
        values = {
            "origin": ORIGIN,
            "x-pos-request": "1",
            "x-pos-relay": secrets()["relay"],
            "content-type": "application/json",
            "cookie": "; ".join(f"{k}={v}" for k, v in jar.items() if v is not None),
        }
        if method == "GET":
            values.pop("origin")
            values.pop("x-pos-request")
        for k, v in (headers or {}).items():
            if v is None:
                values.pop(k, None)
            else:
                values[k] = v
        sent = []
        delivered = False

        async def receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": data, "more_body": False}
            await asyncio.Future()

        async def send(value):
            sent.append(value)

        await self.app(
            {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.4"},
                "http_version": "1.1",
                "method": method,
                "scheme": "https",
                "path": path,
                "raw_path": path.encode(),
                "query_string": query.encode(),
                "headers": [(k.encode(), v.encode()) for k, v in values.items()],
                "server": ("localhost", 8464),
                "client": ("127.0.0.1", 12345),
                "root_path": "",
            },
            receive,
            send,
        )
        start = next(v for v in sent if v["type"] == "http.response.start")
        payload = json.loads(b"".join(v.get("body", b"") for v in sent))
        require(start["status"] == expected, "Unexpected response status")
        require((b"cache-control", b"no-store") in start["headers"], "No-store missing")
        validate_response(op, expected, payload)
        cookies = [(k, v) for k, v in start["headers"] if k.lower() == b"set-cookie"]
        if expected in (401, 403):
            require(
                "current" not in payload and set(payload) == {"code", "message"}, "Protected leak"
            )
        if expected >= 400:
            require(not cookies, "Refusal unexpectedly mutates cookies")
        for _, v in cookies:
            text = v.decode()
            require(
                all(x in text.lower() for x in ("secure", "httponly", "samesite=lax", "path=/"))
                and "domain=" not in text.lower(),
                "Unsafe cookie",
            )
            name, token = text.split(";", 1)[0].split("=", 1)
            require(re.fullmatch(r"[A-Za-z0-9_-]{43}", token), "Bad cookie shape")
            if retain:
                self.cookies[name] = token
        if retain and "cart" in payload:
            self.cart = payload["cart"]
        return payload, {
            "status": start["status"],
            "code": payload.get("code"),
            "set_cookie_count": len(cookies),
        }

    async def check(self, case_id, op, path, *, unchanged=False, expected_code=None, **kwargs):
        global STAGE
        STAGE = case_id
        before = snapshot()
        payload, result = await self.request(op, path, **kwargs)
        if expected_code is not None:
            require(payload.get("code") == expected_code, "Unexpected machine code")
        after = snapshot()
        require(before["connection_id"] != after["connection_id"], "Observer reused connection")
        if unchanged:
            require(
                before["projection_sha256"] == after["projection_sha256"],
                "Rejected/read changed DB",
            )
        EVIDENCE["cases"].append(
            {
                "id": case_id,
                "operation": op,
                "result": result,
                "before": before,
                "after": after,
                "unchanged": unchanged,
                "response": payload,
            }
        )
        return payload

    async def matrix(self, op, path, body=None, query=""):
        prefix = "TC11-" + op
        for tag, change in variants(op, body):
            options = {"body": body, "query": query} | change
            await self.check(
                prefix + "-" + tag,
                op,
                path,
                expected=422,
                retain=False,
                unchanged=True,
                **options,
            )
        if op == "deleteLine":
            parsed = dict(x.split("=", 1) for x in query.split("&"))
            alternatives = [
                ("query-missing-" + k, urlencode({a: b for a, b in parsed.items() if a != k}))
                for k in parsed
            ]
            alternatives += [
                ("query-unknown", query + "&unexpected=1"),
                ("query-duplicate", query + "&version=" + parsed["version"]),
            ]
            alternatives += [
                ("query-bad-" + k, urlencode(parsed | {k: v}))
                for k, v in (
                    ("operation_id", "bad"),
                    ("version", "01"),
                    ("version", str(MAX_VERSION + 1)),
                )
            ]
            for i, (tag, text) in enumerate(alternatives):
                await self.check(
                    prefix + "-" + tag + str(i),
                    op,
                    path,
                    query=text,
                    expected=422,
                    retain=False,
                    unchanged=True,
                )
        template = next(p for key, _, p in OPS if key == op)
        for parameter in re.findall(r"\{([^}]+)\}", template):
            if op in ("product", "member"):
                invalids = ("bad code", "Ａ", "A" * 33)
            else:
                invalids = (
                    "bad",
                    "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA",
                    "aaaaaaaa-aaaa-1aaa-8aaa-aaaaaaaaaaaa",
                )
            pieces = template.split("/")
            position = pieces.index("{" + parameter + "}")
            for i, value in enumerate(invalids):
                actual = path.split("/")
                actual[position] = value
                await self.check(
                    prefix + f"-path-{parameter}-{i}",
                    op,
                    "/".join(actual),
                    body=body,
                    query=query,
                    expected=422,
                    retain=False,
                    unchanged=True,
                )
        method = next(m for key, m, _ in OPS if key == op)
        if method != "GET":
            for i, header in enumerate(
                (
                    {"origin": None},
                    {"origin": "null"},
                    {"origin": "https://invalid.example"},
                    {"x-pos-request": None},
                    {"x-pos-request": "0"},
                )
            ):
                await self.check(
                    prefix + f"-header-{i}",
                    op,
                    path,
                    body=body,
                    query=query,
                    headers=header,
                    expected=403,
                    retain=False,
                    unchanged=True,
                )
        if op not in ("login", "reauth"):
            for i, token in enumerate((None, "A" * 43)):
                await self.check(
                    prefix + f"-auth-{i}",
                    op,
                    path,
                    body=body,
                    query=query,
                    cookie_changes={"__Host-pos_session": token},
                    expected=401,
                    retain=False,
                    unchanged=True,
                )
            with expired_auth():
                await self.check(
                    prefix + "-auth-expired-sql",
                    op,
                    path,
                    body=body,
                    query=query,
                    expected=401,
                    retain=False,
                    unchanged=True,
                )
        if (
            op not in ("login", "reauth", "authStatus", "registerStart")
            and "__Host-pos_resume" in self.cookies
        ):
            for i, token in enumerate((None, "B" * 43)):
                await self.check(
                    prefix + f"-resume-{i}",
                    op,
                    path,
                    body=body,
                    query=query,
                    cookie_changes={"__Host-pos_resume": token},
                    expected=403,
                    retain=False,
                    unchanged=True,
                )
        # Local missing engine proves sanitized contract only, not a live network outage.
        engine = self.app.state.engine
        try:
            self.app.state.engine = None
            await self.check(
                prefix + "-unavailable-engine",
                op,
                path,
                body=body,
                query=query,
                expected=503,
                retain=False,
                unchanged=True,
            )
        finally:
            self.app.state.engine = engine

    async def normal_call(self, op, path, body=None, query="", expected=200, unchanged=False):
        require(op not in self.normal, "Normal operation duplicated")
        await self.matrix(op, path, body, query)
        value = await self.check(
            "TC11-" + op + "-normal",
            op,
            path,
            body=body,
            query=query,
            expected=expected,
            unchanged=unchanged,
        )
        self.normal.add(op)
        return value


async def run():
    from app.infrastructure.settings import Settings
    from app.main import create_app
    from app.services.business import BusinessService

    initial = snapshot()
    data = EVIDENCE["snapshots"][initial["projection_sha256"]]["data"]
    require(
        data["REGISTER"][0]["start_state"] == "UNSTARTED"
        and not data["CART"]
        and {p["code"] for p in data["PRODUCT"]} == set(PRODUCTS),
        "Run schema not fresh",
    )
    s = secrets()
    settings = Settings(
        ORIGIN,
        s["relay"],
        "127.0.0.1",
        PORT,
        DB,
        DB + "_app",
        s["pos_app"],
        str(LOCAL / "tls/ca.crt"),
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        require(app.state.engine is not None, "ASGI engine absent")
        suite = Suite(app)
        credentials = {"staff_id": STAFF, "password": s["STAFF_A"]}
        await suite.normal_call("login", "/api/login", credentials)
        await suite.normal_call("authStatus", "/api/auth/status", unchanged=True)
        await suite.normal_call("registerStatus", "/api/register/status", unchanged=True)
        await suite.normal_call("registerStart", "/api/register/start")
        await suite.normal_call("registerConfirm", "/api/register/confirm")
        await suite.normal_call("createCart", "/api/carts")
        with expired_auth():
            await suite.normal_call("reauth", "/api/reauth", credentials)
        await suite.check(
            "TC11-reauth-other-staff",
            "reauth",
            "/api/reauth",
            body={"staff_id": "STAFF_API_B", "password": s["STAFF_B"]},
            expected=403,
            unchanged=True,
        )
        await suite.normal_call("product", "/api/products/P103", unchanged=True)
        await suite.normal_call("member", "/api/members/MEM_API", unchanged=True)
        await suite.normal_call("resume", "/api/resume", unchanged=True)
        cart = suite.cart["cart_id"]
        base = "/api/carts/" + cart
        await suite.normal_call("getCart", base, unchanged=True)
        await suite.normal_call("syncCart", base + "/sync", suite.operation())
        added_body = suite.operation(code="P103")
        await suite.normal_call("addLine", base + "/lines", added_body)
        await suite.check(
            "TC12-key-order-replay",
            "addLine",
            base + "/lines",
            body=dict(reversed(list(added_body.items()))),
            unchanged=True,
        )
        await suite.check(
            "TC12-same-id-other-code",
            "addLine",
            base + "/lines",
            body=dict(added_body, code="MAX_A"),
            expected=409,
            unchanged=True,
        )
        await suite.check(
            "TC12-same-id-other-version",
            "addLine",
            base + "/lines",
            body=dict(added_body, version=suite.cart["version"]),
            expected=409,
            unchanged=True,
        )
        await suite.check(
            "TC12-old-version-new-id",
            "addLine",
            base + "/lines",
            body=dict(added_body, operation_id=str(uuid4())),
            expected=409,
            unchanged=True,
        )
        line = suite.cart["lines"][0]["line_id"]
        await suite.normal_call("setQuantity", base + "/lines/" + line, suite.operation(quantity=3))
        await suite.normal_call("setMember", base + "/member", suite.operation(member_id=MEMBER))
        require(
            suite.cart["subtotal"] == "279" and suite.cart["total"] == "306",
            "Member independent amount",
        )
        await suite.check(
            "TC11-setMember-null-normal",
            "setMember",
            base + "/member",
            body=suite.operation(member_id=None),
        )
        require(
            suite.cart["member_state"] == "NON_MEMBER" and suite.cart["total"] == "339",
            "Null member amount",
        )

        # Actual receipt COMMIT, controlled finish read: no sale writer starts here.
        def deferred_finish(service, auth, resume, cart_id, operation_id, payload):
            return service.read(auth, resume, cart_id, operation_id)

        with patch.object(BusinessService, "finish_purchase", deferred_finish):
            await suite.normal_call(
                "purchase", "/api/purchases", suite.operation(cart_id=cart), expected=202
            )
        require(suite.cart["state"] == "SAVING", "Receipt did not persist SAVING")
        await suite.normal_call("getPurchase", base + "/purchase", unchanged=True)
        await suite.normal_call(
            "getOperation", base + "/operations/" + str(uuid4()), unchanged=True
        )
        await suite.normal_call("resolvePurchase", base + "/resolve-purchase", suite.operation())
        require(suite.cart["state"] == "UNSAVED", "Resolve did not persist UNSAVED")
        await suite.normal_call("reopen", base + "/reopen", suite.operation())
        query = urlencode(suite.operation())
        await suite.normal_call("deleteLine", base + "/lines/" + line, query=query)
        await suite.check(
            "TC12-delete-replay", "deleteLine", base + "/lines/" + line, query=query, unchanged=True
        )
        await bounded(suite)
        # End normal sale and NEXT after all bounded failures leave a known valid line.
        await suite.check(
            "TC11-purchase-saved",
            "purchase",
            "/api/purchases",
            body=suite.operation(cart_id=suite.cart["cart_id"]),
        )
        saved = snapshot()
        saved_data = EVIDENCE["snapshots"][saved["projection_sha256"]]["data"]
        require(
            len(saved_data["PURCHASE"])
            == len(saved_data["PURCHASE_LINE"])
            == len(saved_data["PURCHASE_TAX"])
            == 1,
            "Expected one sale/detail/tax",
        )
        require(
            saved_data["PURCHASE"][0]["subtotal"] == "103"
            and saved_data["PURCHASE"][0]["total"] == "113"
            and saved_data["PURCHASE_LINE"][0]["line_subtotal"] == "103"
            and saved_data["PURCHASE_TAX"][0]["tax_amount"] == "10",
            "Independent saved amount mismatch",
        )
        await suite.normal_call("next", base + "/next", suite.operation())
        require(suite.cart["version"] == "1" and suite.cart["lines"] == [], "NEXT not empty v1")
        require(suite.normal == {op for op, _, _ in OPS}, "Not all 22 normal operations executed")
        EVIDENCE["normal_operation_count"] = len(suite.normal)
        await version_boundaries(suite)
        EVIDENCE["final"] = snapshot()
    EVIDENCE["completed"] = True


async def bounded(suite):
    base = "/api/carts/" + suite.cart["cart_id"]
    # Valid length32 and case sensitivity, with no implicit trimming or normalization.
    for code in ("A" * 32, "Case_a", "case_a"):
        await suite.check(
            "TC08-code-valid-" + code, "addLine", base + "/lines", body=suite.operation(code=code)
        )
    require(len(suite.cart["lines"]) == 3, "Case variants collapsed")
    for i, code in enumerate(("", "A" * 33, " P103", "P103 ", "Ｐ103")):
        await suite.check(
            "TC08-code-invalid-" + str(i),
            "addLine",
            base + "/lines",
            body=suite.operation(code=code),
            expected=422,
            unchanged=True,
        )
    for line in list(suite.cart["lines"]):
        await suite.check(
            "TC08-remove-valid-" + line["code"],
            "deleteLine",
            base + "/lines/" + line["line_id"],
            query=urlencode(suite.operation()),
        )
    await suite.check(
        "TC08-max-first-line", "addLine", base + "/lines", body=suite.operation(code="MAX_A")
    )
    before = snapshot()
    rejected = await suite.check(
        "TC08-line-overflow",
        "setQuantity",
        base + "/lines/" + suite.cart["lines"][0]["line_id"],
        body=suite.operation(quantity=2),
        expected=422,
    )
    require(rejected["code"] == "AMOUNT_INVALID", "Wrong line overflow code")
    after = snapshot()
    compare_business(before, after)
    before = after
    rejected = await suite.check(
        "TC08-transaction-overflow",
        "addLine",
        base + "/lines",
        body=suite.operation(code="MAX_B"),
        expected=422,
    )
    require(rejected["code"] == "AMOUNT_INVALID", "Wrong transaction overflow code")
    compare_business(before, snapshot())
    await suite.check(
        "TC08-remove-max",
        "deleteLine",
        base + "/lines/" + suite.cart["lines"][0]["line_id"],
        query=urlencode(suite.operation()),
    )
    before = snapshot()
    rejected = await suite.check(
        "TC08-gross-only-overflow",
        "addLine",
        base + "/lines",
        body=suite.operation(code="GROSS_MAX"),
        expected=422,
    )
    require(rejected["code"] == "AMOUNT_INVALID", "Wrong gross overflow code")
    compare_business(before, snapshot())
    await suite.check(
        "TC08-add-ordinary", "addLine", base + "/lines", body=suite.operation(code="P103")
    )
    line = suite.cart["lines"][0]["line_id"]
    for i, quantity in enumerate((0, 100, 1.5, "3", True)):
        await suite.check(
            "TC08-quantity-invalid-" + str(i),
            "setQuantity",
            base + "/lines/" + line,
            body=suite.operation(quantity=quantity),
            expected=422,
            unchanged=True,
        )
    await suite.check(
        "TC08-quantity99", "setQuantity", base + "/lines/" + line, body=suite.operation(quantity=99)
    )
    before = snapshot()
    await suite.check(
        "TC08-add-over99",
        "addLine",
        base + "/lines",
        body=suite.operation(code="P103"),
        expected=422,
        expected_code="QUANTITY_LIMIT",
    )
    compare_business(before, snapshot())
    await suite.check(
        "TC08-quantity1", "setQuantity", base + "/lines/" + line, body=suite.operation(quantity=1)
    )
    constraints(suite.cart["cart_id"], line)


async def version_boundaries(suite):
    base = "/api/carts/" + suite.cart["cart_id"]
    await suite.check(
        "TC12-next-cart-line", "addLine", base + "/lines", body=suite.operation(code="P103")
    )
    for version in (
        9007199254740991,
        9007199254740992,
        9007199254740993,
        MAX_VERSION - 2,
        MAX_VERSION - 1,
        MAX_VERSION,
    ):
        with connect() as c, c.cursor() as q:
            q.execute(
                "UPDATE CART SET version=%s WHERE cart_id=%s", (version, suite.cart["cart_id"])
            )
            q.execute("SELECT version FROM CART WHERE cart_id=%s", (suite.cart["cart_id"],))
            require(q.fetchone()["version"] == version, "Fixed version target missing")
            c.commit()
        await suite.check("TC12-read-version-" + str(version), "getCart", base, unchanged=True)
        require(suite.cart["version"] == str(version), "Version string lost precision")
        if version == MAX_VERSION:
            await suite.check(
                "TC12-max-sync-refusal",
                "syncCart",
                base + "/sync",
                body=suite.operation(),
                expected=409,
                expected_code="VERSION_LIMIT",
                unchanged=True,
            )
        elif version == MAX_VERSION - 1:
            await suite.check(
                "TC12-purchase-needs-two",
                "purchase",
                "/api/purchases",
                body=suite.operation(cart_id=suite.cart["cart_id"]),
                expected=409,
                expected_code="VERSION_LIMIT",
                unchanged=True,
            )
        else:
            await suite.check(
                "TC12-sync-precision-" + str(version),
                "syncCart",
                base + "/sync",
                body=suite.operation(),
            )
            require(suite.cart["version"] == str(version + 1), "Sync precision lost")


@contextmanager
def expired_auth():
    """Local dedicated expiry setup; preserve/restore dates, never record token hashes."""
    with connect() as c, c.cursor() as q:
        q.execute(
            "SELECT s.token_hash,s.created_at,s.expires_at FROM AUTH_SESSION s JOIN REGISTER r "
            "ON r.active_session_hash=s.token_hash WHERE r.register_id=1"
        )
        old = q.fetchone()
        require(old is not None, "Active dedicated auth session missing")
        q.execute(
            "UPDATE AUTH_SESSION s JOIN REGISTER r ON r.active_session_hash=s.token_hash "
            "SET s.created_at=UTC_TIMESTAMP(6)-INTERVAL 2 HOUR, "
            "s.expires_at=UTC_TIMESTAMP(6)-INTERVAL 1 SECOND WHERE r.register_id=1"
        )
        c.commit()
    try:
        yield
    finally:
        with connect() as c, c.cursor() as q:
            q.execute(
                "UPDATE AUTH_SESSION SET created_at=%s,expires_at=%s WHERE token_hash=%s",
                (old["created_at"], old["expires_at"], old["token_hash"]),
            )
            require(q.rowcount == 1, "Expiry cleanup failed; stop")
            c.commit()


async def planned_tc11():
    """Enumerate finite selected matrix without importing DB/app or reading secrets."""

    class Planner(Suite):
        def __init__(self):
            super().__init__(SimpleNamespace(state=SimpleNamespace(engine=object())))
            self.ids = []

        async def check(self, case_id, op, path, **kwargs):
            require(case_id not in self.ids, "Duplicate planned identity")
            self.ids.append(case_id)
            return {}

    planner = Planner()
    cart = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    line = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    operation = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    normal_body = {"operation_id": operation, "version": "7"}
    for op, _, template in OPS:
        planner.cookies = {"__Host-pos_session": "offline-shape"}
        if op not in ("login", "authStatus", "registerStart", "registerStatus"):
            planner.cookies["__Host-pos_resume"] = "offline-shape"
        path = template.replace("{line_id}", line).replace("{operation_id}", operation)
        path = path.replace("{code}", "P103").replace("{id}", MEMBER if op == "member" else cart)
        body = None
        query = ""
        if op in ("login", "reauth"):
            body = {"staff_id": STAFF, "password": "offline-placeholder"}
        elif SPEC["paths"][template][next(m.lower() for o, m, _ in OPS if o == op)].get(
            "requestBody"
        ):
            body = dict(normal_body)
            if op == "addLine":
                body["code"] = "P103"
            elif op == "setQuantity":
                body["quantity"] = 3
            elif op == "setMember":
                body["member_id"] = MEMBER
            elif op == "purchase":
                body["cart_id"] = cart
        if op == "deleteLine":
            query = urlencode(normal_body)
        with patch(__name__ + ".expired_auth", lambda: nullcontext()):
            await planner.matrix(op, path, body, query)
        planner.ids.append("TC11-" + op + "-normal")
    planner.ids += ["TC11-setMember-null-normal", "TC11-reauth-other-staff", "TC11-purchase-saved"]
    require(len(planner.ids) == len(set(planner.ids)), "Planned duplicates")
    return planner.ids


def compare_business(before, after):
    old = EVIDENCE["snapshots"][before["projection_sha256"]]["data"]
    new = EVIDENCE["snapshots"][after["projection_sha256"]]["data"]
    require(
        all(old[t] == new[t] for t in old if t != "CART_OPERATION"),
        "Business rejection changed state",
    )
    require(len(new["CART_OPERATION"]) == len(old["CART_OPERATION"]) + 1, "Rejection op count")
    added = [r for r in new["CART_OPERATION"] if r not in old["CART_OPERATION"]]
    require(
        len(added) == 1
        and added[0]["status"] == "REJECTED"
        and added[0]["applied_version"] is None,
        "Rejected result not recorded once",
    )


def constraints(cart, line):
    import pymysql

    baseline = snapshot()
    mutations = (
        (
            "register-second",
            "INSERT INTO REGISTER(register_id,start_state) VALUES(2,'UNSTARTED')",
            (),
            {3819},
        ),
        (
            "duplicate-product-code",
            "INSERT INTO PRODUCT(code,name,unit_price,tax_rate_id) "
            "SELECT code,name,unit_price,tax_rate_id FROM PRODUCT WHERE code='P103'",
            (),
            {1062},
        ),
        (
            "product-parent-missing",
            "UPDATE PRODUCT SET tax_rate_id=4294967295 WHERE code='P103'",
            (),
            {1452},
        ),
        (
            "member-required-null",
            "UPDATE MEMBER SET name=NULL WHERE member_id=%s",
            (MEMBER,),
            {1048},
        ),
        ("member-empty", "UPDATE MEMBER SET name='' WHERE member_id=%s", (MEMBER,), {3819}),
        (
            "line-quantity0",
            "UPDATE CART_LINE SET quantity=0 WHERE cart_id=%s AND line_id=%s",
            (cart, line),
            {3819},
        ),
        (
            "candidate-json-object",
            "UPDATE CART_LINE SET discount_candidates=JSON_OBJECT() "
            "WHERE cart_id=%s AND line_id=%s",
            (cart, line),
            {3819},
        ),
        (
            "line-money-inconsistent",
            "UPDATE CART_LINE SET line_subtotal=line_subtotal+1 WHERE cart_id=%s AND line_id=%s",
            (cart, line),
            {3819},
        ),
        ("cart-state-invalid", "UPDATE CART SET state='BROKEN' WHERE cart_id=%s", (cart,), {3819}),
    )
    for tag, sql, args, codes in mutations:
        code = None
        with connect() as c, c.cursor() as q:
            try:
                q.execute(sql, args)
            except pymysql.MySQLError as error:
                code = error.args[0]
                require(code in codes, "Unexpected DB constraint code")
            finally:
                c.rollback()
        require(code is not None, "Constraint accepted invalid input")
        after = snapshot()
        require(
            baseline["projection_sha256"] == after["projection_sha256"],
            "Rollback changed committed data",
        )
        EVIDENCE["cases"].append(
            {
                "id": "TC13-" + tag,
                "mysql_code": code,
                "before": baseline,
                "after": after,
                "unchanged": True,
            }
        )


def main():
    global STAGE, DB, USERS
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--run", action="store_true")
    group.add_argument("--replay-original", action="store_true")
    parser.add_argument("--retry", action="store_true", help="Explicit fresh fixed retry schema")
    args = parser.parse_args()
    if args.replay_original:
        require(not args.retry, "Replay does not select a DB schema")
        print(json.dumps(replay_original()))
        return 0
    if args.retry:
        DB = "pos_oct05_api_retry"
        USERS = {
            "root": "root",
            DB + "_app": "pos_app",
            DB + "_master": "pos_master",
            DB + "_schema": "pos_schema",
        }
        EVIDENCE["schema"] = DB
        EVIDENCE["explicit_fresh_validation_retry"] = True
        EVIDENCE["original_schema_untouched"] = "pos_oct05_api"
    operations = {
        v["operationId"]
        for p in SPEC["paths"].values()
        for m, v in p.items()
        if m in ("get", "post", "put", "patch", "delete")
    }
    require(
        operations == {op for op, _, _ in OPS} and len(operations) == 22,
        "22-operation contract drift",
    )
    plan = asyncio.run(planned_tc11())
    EVIDENCE["planned_tc11_ids"] = plan
    if not args.prepare and not args.run:
        print(
            json.dumps(
                {
                    "offline": True,
                    "operations": len(OPS),
                    "schema": DB,
                    "profile": PROFILE,
                    "db_port": PORT,
                    "normal_planned": 22,
                    "selected_tc11_case_count": len(plan),
                }
            )
        )
        return 0
    require(os.environ.get("M2_LOCAL_PROFILE") == PROFILE, "Fixed profile required")
    action = "prepare" if args.prepare else "run"
    output = OUT / ("api-" + action + ("-retry" if args.retry else "") + ".json")
    require(not output.exists(), "Evidence exists; no automatic rerun/overwrite")
    guard()
    sys.path.insert(0, str(ROOT / "backend"))
    logging.disable(logging.CRITICAL)
    OUT.mkdir(parents=True, exist_ok=True)
    with output.open("x") as handle:
        handle.write("{}\n")
    try:
        STAGE = action
        if args.prepare:
            EVIDENCE["prepare"] = prepare()
            EVIDENCE["completed"] = True
        else:
            asyncio.run(run())
        EVIDENCE["status"] = "limited_cases_passed"
    except Exception as error:  # noqa: BLE001 - only sanitized facts, never SQL/password repr
        EVIDENCE["status"] = "stopped"
        EVIDENCE["error"] = {
            "type": type(error).__name__,
            "line": traceback.extract_tb(error.__traceback__)[-1].lineno,
            "mysql_code": error.args[0] if error.args and type(error.args[0]) is int else None,
        }
        # DDL is not transactional. Preserve partial object counts, never auto-DROP/reset/retry.
        if args.prepare:
            try:
                with connect() as c, c.cursor() as q:
                    q.execute(
                        "SELECT COUNT(*) n FROM information_schema.tables WHERE table_schema=%s",
                        (DB,),
                    )
                    EVIDENCE["partial_schema_table_count"] = q.fetchone()["n"]
            except Exception:  # noqa: BLE001 - a failed observer remains explicitly unobserved
                EVIDENCE["partial_schema_table_count"] = None
    ids = [c["id"] for c in EVIDENCE["cases"]]
    require(len(ids) == len(set(ids)), "Duplicate atomic case IDs")
    EVIDENCE["remaining_tc11_ids"] = sorted(set(plan) - set(ids))
    EVIDENCE["selected_tc11_passed"] = len(set(plan) & set(ids))
    if args.run and EVIDENCE["completed"]:
        require(
            not EVIDENCE["remaining_tc11_ids"], "Completed suite has missing selected TC11 cases"
        )
    EVIDENCE.update(
        last_stage=STAGE,
        completed_case_count=len(ids),
        at_utc=datetime.now(UTC).isoformat(),
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    )
    output.write_text(json.dumps(EVIDENCE, default=encode, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": EVIDENCE["status"], "case_count": len(ids), "stage": STAGE}))
    return 0 if EVIDENCE["completed"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # noqa: BLE001 - preflight remains sanitized
        print(json.dumps({"stopped_before_execution": True, "error_type": type(error).__name__}))
        raise SystemExit(1) from None
