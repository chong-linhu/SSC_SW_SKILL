---
name: ssc-switch-control
display_name: SSC Switch Control
display_name_zh: 云网管交换机控制
display_name_en: SSC Switch Control
description: Control cloud-managed (SSC) series switches through their private interfaces. Use it when the user needs to query or configure such switches - discovering devices on the LAN via UDP multicast, reading device status and details, enabling or disabling ports, restarting ports, PoE power control, PHY mode, VLAN (802.1Q / MTU / port VLAN), port rate limiting, storm suppression, port flow control, LLDP, loop protection, port mirroring, DHCP snooping, port priority, network configuration (IP / gateway / DNS), device reboot and factory reset. Note that the MAC address table interface is an empty stub in some firmware builds (unavailable) - read the Function Availability section in SKILL.md before use. Trigger words - cloud managed switch, SSC, switch, callcmd, calludp, port, VLAN, PoE, rate limit, storm, loop, mirroring, LLDP.
description_zh: 通过云网管(SSC)系列交换机的私有接口控制交换机。当用户需要查询或配置云网管交换机时使用,包括:发现内网设备、查看设备状态/详情、开关端口、端口重启、POE 供电开关、PHY 模式、VLAN(802.1Q/MTU/端口VLAN)、端口限速、风暴抑制、端口流控、LLDP、环网、端口镜像、DHCP 侦听、端口优先级、网络配置(IP/网关/DNS)、设备重启、恢复出厂。注意:MAC 地址表接口在本系列部分固件为空实现(不可用),使用前先读 SKILL.md 的"功能可用性"章节。触发词:云网管、SSC、交换机、callcmd、calludp、端口、VLAN、PoE、限速、风暴、环网、镜像、LLDP、交换机控制。
description_en: Control cloud-managed (SSC) series switches through their private interfaces. Use it when the user needs to query or configure such switches - discovering devices on the LAN via UDP multicast, reading device status and details, enabling or disabling ports, restarting ports, PoE power control, PHY mode, VLAN (802.1Q / MTU / port VLAN), port rate limiting, storm suppression, port flow control, LLDP, loop protection, port mirroring, DHCP snooping, port priority, network configuration (IP / gateway / DNS), device reboot and factory reset. Note that the MAC address table interface is an empty stub in some firmware builds (unavailable) - read the Function Availability section in SKILL.md before use. Trigger words - cloud managed switch, SSC, switch, callcmd, calludp, port, VLAN, PoE, rate limit, storm, loop, mirroring, LLDP.
version: "1.0.2"
agent_created: true
---

# SSC (Cloud-Managed) Switch Control

## Overview

This skill queries and configures cloud-managed (SSC) series switches through their
private interfaces. The protocol exchanges JSON messages; commands are identified by
`callcmd` (command name or command number). All calls go through the Python scripts
under `scripts/` to keep behavior consistent and reproducible.

Applicable devices: cloud-managed switch series (SSC-Cloud / V2.x / V3.x firmware).

## Binary Modules Disclosure (Read Before Use)

The implementation modules under `scripts/` are **compiled CPython extensions
(`.pyd`, Windows PE DLLs)**, not readable Python source. Their purpose, behavior
boundaries, and SHA-256 checksums are fully disclosed in
[`SECURITY_DISCLOSURE.md`](SECURITY_DISCLOSURE.md). Verify before first use:

```bash
cd <skill_dir>/scripts && python verify_checksums.py   # pure Python, offline, read-only
```

Key facts:
- **Runtime requirement: Windows x64 + CPython 3.13** (`cp313-win_amd64`). Other
  platforms/versions fail fast with a clear error message.
- The binaries only talk to the user-specified device (`SSC_HOST` / UDP multicast
  `239.0.0.100:10086`) and persist the session cookie under
  `~/.ssc_switch_sessions/`. No hardcoded addresses, no telemetry, no other network
  targets, no process spawning or system modification.
