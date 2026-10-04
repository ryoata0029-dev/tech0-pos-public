"""Fresh fixed continuation trial, isolated from every previous runtime."""

import os
import sys

os.environ["M2_LOCAL_PROFILE"] = "parallel-next"

if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] in ("setup", "finish-setup"):
        from mac_recovery_setup import main

        os.umask(0o077)
        main(prepared=sys.argv[1] == "finish-setup")
    elif len(sys.argv) > 1 and sys.argv[1] == "release-after":
        from mac_product_release import release_after

        release_after()
    else:
        from mac_recovery_control import main

        main()
