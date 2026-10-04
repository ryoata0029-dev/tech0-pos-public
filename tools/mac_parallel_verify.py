"""Read fixed Mac-parallel evidence; write only a new offline verification JSON."""

import argparse
import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from itertools import pairwise
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/implementation/evidence/mac-parallel"
DB_KEYS = (
    "register",
    "contexts",
    "carts",
    "lines",
    "operations",
    "purchases",
    "purchase_lines",
    "purchase_taxes",
    "products",
)
TC01_STAGES = (
    "nonmember-ready",
    "nonmember-saved",
    "nonmember-next-empty",
    "nonmember-next-added",
)
TC02_EXPECTED = {
    "old200": ("product-late", 200, 200, "0001"),
    "old404": ("product-late-missing", 404, 404, "PRODUCT_NOT_FOUND"),
    "old503": ("product-late-unavailable", 200, 503, "SERVICE_UNAVAILABLE"),
    "aba200": ("product-late", 200, 200, "0001"),
}


class EvidenceError(Exception):
    """A saved evidence condition failed; messages do not include raw bodies."""


def require(condition, reason):
    if not condition:
        raise EvidenceError(reason)


def path_for(name):
    require(
        isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9_-]+\.(json|txt)", name),
        "Evidence filename must be a local basename",
    )
    path = EVIDENCE / name
    require(
        path.resolve().parent == EVIDENCE and EVIDENCE.resolve() == EVIDENCE,
        "Evidence path must remain in the fixed Mac-parallel directory",
    )
    return path


def read(name):
    try:
        value = json.loads(path_for(name).read_text())
    except json.JSONDecodeError:
        raise EvidenceError(f"Invalid JSON: {name}") from None
    require(isinstance(value, dict), "Evidence JSON must be an object")
    return value


def missing(names):
    return [name for name in names if not path_for(name).is_file()]


def text_evidence(name):
    require(name.endswith(".txt"), "Text evidence must have a txt extension")
    return path_for(name).read_text()


