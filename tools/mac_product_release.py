"""Release a reached product gate only in fixed isolated Mac trial profiles."""

import argparse
import json
import re
import time
from datetime import UTC, datetime


def release_after():
    """Release only a fresh armed product reply after actual lookup arrival."""
    from m2_local_profile import EVIDENCE, LOCAL, PROFILE

    if PROFILE not in (
        "mac-batch",
        "mac-parallel",
        "parallel-next",
        "parallel-mac-next",
        "oct05-mac",
    ):
        raise ValueError("Automatic release is limited to the named Mac trials")
    parser = argparse.ArgumentParser(description=release_after.__doc__)
    parser.add_argument("action", choices=("release-after",))
    parser.add_argument("--tag", required=True)
    parser.add_argument(
        "--kind",
        required=True,
        choices=("product-late", "product-late-missing", "product-late-unavailable"),
    )
    parser.add_argument("--seconds", type=int, required=True, choices=range(2, 8))
    args = parser.parse_args()
    if re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", args.tag) is None:
        raise ValueError("Unsafe tag")
    config = {"kind": args.kind, "tag": args.tag}
    control = LOCAL / "product-gate.json"
    used = LOCAL / f"product-gate-used-{args.tag}.json"
    release = LOCAL / f"release-{args.tag}.json"
    reached = EVIDENCE / f"gate-{args.tag}.json"
    returned = EVIDENCE / f"gate-response-{args.tag}.json"
    claim = LOCAL / f"release-after-{args.tag}.json"
    evidence = EVIDENCE / f"release-after-{args.tag}.json"
    if not control.exists() or json.loads(control.read_text()) != config:
        raise ValueError("The matching product reply gate must be armed first")
    if any(path.exists() for path in (used, release, reached, returned, claim, evidence)):
        raise ValueError("An unused armed tag is required")
    started_at = datetime.now(UTC).isoformat()
    # Retain the exclusive claim even on failure; do not reuse this run/tag.
    with claim.open("x") as output:
        json.dump(
            {**config, "started_at_utc": started_at, "wait_seconds": args.seconds},
            output,
        )
    deadline = time.monotonic() + 45

    def read_if_present(path):
        try:
            return json.loads(path.read_text())
        except FileNotFoundError:
            return None

    while True:
        if release.exists() or returned.exists():
            raise ValueError("The reply was already released or returned")
        armed_config = read_if_present(control)
        used_config = read_if_present(used)
        if armed_config is not None and armed_config != config:
            raise ValueError("The armed gate configuration changed")
        if used_config is not None and used_config != config:
            raise ValueError("The reached gate configuration changed")
        if reached.exists():
            try:
                arrival = json.loads(reached.read_text())
            except json.JSONDecodeError:
                # The gate creates its exclusive file before completing the JSON write.
                arrival = None
            if arrival is not None:
                break
        if time.monotonic() >= deadline:
            raise TimeoutError("The actual product lookup gate was not reached within 45 seconds")
        time.sleep(0.05)
    expected_status = 404 if args.kind == "product-late-missing" else 200
    if (
        any(arrival.get(key) != value for key, value in config.items())
        or arrival.get("after_real_lookup") is not True
        or arrival.get("outside_read_transaction") is not True
        or arrival.get("real_status") != expected_status
        or not isinstance(arrival.get("at_utc"), str)
        or not used.exists()
        or json.loads(used.read_text()) != config
        or control.exists()
    ):
        raise ValueError("The actual gate does not match the armed configuration")
    observed_at = datetime.now(UTC).isoformat()
    waiting_started = time.monotonic()
    time.sleep(args.seconds)
    if (
        release.exists()
        or returned.exists()
        or control.exists()
        or not used.exists()
        or json.loads(used.read_text()) != config
        or json.loads(reached.read_text()) != arrival
    ):
        raise ValueError("Gate configuration changed or the reply was already released")
    released_at = datetime.now(UTC).isoformat()
    with release.open("x") as output:
        json.dump({"tag": args.tag}, output)
    record = {
        **config,
        "started_at_utc": started_at,
        "gate_at_utc": arrival["at_utc"],
        "observed_at_utc": observed_at,
        "released_at_utc": released_at,
        "wait_seconds": args.seconds,
        "actual_wait_seconds": round(time.monotonic() - waiting_started, 6),
        "after_real_lookup": True,
        "outside_read_transaction": True,
    }
    with evidence.open("x") as output:
        json.dump(record, output, indent=2)
    print(json.dumps({"released": args.tag, "kind": args.kind, "wait_seconds": args.seconds}))
