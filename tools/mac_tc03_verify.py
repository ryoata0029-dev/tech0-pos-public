"""Offline verification of actual TC-03 records; a passing audit is not a passing TC-03."""

import hashlib
import json
import plistlib
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from m2_verify_https import Client

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/implementation/evidence/mac-tc03"


def read(name):
    return json.loads((EVIDENCE / name).read_text())


def dom(tag):
    return (EVIDENCE / f"ui-{tag}.txt").read_text()


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main():
    snapshots = {path.stem: read(path.name) for path in EVIDENCE.glob("db-*.json")}
    baseline = snapshots["db-lines-baseline"]
    fixed = (
        "cart_id",
        "line_id",
        "line_no",
        "product_id",
        "quantity",
        "unit_price_snapshot",
        "tax_rate_snapshot",
        "conditions_fixed_at",
    )
    identity = [{key: row[key] for key in fixed} for row in baseline["lines"]]
    assert [(row["product_id"], row["quantity"]) for row in identity] == [(1, 3), (2, 1), (3, 1)]
    for name, snapshot in snapshots.items():
        assert len(snapshot["carts"]) == 1
        cart = snapshot["carts"][0]
        assert cart["cart_id"] == baseline["carts"][0]["cart_id"]
        assert cart["state"] == "EDITING" and cart["staff_id"] == "STAFF_A"
        assert (
            not snapshot["purchases"]
            and not snapshot["purchase_lines"]
            and not snapshot["purchase_taxes"]
        )
        assert cart["active_purchase_operation_id"] is None
        assert not any(op["kind"] in ("PURCHASE", "NEXT") for op in snapshot["operations"])
        if name.startswith("db-empty-"):
            assert not snapshot["lines"] and cart["total"] == "0"
        else:
            assert [{key: row[key] for key in fixed} for row in snapshot["lines"]] == identity

    groups = (
        ("initial-notfound", "lines-initial-notfound"),
        ("change-notfound", "lines-change-notfound"),
        ("initial-unavailable", "lines-initial-unavailable"),
        ("change-unavailable", "lines-change-unavailable"),
        ("held", "initial-held"),
    )
    request_count = 0
    for api_tag, db_tag in groups:
        before, after = snapshots[f"db-{db_tag}-before-api"], snapshots[f"db-{db_tag}-after-api"]
        for key in (
            "carts",
            "lines",
            "operations",
            "purchases",
            "purchase_lines",
            "purchase_taxes",
        ):
            assert before[key] == after[key], "Blocked requests changed business state"
        record = read(f"api-{api_tag}-blocked.json")
        assert record["completed"] and record["before"] == record["after"]
        assert record["before"]["cart"]["member_state"] == "PENDING"
        assert len(record["requests"]) == 4
        assert [row["method"] for row in record["requests"]] == ["POST", "PATCH", "DELETE", "POST"]
        for row in record["requests"]:
            assert row["status"] == 409 and row["value"]["code"] == "STATE_CONFLICT"
            Client.validate(row["value"], "Error")
            request_version = (
                parse_qs(urlsplit(row["path"]).query)["version"][0]
                if row["method"] == "DELETE"
                else row["body"]["version"]
            )
            assert request_version == record["before"]["cart"]["version"]
            request_count += 1
    for tag in ("initial-notfound", "initial-unavailable", "held"):
        record = read(f"api-{tag}-member-get.json")
        assert record["completed"] and record["before"] == record["after"]
        assert record["requests"][0]["status"] == 200
        assert record["requests"][0]["value"]["member_id"] == "MEMBER_0"
        assert record["after"]["cart"]["member_state"] == "PENDING"
    for tag in (
        "initial-notfound",
        "change-notfound",
        "initial-unavailable",
        "change-unavailable",
        "held",
    ):
        view = dom(f"other-{tag}")
        assert "会員：会員確認待ち" in view and "変更前の参考額" in view
        for name in ("購入確定", "演習食品103円", "演習食品107円A", "演習食品107円B"):
            assert f'button "{name}" [disabled]' in view
        assert 'textbox "商品コード" [disabled]' in view

    defects = []
    for tag, db_tag in (
        ("empty-notfound", "empty-notfound"),
        ("empty-change-notfound", "empty-change-notfound"),
        ("lines-initial-notfound", "lines-initial-notfound-before-api"),
        ("lines-change-notfound", "lines-change-notfound-before-api"),
    ):
        view, snapshot = dom(tag), snapshots[f"db-{db_tag}"]
        assert "会員が見つかりません。再入力または非会員を選択してください。" in view
        assert "会員：会員確認待ち" in view and "変更前の参考額" in view
        for role, name in (
            ("textbox", "変更先の会員ID"),
            ("button", "照会・再照会"),
            ("button", "非会員として続ける"),
        ):
            assert f'{role} "{name}" [disabled]' in view
        cart = snapshot["carts"][0]
        assert cart["member_state"] == "PENDING"
        operation = next(
            op
            for op in snapshot["operations"]
            if op["operation_id"] == cart["active_member_operation_id"]
        )
        assert operation["status"] == "REJECTED" and operation["result_code"] == "MEMBER_NOT_FOUND"
        defects.append(
            {
                "condition": tag,
                "priority": "P2",
                "result": "failed",
                "defect": (
                    "definite member-not-found followed by stable cart GET "
                    "leaves member controls disabled"
                ),
            }
        )
    late_results = []
    for tag, api_tag in (
        ("initial-held", "initial-new-member"),
        ("change-held", "change-new-nonmember"),
        ("initial-fast", "initial-fast-new-member"),
    ):
        gate, held = read(f"gate-{tag}.json"), read(f"lookup-held-{tag}.json")
        released, finished = (
            read(f"lookup-released-{tag}.json"),
            read(f"lookup-finished-{tag}.json"),
        )
        chosen = read(f"api-{api_tag}.json")
        assert gate["after_real_receipt_commit"] and held["found"] and held["after_real_lookup"]
        assert held["outside_update_transaction"]
        assert chosen["completed"]
        assert (
            timestamp(held["at_utc"])
            < timestamp(chosen["finished_at_utc"])
            < timestamp(released["at_utc"])
            <= timestamp(finished["at_utc"])
        )
        assert finished["operation_id"] == gate["operation_id"] == held["operation_id"]
        assert (
            finished["operation_status"] == "REJECTED"
            and finished["code"] == "MEMBER_LOOKUP_SUPERSEDED"
        )
        assert finished["cart"] == chosen["after"]["cart"]
        delay = (timestamp(finished["at_utc"]) - timestamp(gate["at_utc"])).total_seconds()
        if tag != "initial-held":
            assert delay < 10
            old_view = dom(
                "change-old-response" if tag == "change-held" else "initial-fast-old-response"
            )
            assert "操作を停止しました。状態を確認してください。" in old_view
            assert "paragraph: 会員：MEMBER_1" not in old_view
            Client.validate(chosen["requests"][0]["value"], "OperationResult")
        else:
            assert delay > 10
            assert (
                snapshots["db-initial-new-member-before-release"]["carts"]
                == snapshots["db-initial-new-member-after-release"]["carts"]
            )
            assert (
                snapshots["db-initial-new-member-before-release"]["lines"]
                == snapshots["db-initial-new-member-after-release"]["lines"]
            )
        late_results.append(
            {
                "tag": tag,
                "receipt_to_finish_seconds": delay,
                "old_operation": "REJECTED/MEMBER_LOOKUP_SUPERSEDED",
                "new_member_id": finished["cart"]["member_id"],
                "new_total": finished["cart"]["total"],
                "old_browser_response_observed_before_relay_timeout": tag != "initial-held",
            }
        )
    for tag in (
        "empty-change-unavailable",
        "empty-initial-unavailable",
        "lines-initial-unavailable",
        "lines-change-unavailable",
    ):
        gate, response = read(f"gate-{tag}.json"), read(f"gate-response-{tag}.json")
        assert gate["after_real_receipt_commit"] and gate["member_state"] == "PENDING"
        assert response["status"] == 503
        assert 3 <= (timestamp(response["at_utc"]) - timestamp(gate["at_utc"])).total_seconds() < 10
    final = snapshots["db-final"]["carts"][0]
    assert (
        final["member_state"] == "NON_MEMBER"
        and final["member_id"] is None
        and final["total"] == "570"
    )
    for name in ("変更前の参考額", "指定結果は未確認"):
        assert name not in dom("final-nonmember")
    previous = json.loads(
        (ROOT / "docs/implementation/evidence/member-display-fix/verification.json").read_text()
    )
    for name, expected in previous["sources_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert (ROOT / "frontend/.next/BUILD_ID").read_text().strip() == previous["build_id"]
    chrome = plistlib.loads(
        Path("/Applications/Google Chrome.app/Contents/Info.plist").read_bytes()
    )
    proof = {
        "at_utc": datetime.now(UTC).isoformat(),
        "evidence_assertions": "passed",
        "tc03_overall": "failed; P2 remains; device/camera conditions outside current scope",
        "defect_count": 1,
        "defect_reproductions": defects,
        "snapshots_checked": len(snapshots),
        "same_cart": True,
        "lines": 3,
        "purchases": 0,
        "blocked_api_requests": request_count,
        "member_get_did_not_confirm_cart": True,
        "late_lookup_results": late_results,
        "final_total": 570,
        "build_id": previous["build_id"],
        "application_sources_sha256": previous["sources_sha256"],
        "chrome_version": chrome["CFBundleShortVersionString"],
        "macos_version": subprocess.check_output(["sw_vers", "-productVersion"], text=True).strip(),
    }
    with (EVIDENCE / "verification.json").open("x") as output:
        json.dump(proof, output, ensure_ascii=False, indent=2)
    print(json.dumps(proof, ensure_ascii=False))


if __name__ == "__main__":
    main()
