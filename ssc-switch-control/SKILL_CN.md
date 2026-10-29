---
name: ssc-switch-control
display_name: 云网管交换机控制
display_name_zh: 云网管交换机控制
display_name_en: SSC Switch Control
description: 通过云网管(SSC)系列交换机的私有接口控制交换机。当用户需要查询或配置云网管交换机时使用,包括:发现内网设备、查看设备状态/详情、开关端口、端口重启、POE 供电开关、PHY 模式、VLAN(802.1Q/MTU/端口VLAN)、端口限速、风暴抑制、端口流控、LLDP、环网、端口镜像、DHCP 侦听、端口优先级、网络配置(IP/网关/DNS)、设备重启、恢复出厂。注意:MAC 地址表接口在本系列部分固件为空实现(不可用),使用前先读 SKILL.md 的"功能可用性"章节。触发词:云网管、SSC、交换机、callcmd、calludp、端口、VLAN、PoE、限速、风暴、环网、镜像、LLDP、交换机控制。
description_zh: 通过云网管(SSC)系列交换机的私有接口控制交换机。当用户需要查询或配置云网管交换机时使用,包括:发现内网设备、查看设备状态/详情、开关端口、端口重启、POE 供电开关、PHY 模式、VLAN(802.1Q/MTU/端口VLAN)、端口限速、风暴抑制、端口流控、LLDP、环网、端口镜像、DHCP 侦听、端口优先级、网络配置(IP/网关/DNS)、设备重启、恢复出厂。注意:MAC 地址表接口在本系列部分固件为空实现(不可用),使用前先读 SKILL.md 的"功能可用性"章节。触发词:云网管、SSC、交换机、callcmd、calludp、端口、VLAN、PoE、限速、风暴、环网、镜像、LLDP、交换机控制。
description_en: Control cloud-managed (SSC) series switches through their private interfaces. Use it when the user needs to query or configure such switches - discovering devices on the LAN via UDP multicast, reading device status and details, enabling or disabling ports, restarting ports, PoE power control, PHY mode, VLAN (802.1Q / MTU / port VLAN), port rate limiting, storm suppression, port flow control, LLDP, loop protection, port mirroring, DHCP snooping, port priority, network configuration (IP / gateway / DNS), device reboot and factory reset. Note that the MAC address table interface is an empty stub in some firmware builds (unavailable) - read the Function Availability section in SKILL.md before use. Trigger words - cloud managed switch, SSC, switch, callcmd, calludp, port, VLAN, PoE, rate limit, storm, loop, mirroring, LLDP.
version: "1.0.2"
agent_created: true
---

# 云网管交换机控制

## 概述

本技能通过云网管(SSC)系列交换机提供的私有接口对交换机进行查询与配置。
协议以 JSON 消息交互,命令用 `callcmd`(命令名或命令号)标识,统一走
`scripts/` 下的 Python 脚本,保证调用行为一致、可复现。

适用设备:云网管交换机系列(SSC-Cloud / 云网管 V2.x / V3.x 固件)。

## 二进制模块披露(使用前必读)

`scripts/` 下的实现模块为**编译后的 CPython 扩展(`.pyd`,Windows PE DLL)**,
不是可读的 Python 源码。其用途、行为边界与 SHA-256 校验值已在
[`SECURITY_DISCLOSURE.md`](SECURITY_DISCLOSURE.md) 中完整披露。首次使用前请校验:

```bash
cd <skill_dir>/scripts && python verify_checksums.py   # 纯 Python、离线、只读
```

要点:
- **运行环境要求:Windows x64 + CPython 3.13**(`cp313-win_amd64`)。其他平台/版本
  会立即报错退出并给出环境说明。
- 二进制模块仅与用户指定的设备通信(`SSC_HOST` / UDP 组播 239.0.0.100:10086),
  会话 Cookie 持久化在 `~/.ssc_switch_sessions/` 下;不内嵌地址、无遥测、无其他
  网络目标、不派生进程、不修改系统。
