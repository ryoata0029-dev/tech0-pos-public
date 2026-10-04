"""Offline assertions for the recorded Mac member-display trial; no DB or UI writes."""

import hashlib
import json
import plistlib
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/implementation/evidence/mac-member"


def read(name):
    return json.loads((EVIDENCE / name).read_text())


def main():
    snapshots = {path.stem: read(path.name) for path in EVIDENCE.glob("db-*.json")}
    baseline = snapshots["db-baseline"]
    identity_keys = (
        "cart_id",
        "line_id",
        "line_no",
        "product_id",
        "quantity",
        "unit_price_snapshot",
        "tax_rate_snapshot",
        "conditions_fixed_at",
    )
    line_identity = [{key: line[key] for key in identity_keys} for line in baseline["lines"]]
    assert len(line_identity) == 3
    assert [(line["product_id"], line["quantity"]) for line in line_identity] == [
        (1, 3),
        (2, 1),
        (3, 1),
    ]
    for snapshot in snapshots.values():
        assert len(snapshot["carts"]) == 1
        cart = snapshot["carts"][0]
        assert cart["cart_id"] == baseline["carts"][0]["cart_id"]
        assert cart["staff_id"] == "STAFF_A" and cart["state"] == "EDITING"
        assert not snapshot["purchases"] and not snapshot["purchase_lines"]
        assert not snapshot["purchase_taxes"]
        assert cart["active_purchase_operation_id"] is None
        assert snapshot["products"] == baseline["products"]
        assert [
            {key: line[key] for key in identity_keys} for line in snapshot["lines"]
        ] == line_identity
        assert not any(op["kind"] in ("PURCHASE", "NEXT") for op in snapshot["operations"])

    faults = {}
    for prefix, total, version in (("first", "570", 7), ("change", "537", 11)):
        unknown = snapshots[f"db-{prefix}-unknown"]
        pending = snapshots[f"db-{prefix}-pending"]
        for key in ("register", "contexts", "carts", "lines", "operations", "purchases"):
            assert unknown[key] == pending[key], "Explicit GET changed business state"
        cart = unknown["carts"][0]
        assert cart["member_state"] == "PENDING" and cart["pending_member_id"] == "MEMBER_1"
        assert cart["total"] == total and cart["version"] == version
        assert cart["member_id"] == (None if prefix == "first" else "MEMBER_0")
        gate = read(f"gate-{prefix}-fault.json")
        response = read(f"gate-response-{prefix}-fault.json")
        assert gate["after_real_receipt_commit"] and response["after_real_receipt_commit"]
        assert gate["cart_id"] == cart["cart_id"]
        assert gate["operation_id"] == cart["active_member_operation_id"]
        op = next(op for op in unknown["operations"] if op["operation_id"] == gate["operation_id"])
        assert op["status"] == "PREPARED" and op["prepared_version"] == version
        assert response["status"] == 503 and response["delay_seconds"] == 3
        delay = (
            datetime.fromisoformat(response["at_utc"]) - datetime.fromisoformat(gate["at_utc"])
        ).total_seconds()
        assert 3 <= delay < 15
        for stage in ("sending", "unknown"):
            dom = (EVIDENCE / f"ui-{prefix}-{stage}.txt").read_text()
            assert "会員：確認待ち（指定結果は未確認）" in dom
            assert "変更前の参考額・会員指定の結果は未確認です。" in dom
            assert "paragraph: 会員：MEMBER_0" not in dom
            assert f"税込合計：{total}円" in dom
            for role, name in (
                ("button", "購入確定"),
                ("button", "数量変更"),
                ("button", "削除"),
                ("textbox", "商品コード"),
                ("textbox", "変更先の会員ID"),
                ("button", "照会・再照会"),
            ):
                assert f'{role} "{name}" [disabled]' in dom
            at = datetime.fromisoformat(dom.splitlines()[0].replace("Z", "+00:00"))
            if stage == "sending":
                assert at < datetime.fromisoformat(response["at_utc"])
            else:
                assert at > datetime.fromisoformat(response["at_utc"])
        dom = (EVIDENCE / f"ui-{prefix}-pending.txt").read_text()
        assert "会員：会員確認待ち" in dom and "変更前の参考額・会員確認待ち" in dom
        assert 'button "購入確定" [disabled]' in dom
        assert 'textbox "商品コード" [disabled]' in dom
        for name in ("照会・再照会", "非会員として続ける"):
            assert f'button "{name}"' in dom and f'button "{name}" [disabled]' not in dom
        faults[prefix] = {
            "operation_id": gate["operation_id"],
            "receipt_version": version,
            "delay_seconds_observed": delay,
            "reference_total": int(total),
        }

    for tag, member, total in (
        ("member-a-confirmed", "MEMBER_0", "537"),
        ("relookup-confirmed", "MEMBER_0", "537"),
        ("final", None, "570"),
    ):
        cart = snapshots[f"db-{tag}"]["carts"][0]
        assert cart["member_id"] == member and cart["total"] == total
        assert cart["member_state"] == ("CONFIRMED" if member else "NON_MEMBER")
        assert cart["pending_member_id"] is None and cart["active_member_operation_id"] is None
    for tag in ("first-nonmember", "member-a-confirmed", "relookup-confirmed", "final-nonmember"):
        dom = (EVIDENCE / f"ui-{tag}.txt").read_text()
        assert "変更前の参考額" not in dom and "指定結果は未確認" not in dom
        assert 'button "購入確定" [disabled]' not in dom
        assert 'button "購入確定"' in dom
    final = snapshots["db-final"]
    for fault in faults.values():
        op = next(op for op in final["operations"] if op["operation_id"] == fault["operation_id"])
        assert op["status"] == "REJECTED" and op["result_code"] == "MEMBER_LOOKUP_SUPERSEDED"
    previous = json.loads(
        (ROOT / "docs/implementation/evidence/member-display-fix/verification.json").read_text()
    )
    for name, expected in previous["sources_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    build_id = (ROOT / "frontend/.next/BUILD_ID").read_text().strip()
    assert build_id == previous["build_id"]
    chrome = plistlib.loads(
        Path("/Applications/Google Chrome.app/Contents/Info.plist").read_bytes()
    )
    node = ROOT / ".m0-cache/fnm/node-versions/v24.21.0/installation/bin/node"
    proof = {
        "at_utc": datetime.now(UTC).isoformat(),
        "offline_assertions": "passed",
        "same_cart": True,
        "line_identity_and_conditions_retained": True,
        "snapshots_checked": len(snapshots),
        "purchases": 0,
        "faults": faults,
        "explicit_get_changed_business_state": False,
        "relookup_confirmed_member": "MEMBER_0",
        "member_total": 537,
        "final_nonmember_total": 570,
        "build_id": build_id,
        "sources_sha256": previous["sources_sha256"],
        "chrome_version": chrome["CFBundleShortVersionString"],
        "macos_version": subprocess.check_output(["sw_vers", "-productVersion"], text=True).strip(),
        "node_version": subprocess.check_output([str(node), "--version"], text=True).strip(),
        "scope": "Mac Chrome non-camera receipt-after-COMMIT member503 display regression only",
    }
    with (EVIDENCE / "verification.json").open("x") as output:
        json.dump(proof, output, indent=2)
    print(json.dumps(proof, ensure_ascii=False))


if __name__ == "__main__":
    main()
