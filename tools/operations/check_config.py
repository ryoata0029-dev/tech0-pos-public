"""Validate locally prepared Azure values, without sending configuration anywhere."""

import argparse
import ipaddress
import json
import re
from pathlib import Path
from urllib.parse import urlsplit


def validate(value: dict[str, object]) -> None:
    if set(value) != {
        "frontend_outbound_cidrs",
        "backend_outbound_ips",
        "operator_cidrs",
        "frontend_origin",
        "backend_url",
        "deployment_version",
        "log_retention_days",
        "log_quota_mb",
    }:
        raise ValueError("Missing or extra configuration")
    for field in ("frontend_outbound_cidrs", "backend_outbound_ips", "operator_cidrs"):
        rows = value[field]
        if not isinstance(rows, list) or not rows or len(rows) != len(set(rows)):
            raise ValueError("Explicit unique network addresses required")
        for row in rows:
            network = ipaddress.ip_network(row, strict=True)
            if (
                network.version != 4
                or network.prefixlen != 32
                or not network.network_address.is_global
            ):
                raise ValueError("Only individually verified public IPv4 addresses allowed")
            if field == "backend_outbound_ips" and "/" in row:
                raise ValueError("DB firewall requires bare individual IPs")
    for field in ("frontend_origin", "backend_url"):
        raw = value[field]
        if not isinstance(raw, str):
            raise ValueError("Invalid HTTPS origin")
        parts = urlsplit(raw)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.path
            or parts.query
            or parts.fragment
            or parts.username
            or parts.password
            or parts.port not in (None, 443)
        ):
            raise ValueError("Exact HTTPS origin required")
    if value["frontend_origin"] == value["backend_url"]:
        raise ValueError("Separate frontend and backend origins required")
    if not isinstance(value["deployment_version"], str) or not re.fullmatch(
        r"[A-Za-z0-9_.-]{1,64}", value["deployment_version"]
    ):
        raise ValueError("Invalid deployment version")
    if (
        type(value["log_retention_days"]) is not int
        or value["log_retention_days"] != 7
        or type(value["log_quota_mb"]) is not int
        or value["log_quota_mb"] != 100
    ):
        raise ValueError("Record the designed log retention and quota")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    try:
        value = json.loads(args.file.read_text())
        validate(value)
        print('{"valid":true,"scope":"input only; Azure application is unverified"}')
        return 0
    except (ValueError, TypeError, KeyError, OSError):
        print('{"valid":false,"error":"INVALID_CONFIG"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
