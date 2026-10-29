#!/usr/bin/env python3
"""Verify SHA-256 checksums of the compiled binary modules in this directory.

Pure-Python, read-only, no network access. Run from anywhere:

    python verify_checksums.py            # verify against SHA256SUMS.txt
    python verify_checksums.py --quiet    # exit code only

Exit codes: 0 = all match, 1 = mismatch/missing file, 2 = manifest missing.
"""

import hashlib
import os
import sys

MANIFEST = "SHA256SUMS.txt"


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    manifest_path = os.path.join(here, MANIFEST)
    if not os.path.isfile(manifest_path):
        print(f"[ERROR] Manifest not found: {manifest_path}", file=sys.stderr)
        return 2

    failures = 0
    checked = 0
    with open(manifest_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            expected, name = line.split(None, 1)
            name = name.strip()
            target = os.path.join(here, name)
            if not os.path.isfile(target):
                print(f"[MISSING] {name}")
                failures += 1
                continue
            digest = hashlib.sha256(open(target, "rb").read()).hexdigest()
            if digest == expected:
                print(f"[OK]      {name}")
                checked += 1
            else:
                print(f"[MISMATCH] {name}\n           expected {expected}\n           actual   {digest}")
                failures += 1

    if "--quiet" not in sys.argv:
        print(f"\n{checked} file(s) verified, {failures} failure(s).")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
