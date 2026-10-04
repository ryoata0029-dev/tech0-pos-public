"""Named Mac-recovery gates, snapshots and process metadata. No browser interaction."""

import argparse
import json
import os
import socket
import subprocess
from datetime import UTC, datetime

os.environ.setdefault("M2_LOCAL_PROFILE", "mac-recovery")
from m2_local_profile import (  # noqa: E402
    BACKEND_PORT,
    EVIDENCE,
    FRONTEND_PORT,
    LOCAL,
    MYSQL_PORT,
    NAME,
    PROFILE,
    ROOT,
    VOLUME,
)

if PROFILE not in (
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
    raise ValueError("Dedicated Mac recovery profiles only")


def chrome_processes():
    rows = subprocess.check_output(["ps", "-axo", "pid=,comm="], text=True).splitlines()
    return [row.strip() for row in rows if "/Google Chrome.app/" in row]


def run(tool, *args):
    subprocess.run(
        [str(ROOT / "backend/.venv/bin/python"), str(ROOT / "tools" / tool), *args],
        check=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=(
            "snapshot",
            "arm",
            "release",
            "chrome-before",
            "chrome-stopped",
            "shutdown",
            "restart-servers",
            "stop-servers",
            "change-price",
        ),
    )
    parser.add_argument("--tag", required=True)
    parser.add_argument(
        "--kind",
        choices=(
            "member-unavailable",
            "member-late",
            "product-late",
            "product-unavailable",
            "product-late-missing",
            "product-late-unavailable",
            "purchase-hold",
            "purchase",
            "next",
        ),
    )
    args = parser.parse_args()
    tag = args.tag
    if not tag.replace("-", "").isalnum():
        raise ValueError("Unsafe tag")
    if args.action == "snapshot":
        run("mac_flow_db.py", "snapshot", "--stage", tag)
    elif args.action == "change-price":
        run("mac_flow_db.py", "change-price")
    elif args.action == "arm":
        kind = args.kind
        if not kind:
            raise ValueError("Fault kind required")
        control = LOCAL / (
            "backend-gate.json"
            if kind in ("member-unavailable", "member-late", "purchase-hold")
            else "product-gate.json"
            if kind.startswith("product-")
            else "drop-response.json"
        )
        if kind.startswith("product-") and PROFILE not in (
            "mac-tc02",
            "mac-batch",
            "mac-parallel",
            "parallel-next",
            "parallel-mac-next",
            "oct05-mac",
        ):
            raise ValueError("Product lookup gates are limited to Mac TC-02")
        if kind in (
            "product-late-missing",
            "product-late-unavailable",
        ) and PROFILE not in (
            "mac-batch",
            "mac-parallel",
            "parallel-next",
            "parallel-mac-next",
            "oct05-mac",
        ):
            raise ValueError("Additional reply gates are limited to the fresh Mac batch")
        if kind == "member-late" and PROFILE not in (
            "mac-tc03",
            "mac-tc03-fix",
            "mac-batch",
            "mac-parallel",
            "parallel-next",
            "parallel-mac-next",
            "oct05-mac",
        ):
            raise ValueError("Member lookup hold is limited to the current TC-03 trial")
        if (
            control.exists()
            or any(EVIDENCE.glob(f"*{tag}*"))
            or (LOCAL / f"release-{tag}.json").exists()
        ):
            raise ValueError("An unused gate/tag is required")
        with control.open("x") as output:
            json.dump({"kind": kind, "tag": tag}, output)
        print(json.dumps({"armed": kind, "tag": tag}))
    elif args.action == "release":
        if not (EVIDENCE / f"gate-{tag}.json").exists():
            raise ValueError("Gate must actually be reached")
        with (LOCAL / f"release-{tag}.json").open("x") as output:
            json.dump({"tag": tag}, output)
        print(json.dumps({"released": tag}))
    elif args.action.startswith("chrome-"):
        processes = chrome_processes()
        if args.action == "chrome-stopped" and processes:
            raise ValueError("Chrome processes still exist")
        if args.action == "chrome-before" and not processes:
            raise ValueError("Chrome is not running")
        evidence = {
            "tag": tag,
            "phase": args.action,
            "at_utc": datetime.now(UTC).isoformat(),
            "processes": processes,
            "complete_process_stop": not processes,
        }
        with (EVIDENCE / f"{args.action}-{tag}.json").open("x") as output:
            json.dump(evidence, output, indent=2)
        print(json.dumps({"phase": args.action, "tag": tag, "process_count": len(processes)}))
    elif args.action == "stop-servers":
        run("m2_local_servers.py", "stop")
    elif args.action == "restart-servers":
        run("m2_local_servers.py", "stop")
        run("m2_local_servers.py", "start")
    else:
        if PROFILE in ("parallel-mac-next", "oct05-mac"):
            identity = json.loads((EVIDENCE / "mysql-environment.json").read_text())
            actual_id = subprocess.check_output(
                ["docker", "inspect", "--format", "{{.Id}}", NAME], text=True
            ).strip()
            if identity.get("container") != NAME or identity.get("container_id") != actual_id:
                raise ValueError("Dedicated Mac container identity mismatch; not stopping")
        run("mac_flow_tunnel.py", "stop")
        run("m2_local_servers.py", "stop")
        subprocess.run(["docker", "stop", NAME], check=True)
        state = subprocess.check_output(
            ["docker", "inspect", "--format", "{{.State.Status}}", NAME], text=True
        ).strip()
        assert state == "exited"
        subprocess.check_output(["docker", "volume", "inspect", VOLUME])
        ports = {}
        for port in (MYSQL_PORT, FRONTEND_PORT, BACKEND_PORT):
            with socket.socket() as sock:
                sock.settimeout(1)
                ports[str(port)] = sock.connect_ex(("127.0.0.1", port)) != 0
        assert all(ports.values())
        secret_values = [
            v.encode() for v in json.loads((LOCAL / "secrets.json").read_text()).values()
        ]
        paths = subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
        ).split(b"\0")
        assert not any((LOCAL.name + "/").encode() in path for path in paths)
        for path in paths:
            if path and (ROOT / path.decode()).is_file():
                assert not any(v in (ROOT / path.decode()).read_bytes() for v in secret_values)
        for name in ("frontend.log", "backend.log", "tunnel.log"):
            assert not any(v in (LOCAL / name).read_bytes() for v in secret_values)
        with (EVIDENCE / f"shutdown-{tag}.json").open("x") as output:
            json.dump(
                {
                    "at_utc": datetime.now(UTC).isoformat(),
                    "profile": PROFILE,
                    "container": NAME,
                    "container_id": actual_id
                    if PROFILE in ("parallel-mac-next", "oct05-mac")
                    else None,
                    "ports_closed": ports,
                    "container_status": state,
                    "volume_retained": VOLUME,
                    "secrets_absent_from_git_candidates_and_logs": True,
                },
                output,
                indent=2,
            )
        print("Mac-recovery environment stopped; volume and evidence retained.")


if __name__ == "__main__":
    main()