- 全部 CLI 行为、命令号与协议细节均以纯文本形式记录在
  `references/commands.md` / `references/protocol.md`——文档即二进制的可审计对应物。

## 三条通道(选对通道是关键)

| 通道 | 传输 | 加密 | 用途 | 是否需要密钥 |
|------|------|------|------|--------------|
| **WEB 到设备** | HTTP POST | **不加密** | 几乎所有命令 | 否(除激活/登录) |
| 客户端到设备 | UDP 组播 239.0.0.100:10086 | TEA+base64 | 发现设备、改密钥、安全验证 | 视命令 |
| 云端到设备 | TCP 保活连接 | TEA+base64 | 云平台调用设备(本技能不涉及) | 是 |

**默认走 WEB 到设备通道**——它最简单(HTTP、明文 JSON)、覆盖命令最全、无需维护长连接。
只有在"发现内网设备"和"本地安全验证"时才用 UDP 组播通道。

## 快速开始

```bash
cd <skill_dir>/scripts
pip install requests                # 唯一外部依赖
# 注意:需 Windows x64 + Python 3.13(编译 .pyd 模块,见 SECURITY_DISCLOSURE.md)

# 1) 发现内网设备(UDP 组播,不需要知道 IP)
python switchctl.py search

# 2) 指定设备(WEB 通道)
export SSC_HOST=192.168.1.10        # 设备 IP(必填)
export SSC_WEB_PORT=80              # 可选,默认 80
export SSC_PASSWORD=YourPwd         # WEB 登录密码(除 state 外多数命令需要)
python switchctl.py login           # 登录并把会话 cookie 存到本地(设了 SSC_PASSWORD 会自动登录)
python switchctl.py state           # 查设备状态(100,免登录)
python switchctl.py cmd-all         # 取回全部接口数据(200,登录后)
```

### 真机协议要点(已实测确认)

- **URL 路径 = 命令号**:`POST http://<ip>/<callcmd>`(如 `/100`、`/123`、`/109`)。
  未注册的命令号,设备会直接断开连接(空回复)。
- **请求体**:`{"data": {"callcmd": <命令号>, "calldata": {...}}}`(无参数时不带 `calldata`)。
- **会话靠 Cookie 维持(最关键,最容易踩坑)**:
  - 先 `Security_verification/123` 带 `password` 登录,成功时**响应头返回
    `Set-Cookie: <裸 token>`**(注意:不是标准 `name=value` 形式)。
  - **只要设备端存在活动会话,后续每个请求都必须带 `Cookie: <token>`**,
    否则设备直接断开连接(空回复)。**这条闸门连登录 `/123` 本身也管**:
    已有会话时,不带 cookie 的登录请求同样会被拒。
  - 因为该 cookie 非标准,`requests` 的 cookie jar 会丢弃它,故客户端**手动**收发
    `Cookie` 头;会话 token 会**持久化到本地文件**,`login` 保存、后续命令自动复用。
  - 会话文件默认 `~/.ssc_switch_sessions/<host>.cookie`,可用 `SSC_COOKIE_FILE`
    或 `--cookie-file` 指定;`python switchctl.py logout` 可清除本地会话。
- **会话有 2 分钟空闲超时(固件实测)**:
  设备每秒给 `cookie_info.idleTime` 计数,**只有带正确 cookie 的请求才把它清零**;
  累计约 20000 次(≈2 分钟)后设备自动清空会话。因此:
  - 每个请求都带 cookie → 会话**不会过期**;
  - 不带 cookie 的请求会一直被拒,直到 2 分钟超时后会话自动失效,才恢复正常。
  - **过去以为的"设备被打饱和、60~90s 自己恢复"是误判**:实测带有效 cookie
    连发 12 次(间隔 0.3s)**全部成功**,频率并非问题;真正原因是 cookie 缺失,
    以及随后约 2 分钟的空闲超时解除。
