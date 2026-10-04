"""Fresh, named Mac recovery setup only; retain all resources on failure."""

import os
import subprocess
import time

from m2_local_profile import EVIDENCE, LOCAL, PROFILE, ROOT


def main(*, prepared=False):
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
        raise ValueError("Mac-recovery only")
    python = ROOT / "backend/.venv/bin/python"

    def run(tool, *args):
        subprocess.run([str(python), str(ROOT / "tools" / tool), *args], check=True)

    if prepared:
        if EVIDENCE.exists() or not all(
            (LOCAL / path).is_file()
            for path in (
                "secrets.json",
                "mysql-root",
                "tls/ca.crt",
                "tls/server.crt",
                "tls/server.key",
            )
        ):
            raise ValueError("Only a fresh prepare interrupted before MySQL may continue")
    else:
        run("m2_local_prepare.py")
    run("m2_local_mysql.py")
    for _ in range(40):
        ready = subprocess.run(
            [str(python), str(ROOT / "tools/m2_local_db.py"), "ready"],
            stdout=subprocess.DEVNULL,
        )
        if ready.returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError("MySQL readiness timeout; resources retained")
    for phase in ("bootstrap", "schema", "grants", "seed"):
        run("m2_local_db.py", phase)
    run("mac_flow_db.py", "fixture")
    run("m2_local_db.py", "release")
    run("m2_local_db.py", "snapshot")
    run("mac_flow_tunnel.py", "start")
    run("m2_local_servers.py", "start")


if __name__ == "__main__":
    os.umask(0o077)
    main()
