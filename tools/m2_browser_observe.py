"""Read-only snapshots of the dedicated M2 browser DB; never read Cookie hashes."""

import argparse
import json

from m2_local_db import connect
from m2_local_profile import EVIDENCE, PROFILE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("initial", "after_reload", "after_restart"))
    phase = parser.parse_args().phase
    if PROFILE not in ("browser", "mac"):
        raise ValueError("Only the dedicated browser profiles can be observed")
    identity = json.loads((EVIDENCE / "mysql-environment.json").read_text())
    target = EVIDENCE / f"cart-{phase}.json"
    if target.exists():
        raise ValueError("Evidence already exists; inspect instead of overwriting")
    with connect("pos_app") as conn, conn.cursor() as cursor:
        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")
        cursor.execute("SELECT @@hostname, DATABASE(), UTC_TIMESTAMP(6)")
        hostname, database, observed_at = cursor.fetchone()
        if hostname != identity["container_id"][:12] or database != "pos_validation":
            raise ValueError("Unexpected database identity")
        cursor.execute(
            "SELECT r.start_state, r.maintenance_hold, r.active_context_id, r.current_cart_id, "
            "b.starting_staff_id, b.confirmed_at, b.last_business_at, b.manual_released_at, "
            "b.invalidated_at, c.context_id, c.staff_id, c.state, c.version, c.member_state, "
            "c.subtotal, c.total, c.created_at, c.updated_at "
            "FROM REGISTER r "
            "LEFT JOIN BROWSER_CONTEXT b ON b.context_id=r.active_context_id "
            "LEFT JOIN CART c ON c.cart_id=r.current_cart_id WHERE r.register_id=1"
        )
        columns = [column[0] for column in cursor.description]
        row = cursor.fetchone()
        state = dict(zip(columns, row, strict=True))
        counts = {}
        for table in ("BROWSER_CONTEXT", "CART", "CART_LINE", "CART_OPERATION", "PURCHASE"):
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            counts[table] = cursor.fetchone()[0]
        conn.rollback()
    valid = (
        state["start_state"] == "READY"
        and state["maintenance_hold"] == 0
        and state["active_context_id"] == state["context_id"]
        and state["current_cart_id"] is not None
        and state["starting_staff_id"] == state["staff_id"] == "STAFF_A"
        and state["state"] == "EDITING"
        and state["member_state"] == "UNSPECIFIED"
        and state["confirmed_at"] is not None
        and state["invalidated_at"] is None
        and state["subtotal"] == state["total"] == 0
        and counts
        == {"BROWSER_CONTEXT": 1, "CART": 1, "CART_LINE": 0, "CART_OPERATION": 0, "PURCHASE": 0}
    )
    result = {
        "phase": phase,
        "observed_at_utc": str(observed_at),
        "state": state,
        "counts": counts,
        "valid_empty_cart": valid,
    }
    # String conversion makes timestamps/decimal yen reproducible without credentials.
    result = json.loads(json.dumps(result, default=str))
    if phase != "initial":
        initial = json.loads((EVIDENCE / "cart-initial.json").read_text())
        result["matches_initial"] = (
            result["state"] == initial["state"] and counts == initial["counts"]
        )
    with target.open("x") as output:
        output.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))
    if not valid or result.get("matches_initial", True) is not True:
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"stopped": True, "error_type": type(exc).__name__}))
        raise SystemExit(1) from None
