"""Audit retained TC-02 evidence; never start DB or operate the browser."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/implementation/evidence/mac-tc02"


def read(name):
    return json.loads((EVIDENCE / name).read_text())


def dom(tag):
    return (EVIDENCE / f"ui-{tag}.txt").read_text()


def main():
    snapshots = {p.stem: read(p.name) for p in EVIDENCE.glob("db-*.json")}
    assert len(snapshots) == 5
    first, repeated = snapshots["db-first-added"], snapshots["db-repeat-added"]
    assert len(first["lines"]) == len(repeated["lines"]) == 1
    for key in (
        "cart_id",
        "line_id",
        "line_no",
        "product_id",
        "unit_price_snapshot",
        "tax_rate_snapshot",
        "conditions_fixed_at",
    ):
        assert first["lines"][0][key] == repeated["lines"][0][key]
    assert first["lines"][0]["quantity"] == 1
    assert repeated["lines"][0]["quantity"] == 2
    assert first["carts"][0]["total"] == "113"
    assert repeated["carts"][0]["total"] == "226"
    assert first["carts"][0]["version"] == 3 and repeated["carts"][0]["version"] == 4
    assert [op["kind"] for op in repeated["operations"]].count("ADD_LINE") == 2
    for name, snapshot in snapshots.items():
        assert len(snapshot["carts"]) == 1
        assert snapshot["carts"][0]["cart_id"] == first["carts"][0]["cart_id"]
        assert snapshot["carts"][0]["state"] == "EDITING"
        assert not snapshot["purchases"] and not snapshot["purchase_lines"]
        assert not snapshot["purchase_taxes"]
        if name not in ("db-first-added", "db-repeat-added"):
            assert {k: v for k, v in snapshot.items() if k not in ("stage", "observed_at_utc")} == {
                k: v for k, v in repeated.items() if k not in ("stage", "observed_at_utc")
            }
    for tag in ("first-added", "repeat-added"):
        assert 'textbox "商品コード"\n' in dom(tag)
        assert 'button "追加"' not in dom(tag)
    assert 'button "追加"' in dom("before-code-change")
    assert 'textbox "商品コード" [active]: "0002"' in dom("code-changed")
    assert 'button "追加"' not in dom("code-changed")
    assert "paragraph: 追加時に価格を確定" not in dom("code-changed")
    assert "演習食品107円A ／ 税抜単価 107円" in dom("new-code-lookup")
    assert "商品が登録されていません。" in dom("missing")
    assert 'button "追加"' not in dom("missing")
    assert "状態を確認できません。内容を保持して停止してください。" in dom("unavailable")
    assert "商品が登録されていません。" not in dom("unavailable")
    assert 'button "追加"' not in dom("unavailable")
    assert 'button "追加"' in dom("after-unavailable-relookup")
    gates = {}
    for tag, status in (("lookup-unavailable", 503), ("lookup-held", 200)):
        gate, response = read(f"gate-{tag}.json"), read(f"gate-response-{tag}.json")
        assert gate["after_real_lookup"] and gate["outside_read_transaction"]
        assert gate["real_status"] == 200 and gate["product"]["code"] == "0001"
        assert response["status"] == status
        elapsed = (
            datetime.fromisoformat(response["at_utc"]) - datetime.fromisoformat(gate["at_utc"])
        ).total_seconds()
        assert 0 < elapsed < 10
        gates[tag] = {"status": status, "elapsed_seconds": elapsed}
    assert not read("ui-held-input.json")["enabled"]
    assert not read("ui-held-input.json")["actual_change_performed"]
    assert 'textbox "商品コード" [disabled]: "0001"' in dom("lookup-held")
    assert 'button "追加"' not in dom("lookup-held")
    assert 'textbox "商品コード": "0001"' in dom("lookup-released")
    assert 'button "追加"' in dom("lookup-released")
    runtime = read("runtime.json")
    for file, digest in runtime["sources_sha256"].items():
        assert hashlib.sha256((ROOT / file).read_bytes()).hexdigest() == digest
    shutdown = read("shutdown-final.json")
    assert all(shutdown["ports_closed"].values()) and shutdown["container_status"] == "exited"
    assert shutdown["volume_retained"] == "tech0-pos-mac-tc02-mysql-data"
    assert shutdown["secrets_absent_from_git_candidates_and_logs"]
    result = {
        "at_utc": datetime.now(UTC).isoformat(),
        "audit_result": "passed",
        "tc02_overall": "failed_and_incomplete",
        "db_snapshots": len(snapshots),
        "cart_id": repeated["carts"][0]["cart_id"],
        "line_id": repeated["lines"][0]["line_id"],
        "final_quantity": 2,
        "purchases": 0,
        "gates": gates,
        "passed_scope": [
            "same_line_increment_and_fixed_conditions",
            "success_input_clear",
            "result_clear_on_code_change_after_lookup",
            "missing_and_unavailable_distinguished",
            "normal_relookup",
            "read_only_searches_keep_db_unchanged",
            "held_200_release",
        ],
        "failed_scope": {"TC02-P2-01": "product code input disabled during lookup"},
        "unconfirmed_scope": [
            "changed_code_then_old_response",
            "iPhone",
            "camera",
            "full_TC02",
            "owner_acceptance",
        ],
        "missing_http_capture": "No direct HTTP capture; checked UI and actual fixture",
        "application_unchanged": True,
        "environment_stopped": True,
    }
    (EVIDENCE / "verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
