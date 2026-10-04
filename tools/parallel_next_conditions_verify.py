"""Fixed SQL conditions proof after the API suite. Default offline; root alone runs it."""

import argparse
import hashlib
import json
import logging
import sys
import threading
import traceback
from datetime import UTC, datetime, timedelta
from pathlib import Path

import parallel_next_db_verify as base

ROOT, EVIDENCE = base.ROOT, base.EVIDENCE
CODES = ("API_PERIOD", "API_CONSISTENCY")
# MySQL DATETIME and the real repository use naive UTC; derive explicitly from UTC.
NOW = datetime(2030, 1, 1, tzinfo=UTC).replace(tzinfo=None)
STAGE = "not-started"
RESULT = {
    "transport": "actual SQL Repository + real TLS MySQL; no HTTP/API/clock change",
    "schema": base.DB,
    "completed": False,
}


def frozen_business():
    """Explicit allowlist excludes authentication hashes and personal member attributes."""
    with base.connect(readonly=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT cart_id FROM CART WHERE staff_id='STAFF_API' ORDER BY cart_id")
            ids = [r["cart_id"] for r in cursor.fetchall()]
            base.require(len(ids) == 7, "Expected the API suite's seven saved carts")
            cursor.execute("SELECT COUNT(*) n FROM PURCHASE WHERE staff_id='STAFF_API'")
            base.require(cursor.fetchone()["n"] == 7, "Expected seven API purchases")
            cursor.execute(
                "SELECT product_id,code,unit_price,tax_rate_id FROM PRODUCT WHERE "
                "code NOT IN ('API_PERIOD','API_CONSISTENCY') ORDER BY product_id"
            )
            products = cursor.fetchall()
            base.require(
                tuple(r["code"] for r in products) == base.CODES,
                "Original product scope mismatch",
            )
            cursor.execute(
                "SELECT h.* FROM PRICE_HISTORY h JOIN PRODUCT p ON p.product_id=h.product_id "
                "WHERE p.code NOT IN ('API_PERIOD','API_CONSISTENCY') ORDER BY h.history_id"
            )
            history = cursor.fetchall()
        connection.rollback()
    carts = {}
    for cid in ids:
        observed = base.observe(cid)
        observed.pop("connection_id")
        observed.pop("at_utc")
        carts[cid] = observed
    return {"carts": carts, "products": products, "price_history": history}


def fixtures():
    with base.connect("pos_api_master") as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT code FROM PRODUCT WHERE code IN (%s,%s)", CODES)
            base.require(not cursor.fetchall(), "Condition products already exist; no rerun")
            cursor.execute("SELECT tax_rate_id FROM TAX_RATE WHERE rate=0.10")
            rows = cursor.fetchall()
            base.require(len(rows) == 1, "One existing 10-percent tax fixture required")
            tax10 = rows[0]["tax_rate_id"]
            cursor.execute("INSERT INTO TAX_RATE(rate) VALUES(0.08)")
            tax8 = cursor.lastrowid
            result = {"tax10": tax10, "tax8": tax8}
            for code in CODES:
                cursor.execute(
                    "INSERT INTO PRODUCT(code,name,unit_price,tax_rate_id) VALUES(%s,%s,103,%s)",
                    (code, "架空SQL試験商品 " + code, tax10),
                )
                pid = cursor.lastrowid
                cursor.execute(
                    "INSERT INTO PRICE_HISTORY(product_id,old_price,new_price,changed_at) "
                    "VALUES(%s,NULL,103,UTC_TIMESTAMP(6))",
                    (pid,),
                )
                start = (
                    NOW
                    if code == "API_PERIOD"
                    else datetime(2020, 1, 1, tzinfo=UTC).replace(tzinfo=None)
                )
                end = (
                    NOW + timedelta(days=1)
                    if code == "API_PERIOD"
                    else datetime(2099, 1, 1, tzinfo=UTC).replace(tzinfo=None)
                )
                cursor.execute(
                    "INSERT INTO DISCOUNT_CONDITION"
                    "(product_id,valid_from,valid_to,kind,rate,amount) "
                    "VALUES(%s,%s,%s,'RATE',0.10,NULL)",
                    (pid, start, end),
                )
                result[code] = {
                    "product_id": pid,
                    "condition_id": cursor.lastrowid,
                    "valid_from": start,
                    "valid_to": end,
                }
        connection.commit()
    return result


def read_conditions(engine, code, now):
    from sqlalchemy import event

    from app.repositories.business import BusinessRepository

    statements = []

    def record(connection, cursor, statement, parameters, context, many):
        if statement.startswith("SELECT p.*") and "JOIN TAX_RATE" in statement:
            statements.append(
                {
                    "sql_sha256": hashlib.sha256(statement.encode()).hexdigest(),
                    "statement": statement,
                }
            )

    event.listen(engine, "before_cursor_execute", record)
    try:
        with engine.connect() as connection, connection.begin():
            connection_id = connection.exec_driver_sql("SELECT CONNECTION_ID()").scalar_one()
            isolation = connection.exec_driver_sql(
                "SELECT @@session.transaction_isolation"
            ).scalar_one()
            base.require(isolation == "READ-COMMITTED", "Repository read is not READ COMMITTED")
            rows = BusinessRepository(connection).product_conditions(code, now)
    finally:
        event.remove(engine, "before_cursor_execute", record)
    base.require(
        len(statements) == 1 and len(rows) == 1,
        "Expected one real joined SQL and one product row",
    )
    return {
        "input_code": code,
        "input_utc": now,
        "rows": rows,
        "sql": statements[0],
        "isolation": isolation,
        "connection_id": connection_id,
        "observed_at_utc": datetime.now(UTC),
    }


def check_tuple(observed, item, price, tax, rate, tax_id):
    row = observed["rows"][0]
    base.require(
        row["product_id"] == item["product_id"]
        and row["unit_price"] == price
        and row["tax_rate"] == tax
        and row["tax_rate_id"] == tax_id
        and row["condition_id"] == item["condition_id"]
        and row["kind"] == "RATE"
        and row["discount_rate"] == rate
        and row["amount"] is None,
        "Product/tax/discount tuple is mixed or differs from independent expected values",
    )


def consistency(engine, setup):
    from decimal import Decimal

    item = setup["API_CONSISTENCY"]
    pid, cid = item["product_id"], item["condition_id"]
    ready, release = threading.Event(), threading.Event()
    state = {"commit_allowed": False, "committed": False}

    def writer():
        try:
            with (
                base.connect("pos_api_master") as connection,
                connection.cursor() as cursor,
            ):
                cursor.execute("SELECT CONNECTION_ID() n")
                state["writer_connection_id"] = cursor.fetchone()["n"]
                cursor.execute(
                    "SELECT unit_price FROM PRODUCT WHERE product_id=%s FOR UPDATE",
                    (pid,),
                )
                base.require(
                    cursor.fetchone()["unit_price"] == 103,
                    "Writer source price not 103",
                )
                cursor.execute(
                    "UPDATE PRODUCT SET unit_price=500,tax_rate_id=%s WHERE product_id=%s",
                    (setup["tax8"], pid),
                )
                base.require(cursor.rowcount == 1, "Writer product target missing")
                cursor.execute(
                    "UPDATE DISCOUNT_CONDITION SET rate=0.50 WHERE condition_id=%s",
                    (cid,),
                )
                base.require(cursor.rowcount == 1, "Writer condition target missing")
                cursor.execute(
                    "INSERT INTO PRICE_HISTORY(product_id,old_price,new_price,changed_at) "
                    "VALUES(%s,103,500,UTC_TIMESTAMP(6))",
                    (pid,),
                )
                state["uncommitted_changes_ready_at_utc"] = datetime.now(UTC)
                ready.set()
                base.require(release.wait(15), "Writer coordinator release timed out")
                if state["commit_allowed"]:
                    connection.commit()
                    state["committed"] = True
                    state["commit_ack_read_at_utc"] = datetime.now(UTC)
                else:
                    connection.rollback()
                    state["rolled_back"] = True
        except Exception as error:  # noqa: BLE001 - thread errors cannot leak SQL or values
            state["error"] = {
                "type": type(error).__name__,
                "mysql_code": error.args[0] if error.args and type(error.args[0]) is int else None,
            }
            ready.set()

    thread = threading.Thread(target=writer, name="api-conditions-master", daemon=True)
    thread.start()
    RESULT["writer"] = state
    try:
        base.require(
            ready.wait(7) and "error" not in state,
            "Writer did not reach controlled uncommitted stage",
        )
        # No sleep guessing: writer has completed every UPDATE/INSERT and cannot COMMIT yet.
        old = read_conditions(engine, "API_CONSISTENCY", NOW)
        base.require(
            old["connection_id"] != state["writer_connection_id"],
            "Repository reused writer",
        )
        check_tuple(old, item, Decimal(103), Decimal("0.10"), Decimal("0.10"), setup["tax10"])
        committed_view = base.observe(product_id=pid)
        base.require(
            committed_view["connection_id"] != state["writer_connection_id"]
            and committed_view["product"][0]["unit_price"] == 103
            and len(committed_view["history"]) == 1,
            "Fresh TLS observer saw uncommitted writer changes",
        )
        RESULT["old_while_writer_uncommitted"] = old
        RESULT["committed_before_release"] = committed_view
        state["commit_allowed"] = True
        state["coordinator_release_at_utc"] = datetime.now(UTC)
    finally:
        release.set()
        thread.join(7)
    base.require(
        not thread.is_alive() and "error" not in state and state["committed"],
        "Writer completion is failed or unknown; no replay",
    )
    # A new SQL snapshot is already guaranteed by READ COMMITTED; additionally force a
    # fresh physical TLS connection so the entire new product/tax/discount tuple
    # is observed independently.
    engine.dispose()
    new = read_conditions(engine, "API_CONSISTENCY", NOW)
    base.require(
        new["connection_id"] not in (old["connection_id"], state["writer_connection_id"]),
        "Post-COMMIT joined observation did not use a fresh physical connection",
    )
    check_tuple(new, item, Decimal(500), Decimal("0.08"), Decimal("0.50"), setup["tax8"])
    committed = base.observe(product_id=pid)
    base.require(
        committed["product"][0]["unit_price"] == 500
        and len(committed["history"]) == 2
        and committed["history"][1]["old_price"] == 103
        and committed["history"][1]["new_price"] == 500,
        "Fresh committed price/history tuple not consistent",
    )
    RESULT["new_after_commit"] = new
    RESULT["committed_after_release"] = committed


def execute():
    global STAGE
    from app.infrastructure.database import create_database
    from app.infrastructure.settings import Settings

    before = frozen_business()
    RESULT["original_before"] = before
    STAGE = "dedicated-fixtures"
    setup = fixtures()
    RESULT["fixture"] = setup
    settings = Settings(
        "https://localhost:8443",
        base.secret_values()["relay"],
        "127.0.0.1",
        3307,
        base.DB,
        "pos_api_app",
        base.secret_values()["pos_app"],
        str(base.LOCAL / "tls/ca.crt"),
    )
    engine = create_database(settings)
    try:
        STAGE = "explicit-sql-period-boundaries"
        period = setup["API_PERIOD"]
        cases = []
        for name, at, active in (
            ("before-start", NOW - timedelta(microseconds=1), False),
            ("exact-start", NOW, True),
            ("before-end", period["valid_to"] - timedelta(microseconds=1), True),
            ("exact-end", period["valid_to"], False),
        ):
            observed = read_conditions(engine, "API_PERIOD", at)
            row = observed["rows"][0]
            base.require(
                row["product_id"] == period["product_id"],
                "Period product identity changed",
            )
            # Decimal-to-string checks avoid float equality; independent SQL bounds are explicit.
            base.require(
                str(row["unit_price"]) == "103" and str(row["tax_rate"]) == "0.1000",
                "Period product amount/tax mismatch",
            )
            base.require(
                row["condition_id"] == period["condition_id"]
                if active
                else row["condition_id"] is None,
                "SQL interval endpoint selection wrong",
            )
            if active:
                base.require(
                    row["valid_from"] == period["valid_from"]
                    and row["valid_to"] == period["valid_to"]
                    and str(row["discount_rate"]) == "0.1000",
                    "Candidate interval/rate wrong",
                )
            cases.append(
                {
                    "case": name,
                    "expected_candidate_count": int(active),
                    "observed": observed,
                }
            )
        RESULT["period_boundaries"] = cases
        STAGE = "controlled-uncommitted-master-writer"
        consistency(engine, setup)
    finally:
        engine.dispose()
    after = frozen_business()
    base.require(before == after, "Original seven purchases/products/history changed")
    RESULT["original_after"] = after
    RESULT["original_seven_purchases_products_history_unchanged"] = True
    RESULT["limits"] = [
        "Fixed input UTC values test real SQL comparison, not normal HTTP clock arrival",
        "Controlled old/new single-SELECT snapshots, not SQL JOIN internal interleavings",
        "No new cart line, Cookie, HTTP, browser, phone or camera request",
    ]
    RESULT["completed"] = True
    STAGE = "completed"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if not args.run:
        print(
            json.dumps(
                {
                    "offline_only": True,
                    "profile": "parallel-next",
                    "schema": base.DB,
                    "codes": CODES,
                    "checks": [
                        "real SQL four interval boundaries",
                        "controlled master TX old/new",
                    ],
                    "transport": "Repository + TLS MySQL; no HTTP",
                }
            )
        )
        return 0
    base.EXPECTED_HOSTNAME = base.resource_guard()
    proof = json.loads((EVIDENCE / "api-db-run.json").read_text())
    base.require(
        proof["status"] == "limited_conditions_passed" and proof["schema"] == base.DB,
        "Completed initial API DB proof required",
    )
    output = EVIDENCE / "api-db-conditions.json"
    base.require(not output.exists(), "Conditions evidence exists; no automatic overwrite/rerun")
    sys.path.insert(0, str(ROOT / "backend"))
    logging.disable(logging.CRITICAL)
    with output.open("x") as stream:
        json.dump({"status": "started", "schema": base.DB}, stream)
    try:
        execute()
        RESULT["status"] = "limited_sql_conditions_passed"
    except Exception as error:  # noqa: BLE001 - never print SQL or secret-bearing tracebacks
        RESULT.update(
            status="stopped_partial_state_retained",
            error_type=type(error).__name__,
            mysql_code=error.args[0] if error.args and type(error.args[0]) is int else None,
            line=traceback.extract_tb(error.__traceback__)[-1].lineno,
        )
    RESULT.update(
        at_utc=datetime.now(UTC),
        last_stage=STAGE,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    )
    output.write_text(json.dumps(RESULT, default=base.encode, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": RESULT["status"], "output": output.name, "stage": STAGE}))
    return 0 if RESULT["completed"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # noqa: BLE001 - sanitized preflight boundary
        print(json.dumps({"stopped_before_execution": True, "error_type": type(error).__name__}))
        raise SystemExit(1) from None
