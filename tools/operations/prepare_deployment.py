"""Create a local deployment directory from a Linux build. Never deploy or install."""

import argparse
import shutil
import sys
from pathlib import Path


def prepare(root: Path, output: Path) -> None:
    if (
        output.exists()
        or output.resolve().is_relative_to((root / "frontend").resolve())
        or output.resolve().is_relative_to((root / "backend").resolve())
    ):
        raise ValueError("A new output directory outside source trees is required")
    standalone = root / "frontend/.next/standalone"
    if not (standalone / "server.js").is_file() or not (root / "frontend/.next/static").is_dir():
        raise ValueError("Standalone build required")
    # Copy only the built app, not the repository, secret files, validation environments or DB.
    shutil.copytree(
        standalone,
        output / "frontend",
        ignore=shutil.ignore_patterns(".env*", "*.pem", "*.key", ".git"),
    )
    shutil.copytree(root / "frontend/.next/static", output / "frontend/.next/static")
    if (root / "frontend/public").is_dir():
        shutil.copytree(root / "frontend/public", output / "frontend/public")
    shutil.copytree(
        root / "backend/app", output / "backend/app", ignore=shutil.ignore_patterns("__pycache__")
    )
    shutil.copy2(root / "backend/requirements.lock", output / "backend/requirements.lock")
    for app in ("frontend", "backend"):
        (output / app / "infra").mkdir()
        shutil.copy2(root / f"infra/start-{app}.sh", output / app / f"infra/start-{app}.sh")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        if sys.platform != "linux":
            raise ValueError("Linux build host required")
        prepare(Path(__file__).resolve().parents[2], args.output)
        print(
            "Local files prepared; Linux dependencies, CA, settings "
            "and deployment are separate steps"
        )
        return 0
    except (ValueError, OSError):
        print("Preparation failed; inspect prerequisites, keep partial output for review")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
