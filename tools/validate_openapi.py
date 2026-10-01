"""Validate the authoritative contract locally; never fetch external references."""

import json
from pathlib import Path

from openapi_spec_validator import validate

path = Path(__file__).resolve().parents[1] / "API契約.openapi.json"
spec = json.loads(path.read_text())


def check_refs(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "$ref" and (not isinstance(item, str) or not item.startswith("#/")):
                raise ValueError("External OpenAPI references are not permitted")
            check_refs(item)
    elif isinstance(value, list):
        for item in value:
            check_refs(item)


check_refs(spec)
validate(spec)
methods = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
operations = sum(key in methods for path in spec["paths"].values() for key in path)
print(f"OpenAPI {spec['openapi']}: valid ({operations} operations)")
