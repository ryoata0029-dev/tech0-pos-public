"""Start only a fresh, named M2 MySQL instance; retain it on all failures."""

import json
import socket
import subprocess

from m2_local_profile import EVIDENCE, LOCAL, NAME, VOLUME

IMAGE = "mysql@sha256:0744ee5ef89ce6ccfa13de3e579fe6b9e27f93dd70da9c06d2c908b1b193fb8d"


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


def main():
    if NAME in docker("ps", "-a", "--format", "{{.Names}}").splitlines():
        raise RuntimeError("Container already exists; inspect, do not recreate")
    if VOLUME in docker("volume", "ls", "--format", "{{.Name}}").splitlines():
        raise RuntimeError("Volume already exists; inspect, do not reuse")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 3307))
    info = json.loads(docker("image", "inspect", IMAGE))[0]
    docker("volume", "create", "--label", "purpose=tech0-pos-m2", VOLUME)
    command = [
        "run",
        "-d",
        "--name",
        NAME,
        "--label",
        "purpose=tech0-pos-m2",
        "--publish",
        "127.0.0.1:3307:3306",
        "--mount",
        f"type=volume,source={VOLUME},target=/var/lib/mysql",
        "-e",
        "MYSQL_ROOT_PASSWORD_FILE=/run/secrets/mysql-root",
        "-e",
        "MYSQL_ROOT_HOST=%",
        "-e",
        "MYSQL_INITDB_SKIP_TZINFO=1",
    ]
    for source, target in [
        ("mysql-root", "/run/secrets/mysql-root"),
        ("tls/ca.crt", "/run/tls/ca.crt"),
        ("tls/server.crt", "/run/tls/server.crt"),
        ("tls/server.key", "/run/tls/server.key"),
    ]:
        command += [
            "--mount",
            f"type=bind,source={LOCAL / source},target={target},readonly",
        ]
    command += [
        "--entrypoint",
        "/bin/bash",
        IMAGE,
        "-c",
        "mkdir -p /tmp/m2-tls && cp /run/tls/* /tmp/m2-tls/ && "
        "chown -R mysql:mysql /tmp/m2-tls && chmod 700 /tmp/m2-tls && "
        "chmod 600 /tmp/m2-tls/* && exec /usr/local/bin/docker-entrypoint.sh mysqld "
        "--require-secure-transport=ON --ssl-ca=/tmp/m2-tls/ca.crt "
        "--ssl-cert=/tmp/m2-tls/server.crt --ssl-key=/tmp/m2-tls/server.key "
        "--general-log=OFF --slow-query-log=OFF --local-infile=OFF",
    ]
    identity = docker(*command)
    evidence = {
        "image": IMAGE,
        "image_id": info["Id"],
        "architecture": info["Architecture"],
        "container": NAME,
        "container_id": identity,
        "volume": VOLUME,
        "port_binding": "127.0.0.1:3307 -> 3306",
        "tls_required": True,
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "mysql-environment.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
