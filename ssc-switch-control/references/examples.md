# SSC (Cloud-Managed) Switch Worked Examples

All examples below assume `SSC_HOST` (device IP) is set. Replace the script directory
with your actual path.

## Scenario 0: Discover LAN Devices and Confirm the WEB Path

```bash
cd scripts
# UDP multicast discovery (no IP needed). Requests are automatically TEA+base64
# encrypted as required by the firmware
python switchctl.py search
# Example output: {"ip":"192.168.1.10","sn":"...","mac":"...","model":"PS208GV3",
#         "V":"6.0.250111","Active_state":"active"}

# A healthy device replies within 0.1s; default wait is 6 seconds
python switchctl.py search --timeout 10

# Devices with OEM WEIWO use a different key and need this flag
# (otherwise the response cannot be decrypted)
python switchctl.py search --oem weiwo
```

Troubleshooting order when there is no response:

1. Is the local machine on the same subnet as the device (multicast is not routed
   across subnets by default)?
2. Does the firewall allow **inbound UDP 10086**?
3. Is another cloud-managed switch client occupying port 10086 (bind failure is reported)?
4. Is the target device's application layer hung — verify by comparing `ping` and HTTP:
   if ping works but HTTP also times out, power-cycle the device.

Once you have the IP, log in to establish a session, then query:

```bash
export SSC_HOST=192.168.1.10 SSC_PASSWORD=<PASSWORD>
python switchctl.py login                  # Login; on success it prints the session cookie and save path
# Example: Session cookie: 26zG0fCoHs01/sY4yj/cBAA=
#     Saved to: C:\Users\<your-username>\.ssc_switch_sessions\192.168.1.10.cookie
python switchctl.py detail --show-ports    # Later commands reuse this cookie automatically
```

> The URL path is simply the command number (e.g. `/100`, `/101`, `/200`) — **no need**
> to guess sub-paths.
> If a command returns an "empty reply", the session has most likely expired or that
> command number is not registered in this firmware:
> first run `python switchctl.py logout && python switchctl.py login` to rebuild the
> session, then retry.

## Scenario 1: View Device and Port Status

```bash
python switchctl.py detail --show-ports
```

Prints a port table (link status, power, SNR, STP, admin state).
In the JSON, `link[i]` corresponds to port `i+1`; values 0-5 mean disconnected/various speeds.

## Scenario 2: Enable/Disable a Port

```bash
python switchctl.py port-down --port 3    # Disable port 3
python switchctl.py port-up   --port 3    # Enable port 3
```

Equivalent to `config/103`, `opcode = (1<<9)|(2<<4)|4` (port 3 → index 2, phyup=1).

## Scenario 3: Restart a Port / Control POE

```bash
python switchctl.py port-restart --port 3     # Soft-restart a port (often used to renegotiate)
python switchctl.py poe --port 3 --off        # Disable POE power on that port
python switchctl.py poe --port 3 --on
```

## Scenario 4: Configure an 802.1Q VLAN

Goal: create an 802.1Q VLAN with VID=100, untag port 25, trunk port 26.

> ⚠️ **Port range limitation (firmware-determined, not a bug)**: the 802.1Q member-port
> mask only processes **bit24-27, i.e. ports 25-28**. Passing ports 1-24 is not handled
> by `dev_802VLAN`, so the configuration has no effect.

```bash
python switchctl.py vlan-set --vlantype 1 --vlanid 100 \
    --untag-ports 25 --trunk-ports 26
```

Underlying packet: `{"vlan":1,"vlantype":1,"vlanid":[100],"vlanport":[16777216],"porttype":33554432}`
- `--untag-ports 25` → mask 1<<24 = 16777216
- `--trunk-ports 26` → mask 1<<25 = 33554432
- **`vlanid` / `vlanport` must be arrays**; `porttype` must be a number (passing an array is
  rejected by the firmware as a parameter error)

Disabling VLAN (`vlantype` must be included, otherwise the firmware falsely reports 1001):

```bash
python switchctl.py vlan-set --off --vlantype 1
```

Read before write (recommended):

