"""Live HTTPS integration checks. Cookie/password values stay in process memory only."""

import argparse
import concurrent.futures
import hashlib
import http.client
import json
import re
import secrets as random
import ssl

from jsonschema import Draft202012Validator
from m2_local_db import LOCAL, ROOT, connect, secrets
from referencing import Registry, Resource

ORIGIN = "https://localhost:8443"
SPEC = json.loads((ROOT / "API契約.openapi.json").read_text())
SPEC["$schema"] = "https://json-schema.org/draft/2020-12/schema"
REGISTRY = Registry().with_resource("urn:pos", Resource.from_contents(SPEC))


class Client:
    def __init__(self, cookies=None):
        self.cookies = dict(cookies or {})

    def request(
        self,
        method,
        path,
        body=None,
        *,
        header_changes=None,
        port=8443,
        raw=None,
        discard_cookies=False,
    ):
        headers = {
            "Origin": ORIGIN,
            "X-POS-Request": "1",
            "Content-Type": "application/json",
            "Cookie": "; ".join(f"{k}={v}" for k, v in self.cookies.items()),
        }
        for key, value in (header_changes or {}).items():
            if value is None:
                headers.pop(key, None)
            else:
                headers[key] = value
        payload = raw if raw is not None else (None if body is None else json.dumps(body))
        context = ssl.create_default_context(cafile=str(LOCAL / "tls/ca.crt"))
        connection = http.client.HTTPSConnection("localhost", port, context=context, timeout=15)
        try:
            connection.request(method, "/api/" + path, body=payload, headers=headers)
            response = connection.getresponse()
            data = json.loads(response.read())
            all_headers = response.getheaders()
            assert response.getheader("Cache-Control") == "no-store"
            values = [v for k, v in all_headers if k.lower() == "set-cookie"]
            for value in values:
                assert all(
                    marker in value.lower()
                    for marker in ["secure", "httponly", "samesite=lax", "path=/"]
                )
                assert "domain=" not in value.lower()
                name, token = value.split(";", 1)[0].split("=", 1)
                assert re.fullmatch(r"[A-Za-z0-9_-]{43}", token)
                if not discard_cookies:
                    self.cookies[name] = token
            if response.status >= 400:
                self.validate(data, "Error")
            return response.status, data, values
        finally:
            connection.close()

    @staticmethod
    def validate(data, schema):
        Draft202012Validator(
            {"$ref": f"urn:pos#/components/schemas/{schema}"}, registry=REGISTRY
        ).validate(data)

    def login(self, staff="STAFF_A", path="login", password=None):
        return self.request(
            "POST",
            path,
            {
                "staff_id": staff,
                "password": secrets()[staff] if password is None else password,
            },
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["maintenance", "startup"])
    phase = parser.parse_args().phase
    results = []

    def ok(name, **fields):
        results.append({"check": name, "passed": True, **fields})
        print(json.dumps({"check": name, "passed": True}, ensure_ascii=False), flush=True)

    client = Client()
    for path in [
        "auth/status",
        "register/status",
        "products/0001",
        "members/MEMBER_0",
        "resume",
    ]:
        assert client.request("GET", path)[0] == 401
    ok("unauthenticated M2 reads rejected")
    for path in ["login", "reauth", "register/start", "register/confirm", "carts"]:
        for changes in [
            {"Origin": None},
            {"Origin": "null"},
            {"Origin": ORIGIN + "/"},
            {"X-POS-Request": None},
        ]:
            assert client.request("POST", path, header_changes=changes)[0] == 403
    ok("origin and custom header guards reject all M2 writes")
    assert client.request("GET", "auth/status", port=8444)[0] == 403
    ok("direct backend request without relay secret rejected")
    assert client.request("POST", "login", {"staff_id": "STAFF_A", "password": None})[0] == 422
    assert (
        client.request(
            "POST", "login", {"staff_id": "STAFF_A", "password": "unused", "price": "0"}
        )[0]
        == 422
    )
    ok("HTTP input validation excludes unknown fields and null password")
    status, body, headers = client.login()
    assert status == 200, (status, body.get("code"))
    client.validate(body, "Auth")
    assert (
        client.request(
            "GET", "auth/status", header_changes={"Origin": None, "X-POS-Request": None}
        )[0]
        == 200
    )
    ok("real HTTPS login and readonly auth status", staff_id=body["staff_id"])
    assert client.request("POST", "carts", {})[0] == 422
    if phase == "maintenance":
        state = client.request("GET", "register/status")
        assert state[0] == 200 and state[1]["maintenance_hold"] is True
        for path in ["register/start", "register/confirm"]:
            result = client.request("POST", path)
            assert result[0] == 409 and result[1]["code"] == "MAINTENANCE_HOLD"
        ok("maintenance allows authentication and status but rejects startup")
    else:
        assert client.request("GET", "register/status")[1]["start_state"] == "UNSTARTED"

        # Competing starts share one session, but use independent HTTP connections/jars.
        def start(_):
            local = Client(client.cookies)
            response = local.request("POST", "register/start")
            return response, local.cookies

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            starts = list(pool.map(start, range(2)))
        assert sorted(x[0][0] for x in starts) == [200, 409]
        client.cookies = next(jar for response, jar in starts if response[0] == 200)
        ok("simultaneous start creates exactly one context")
        state = client.request("GET", "register/status")
        client.validate(state[1], "Register")
        assert state[1]["start_state"] == "COOKIE_PENDING"
        assert client.request("POST", "carts")[0] == 409
        lost = Client({"__Host-pos_session": client.cookies["__Host-pos_session"]})
        assert lost.request("GET", "register/status")[0] == 403
        assert lost.request("POST", "register/confirm")[0] == 403
        ok("cookie loss before first cart stops without replacement")
        # Discard the confirm response to model its loss after server completion; GET resolves it.
        assert client.request("POST", "register/confirm", discard_cookies=True)[0] == 200
        assert client.request("GET", "register/status")[1]["start_state"] == "READY"
        assert not client.request("POST", "register/confirm")[2]
        assert client.request("GET", "resume")[0] == 404
        ok("confirm response loss resolved by readonly status and idempotent confirm")

        def create(_):
            return Client(client.cookies).request("POST", "carts")

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            carts = list(pool.map(create, range(2)))
        assert [x[0] for x in carts] == [200, 200]
        assert carts[0][1] == carts[1][1]
        cart = carts[0][1]
        client.validate(cart, "CartResult")
        assert client.request("GET", "resume")[1] == cart
        assert client.request("GET", f"carts/{cart['cart']['cart_id']}")[1] == cart
        assert not client.request("POST", "carts")[2]
        ok(
            "simultaneous cart creation and lost reply preserve one cart",
            cart_id=cart["cart"]["cart_id"],
        )
        cookie = client.cookies["__Host-pos_resume"]
        with connect() as conn, conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM BROWSER_CONTEXT")
            assert cursor.fetchone()[0] == 1
            cursor.execute("SELECT COUNT(*) FROM CART")
            assert cursor.fetchone()[0] == 1
            cursor.execute("SELECT token_hash,last_business_at FROM BROWSER_CONTEXT")
            hashed, business = cursor.fetchone()
            assert hashed == hashlib.sha256(cookie.encode()).digest()
        ok("real DB contains single context/cart and hashed resume token")
        assert Client().login()[0] == 403
        assert client.login("STAFF_B")[0] == 403
        assert client.request("GET", "resume")[1] == cart
        ok("missing resume cookie and other staff cannot replace active transaction")
        for path, schema in [
            ("products/0001", "Product"),
            ("members/MEMBER_0", "Member"),
        ]:
            result = client.request("GET", path)
            assert result[0] == 200
            client.validate(result[1], schema)
        assert client.request("GET", "products/MISSING")[0] == 404
        ok("authenticated product/member read and not-found distinction")
        old = Client(client.cookies)
        assert client.login(path="reauth")[0] == 200
        assert old.request("GET", "auth/status")[0] == 401
        assert client.request("GET", "resume")[1] == cart
        ok("reauthentication revokes old session and retains original cart")
        # Parallel failures for the same nonexistent ID must serialize into one shared limit.
        missing = "M2_LIMIT_" + random.token_hex(4)

        def bad(_):
            return Client(client.cookies).login(missing, password=random.token_urlsafe(16))[0]

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            statuses = list(pool.map(bad, range(5)))
        assert statuses == [401] * 5, statuses
        with connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT JSON_LENGTH(failure_times),locked_until FROM AUTH_LOGIN_LIMIT "
                    "WHERE staff_id=%s",
                    (missing,),
                )
                count, until = cursor.fetchone()
                assert count == 5 and until is not None
        assert client.login(missing, password="unused")[0] == 401
        with connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT JSON_LENGTH(failure_times),locked_until FROM AUTH_LOGIN_LIMIT "
                    "WHERE staff_id=%s",
                    (missing,),
                )
                assert cursor.fetchone() == (count, until)
        assert client.request("GET", "auth/status")[0] == 200
        ok("five concurrent failures persist and subsequent attempts do not extend lock")
        before = Client(client.cookies)
        # Keep credentials out of evidence while retaining the cookie from a discarded response.
        assert client.login(path="reauth")[0] == 200
        assert client.request("GET", "auth/status")[0] == 200
        assert before.request("GET", "auth/status")[0] == 401
        assert client.request("GET", "resume")[1] == cart
        with connect() as conn, conn.cursor() as cursor:
            cursor.execute("SELECT last_business_at FROM BROWSER_CONTEXT")
            assert cursor.fetchone()[0] == business
        ok("authentication response reconciliation and reads do not extend resume deadline")
    target = ROOT / f"docs/implementation/evidence/m2/https-{phase}.json"
    target.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"phase": phase, "passed": len(results), "failed": 0}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback

        print(
            json.dumps(
                {
                    "stopped": True,
                    "type": type(exc).__name__,
                    "line": traceback.extract_tb(exc.__traceback__)[-1].lineno,
                }
            )
        )
        raise SystemExit(1) from None