def when(value):
    require(isinstance(value, str), "Missing observation timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    # DB snapshots use an explicitly UTC column serialized without a timezone.
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def snapshot(name):
    value = read(name)
    require(
        all(isinstance(value.get(key), list) for key in DB_KEYS),
        "Snapshot must contain all nine database collections",
    )
    when(value["observed_at_utc"])
    require(
        value["stage"] == name.removeprefix("db-").removesuffix(".json"),
        "Snapshot stage and filename must agree",
    )
    return value


def compare_snapshots(before, after):
    """Ignore only stage/time metadata; never omit a business collection."""
    require(
        when(before["observed_at_utc"]) <= when(after["observed_at_utc"]),
        "Snapshot observations are out of order",
    )
    return {key: before[key] == after[key] for key in DB_KEYS}


def one(rows, reason):
    require(len(rows) == 1, reason)
    return rows[0]


def cart_in(value, cart_id):
    return one(
        [row for row in value["carts"] if row["cart_id"] == cart_id],
        "Expected exactly one matching cart",
    )


def current(value):
    register = one(value["register"], "Expected one REGISTER")
    require(
        register["register_id"] == 1
        and register["start_state"] == "READY"
        and register["maintenance_hold"] == 0,
        "REGISTER is not ready",
    )
    cart_id = register["current_cart_id"]
    require(
        isinstance(cart_id, str) and UUID(cart_id).version == 4,
        "Current cart is not a UUID4",
    )
    context = one(
        [row for row in value["contexts"] if row["context_id"] == register["active_context_id"]],
        "Active context is absent or ambiguous",
    )
    require(
        context["starting_staff_id"] == "STAFF_A"
        and context["confirmed_at"]
        and context["invalidated_at"] is None,
        "Active STAFF_A context is not confirmed",
    )
    return cart_in(value, cart_id)


def amount(value, expected):
    return Decimal(str(value)) == Decimal(str(expected))


def taxes(rows, rate_key):
    pairs = [
        (
            Decimal(str(row[rate_key])),
            Decimal(str(row["taxable_subtotal"])),
            Decimal(str(row["tax_amount"])),
        )
        for row in rows
    ]
    require(len({row[0] for row in pairs}) == len(pairs), "Duplicate tax-rate rows")
    return sorted(pairs)


def cart_taxes(cart):
    return taxes(json.loads(cart["tax_breakdown"]), "tax_rate")


def lines_in(value, cart_id):
    return sorted(
        [row for row in value["lines"] if row["cart_id"] == cart_id],
        key=lambda row: row["line_no"],
    )


def no_pending(cart):
    require(
        cart["pending_member_id"] is None and cart["active_member_operation_id"] is None,
        "Member request remains pending",
    )


def fixed_lines(rows):
    require(
        [(row["product_id"], row["quantity"]) for row in rows] == [(1, 3), (2, 1), (3, 1)],
        "Expected quantities 3/1/1 in the three product rows",
    )
    for row, price, rate in zip(rows, (103, 107, 107), ("0.10", "0.08", "0.08"), strict=True):
        require(
            amount(row["unit_price_snapshot"], price)
            and amount(row["tax_rate_snapshot"], rate)
            and amount(row["discount_per_unit"], 0)
            and amount(row["net_unit_price"], price)
            and amount(row["line_subtotal"], price * row["quantity"]),
            "Nonmember line prices, tax or subtotals differ from the fixture",
        )


def verify_tc01():
    names = [f"db-{stage}.json" for stage in TC01_STAGES]
    absent = missing(names)
    if absent:
        return {"status": "missing", "missing": absent}
    values = [snapshot(name) for name in names]
    ready, saved, empty, added = values
    require(
        all(when(a["observed_at_utc"]) <= when(b["observed_at_utc"]) for a, b in pairwise(values)),
        "TC01 snapshots are out of order",
    )
    first = current(ready)
    old_id = first["cart_id"]
    require(
        [(row["product_id"], row["code"]) for row in ready["products"]]
        == [(1, "0001"), (2, "0002"), (3, "0003")],
        "Product IDs do not identify the expected three fixture codes",
    )
    require(
        len(ready["carts"]) == 1 and first["state"] == "EDITING",
        "Ready cart is not EDITING",
    )
    require(
        not ready["purchases"] and not ready["purchase_lines"] and not ready["purchase_taxes"],
        "Sale already exists before the normal purchase",
    )
    require(first["active_purchase_operation_id"] is None, "A purchase is already pending")
    expected_tax = [
        (Decimal("0.08"), Decimal(214), Decimal(17)),
        (Decimal("0.10"), Decimal(309), Decimal(30)),
    ]
    for value in values:
        require(
            value["contexts"] == ready["contexts"] and value["products"] == ready["products"],
            "Context or product masters changed during the normal flow",
        )
        old = cart_in(value, old_id)
        require(
            old["staff_id"] == "STAFF_A"
            and old["member_id"] is None
            and old["member_state"] == "NON_MEMBER",
            "Saved cart is not the same nonmember/staff",
        )
        no_pending(old)
        require(
            amount(old["subtotal"], 523)
            and amount(old["total"], 570)
            and cart_taxes(old) == expected_tax,
            "Nonmember cart amounts differ from 570",
        )
        fixed_lines(lines_in(value, old_id))
        require(
            lines_in(value, old_id) == lines_in(ready, old_id),
            "Original line snapshots changed",
        )
    saved_cart = current(saved)
    require(
        len(saved["carts"]) == 1
        and saved_cart["cart_id"] == old_id
        and saved_cart["state"] == "SAVED"
        and saved_cart["version"] > first["version"],
        "Purchase did not save the original cart",
    )
    purchase = one(saved["purchases"], "Expected exactly one purchase")
    require(
        purchase["cart_id"] == old_id
        and purchase["staff_id"] == "STAFF_A"
        and purchase["member_id"] is None
        and amount(purchase["subtotal"], 523)
        and amount(purchase["total"], 570),
        "Purchase identity, staff or amounts differ",
    )
    require(
        when(ready["observed_at_utc"])
        <= when(purchase["purchased_at"])
        <= when(saved["observed_at_utc"]),
        "Purchase timestamp is outside the observed interval",
    )
    sale_lines = sorted(saved["purchase_lines"], key=lambda row: row["line_no"])
    require(
        len(sale_lines) == 3 and all(row["cart_id"] == old_id for row in sale_lines),
        "Expected three details belonging to the purchase",
    )
    fields = (
        "cart_id",
        "line_no",
        "product_id",
        "quantity",
        "unit_price_snapshot",
        "tax_rate_snapshot",
        "discount_per_unit",
        "net_unit_price",
        "line_subtotal",
    )
    require(
        [{key: row[key] for key in fields} for row in sale_lines]
        == [{key: row[key] for key in fields} for row in lines_in(ready, old_id)],
        "Purchase details do not preserve the edited line conditions",
    )
    require(
        len(saved["purchase_taxes"]) == 2
        and all(row["cart_id"] == old_id for row in saved["purchase_taxes"])
        and taxes(saved["purchase_taxes"], "tax_rate_snapshot") == expected_tax,
        "Expected two matching purchase tax rows",
    )
    purchase_op = one(
        [row for row in saved["operations"] if row["kind"] == "PURCHASE"],
        "Expected one purchase operation",
    )
    require(
        purchase_op["cart_id"] == old_id
        and purchase_op["status"] == "APPLIED"
        and purchase_op["applied_version"] == saved_cart["version"],
        "Purchase operation did not apply",
    )
    next_cart = current(empty)
    new_id = next_cart["cart_id"]
    require(
        len(empty["carts"]) == 2 and new_id != old_id and next_cart["state"] == "EDITING",
        "NEXT did not create a distinct current EDITING cart",
    )
    require(
        cart_in(empty, old_id)["state"] == "CLOSED"
        and cart_in(empty, old_id)["version"] > saved_cart["version"],
        "Old cart was not closed",
    )
    require(
        not lines_in(empty, new_id)
        and amount(next_cart["subtotal"], 0)
        and amount(next_cart["total"], 0)
        and cart_taxes(next_cart) == [],
        "Next cart is not empty",
    )
    require(
        next_cart["member_state"] == "UNSPECIFIED" and next_cart["member_id"] is None,
        "Next cart retained a member selection",
    )
    require(
        next_cart["active_purchase_operation_id"] is None
        and next_cart["purchase_prepared_version"] is None,
        "Next cart retained a purchase request",
    )
    no_pending(next_cart)
    next_op = one(
        [row for row in empty["operations"] if row["kind"] == "NEXT"],
        "Expected one NEXT",
    )
    require(
        next_op["cart_id"] == old_id
        and next_op["next_cart_id"] == new_id
        and next_op["status"] == "APPLIED",
        "NEXT identity or status differs",
    )
    for value in (empty, added):
        for key in ("purchases", "purchase_lines", "purchase_taxes"):
            require(
                value[key] == saved[key],
                "NEXT or the new addition changed the one saved sale",
            )
        require(
            [row for row in value["operations"] if row["kind"] == "PURCHASE"] == [purchase_op],
            "Purchase operation changed or another purchase was attempted",
        )
    last = current(added)
    require(
        len(added["carts"]) == 2
        and last["cart_id"] == new_id
        and last["staff_id"] == "STAFF_A"
        and last["state"] == "EDITING"
        and last["member_state"] == "UNSPECIFIED"
        and last["member_id"] is None,
        "New product did not remain in the same current nonmember cart",
    )
    no_pending(last)
    require(
        cart_in(added, old_id) == cart_in(empty, old_id),
        "Closed old cart changed after NEXT",
    )
    row = one(lines_in(added, new_id), "Expected one new product line")
    require(
        row["product_id"] == 1
        and row["quantity"] == 1
        and amount(row["unit_price_snapshot"], 103)
        and amount(row["tax_rate_snapshot"], "0.10")
        and amount(row["discount_per_unit"], 0)
        and amount(row["net_unit_price"], 103)
        and amount(row["line_subtotal"], 103)
        and amount(last["subtotal"], 103)
        and amount(last["total"], 113)
        and cart_taxes(last) == [(Decimal("0.10"), Decimal(103), Decimal(10))]
        and last["version"] > next_cart["version"],
        "Next product is not quantity1 / 113 yen",
    )
    require(current(empty)["staff_id"] == "STAFF_A", "Staff changed on NEXT")
    return {
        "status": "database_passed",
        "old_cart_id": old_id,
        "new_cart_id": new_id,
        "purchases": 1,
        "saved_total": 570,
        "next_total": 113,
        "evidence": names,
        "limits": [
            "DB does not prove UI input/selection clearing, login retention "
            "or single-click behavior",
            "GUI evidence requires a separate independent review",
        ],
    }


def product_input(dom):
    matches = re.findall(
        r'^\s*- textbox "商品コード"((?: \[[^\]\n]+\])*)(?:: ([^\n]*))?$',
        dom,
        re.MULTILINE,
    )
    flags, value = one(matches, "Expected exactly one product-code textbox")
    return flags, (value or "").strip('"')


def search_flags(dom):
    return one(
        re.findall(r'^\s*- button "検索"((?: \[[^\]\n]+\])*)$', dom, re.MULTILINE),
        "Expected exactly one search button",
    )


def verify_tc02_gui(case, gate_at, release_at, response_at, response):
    gui, network = case.get("gui"), case.get("browser_network")
    if not isinstance(gui, dict) or not isinstance(network, dict):
        return {"status": "missing", "missing": ["gui/browser_network metadata"]}
    keys = (
        (gui, "busy_dom_file"),
        (gui, "ready_dom_file"),
        (network, "status_file"),
        (network, "body_file"),
    )
    absent_keys = [key for value, key in keys if key not in value]
    if absent_keys:
        return {"status": "missing", "missing": absent_keys}
    names = [value[key] for value, key in keys]
    absent = missing(names)
    if absent:
        return {"status": "missing", "missing": absent}
    busy, ready, status_ax, body_ax = [text_evidence(name) for name in names]
    started, changed, ready_at, observed = [
        when(value)
        for value in (
            gui["started_at_utc"],
            gui["input_changed_at_utc"],
            gui["ready_at_utc"],
            network["observed_at_utc"],
        )
    ]
    elapsed_ms = (ready_at - started).total_seconds() * 1000
    require(
        started < gate_at and started < changed < release_at < response_at < ready_at <= observed,
        "GUI input/release/server reply/ready/Network observation order differs",
    )
    require(
        0 < elapsed_ms < 10000 and abs(elapsed_ms - gui["elapsed_ms"]) < 0.01,
        "GUI measured start-to-ready interval is not consistent or below 10 seconds",
    )
    request_code = "PRODUCT_MISSING" if case["id"] == "old404" else "0001"
    expected_input = "0001" if case["id"] == "aba200" else "0002"
    busy_flags, busy_code = product_input(busy)
    ready_flags, ready_code = product_input(ready)
    require(
        busy_code == request_code
        and "[disabled]" not in busy_flags
        and "[disabled]" in search_flags(busy)
        and ready_code == gui["input_after"] == expected_input
        and "[disabled]" not in ready_flags
        and "[disabled]" not in search_flags(ready)
        and all(
            gui[key] is True for key in ("search_exists", "search_enabled", "candidate_absent")
        ),
        "Busy input or ready input/search DOM differs from the expected state",
    )
    require(
        not re.search(r'^\s*- button "追加"(?: |$)', ready, re.MULTILINE)
        and " ／ 税抜単価 " not in ready
        and not re.search(r'^\s*- button "状態を再確認"(?: |$)', ready, re.MULTILINE)
        and not re.search(r"^\s*- status: .*操作を停止", ready, re.MULTILINE)
        and "商品が登録されていません。" not in ready
        and "状態を確認できません。" not in ready,
        "Old reply left a candidate or stopped the ready UI",
    )
    expected_status = response["status"]
    statuses = re.findall(
        r"^\s*\d+ セル (\d{3}) (?:OK|Not Found|Service Unavailable)$",
        status_ax,
        re.MULTILINE,
    )
    require(
        statuses == [str(expected_status)]
        and network["status"] == expected_status
        and network["body_code"] == response["body"]["code"]
        and network.get("request_code", request_code) == request_code,
        "Chrome Network status or case metadata differs from the actual server reply",
    )
    for ax in (status_ax, body_ax):
        requests = re.findall(
            r"^\s*\d+ セル https://[^/\s]+/api/products/([^\s]+)$", ax, re.MULTILINE
        )
        require(
            requests == [request_code] and "リクエスト 1 件" in ax,
            "Chrome Network did not isolate the one expected product request",
        )
    editors = re.findall(
        r"^\s*\d+ テキスト入力領域 \(settable\) コードエディタ, Value: (\{[^\n]*\})$",
        body_ax,
        re.MULTILINE,
    )
    body = json.loads(one(editors, "Expected one Chrome Response JSON editor"))
    require(
        body == response["body"]
        and "タブ (selected) レスポンス, Value: 1" in body_ax
        and "ヘッダー, Value: 0" in body_ax,
        "Chrome selected Response does not match the exact server body",
    )
    limits = [
        "Evidence confirms these empty-cart v2 cases only; deselect restrictions "
        "and whole TC02 acceptance are outside scope",
        "GUI UTC timestamps are controller observations, not a browser performance clock; "
        "Network observation was taken after ready",
    ]
    sequence = "changed_to_other_code"
    if case["id"] == "aba200":
        if (
            gui.get("input_sequence") == ["0001", "0002", "0001"]
            and isinstance(gui.get("sequence_evidence"), str)
            and gui["sequence_evidence"]
        ):
            trace_name = gui.get("sequence_evidence_file")
            if trace_name is None or missing([trace_name]):
                sequence = "reported_sequence_without_saved_trace"
                limits.append("ABA intermediate code has no saved CUA execution trace")
            else:
                trace = text_evidence(trace_name)
                require(
                    re.search(
                        r"await .*?\.fill\('0002'\);var t1=new Date\(\);"
                        r"if\(aba\)await .*?\.fill\('0001'\);",
                        trace,
                    )
                    and f"mpRunOldSearch('aba200','{case['tag']}','0001',true)" in trace,
                    "Saved normal CUA execution trace does not support ABA input sequence",
                )
                sequence = "normal_CUA_fill_sequence_supported_by_saved_trace"
                names.append(trace_name)
        else:
            sequence = "unverified_intermediate_code"
            limits.append("ABA intermediate code is absent from saved before/after DOM")
        limits.append("ABA return-to-0001 completion UTC was not separately measured")
    return {
        "status": "browser_and_gui_passed",
        "browser_http_arrival": "confirmed_exact_status_and_body",
        "ui_recovery_within_10_seconds": "confirmed",
        "elapsed_ms": gui["elapsed_ms"],
        "input_generation_sequence": sequence,
        "evidence": names,
        "limits": limits,
    }


def verify_tc02(case):
    case_id = case["id"]
    kind, lookup_status, response_status, response_code = TC02_EXPECTED[case_id]
    tag = case["tag"]
    require(
        isinstance(tag, str) and re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", tag),
        "Unsafe TC02 tag",
    )
    names = [
        case["before"],
        case["after"],
        f"gate-{tag}.json",
        f"release-after-{tag}.json",
        f"gate-response-{tag}.json",
    ]
    absent = missing(names)
    if absent:
        return {"id": case_id, "status": "missing", "missing": absent}
    before, after = snapshot(case["before"]), snapshot(case["after"])
    initial = current(before)
    require(
        len(before["carts"]) == 1
        and initial["state"] == "EDITING"
        and initial["version"] == 2
        and not before["lines"]
        and not before["purchases"]
        and amount(initial["total"], 0),
        "TC02 fixture is not the one empty EDITING cart v2 with zero sales",
    )
    equality = compare_snapshots(before, after)
    require(all(equality.values()), "Read-only product replies changed database state")
    gate, release, response = [read(name) for name in names[2:]]
    require(
        gate["kind"] == release["kind"] == kind
        and gate["tag"] == release["tag"] == tag
        and gate["after_real_lookup"] is True
        and gate["outside_read_transaction"] is True
        and gate["real_status"] == lookup_status,
        "Actual lookup gate classification differs",
    )
    require(
        gate["body"]["code"] == ("PRODUCT_NOT_FOUND" if case_id == "old404" else "0001")
        and response["status"] == response_status
        and response["body"]["code"] == response_code,
        "Exact server reply status or code differs",
    )
    gate_at, release_at, response_at = [
        when(value) for value in (gate["at_utc"], release["released_at_utc"], response["at_utc"])
    ]
    require(
        when(before["observed_at_utc"])
        <= gate_at
        <= release_at
        <= response_at
        <= when(after["observed_at_utc"]),
        "Gate/release/response/snapshot order differs",
    )
    require(
        when(release["gate_at_utc"]) == gate_at
        and gate_at <= when(release["observed_at_utc"]) <= release_at
        and release["after_real_lookup"] is True
        and release["outside_read_transaction"] is True,
        "Release helper did not observe the same actual gate",
    )
    require(
        2 <= release["wait_seconds"] <= 7
        and release_at > gate_at
        and 0 < (response_at - gate_at).total_seconds() < 10,
        "Server gate interval is outside the bounded short-reply window",
    )
    gui = verify_tc02_gui(case, gate_at, release_at, response_at, response)
    return {
        "id": case_id,
        "status": "missing"
        if gui["status"] == "missing"
        else "limited_condition_passed"
        if gui.get("input_generation_sequence")
        in ("unverified_intermediate_code", "reported_sequence_without_saved_trace")
        else "tested_condition_passed",
        "tag": tag,
        "lookup_status": lookup_status,
        "server_status": response_status,
        "gate_to_response_seconds": (response_at - gate_at).total_seconds(),
        "db_equal": equality,
        "evidence": names,
        "gui_network": gui,
        "browser_http_arrival": gui.get("browser_http_arrival", "unverified"),
        "ui_recovery_within_10_seconds": gui.get("ui_recovery_within_10_seconds", "unverified"),
        "limits": gui.get("limits", ["GUI/Network evidence is missing"]),
    }


def verify_environment():
    name = "mysql-environment.json"
    if missing([name]):
        return {"status": "missing", "missing": [name]}
    value = read(name)
    require(
        value["container"] == "tech0-pos-mac-parallel-mysql"
        and value["volume"] == "tech0-pos-mac-parallel-mysql-data"
        and value["port_binding"] == "127.0.0.1:3307 -> 3306"
        and value["tls_required"] is True,
        "Database environment is not the fixed Mac-parallel target",
    )
    return {"status": "identity_passed", "evidence": name}


def attempt(action):
    try:
        return action()
    except EvidenceError as error:
        return {"status": "failed", "reason": str(error)}
    except (KeyError, TypeError, ValueError, ArithmeticError, OSError) as error:
        return {
            "status": "failed",
            "reason": "Invalid or unreadable evidence schema",
            "error_type": type(error).__name__,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="final")
    args = parser.parse_args()
    require(re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", args.tag), "Unsafe output tag")
    manifest_name = "tc02-cases.json"
    tc02 = []
    if missing([manifest_name]):
        tc02 = [
            {"id": case_id, "status": "missing", "missing": [manifest_name]}
            for case_id in TC02_EXPECTED
        ]
    else:
        manifest = attempt(lambda: read(manifest_name))
        if "cases" not in manifest or not isinstance(manifest["cases"], list):
            tc02 = [{"status": "failed", "reason": "TC02 case manifest is invalid"}]
        else:
            cases = manifest["cases"]
            tags = [case.get("tag") for case in cases if isinstance(case, dict)]
            unique_tags = all(isinstance(tag, str) for tag in tags) and len(set(tags)) == len(tags)
            for case_id in TC02_EXPECTED:
                matches = [
                    case for case in cases if isinstance(case, dict) and case.get("id") == case_id
                ]
                if not matches:
                    tc02.append(
                        {
                            "id": case_id,
                            "status": "missing",
                            "missing": [f"case:{case_id}"],
                        }
                    )
                elif len(matches) != 1:
                    tc02.append(
                        {
                            "id": case_id,
                            "status": "failed",
                            "reason": "Duplicate TC02 case",
                        }
                    )
                elif not unique_tags:
                    tc02.append(
                        {
                            "id": case_id,
                            "status": "failed",
                            "reason": "TC02 tags must be distinct",
                        }
                    )
                else:
                    result = attempt(lambda case=matches[0]: verify_tc02(case))
                    result["id"] = case_id
                    tc02.append(result)
    tc01 = attempt(verify_tc01)
    environment = attempt(verify_environment)
    statuses = [
        environment["status"],
        tc01["status"],
        *(case["status"] for case in tc02),
    ]
    result = {
        "at_utc": datetime.now(UTC).isoformat(),
        "profile": "mac-parallel",
        "scope": (
            "Offline saved DB/gate/GUI/Chrome Response checks "
            "for the specified Mac-parallel conditions"
        ),
        "result": "failed"
        if "failed" in statuses
        else "incomplete"
        if "missing" in statuses
        else "limited",
        "environment": environment,
        "tc01": tc01,
        "tc02": tc02,
        "unverified": [
            "Whole TC02 acceptance and deselect restrictions in these empty-cart cases",
            "TC01 normal GUI sequence and clearing/login behavior",
            "TC03, iPhone, camera, overall TC acceptance and owner acceptance",
        ],
    }
    output = path_for(f"verification-mac-parallel-{args.tag}.json")
    with output.open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(
        json.dumps(
            {
                "result": result["result"],
                "output": output.name,
                "tc01": tc01["status"],
                "tc02": {case.get("id", "manifest"): case["status"] for case in tc02},
            }
        )
    )
    return 1 if result["result"] == "failed" else 2 if result["result"] == "incomplete" else 0


if __name__ == "__main__":
    raise SystemExit(main())
