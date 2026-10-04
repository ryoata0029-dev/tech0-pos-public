"""Dedicated oct05-mac browser panel and post-COMMIT NEXT reply fixture.

No server/DB is started by this module. Install only from the approved private
runtime. The ordinary built application's handlers remain unchanged.
"""

import argparse
import json
import re
import tempfile
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
TAG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def write_once(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def config_checked(value):
    if set(value) != {"kind", "tag", "cart_id", "wait_seconds"}:
        raise ValueError("Unexpected NEXT fixture configuration")
    if value["kind"] != "next-late" or not TAG.fullmatch(value["tag"]):
        raise ValueError("Invalid NEXT fixture kind/tag")
    if not UUID.fullmatch(value["cart_id"]):
        raise ValueError("Expected saved cart UUIDv4")
    if value["wait_seconds"] != 7:
        raise ValueError("Fixed seven-second post-COMMIT reply deadline required")
    return value


class NextReplyGate:
    """Observe real committed results; release A's reply only after C's addition.

    The original business.phase closes its transaction before returning. B's
    purchase and NEXT are actual API operations from the explicitly clicked
    panel, never created/retried by this gate. Failed progression times out.
    """

    def __init__(self, local, evidence, original, unavailable):
        self.local, self.evidence = local, evidence
        self.original, self.unavailable = original, unavailable
        self.lock = threading.Lock()
        self.current = None

    def __call__(self, request, action, *, readonly=False):
        result = self.original(request, action, readonly=readonly)
        if readonly or request.method != "POST":
            return result
        body = result.body
        held = None
        with self.lock:
            active = self.current
            if active and body.get("operation_status") == "APPLIED":
                if request.url.path == f"/api/carts/{active['b']}/next":
                    c = body.get("new_cart_id")
                    if not c or not UUID.fullmatch(c) or c == active["b"]:
                        raise ValueError("Cannot identify C after the second committed NEXT")
                    if active.get("c"):
                        raise ValueError("Unexpected repeated second NEXT")
                    active["c"] = c
                    active["second_next_operation_id"] = body["operation_id"]
                elif active.get("c") and request.url.path == f"/api/carts/{active['c']}/lines":
                    cart = body["cart"]
                    if (
                        cart["cart_id"] != active["c"]
                        or cart["state"] != "EDITING"
                        or len(cart["lines"]) != 1
                        or cart["lines"][0]["code"] != "0001"
                        or cart["lines"][0]["quantity"] != 1
                    ):
                        raise ValueError("Final C addition did not match the dedicated scenario")
                    active["final_add_operation_id"] = body["operation_id"]
                    write_once(
                        self.evidence / f"next-progression-{active['tag']}.json",
                        {
                            "at_utc": datetime.now(UTC).isoformat(),
                            "tag": active["tag"],
                            "after_real_C_add_commit": True,
                            "a": active["a"],
                            "b": active["b"],
                            "c": active["c"],
                            "second_next_operation_id": active["second_next_operation_id"],
                            "final_add_operation_id": active["final_add_operation_id"],
                        },
                    )
                    active["release"].set()
            control = self.local / "next-reply-gate.json"
            if control.exists():
                config = config_checked(json.loads(control.read_text()))
                if request.url.path == f"/api/carts/{config['cart_id']}/next":
                    if self.current is not None:
                        raise ValueError("A NEXT fixture is already active")
                    b = body.get("new_cart_id")
                    if (
                        body.get("operation_status") != "APPLIED"
                        or not b
                        or not UUID.fullmatch(b)
                        or b == config["cart_id"]
                        or body["cart"]["cart_id"] != b
                    ):
                        raise ValueError("First NEXT must be an actual applied A-to-B result")
                    used = self.local / f"next-reply-gate-used-{config['tag']}.json"
                    if used.exists():
                        raise ValueError("NEXT fixture tag was already consumed")
                    control.rename(used)
                    held = config | {
                        "a": config["cart_id"],
                        "b": b,
                        "release": threading.Event(),
                    }
                    self.current = held
                    write_once(
                        self.evidence / f"next-held-{config['tag']}.json",
                        {
                            "at_utc": datetime.now(UTC).isoformat(),
                            "tag": config["tag"],
                            "after_real_next_commit": True,
                            "outside_transaction": True,
                            "old_cart_id": config["cart_id"],
                            "historical_next_cart_id": b,
                            "operation_id": body["operation_id"],
                            "applied_version": body.get("applied_version"),
                            "deadline_seconds": 7,
                        },
                    )
        if held:
            released = held["release"].wait(7)
            with self.lock:
                self.current = None
            write_once(
                self.evidence / f"next-returned-{held['tag']}.json",
                {
                    "at_utc": datetime.now(UTC).isoformat(),
                    "tag": held["tag"],
                    "actual_historical_success_returned": released,
                    "reason": "C_addition_committed"
                    if released
                    else "deadline_no_success_coverage",
                    "old_cart_id": held["a"],
                    "historical_next_cart_id": held["b"],
                    "latest_cart_id": held.get("c"),
                },
            )
            if not released:
                raise self.unavailable()
        return result


def install_next_gate():
    from m2_local_profile import EVIDENCE, LOCAL, PROFILE

    if PROFILE != "oct05-mac":
        raise ValueError("Only oct05-mac can install the NEXT fixture")
    from app.api import business
    from app.services.errors import unavailable

    if isinstance(business.phase, NextReplyGate):
        raise TypeError("NEXT fixture already installed")
    business.phase = NextReplyGate(LOCAL, EVIDENCE, business.phase, unavailable)


PANEL = (ROOT / "tools/oct05_recovery_panel.html").read_text()


def self_check():
    """Threaded fake-response control checks only; does not import the app/DB."""
    a = "11111111-1111-4111-8111-111111111111"
    b = "22222222-2222-4222-8222-222222222222"
    c = "33333333-3333-4333-8333-333333333333"
    op = "44444444-4444-4444-8444-444444444444"
    with tempfile.TemporaryDirectory() as tmp:
        local = Path(tmp) / "local"
        evidence = Path(tmp) / "evidence"
        local.mkdir()
        evidence.mkdir()
        config = {
            "kind": "next-late",
            "tag": "offline",
            "cart_id": a,
            "wait_seconds": 7,
        }
        config_checked(config)
        for invalid in [
            config | {"wait_seconds": 8},
            config | {"tag": "../bad"},
            config | {"cart_id": "AAAAAAAA-0000-4000-8000-000000000000"},
        ]:
            try:
                config_checked(invalid)
            except ValueError:
                pass
            else:
                raise AssertionError("Unsafe configuration accepted")
        write_once(local / "next-reply-gate.json", config)
        committed = threading.Event()

        def original(request, action, *, readonly=False):
            committed.set()
            return action

        gate = NextReplyGate(local, evidence, original, lambda: RuntimeError("deadline"))

        def req(path):
            return SimpleNamespace(method="POST", url=SimpleNamespace(path=path))

        def result(target):
            return SimpleNamespace(
                body={
                    "operation_status": "APPLIED",
                    "operation_id": op,
                    "new_cart_id": target,
                    "cart": {"cart_id": target, "state": "EDITING", "lines": []},
                }
            )

        first = result(b)
        returned = []
        worker = threading.Thread(
            target=lambda: returned.append(gate(req(f"/api/carts/{a}/next"), first))
        )
        worker.start()
        assert committed.wait(1)
        deadline = time.monotonic() + 1
        while not (evidence / "next-held-offline.json").exists():
            assert time.monotonic() < deadline
            threading.Event().wait(0.001)
        assert not returned
        gate(req(f"/api/carts/{b}/next"), result(c))
        assert not returned
        final = result(c)
        final.body["cart"]["lines"] = [{"code": "0001", "quantity": 1}]
        gate(req(f"/api/carts/{c}/lines"), final)
        worker.join(1)
        assert returned == [first]
        saved = json.loads((evidence / "next-returned-offline.json").read_text())
        assert saved["actual_historical_success_returned"] and saved["latest_cart_id"] == c
        assert (local / "next-reply-gate-used-offline.json").exists()
        assert not (local / "next-reply-gate.json").exists()
    print(json.dumps({"offline_gate_checks": "passed", "real_browser_DB_server_executed": False}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["self-check", "prepare-panel", "arm-next"])
    parser.add_argument("--tag")
    parser.add_argument("--cart-id")
    args = parser.parse_args()
    if args.command == "self-check":
        self_check()
        return
    from m2_local_profile import EVIDENCE, LOCAL, PROFILE

    if PROFILE != "oct05-mac" or not LOCAL.is_dir() or not EVIDENCE.is_dir():
        raise ValueError("Only an already prepared oct05-mac private runtime is allowed")
    if args.command == "prepare-panel":
        with (LOCAL / "recovery-panel.html").open("x") as output:
            output.write(PANEL)
        print(json.dumps({"profile": PROFILE, "panel_prepared": True, "live_operation": False}))
        return
    config = config_checked(
        {
            "kind": "next-late",
            "tag": args.tag or "",
            "cart_id": args.cart_id or "",
            "wait_seconds": 7,
        }
    )
    if (LOCAL / f"next-reply-gate-used-{config['tag']}.json").exists() or any(
        EVIDENCE.glob(f"next-*-{config['tag']}.json")
    ):
        raise ValueError("Fixture tag already used")
    write_once(LOCAL / "next-reply-gate.json", config)
    print(
        json.dumps(
            {
                "profile": PROFILE,
                "kind": "next-late",
                "tag": config["tag"],
                "armed": True,
            }
        )
    )


if __name__ == "__main__":
    main()
