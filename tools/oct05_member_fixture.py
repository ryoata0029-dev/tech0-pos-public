"""Fixed Oct-05 member gate: release only after a different real selection commits.

Install outside the existing recovery phase wrapper. No DB/network/browser calls,
request payload/cookie reads, public controls, fake application results or timers
that release a request before the replacement selection has actually committed.
"""

import argparse
import json
import re
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID


def _uuid(value):
    parsed = UUID(value)
    if parsed.version != 4 or str(parsed) != value:
        raise ValueError("Canonical generated UUID required")
    return value


def _tag(value):
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value):
        raise ValueError("Fresh safe tag required")
    return value


def _write(path, value):
    with path.open("x") as output:
        json.dump(value, output, ensure_ascii=False, indent=2)


def _retained_lines(cart):
    keys = ("line_id", "line_no", "code", "quantity", "unit_price", "tax_rate")
    return [{key: line[key] for key in keys} for line in cart["lines"]]


def _fixed_paths():
    from m2_local_profile import EVIDENCE, LOCAL, NAME, PROFILE, ROOT

    if (
        PROFILE != "oct05-mac"
        or LOCAL != ROOT / ".oct05-mac-local"
        or EVIDENCE != ROOT / "docs/implementation/evidence/oct05-mac"
        or NAME != "tech0-pos-oct05-mac-mysql"
    ):
        raise ValueError("Only the fresh fixed oct05-mac runtime is allowed")
    return LOCAL, EVIDENCE


class _MemberFixture:
    def __init__(self, upstream, local: Path, evidence: Path):
        self.upstream = upstream
        self.local = local
        self.evidence = evidence
        self.lock = threading.Lock()

    def _ready(self, path):
        # A gate uses exclusive creation before its JSON write completes.
        deadline = time.monotonic() + 1
        while True:
            try:
                return json.loads(path.read_text())
            except (FileNotFoundError, json.JSONDecodeError):
                if time.monotonic() >= deadline:
                    raise ValueError("Actual old gate evidence did not become ready") from None
                time.sleep(0.01)

    def phase(self, request, action, *, readonly=False):
        result = self.upstream(request, action, readonly=readonly)
        observed_at = datetime.now(UTC).isoformat()
        control = self.local / "oct05-member-auto.json"
        if readonly or request.method != "PUT" or not control.exists():
            return result
        with self.lock:
            if not control.exists():
                return result
            config = json.loads(control.read_text())
            tag = _tag(config["tag"])
            cart_id = _uuid(config["cart_id"])
            if (
                set(config) != {"tag", "cart_id", "old_member_id", "new_member_id"}
                or config["old_member_id"] != "MEMBER_1"
                or config["new_member_id"] not in ("MEMBER_0", None)
            ):
                raise ValueError("Only fixed replacement member selections are allowed")
            if request.url.path != f"/api/carts/{cart_id}/member":
                return result
            body = result.body
            cart = body.get("cart", {})
            if cart.get("cart_id") != cart_id or cart.get("state") != "EDITING":
                return result
            late = getattr(request.state, "tc03_member_gate", None)
            if body.get("operation_status") == "PREPARED" and result.continue_member:
                if (
                    late is not None
                    and late.get("tag") == tag
                    and late.get("kind") == "member-late"
                    and late.get("operation_id") == body.get("operation_id")
                    and cart.get("member_state") == "PENDING"
                    and cart.get("pending_member_id") == "MEMBER_1"
                ):
                    _write(
                        self.evidence / f"member-old-receipt-{tag}.json",
                        {
                            "at_utc": observed_at,
                            "tag": tag,
                            "cart_id": cart_id,
                            "operation_id": _uuid(body["operation_id"]),
                            "version": cart["version"],
                            "pending_member_id": "MEMBER_1",
                            "line_count": len(cart["lines"]),
                            "retained_lines": _retained_lines(cart),
                            "after_real_receipt_commit": True,
                        },
                    )
                return result
            expected_state = "CONFIRMED" if config["new_member_id"] else "NON_MEMBER"
            if (
                body.get("operation_status") != "APPLIED"
                or body.get("code") is not None
                or cart.get("member_state") != expected_state
                or cart.get("member_id") != config["new_member_id"]
                or cart.get("pending_member_id") is not None
            ):
                return result
            receipt = self._ready(self.evidence / f"member-old-receipt-{tag}.json")
            gate = self._ready(self.evidence / f"gate-{tag}.json")
            held = self._ready(self.evidence / f"lookup-held-{tag}.json")
            new_id = _uuid(body["operation_id"])
            old_id = _uuid(receipt["operation_id"])
            held_version = int(receipt["version"])
            expected_version = held_version + (2 if config["new_member_id"] else 1)
            if (
                receipt.get("tag") != tag
                or receipt.get("cart_id") != cart_id
                or receipt.get("after_real_receipt_commit") is not True
                or receipt.get("pending_member_id") != "MEMBER_1"
                or gate.get("tag") != tag
                or gate.get("kind") != "member-late"
                or gate.get("state") != "EDITING"
                or gate.get("member_state") != "PENDING"
                or gate.get("cart_id") != cart_id
                or gate.get("operation_id") != old_id
                or int(gate.get("version", 0)) != held_version
                or gate.get("after_real_receipt_commit") is not True
                or held.get("tag") != tag
                or held.get("operation_id") != old_id
                or held.get("found") is not True
                or held.get("after_real_lookup") is not True
                or held.get("outside_update_transaction") is not True
                or datetime.fromisoformat(held["at_utc"]) >= datetime.fromisoformat(observed_at)
                or new_id == old_id
                or int(cart["version"]) != expected_version
                or int(body.get("applied_version") or 0) != expected_version
                or receipt.get("line_count") != len(cart["lines"])
                or receipt.get("retained_lines") != _retained_lines(cart)
            ):
                raise ValueError("Old hold and new real selection do not match")
            release = self.local / f"release-{tag}.json"
            commit_file = self.evidence / f"member-new-commit-{tag}.json"
            if release.exists() or commit_file.exists():
                raise ValueError("Do not reuse an already released member trial")
            self.local.joinpath("oct05-member-auto.json").rename(
                self.local / f"oct05-member-auto-used-{tag}.json"
            )
            _write(
                commit_file,
                {
                    "at_utc": observed_at,
                    "time_semantics": "phase return observed immediately after real COMMIT",
                    "tag": tag,
                    "cart_id": cart_id,
                    "old_operation_id": old_id,
                    "new_operation_id": new_id,
                    "old_prepared_version": str(held_version),
                    "new_applied_version": str(expected_version),
                    "member_state": expected_state,
                    "member_id": config["new_member_id"],
                    "subtotal": cart["subtotal"],
                    "total": cart["total"],
                    "line_count": len(cart["lines"]),
                    "method": "PUT",
                    "path": request.url.path,
                    "after_real_new_selection_commit": True,
                    "outside_update_transaction": True,
                    "upstream_phase": self.upstream.__module__,
                },
            )
            released_at = datetime.now(UTC).isoformat()
            _write(release, {"tag": tag, "after_new_selection_commit": True})
            _write(
                self.evidence / f"member-auto-release-{tag}.json",
                {
                    "at_utc": released_at,
                    "tag": tag,
                    "cart_id": cart_id,
                    "old_operation_id": old_id,
                    "new_operation_id": new_id,
                    "new_commit_evidence": commit_file.name,
                    "hold_elapsed_seconds": (
                        datetime.fromisoformat(released_at) - datetime.fromisoformat(held["at_utc"])
                    ).total_seconds(),
                    "old_receipt_elapsed_seconds": (
                        datetime.fromisoformat(released_at)
                        - datetime.fromisoformat(receipt["at_utc"])
                    ).total_seconds(),
                    "release_after_actual_new_commit": True,
                    "browser_http_arrival_proven": False,
                },
            )
        return result


