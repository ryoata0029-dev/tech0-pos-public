"""Fixed Mac-flow fixture and secret-free, read-only stage snapshots. No reset."""

import argparse
import json

from m2_local_db import connect
from m2_local_profile import (
    BACKEND_PORT,
    EVIDENCE,
    FRONTEND_PORT,
    MYSQL_PORT,
    NAME,
    PROFILE,
    VOLUME,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("fixture", "snapshot", "change-price"))
    parser.add_argument("--stage")
    args = parser.parse_args()
    if PROFILE not in (
        "mac-flow",
        "mac-recovery",
        "mac-restart",
        "mac-member",
        "mac-tc03",
        "mac-tc03-fix",
        "mac-tc02",
        "mac-batch",
        "mac-parallel",
        "parallel-next",
        "parallel-mac-next",
        "oct05-mac",
        "iphone-camera",
    ):
        raise ValueError("Only mac-flow is allowed")
    identity = json.loads((EVIDENCE / "mysql-environment.json").read_text())
    ports = {"mysql": MYSQL_PORT, "frontend": FRONTEND_PORT, "backend": BACKEND_PORT}
    if PROFILE in ("parallel-mac-next", "oct05-mac") and (
        identity.get("container") != NAME
        or identity.get("volume") != VOLUME
        or identity.get("port_binding") != f"127.0.0.1:{MYSQL_PORT} -> 3306"
        or identity.get("ports") != ports
    ):
        raise ValueError("Dedicated Mac resource/port identity mismatch")
    target = None
    if args.action == "snapshot":
        if not args.stage or not args.stage.replace("-", "").isalnum():
            raise ValueError("A safe stage name is required")
        target = EVIDENCE / f"db-{args.stage}.json"
        if target.exists():
            raise ValueError("Never overwrite evidence")
    with connect("pos_app" if target else "root") as conn, conn.cursor() as c:
        c.execute("SELECT @@hostname,DATABASE(),UTC_TIMESTAMP(6)")
        hostname, database, now = c.fetchone()
        if hostname != identity["container_id"][:12] or database != "pos_validation":
            raise ValueError("Wrong database identity")
        if args.action == "fixture":
            c.execute(
                "SELECT start_state,current_cart_id FROM REGISTER WHERE register_id=1 FOR UPDATE"
            )
            if c.fetchone() != ("UNSTARTED", None):
                raise ValueError("Fixture requires untouched register")
            c.execute("SELECT COUNT(*) FROM CART")
            if c.fetchone() != (0,):
                raise ValueError("Fixture requires no carts")
            c.execute("SELECT COUNT(*) FROM PRODUCT")
            if c.fetchone() != (2,):
                raise ValueError("Fixture already changed")
            c.execute("UPDATE PRODUCT SET tax_rate_id=2 WHERE product_id=1")
            c.execute(
                "UPDATE PRODUCT SET unit_price=107,tax_rate_id=1,name='演習食品107円A' "
                "WHERE product_id=2"
            )
            c.execute(
                "INSERT INTO PRICE_HISTORY(product_id,old_price,new_price,changed_at) "
                "VALUES(2,210,107,UTC_TIMESTAMP(6))"
            )
            c.execute(
                "INSERT INTO PRODUCT(product_id,code,name,unit_price,tax_rate_id) "
                "VALUES(3,'0003','演習食品107円B',107,1)"
            )
            c.execute(
                "INSERT INTO PRICE_HISTORY(product_id,old_price,new_price,changed_at) "
                "VALUES(3,NULL,107,UTC_TIMESTAMP(6))"
            )
            if PROFILE in ("iphone-camera", "parallel-next"):
                for product_id, code, name in (
                    (4, "0001234567895", "演習EAN13商品"),
                    (5, "00123457", "演習EAN8商品"),
                    (6, "Ab_01", "演習Code128大小文字商品"),
                ):
                    c.execute(
                        "INSERT INTO PRODUCT(product_id,code,name,unit_price,tax_rate_id) "
                        "VALUES(%s,%s,%s,103,2)",
                        (product_id, code, name),
                    )
                    c.execute(
                        "INSERT INTO PRICE_HISTORY(product_id,old_price,new_price,changed_at) "
                        "VALUES(%s,NULL,103,UTC_TIMESTAMP(6))",
                        (product_id,),
                    )
            conn.commit()
            print("Mac-only three-product fixture committed; register remains held.")
            return
        if args.action == "change-price":
            c.execute("SELECT unit_price FROM PRODUCT WHERE product_id=1 FOR UPDATE")
            if c.fetchone() != (103,):
                raise ValueError("Original master price required")
            c.execute(
                "SELECT COUNT(*) FROM CART_LINE WHERE product_id=1 AND unit_price_snapshot=103"
            )
            if c.fetchone()[0] == 0:
                raise ValueError("An actual browser-added snapshot is required")
            c.execute("UPDATE PRODUCT SET unit_price=500,tax_rate_id=1 WHERE product_id=1")
            c.execute(
                "INSERT INTO PRICE_HISTORY(product_id,old_price,new_price,changed_at) "
                "VALUES(1,103,500,UTC_TIMESTAMP(6))"
            )
            conn.commit()
            print("Mac-only master price/tax changed atomically; cart snapshots untouched.")
            return
        conn.rollback()
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        c.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")
        queries = {
            "register": "SELECT register_id,start_state,maintenance_hold,active_context_id,"
            "current_cart_id FROM REGISTER",
            "contexts": "SELECT context_id,starting_staff_id,confirmed_at,invalidated_at "
            "FROM BROWSER_CONTEXT",
            "carts": "SELECT cart_id,staff_id,state,version,member_state,member_id,"
            "pending_member_id,active_member_operation_id,active_purchase_operation_id,"
            "purchase_prepared_version,"
            "subtotal,total,tax_breakdown FROM CART ORDER BY created_at",
            "lines": "SELECT cart_id,line_id,line_no,product_id,quantity,unit_price_snapshot,"
            "tax_rate_snapshot,discount_per_unit,net_unit_price,line_subtotal,conditions_fixed_at "
            "FROM CART_LINE ORDER BY cart_id,line_no",
            "operations": "SELECT cart_id,operation_id,kind,request_version,status,"
            "prepared_version,applied_version,result_code,next_cart_id "
            "FROM CART_OPERATION ORDER BY created_at",
            "purchases": "SELECT cart_id,staff_id,member_id,subtotal,total,purchased_at "
            "FROM PURCHASE ORDER BY purchased_at",
            "purchase_lines": "SELECT cart_id,line_no,product_id,quantity,unit_price_snapshot,"
            "tax_rate_snapshot,discount_per_unit,net_unit_price,line_subtotal "
            "FROM PURCHASE_LINE ORDER BY cart_id,line_no",
            "purchase_taxes": "SELECT cart_id,tax_rate_snapshot,taxable_subtotal,tax_amount "
            "FROM PURCHASE_TAX ORDER BY cart_id,tax_rate_snapshot",
            "products": "SELECT product_id,code,unit_price,tax_rate_id "
            "FROM PRODUCT ORDER BY product_id",
        }
        if PROFILE in ("iphone-camera", "parallel-next"):
            # Fixture codes only; never export the full request payload.
            queries["operations"] = (
                "SELECT cart_id,operation_id,kind,request_version,status,"
                "prepared_version,applied_version,result_code,next_cart_id,created_at,"
                "JSON_UNQUOTE(JSON_EXTRACT(request_payload,'$.code')) AS requested_code "
                "FROM CART_OPERATION ORDER BY created_at"
            )
        result = {"stage": args.stage, "observed_at_utc": str(now)}
        if PROFILE in ("parallel-mac-next", "oct05-mac"):
            result.update(profile=PROFILE, container=NAME, ports=ports)
        for name, query in queries.items():
            c.execute(query)
            keys = [column[0] for column in c.description]
            result[name] = [dict(zip(keys, row, strict=True)) for row in c.fetchall()]
        conn.rollback()
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n")
    print(
        json.dumps(
            {
                "stage": args.stage,
                "carts": len(result["carts"]),
                "purchases": len(result["purchases"]),
                "current": result["carts"][-1] if result["carts"] else None,
            },
            default=str,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"stopped": True, "error_type": type(exc).__name__}))
        raise SystemExit(1) from None
