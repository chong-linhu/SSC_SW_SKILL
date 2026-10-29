# SSC (Cloud-Managed) Switch Protocol Specification

This document describes the layering, packet formats, and encryption/framing of the
cloud-managed (SSC) switch private protocol.
Sources: "Cloud-Managed Series Interface Specification (250806)", "Cloud_Series_API",
"Switch Interface Document (IPCC)", "Switch Production Test Interface",
"Device Upgrade Process Specification".

## 1. Unified Packet Structure

**Request**

```json
{ "cmd": "topic-name", "syn": "8-digit sync code", "data": { ... } }
```

**Response**

```json
{ "errcode": 0, "ack": "topic-name", "syn": "8-digit sync code", "data": { ... } }
```

- `syn`: sync code (8 digits); it must match between request and response.
- `errcode`: 0 means success; anything else is an error code.
- `ack`: response topic name, corresponding to the request's `cmd`.

## 2. Two Channels

### 2.1 WEB to Device (Recommended, Verified by Testing)

- Transport: HTTP **POST**, data is **not encrypted**, sessions are maintained via
  **Cookie**, and multiple devices can be accessed concurrently.
- **URL path = command number**: `POST http://<ip>/<callcmd>`, e.g. `/100`, `/109`, `/123`.
  For unregistered command numbers the device (lwIP HTTP service) **drops the
  connection immediately** (empty reply).
- Request body (omit the `calldata` key when there are no parameters):


  ```json
  {"data": {"callcmd": 109, "calldata": { ... }}}
  ```
- Response body:
  ```json
  {"data": {"callcmd": 109, "calldata": { ... }}, "errcode": 0}
  ```
  Failure: `{"data":{"callcmd":123,"calldata":{"login":"fail"}},"errmsg":"parameter error","errcode":1001}`
