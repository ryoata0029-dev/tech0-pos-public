"""Create fresh M2-only secrets/TLS material. Refuse to overwrite any existing directory."""

import json
import os
import secrets
import subprocess

from m2_local_profile import LOCAL, PROFILE


def main():
    os.umask(0o077)
    LOCAL.mkdir(mode=0o700, exist_ok=False)
    tls = LOCAL / "tls"
    tls.mkdir(mode=0o700)
    passwords = {
        name: secrets.token_urlsafe(32)
        for name in (
            "root",
            "pos_app",
            "pos_master",
            "pos_schema",
            "STAFF_A",
            "STAFF_B",
            "relay",
        )
    }
    if PROFILE in (
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
    ):
        for staff in ("STAFF_A", "STAFF_B"):
            passwords[staff] = "".join(
                secrets.choice("abcdefghjkmnpqrstuvwxyz23456789") for _ in range(10)
            )
    (LOCAL / "secrets.json").write_text(json.dumps(passwords))
    (LOCAL / "mysql-root").write_text(passwords["root"])
    ca_config = tls / "ca.cnf"
    ca_config.write_text(
        "[req]\nprompt=no\ndistinguished_name=dn\nx509_extensions=v3\n"
        "[dn]\nCN=Tech0 POS M2 Local Validation CA\n[v3]\n"
        "basicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,cRLSign\n"
    )
    server_config = tls / "server.cnf"
    server_config.write_text(
        "[req]\nprompt=no\ndistinguished_name=dn\n"
        "[dn]\nCN=localhost\n[v3]\nbasicConstraints=critical,CA:FALSE\n"
        "keyUsage=critical,digitalSignature,keyEncipherment\n"
        "extendedKeyUsage=serverAuth\nsubjectAltName=DNS:localhost,IP:127.0.0.1\n"
    )
    commands = [
        [
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "30",
            "-sha256",
            "-config",
            str(ca_config),
            "-keyout",
            str(tls / "ca.key"),
            "-out",
            str(tls / "ca.crt"),
        ],
        [
            "req",
            "-new",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-sha256",
            "-config",
            str(server_config),
            "-keyout",
            str(tls / "server.key"),
            "-out",
            str(tls / "server.csr"),
        ],
        [
            "x509",
            "-req",
            "-in",
            str(tls / "server.csr"),
            "-CA",
            str(tls / "ca.crt"),
            "-CAkey",
            str(tls / "ca.key"),
            "-CAcreateserial",
            "-out",
            str(tls / "server.crt"),
            "-days",
            "30",
            "-sha256",
            "-extfile",
            str(server_config),
            "-extensions",
            "v3",
        ],
    ]
    for command in commands:
        subprocess.run(
            ["openssl", *command],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    print("Fresh M2 local directory, independent secrets and localhost TLS certificate created.")


if __name__ == "__main__":
    main()
