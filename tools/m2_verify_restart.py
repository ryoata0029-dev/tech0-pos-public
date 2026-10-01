"""Stop/restart the named M2 container and verify outage classification and persistence."""

import json
import subprocess
import time

from m2_local_db import ROOT, connect
from m2_verify_https import Client

NAME = "tech0-pos-m2-mysql"


def state():
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT start_state,maintenance_hold,active_context_id,current_cart_id,"
                "active_session_hash FROM REGISTER WHERE register_id=1"
            )
            register = cursor.fetchone()
            cursor.execute("SELECT context_id,token_hash,last_business_at FROM BROWSER_CONTEXT")
            contexts = cursor.fetchall()
            counts = []
            for table in ["AUTH_SESSION", "AUTH_LOGIN_LIMIT", "CART", "PURCHASE"]:
                cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
                counts.append(cursor.fetchone()[0])
    return register, contexts, counts


def main():
    info = json.loads(subprocess.check_output(["docker", "inspect", NAME], text=True))[0]
    assert info["Config"]["Labels"].get("purpose") == "tech0-pos-m2"
    assert info["HostConfig"]["PortBindings"]["3306/tcp"][0]["HostIp"] == "127.0.0.1"
    before = state()
    subprocess.run(["docker", "stop", "--timeout", "15", NAME], check=True, capture_output=True)
    try:
        for method, path, body in [
            ("GET", "auth/status", None),
            ("POST", "login", {"staff_id": "M2_OUTAGE", "password": "unused"}),
        ]:
            status, data, headers = Client().request(method, path, body)
            assert status == 503 and data["code"] == "SERVICE_UNAVAILABLE"
            assert not headers
        print(
            "Database outage returns sanitized 503; no authentication cookies issued.", flush=True
        )
    finally:
        subprocess.run(["docker", "start", NAME], check=True, capture_output=True)
    for attempt in range(30):
        try:
            after = state()
            break
        except Exception:
            if attempt == 29:
                raise
            time.sleep(1)
    assert before == after
    assert Client().request("GET", "auth/status")[0] == 401
    result = {
        "outage_status": 503,
        "no_cookie_issued": True,
        "restart_preserved_state": True,
        "post_restart_unauthenticated_status": 401,
        "container": NAME,
    }
    (ROOT / "docs/implementation/evidence/m2/mysql-restart.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(json.dumps(result))


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
