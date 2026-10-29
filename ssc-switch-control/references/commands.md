# SSC (Cloud-Managed) Switch Command Reference

Commands are invoked via `callcmd` (command name or command number). Requests are
uniformly `{"data":{"callcmd":<command>,"calldata":{...}}}`, and responses are
`{"data":{"callcmd":...,"calldata":{...}},"errcode":0}`.
`errcode=0` means success.

> Ports are always expressed as **indices**: the port 1 you see = index 0, port N = index N-1.
> `vlanport`/`bitmap`/`porttype` etc. are **decimal bitmasks**: ports 1, 2 → `3` (0b11).

## I. Query Commands

| Command | No. | calldata | Response | Description |
|------|----|----------|------|------|
| `state` | 100 | none | link/pw/snr/Active_state/stpPort_State/AdminState | Device state. link: 0-disconnected, 1~5 speeds; AdminState: 0-phydown 1-phyup |
| `detail` | 101 | none | ip/mac/V/tp/T/uplink/tx/rx/link/pw/snr/stpPort_State/AdminState/cloud_status | Device details; `V`=firmware version, `tp`=total power, `T`=temperature, `cloud_status`: 0-offline 1-online |
| `vlan` | 109 | none | vlan/vlantype/vlanid[]/vlanport[]/porttype | Read VLAN |
| `limit` | 106 | none | up[]/down[] | Read port rate limits (kbps, 0=no limit) |
| `storm` | 107 | none | storm:1/0 | Read storm suppression |
| `netcfg` | 108 | none | dhcp/ip/gw/mask/dns | Read network configuration |
| `mac_table` | 114 | `null` global / `{"port":N}` per port | MAC[]/bitmap[]/fwd[]/sign[] | Read MAC address table |
| `dhcp_snop` | 124 | none | global_enable/trust_port[] | Read DHCP snooping |
| `lldp` | 127 | none | lldp:0/1 (V3.0 also has lldp_info[]) | Read LLDP |
| `PORT_FLOW` | 133 | none | flow[] | Read port flow control |
| `port_mibCnt` | 136 | `null` / `{"port":N}` | RxDp/RxCrc/Txbrd/Rxbrd/TxMult/RxMult/TxUni/RxUni | Per-port packet statistics (V3.2) |
| `port_pri` | 138 | none | PortPri[] (0-6, higher = higher priority) | Read port priority (V3.2) |
| `get_dev` | 137 | none | sn[] | Get current devices on the LAN (V3.2) |
| `cmd_all` | 200 | none | all interface data | Fetch all interface info in one call (WEB) |

## II. Port Configuration (all via `config`/103, bitwise opcode)

`opcode = (value << 9) | (port_index << 4) | func`

| func | Function | value meaning |
|------|------|-----------|
| 0 | PHY setting | 0-down 1-half10M 2-full10M 3-half100M 4-full100M 5-full1000M |
| 1 | Isolation setting (iso) | Device-specific |
| 2 | POE setting | 0-off 1-on |
| 3 | Port restart | No value needed |
| 4 | Port admin control | 0-phydown (off) 1-phyup (on) |
| 5 | Force POE on/off | 0-off 1-on |

Python: `build_config_opcode(func, port_index, value)`
CLI: `port-up/port-down/port-restart/poe/phy` subcommands.

## III. Configuration Commands

### vlan / 109
calldata: `{"vlan":T,"vlantype":T,"vlanid":[X,...],"vlanport":[mask,...],"porttype":mask}`

**Field shapes are strictly validated by the firmware's `call_procVlan`
(from source code + real-device testing, corrected 2026-10-15):**
- `vlan`: number (required), 1-enable 0-disable
- `vlantype`: number, 1-802.1Q 2-MTU 3-port VLAN
- `porttype`: **must be a number** (trunk port mask); omitting it causes a null-pointer
  dereference in the firmware → failure
- `vlanid` and `vlanport`: **either both present or both absent**, and **both must be
  arrays** (the old doc example used a scalar `"vlanid":100` → the firmware reports
  `1000` parameter error!)
  They map one-to-one, in order, to the vid and port mask of `vlanGroup[i]`
- The 802.1Q member-port mask **only uses bit24-27 (ports 25-28)**; other bits are ignored

