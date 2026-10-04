"""Audit saved TC03-P2-01 Mac regression evidence without DB/UI changes."""

import difflib
import hashlib
import json
import plistlib
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/implementation/evidence/mac-tc03-fix"


def read(name):
    return json.loads((EVIDENCE / name).read_text())


def dom(tag):
    return (EVIDENCE / f"ui-{tag}.txt").read_text()


def disabled(text, role, name, expected):
    marker = f'{role} "{name}"'
    assert marker in text
    assert (marker + " [disabled]" in text) == expected


def main():
    snapshots = {p.stem: read(p.name) for p in EVIDENCE.glob("db-*.json")}
    assert len(snapshots) == 9
    baseline = snapshots["db-lines-baseline"]
    cart_id = baseline["carts"][0]["cart_id"]
    identity = (
        "cart_id",
        "line_id",
        "line_no",
        "product_id",
        "quantity",
        "unit_price_snapshot",
        "tax_rate_snapshot",
        "conditions_fixed_at",
    )
    fixed_lines = [{k: line[k] for k in identity} for line in baseline["lines"]]
    assert [(line["product_id"], line["quantity"]) for line in fixed_lines] == [
        (1, 3),
        (2, 1),
        (3, 1),
    ]
    for name, snapshot in snapshots.items():
        assert len(snapshot["carts"]) == 1 and snapshot["carts"][0]["cart_id"] == cart_id
        cart = snapshot["carts"][0]
        assert cart["staff_id"] == "STAFF_A" and cart["state"] == "EDITING"
        assert cart["active_purchase_operation_id"] is None
        assert not any(op["kind"] in ("PURCHASE", "NEXT") for op in snapshot["operations"])
        assert (
            not snapshot["purchases"]
            and not snapshot["purchase_lines"]
            and not snapshot["purchase_taxes"]
        )
        assert snapshot["products"] == baseline["products"]
        assert [{k: line[k] for k in identity} for line in snapshot["lines"]] == (
            [] if name.startswith("db-empty-") else fixed_lines
        )

    cases = []
    for tag, snapshot_name, old_member, total in (
        ("empty-initial-notfound", "db-empty-initial-notfound", None, "0"),
        ("empty-change-notfound", "db-empty-change-notfound", "MEMBER_0", "0"),
        ("lines-initial-notfound", "db-lines-initial-notfound", None, "570"),
        ("lines-change-notfound", "db-lines-change-notfound-before-api", "MEMBER_0", "537"),
    ):
        snapshot = snapshots[snapshot_name]
        cart = snapshot["carts"][0]
        assert cart["member_state"] == "PENDING" and cart["pending_member_id"] == "MEMBER_MISSING"
        assert cart["member_id"] == old_member and cart["total"] == total
        op = next(
            op
            for op in snapshot["operations"]
            if op["operation_id"] == cart["active_member_operation_id"]
        )
        assert op["status"] == "REJECTED" and op["result_code"] == "MEMBER_NOT_FOUND"
        text = dom(tag)
        assert "会員が見つかりません。再入力または非会員を選択してください。" in text
        assert "会員：会員確認待ち" in text and "変更前の参考額・会員確認待ち" in text
        assert "paragraph: 会員：MEMBER_0" not in text
        assert f"税込合計：{total}円" in text
        for role, name in (
            ("textbox", "変更先の会員ID"),
            ("button", "照会・再照会"),
            ("button", "非会員として続ける"),
        ):
            disabled(text, role, name, False)
        for role, name in (
            ("textbox", "商品コード"),
            ("button", "商品をカメラで読む"),
            ("button", "購入確定"),
        ):
            disabled(text, role, name, True)
        if tag.startswith("lines-"):
            for name in ("数量変更", "削除"):
                disabled(text, "button", name, True)
        assert (
            'button "状態を再確認"' not in text and 'button "同じ要求で再確認・再試行"' not in text
        )
        cases.append(
            {
                "tag": tag,
                "result": "passed",
                "cart_version": cart["version"],
                "reference_total": int(total),
            }
        )

    for tag, member, total, has_lines in (
        ("empty-initial-member", "MEMBER_0", "0", False),
        ("empty-change-nonmember", None, "0", False),
        ("lines-initial-member", "MEMBER_0", "537", True),
        ("lines-change-nonmember", None, "570", True),
        ("initial-unavailable-relookup", "MEMBER_0", "537", True),
        ("final-nonmember", None, "570", True),
    ):
        text = dom(tag)
        assert "参考額" not in text
        assert f"会員：{member or '未指定の非会員'}" in text
        assert f"税込合計：{total}円" in text
        disabled(text, "textbox", "商品コード", False)
        disabled(text, "button", "購入確定", not has_lines)

    final = snapshots["db-final"]
    for tag in ("initial-unavailable", "change-unavailable"):
        snapshot = snapshots[f"db-{tag}"]
        cart = snapshot["carts"][0]
        total = "570" if tag.startswith("initial") else "537"
        assert cart["member_state"] == "PENDING" and cart["total"] == total
        gate = read(f"gate-{tag}.json")
        response = read(f"gate-response-{tag}.json")
        assert gate["after_real_receipt_commit"] and response["after_real_receipt_commit"]
        assert gate["operation_id"] == cart["active_member_operation_id"]
        assert response["status"] == 503 and response["delay_seconds"] == 3
        op = next(op for op in snapshot["operations"] if op["operation_id"] == gate["operation_id"])
        assert op["status"] == "PREPARED"
        for stage in (tag + "-sending", tag):
            text = dom(stage)
            assert "会員：確認待ち（指定結果は未確認）" in text and "参考額" in text
            assert f"税込合計：{total}円" in text
            for role, name in (
                ("textbox", "変更先の会員ID"),
                ("button", "照会・再照会"),
                ("button", "非会員として続ける"),
                ("button", "購入確定"),
            ):
                disabled(text, role, name, True)
        text = dom(tag + "-reconciled")
        disabled(text, "button", "非会員として続ける", False)
        disabled(text, "button", "購入確定", True)
        op = next(op for op in final["operations"] if op["operation_id"] == gate["operation_id"])
        assert op["status"] == "REJECTED" and op["result_code"] == "MEMBER_LOOKUP_SUPERSEDED"

    api = read("api-change-notfound-blocked.json")
    assert api["completed"] and len(api["requests"]) == 4 and api["before"] == api["after"]
    operation_ids = []
    for request, method in zip(api["requests"], ("POST", "PATCH", "DELETE", "POST"), strict=True):
        assert request["method"] == method and request["status"] == 409
        assert request["value"]["code"] == "STATE_CONFLICT" and request["value"]["message"]
        if method == "DELETE":
            from urllib.parse import parse_qs, urlsplit

            params = parse_qs(urlsplit(request["path"]).query)
            op_id = params["operation_id"][0]
            version = params["version"][0]
        else:
            op_id = request["body"]["operation_id"]
            version = request["body"]["version"]
        assert UUID(op_id).version == 4 and version == api["before"]["cart"]["version"]
        operation_ids.append(op_id)
    assert len(set(operation_ids)) == 4
    before = snapshots["db-lines-change-notfound-before-api"]
    after = snapshots["db-lines-change-notfound-after-api"]
    for key in (
        "register",
        "contexts",
        "carts",
        "lines",
        "operations",
        "purchases",
        "purchase_lines",
        "purchase_taxes",
    ):
        assert before[key] == after[key]
    cart = final["carts"][0]
    assert (
        cart["version"] == 21 and cart["member_state"] == "NON_MEMBER" and cart["member_id"] is None
    )
    assert cart["pending_member_id"] is None and cart["total"] == "570"
    assert cart["active_member_operation_id"] is None
    assert "Ran 71 tests" in (EVIDENCE / "make-check.log").read_text()
    assert "ℹ pass 74" in (EVIDENCE / "make-check.log").read_text()
    assert "ℹ fail 0" in (EVIDENCE / "make-check.log").read_text()
    assert "ℹ fail 8" in (EVIDENCE / "regression-before.log").read_text()
    assert "ℹ pass 32" in (EVIDENCE / "regression-after.log").read_text()
    shutdown = read("shutdown-final.json")
    assert shutdown["container_status"] == "exited" and all(shutdown["ports_closed"].values())
    assert shutdown["volume_retained"] == "tech0-pos-mac-tc03-fix-mysql-data"
    assert shutdown["secrets_absent_from_git_candidates_and_logs"]
    source = (ROOT / "frontend/app/register-cart.tsx").read_text()
    start = source.index("          const missingMember = changingMember")
    end = source.index(
        "            pending.current = null; setPhase('ready'); return keepCamera;", start
    )
    old = (
        "          if (state.cart.state === 'EDITING' && state.cart.member_state !== 'PENDING'\n"
        "            && current.current.cart.state === 'EDITING'"
        " && current.current.cart.member_state !== 'PENDING') {\n"
    )
    prior = source[:start] + old + source[end:]
    prior_hash = json.loads(
        (ROOT / "docs/implementation/evidence/mac-tc03/verification.json").read_text()
    )["application_sources_sha256"]["frontend/app/register-cart.tsx"]
    assert hashlib.sha256(prior.encode()).hexdigest() == prior_hash
    patch = "".join(
        difflib.unified_diff(
            prior.splitlines(True),
            source.splitlines(True),
            fromfile="before/register-cart.tsx",
            tofile="after/register-cart.tsx",
        )
    )
    (EVIDENCE / "application.patch").write_text(patch)
    names = (
        "frontend/app/register-cart.tsx",
        "frontend/tests/register-member.test.mjs",
        "tools/mac_tc03_fix.py",
        "tools/mac_tc03_fix_verify.py",
    )
    proof = {
        "at_utc": datetime.now(UTC).isoformat(),
        "offline_assertions": "passed",
        "tc03_p2_01": "resolved within tested Mac manual-entry scope",
        "cases": cases,
        "snapshots_checked": len(snapshots),
        "same_cart": cart_id,
        "fixed_line_conditions_retained": True,
        "blocked_api_requests": 4,
        "member_503_cases": 2,
        "final_version": 21,
        "final_total": 570,
        "purchases": 0,
        "local_tests": {"python": 71, "node": 74, "total": 145},
        "build_id": (ROOT / "frontend/.next/BUILD_ID").read_text().strip(),
        "sources_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names
        },
        "chrome_version": plistlib.loads(
            Path("/Applications/Google Chrome.app/Contents/Info.plist").read_bytes()
        )["CFBundleShortVersionString"],
        "macos_version": subprocess.check_output(["sw_vers", "-productVersion"], text=True).strip(),
        "tc03_overall": "not accepted; iPhone, camera/Code128 and owner acceptance remain",
    }
    with (EVIDENCE / "verification.json").open("x") as output:
        json.dump(proof, output, ensure_ascii=False, indent=2)
    print(
        json.dumps(
            {
                "offline_assertions": "passed",
                "snapshots": len(snapshots),
                "cases": 4,
                "purchases": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
