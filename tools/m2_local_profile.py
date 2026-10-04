"""Fixed, isolated M2 harness profiles; never accept arbitrary resource names."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = os.environ.get("M2_LOCAL_PROFILE", "initial")
if PROFILE not in (
    "initial",
    "browser",
    "mac",
    "m3",
    "m4",
    "mac-flow",
    "mac-recovery",
    "mac-restart",
    "mac-member",
    "mac-tc03",
    "mac-tc03-fix",
    "mac-tc02",
    "mac-batch",
    "mac-parallel",
    "parallel-next",
    "parallel-mac-next",
    "oct05-mac",
    "iphone-camera",
):
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
elif PROFILE == "m4":
    LOCAL = ROOT / ".m4-local"
    EVIDENCE = ROOT / "docs/implementation/evidence/m4"
    NAME = "tech0-pos-m4-mysql"
elif PROFILE == "mac-flow":
    LOCAL = ROOT / ".mac-flow-local"
    EVIDENCE = ROOT / "docs/implementation/evidence/mac-flow"
    NAME = "tech0-pos-mac-flow-mysql"
elif PROFILE == "mac-recovery":
    LOCAL = ROOT / ".mac-recovery-local"
    EVIDENCE = ROOT / "docs/implementation/evidence/mac-recovery"
    NAME = "tech0-pos-mac-recovery-mysql"
elif PROFILE == "mac-restart":
    LOCAL = ROOT / ".mac-restart-local"
    EVIDENCE = ROOT / "docs/implementation/evidence/mac-restart"
    NAME = "tech0-pos-mac-restart-mysql"
elif PROFILE == "mac-member":
    LOCAL = ROOT / ".mac-member-local"
    EVIDENCE = ROOT / "docs/implementation/evidence/mac-member"
    NAME = "tech0-pos-mac-member-mysql"
elif PROFILE == "mac-tc03":
    LOCAL = ROOT / ".mac-tc03-local"
    EVIDENCE = ROOT / "docs/implementation/evidence/mac-tc03"
    NAME = "tech0-pos-mac-tc03-mysql"
elif PROFILE == "mac-tc03-fix":
    LOCAL = ROOT / ".mac-tc03-fix-local"
    EVIDENCE = ROOT / "docs/implementation/evidence/mac-tc03-fix"
    NAME = "tech0-pos-mac-tc03-fix-mysql"
elif PROFILE == "mac-tc02":
    LOCAL = ROOT / ".mac-tc02-local"
    EVIDENCE = ROOT / "docs/implementation/evidence/mac-tc02"
    NAME = "tech0-pos-mac-tc02-mysql"
elif PROFILE == "mac-batch":
    LOCAL = ROOT / ".mac-batch-local"
    EVIDENCE = ROOT / "docs/implementation/evidence/mac-batch"
    NAME = "tech0-pos-mac-batch-mysql"
elif PROFILE == "mac-parallel":
    LOCAL = ROOT / ".mac-parallel-local"
    EVIDENCE = ROOT / "docs/implementation/evidence/mac-parallel"
    NAME = "tech0-pos-mac-parallel-mysql"
elif PROFILE == "parallel-next":
    LOCAL = ROOT / ".parallel-next-local"
    EVIDENCE = ROOT / "docs/implementation/evidence/parallel-next"
    NAME = "tech0-pos-parallel-next-mysql"
elif PROFILE == "parallel-mac-next":
    LOCAL = ROOT / ".parallel-mac-next-local"
    EVIDENCE = ROOT / "docs/implementation/evidence/parallel-mac-next"
    NAME = "tech0-pos-parallel-mac-next-mysql"
elif PROFILE == "oct05-mac":
    LOCAL = ROOT / ".oct05-mac-local"
    EVIDENCE = ROOT / "docs/implementation/evidence/oct05-mac"
    NAME = "tech0-pos-oct05-mac-mysql"
elif PROFILE == "iphone-camera":
    LOCAL = ROOT / ".iphone-camera-local"
    EVIDENCE = ROOT / "docs/implementation/evidence/iphone-camera"
    NAME = "tech0-pos-iphone-camera-mysql"
VOLUME = NAME + "-data"
MYSQL_PORT, FRONTEND_PORT, BACKEND_PORT = {
    "parallel-mac-next": (3317, 8453, 8454),
    "oct05-mac": (3327, 8463, 8464),
}.get(PROFILE, (3307, 8443, 8444))