- **Sessions are maintained via Cookie (verified by testing, critical)**:
  - First call `Security_verification/123` with `{"password":"..."}` to log in; on success
    **the response header returns `Set-Cookie: <bare token>`** (not the standard
    `name=value` form, e.g. `Set-Cookie: HaJ2HTgcNuLhu5OVWTqwLgA=`).
  - **As long as an active session exists on the device, every subsequent request must
    carry `Cookie: <token>`**; without it the device **drops the connection** (empty
    reply). This gate **also applies to login `/123` itself**: with a session already
    active, a cookie-less login request is rejected too (verified: re-login only becomes
    possible after the session's idle timeout). This is the real reason why `/101`,
    `/200`, etc. "still fail after login".
  - This cookie is non-standard, so the `requests` cookie jar discards it as an invalid
    value; the client therefore sends/receives the `Cookie` header **manually**
    (see `ssc_web.py`) and persists the token to
    `~/.ssc_switch_sessions/<host>.cookie` for reuse across commands/processes.
  - **The device allows only one session**: if another client (e.g. the browser web UI)
    has logged in and holds the session, the script must wait for its idle timeout or
    first call `logout/126` to clear the session before logging in again.
  - Channel-specific commands: `123` (login), `120` (change key), `126` (logout),
    `200` (cmd_all, fetch all interface data).
- **Logout `/126` (verified effective on a real device)**: `POST /126`, body
  `{"data":{"callcmd":126}}`, **immediately clears the device-side session**; the old
  cookie becomes invalid right away and re-login issues a new cookie.
  - **A normal return is `errcode 1003`** — the logout-dedicated **success code, not an
    error** (the device web frontend also uses 1003 to detect logout completion); `0` is
    also treated as success. In code, `ssc_web.LOGOUT_OK_CODES = {0, 1003}`.
  - Key points for verification: to determine "whether the session was cleared" you must
    use a **login-required** endpoint (e.g. `/200`); `/100` needs no login and returns 0
    either way, so it cannot serve as evidence.
- **Session idle timeout ≈ 2 minutes (verified on firmware)**:
  The firmware increments `cookie_info.idleTime` every second and **clears it only when a
  request with the correct cookie arrives**; after about 20000 counts (~2 minutes) it
  executes `memset(&cookie_info,0,...)` to clear the session.
  Corollaries: ① carrying the cookie on every request → the session lives indefinitely;
  ② cookie-less requests keep being rejected until the ~2-minute timeout expires the
  session, after which requests recover. **This is not "the device being saturated"** —
  in testing, 12 consecutive requests with a valid cookie (0.3s apart) all succeeded;
  request rate is not the bottleneck.
  ③ A `/126` logout releases the session **immediately**, with no need to wait those
  2 minutes.
- **System proxies must be bypassed**: if `http_proxy` is set in the environment, LAN
  devices become unreachable.
  `ssc_web.py` has `session.trust_env = False` built in.
- Call it directly via `scripts/ssc_web.py` or `switchctl.py`.

### 2.2 Client to Device (UDP Multicast)

- Multicast address `239.0.0.100`, port `10086`.
- Request body:
  ```json
  {"cmd":"calludp","syn":"xxxxxxxx","data":{"callcmd":119,"sn":"..","calldata":{...}}}
  ```
  When `calldata` is empty **the field should be omitted** — this is exactly how the
  firmware's own `getDEV()` sends it (`iot_local.c:171`).
- The response body has `ack` set to `calludp`.
- Purpose: `search` (discovery), `Security verification` (activation/login),
  `modify_key` (key change).
  Note that the security-verification command name is **`Security verification`**
  (full spelling); the buggy lower-layer spelling `Security ver` will not match.
- These are local management commands; security verification is required before
  performing management operations.

**Two conditions must be met to receive responses** (otherwise you will never get one):

1. **Requests must be encrypted**. On the device side, `iot_local.c:305`
   **unconditionally** applies `base64 decode + TEA decrypt` to received packets before
   JSON parsing; plain-text requests are silently dropped. The earlier claim that
   "search needs no encryption" was wrong.
2. **The socket must `bind` to the sending port 10086 and join the multicast group via
   `IP_ADD_MEMBERSHIP`**. The device sends the response to
   **multicast `239.0.0.100:<request source port>`** (`net/ssc_net.c:202`), not
   unicast back to the requester — send-only without binding receives nothing.

Verified: a healthy device **replies within 0.1 seconds**; if a device responds to ping
but neither to UDP nor HTTP, its application layer is hung and it needs a power cycle —
this is unrelated to this channel's implementation.

## 3. Encryption and Framing

WEB channel: **no encryption**.

UDP / cloud channels: request data is first **TEA-encrypted**, then **base64-encoded**,
and finally terminated with `\r\n`.
Device responses are encrypted the same way.

- Keys:
  - `activate`: the cloud assigns a `did`;
  - `connect`: the cloud assigns a `key` (16 visible characters), used as the encryption
    key afterwards;
  - For local management, the admin key set via `Security verification` / `modify_key`.

## 4. Port Numbering and Masks

Port numbering rules differ across versions:

- V2.0: corresponds to port numbers as configured
- V2.1-V2.2: by default the port farthest from the cascade port is the starting port,
  indexed
- V3.0: no fixed cascade port; with the device placed upright, the leftmost (or top-left)
  port is the first port, indexed

The protocol internally uses **indices** (port number - 1) uniformly. `vlanport`/`bitmap`/
`porttype`/`Catched_port` etc. are **decimal bitmasks represented as bit positions**:

| Port | Bit  | Mask contribution | Combination example |
| -- | ---- | ---- | -------------- |
| 1  | bit0 | 1    | Ports 1,2 → 3      |
| 2  | bit1 | 2    | Ports 3,4 → 12     |
| 3  | bit2 | 4    | Ports 1,2,3,4 → 15 |
| 4  | bit3 | 8    | Ports 2,3,4 → 14   |

Utility functions: `port_mask(1,2) -> 3`, `mask_ports(12) -> [3,4]`.

## 5. State Field Dictionary

- `link` / `phyc`: 0-disconnected 1-half duplex 10M 2-full duplex 10M 3-half duplex 100M 4-full duplex 100M 5-full duplex 1000M
- `snr`: 0-excellent 1-good 2-poor
- `stpPort_State`: 0-Disable 1-Discarding 2-Learning 3-Forward
- `AdminState`: 0-phydown 1-phyup 2-loop-blocked
- `fwd` (MAC): 0-system default 1-LAN+CPU 2-LAN 3-CPU only 4-drop
- `cloud_status`: 0-offline 1-online
- `Active_state`: `active` activated / `not_active` not activated

## 6. Version Differences Quick Reference

| Feature                                          | Starting version |
| ---------------------------------------------- | ---- |
| limit/storm/netcfg                             | V2.1 |
| dev_add/ResKey/local management                | V2.2 |
| mac_table/PortMirror/dhcp_snop/LoopDetect      | V3.0 |
| lldp                                           | V2.3 |
| AI_AnAuto/AI_Wdog                              | V2.4 |
| LoopNet (loop protection)/event/port_mibCnt/get_dev/port_pri | V3.2 |
| LBZ/pwWarCfg                                   | V3.1 |
