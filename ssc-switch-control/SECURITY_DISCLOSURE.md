# Binary Modules Security Disclosure / 二进制模块安全披露

This skill ships five compiled CPython extension modules (`.pyd`, Windows PE DLLs).
This document discloses their purpose, behavior boundaries, and integrity checksums
so that they can be reviewed and verified before use.

本技能包含 5 个编译后的 CPython 扩展模块（`.pyd`，即 Windows PE DLL）。本文档披露
其用途、行为边界与完整性校验值，供安全审查与使用前核验。

## 1. Why binaries / 为什么使用二进制

The implementation is compiled to `.pyd` to protect the reverse-engineered private
protocol details of the SSC switch series from being casually repackaged. The CLI
entry point (`switchctl.py`) is plain readable Python and contains **no business
logic** — it only imports the compiled implementation and calls `main()`.

实现代码被编译为 `.pyd`，目的是保护对 SSC 系列交换机私有协议的逆向成果不被随意
二次打包。CLI 入口 `switchctl.py` 为纯文本 Python、无任何业务逻辑，仅负责加载
编译实现并调用 `main()`。

## 2. Module inventory / 模块清单

| File | Purpose | Original Python source |
|------|---------|------------------------|
| `_ssc_cli.cp313-win_amd64.pyd` | CLI implementation: argument parsing, all ~30 subcommands (`search`, `login`, `state`, `cmd-all`, port/VLAN/PoE control, `raw` passthrough...) | CLI 实现：参数解析与全部子命令 |
| `ssc_web.cp313-win_amd64.pyd` | WEB channel HTTP client (`SSCWebClient`): POST plain JSON to `http://<device-ip>/<cmd>`, manual Cookie session handling | WEB 通道 HTTP 客户端 |
| `ssc_udp.cp313-win_amd64.pyd` | UDP multicast client (`SSCUdpClient`): LAN device discovery (239.0.0.100:10086), security verification | UDP 组播客户端（设备发现/安全验证） |
| `ssc_protocol.cp313-win_amd64.pyd` | Protocol core: command registry, message codecs, port masks/opcodes, state decoding | 协议核心：命令注册表、编解码、端口掩码 |
| `tea.cp313-win_amd64.pyd` | TEA block cipher + base64 framing for the UDP/cloud channels | TEA 加解密与封帧（UDP/云通道用） |

## 3. Behavior boundaries / 行为边界

The binaries **do**:
- Talk to the **user-specified** device only: HTTP to `SSC_HOST` (default port 80),
  and UDP multicast `239.0.0.100:10086` for LAN discovery.
- Persist the device session cookie to `~/.ssc_switch_sessions/<host>.cookie`.

The binaries **do not**:
- Contain any hardcoded device address, account, or password.
- Contact any server other than the local LAN device the user targets.
- Collect telemetry, usage statistics, or environment fingerprints.
- Spawn processes, write files outside the session-cookie path, or modify the system.

二进制模块**只会**：与用户指定的设备通信（HTTP 指向 `SSC_HOST`；UDP 组播
239.0.0.100:10086 用于局域网发现）；将会话 Cookie 持久化到
`~/.ssc_switch_sessions/<host>.cookie`。

二进制模块**不会**：内嵌任何设备地址/账号/密码；连接用户目标之外的任何服务器；
收集遥测数据；派生进程、越权写文件或修改系统。

## 4. Integrity verification / 完整性校验

SHA-256 checksums are published in `scripts/SHA256SUMS.txt`. Verify with the bundled
readable script (pure Python, no network):

```bash
cd scripts
python verify_checksums.py
```

Expected output ends with `5 file(s) verified, 0 failure(s).` Any mismatch means the
binary has been tampered with or corrupted — do not use it.

SHA-256 校验值发布于 `scripts/SHA256SUMS.txt`。可使用附带的纯 Python 可读脚本
`verify_checksums.py` 校验；输出应以 `5 file(s) verified, 0 failure(s).` 结尾。
任何不匹配都说明文件被篡改或损坏，请勿使用。

## 5. Runtime requirement / 运行环境要求

The shipped binaries are built for **Windows x64 + CPython 3.13 only**
(`cp313-win_amd64` tag). On other platforms / Python versions the CLI entry point
fails fast with a clear error message (see `switchctl.py`). The only third-party
runtime dependency is `requests` (used by the WEB channel).

随包二进制仅为 **Windows x64 + CPython 3.13** 构建（`cp313-win_amd64`）。其他平台
或 Python 版本下，CLI 入口会立即报错退出并给出环境说明。唯一第三方运行依赖为
`requests`（WEB 通道使用）。
