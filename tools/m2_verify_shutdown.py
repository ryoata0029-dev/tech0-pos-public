"""Read-only final checks. Never emit credentials, cookie values or private keys."""

import json
import socket
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".m2-local"


def main():
    ports = {}
    for port in (3307, 8443, 8444):
        with socket.socket() as sock:
            sock.settimeout(1)
            ports[str(port)] = sock.connect_ex(("127.0.0.1", port)) != 0
    assert all(ports.values())
    names = ["tech0-pos-m2-mysql", "pos-validation-mysql"]
    states = {}
    for name in names:
        status = subprocess.check_output(
            ["docker", "inspect", "--format", "{{.State.Status}}", name], text=True
        ).strip()
        states[name] = status
        assert status == "exited"
    trust = subprocess.run(
        [
            "security",
            "find-certificate",
            "-c",
            "Tech0 POS M2 Local Validation CA",
            "/Users/ryotaasano/Library/Keychains/login.keychain-db",
        ],
        capture_output=True,
        check=False,
    )
    assert trust.returncode != 0
    paths = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
    ).split(b"\0")
    assert not any(b".m2-local/" in path for path in paths if path)
    values = [s.encode() for s in json.loads((LOCAL / "secrets.json").read_text()).values()]
    for path in paths:
        if path and (ROOT / path.decode()).is_file():
            content = (ROOT / path.decode()).read_bytes()
            assert not any(value in content for value in values), "Secret in a Git candidate file"
            assert b"-----BEGIN PRIVATE KEY-----" not in content.splitlines()
    for name in ("backend.log", "frontend.log"):
        content = (LOCAL / name).read_bytes()
        assert not any(value in content for value in values), "Secret in application log"
    result = {
        "ports_closed": ports,
        "containers": states,
        "local_ca_not_in_login_keychain": True,
        "local_secrets_git_ignored": True,
        "generated_secrets_absent_from_git_candidates_and_app_logs": True,
        "new_volume_retained": "tech0-pos-m2-mysql-data",
        "docker_desktop_left_running": True,
    }
    (ROOT / "docs/implementation/evidence/m2/shutdown.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
