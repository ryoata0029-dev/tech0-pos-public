"""One-shot live checks on the isolated M2 DB; DML probes are always rolled back."""

import json
import re
import ssl
import sys
import traceback

import pymysql
from m2_local_db import ROOT, configure, connect, secrets
from sqlalchemy import text

sys.path.insert(0, str(ROOT / "backend"))
from app.infrastructure.database import create_database, transaction  # noqa: E402
from app.infrastructure.settings import Settings  # noqa: E402


def main():
    results = []

    def ok(name, **evidence):
        results.append({"check": name, "passed": True, **evidence})

    with connect() as conn:
        with conn.cursor() as cursor:
            source = re.sub(r"--[^\n]*", "", (ROOT / "設計確認.sql").read_text())
            rows = []
            for statement in source.split(";"):
                if statement.strip():
                    cursor.execute(statement)
                    rows.append(cursor.fetchall())
            assert len(rows[1]) == 16 and rows[4] == ((1,),)
            assert all(not result for result in rows[5:])
            ok(
                "approved read-only verification SQL",
                table_count=16,
                integrity_queries_empty=len(rows) - 5,
            )
            columns = [
                dict(zip(("table", "column", "type", "nullable", "collation"), row, strict=True))
                for row in rows[2]
            ]
            constraints = [
                dict(zip(("table", "name", "type"), row, strict=True)) for row in rows[3]
            ]
            (ROOT / "docs/implementation/evidence/m2/mysql-schema.json").write_text(
                json.dumps({"columns": columns, "constraints": constraints}, indent=2) + "\n"
            )
        conn.rollback()
    probes = [
        (
            "unique code",
            "INSERT INTO PRODUCT(code,name,unit_price,tax_rate_id) VALUES('0001','probe',1,1)",
            {1062},
        ),
        (
            "foreign key",
            "INSERT INTO PRODUCT(code,name,unit_price,tax_rate_id) "
            "VALUES('PROBE_FK','probe',1,999999)",
            {1452},
        ),
        (
            "member mandatory field",
            "INSERT INTO MEMBER(member_id,name,phone,address,gender,age) "
            "VALUES('PROBE_NULL',NULL,'x','x','x',0)",
            {1048},
        ),
        (
            "member empty string",
            "INSERT INTO MEMBER(member_id,name,phone,address,gender,age) "
            "VALUES('PROBE_EMPTY','','x','x','x',0)",
            {3819},
        ),
        (
            "member age unsigned",
            "INSERT INTO MEMBER(member_id,name,phone,address,gender,age) "
            "VALUES('PROBE_AGE','x','x','x','x',-1)",
            {1264},
        ),
        ("tax check", "INSERT INTO TAX_RATE(rate) VALUES(1.1)", {3819}),
        (
            "register state check",
            "UPDATE REGISTER SET start_state='READY' WHERE register_id=1",
            {3819},
        ),
        (
            "staff code check",
            "INSERT INTO STAFF(staff_id,password_hash) VALUES('bad code','unused')",
            {3819},
        ),
    ]
    for name, sql, codes in probes:
        with connect() as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute("SET SESSION sql_mode='STRICT_ALL_TABLES'")
                    cursor.execute(sql)
                raise AssertionError("Constraint did not reject")
            except pymysql.MySQLError as error:
                assert error.args[0] in codes, (name, error.args[0])
                ok(name, mysql_error=error.args[0])
            finally:
                conn.rollback()
    forbidden = [
        ("master UPDATE denied", "UPDATE PRODUCT SET name=name WHERE product_id=1"),
        ("purchase UPDATE denied", "UPDATE PURCHASE SET total=total WHERE 1=0"),
        ("purchase DELETE denied", "DELETE FROM PURCHASE WHERE 1=0"),
        (
            "register INSERT denied",
            "INSERT INTO REGISTER(register_id,start_state) VALUES(1,'UNSTARTED')",
        ),
        ("cart DELETE denied", "DELETE FROM CART WHERE 1=0"),
        ("DDL denied", "CREATE TABLE M2_PERMISSION_PROBE(id INT)"),
    ]
    for name, sql in forbidden:
        with connect("pos_app") as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute(sql)
                raise AssertionError("Forbidden statement unexpectedly succeeded")
            except pymysql.MySQLError as error:
                assert error.args[0] == 1142
                ok(name, mysql_error=1142)
            finally:
                conn.rollback()
    for name, options in [
        ("non-TLS rejected", {"ssl_disabled": True}),
        ("untrusted CA rejected", {"ssl": ssl.create_default_context()}),
    ]:
        try:
            connection = pymysql.connect(
                host="127.0.0.1",
                port=3307,
                user="pos_app",
                password=secrets()["pos_app"],
                database="pos_validation",
                connect_timeout=3,
                **options,
            )
            connection.close()
            raise AssertionError("Insecure/untrusted connection succeeded")
        except pymysql.MySQLError as error:
            assert error.args[0] in ({3159, 1045} if name.startswith("non-") else {2003, 2026}), (
                name,
                error.args[0],
            )
            ok(name, mysql_error=error.args[0])
    configure("pos_app")
    engine = create_database(Settings.from_env())
    with transaction(engine, readonly=True) as conn:
        values = conn.execute(
            text("SELECT @@session.transaction_isolation,@@session.time_zone,@@session.sql_mode")
        ).one()
        assert values[0] == "REPEATABLE-READ" and values[1] == "+00:00"
        assert "STRICT_ALL_TABLES" in values[2]
        try:
            conn.execute(
                text("UPDATE REGISTER SET maintenance_hold=maintenance_hold WHERE register_id=1")
            )
            raise AssertionError("READ ONLY transaction accepted update")
        except Exception as error:
            assert getattr(getattr(error, "orig", None), "args", (None,))[0] == 1792
            ok("read-only transaction rejects writes", mysql_error=1792)
    with transaction(engine) as conn:
        isolation = conn.execute(text("SELECT @@session.transaction_isolation")).scalar_one()
        assert isolation == "READ-COMMITTED"
        ok("pool returns default isolation after read snapshot", isolation=isolation)
    engine.dispose()
    (ROOT / "docs/implementation/evidence/m2/mysql-checks.json").write_text(
        json.dumps(results, indent=2) + "\n"
    )
    print(json.dumps({"passed": len(results), "failed": 0}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(
            json.dumps(
                {
                    "stopped": True,
                    "type": type(exc).__name__,
                    "code": exc.args[0] if exc.args and type(exc.args[0]) is int else None,
                    "line": traceback.extract_tb(exc.__traceback__)[-1].lineno,
                }
            )
        )
        raise SystemExit(1) from None
