"""Start/stop this approved Mac-only temporary tunnel using the existing vendor CLI."""

import argparse
import json
import os
import re
import signal
import subprocess
import time

from m2_local_profile import FRONTEND_PORT, LOCAL, PROFILE, ROOT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("start", "stop"))
    action = parser.parse_args().action
    if PROFILE not in (
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
    ):
        raise ValueError("Mac-flow only")
    binary = ROOT / ".m2-local/bin/cloudflared"
    record = LOCAL / "tunnel-process.json"
    if action == "stop":
        saved = json.loads(record.read_text())
        if PROFILE in ("parallel-mac-next", "oct05-mac") and (
            saved.get("profile") != PROFILE or saved.get("port") != FRONTEND_PORT
        ):
            raise ValueError("Dedicated Mac tunnel identity mismatch")
        pid = saved["pid"]
        current = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True
        )
        if current.returncode == 0:
            if str(binary) not in current.stdout or str(LOCAL / "tls/ca.crt") not in current.stdout:
                raise ValueError("Tunnel PID mismatch")
            os.killpg(pid, signal.SIGTERM)
        print("Mac-only tunnel stopped.")
        return
    if record.exists() or (LOCAL / "public-origin.txt").exists():
        raise ValueError("Do not overwrite a prior tunnel")
    with (LOCAL / "tunnel.log").open("x") as log:
        process = subprocess.Popen(
            [
                str(binary),
                "tunnel",
                "--url",
                f"https://localhost:{FRONTEND_PORT}",
                "--origin-ca-pool",
                str(LOCAL / "tls/ca.crt"),
                "--no-autoupdate",
                "--protocol",
                "http2",
            ],
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    record.write_text(json.dumps({"pid": process.pid, "profile": PROFILE, "port": FRONTEND_PORT}))
    for _ in range(25):
        match = re.search(
            r"https://[a-z0-9-]+\.trycloudflare\.com",
            (LOCAL / "tunnel.log").read_text(),
        )
        if match:
            (LOCAL / "public-origin.txt").write_text(match.group() + "\n")
            print(json.dumps({"origin": match.group(), "origin_tls_verification": True}))
            return
        if process.poll() is not None:
            raise ValueError("Tunnel exited before URL assignment")
        time.sleep(1)
    raise ValueError("Tunnel did not assign a URL; process retained for inspection")


if __name__ == "__main__":
    main()
