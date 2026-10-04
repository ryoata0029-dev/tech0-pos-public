"""Observe only the original failed API fixture; never resolve, repair or retry it."""

import json
from datetime import UTC, datetime

import oct05_api_verify as api


def observe(tag):
    if not tag.replace("-", "").isalnum() or api.DB != "pos_oct05_api":
        raise ValueError("Only the original fixed fixture and an unused tag are allowed")
    target = api.OUT / f"api-original-{tag}.json"
    if target.exists():
        raise ValueError("Original observation already exists")
    api.guard()
    metadata = api.snapshot()
    data = api.EVIDENCE["snapshots"][metadata["projection_sha256"]]["data"]
    result = {
        "at_utc": datetime.now(UTC).isoformat(),
        "database": api.DB,
        "purpose": "read-only observation of failed validation fixture, no recovery action",
        "metadata": metadata,
        "data": data,
    }
    rendered = json.dumps(result, indent=2, default=api.encode)
    with target.open("x") as output:
        output.write(rendered)
    print(json.dumps({"database": api.DB, "projection_sha256": metadata["projection_sha256"]}))
