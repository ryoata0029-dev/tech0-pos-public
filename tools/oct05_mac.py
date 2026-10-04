"""Fresh October 5 Mac trial; fixed resources, no previous runtime reuse."""

import os
import sys

os.environ["M2_LOCAL_PROFILE"] = "oct05-mac"

if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1:3] == ["api-observe", "--tag"]:
        from oct05_api_observe import observe

        observe(sys.argv[3])
    elif len(sys.argv) > 1 and sys.argv[1] == "member-auto":
        from oct05_member_fixture import main

        main(sys.argv[2:])
    elif len(sys.argv) > 1 and sys.argv[1] == "recovery":
        from oct05_recovery_fixture import main

        del sys.argv[1]
        main()
    elif len(sys.argv) > 1 and sys.argv[1] == "api":
        from oct05_api_verify import main

        del sys.argv[1]
        main()
    elif len(sys.argv) == 4 and sys.argv[1:3] == ["verify", "--tag"]:
        from oct05_environment import verify

        verify(sys.argv[3])
    elif len(sys.argv) == 2 and sys.argv[1] in ("setup", "finish-setup"):
        from mac_recovery_setup import main

        os.umask(0o077)
        main(prepared=sys.argv[1] == "finish-setup")
    else:
        from mac_recovery_control import main

        main()
