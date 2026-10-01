"""Fixed, isolated M2 harness profiles; never accept arbitrary resource names."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = os.environ.get("M2_LOCAL_PROFILE", "initial")
if PROFILE not in ("initial", "browser", "mac", "m3"):
    raise ValueError("Unknown M2 local profile")
LOCAL = ROOT / ".m2-local"
EVIDENCE = ROOT / "docs/implementation/evidence/m2"
NAME = "tech0-pos-m2-mysql"
if PROFILE == "browser":
    LOCAL = LOCAL / "browser"
    EVIDENCE = EVIDENCE / "browser"
    NAME = "tech0-pos-m2-browser-mysql"
elif PROFILE == "mac":
    LOCAL = LOCAL / "mac"
    EVIDENCE = EVIDENCE / "mac"
    NAME = "tech0-pos-m2-mac-mysql"
if PROFILE == "m3":
    LOCAL = ROOT / ".m3-local"
    EVIDENCE = ROOT / "docs/implementation/evidence/m3"
    NAME = "tech0-pos-m3-mysql"
VOLUME = NAME + "-data"
