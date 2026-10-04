"""Private receipt-COMMIT gates; no public control API, fake state or DB rewrites."""

import json
import os
import threading
import time
from datetime import UTC, datetime

from m2_local_profile import EVIDENCE, LOCAL, PROFILE

if PROFILE not in (
    "mac-recovery",
    "mac-restart",
    "mac-member",
    "mac-tc03",
    "mac-tc03-fix",
    "mac-batch",
    "mac-parallel",
    "parallel-next",
    "parallel-mac-next",
    "oct05-mac",
    "iphone-camera",
):
    raise ValueError("Mac-recovery only")

import app.api.business as business  # noqa: E402
from app.main import app  # noqa: E402, F401
from app.services.errors import unavailable  # noqa: E402

original_phase = business.phase
gate_lock = threading.Lock()


def phase(request, action, *, readonly=False):
    result = original_phase(request, action, readonly=readonly)
    late = getattr(request.state, "tc03_member_gate", None)
    if (
        PROFILE
        in (
            "mac-tc03",
            "mac-tc03-fix",
            "mac-batch",
            "mac-parallel",
            "parallel-next",
            "parallel-mac-next",
            "oct05-mac",
            "iphone-camera",
        )
        and late is not None
    ):
        tag = late["tag"]
        if readonly and "found" in result.body:
            # The real lookup has completed and its transaction/connection is closed.
            with (EVIDENCE / f"lookup-held-{tag}.json").open("x") as output:
                json.dump(
                    {
                        "at_utc": datetime.now(UTC).isoformat(),
                        "tag": tag,
                        "operation_id": late["operation_id"],
                        "found": result.body["found"],
                        "after_real_lookup": True,
                        "outside_update_transaction": True,
                    },
                    output,
                    indent=2,
                )
            release = LOCAL / f"release-{tag}.json"
            deadline = time.monotonic() + 600
            waiter = threading.Event()
            while not release.exists():
                if time.monotonic() >= deadline:
                    raise unavailable()
                waiter.wait(0.1)
            with (EVIDENCE / f"lookup-released-{tag}.json").open("x") as output:
                json.dump({"at_utc": datetime.now(UTC).isoformat(), "tag": tag}, output)
        elif not readonly and result.body.get("operation_id") == late["operation_id"]:
            with (EVIDENCE / f"lookup-finished-{tag}.json").open("x") as output:
                json.dump(
                    {
                        "at_utc": datetime.now(UTC).isoformat(),
                        "tag": tag,
                        "operation_id": result.body["operation_id"],
                        "operation_status": result.body["operation_status"],
                        "code": result.body.get("code"),
                        "cart": result.body["cart"],
                    },
                    output,
                    indent=2,
                )
        return result
    control = LOCAL / "backend-gate.json"
    config = None
    # This point is AFTER the actual phase's transaction context has committed.
    with gate_lock:
        if control.exists():
            candidate = json.loads(control.read_text())
            kind = candidate["kind"]
            eligible = (
                kind in ("member-unavailable", "member-late") and result.continue_member
            ) or (
                kind == "purchase-hold"
                and request.url.path == "/api/purchases"
                and result.body.get("operation_status") == "PREPARED"
                and result.body.get("cart", {}).get("state") == "SAVING"
            )
            if eligible:
                tag = candidate["tag"]
                if not tag.replace("-", "").isalnum():
                    raise ValueError("Unsafe gate tag")
                os.rename(control, LOCAL / f"backend-gate-used-{tag}.json")
                config = candidate
    if config is None:
        return result
    tag = config["tag"]
    event = {
        "at_utc": datetime.now(UTC).isoformat(),
        "tag": tag,
        "kind": config["kind"],
        "after_real_receipt_commit": True,
        "operation_id": result.body["operation_id"],
        "cart_id": result.body["cart"]["cart_id"],
        "version": result.body["cart"]["version"],
        "state": result.body["cart"]["state"],
        "member_state": result.body["cart"]["member_state"],
    }
    with (EVIDENCE / f"gate-{tag}.json").open("x") as output:
        json.dump(event, output, indent=2)
    if config["kind"] == "member-late":
        if PROFILE not in (
            "mac-tc03",
            "mac-tc03-fix",
            "mac-batch",
            "mac-parallel",
            "parallel-next",
            "parallel-mac-next",
            "oct05-mac",
            "iphone-camera",
        ):
            raise ValueError("Member lookup hold is limited to TC-03")
        request.state.tc03_member_gate = config | {"operation_id": result.body["operation_id"]}
        return result
    if config["kind"] == "member-unavailable":
        if PROFILE in (
            "mac-member",
            "mac-tc03",
            "mac-tc03-fix",
            "mac-batch",
            "mac-parallel",
            "parallel-next",
            "parallel-mac-next",
            "oct05-mac",
            "iphone-camera",
        ):
            # Observe the actual sending UI, then inject the same receipt-after-COMMIT 503.
            threading.Event().wait(3)
            with (EVIDENCE / f"gate-response-{tag}.json").open("x") as output:
                json.dump(
                    {
                        "at_utc": datetime.now(UTC).isoformat(),
                        "tag": tag,
                        "status": 503,
                        "after_real_receipt_commit": True,
                        "delay_seconds": 3,
                    },
                    output,
                    indent=2,
                )
        raise unavailable()
    release = LOCAL / f"release-{tag}.json"
    deadline = time.monotonic() + 600
    waiter = threading.Event()
    while not release.exists():
        if time.monotonic() >= deadline:
            raise unavailable()
        waiter.wait(0.1)
    # A subsequent recovery fence must make this old request harmless.
    with (EVIDENCE / f"gate-released-{tag}.json").open("x") as output:
        json.dump({"tag": tag, "at_utc": datetime.now(UTC).isoformat()}, output)
    return result


business.phase = phase
