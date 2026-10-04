"""Read-only checks for the single fresh October 5 environment."""

import hashlib
import json
import socket
import subprocess
from datetime import UTC, datetime

from m2_local_profile import (
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


def verify(tag):
    if PROFILE != "oct05-mac" or not tag.replace("-", "").isalnum():
        raise ValueError("Only the fixed October 5 environment and an unused tag are allowed")
    destination = EVIDENCE / f"environment-{tag}.json"
    if destination.exists():
        raise ValueError("Evidence exists; not overwriting")
    created = json.loads((EVIDENCE / "mysql-environment.json").read_text())
    info = json.loads(subprocess.check_output(["docker", "inspect", NAME], text=True))[0]
    assert created["container_id"] == info["Id"]
    assert info["State"]["Status"] == "running"
    assert any(m.get("Name") == VOLUME for m in info["Mounts"])
    ports = {}
    for port in (MYSQL_PORT, FRONTEND_PORT, BACKEND_PORT):
        with socket.socket() as sock:
            sock.settimeout(1)
            ports[str(port)] = sock.connect_ex(("127.0.0.1", port)) == 0
    assert all(ports.values())
    records = json.loads((LOCAL / "processes.json").read_text())
    assert len(records) == 2 and {r["name"] for r in records} == {"frontend", "backend"}
    for record in records:
        expected_port = FRONTEND_PORT if record["name"] == "frontend" else BACKEND_PORT
        assert record["profile"] == PROFILE and record["port"] == expected_port
        command = subprocess.check_output(
            ["ps", "-p", str(record["pid"]), "-o", "command="], text=True
        )
        assert record["marker"] in command
    tunnel = json.loads((LOCAL / "tunnel-process.json").read_text())
    assert tunnel["profile"] == PROFILE and tunnel["port"] == FRONTEND_PORT
    tunnel_command = subprocess.check_output(
        ["ps", "-p", str(tunnel["pid"]), "-o", "command="], text=True
    )
    assert str(LOCAL / "tls/ca.crt") in tunnel_command
    origin = (LOCAL / "public-origin.txt").read_text().strip()
    assert origin.startswith("https://") and origin.endswith(".trycloudflare.com")
    prior = ROOT / "docs/implementation/evidence/parallel-next"
    expected = json.loads((prior / "application-source-manifest.json").read_text())[
        "application_sha256"
    ]
    expected.update(json.loads((prior / "runtime-start.json").read_text())["source_sha256"])
    actual = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in expected}
    assert actual == expected
    build = (ROOT / "frontend/.next/BUILD_ID").read_text().strip()
    assert build == "5_wgTZOtPLE3as7vfiFAN"
    secret_values = [v.encode() for v in json.loads((LOCAL / "secrets.json").read_text()).values()]
    candidates = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
    ).split(b"\0")
    assert not any((LOCAL.name + "/").encode() in candidate for candidate in candidates)
    for candidate in candidates:
        if candidate and (ROOT / candidate.decode()).is_file():
            assert not any(v in (ROOT / candidate.decode()).read_bytes() for v in secret_values)
    for name in ("frontend.log", "backend.log", "tunnel.log"):
        assert not any(v in (LOCAL / name).read_bytes() for v in secret_values)
    data = {
        "at_utc": datetime.now(UTC).isoformat(),
        "profile": PROFILE,
        "container": NAME,
        "container_id": info["Id"],
        "volume": VOLUME,
        "ports_open": ports,
        "runtime_identities_checked": True,
        "origin": origin,
        "build_id": build,
        "application_source_files": len(actual),
        "application_sha256": actual,
        "source_equal_to_previously_verified_build": True,
        "secrets_absent_from_git_candidates_and_logs": True,
        "full_application_suite_rerun_by_this_command": False,
    }
    with destination.open("x") as output:
        json.dump(data, output, indent=2)
    print(json.dumps({k: v for k, v in data.items() if k != "application_sha256"}))