def install():
    """Root calls once after installing the existing real member-late wrapper."""
    local, evidence = _fixed_paths()
    import app.api.business as business

    if getattr(business.phase, "oct05_member_observer", False):
        raise ValueError("Member observer already installed")
    fixture = _MemberFixture(business.phase, local, evidence)

    def observed_phase(request, action, *, readonly=False):
        return fixture.phase(request, action, readonly=readonly)

    observed_phase.oct05_member_observer = True
    business.phase = observed_phase


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("arm",))
    parser.add_argument("--tag", required=True, type=_tag)
    parser.add_argument("--cart-id", required=True, type=_uuid)
    parser.add_argument("--new-member", required=True, choices=("member0", "nonmember"))
    args = parser.parse_args(argv)
    local, evidence = _fixed_paths()
    config = {"kind": "member-late", "tag": args.tag}
    if json.loads((local / "backend-gate.json").read_text()) != config:
        raise ValueError("Arm the matching fresh member-late gate first")
    paths = (
        local / "oct05-member-auto.json",
        local / f"oct05-member-auto-used-{args.tag}.json",
        local / f"release-{args.tag}.json",
        evidence / f"gate-{args.tag}.json",
        evidence / f"lookup-held-{args.tag}.json",
        evidence / f"member-old-receipt-{args.tag}.json",
        evidence / f"member-new-commit-{args.tag}.json",
        evidence / f"member-auto-release-{args.tag}.json",
    )
    if any(path.exists() for path in paths):
        raise ValueError("An unused pre-lookup trial is required")
    _write(
        paths[0],
        {
            "tag": args.tag,
            "cart_id": args.cart_id,
            "old_member_id": "MEMBER_1",
            "new_member_id": "MEMBER_0" if args.new_member == "member0" else None,
        },
    )
    print(json.dumps({"armed_auto_member_release": args.tag, "profile": "oct05-mac"}))


if __name__ == "__main__":
    main()
