"""M4 real-MySQL fault and race tests. Default is offline; requires a fresh m4 profile."""

import argparse
import asyncio
import concurrent.futures
import json
import os
import sys
import threading
import time
from contextlib import contextmanager
from unittest.mock import patch
from uuid import uuid4

import pymysql
from m2_local_db import configure, connect, secrets
from m2_local_profile import EVIDENCE, LOCAL, PROFILE, ROOT
from m2_verify_https import Client
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

sys.path.insert(0, str(ROOT / "backend"))
from app.infrastructure.database import transaction  # noqa: E402
from app.infrastructure.settings import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.repositories.business import BusinessRepository  # noqa: E402
from app.services.business import BusinessService  # noqa: E402


async def asgi(app, client, method, path, body=None):
    """Use actual FastAPI middleware and real DB. No test repository or response substitution."""
    sent = []
    delivered = False

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": json.dumps(body).encode() if body else b""}
        await asyncio.Future()

    async def send(value):
        sent.append(value)

    headers = {
        "origin": "https://localhost:8443",
        "x-pos-request": "1",
        "x-pos-relay": secrets()["relay"],
        "content-type": "application/json",
        "cookie": "; ".join(f"{k}={v}" for k, v in client.cookies.items()),
    }
    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1",
            "method": method,
            "scheme": "https",
            "path": "/api/" + path,
            "raw_path": ("/api/" + path).encode(),
            "query_string": b"",
            "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
            "server": ("localhost", 8444),
            "client": ("127.0.0.1", 12345),
            "root_path": "",
        },
        receive,
        send,
    )
    status = next(value["status"] for value in sent if value["type"] == "http.response.start")
    value = json.loads(b"".join(value.get("body", b"") for value in sent))
    Client.validate(
        value, "Error" if status >= 400 else "CartResult" if method == "GET" else "OperationResult"
    )
    return status, value


def snapshot(cart_id):
    """Always observe through a fresh connection; never disclose secrets or customer attributes."""
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT CONNECTION_ID()")
            connection_id = cursor.fetchone()[0]
            cursor.execute(
                "SELECT state,version,member_state FROM CART WHERE cart_id=%s", (cart_id,)
            )
            state, version, member = cursor.fetchone()
            counts = {}
            for table in ("PURCHASE", "PURCHASE_LINE", "PURCHASE_TAX"):
                cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE cart_id=%s", (cart_id,))
                counts[table] = cursor.fetchone()[0]
            cursor.execute(
                "SELECT kind,status FROM CART_OPERATION WHERE cart_id=%s "
                "ORDER BY created_at,operation_id",
                (cart_id,),
            )
            operations = [list(row) for row in cursor.fetchall()]
        connection.rollback()
    return {
        "connection_id": connection_id,
        "state": state,
        "version": str(version),
        "member_state": member,
        "counts": counts,
        "operations": operations,
    }


