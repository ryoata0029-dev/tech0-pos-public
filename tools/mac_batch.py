"""Fixed fresh Mac batch trial; no reset/reuse of earlier resources."""

import os
import sys

os.environ["M2_LOCAL_PROFILE"] = "mac-batch"


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "setup":
        from mac_recovery_setup import main

        os.umask(0o077)
        main()
    elif len(sys.argv) > 1 and sys.argv[1] == "release-after":
        from mac_product_release import release_after

        release_after()
    else:
        from mac_recovery_control import main

        main()
