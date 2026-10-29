#!/usr/bin/env python3
"""云网管(SSC)系列交换机控制 CLI —— 启动壳。

本文件只负责加载已编译的实现模块并执行,不含业务逻辑。
实现已编译为本机扩展,以二进制形式分发。
二进制的用途、行为边界与 SHA-256 校验值见包根目录 SECURITY_DISCLOSURE.md;
可运行 `python verify_checksums.py` 离线校验二进制完整性。
"""

import platform
import sys

REQUIRED_PY = (3, 13)

try:
    from _ssc_cli import main
except Exception as exc:  # noqa: BLE001
    v = sys.version_info
    print("[错误] 无法加载已编译的实现模块 _ssc_cli。", file=sys.stderr)
    print("       本版本为 Windows x64 + Python %d.%d 构建。" % REQUIRED_PY,
          file=sys.stderr)
    print("       当前环境: %s %s / Python %d.%d.%d" % (
        platform.system(), platform.machine(), v.major, v.minor, v.micro),
        file=sys.stderr)
    print("       原始错误: %s" % exc, file=sys.stderr)
    print("       请获取与当前环境匹配的版本;二进制完整性可用", file=sys.stderr)
    print("       `python verify_checksums.py` 校验(详见 SECURITY_DISCLOSURE.md)。",
          file=sys.stderr)
    raise SystemExit(3)


if __name__ == "__main__":
    raise SystemExit(main())
