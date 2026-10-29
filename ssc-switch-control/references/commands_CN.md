# 云网管交换机命令清单

命令通过 `callcmd`(命令名或命令号)调用。请求统一为
`{"data":{"callcmd":<命令>,"calldata":{...}}}`,响应为
`{"data":{"callcmd":...,"calldata":{...}},"errcode":0}`。
`errcode=0` 表示成功。

> 端口一律按**索引**表示:看到的端口 1 = 索引 0,端口 N = 索引 N-1。
> `vlanport`/`bitmap`/`porttype` 等是**十进制位掩码**:端口 1、2 → `3`(0b11)。

## 一、查询类

| 命令 | 号 | calldata | 返回 | 说明 |
|------|----|----------|------|------|
| `state` | 100 | 无 | link/pw/snr/Active_state/stpPort_State/AdminState | 设备状态。link:0-未连 1~5 速率;AdminState:0-phydown 1-phyup |
| `detail` | 101 | 无 | ip/mac/V/tp/T/uplink/tx/rx/link/pw/snr/stpPort_State/AdminState/cloud_status | 设备详情;`V`=固件版本,`tp`=总功率,`T`=温度,`cloud_status`:0-离线 1-在线 |
| `vlan` | 109 | 无 | vlan/vlantype/vlanid[]/vlanport[]/porttype | 读 VLAN |
| `limit` | 106 | 无 | up[]/down[] | 读端口限速(kbps,0=不限速) |
| `storm` | 107 | 无 | storm:1/0 | 读风暴抑制 |
| `netcfg` | 108 | 无 | dhcp/ip/gw/mask/dns | 读网络配置 |
| `mac_table` | 114 | `null` 全局 / `{"port":N}` 指定端口 | MAC[]/bitmap[]/fwd[]/sign[] | 读 MAC 地址表 |
| `dhcp_snop` | 124 | 无 | global_enable/trust_port[] | 读 DHCP 侦听 |
| `lldp` | 127 | 无 | lldp:0/1 (V3.0 另有 lldp_info[]) | 读 LLDP |
| `PORT_FLOW` | 133 | 无 | flow[] | 读端口流控 |
| `port_mibCnt` | 136 | `null` / `{"port":N}` | RxDp/RxCrc/Txbrd/Rxbrd/TxMult/RxMult/TxUni/RxUni | 端口流量包统计(V3.2) |
| `port_pri` | 138 | 无 | PortPri[] (0-6,越大越优先) | 读端口优先级(V3.2) |
| `get_dev` | 137 | 无 | sn[] | 获取局域网当前设备(V3.2) |
| `cmd_all` | 200 | 无 | 所有接口数据 | 一次性取回全部接口信息(WEB) |

## 二、端口配置(均走 `config`/103,位运算 opcode)

`opcode = (value << 9) | (port_index << 4) | func`

| func | 功能 | value 含义 |
|------|------|-----------|
| 0 | PHY 设置 | 0-down 1-half10M 2-full10M 3-half100M 4-full100M 5-full1000M |
| 1 | 隔离设置(iso) | 按设备定义 |
| 2 | POE 设置 | 0-关 1-开 |
| 3 | 端口重启 | 无需 value |
| 4 | 端口 Admin 控制 | 0-phydown(关) 1-phyup(开) |
| 5 | 强制 POE 开关 | 0-关 1-开 |

Python:`build_config_opcode(func, port_index, value)`
CLI:`port-up/port-down/port-restart/poe/phy` 子命令。

## 三、配置类

### vlan / 109
calldata:`{"vlan":T,"vlantype":T,"vlanid":[X,...],"vlanport":[mask,...],"porttype":mask}`

**字段形态由固件 `call_procVlan` 强校验(依据源码 + 真机实测,2026-10-15 修正):**
- `vlan`:数字(必填),1-开启 0-关闭
- `vlantype`:数字,1-802.1Q 2-MTU 3-端口VLAN
- `porttype`:**必须传数字**(trunk 端口掩码);漏传会让固件空指针 → 失败
- `vlanid` 与 `vlanport`:**要么都传、要么都不传**,且**都必须是数组**
  (旧文档示例写成标量 `"vlanid":100` → 固件判 `1000` 参数错!)
  二者按顺序一一对应到 `vlanGroup[i]` 的 vid 与 port 掩码