- All CLI behavior, command numbers, and protocol details are documented in plain
  text in `references/commands.md` / `references/protocol.md` — the documentation is
  the auditable counterpart of the binaries.

## Three Channels (Choosing the Right One Is Key)

| Channel | Transport | Encryption | Purpose | Key Required |
|------|------|------|------|--------------|
| **WEB to device** | HTTP POST | **None** | Almost all commands | No (except activate/login) |
| Client to device | UDP multicast 239.0.0.100:10086 | TEA+base64 | Device discovery, key change, security verification | Depends on command |
| Cloud to device | TCP keep-alive connection | TEA+base64 | Cloud platform calling the device (out of scope for this skill) | Yes |

**Default to the WEB-to-device channel** — it is the simplest (HTTP, plain-text JSON),
covers the most commands, and requires no long-lived connection.
Only use the UDP multicast channel for "LAN device discovery" and "local security verification".

## Quick Start

```bash
cd <skill_dir>/scripts
pip install requests                # The only external dependency
# NOTE: requires Windows x64 + Python 3.13 (compiled .pyd modules, see SECURITY_DISCLOSURE.md)

# 1) Discover devices on the LAN (UDP multicast, no IP needed)
python switchctl.py search

# 2) Target a specific device (WEB channel)
export SSC_HOST=192.168.1.10        # Device IP (required)
export SSC_WEB_PORT=80              # Optional, default 80
export SSC_PASSWORD=YourPwd         # WEB login password (required by most commands except state)
python switchctl.py login           # Log in and save the session cookie locally (auto-login if SSC_PASSWORD is set)
python switchctl.py state           # Device state (100, no login needed)
python switchctl.py cmd-all         # Fetch all interface data (200, after login)
```

### Real-Device Protocol Essentials (Verified by Testing)

- **URL path = command number**: `POST http://<ip>/<callcmd>` (e.g. `/100`, `/123`, `/109`).
  For unregistered command numbers the device simply drops the connection (empty reply).
- **Request body**: `{"data": {"callcmd": <command number>, "calldata": {...}}}` (omit `calldata` when there are no parameters).
- **Sessions are maintained via Cookie (most critical, easiest to trip over)**:
  - First call `Security_verification/123` with `password` to log in; on success **the
    response header returns `Set-Cookie: <bare token>`** (note: NOT the standard
    `name=value` form).
  - **As long as an active session exists on the device, every subsequent request must
    carry `Cookie: <token>`**, otherwise the device drops the connection (empty reply).
    **This gate even applies to the login `/123` itself**: with a session already active,
    a cookie-less login request is rejected too.
  - Because this cookie is non-standard, the `requests` cookie jar discards it, so the
    client sends/receives the `Cookie` header **manually**; the session token is
    **persisted to a local file** — `login` saves it and later commands reuse it automatically.
  - The session file defaults to `~/.ssc_switch_sessions/<host>.cookie`; override with
    `SSC_COOKIE_FILE` or `--cookie-file`; `python switchctl.py logout` clears the local session.
- **The session has a 2-minute idle timeout (verified on firmware)**:
  The firmware increments `cookie_info.idleTime` every second, **and only requests with
  the correct cookie reset it to zero**; after about 20000 counts (~2 minutes) the device
  clears the session automatically. Therefore:
  - Carry the cookie on every request → the session **never expires**;
  - Cookie-less requests keep being rejected until the 2-minute timeout expires the
    session, after which things return to normal.
  - **The old belief that "the device got saturated and self-recovered in 60~90s" was a
    misjudgment**: in testing, 12 consecutive requests with a valid cookie (0.3s apart)
    **all succeeded** — request rate is not the issue. The real causes were the missing
    cookie and the subsequent ~2-minute idle timeout release.