@contextmanager
def fault(engine, cart_id, *, commit=None, after_sql=None, unread=False, member_pending=False):
    """Local injector: send COMMIT, independently observe it, drop connection before ACK read."""
    evidence = {"commits_sent": 0, "sale_insertions": 0, "invalidated": 0, "injected": False}
    wrapped = []

    def checkout(dbapi, record, proxy):
        if any(dbapi is row[0] for row in wrapped):
            return
        execute, read = dbapi._execute_command, dbapi._read_ok_packet
        wrapped.append((dbapi, execute, read))
        pending = False

        def command(kind, sql):
            nonlocal pending
            pending = kind == 3 and sql in ("COMMIT", b"COMMIT")
            if pending:
                evidence["commits_sent"] += 1
            return execute(kind, sql)

        def read_ok():
            nonlocal pending
            lose = pending and commit == evidence["commits_sent"] and not evidence["injected"]
            pending = False
            if not lose:
                return read()
            # COMMIT is on the wire. Do not read or manufacture its success result.
            deadline = time.monotonic() + 3
            while True:
                observed = snapshot(cart_id)
                target = "EDITING" if member_pending else "SAVING" if commit == 1 else "SAVED"
                if observed["state"] == target and (
                    not member_pending or observed["member_state"] == "PENDING"
                ):
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError("COMMIT observation timed out")
                time.sleep(0.02)
            assert observed["connection_id"] != dbapi.thread_id()
            evidence.update(
                injected=True,
                writer_connection_id=dbapi.thread_id(),
                observer=observed,
                ack_read=False,
            )
            # Physically drop the socket, leaving normal driver close idempotent for invalidation.
            dbapi._force_close()
            raise pymysql.err.OperationalError(2013, "M4 injected unread COMMIT acknowledgement")

        dbapi._execute_command, dbapi._read_ok_packet = command, read_ok

    def executed(connection, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO PURCHASE("):
            evidence["sale_insertions"] += 1
        if after_sql and statement.startswith(after_sql) and not evidence["injected"]:
            evidence["injected"] = True
            raise OperationalError(
                None, None, pymysql.err.OperationalError(2013, "M4 mid-write fault")
            )

    def invalidated(dbapi, record, error):
        evidence["invalidated"] += 1

    def blocked(connection, cursor, statement, parameters, context, many):
        raise OperationalError(
            None, None, pymysql.err.OperationalError(2013, "M4 lookup unavailable")
        )

    event.listen(engine, "checkout", checkout)
    event.listen(engine, "after_cursor_execute", executed)
    event.listen(engine, "invalidate", invalidated)
    if unread:
        event.listen(engine, "before_cursor_execute", blocked)
    try:
        yield evidence
    finally:
        event.remove(engine, "checkout", checkout)
        event.remove(engine, "after_cursor_execute", executed)
        event.remove(engine, "invalidate", invalidated)
        if unread:
            event.remove(engine, "before_cursor_execute", blocked)
        for dbapi, execute, read in wrapped:
            dbapi._execute_command, dbapi._read_ok_packet = execute, read


class Suite:
    def __init__(self):
        self.client = Client()
        self.results = []
        self.cart = None
        self.stage = "initial"
        self.started = False

    def ok(self, name, **details):
        self.results.append({"check": name, "passed": True, **details})
        self.save()

    def save(self):
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        (EVIDENCE / "fault-races.json").write_text(
            json.dumps(
                {"results": self.results, "last_stage": self.stage, "browser_test": False},
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
        if self.client.cookies:
            # Dedicated harness credentials only, never returned in evidence or logs.
            target = LOCAL / "client-cookies.json"
            target.write_text(json.dumps(self.client.cookies))
            target.chmod(0o600)

    def request(self, method, path, body=None, status=200):
        actual, value, _ = self.client.request(method, path, body)
        assert actual == status, (self.stage, actual, value.get("code"))
        if actual < 400:
            schema = (
                "OperationResult"
                if "/operations/" in path
                else "NextResult"
                if path.endswith("/next")
                else "CartResult"
                if method == "GET" or path == "carts"
                else "Register"
                if path.startswith("register/")
                else "OperationResult"
            )
            self.client.validate(value, schema)
            if "cart" in value:
                self.cart = value["cart"]
        return value

    def operation(self, **extra):
        return {"operation_id": str(uuid4()), "version": self.cart["version"], **extra}

    def prepare(self):
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT start_state,current_cart_id FROM REGISTER "
                    "WHERE register_id=1 FOR UPDATE"
                )
                assert cursor.fetchone() == ("UNSTARTED", None)
                cursor.execute("SELECT COUNT(*) FROM CART")
                assert cursor.fetchone() == (0,)
                self.started = True
                cursor.execute("UPDATE PRODUCT SET tax_rate_id=2 WHERE product_id=1")
                cursor.execute("UPDATE PRODUCT SET unit_price=107,tax_rate_id=1 WHERE product_id=2")
                cursor.execute(
                    "INSERT INTO PRICE_HISTORY(product_id,old_price,new_price,changed_at) "
                    "VALUES(2,210,107,UTC_TIMESTAMP(6))"
                )
                cursor.execute(
                    "INSERT INTO PRODUCT(product_id,code,name,unit_price,tax_rate_id) "
                    "VALUES(3,'0003','M4食品107円',107,1)"
                )
                cursor.execute(
                    "INSERT INTO PRICE_HISTORY(product_id,old_price,new_price,changed_at) "
                    "VALUES(3,NULL,107,UTC_TIMESTAMP(6))"
                )
            connection.commit()
        assert self.client.login()[0] == 200
        self.request("POST", "register/start")
        self.request("POST", "register/confirm")
        self.request("POST", "carts")

    def fill(self):
        self.stage = "fill"
        for code in ("0001", "0002", "0003"):
            self.request("POST", f"carts/{self.cart['cart_id']}/lines", self.operation(code=code))
        self.request(
            "PUT", f"carts/{self.cart['cart_id']}/member", self.operation(member_id="MEMBER_0")
        )
        line = self.cart["lines"][0]["line_id"]
        self.request(
            "PATCH", f"carts/{self.cart['cart_id']}/lines/{line}", self.operation(quantity=3)
        )
        assert self.cart["total"] == "537"

    def buy(self, body=None, status=200):
        return self.request(
            "POST", "purchases", body or self.operation(cart_id=self.cart["cart_id"]), status
        )

    def next(self):
        self.request("POST", f"carts/{self.cart['cart_id']}/next", self.operation())

    def fence(self, body=None):
        return self.request(
            "POST", f"carts/{self.cart['cart_id']}/resolve-purchase", body or self.operation()
        )

    def https_cases(self):
        self.stage = "HTTPS update response discarded and sync ordering"
        cart_id = self.cart["cart_id"]
        body = self.operation(code="0001")
        self.client.request(
            "POST", f"carts/{cart_id}/lines", body
        )  # Deliberately ignore the response.
        repeated = self.request("POST", f"carts/{cart_id}/lines", body)
        assert repeated["cart"]["lines"][0]["quantity"] == 1
        delayed = self.operation(code="0002")
        self.request("POST", f"carts/{cart_id}/sync", self.operation())
        self.request("POST", f"carts/{cart_id}/lines", delayed, 409)
        self.ok(
            "TC19 response-discard same-request replay and sync-before-update fence",
            transport="HTTPS",
        )

        self.stage = "HTTPS two simultaneous quantity updates"
        line = self.cart["lines"][0]["line_id"]
        bodies = [self.operation(quantity=q) for q in (2, 3)]
        barrier = threading.Barrier(2)

        def update(body):
            client = Client(self.client.cookies)
            barrier.wait(timeout=5)
            return client.request("PATCH", f"carts/{cart_id}/lines/{line}", body)[:2]

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(update, bodies))
        assert sorted(r[0] for r in results) == [200, 409]
        current = self.request("GET", f"carts/{cart_id}")
        winner = next(value for code, value in results if code == 200)
        assert current["cart"] == winner["cart"]
        self.ok("TC18 same-version updates have one winner without overwrite", transport="HTTPS")

        self.stage = "HTTPS two simultaneous purchases"
        bodies = [self.operation(cart_id=cart_id) for _ in range(2)]
        barrier = threading.Barrier(2)

        def purchase(body):
            client = Client(self.client.cookies)
            barrier.wait(timeout=5)
            return client.request("POST", "purchases", body)[:2]

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(purchase, bodies))
        assert any(code == 200 for code, _ in results)
        assert all(code in (200, 409) for code, _ in results)
        self.request("GET", f"carts/{cart_id}")
        observed = snapshot(cart_id)
        assert observed["counts"]["PURCHASE"] == 1
        self.ok("TC18 concurrent purchases persist one sale", transport="HTTPS", observer=observed)

        self.stage = "HTTPS next response discarded"
        body = self.operation()
        self.client.request("POST", f"carts/{cart_id}/next", body)
        replay = self.request("POST", f"carts/{cart_id}/next", body)
        op = self.request("GET", f"carts/{cart_id}/operations/{body['operation_id']}")
        assert op["cart"]["cart_id"] == cart_id and op["cart"]["state"] == "CLOSED"
        resumed = self.request("GET", "resume")
        assert resumed["cart"]["cart_id"] == replay["new_cart_id"] == op["new_cart_id"]
        self.ok(
            "TC24 next-response discard converges through replay, operation GET and resume",
            transport="HTTPS",
        )

    async def fault_cases(self, app):
        for name, options in (
            ("receipt COMMIT ACK unread", {"commit": 1}),
            ("sale COMMIT ACK unread", {"commit": 2}),
            ("after sale lines SQL", {"after_sql": "INSERT INTO PURCHASE_LINE("}),
            ("after first sale tax SQL", {"after_sql": "INSERT INTO PURCHASE_TAX("}),
        ):
            self.fill()
            self.stage = name
            cart_id = self.cart["cart_id"]
            body = self.operation(cart_id=cart_id)
            with fault(app.state.engine, cart_id, **options) as injection:
                status, value = await asgi(app, self.client, "POST", "purchases", body)
            assert status == 503 and injection["injected"]
            if "commit" in options:
                assert injection["invalidated"] >= 1
                assert injection["commits_sent"] == options["commit"]
            observed = snapshot(cart_id)
            expected_sale = 1 if options.get("commit") == 2 else 0
            assert observed["counts"] == {
                "PURCHASE": expected_sale,
                "PURCHASE_LINE": 3 * expected_sale,
                "PURCHASE_TAX": 2 * expected_sale,
            }
            assert observed["state"] == ("SAVED" if expected_sale else "SAVING")
            assert ["PURCHASE", "APPLIED" if expected_sale else "PREPARED"] in observed[
                "operations"
            ]
            assert injection["sale_insertions"] == (0 if options.get("commit") == 1 else 1)
            known = self.request("GET", f"carts/{cart_id}/purchase")
            assert known["purchase_status"] == ("SAVED" if expected_sale else "UNKNOWN")
            with fault(app.state.engine, cart_id, unread=True) as unavailable:
                assert (await asgi(app, self.client, "GET", f"carts/{cart_id}/purchase"))[0] == 503
            assert unavailable["sale_insertions"] == 0
            assert snapshot(cart_id)["counts"] == observed["counts"]
            saved = self.buy(body)
            assert saved["purchase"]["total"] == "537"
            assert saved == self.buy(body)
            assert snapshot(cart_id)["counts"] == {
                "PURCHASE": 1,
                "PURCHASE_LINE": 3,
                "PURCHASE_TAX": 2,
            }
            self.ok(
                "TC16 " + name, transport="ASGI+real MySQL", injection=injection, observed=observed
            )
            self.next()

    def fence_cases(self):
        self.fill()
        self.stage = "resolve-before-delayed-purchase and re-resolve UNSAVED"
        delayed = self.operation(cart_id=self.cart["cart_id"])
        result = self.fence()
        assert result["purchase_status"] == "UNSAVED"
        self.buy(delayed, 409)
        retry = self.operation(cart_id=self.cart["cart_id"])
        confirmation = self.operation()
        result = self.fence(confirmation)
        assert result == self.fence(confirmation)
        self.buy(retry, 409)
        assert snapshot(self.cart["cart_id"])["counts"]["PURCHASE"] == 0
        before = self.cart
        self.request("POST", f"carts/{self.cart['cart_id']}/reopen", self.operation())
        assert (
            self.cart["lines"] == before["lines"] and self.cart["member_id"] == before["member_id"]
        )
        line = self.cart["lines"][0]["line_id"]
        self.request(
            "PATCH", f"carts/{self.cart['cart_id']}/lines/{line}", self.operation(quantity=2)
        )
        saved = self.buy()
        assert saved["purchase"]["total"] == "435"
        late = self.fence({"operation_id": str(uuid4()), "version": "1"})
        assert late["purchase"] == saved["purchase"]
        self.request("POST", f"carts/{self.cart['cart_id']}/reopen", self.operation(), 409)
        self.ok(
            "TC17 resolve-first fences delayed purchase/retry; "
            "reopen keeps conditions; saved-first wins"
        )
        self.next()

    async def pending_case(self, app, missing=False):
        self.fill()
        self.stage = "member rejected pending" if missing else "member prepared pending"
        cart_id = self.cart["cart_id"]
        delayed = self.operation(cart_id=cart_id)
        body = self.operation(member_id="MISSING" if missing else "MEMBER_0")
        if missing:
            self.request("PUT", f"carts/{cart_id}/member", body, 404)
        else:
            # Commit member PREPARED but deny receipt success to the application.
            with fault(app.state.engine, cart_id, commit=1, member_pending=True) as injection:
                assert (await asgi(app, self.client, "PUT", f"carts/{cart_id}/member", body))[
                    0
                ] == 503
            assert injection["injected"]
        pending = self.request("GET", f"carts/{cart_id}")
        assert pending["cart"]["member_state"] == "PENDING"
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT b.last_business_at FROM BROWSER_CONTEXT b "
                    "JOIN CART c ON c.context_id=b.context_id WHERE c.cart_id=%s",
                    (cart_id,),
                )
                timestamp = cursor.fetchone()[0]
                cursor.execute(
                    "SELECT status,result_code,completed_at FROM CART_OPERATION "
                    "WHERE cart_id=%s AND operation_id=%s",
                    (cart_id, body["operation_id"]),
                )
                old_operation = cursor.fetchone()
            connection.rollback()
        confirmation = self.operation()
        status, result, cookies = self.client.request(
            "POST", f"carts/{cart_id}/resolve-purchase", confirmation
        )
        assert status == 200 and not cookies
        assert result["code"] == "PURCHASE_FENCED_MEMBER_PENDING"
        assert result["cart"]["version"] == str(int(pending["cart"]["version"]) + 1)
        assert result["applied_version"] == result["cart"]["version"]
        assert result["purchase_status"] == "NOT_REQUESTED" and result["purchase"] is None
        assert result["cart"]["total"] == pending["cart"]["total"]
        assert result["cart"]["member_state"] == "PENDING"
        self.cart = result["cart"]
        assert result == self.fence(confirmation)
        self.buy(delayed, 409)
        self.request("POST", f"carts/{cart_id}/lines", self.operation(code="0001"), 409)
        self.request("PUT", f"carts/{cart_id}/member", body, 404 if missing else 409)
        # Finish the original member phase explicitly to prove no delayed success can overwrite.
        with transaction(app.state.engine) as connection:
            service = BusinessService(BusinessRepository(connection), app.state.passwords)
            late = service.finish_member(
                self.client.cookies["__Host-pos_session"],
                self.client.cookies["__Host-pos_resume"],
                cart_id,
                body["operation_id"],
                {k: v for k, v in body.items() if k != "operation_id"},
                True,
            )
            assert (
                late.body["operation_status"] == "REJECTED"
                and late.body["cart"]["member_state"] == "PENDING"
            )
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT b.last_business_at FROM BROWSER_CONTEXT b "
                    "JOIN CART c ON c.context_id=b.context_id WHERE c.cart_id=%s",
                    (cart_id,),
                )
                assert cursor.fetchone()[0] == timestamp
                cursor.execute(
                    "SELECT active_member_operation_id FROM CART WHERE cart_id=%s", (cart_id,)
                )
                assert cursor.fetchone()[0] == body["operation_id"]
                cursor.execute(
                    "SELECT status,result_code,completed_at FROM CART_OPERATION "
                    "WHERE cart_id=%s AND operation_id=%s",
                    (cart_id, body["operation_id"]),
                )
                final_operation = cursor.fetchone()
                if missing:
                    assert final_operation == old_operation
                else:
                    assert final_operation[0:2] == ("REJECTED", "MEMBER_LOOKUP_SUPERSEDED")
            connection.rollback()
        self.request("PUT", f"carts/{cart_id}/member", self.operation(member_id=None))
        self.buy()
        self.ok(
            "TC18/20 pending member fence preserves reference, expiry and rejected history",
            missing_member=missing,
            pending_version=pending["cart"]["version"],
            fence_version=result["applied_version"],
            operation_preserved=missing,
        )
        self.next()

    def lock_case(self):
        self.fill()
        self.stage = "resolve lock timeout"
        cart_id = self.cart["cart_id"]
        before = snapshot(cart_id)
        body = self.operation()
        with connect() as blocker:
            with blocker.cursor() as cursor:
                cursor.execute("SELECT register_id FROM REGISTER WHERE register_id=1 FOR UPDATE")
                self.request("POST", f"carts/{cart_id}/resolve-purchase", body, 503)
                blocked = snapshot(cart_id)
                for key in ("operations", "counts", "state", "version"):
                    assert blocked[key] == before[key]
            blocker.rollback()
        self.fence(body)
        self.buy()
        self.ok(
            "TC17 real MySQL lock timeout leaves confirmation unapplied, same retry succeeds",
            before=before,
            blocked=blocked,
        )
        self.next()

    async def read_consistency(self, app):
        self.fill()
        self.stage = "read snapshot across committed update"
        cart_id = self.cart["cart_id"]
        before = self.request("GET", f"carts/{cart_id}")
        entered, release = threading.Event(), threading.Event()
        original = BusinessRepository.lines

        def paused(repo, identifier):
            if identifier == cart_id:
                entered.set()
                assert release.wait(5)
            return original(repo, identifier)

        with patch.object(BusinessRepository, "lines", paused):
            task = asyncio.create_task(asgi(app, self.client, "GET", f"carts/{cart_id}"))
            assert await asyncio.to_thread(entered.wait, 5)
            try:
                # A different process/connection performs a normal API update after cart SELECT.
                line = self.cart["lines"][0]["line_id"]
                await asyncio.to_thread(
                    self.request,
                    "PATCH",
                    f"carts/{cart_id}/lines/{line}",
                    self.operation(quantity=2),
                )
            finally:
                release.set()
            status, old = await task
        assert status == 200 and old == before
        after = self.request("GET", f"carts/{cart_id}")
        assert (
            after["cart"]["total"] == "435"
            and after["cart"]["version"] != before["cart"]["version"]
        )
        self.ok(
            "TC12 actual API read snapshot remains coherent across separate committed write",
            transport="ASGI read+HTTPS write",
            old_version=old["cart"]["version"],
            old_total=old["cart"]["total"],
            new_version=after["cart"]["version"],
            new_total=after["cart"]["total"],
            order=["read cart SELECT", "HTTPS quantity update COMMIT", "release read lines SELECT"],
        )
        self.buy()
        self.next()

    async def prepared_fence(self, app):
        self.fill()
        self.stage = "prepared purchase fenced before delayed save"
        cart_id = self.cart["cart_id"]
        purchase = self.operation(cart_id=cart_id)
        with fault(app.state.engine, cart_id, commit=1) as injection:
            assert (await asgi(app, self.client, "POST", "purchases", purchase))[0] == 503
        assert injection["injected"] and injection["invalidated"] >= 1
        self.request("GET", f"carts/{cart_id}")
        assert self.cart["state"] == "SAVING"
        confirmation = self.operation()
        resolved = self.fence(confirmation)
        assert resolved == self.fence(confirmation) and resolved["purchase_status"] == "UNSAVED"
        known = self.request("GET", f"carts/{cart_id}/operations/{purchase['operation_id']}")
        assert (
            known["operation_status"] == "REJECTED" and known["code"] == "PURCHASE_ATTEMPT_CLOSED"
        )
        self.buy(purchase, 409)
        assert snapshot(cart_id)["counts"]["PURCHASE"] == 0
        self.request("POST", f"carts/{cart_id}/reopen", self.operation())
        saved = self.buy()
        assert saved["purchase"]["total"] == "537"
        self.ok(
            "TC17 receipt-committed purchase fence rejects delayed save before reopen/new purchase",
            injection=injection,
        )
        self.next()