Examples (verified on a real device):
- 802.1Q VID100, untag port 25, trunk port 26 →
  `{"vlan":1,"vlantype":1,"vlanid":[100],"vlanport":[16777216],"porttype":33554432}`
- MTU VLAN (LAN interconnect) → `{"vlan":1,"vlantype":2,"porttype":0}` (no vlanid/vlanport;
  **reconfiguration is slow, the response may time out — increase the timeout**)
- Disable → `{"vlan":0,"vlantype":1,"porttype":0}` (**even disabling requires vlantype**,
  otherwise the firmware hits the default branch and returns 1001 — the setting succeeds
  but falsely reports failure)

CLI: `switchctl.py vlan-set --vlantype 1 --vlanid 100 --untag-ports 25 --trunk-ports 26`
/ `switchctl.py vlan-set --vlantype 1 --off`

### limit / 106
calldata: `{"up":[..],"down":[..]}`, array index = port index, unit kbps, 0 = rate limiting off.

> **Rules (source `ssc_dev_setRateLimit` + real-device testing)**: not an arbitrary
> whitelist, but rather —
> - Regular ports (ports 1-24, non-AN8858B): the value **must be a multiple of 64**
>   (`value % 64 == 0`);
> - AN8858B ports (ports 25-28): the value must be a multiple of `AIR_CHIP_LIMIT_CIR`;
> - All values `≤ AIR_CHIP_RATE_MAX`; array **indices 26, 27 (i.e. ports 27, 28) must be 0**
>   (SFP does not support rate limiting, otherwise the whole call fails).
>
> Verified: `64`/`128`/`1024`/`1000000` (all multiples of 64) succeed; `1`/`1000`
> (not multiples of 64) return `{"limit":"fail"} (1001)`.
> Invalid values do not trigger a parameter error but a direct business rejection —
> pick multiples of 64 before pushing.

### storm / 107
calldata: `{"storm":1/0}` suppresses broadcast/multicast/unicast rates to 4Mbps.
(Verified readable and writable on a real device.)

### netcfg / 108
calldata: `{"dhcp":1/0,"ip":"..","gw":"..","mask":"..","dns":".."}`
> ⚠️ Changing the device's own IP/gateway **cuts the current connection**; operate on site.

### mac_table / 114 (configuration)
calldata: `{"MAC":[".."],"bitmap":[...],"fwd":[...],"sign":[...],"flag":N}`
- `fwd`: 0-system default 1-LAN+CPU 2-LAN 3-CPU only 4-drop
- `sign`: 3-static+IVL
- `flag`: 1-add 2-delete one 3-delete all
- A port can bind at most 5 entries; once bound, learning is disabled on that port

Example: add `80FA5B2B1247` on port 4 → `{"MAC":["80FA5B2B1247"],"bitmap":[8],"fwd":[0],"sign":[3],"flag":1}`

> **⚠️ This model's (PS424GV3) firmware is an empty stub and cannot be fixed**
> (source `dev_PS424GV3.c`):
> - Writing: `ssc_dev_macCfg()` **directly `return -1`** → any write returns
>   `1001 {"mac_table":"fail"}`
> - Reading: `ssc_dev_mactable_refresh()` **directly `return;` (empty function)** → reads
>   always come back empty
> That is, this firmware's MAC table feature is **unimplemented for both read and
> write** — a firmware-level limitation; no parameter combination can succeed.
> (Accordingly, `switchctl.py mac-add/mac-del/mac-clear` fail on this model, as expected.)

### lldp / 127
calldata: `{"lldp":1/0}`

### PORT_FLOW / 133
calldata: `{"flow":[...]}`, array indexed by port.

### dhcp_snop / 124
calldata: `{"global_enable":1/0,"trust_port":[0/1,...]}`

### LoopNet / 115 (loop protection, V3.2)
calldata: `{"LoopNet":1/0,"mode":0/1}`, mode: 0-loop prevention (manual recovery)
1-loop formation (self-healing).

### PortMirror / 118 (port mirroring)
calldata: `{"Catch_port":<mask>,"Catched_port":<mask>}` (**these are bitmasks, not port
numbers**)
- `Catch_port` = capture port (mirror destination, a single bit); `Catched_port` = mirrored
  ports (multiple bits allowed)
- The two must not share any bits; all zeros disables mirroring