- **Logout endpoint = `POST /126` (verified on a real device)**: body `{"data":{"callcmd":126}}`.
  It **immediately clears the device-side session** (cookie_info); the old cookie becomes
  invalid right away, and a subsequent `login` issues a **new** cookie.
  - **A normal logout returns `errcode 1003`** — this is the logout-dedicated **success
    code, not an error** (the device web frontend also uses 1003 to detect logout
    completion). `0` is also treated as success.
    The script treats both `{0, 1003}` as success (`ssc_web.LOGOUT_OK_CODES`).
  - **Practical use**: the device "allows only one session". If the session is occupied
    or stuck, `logout` lets you **re-login immediately** without waiting the ~2-minute
    idle timeout — the fastest way to reset a session.
- **System proxies must be bypassed**: if `http_proxy` is set in the environment, LAN
  devices become unreachable. The client has `trust_env=False` built in to bypass this.
- **Response**: `{"data":{"callcmd":...,"calldata":{...}},"errcode":0}`; failure looks like
  `{"errcode":1001,"errmsg":"parameter error"}`.

## Common Operations

**Queries (safe, run directly)**

```bash
python switchctl.py search                 # Multicast device discovery
python switchctl.py login                  # WEB login (123), saves the session cookie
python switchctl.py logout --yes           # Terminate the device session (POST /126) + clear local cookie
                                           # Non-interactive (scripts/automation) MUST pass --yes, otherwise it blocks waiting for confirmation
python switchctl.py state                  # Device state (100, no login)
python switchctl.py cmd-all                # Fetch all device interface data (200, login required)
python switchctl.py detail --show-ports    # Device details + port status table (101, login required)
python switchctl.py vlan-get               # Read VLAN
python switchctl.py mac-get --port 4       # Read the MAC table for port 4
python switchctl.py limit-get              # Read port rate limits
python switchctl.py storm-get              # Read storm suppression
python switchctl.py netcfg-get             # Read network configuration
python switchctl.py flow-get               # Read port flow control
python switchctl.py lldp-get               # Read LLDP
```

**Configuration (risky; a second confirmation is required before execution)**

```bash
python switchctl.py port-up   --port 1              # Enable a port
python switchctl.py port-down --port 1              # Disable a port
python switchctl.py port-restart --port 1           # Restart a port
python switchctl.py poe --port 1 --on               # POE on
python switchctl.py poe --port 1 --off              # POE off
python switchctl.py phy --port 1 --mode full1000    # Set PHY mode
# 802.1Q member ports are only valid for ports 25-28 (see "Implementation Notes" below)
python switchctl.py vlan-set --vlantype 1 --vlanid 100 --untag-ports 25 --trunk-ports 26
python switchctl.py port-pri --ports 28 --pri 5       # Port priority 0-6 (ports 25-28 only)
python switchctl.py port-mirror --catch 27 --catched 25   # Mirror: port25 -> 27 (25-28 only)
python switchctl.py limit-set --up "[0,0,64]" --down "[0,0,64]"   # Values must be multiples of 64 (0 = no limit)
python switchctl.py storm-set --on
python switchctl.py reboot --yes                    # Reboot the device (connection drops)
```

> **The MAC table (114) is an empty stub in this model's firmware — `mac-get`/`mac-add`/
> `mac-del`/`mac-clear` will always fail**. Do not use them and do not put them in scripts.

**Arbitrary commands (fallback)**

```bash
# vlanid / vlanport must be arrays; porttype must be a number
python switchctl.py raw vlan '{"vlan":1,"vlantype":1,"vlanid":[100],"vlanport":[16777216],"porttype":33554432}'
python switchctl.py raw 109 '{"vlan":1,"vlantype":1,"vlanid":[100],"vlanport":[16777216],"porttype":33554432}'
# The PortMirror mask may only use bit24-27 (ports 25-28)
python switchctl.py raw PortMirror '{"Catch_port":134217728,"Catched_port":16777216}'
```

## Key Conventions (Common Pitfalls)

