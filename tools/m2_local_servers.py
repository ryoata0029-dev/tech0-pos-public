"""Launch/stop only M2 HTTPS processes, with environment secrets held off the command line."""

import argparse
import json
import os
import signal
import socket
import subprocess
import time

from m2_local_db import configure
from m2_local_profile import BACKEND_PORT, FRONTEND_PORT, LOCAL, PROFILE, ROOT


def main():
    action = argparse.ArgumentParser()
    action.add_argument("action", choices=["start", "stop"])
    if action.parse_args().action == "stop":
        records = json.loads((LOCAL / "processes.json").read_text())
        if PROFILE in ("parallel-mac-next", "oct05-mac"):
            expected = {
                "frontend": (
                    FRONTEND_PORT,
                    f"--pos-harness-profile {PROFILE} --pos-harness-port {FRONTEND_PORT}",
                ),
                "backend": (BACKEND_PORT, str(LOCAL / "tls/server.key")),
            }
            if len(records) != 2 or {row.get("name") for row in records} != set(expected):
                raise RuntimeError("Dedicated Mac process records required; not stopping")
            for record in records:
                port, marker = expected[record["name"]]
                if (
                    record.get("profile") != PROFILE
                    or record.get("port") != port
                    or record.get("marker") != marker
                ):
                    raise RuntimeError("Dedicated Mac process identity mismatch; not stopping")
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
        for port in (FRONTEND_PORT, BACKEND_PORT):
            with socket.socket() as sock:
                sock.settimeout(1)
                if sock.connect_ex(("127.0.0.1", port)) == 0:
                    raise RuntimeError("Process still listening")
        print("M2 HTTPS processes stopped; neither port accepts connections.")
        return
    for port in (FRONTEND_PORT, BACKEND_PORT):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", port))
    if (
        PROFILE
        in (
            "browser",
            "mac",
            "mac-flow",
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
        )
        and not (LOCAL / "public-origin.txt").is_file()
    ):
        raise RuntimeError("Browser profile requires its fixed public origin before startup")
    configure("pos_app")
    env = dict(os.environ)
    env.update(
        POS_BACKEND_URL=f"https://127.0.0.1:{BACKEND_PORT}",
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
                "oct05_backend:app"
                if PROFILE == "oct05-mac"
                else "mac_tc02_backend:app"
                if PROFILE
                in (
                    "mac-tc02",
                    "mac-batch",
                    "mac-parallel",
                    "parallel-next",
                    "parallel-mac-next",
                    "oct05-mac",
                )
                else "mac_recovery_backend:app"
                if PROFILE
                in (
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
                )
                else "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(BACKEND_PORT),
                "--ssl-keyfile",
                str(LOCAL / "tls/server.key"),
                "--ssl-certfile",
                str(LOCAL / "tls/server.crt"),
                "--no-access-log",
            ],
            ROOT / "backend",
            str(BACKEND_PORT),
        ),
        (
            "frontend",
            [
                str(node),
                str(
                    ROOT
                    / (
                        "tools/mac_flow_https.mjs"
                        if PROFILE
                        in (
                            "mac-flow",
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
                        )
                        else "tools/m2_https.mjs"
                    )
                ),
            ],
            ROOT,
            "mac_flow_https.mjs"
            if PROFILE
            in (
                "mac-flow",
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
            )
            else "m2_https.mjs",
        ),
    ]
    records = []
    if PROFILE in (
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
        env["PYTHONPATH"] = str(ROOT / "tools") + os.pathsep + str(ROOT / "backend")
    for name, command, cwd, marker in commands:
        if PROFILE in ("parallel-mac-next", "oct05-mac") and name == "frontend":
            command += ["--pos-harness-profile", PROFILE, "--pos-harness-port", str(FRONTEND_PORT)]
            marker = f"--pos-harness-profile {PROFILE} --pos-harness-port {FRONTEND_PORT}"
        elif PROFILE in ("parallel-mac-next", "oct05-mac") and name == "backend":
            marker = str(LOCAL / "tls/server.key")
        with (LOCAL / f"{name}.log").open("a") as log:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                start_new_session=True,
                stdout=log,
                stderr=log,
            )
        records.append(
            {
                "name": name,
                "pid": process.pid,
                "marker": marker,
                "profile": PROFILE,
                "port": FRONTEND_PORT if name == "frontend" else BACKEND_PORT,
            }
        )
    (LOCAL / "processes.json").write_text(json.dumps(records))
    print(
        f"Started M2 HTTPS processes; frontend localhost:{FRONTEND_PORT}, "
        f"backend 127.0.0.1:{BACKEND_PORT}."
    )


if __name__ == "__main__":
    main()