- **登出接口 = `POST /126`(已真机验证)**:body `{"data":{"callcmd":126}}`,
  会**立即清空设备端会话**(cookie_info),旧 cookie 随即失效;之后重新 `login`
  会换发**新的** cookie。
  - **正常登出返回 `errcode 1003`**——这是登出的**专用成功码,不是错误**
    (设备前端也用 1003 判定登出完成)。`0` 同样视为成功。
    脚本已把 `{0, 1003}` 都当成功(`ssc_web.LOGOUT_OK_CODES`)。
  - **实际用途**:设备"只允许一个会话",若会话被占用/卡住,`logout` 后**可立即
    重新登录**,不必再等那 ~2 分钟空闲超时——这是重置会话最快的手段。
- **必须绕过系统代理**:环境里若设了 `http_proxy`,内网设备会连不上。
  客户端已内置 `trust_env=False` 自动绕过。
- **返回**:`{"data":{"callcmd":...,"calldata":{...}},"errcode":0}`;失败形如
  `{"errcode":1001,"errmsg":"parameter error"}`。

## 常用操作

**查询类(安全,直接执行)**

```bash
python switchctl.py search                 # 组播发现设备
python switchctl.py login                  # WEB 登录(123),保存会话 cookie
python switchctl.py logout --yes           # 注销设备会话(POST /126)+ 清本地 cookie
                                           # 非交互(脚本/自动化)必须加 --yes,否则会等待确认而阻塞
python switchctl.py state                  # 设备状态(100,免登录)
python switchctl.py cmd-all                # 取回设备全部接口数据(200,需登录)
python switchctl.py detail --show-ports    # 设备详情 + 端口状态表(101,需登录)
python switchctl.py vlan-get               # 读 VLAN
python switchctl.py mac-get --port 4       # 读端口 4 的 MAC 表
python switchctl.py limit-get              # 读端口限速
python switchctl.py storm-get              # 读风暴抑制
python switchctl.py netcfg-get             # 读网络配置
python switchctl.py flow-get               # 读端口流控
python switchctl.py lldp-get               # 读 LLDP
```

**配置类(有风险,执行前会二次确认)**

```bash
python switchctl.py port-up   --port 1              # 开启端口
python switchctl.py port-down --port 1              # 关闭端口
python switchctl.py port-restart --port 1           # 重启端口
python switchctl.py poe --port 1 --on               # POE 开
python switchctl.py poe --port 1 --off              # POE 关
python switchctl.py phy --port 1 --mode full1000    # 设 PHY 模式
# 802.1Q 成员端口仅端口 25-28 有效(见下方"实现要点")
python switchctl.py vlan-set --vlantype 1 --vlanid 100 --untag-ports 25 --trunk-ports 26
python switchctl.py port-pri --ports 28 --pri 5       # 端口优先级 0-6(仅端口 25-28)
python switchctl.py port-mirror --catch 27 --catched 25   # 镜像:端口25 -> 27(仅 25-28)
python switchctl.py limit-set --up "[0,0,64]" --down "[0,0,64]"   # 值须为 64 的整数倍(0=不限速)
python switchctl.py storm-set --on
python switchctl.py reboot --yes                    # 重启设备(会断连)
```

> **MAC 表(114)在本机型固件中是空实现,`mac-get`/`mac-add`/`mac-del`/`mac-clear`
> 一定失败**——不要用,也不要写进脚本。

**任意命令(兜底)**

```bash
# vlanid / vlanport 必须是数组,porttype 必须是数字
python switchctl.py raw vlan '{"vlan":1,"vlantype":1,"vlanid":[100],"vlanport":[16777216],"porttype":33554432}'
python switchctl.py raw 109 '{"vlan":1,"vlantype":1,"vlanid":[100],"vlanport":[16777216],"porttype":33554432}'
# PortMirror 掩码只能 bit24-27(端口 25-28)
python switchctl.py raw PortMirror '{"Catch_port":134217728,"Catched_port":16777216}'
```

