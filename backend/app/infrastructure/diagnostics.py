"""Allowlisted diagnostics. Never format exceptions, SQL, headers or raw URLs."""

import json
import logging
import os
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

context: ContextVar[dict[str, str] | None] = ContextVar("pos_diagnostic", default=None)
logger = logging.getLogger("pos.events")
logger.propagate = False
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


def database_error(error: Exception) -> None:
    state = context.get()
    if state is None:
        return
    # Inspect only numeric driver errno; exception strings can contain SQL/credentials.
    original = getattr(error, "orig", None)
    arguments = getattr(original, "args", ())
    errno = arguments[0] if arguments and type(arguments[0]) is int else None
    state["db_error"] = {1205: "LOCK_TIMEOUT", 1213: "DEADLOCK"}.get(
        errno if errno is not None else -1, "DB_FAILURE"
    )


def event(
    *, request_id: str, route: str, elapsed_ms: float, status: int, state: dict[str, str]
) -> None:
    version = os.environ.get("POS_DEPLOYMENT_VERSION", "UNSET")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", version):
        version = "INVALID"
    value: dict[str, Any] = {
        "utc": datetime.now(UTC).isoformat(),
        "request_id": request_id,
        "operation_id": state.get("operation_id"),
        "api": route,
        "elapsed_ms": round(elapsed_ms, 2),
        "result_code": state.get("result_code", f"HTTP_{status}"),
        "db_error": state.get("db_error", "NONE"),
        "deployment_version": version,
    }
    try:
        logger.log(
            logging.ERROR if status >= 500 else logging.WARNING if status >= 400 else logging.INFO,
            json.dumps(value, separators=(",", ":")),
        )
    except Exception:
        # Diagnostics never decide whether a transaction saved successfully.
        pass