1. **Ports are expressed as "indices"**: the port number 1 that humans see corresponds to
   index 0. Commands such as port up/down convert automatically via `build_config_opcode()`,
   so just pass `--port <port number>`.
2. **Port masks are decimal bitmasks**: in fields such as `vlanport`/`bitmap`, ports 1 and 2
   correspond to mask `3` (=0b11). Convert with `port_mask(1,2)`; reverse with `mask_ports(3)`.
   (`vlan-set --untag-ports 1 2` converts automatically.)
3. **callcmd uses command numbers on the WEB channel**. Both the URL path and body use
   numbers (e.g. `/100`, `/109`, `/123`). For UDP/cloud channels, string command names are
   recommended (older firmware only accepts strings). The script's `resolve_callcmd_num()`
   converts names to numbers automatically.
4. **The Cookie must be sent after login** (see "Real-Device Protocol Essentials" above).
   The CLI stores the session token in a local file; after one `login`, all commands reuse it.
   - If a command returns an "empty reply": usually that **command number is not registered
     in the firmware**; it may also mean the device-side session is occupied by another
     client (the device **allows only one session**), or the request is missing the cookie.
   - **The fastest way to reset a session is `logout` (POST /126)**: it immediately clears
     the device-side session (returns `errcode 1003` = logout success), after which you can
     `login` **immediately** without waiting.
     Alternatives: wait ~2 minutes for the idle timeout, or reboot the device.
   - **When calling `logout` from scripts/automation you MUST pass `--yes`**: this
     subcommand has an interactive confirmation by default and will block waiting for input
     in non-TTY environments (symptom: command hangs/times out).
   - While a session is valid, do **not** probe repeatedly with cookie-less requests —
     they will just keep being rejected.
5. **errcode semantics**: `0` = success; `1001` usually means a parameter/business rejection
   (often with `{"xxx":"fail"}`); `1000` usually means a malformed parameter; `1003` is the
   **logout-dedicated success code for `/126`** (not an error);
   **`-1` means the command number is not registered in the firmware** (the device drops the
   connection). Handle unknown errcodes per their literal messages.
6. **Configuration takes effect with a delay (~10 seconds)**: right after pushing port/VLAN
   configuration, an immediate read-back may still show the old value; wait about 10 seconds
   before reading back to confirm.
7. **config/103 is a bitwise opcode**: `opcode = (value<<9) | (index<<4) | func`,
   func: 0-phy 1-iso 2-poe 3-port restart 4-port admin 5-force POE.
8. **The WEB channel needs no encryption**; UDP/cloud channels require TEA encryption
   (see the `tea` module under `scripts/`).
   **`search` must be encrypted too** — the device unconditionally decrypts before parsing
   JSON; plain-text requests are silently dropped.
   Also, the UDP client must `bind` to 10086 and join the multicast group to receive
   responses (responses go to the multicast address, not unicast back to the sender).
   See `references/protocol.md` section 3.1 for details.
9. **Port/array lengths may differ**: e.g. `pw`/`poec` only cover PoE ports (24), while
   `link`/`AdminState` cover all ports (28). Apply bounds checks when parsing by index
   (the CLI already does).
10. **Feature availability varies by firmware** (cross-checked against firmware source,
    PS424GV3 / V6.1.260918):
    - ✅ Available: storm / lldp / flow / dhcp_snop / LoopNet / pwWarCfg / port-type configs;
      **VLAN (802.1Q/MTU/port VLAN)**, **port priority**, and **port mirroring** are all
      writable (see "Implementation Notes" below).
    - ❌ **Unavailable (firmware-level; no parameter combination helps)**: both read and
      write of `mac_table/114` are **empty stubs** (`ssc_dev_macCfg` always `return -1`);
      `TCP_ONLINE/131` is **not compiled** in this model (returns -1).
    - Read back to confirm before and after pushing configuration.