- 802.1Q 的成员端口掩码**只用 bit24-27(端口 25-28)**,其他位不会被处理

示例(真机验证通过):
- 802.1Q VID100,untag 端口25,trunk 端口26 →
  `{"vlan":1,"vlantype":1,"vlanid":[100],"vlanport":[16777216],"porttype":33554432}`
- MTU VLAN(LAN 内互联)→ `{"vlan":1,"vlantype":2,"porttype":0}`(不带 vlanid/vlanport;
  **重配较慢,响应可能超时,需把超时调大**)
- 关闭 → `{"vlan":0,"vlantype":1,"porttype":0}`(**关闭也要带 vlantype**,
  否则固件走 default 分支返回 1001,虽已置 0 但会误报失败)

CLI:`switchctl.py vlan-set --vlantype 1 --vlanid 100 --untag-ports 25 --trunk-ports 26`
/ `switchctl.py vlan-set --vlantype 1 --off`

### limit / 106
calldata:`{"up":[..],"down":[..]}`,数组索引=端口索引,单位 kbps,0=关闭限速。

> **规则(源码 `ssc_dev_setRateLimit` + 真机实测)**:不是随意白名单,而是——
> - 普通口(端口 1-24,非 AN8858B):值**必须是 64 的整数倍**(`value % 64 == 0`);
> - AN8858B 口(端口 25-28):值必须是 `AIR_CHIP_LIMIT_CIR` 的整数倍;
> - 所有值 `≤ AIR_CHIP_RATE_MAX`;数组**索引 26、27(即端口 27、28)必须为 0**(SFP 不支持限速,否则整体 fail)。
>
> 实测:`64`/`128`/`1024`/`1000000`(均为 64 倍数)成功;`1`/`1000`(非 64 倍数)返回 `{"limit":"fail"}(1001)`。
> 传非法值不报参数错,而是直接业务拒绝——下发前按 64 的倍数取值。

### storm / 107
calldata:`{"storm":1/0}` 抑制广播/组播/单播速率为 4Mbps。(真机验证可读写)

### netcfg / 108
calldata:`{"dhcp":1/0,"ip":"..","gw":"..","mask":"..","dns":".."}`
> ⚠️ 改本机 IP/网关会**切断当前连接**,务必现场操作。

### mac_table / 114(配置)
calldata:`{"MAC":[".."],"bitmap":[...],"fwd":[...],"sign":[...],"flag":N}`
- `fwd`:0-系统默认 1-LAN+CPU 2-LAN 3-仅CPU 4-丢弃
- `sign`:3-static+IVL
- `flag`:1-添加 2-删除一条 3-删除所有
- 一个端口最多绑定 5 条;绑定后该端口关闭学习

示例:端口 4 加 `80FA5B2B1247` → `{"MAC":["80FA5B2B1247"],"bitmap":[8],"fwd":[0],"sign":[3],"flag":1}`

> **⚠️ 本机型(PS424GV3)固件为空实现,无法修复**(源码 `dev_PS424GV3.c`):
> - 写入 `ssc_dev_macCfg()` **直接 `return -1`** → 任何写入都返回 `1001 {"mac_table":"fail"}`
> - 读取 `ssc_dev_mactable_refresh()` **直接 `return;`(空函数)** → 读回永远是空的
> 即本固件的 MAC 表功能**读、写都未实现**,属固件层面限制,换参数也无法成功。
> (对应地,`switchctl.py mac-add/mac-del/mac-clear` 在本机型会失败,属预期。)

### lldp / 127
calldata:`{"lldp":1/0}`

### PORT_FLOW / 133
calldata:`{"flow":[...]}`,数组按端口索引。

### dhcp_snop / 124
calldata:`{"global_enable":1/0,"trust_port":[0/1,...]}`

### LoopNet / 115(环网,V3.2)
calldata:`{"LoopNet":1/0,"mode":0/1}`,mode:0-防环(手动恢复) 1-成环(自恢复)。

### PortMirror / 118(端口镜像)
calldata:`{"Catch_port":<mask>,"Catched_port":<mask>}`(**注意是位掩码,不是端口号**)
- `Catch_port`=捕获口(镜像目的地,单个 bit);`Catched_port`=被镜像口(可多位)
- 两者不能有重叠位;全 0 表示关闭镜像

