"""Named, local M2 setup phases. No deletes, reset, retries or secret output."""

import argparse
import json
import os
import re
import sys
from unittest.mock import patch

import pymysql
from m2_local_profile import EVIDENCE, LOCAL, PROFILE, ROOT

sys.path.insert(0, str(ROOT / "backend"))
import m2_database  # noqa: E402


def secrets():
    return json.loads((LOCAL / "secrets.json").read_text())


def connect(user="root", database="pos_validation"):
    return pymysql.connect(
        host="127.0.0.1",
        port=3307,
        user=user,
        password=secrets()[user],
        database=database,
        ssl_ca=str(LOCAL / "tls/ca.crt"),
        ssl_verify_cert=True,
        ssl_verify_identity=True,
        autocommit=False,
        charset="utf8mb4",
        connect_timeout=3,
        read_timeout=5,
        write_timeout=5,
    )


def configure(user):
    values = secrets()
    os.environ.update(
        POS_FRONTEND_ORIGIN=(
            (LOCAL / "public-origin.txt").read_text().strip()
            if PROFILE in ("browser", "mac") and (LOCAL / "public-origin.txt").exists()
            else "https://localhost:8443"
        ),
        POS_RELAY_SECRET=values["relay"],
        POS_DB_HOST="127.0.0.1",
        POS_DB_PORT="3307",
        POS_DB_NAME="pos_validation",
        POS_DB_USER=user,
        POS_DB_PASSWORD=values[user],
        POS_DB_SSL_CA=str(LOCAL / "tls/ca.crt"),
    )


def execute_file(connection, path):
    sql = re.sub(r"--[^\n]*", "", path.read_text())
    with connection.cursor() as cursor:
        for statement in sql.split(";"):
            if statement.strip() and not statement.strip().startswith("SHOW GRANTS"):
                cursor.execute(statement)
    connection.commit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=[
            "ready",
            "bootstrap",
            "schema",
            "grants",
            "seed",
            "release",
            "snapshot",
        ],
    )
    action = parser.parse_args().action
    if action in ("schema", "seed"):
        configure("pos_schema" if action == "schema" else "root")
        args = ["m2_database.py", action, "--target", "pos_validation"]
        values = secrets()

        def password(prompt):
            return values[prompt.split()[0]]

        with patch.object(sys, "argv", args), patch("getpass.getpass", password):
            m2_database.main()
        return
    with connect(database=None if action in ("ready", "bootstrap") else "pos_validation") as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()[0]
            if not version.startswith("8.4."):
                raise ValueError("Version mismatch")
            if action == "ready":
                print(json.dumps({"mysql_version": version, "verified_tls_connection": True}))
                return
            if action == "bootstrap":
                cursor.execute("SHOW DATABASES LIKE %s", ("pos_validation",))
                if cursor.fetchone():
                    raise ValueError("Target already exists")
                cursor.execute(
                    "CREATE DATABASE pos_validation CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin"
                )
                values = secrets()
                for user in ["pos_app", "pos_master", "pos_schema"]:
                    cursor.execute(
                        "CREATE USER %s@%s IDENTIFIED BY %s REQUIRE SSL",
                        (user, "%", values[user]),
                    )
                cursor.execute(
                    "GRANT SELECT,CREATE,ALTER,INDEX,REFERENCES "
                    "ON pos_validation.* TO 'pos_schema'@'%'"
                )
                print("New database/accounts and DDL-only grants created.")
            elif action == "grants":
                execute_file(conn, ROOT / "backend/sql/m2_grants.sql")
                print("Table-scoped grants applied.")
            elif action == "release":
                cursor.execute(
                    "SELECT start_state,maintenance_hold,active_context_id,current_cart_id "
                    "FROM REGISTER WHERE register_id=1 FOR UPDATE"
                )
                if cursor.fetchone() != ("UNSTARTED", 1, None, None):
                    raise ValueError("Release requires the untouched initial validation register")
                cursor.execute(
                    "UPDATE REGISTER SET maintenance_hold=FALSE "
                    "WHERE register_id=1 AND maintenance_hold=TRUE"
                )
                if cursor.rowcount != 1:
                    raise ValueError("Release row count mismatch")
                conn.commit()
                execute_file(conn, ROOT / "backend/sql/m2_revoke_initial.sql")
                print("Initial hold released and initial master privileges revoked.")
            elif action == "snapshot":
                cursor.execute(
                    "SELECT @@require_secure_transport,@@global.general_log,@@global.slow_query_log"
                )
                flags = cursor.fetchone()
                cursor.execute("SHOW SESSION STATUS LIKE 'Ssl_cipher'")
                cipher = cursor.fetchone()[1]
                cursor.execute(
                    "SELECT TABLE_NAME FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME"
                )
                tables = [row[0] for row in cursor.fetchall()]
                counts = {}
                for table in tables:
                    cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
                    counts[table] = cursor.fetchone()[0]
                grants = {}
                for user in ["pos_app", "pos_master", "pos_schema"]:
                    cursor.execute("SHOW GRANTS FOR %s@%s", (user, "%"))
                    grants[user] = [row[0] for row in cursor.fetchall()]
                result = {
                    "version": version,
                    "tls_required": bool(flags[0]),
                    "general_log": bool(flags[1]),
                    "slow_log": bool(flags[2]),
                    "cipher": cipher,
                    "table_counts": counts,
                    "grants": grants,
                }
                EVIDENCE.mkdir(parents=True, exist_ok=True)
                target = EVIDENCE / "mysql-snapshot.json"
                target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
                print(
                    json.dumps(
                        {
                            "version": version,
                            "table_count": len(tables),
                            "cipher": cipher,
                        }
                    )
                )
            conn.commit()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Exception text may contain SQL parameters. Only classification is public.
        error_number = exc.args[0] if exc.args and type(exc.args[0]) is int else None
        print(
            json.dumps(
                {
                    "stopped": True,
                    "type": type(exc).__name__,
                    "db_error_number": error_number,
                }
            )
        )
        raise SystemExit(1) from None