## 关键约定(容易踩坑)

1. **端口用"索引"表示**:人看到的端口号 1 对应索引 0。开关端口等命令由
   `build_config_opcode()` 自动换算,直接用 `--port <端口号>` 即可。
2. **端口掩码是十进制位掩码**:`vlanport`/`bitmap` 等字段里,端口 1、2 对应
   掩码 `3`(=0b11)。用 `port_mask(1,2)` 换算,`mask_ports(3)` 还原。
   (`vlan-set --untag-ports 1 2` 会自动换算。)
3. **callcmd 在 WEB 通道用命令号**。URL 路径和 body 都用数字(如 `/100`、`/109`、
   `/123`)。UDP/云端通道建议用字符串命令名(低版本固件只认字符串)。脚本的
   `resolve_callcmd_num()` 已自动把名字转成命令号。
4. **登录后必须带 Cookie**(见上"真机协议要点")。CLI 把会话 token 存在本地文件,
   一次 `login` 之后所有命令自动复用。
   - 若某命令报"空回复":多为该**命令号未在固件注册**;也可能是设备端会话被别的
     客户端占用(设备**只允许一个会话**),或本请求漏带 cookie。
   - **重置会话最快的办法是 `logout`(POST /126)**:它立即清除设备端会话
     (返回 `errcode 1003` = 登出成功),随后可**立刻** `login`,无需等待。
     备选办法:等约 2 分钟空闲超时,或重启设备。
   - **脚本/自动化里调用 `logout` 必须加 `--yes`**:该子命令默认带交互确认,
     非 TTY 环境下会等待输入而阻塞(表现为命令卡住/超时)。
   - 会话有效期内**不要**用不带 cookie 的请求反复试探,那只会一直被拒。
5. **errcode 语义**:`0` 为成功;`1001` 多为参数/业务被拒(常伴 `{"xxx":"fail"}`);
   `1000` 多为参数格式错误;`1003` 是 **`/126` 登出专用成功码**(非错误);
   **`-1` 表示该命令号在固件中未注册**(设备直接断连)。未知 errcode 按字面提示处理。
6. **配置生效有延迟(~10 秒)**:下发端口/VLAN 等配置后,立即读回可能仍是旧值,
   请等待约 10 秒再读回确认。
7. **config/103 是位运算 opcode**:`opcode = (value<<9) | (index<<4) | func`,
   func: 0-phy 1-iso 2-poe 3-端口重启 4-端口Admin 5-强制POE。
8. **WEB 通道无需加密**;UDP/云端通道需 TEA 加密(见 `scripts/` 下的 `tea` 模块)。
   **`search` 也必须加密**——设备无条件先解密再解析 JSON,明文请求直接丢弃。
   另外 UDP 客户端必须 `bind` 到 10086 并加入组播组才能收到响应(响应发往组播,
   不是单播回包)。详见 `references/protocol.md` 第 3.1 节。
9. **端口/数组长度可能不一致**:如 `pw`/`poec` 只含 PoE 口(24),`link`/`AdminState`
   含全部端口(28)。按索引解析时务必做边界保护(CLI 已处理)。
10. **功能可用性随固件而异**(已结合固件源码核对,PS424GV3 / V6.1.260918):
    - ✅ 可用:storm / lldp / flow / dhcp_snop / LoopNet / pwWarCfg / 端口类配置;
      **VLAN(802.1Q/MTU/端口VLAN)**、**端口优先级**、**端口镜像** 均可写(见下"实现要点")。
    - ❌ **不可用(固件层面,换参数也无效)**:`mac_table/114` 读、写都是**空实现**
      (`ssc_dev_macCfg` 恒 `return -1`);`TCP_ONLINE/131` 本机型**未编译**(返回 -1)。
    - 下发前先读回确认。
