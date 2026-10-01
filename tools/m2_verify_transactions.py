"""Live M2 transaction tests. Time fixtures use one rolled-back root transaction."""

import json
import sys
from datetime import timedelta

from m2_local_db import ROOT, configure, connect
from m2_verify_https import Client
from sqlalchemy import text

sys.path.insert(0, str(ROOT / "backend"))
from app.infrastructure.database import create_database, transaction  # noqa: E402
from app.infrastructure.settings import Settings  # noqa: E402
from app.repositories.startup import StartupRepository  # noqa: E402
from app.security.credentials import Passwords, new_token, token_hash  # noqa: E402
from app.services.errors import PosError  # noqa: E402
from app.services.startup import StartupService  # noqa: E402


def main():
    results = []

    def ok(name):
        results.append({"check": name, "passed": True})
        print(json.dumps({"check": name, "passed": True}), flush=True)

    def fails(status, call):
        try:
            call()
            raise AssertionError("Expected rejection")
        except PosError as error:
            assert error.status == status

    configure("root")
    engine = create_database(Settings.from_env())
    with engine.connect() as conn:
        tx = conn.begin()
        try:
            repo = StartupRepository(conn)
            service = StartupService(repo, Passwords())
            register = service.register(lock=True)
            context_id = register["active_context_id"]
            assert register["start_state"] == "READY" and context_id is not None
            now = repo.now()
            # Rollback-only fixture cookies never enter HTTP responses or persistent files.
            resume = new_token()
            auth = new_token()
            repo.write(
                "UPDATE BROWSER_CONTEXT SET token_hash=:token WHERE context_id=:id",
                token=token_hash(resume),
                id=context_id,
            )
            repo.rotate_session(
                "STAFF_A",
                token_hash(auth),
                register["active_session_hash"],
                now,
                now + timedelta(hours=8),
            )
            register = service.register(lock=True)
            service.authenticate(
                register, auth, now + timedelta(hours=8) - timedelta(microseconds=1)
            )
            fails(
                401,
                lambda: service.authenticate(register, auth, now + timedelta(hours=8)),
            )
            ok("DB-backed auth is valid immediately before 8h and invalid at boundary")
            repo.write(
                "UPDATE BROWSER_CONTEXT SET last_business_at=:now,manual_released_at=NULL "
                "WHERE context_id=:id",
                now=now,
                id=context_id,
            )
            service.context(
                register,
                "STAFF_A",
                resume,
                now + timedelta(hours=24) - timedelta(microseconds=1),
            )
            fails(
                409,
                lambda: service.context(register, "STAFF_A", resume, now + timedelta(hours=24)),
            )
            repo.write(
                "UPDATE BROWSER_CONTEXT SET manual_released_at=:now WHERE context_id=:id",
                now=now + timedelta(hours=24),
                id=context_id,
            )
            service.context(register, "STAFF_A", resume, now + timedelta(hours=24))
            ok("DB-backed resume 24h boundary and manual-release origin remain distinct")
            # Expired lock and lower rolling-window endpoint use a fixed DB-origin timestamp.
            failure_time = (now - timedelta(minutes=10)).isoformat() + "Z"
            repo.limit("M2_TIME_FIXTURE")
            repo.save_limit("M2_TIME_FIXTURE", json.dumps([failure_time]), None)
            repo.now = lambda: now
            service.login("M2_TIME_FIXTURE", "not-a-stored-password", resume)
            row = repo.limit("M2_TIME_FIXTURE")
            assert len(json.loads(row["failure_times"])) == 1
            repo.save_limit("M2_TIME_FIXTURE", row["failure_times"], now)
            service.login("M2_TIME_FIXTURE", "not-a-stored-password", resume)
            assert len(json.loads(repo.limit("M2_TIME_FIXTURE")["failure_times"])) == 1
            ok("DB-backed login window excludes exact lower endpoint and lock releases at deadline")
            # Corrupt/missing links must stop. All mutations here are rolled back.
            repo.write("UPDATE REGISTER SET current_cart_id=NULL WHERE register_id=1")
            fails(503, lambda: service.get_cart(auth, resume, create=True))
            repo.write(
                "UPDATE REGISTER SET current_cart_id=:id WHERE register_id=1",
                id=register["current_cart_id"],
            )
            repo.write(
                "UPDATE CART SET staff_id=:staff WHERE cart_id=:id",
                staff="STAFF_B",
                id=register["current_cart_id"],
            )
            fails(403, lambda: service.get_cart(auth, resume))
            ok("inconsistent pointer and cart owner rejected without replacement")
        finally:
            tx.rollback()
    engine.dispose()
    # A real row lock must cause a bounded 503 and must not count a credential failure.
    missing = "M2_LOCK_TIMEOUT"
    with connect() as holder:
        with holder.cursor() as cursor:
            cursor.execute("SELECT register_id FROM REGISTER WHERE register_id=1 FOR UPDATE")
            result = Client().login(missing, password="not-a-stored-password")
            assert result[0] == 503
        holder.rollback()
    with connect() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM AUTH_LOGIN_LIMIT WHERE staff_id=%s", (missing,))
        assert cursor.fetchone()[0] == 0
    ok("real REGISTER lock timeout returns 503 without failed-login record or replay")
    configure("pos_app")
    engine = create_database(Settings.from_env())
    try:
        with transaction(engine, readonly=True) as reader:
            before = reader.execute(
                text("SELECT maintenance_hold FROM REGISTER WHERE register_id=1")
            ).scalar_one()
            assert before == 0
            with connect() as writer:
                with writer.cursor() as cursor:
                    cursor.execute(
                        "UPDATE REGISTER SET maintenance_hold=TRUE "
                        "WHERE register_id=1 AND maintenance_hold=FALSE"
                    )
                    assert cursor.rowcount == 1
                writer.commit()
            during = reader.execute(
                text("SELECT maintenance_hold FROM REGISTER WHERE register_id=1")
            ).scalar_one()
            assert during == before
        with transaction(engine, readonly=True) as reader:
            assert (
                reader.execute(
                    text("SELECT maintenance_hold FROM REGISTER WHERE register_id=1")
                ).scalar_one()
                == 1
            )
        ok("two SELECTs share repeatable-read snapshot while another connection commits")
    finally:
        with connect() as writer:
            with writer.cursor() as cursor:
                cursor.execute(
                    "UPDATE REGISTER SET maintenance_hold=FALSE "
                    "WHERE register_id=1 AND maintenance_hold=TRUE"
                )
            writer.commit()
        engine.dispose()
    # Confirm rollback fixtures did not persist and ordinary cart count remains one.
    with connect() as conn, conn.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM AUTH_LOGIN_LIMIT WHERE staff_id=%s",
            ("M2_TIME_FIXTURE",),
        )
        assert cursor.fetchone()[0] == 0
        cursor.execute("SELECT COUNT(*) FROM CART")
        assert cursor.fetchone()[0] == 1
        cursor.execute("SELECT starting_staff_id FROM BROWSER_CONTEXT")
        assert cursor.fetchone()[0] == "STAFF_A"
    ok("rolled-back test fixtures leave original context and cart intact")
    (ROOT / "docs/implementation/evidence/m2/mysql-transactions.json").write_text(
        json.dumps(results, indent=2) + "\n"
    )
    print(json.dumps({"passed": len(results), "failed": 0}))


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