```bash
python switchctl.py vlan-get
```

## Scenario 5: MAC Address Management

```bash
python switchctl.py mac-get --port 4                    # Read the MAC table for port 4
python switchctl.py mac-add --mac 80:FA:5B:2B:12:47 --port 4   # Bind a static MAC
python switchctl.py mac-del --mac 80FA5B2B1247 --port 4       # Delete
python switchctl.py mac-clear --yes                     # Clear all (dangerous)
```

Port 4 → mask 8. A port can bind at most 5 MACs; once bound, learning is disabled on that port.

## Scenario 6: Port Rate Limiting and Storm Suppression

```bash
python switchctl.py limit-get
# Set port 3 up/down to 1000kbps (arrays are indexed by port; 0 means no limit elsewhere)
python switchctl.py limit-set --up "[0,0,1000]" --down "[0,0,1000]"

python switchctl.py storm-set --on     # Enable storm suppression (broadcast/multicast/unicast limited to 4Mbps)
python switchctl.py storm-set          # Disable
```

## Scenario 7: Network Configuration

```bash
python switchctl.py netcfg-get
python switchctl.py netcfg-set --dhcp                       # Enable DHCP
python switchctl.py netcfg-set --ip 192.168.1.20 --gw 192.168.1.1 \
    --mask 255.255.255.0 --dns 223.5.5.5                    # Static IP
```

## Scenario 8: Port Mirroring and Traffic Statistics

```bash
# Port 1 captures traffic from ports 2, 3, 4
python switchctl.py raw PortMirror '{"Catch_port":1,"Catched_port":14}'
# Disable mirroring
python switchctl.py raw PortMirror '{"Catch_port":0,"Catched_port":0}'

# Per-port packet statistics (V3.2)
python switchctl.py raw port_mibCnt '{"port":4}'
python switchctl.py raw port_mibCnt
```

## Scenario 9: LLDP Neighbor Discovery

```bash
python switchctl.py lldp-set --on
python switchctl.py lldp-get       # V3.0 returns lldp_info, including neighbor port/system name/management address
```

## Scenario 10: Loop Protection / Port Priority (V3.2)

```bash
python switchctl.py raw LoopNet '{"LoopNet":1,"mode":1}'   # Enable loop protection, self-healing on loop formation
python switchctl.py raw port_pri '{"PortPri":[0,1,5,2]}'   # Port priority 0-6
```

## Scenario 11: Factory Reset / Reboot (Dangerous)

```bash
python switchctl.py reboot --yes     # Soft reboot
python switchctl.py reset --yes      # Factory reset (wipes all configuration!)
```

## Scenario 12: Bulk Operations in Python

Enable POE on ports 1-8 in one go:

```python
import sys
sys.path.insert(0, "scripts")
from ssc_web import SSCWebClient
from ssc_protocol import build_config_opcode

cli = SSCWebClient("192.168.1.10")
for port in range(1, 9):
    opcode = build_config_opcode(func=2, port_index=port - 1, value=1)  # POE on
    err, data = cli.call("config", {"opcode": opcode})
    print(f"Port {port}: errcode={err} {data}")
```

Export all interface data for archival:

```python
import json
err, data = cli.call("cmd_all", None)
open("device_dump.json", "w", encoding="utf-8").write(
    json.dumps(data, indent=2, ensure_ascii=False))
```

## Troubleshooting Quick Reference

| Symptom | Troubleshooting |
|------|------|
| Connection refused | Wrong IP/port, or the device's WEB service is not running |
| Response is not valid JSON | Wrong `--path`, or that path returned an HTML page |
| errcode non-zero | Parameter out of range (e.g. vlanid<2), non-existent port, or unsupported on this model |
| UDP search gets no response | See Scenario 0's troubleshooting order: subnet / inbound UDP 10086 / port occupied / device application layer hung |
| Configuration succeeds but has no effect | Some models/versions do not support the feature; or read the current value via `vlan`/`detail` first before changing |
| Port numbers do not match | Note the index rule and each model's first-port definition (see protocol.md section 4) |
