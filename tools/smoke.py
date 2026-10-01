"""Local M2 fail-closed process smoke check. No DB, credentials, camera or external request."""

import json
import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def request(url: str) -> tuple[int, bytes]:
    try:
        with OPENER.open(url, timeout=2) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def smoke(name: str, command: list[str], cwd: Path, expected: int) -> dict[str, object]:
    port = available_port()
    command = [arg.replace("{port}", str(port)) for arg in command]
    url = f"http://127.0.0.1:{port}/"
    process = subprocess.Popen(
        command,
        cwd=cwd,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 30
        while True:
            if process.poll() is not None:
                raise RuntimeError(f"{name} exited before readiness: {process.returncode}")
            try:
                status, body = request(url)
                break
            except (urllib.error.URLError, TimeoutError):
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"{name} startup timed out") from None
                time.sleep(0.1)
        if status != expected:
            raise RuntimeError(f"{name}: unexpected HTTP {status}")
        if name == "frontend" and "レジの利用開始".encode() not in body:
            raise RuntimeError("Frontend startup page missing")
        # No configuration: API must fail closed without accessing a DB.
        for path in ("api/products/0001", "api/auth/status"):
            if request(url + path)[0] != 503:
                raise RuntimeError(f"{name}: unexpected business endpoint")
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGINT)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=10)
    try:
        request(url)
    except (urllib.error.URLError, TimeoutError):
        return {"name": name, "http_status": status, "stopped": True}
    raise RuntimeError(f"{name} still answers after shutdown")


results = [
    smoke(
        "backend",
        [
            str(ROOT / "backend/.venv/bin/python"),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "{port}",
            "--no-access-log",
        ],
        ROOT / "backend",
        404,
    ),
    smoke(
        "frontend",
        ["sh", "tools/frontend.sh", "run", "start", "--", "--port", "{port}"],
        ROOT,
        200,
    ),
]
print(
    json.dumps(
        {"scope": "M2 local HTTP fail-closed process smoke only", "results": results},
        indent=2,
    )
)
