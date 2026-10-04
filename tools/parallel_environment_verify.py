"""Read-only identity/port/build evidence for exactly the two continuation runtimes."""

import argparse
import hashlib
import json
import re
import socket
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {"parallel-next": (3307, 8443, 8444), "parallel-mac-next": (3317, 8453, 8454)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument(
        "--phone-only",
        action="store_true",
        help="Check the waiting phone runtime after the Mac trial has stopped",
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.tag):
        raise ValueError("Unsafe tag")
    output = ROOT / "docs/implementation/evidence/parallel-next" / f"environments-{args.tag}.json"
    if output.exists():
        raise ValueError("Existing evidence must be retained")
    targets = {"parallel-next": TARGETS["parallel-next"]} if args.phone_only else TARGETS
    result = {"at_utc": datetime.now(UTC).isoformat(), "phase": args.tag, "targets": {}}
    for profile, ports in targets.items():
        local = ROOT / f".{profile}-local"
        evidence = ROOT / "docs/implementation/evidence" / profile
        name = f"tech0-pos-{profile}-mysql"
        saved = json.loads((evidence / "mysql-environment.json").read_text())
        actual = json.loads(subprocess.check_output(["docker", "inspect", name], text=True))[0]
        if actual["Id"] != saved["container_id"] or actual["Name"] != "/" + name:
            raise ValueError("Wrong fixed container identity")
        if not actual["State"]["Running"]:
            raise ValueError("Expected continuation container running")
        if actual["NetworkSettings"]["Ports"]["3306/tcp"] != [
            {"HostIp": "127.0.0.1", "HostPort": str(ports[0])}
        ]:
            raise ValueError("Wrong fixed port binding")
        opened = {}
        for port in ports:
            with socket.socket() as sock:
                sock.settimeout(1)
                opened[str(port)] = sock.connect_ex(("127.0.0.1", port)) == 0
        if not all(opened.values()):
            raise ValueError("Expected private ports open")
        processes = json.loads((local / "processes.json").read_text())
        checked = []
        for process in processes:
            command = subprocess.check_output(
                ["ps", "-p", str(process["pid"]), "-o", "command="], text=True
            ).strip()
            if process["marker"] not in command:
                raise ValueError("Owned process identity mismatch")
            if profile == "parallel-next" and "--pos-harness-profile parallel-mac-next" in command:
                raise ValueError("Phone record points to Mac process")
            if process["name"] == "backend" and str(local / "tls/server.key") not in command:
                raise ValueError("Backend TLS identity mismatch")
            checked.append({"name": process["name"], "pid": process["pid"], "command": command})
        tunnel = json.loads((local / "tunnel-process.json").read_text())
        command = subprocess.check_output(
            ["ps", "-p", str(tunnel["pid"]), "-o", "command="], text=True
        ).strip()
        if (
            str(local / "tls/ca.crt") not in command
            or f"https://localhost:{ports[1]}" not in command
        ):
            raise ValueError("Owned tunnel identity mismatch")
        result["targets"][profile] = {
            "container": name,
            "container_id": actual["Id"],
            "status": "running",
            "ports_open": opened,
            "processes": checked,
            "tunnel_pid": tunnel["pid"],
            "origin": (local / "public-origin.txt").read_text().strip(),
        }
        if args.phone_only:
            secret_values = [
                v.encode() for v in json.loads((local / "secrets.json").read_text()).values()
            ]
            paths = subprocess.check_output(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
            ).split(b"\0")
            if any(path.startswith((local.name + "/").encode()) for path in paths):
                raise ValueError("Private continuation files entered Git candidates")
            for path in paths:
                candidate = ROOT / path.decode()
                if (
                    path
                    and candidate.is_file()
                    and any(v in candidate.read_bytes() for v in secret_values)
                ):
                    raise ValueError("Private value found in Git candidate")
            for name in ("frontend.log", "backend.log", "tunnel.log"):
                if any(v in (local / name).read_bytes() for v in secret_values):
                    raise ValueError("Private value found in runtime log")
            result["targets"][profile]["secrets_absent_from_git_candidates_and_logs"] = True
    result["build_id"] = (ROOT / "frontend/.next/BUILD_ID").read_text().strip()
    result["build_manifest_sha256"] = hashlib.sha256(
        (ROOT / "frontend/.next/build-manifest.json").read_bytes()
    ).hexdigest()
    with output.open("x") as stream:
        json.dump(result, stream, indent=2)
    print(
        json.dumps(
            {
                "phase": args.tag,
                "checked_profiles": list(targets),
                "checked_environments_running": True,
                "build_id": result["build_id"],
            }
        )
    )


if __name__ == "__main__":
    main()
