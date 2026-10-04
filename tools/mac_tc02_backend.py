"""Mac TC-02 read-only product reply gates after the actual lookup; no public control."""

import json
import os
import threading
import time
from datetime import UTC, datetime

from m2_local_profile import EVIDENCE, LOCAL, PROFILE

if PROFILE not in (
    "mac-tc02",
    "mac-batch",
    "mac-parallel",
    "parallel-next",
    "parallel-mac-next",
    "oct05-mac",
):
    raise ValueError("Only the fresh Mac TC-02 profile is allowed")

import app.api.startup as startup  # noqa: E402
from app.main import app  # noqa: E402, F401
from app.services.errors import PosError, unavailable  # noqa: E402

if PROFILE in ("mac-batch", "mac-parallel", "parallel-next", "parallel-mac-next", "oct05-mac"):
    import mac_recovery_backend  # noqa: F401

original_run = startup.run
gate_lock = threading.Lock()


def run(request, action, *, readonly=False):
    real_error = None
    try:
        response = original_run(request, action, readonly=readonly)
    except PosError as error:
        if not (
            PROFILE
            in ("mac-batch", "mac-parallel", "parallel-next", "parallel-mac-next", "oct05-mac")
            and request.method == "GET"
            and readonly
            and request.url.path == "/api/products/PRODUCT_MISSING"
            and error.status == 404
            and error.code == "PRODUCT_NOT_FOUND"
        ):
            raise
        # The original transaction has already unwound; retain the actual exception.
        real_error = error
        response = None

    def finish():
        if real_error is not None:
            raise real_error
        return response

    if request.method != "GET" or not readonly:
        return finish()
    control = LOCAL / "product-gate.json"
    with gate_lock:
        if not control.exists():
            return finish()
        config = json.loads(control.read_text())
        if config["kind"] not in (
            "product-late",
            "product-unavailable",
            "product-late-missing",
            "product-late-unavailable",
        ):
            raise ValueError("Unsupported TC-02 gate")
        expected_code = "PRODUCT_MISSING" if config["kind"] == "product-late-missing" else "0001"
        if request.url.path != f"/api/products/{expected_code}":
            return finish()
        if config["kind"] in (
            "product-late-missing",
            "product-late-unavailable",
        ) and PROFILE not in (
            "mac-batch",
            "mac-parallel",
            "parallel-next",
            "parallel-mac-next",
            "oct05-mac",
        ):
            raise ValueError("Additional reply gates require the fresh Mac batch")
        tag = config["tag"]
        if not tag.replace("-", "").isalnum():
            raise ValueError("Unsafe tag")
        os.rename(control, LOCAL / f"product-gate-used-{tag}.json")
    value = (
        {"code": real_error.code, "message": real_error.message}
        if real_error is not None
        else json.loads(response.body)
    )
    real_status = real_error.status if real_error is not None else response.status_code
    if config["kind"] == "product-late-missing":
        assert value["code"] == "PRODUCT_NOT_FOUND" and real_status == 404
    else:
        assert value["code"] == "0001" and real_status == 200
    with (EVIDENCE / f"gate-{tag}.json").open("x") as output:
        json.dump(
            {
                "at_utc": datetime.now(UTC).isoformat(),
                "kind": config["kind"],
                "tag": tag,
                "after_real_lookup": True,
                "outside_read_transaction": True,
                "real_status": real_status,
                "body": value,
            },
            output,
            indent=2,
        )
    if config["kind"] == "product-unavailable":
        threading.Event().wait(3)
        with (EVIDENCE / f"gate-response-{tag}.json").open("x") as output:
            json.dump({"at_utc": datetime.now(UTC).isoformat(), "status": 503}, output)
        raise unavailable()
    release = LOCAL / f"release-{tag}.json"
    deadline = time.monotonic() + 600
    while not release.exists():
        if time.monotonic() >= deadline:
            raise unavailable()
        threading.Event().wait(0.1)
    injected_error = unavailable() if config["kind"] == "product-late-unavailable" else None
    returned_status = injected_error.status if injected_error else real_status
    returned_body = (
        {"code": injected_error.code, "message": injected_error.message}
        if injected_error
        else value
    )
    with (EVIDENCE / f"gate-response-{tag}.json").open("x") as output:
        json.dump(
            {
                "at_utc": datetime.now(UTC).isoformat(),
                "status": returned_status,
                "body": returned_body,
            },
            output,
        )
    if injected_error is not None:
        raise injected_error
    return finish()


startup.run = run
