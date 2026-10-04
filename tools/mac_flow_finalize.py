"""Offline business-evidence assertions plus read-only Mac-flow shutdown checks."""

import hashlib
import json
import socket
import subprocess

from m2_local_profile import EVIDENCE, LOCAL, NAME, PROFILE, ROOT, VOLUME


def main():
    if PROFILE != "mac-flow":
        raise ValueError("Mac-flow only")
    final = json.loads((EVIDENCE / "db-final.json").read_text())
    carts = final["carts"]
    assert len(carts) == len(final["purchases"]) == 2
    assert [cart["state"] for cart in carts] == ["CLOSED", "SAVED"]
    assert final["register"][0]["current_cart_id"] == carts[1]["cart_id"]
    assert len(final["purchase_lines"]) == 6 and len(final["purchase_taxes"]) == 4
    for cart, expected, subtotal, member, discount, tax10 in zip(
        carts, (537, 570), (493, 523), ("MEMBER_0", None), (10, 0), (27, 30), strict=True
    ):
        purchase = next(p for p in final["purchases"] if p["cart_id"] == cart["cart_id"])
        assert purchase["staff_id"] == "STAFF_A" and purchase["member_id"] == member
        assert int(purchase["subtotal"]) == subtotal and int(purchase["total"]) == expected
        lines = [p for p in final["purchase_lines"] if p["cart_id"] == cart["cart_id"]]
        assert sorted((p["product_id"], p["quantity"]) for p in lines) == [(1, 3), (2, 1), (3, 1)]
        first = next(p for p in lines if p["product_id"] == 1)
        assert first["unit_price_snapshot"] == "103" and first["tax_rate_snapshot"] == "0.1000"
        assert int(first["discount_per_unit"]) == discount
        taxes = [p for p in final["purchase_taxes"] if p["cart_id"] == cart["cart_id"]]
        assert sorted(int(t["tax_amount"]) for t in taxes) == sorted((17, tax10))
    next_ops = [o for o in final["operations"] if o["kind"] == "NEXT"]
    assert len(next_ops) == 1 and next_ops[0]["status"] == "APPLIED"
    assert next_ops[0]["next_cart_id"] == carts[1]["cart_id"]
    assert final["products"][0]["unit_price"] == "500"
    assert final["products"][0]["tax_rate_id"] == 1
    before = json.loads((EVIDENCE / "db-nonmember-before-master.json").read_text())
    lost = json.loads((EVIDENCE / "db-next-response-lost.json").read_text())
    assert lost["carts"] == carts and lost["purchases"] == final["purchases"]
    assert before["lines"] == final["lines"]
    ports = {}
    for port in (3307, 8443, 8444):
        with socket.socket() as sock:
            sock.settimeout(1)
            ports[str(port)] = sock.connect_ex(("127.0.0.1", port)) != 0
    assert all(ports.values())
    state = subprocess.check_output(
        ["docker", "inspect", "--format", "{{.State.Status}}", NAME], text=True
    ).strip()
    assert state == "exited"
    subprocess.check_output(["docker", "volume", "inspect", VOLUME])
    tunnel_pid = str(json.loads((LOCAL / "tunnel-process.json").read_text())["pid"])
    current = subprocess.run(["ps", "-p", tunnel_pid, "-o", "command="], capture_output=True)
    assert current.returncode != 0 or b"cloudflared" not in current.stdout
    paths = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
    ).split(b"\0")
    assert not any(b".mac-flow-local/" in path for path in paths)
    secrets = [v.encode() for v in json.loads((LOCAL / "secrets.json").read_text()).values()]
    for path in paths:
        if path and (ROOT / path.decode()).is_file():
            content = (ROOT / path.decode()).read_bytes()
            assert not any(v in content for v in secrets), "Secret in Git candidate"
    for path in (LOCAL / "backend.log", LOCAL / "frontend.log", LOCAL / "tunnel.log"):
        assert not any(v in path.read_bytes() for v in secrets), "Secret in private app log"
    proof = {
        "business_assertions": "passed",
        "member_total": 537,
        "nonmember_total": 570,
        "purchases": 2,
        "purchase_lines": 6,
        "purchase_tax_rows": 4,
        "normal_next_operations": 1,
        "failed_next_attempt_changed_business_state": False,
        "response_loss_fault_executed": False,
        "ports_closed": ports,
        "container_status": state,
        "volume_retained": VOLUME,
        "tunnel_stopped": True,
        "generated_secrets_absent_from_git_candidates_and_logs": True,
        "evidence_sha256": hashlib.sha256((EVIDENCE / "db-final.json").read_bytes()).hexdigest(),
    }
    (EVIDENCE / "verified-shutdown.json").write_text(json.dumps(proof, indent=2) + "\n")
    print(json.dumps(proof))


if __name__ == "__main__":
    main()