async def run(suite, *, supplement=False):
    if supplement:
        previous = json.loads((EVIDENCE / "fault-races.json").read_text())
        if previous["last_stage"] != "complete":
            raise ValueError("Do not resume an incomplete fault run")
        suite.results = previous["results"]
        suite.client = Client(json.loads((LOCAL / "client-cookies.json").read_text()))
        suite.request("GET", "resume")
        if suite.cart["state"] != "EDITING" or suite.cart["lines"]:
            raise ValueError("Supplement requires the empty next cart of a completed suite")
        suite.started = True
    else:
        suite.prepare()
        suite.https_cases()
    configure("pos_app")
    app = create_app(Settings.from_env())
    async with app.router.lifespan_context(app):
        if not supplement:
            await suite.fault_cases(app)
            suite.fence_cases()
        await suite.pending_case(app)
        await suite.pending_case(app, missing=True)
        await suite.prepared_fence(app)
        if not supplement:
            suite.lock_case()
            await suite.read_consistency(app)
    suite.stage = "complete"
    suite.save()
    print(json.dumps({"passed": len(suite.results), "browser_test": False}))


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument(
        "--supplement",
        action="store_true",
        help="Additional checks after a fully completed run only",
    )
    args = parser.parse_args()
    if not args.run:
        print(
            json.dumps(
                {
                    "offline_only": True,
                    "profile": "m4",
                    "checks": [
                        "concurrent writes/purchases",
                        "sync and next response discard",
                        "receipt/sale COMMIT unread ACK",
                        "mid-lines/tax rollback",
                        "resolve/reopen/delayed requests",
                        "member pending",
                        "lock timeout",
                        "read consistency",
                    ],
                }
            )
        )
        return
    if PROFILE != "m4":
        raise ValueError("Requires fresh m4-only profile")
    if not args.supplement and (EVIDENCE / "fault-races.json").exists():
        print('{"stopped":true,"reason":"EXISTING_EVIDENCE_PRESERVED"}')
        sys.exit(1)
    suite = Suite()
    try:
        asyncio.run(run(suite, supplement=args.supplement))
    except Exception as error:
        if suite.started:
            suite.save()
        print(json.dumps({"stopped": True, "stage": suite.stage, "type": type(error).__name__}))
        sys.exit(1)


if __name__ == "__main__":
    main()