**Key limitation (source `ssc_dev_PortMirror` + real-device testing, 2026-10-15)**: the
function starts with
`if (captur_port & 0xffffff || captured_port & 0xffffff) return -1;`
— **the mask may only fall on bit24-27, i.e. ports 25-28**; any mask containing bit0-23
returns `1001 fail`.

Examples (verified on a real device):
- Port 27 captures port 25 → `{"Catch_port":67108864,"Catched_port":16777216}`
  (port 25 → bit24 → 16777216; port 27 → bit26 → 67108864)
- Disable → `{"Catch_port":0,"Catched_port":0}`

CLI: `switchctl.py port-mirror --catch 27 --catched 25` / `switchctl.py port-mirror --off`

### port_pri / 138 (port priority, V3.2)
calldata: `{"PortPri":[..]}` (array, values 0-6, higher = higher priority)

**Key limitation (source `ssc_dev_setPortPri` + `dev_setPortPri` + real-device testing,
2026-10-15)**:
The firmware iterates over all ports and calls `dev_setPortPri` for **any port whose value
changed**, but that function `return -1` for ports on **non-AN8858B chips**. Ports 1-24
are RTL chips, therefore:
- **The first 24 entries must remain 0 (unchanged)**;
- Priority may only be set for **ports 25-28 (bit24-27, AN8858B gigabit ports)**.

Example (verified on a real device): `[0]*24 + [1,1,1,1]` (ports 25-28 priority = 1).
Counter-example: changing the first array entry to 1 → hits port 1 → whole call
`1001 {"PortPri":"fail"}`.

CLI: `switchctl.py port-pri --ports 25 26 --pri 2` / read: `switchctl.py port-pri-get`

### AI_AnAuto / 129, AI_Wdog / 130
calldata: `{"AI_AnAuto":1/0}` / `{"AI_Wdog":1/0}`

### TCP_ONLINE / 131
calldata: `{"Cloud_TCP":1/0}` — cloud-managed feature switch.

> **⚠️ This command is not registered on this model (PS424GV3)**: in the source
> `iot_call.c / iot_call_proc` `switch`, `case TCP_ONLINE` and `case Snvr` are only
> compiled under small-model macros (`DEV_GS105V1_1` etc.); this model falls into
> `default: errcode = -1`.
> Verified: returns `errcode -1` (command not registered) — **the firmware does not
> compile this feature and it cannot be fixed**.
> (Device-wide cloud-management switches are carried by other commands such as
> `netcfg`/`AI_*`.)

### pwWarCfg / 140 (power warning, V3.1+)
calldata: `{"PoWarn":<watts>}`

### LBZ / 139 (PD voltage ratio, V3.1+)
calldata: `{"min":x,"max":x}`

### Snvr / 132 (reset key via serial number)
calldata: `{"Snvr":"<last 6 digits of the serial number>"}`

## IV. Device-Level Operations (Dangerous)

| Command | No. | calldata | Description |
|------|----|----------|------|
| `reboot` | 104 | none | Soft reboot of the device |
| `reset` | 105 | none | **Factory reset, wipes all configuration** |

## V. Security Verification and Keys (via the UDP multicast channel)

| Command | No. | calldata | Description |
|------|----|----------|------|
| `search` | 119 | none | Search LAN devices; returns ip/sn/mac/model/basemodel/Active_state/V |
| `Security ver` | 121 | `{"password":x}` | Activation (when the device has no key yet, password sets the new key) |
| `Security login` | 122 | `{"password":x}` | Login verification (when the device already has a key) |
| `modify_key` | 120 | `{"Original_Key":x,"New_Key":x}` | Change the admin key |

## VI. WEB Login / Logout

| Command | No. | calldata | Description |
|------|----|----------|------|
| `Security_verification` | 123 | `{"password":x}` | WEB page login verification; returns `{"login":"success/fail"}` |
| `logout` | 126 | none | WEB logout; **immediately clears the device-side session cookie** |

> Logout `/126` normally returns **`errcode 1003` (the logout-dedicated success code, not
> an error)**; `0` is also treated as success.
> The device "allows only one session"; after logout you can **immediately** `login` again
> (no need to wait the ~2-minute idle timeout), and re-login issues a new cookie.
> CLI: `python switchctl.py logout --yes`
> (**scripts/automation MUST pass `--yes`**; otherwise the default interactive
> confirmation blocks).
