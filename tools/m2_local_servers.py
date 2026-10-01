"""Launch/stop only M2 HTTPS processes, with environment secrets held off the command line."""

import argparse
import json
import os
import signal
import socket
import subprocess
import time

from m2_local_db import configure
from m2_local_profile import LOCAL, PROFILE, ROOT


def main():
    action = argparse.ArgumentParser()
    action.add_argument("action", choices=["start", "stop"])
    if action.parse_args().action == "stop":
        records = json.loads((LOCAL / "processes.json").read_text())
        for record in records:
            current = subprocess.run(
                ["ps", "-p", str(record["pid"]), "-o", "command="],
                text=True,
                capture_output=True,
            )
            if current.returncode == 0:
                if record["marker"] not in current.stdout:
                    raise RuntimeError("PID identity mismatch; not stopping")
                os.killpg(record["pid"], signal.SIGTERM)
        time.sleep(1)
        for port in (8443, 8444):
            with socket.socket() as sock:
                sock.settimeout(1)
                if sock.connect_ex(("127.0.0.1", port)) == 0:
                    raise RuntimeError("Process still listening")
        print("M2 HTTPS processes stopped; neither port accepts connections.")
        return
    for port in (8443, 8444):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", port))
    if PROFILE in ("browser", "mac") and not (LOCAL / "public-origin.txt").is_file():
        raise RuntimeError("Browser profile requires its fixed public origin before startup")
    configure("pos_app")
    env = dict(os.environ)
    env.update(
        POS_BACKEND_URL="https://127.0.0.1:8444",
        NODE_EXTRA_CA_CERTS=str(LOCAL / "tls/ca.crt"),
        NEXT_TELEMETRY_DISABLED="1",
        M2_LOCAL_PROFILE=PROFILE,
    )
    node = ROOT / ".m0-cache/fnm/node-versions/v24.21.0/installation/bin/node"
    commands = [
        (
            "backend",
            [
                str(ROOT / "backend/.venv/bin/python"),
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8444",
                "--ssl-keyfile",
                str(LOCAL / "tls/server.key"),
                "--ssl-certfile",
                str(LOCAL / "tls/server.crt"),
                "--no-access-log",
            ],
            ROOT / "backend",
            "8444",
        ),
        (
            "frontend",
            [str(node), str(ROOT / "tools/m2_https.mjs")],
            ROOT,
            "m2_https.mjs",
        ),
    ]
    records = []
    for name, command, cwd, marker in commands:
        with (LOCAL / f"{name}.log").open("a") as log:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                start_new_session=True,
                stdout=log,
                stderr=log,
            )
        records.append({"name": name, "pid": process.pid, "marker": marker})
    (LOCAL / "processes.json").write_text(json.dumps(records))
    print("Started M2 HTTPS processes; frontend localhost:8443, backend 127.0.0.1:8444.")


if __name__ == "__main__":
    main()