11. **几个易踩的"实现要点"**(源码+真机实测,详见 `references/commands.md`):
    - `vlan`: `vlanid`/`vlanport` **必须是数组**且必须带 `porttype`(数字);
      802.1Q 成员端口只用 **端口 25-28**;关闭也要带 `vlantype`。
    - `port_pri`: 只能设 **端口 25-28**(数组前 24 位须保持 0,否则整体 fail)。
    - `PortMirror`: 掩码只能用 **bit24-27(端口 25-28)**。
    - `limit`: 值须为 **64 的整数倍**(端口 27/28 的数组位须为 0)。

## 完整命令清单

所有命令号、参数含义、示例见 `references/commands.md`。
协议分层、报文结构、加密封帧见 `references/protocol.md`。
典型场景的完整实战示例见 `references/examples.md`。

## Python 中直接调用

```python
import sys
sys.path.insert(0, "<skill_dir>/scripts")
from ssc_web import SSCWebClient
from ssc_protocol import build_config_opcode, port_mask

cli = SSCWebClient("192.168.1.10")          # 或留空,读 SSC_HOST;密码读 SSC_PASSWORD
cli.login("YourPwd")                        # 登录(123);成功后会保存会话 cookie
print(cli.cookie, cli.cookie_file)          # 会话 token 与落盘位置
err, data = cli.state()                     # 设备状态(100)
err, data = cli.call(200)                   # 全部接口数据(200)
err, data = cli.call(109, None)             # 读 VLAN
err, data = cli.call(103, {"opcode": build_config_opcode(4, 0, 1)})  # 端口1 up
cli.clear_cookie()                          # 清除本地会话
```

> `SSCWebClient` 会**自动管理 Cookie 会话**:构造时读取本地会话文件,请求时带上
> `Cookie` 头,收到 `Set-Cookie` 就更新并落盘;若请求遇到空回复且配置了密码,会
> **自动重新登录并重试一次**。因此通常只需构造一次客户端即可连续操作。

- `ssc_web.SSCWebClient` — WEB 通道:POST 明文 JSON,返回 `(errcode, calldata)`。
- `ssc_udp.SSCUdpClient` — UDP 组播:`.search()` 发现设备,`.verify()` 安全验证。
- `ssc_protocol` — 命令注册表、消息构造、端口掩码/opcode、状态解码。
- `tea` — TEA 加解密与 base64 分帧(UDP/云端通道用)。

## 安全注意事项

- 危险操作(`reboot`/`reset`/`update`/`ResKey`/`dev_add`/`modify_key`)执行前
  必须向用户确认,CLI 已内置二次确认(可用 `--yes` 跳过,但不建议)。
- 恢复出厂(`reset`)、清空 MAC 表会不可逆地清除配置,务必谨慎。
- 设备地址仅通过环境变量/参数传入,不硬编码。
- UDP 组播仅限与本机同网段使用。

## 资源文件

- `scripts/switchctl.py` — 统一命令行入口(可读 Python;负责加载编译实现)。
- `scripts/_ssc_cli.cp313-win_amd64.pyd` — 编译后的 CLI 实现(全部子命令)。
- `scripts/ssc_web.cp313-win_amd64.pyd` — WEB 到设备 HTTP 通道客户端(`SSCWebClient`)。
- `scripts/ssc_udp.cp313-win_amd64.pyd` — UDP 组播通道(发现/验证,`SSCUdpClient`)。
- `scripts/ssc_protocol.cp313-win_amd64.pyd` — 协议核心:命令注册表、消息编解码、工具函数。
- `scripts/tea.cp313-win_amd64.pyd` — TEA 加密与分帧。
- `scripts/SHA256SUMS.txt` — 二进制模块的 SHA-256 校验值清单。
- `scripts/verify_checksums.py` — 可读、离线的校验脚本。
- `SECURITY_DISCLOSURE.md` — 二进制模块安全披露(用途、行为边界、校验方法)。
- `references/commands.md` — 全部命令清单与参数说明。
- `references/protocol.md` — 协议分层与报文格式。
- `references/examples.md` — 实战示例。