**关键限制(源码 `ssc_dev_PortMirror` + 真机实测,2026-10-15)**:函数开头即
`if (captur_port & 0xffffff || captured_port & 0xffffff) return -1;`
—— **掩码只能落在 bit24-27,即端口 25-28**;任何含 bit0-23 的掩码都会 `1001 fail`。

示例(真机验证通过):
- 端口27 捕获 端口25 → `{"Catch_port":67108864,"Catched_port":16777216}`
  (端口25→bit24→16777216;端口27→bit26→67108864)
- 关闭 → `{"Catch_port":0,"Catched_port":0}`

CLI:`switchctl.py port-mirror --catch 27 --catched 25` / `switchctl.py port-mirror --off`

### port_pri / 138(端口优先级,V3.2)
calldata:`{"PortPri":[..]}`(数组,值 0-6,越大越优先)

**关键限制(源码 `ssc_dev_setPortPri` + `dev_setPortPri` + 真机实测,2026-10-15)**:
固件遍历所有端口,对**任何数值发生变化的端口**调用 `dev_setPortPri`,
而该函数对**非 AN8858B 芯片**的端口 `return -1`。端口 1-24 是 RTL 芯片,因此:
- **前 24 位必须保持 0(不改动)**;
- 只允许给 **端口 25-28(bit24-27,AN8858B 千兆口)** 设置优先级。

示例(真机验证通过):`[0]*24 + [1,1,1,1]`(端口25-28 优先级=1)。
反例:数组首位改成 1 → 命中端口 1 → 整体 `1001 {"PortPri":"fail"}`。

CLI:`switchctl.py port-pri --ports 25 26 --pri 2` / 读取:`switchctl.py port-pri-get`

### AI_AnAuto / 129,AI_Wdog / 130
calldata:`{"AI_AnAuto":1/0}` / `{"AI_Wdog":1/0}`

### TCP_ONLINE / 131
calldata:`{"Cloud_TCP":1/0}` 云网管功能开关。

> **⚠️ 本机型(PS424GV3)未注册此命令**:源码 `iot_call.c / iot_call_proc` 的 `switch`
> 中,`case TCP_ONLINE` 与 `case Snvr` 仅在小机型宏
> (`DEV_GS105V1_1` 等)下编译,本机型走 `default: errcode = -1`。
> 实测返回 `errcode -1`(命令未注册),**属固件未编译该功能,无法修复**。
> (整机云网管相关开关由 `netcfg`/`AI_*` 等其它命令承载。)

### pwWarCfg / 140(功率预警,V3.1+)
calldata:`{"PoWarn":<瓦数>}`

### LBZ / 139(PD 电压比值,V3.1+)
calldata:`{"min":x,"max":x}`

### Snvr / 132(序列号重置密钥)
calldata:`{"Snvr":"<序列号后6位>"}`

## 四、设备级操作(危险)

| 命令 | 号 | calldata | 说明 |
|------|----|----------|------|
| `reboot` | 104 | 无 | 设备软重启 |
| `reset` | 105 | 无 | **恢复出厂,清空所有配置** |

## 五、安全验证与密钥(走 UDP 组播通道)

| 命令 | 号 | calldata | 说明 |
|------|----|----------|------|
| `search` | 119 | 无 | 搜索内网设备,返回 ip/sn/mac/model/basemodel/Active_state/V |
| `Security ver` | 121 | `{"password":x}` | 激活(设备无密钥时,password 为设置的新密钥) |
| `Security login` | 122 | `{"password":x}` | 登录验证(设备已有密钥时) |
| `modify_key` | 120 | `{"Original_Key":x,"New_Key":x}` | 修改管理密钥 |

## 六、WEB 登录 / 登出

| 命令 | 号 | calldata | 说明 |
|------|----|----------|------|
| `Security_verification` | 123 | `{"password":x}` | WEB 页面登录验证;返回 `{"login":"success/fail"}` |
| `logout` | 126 | 无 | WEB 登出;**立即清除设备端会话 cookie** |

> 登出 `/126` 正常返回 **`errcode 1003`(登出专用成功码,非错误)**;`0` 也视为成功。
> 设备"只允许一个会话",登出后可**立刻**重新 `login`(无需等 ~2 分钟空闲超时),
> 重登会换发新 cookie。CLI:`python switchctl.py logout --yes`
> (**脚本/自动化中必须加 `--yes`**,否则默认交互确认会阻塞)。

