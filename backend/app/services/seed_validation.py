"""Validate synthetic member rows before MySQL can coerce or truncate values."""

from typing import Any

from app.services.validation import code


def validate_member(row: dict[str, Any]) -> None:
    if set(row) != {"member_id", "name", "phone", "address", "gender", "age"}:
        raise ValueError("Member must have exactly the six required attributes")
    code(row["member_id"])
    for key in ("name", "phone", "address", "gender"):
        value = row[key]
        if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 65535:
            raise ValueError("Member text must be nonempty and fit MySQL TEXT")
    age = row["age"]
    if type(age) is not int or not 0 <= age <= 4294967295:
        raise ValueError("Member age must be an unsigned integer without coercion")
