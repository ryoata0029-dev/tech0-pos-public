"""Install only reviewed local observers on the fixed October 5 runtime."""

from m2_local_profile import PROFILE

if PROFILE != "oct05-mac":
    raise ValueError("Only the fresh October 5 profile is allowed")

from mac_tc02_backend import app  # noqa: E402, F401
from oct05_member_fixture import install  # noqa: E402
from oct05_recovery_fixture import install_next_gate  # noqa: E402

install()
install_next_gate()
