"""M3-only live integration. Default validates the plan without connecting."""

import argparse
import json
import re
import sys
from uuid import uuid4

from m2_local_db import connect
from m2_local_profile import EVIDENCE, PROFILE, ROOT
from m2_verify_https import Client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if not args.run:
        print(
            json.dumps(
                {
                    "offline_only": True,
                    "profile": "m3",
                    "checks": [
                        "member/nonmember",
                        "snapshot retention",
                        "quantity/delete",
                        "306/537 totals",
                        "empty/zero",
                        "purchase/next idempotency",
                        "saved immutability",
                        "SQL integrity",
                    ],
                }
            )
        )
        return
    if PROFILE != "m3":
        raise ValueError("Requires the new M3-only profile")
    results = []

    def ok(name):
        results.append({"check": name, "passed": True})

    client = Client()

    def request(method, path, body=None, schema=None, status=200):
        response, value, _ = client.request(method, path, body)
        assert response == status, (path, response, value.get("code"))
        if schema:
            client.validate(value, schema)
        return value

    def operation(cart, **extra):
        return {"operation_id": str(uuid4()), "version": cart["version"], **extra}

    # Refuse any previously used register before changing fixture masters.
    with connect() as connection:
        with connection.cursor() as c:
            c.execute(
                "SELECT start_state,current_cart_id FROM REGISTER WHERE register_id=1 FOR UPDATE"
            )
            assert c.fetchone() == ("UNSTARTED", None)
            c.execute("SELECT COUNT(*) FROM CART")
            assert c.fetchone() == (0,)
            c.execute("UPDATE PRODUCT SET tax_rate_id=2 WHERE product_id=1")
            c.execute("UPDATE PRODUCT SET unit_price=107,tax_rate_id=1 WHERE product_id=2")
            c.execute(
                "INSERT INTO PRICE_HISTORY(product_id,old_price,new_price,changed_at) "
                "VALUES(2,210,107,UTC_TIMESTAMP(6))"
            )
            c.execute(
                "INSERT INTO PRODUCT(product_id,code,name,unit_price,tax_rate_id) "
                "VALUES(3,'0003','演習食品107円',107,1)"
            )
            c.execute(
                "INSERT INTO PRICE_HISTORY(product_id,old_price,new_price,changed_at) "
                "VALUES(3,NULL,107,UTC_TIMESTAMP(6))"
            )
        connection.commit()
    assert client.login()[0] == 200
    request("POST", "register/start", schema="Register")
    request("POST", "register/confirm", schema="Register")
    cart = request("POST", "carts", schema="CartResult")["cart"]
    request("POST", "purchases", operation(cart, cart_id=cart["cart_id"]), status=409)
    ok("empty cart rejected")
    added = operation(cart, code="0001")
    cart = request("POST", f"carts/{cart['cart_id']}/lines", added, "OperationResult")["cart"]
    duplicate = request("POST", f"carts/{cart['cart_id']}/lines", added, "OperationResult")["cart"]
    assert duplicate == cart and cart["lines"][0]["quantity"] == 1
    ok("add duplicate remains one unit")
    line = cart["lines"][0]["line_id"]
    cart = request(
        "PATCH",
        f"carts/{cart['cart_id']}/lines/{line}",
        operation(cart, quantity=3),
        "OperationResult",
    )["cart"]
    cart = request(
        "PUT",
        f"carts/{cart['cart_id']}/member",
        operation(cart, member_id="MEMBER_0"),
        "OperationResult",
    )["cart"]
    assert cart["total"] == "306"
    for code in ("0002", "0003"):
        cart = request(
            "POST",
            f"carts/{cart['cart_id']}/lines",
            operation(cart, code=code),
            "OperationResult",
        )["cart"]
    assert cart["total"] == "537"
    ok("member totals 306 and 537")
    # Update masters+history together; existing cart and confirmed sale keep their snapshots.
    with connect("pos_master") as connection:
        with connection.cursor() as c:
            c.execute("SELECT unit_price FROM PRODUCT WHERE product_id=1 FOR UPDATE")
            assert str(c.fetchone()[0]) == "103"
            c.execute("UPDATE PRODUCT SET unit_price=500,tax_rate_id=1 WHERE product_id=1")
            c.execute(
                "INSERT INTO PRICE_HISTORY(product_id,old_price,new_price,changed_at) "
                "VALUES(1,103,500,UTC_TIMESTAMP(6))"
            )
            c.execute("UPDATE DISCOUNT_CONDITION SET rate=0.5 WHERE condition_id=1")
        connection.commit()
    purchase_request = operation(cart, cart_id=cart["cart_id"])
    saved = request("POST", "purchases", purchase_request, "OperationResult")
    repeated = request("POST", "purchases", purchase_request, "OperationResult")
    assert saved == repeated and saved["purchase"]["total"] == "537"
    assert saved["purchase"]["lines"][0]["unit_price"] == "103"
    assert (
        request("GET", f"carts/{cart['cart_id']}/purchase", schema="CartResult")["purchase"]
        == saved["purchase"]
    )
    ok("snapshots and single purchase preserved after master change")
    old_id = cart["cart_id"]
    cart = saved["cart"]
    next_request = operation(cart)
    next_result = request("POST", f"carts/{old_id}/next", next_request, "NextResult")
    assert next_result == request("POST", f"carts/{old_id}/next", next_request, "NextResult")
    assert (
        request(
            "GET",
            f"carts/{old_id}/operations/{next_request['operation_id']}",
            schema="OperationResult",
        )["new_cart_id"]
        == next_result["new_cart_id"]
    )
    cart = next_result["cart"]
    assert not cart["lines"] and cart["member_state"] == "UNSPECIFIED"
    ok("next is atomic and duplicate returns same cart")
    cart = request(
        "POST",
        f"carts/{cart['cart_id']}/lines",
        operation(cart, code="0001"),
        "OperationResult",
    )["cart"]
    assert cart["lines"][0]["unit_price"] == "500"
    line = cart["lines"][0]["line_id"]
    delete = operation(cart)
    cart = request(
        "DELETE",
        f"carts/{cart['cart_id']}/lines/{line}?operation_id={delete['operation_id']}&version={delete['version']}",
        schema="OperationResult",
    )["cart"]
    assert not cart["lines"]
    cart = request(
        "POST",
        f"carts/{cart['cart_id']}/lines",
        operation(cart, code="0002"),
        "OperationResult",
    )["cart"]
    nonmember = request(
        "POST", "purchases", operation(cart, cart_id=cart["cart_id"]), "OperationResult"
    )
    assert nonmember["purchase"]["member_id"] is None and nonmember["purchase"]["total"] == "115"
    cart = request(
        "POST",
        f"carts/{cart['cart_id']}/next",
        operation(nonmember["cart"]),
        "NextResult",
    )["cart"]
    ok("delete and refreshed snapshot; nonmember saved")
    with connect("pos_master") as connection:
        with connection.cursor() as c:
            c.execute(
                "INSERT INTO DISCOUNT_CONDITION(product_id,valid_from,valid_to,kind,rate,amount) "
                "VALUES(1,'2026-01-01','2027-01-01','AMOUNT',NULL,600)"
            )
        connection.commit()
    cart = request(
        "POST",
        f"carts/{cart['cart_id']}/lines",
        operation(cart, code="0001"),
        "OperationResult",
    )["cart"]
    cart = request(
        "PUT",
        f"carts/{cart['cart_id']}/member",
        operation(cart, member_id="MEMBER_0"),
        "OperationResult",
    )["cart"]
    zero = request("POST", "purchases", operation(cart, cart_id=cart["cart_id"]), "OperationResult")
    assert zero["purchase"]["total"] == "0" and zero["purchase"]["lines"]
    ok("zero-yen sale with line and tax saved")
    with connect() as connection:
        with connection.cursor() as c:
            c.execute("SELECT COUNT(*) FROM PURCHASE")
            assert c.fetchone() == (3,)
            c.execute("SELECT COUNT(*) FROM PURCHASE_LINE")
            assert c.fetchone() == (5,)
            c.execute("SELECT COUNT(*) FROM PURCHASE_TAX")
            assert c.fetchone() == (4,)
            c.execute("SELECT COUNT(*) FROM CART")
            assert c.fetchone() == (3,)
            source = re.sub(r"--[^\n]*", "", (ROOT / "設計確認.sql").read_text())
            queries = [q for q in source.split(";") if q.strip()]
            for query in queries[5:]:
                c.execute(query)
                assert not c.fetchall()
        connection.rollback()
    ok("real DB counts and approved SQL integrity checks")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "https-business.json").write_text(
        json.dumps({"results": results, "browser_test": False}, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps({"passed": len(results), "browser_test": False}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # noqa: BLE001 -- suppress SQL/credential exception text
        print(json.dumps({"stopped": True, "type": type(error).__name__}))
        sys.exit(1)