11. **A few easy-to-miss "implementation notes"** (from source + real-device testing,
    see `references/commands.md` for details):
    - `vlan`: `vlanid`/`vlanport` **must be arrays** and `porttype` (a number) is required;
      802.1Q member ports use only **ports 25-28**; even disabling requires `vlantype`.
    - `port_pri`: only **ports 25-28** can be set (the first 24 array entries must stay 0,
      otherwise the whole call fails).
    - `PortMirror`: the mask may only use **bit24-27 (ports 25-28)**.
    - `limit`: values must be **multiples of 64** (array slots for ports 27/28 must be 0).

## Full Command Reference

For all command numbers, parameter meanings, and examples see `references/commands.md`.
For protocol layers, packet structure, and encryption framing see `references/protocol.md`.
For complete worked examples of typical scenarios see `references/examples.md`.

## Direct Use in Python

```python
import sys
sys.path.insert(0, "<skill_dir>/scripts")
from ssc_web import SSCWebClient
from ssc_protocol import build_config_opcode, port_mask

cli = SSCWebClient("192.168.1.10")          # Or leave empty to read SSC_HOST; password comes from SSC_PASSWORD
cli.login("YourPwd")                        # Login (123); on success the session cookie is saved
print(cli.cookie, cli.cookie_file)          # Session token and its on-disk location
err, data = cli.state()                     # Device state (100)
err, data = cli.call(200)                   # All interface data (200)
err, data = cli.call(109, None)             # Read VLAN
err, data = cli.call(103, {"opcode": build_config_opcode(4, 0, 1)})  # Port 1 up
cli.clear_cookie()                          # Clear the local session
```

> `SSCWebClient` **manages the cookie session automatically**: it reads the local session
> file at construction, sends the `Cookie` header with each request, updates and persists
> on `Set-Cookie`; if a request hits an empty reply and a password is configured, it
> **automatically re-logs in and retries once**. So normally one client instance is enough
> for continuous operations.

- `ssc_web.SSCWebClient` — WEB channel: POST plain-text JSON, returns `(errcode, calldata)`.
- `ssc_udp.SSCUdpClient` — UDP multicast: `.search()` discovers devices, `.verify()` performs security verification.
- `ssc_protocol` — Command registry, message construction, port masks/opcodes, state decoding.
- `tea` — TEA encryption/decryption and base64 framing (used by UDP/cloud channels).

## Safety Notes

- Dangerous operations (`reboot`/`reset`/`update`/`ResKey`/`dev_add`/`modify_key`) require
  user confirmation before execution; the CLI has a built-in second confirmation
  (skippable with `--yes`, but not recommended).
- Factory reset (`reset`) and clearing the MAC table irreversibly wipe configuration —
  be very careful.
- Device addresses are passed only via environment variables/parameters; nothing is hardcoded.
- UDP multicast only works on the same subnet as the local machine.

## Resource Files

- `scripts/switchctl.py` — Unified CLI entry point (readable Python; loads the compiled implementation).
- `scripts/_ssc_cli.cp313-win_amd64.pyd` — Compiled CLI implementation (all subcommands).
- `scripts/ssc_web.cp313-win_amd64.pyd` — WEB-to-device HTTP channel client (`SSCWebClient`).
- `scripts/ssc_udp.cp313-win_amd64.pyd` — UDP multicast channel (discovery/verification, `SSCUdpClient`).
- `scripts/ssc_protocol.cp313-win_amd64.pyd` — Protocol core: command registry, message codecs, utilities.
- `scripts/tea.cp313-win_amd64.pyd` — TEA encryption and framing.
- `scripts/SHA256SUMS.txt` — Published SHA-256 checksums of the binary modules.
- `scripts/verify_checksums.py` — Readable, offline checksum verification script.
- `SECURITY_DISCLOSURE.md` — Binary modules security disclosure (purpose, behavior boundaries, verification).
- `references/commands.md` — Full command list with parameter descriptions.
- `references/protocol.md` — Protocol layers and packet formats.
- `references/examples.md` — Worked examples.
