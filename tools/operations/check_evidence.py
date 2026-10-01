"""Offline evidence checks. No DB, browser, cloud connection or repair is performed."""

import argparse
import json
import math
import re
from datetime import datetime, timedelta
from pathlib import Path

TABLES = frozenset(
    "STAFF AUTH_LOGIN_LIMIT MEMBER TAX_RATE PRODUCT DISCOUNT_CONDITION PRICE_HISTORY "
    "REGISTER AUTH_SESSION BROWSER_CONTEXT CART CART_LINE CART_OPERATION PURCHASE "
    "PURCHASE_LINE PURCHASE_TAX".split()
)


def performance(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != {"environment", "samples"}:
        raise ValueError("Invalid measurement envelope")
    if value["environment"] != "AZURE":
        raise ValueError("Azure UI evidence is required")
    seen: set[tuple[str, float]] = set()
    groups: dict[tuple[str, str, str], list[float]] = {}
    samples = value["samples"]
    if not isinstance(samples, list):
        raise ValueError("Missing samples")
    for row in samples:
        if not isinstance(row, dict) or set(row) != {
            "device",
            "operation",
            "mode",
            "start_ms",
            "display_ms",
            "confirmed",
            "idle_ms",
            "no_access_confirmed",
            "conditions_id",
        }:
            raise ValueError("Invalid sample fields")
        if (
            row["device"] not in ("MAC_CHROME", "IPHONE_CHROME")
            or row["operation"] not in ("PRODUCT", "MEMBER", "PURCHASE")
            or row["mode"] not in ("NORMAL", "IDLE")
        ):
            raise ValueError("Invalid measurement target")
        for key in ("start_ms", "display_ms", "idle_ms"):
            if type(row[key]) not in (int, float) or not math.isfinite(row[key]) or row[key] < 0:
                raise ValueError("Invalid timing")
        key = (row["device"], row["start_ms"])
        if key in seen:
            raise ValueError("Duplicate timing evidence")
        seen.add(key)
        duration = row["display_ms"] - row["start_ms"]
        if duration < 0 or row["confirmed"] is not True:
            raise ValueError("Final UI confirmation is required")
        if not isinstance(row["conditions_id"], str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{1,64}", row["conditions_id"]
        ):
            raise ValueError("Record matching device/network/data conditions")
        if row["mode"] == "IDLE" and (
            row["idle_ms"] < 1800000 or row["no_access_confirmed"] is not True
        ):
            raise ValueError("Each idle sample requires 30 minutes without access")
        groups.setdefault((row["device"], row["operation"], row["mode"]), []).append(duration)
    expected = {
        (device, operation, mode)
        for device in ("MAC_CHROME", "IPHONE_CHROME")
        for operation in ("PRODUCT", "MEMBER", "PURCHASE")
        for mode in ("NORMAL", "IDLE")
    }
    if set(groups) != expected or any(
        len(rows) != (10 if key[2] == "NORMAL" else 1) for key, rows in groups.items()
    ):
        raise ValueError("Require 10 normal and 1 individually idle sample per operation/device")
    for device in ("MAC_CHROME", "IPHONE_CHROME"):
        conditions = {row["conditions_id"] for row in samples if row["device"] == device}
        if len(conditions) != 1:
            raise ValueError("Conditions differ within device measurements")
    slow = sum(duration > 2000 for durations in groups.values() for duration in durations)
    return {
        "samples": len(samples),
        "over_2s": slow,
        "passed": slow == 0,
        "scope": "Recorded UI evidence only; evidence authenticity requires human review",
    }


def manifest(value: object) -> dict[str, set[str]]:
    if not isinstance(value, dict) or set(value) != {"snapshot_at", "consistent_read", "tables"}:
        raise ValueError("Invalid restore manifest")
    timestamp = datetime.fromisoformat(value["snapshot_at"])
    if timestamp.utcoffset() != timedelta(0) or value["consistent_read"] is not True:
        raise ValueError("UTC snapshot and consistent read are required")
    tables = value["tables"]
    if not isinstance(tables, dict) or set(tables) != TABLES:
        raise ValueError("All 16 tables are required; missing source cannot establish equality")
    result: dict[str, set[str]] = {}
    for name, rows in tables.items():
        if not isinstance(rows, list) or any(
            not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
            for digest in rows
        ):
            raise ValueError("Only canonical full-row SHA256 digests are accepted")
        if len(set(rows)) != len(rows):
            raise ValueError("Duplicate row digest; export primary keys with all columns")
        result[name] = set(rows)
    return result


def restore(source: object, target: object) -> dict[str, object]:
    old, new = manifest(source), manifest(target)
    differences = {
        name: {"source_only": len(old[name] - new[name]), "target_only": len(new[name] - old[name])}
        for name in sorted(TABLES)
        if old[name] != new[name]
    }
    return {
        "differences": differences,
        "equal": not differences,
        "scope": (
            "Digest equality only; backup validity, session revocation "
            "and safe cutover require separate proof"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("performance", "restore"))
    parser.add_argument("source", type=Path)
    parser.add_argument("target", nargs="?", type=Path)
    args = parser.parse_args()
    try:
        source = json.loads(args.source.read_text())
        if args.mode == "restore":
            if args.target is None:
                raise ValueError("Target manifest required")
            result = restore(source, json.loads(args.target.read_text()))
            success = result["equal"]
        else:
            result = performance(source)
            success = result["passed"]
        print(json.dumps(result))
        return 0 if success else 1
    except (ValueError, TypeError, KeyError, OSError):
        print(json.dumps({"error": "INVALID_OR_INCOMPLETE_EVIDENCE"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
