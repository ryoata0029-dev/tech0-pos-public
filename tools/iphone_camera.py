"""Fixed fresh iPhone-camera trial; never reuse earlier resources."""

import os
import sys

os.environ["M2_LOCAL_PROFILE"] = "iphone-camera"

if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "setup":
        from mac_recovery_setup import main

        os.umask(0o077)
        main()
    else:
        from mac_recovery_control import main

        main()
