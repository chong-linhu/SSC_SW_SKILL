#!/usr/bin/env python3
"""SSC‑Series Switch Control CLI — bootstrap entry‑point.
This file only loads compiled binary implementation module and invoke main entry.
No business logic implemented in source‑code text form.
Implementation compiled as native binary extension module for distribution.
Binary purpose, behavior boundaries and SHA-256 checksums are disclosed in
SECURITY_DISCLOSURE.md (package root); verify integrity offline via
`python verify_checksums.py`.
"""

import platform
import sys

REQUIRED_PY = (3, 13)

try:
    from _ssc_cli import main
except Exception as exc:  # noqa: BLE001
    v = sys.version_info
    print("[ERROR] Failed loading compiled binary extension module _ssc_cli.", file=sys.stderr)
    print("       This binary build compiled for Windows x64 + Python %d.%d." % REQUIRED_PY,
          file=sys.stderr)
    print("       Current runtime environment: %s %s / Python %d.%d.%d" % (
        platform.system(), platform.machine(), v.major, v.minor, v.micro),
        file=sys.stderr)
    print("       Raw exception detail: %s" % exc, file=sys.stderr)
    print("       Obtain a build matching this environment; binary integrity can", file=sys.stderr)
    print("       be verified with `python verify_checksums.py`", file=sys.stderr)
    print("       (see SECURITY_DISCLOSURE.md for details).", file=sys.stderr)
    raise SystemExit(3)
    
    
if __name__ == "__main__":
    raise SystemExit(main())
