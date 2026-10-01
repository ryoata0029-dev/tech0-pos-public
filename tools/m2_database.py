"""Explicit initial DB setup. Default is offline validation, not a connection or mutation.

Run with backend/.venv/bin/python. Never initializes an existing/nonempty schema.
No reset, repair, account creation, secret printing, or automatic retries are provided.
"""

import argparse
import getpass
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.infrastructure.database import create_database, transaction  # noqa: E402
from app.infrastructure.settings import Settings  # noqa: E402
from app.security.credentials import Passwords  # noqa: E402
from app.services.seed_validation import validate_member  # noqa: E402
from app.services.validation import code, parse_money, parse_rate  # noqa: E402


def fixture():
    data = json.loads((ROOT / "backend/fixtures/m2.json").read_text())
    for staff in data["staff_ids"]:
        code(staff)
    for member in data["members"]:
        validate_member(member)
    for tax in data["taxes"]:
        parse_rate(tax["rate"])
    for product in data["products"]:
        code(product["code"])
        parse_money(product["unit_price"])
    for discount in data["discounts"]:
        if discount["kind"] == "RATE":
            parse_rate(discount["rate"])
        else:
            parse_money(discount["amount"])
        start = datetime.fromisoformat(discount["valid_from"])
        end = datetime.fromisoformat(discount["valid_to"])
        if start.tzinfo is None or end.tzinfo is None or start >= end:
            raise ValueError("Invalid fixture period")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=["validate", "schema", "seed"], default="validate", nargs="?"
    )
    parser.add_argument("--target", help="Required for writes: pos_validation")
    args = parser.parse_args()
    data = fixture()
    ddl = re.sub(r"--[^\n]*", "", (ROOT / "設計スキーマ.sql").read_text())
    statements = [s.strip() for s in ddl.split(";") if s.strip()]
    tables = re.findall(r"CREATE TABLE ([A-Z_]+)", ddl)
    if len(tables) != 16 or any(
        not s.startswith(("CREATE TABLE ", "ALTER TABLE ")) for s in statements
    ):
        raise ValueError("Unexpected DDL")
    if args.action == "validate":
        print(
            json.dumps(
                {
                    "offline_only": True,
                    "tables": len(tables),
                    "ddl_statements": len(statements),
                    "staff": len(data["staff_ids"]),
                    "members": len(data["members"]),
                    "products": len(data["products"]),
                }
            )
        )
        return
    settings = Settings.from_env()
    if (
        args.target != "pos_validation"
        or settings.db_name != args.target
        or settings.db_host not in ("localhost", "127.0.0.1")
        or settings.db_port != 3307
    ):
        raise ValueError("Write target must be the dedicated local M2 database on port 3307")
    passwords = {}
    if args.action == "seed":
        hasher = Passwords()
        for staff in data["staff_ids"]:
            password = getpass.getpass(f"{staff} synthetic password (not logged): ")
            if not password:
                raise ValueError("Empty seed password")
            passwords[staff] = hasher.hash(password)
        del password
    engine = create_database(settings)
    try:
        with engine.connect() as connection:
            version, name, secure = connection.execute(
                text("SELECT VERSION(), DATABASE(), @@require_secure_transport")
            ).one()
            if not version.startswith("8.4.") or name != args.target or not secure:
                raise ValueError("Wrong database/version or secure transport disabled")
            existing = set(
                connection.execute(
                    text(
                        "SELECT TABLE_NAME FROM information_schema.TABLES "
                        "WHERE TABLE_SCHEMA=DATABASE()"
                    )
                ).scalars()
            )
            connection.rollback()
            if args.action == "schema":
                if existing:
                    raise ValueError("Schema is not empty; stop and inspect partial DDL")
                for index, statement in enumerate(statements, 1):
                    # MySQL DDL implicitly commits. On failure retain state; never restart the loop.
                    connection.execute(text(statement))
                    connection.commit()
                    print(f"DDL statement {index}/{len(statements)} confirmed")
                return
            if existing != set(tables):
                raise ValueError("Expected exactly the approved 16 tables")
        with transaction(engine) as connection:
            for table in tables:
                # Identifiers come solely from checked-in DDL, never user input.
                if connection.execute(text(f"SELECT COUNT(*) FROM `{table}`")).scalar_one():
                    raise ValueError("Seed requires all tables empty; no UPSERT or reset")
            now = connection.execute(text("SELECT UTC_TIMESTAMP(6)")).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO REGISTER(register_id,start_state,maintenance_hold) "
                    "VALUES(1,'UNSTARTED',TRUE)"
                )
            )
            for staff, encoded in passwords.items():
                connection.execute(
                    text("INSERT INTO STAFF(staff_id,password_hash) VALUES(:id,:hash)"),
                    {"id": staff, "hash": encoded},
                )
            for member in data["members"]:
                connection.execute(
                    text(
                        "INSERT INTO MEMBER(member_id,name,phone,address,gender,age) "
                        "VALUES(:member_id,:name,:phone,:address,:gender,:age)"
                    ),
                    member,
                )
            for tax in data["taxes"]:
                connection.execute(
                    text("INSERT INTO TAX_RATE(tax_rate_id,rate) VALUES(:tax_rate_id,:rate)"),
                    tax,
                )
            for product in data["products"]:
                connection.execute(
                    text(
                        "INSERT INTO PRODUCT(product_id,code,name,unit_price,tax_rate_id) "
                        "VALUES(:product_id,:code,:name,:unit_price,:tax_rate_id)"
                    ),
                    product,
                )
                connection.execute(
                    text(
                        "INSERT INTO PRICE_HISTORY(product_id,old_price,new_price,changed_at) "
                        "VALUES(:id,NULL,:price,:now)"
                    ),
                    {
                        "id": product["product_id"],
                        "price": product["unit_price"],
                        "now": now,
                    },
                )
            for discount in data["discounts"]:
                row = dict(discount)
                for key in ("valid_from", "valid_to"):
                    row[key] = datetime.fromisoformat(row[key]).replace(tzinfo=None)
                connection.execute(
                    text(
                        "INSERT INTO DISCOUNT_CONDITION(condition_id,product_id,kind,rate,"
                        "amount,valid_from,valid_to) "
                        "VALUES(:condition_id,:product_id,:kind,:rate,:amount,"
                        ":valid_from,:valid_to)"
                    ),
                    row,
                )
            expected = {
                "REGISTER": 1,
                "STAFF": 2,
                "MEMBER": 2,
                "TAX_RATE": 2,
                "PRODUCT": 2,
                "PRICE_HISTORY": 2,
                "DISCOUNT_CONDITION": 1,
            }
            for table in tables:
                count = connection.execute(text(f"SELECT COUNT(*) FROM `{table}`")).scalar_one()
                if count != expected.get(table, 0):
                    raise ValueError("Seed readback count mismatch")
        print("Seed COMMIT confirmed; maintenance_hold remains TRUE. Inspect before release.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Never print connector exception strings: they may contain bound credentials.
        print(
            "Stopped. Do not retry writes automatically. Inspect target/state using the runbook.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
