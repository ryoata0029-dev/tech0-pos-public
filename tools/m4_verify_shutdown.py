"""Read-only shutdown and secret-leak checks for the approved m4-only environment."""

import json
import socket
import subprocess

from m2_local_profile import EVIDENCE, LOCAL, NAME, PROFILE, ROOT, VOLUME


def main():
    if PROFILE != "m4":
        raise ValueError("Requires m4 profile")
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
    paths = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
    ).split(b"\0")
    assert not any(b".m4-local/" in path for path in paths)
    values = [s.encode() for s in json.loads((LOCAL / "secrets.json").read_text()).values()]
    values += [s.encode() for s in json.loads((LOCAL / "client-cookies.json").read_text()).values()]
    for path in paths:
        if path and (ROOT / path.decode()).is_file():
            content = (ROOT / path.decode()).read_bytes()
            assert not any(value in content for value in values), "Secret in Git candidate"
    for path in (
        LOCAL / "backend.log",
        LOCAL / "frontend.log",
        EVIDENCE / "live.log",
        EVIDENCE / "supplement.log",
        EVIDENCE / "fault-races.json",
    ):
        content = path.read_bytes()
        assert not any(value in content for value in values), "Secret in test/application output"
    result = {
        "ports_closed": ports,
        "container_status": state,
        "volume_retained": VOLUME,
        "secrets_git_ignored": True,
        "secrets_absent_from_git_candidates_and_logs": True,
        "docker_desktop_left_running": True,
    }
    (EVIDENCE / "shutdown.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
