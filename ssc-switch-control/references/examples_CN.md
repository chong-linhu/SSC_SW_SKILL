# 云网管交换机实战示例

以下示例均假设已设置 `SSC_HOST`(设备 IP)。脚本目录按实际路径替换。

## 场景 0:发现内网设备并确定 WEB 路径

```bash
cd scripts
# UDP 组播发现(不用知道 IP)。请求已按固件要求自动 TEA+base64 加密
python switchctl.py search
# 输出例:{"ip":"192.168.1.10","sn":"...","mac":"...","model":"PS208GV3",
#         "V":"6.0.250111","Active_state":"active"}

# 正常设备 0.1 秒内应答;默认等待 6 秒
python switchctl.py search --timeout 10

# OEM 为 WEIWO 的设备,密钥不同,需指定(否则解不开响应)
python switchctl.py search --oem weiwo
```

无返回时的排查顺序:

1. 本机是否与设备同网段(组播默认不跨网段路由);
2. 防火墙是否放行 **UDP 10086 入站**;
3. 是否有其他云网管客户端占用了 10086 端口(会报绑定失败);
4. 目标设备应用层是否挂死——用 `ping` 和 HTTP 对比确认:
   ping 通但 HTTP 也超时的话,需给设备断电重启。

拿到 IP 后,先登录建立会话,再查询:

```bash
export SSC_HOST=192.168.1.10 SSC_PASSWORD=<PASSWORD>
python switchctl.py login                  # 登录,成功会提示会话 cookie 与保存路径
# 例:会话 cookie: 26zG0fCoHs01/sY4yj/cBAA=
#     已保存到: C:\Users\<你的用户名>\.ssc_switch_sessions\192.168.1.10.cookie
python switchctl.py detail --show-ports    # 之后命令自动复用该 cookie
```

> URL 路径就是命令号(如 `/100`、`/101`、`/200`),**无需**猜测子路径。
> 若某命令返回"空回复",多半是会话失效或该命令号未在该固件注册:
> 先 `python switchctl.py logout && python switchctl.py login` 重建会话再试。

## 场景 1:查看设备与端口状态

```bash
python switchctl.py detail --show-ports
```

输出端口表格(连接状态、功率、信噪比、STP、管理状态)。
JSON 里 `link[i]` 对应端口 `i+1`,值 0-5 表示未连/各速率。

## 场景 2:开关某个端口

```bash
python switchctl.py port-down --port 3    # 关闭端口 3
python switchctl.py port-up   --port 3    # 开启端口 3
```

等价于 `config/103`,`opcode = (1<<9)|(2<<4)|4`(端口3 → 索引2,phyup=1)。

## 场景 3:重启端口 / 控制 POE

```bash
python switchctl.py port-restart --port 3     # 软重启端口(常用于重新协商)
python switchctl.py poe --port 3 --off        # 关闭该口 POE 供电
python switchctl.py poe --port 3 --on
```

## 场景 4:配置 802.1Q VLAN

需求:创建 VID=100 的 802.1Q VLAN,untag 端口 25,trunk 端口 26。

> ⚠️ **端口范围限制(固件决定,不是 bug)**:802.1Q 的成员端口掩码只处理
> **bit24-27,即端口 25-28**。传端口 1-24 不会被 `dev_802VLAN` 处理,配置不会生效。

```bash
python switchctl.py vlan-set --vlantype 1 --vlanid 100 \
    --untag-ports 25 --trunk-ports 26
```

底层报文:`{"vlan":1,"vlantype":1,"vlanid":[100],"vlanport":[16777216],"porttype":33554432}`
- `--untag-ports 25` → 掩码 1<<24 = 16777216
- `--trunk-ports 26` → 掩码 1<<25 = 33554432
- **`vlanid` / `vlanport` 必须是数组**;`porttype` 必须是数字(传数组会被固件判参数错)

关闭 VLAN(必须带 `vlantype`,否则固件误报 1001):

```bash
python switchctl.py vlan-set --off --vlantype 1
```

先读后写(推荐):

```bash
python switchctl.py vlan-get
```

## 场景 5:MAC 地址管理

```bash
python switchctl.py mac-get --port 4                    # 读端口 4 的 MAC 表
python switchctl.py mac-add --mac 80:FA:5B:2B:12:47 --port 4   # 绑定静态 MAC
python switchctl.py mac-del --mac 80FA5B2B1247 --port 4       # 删除
python switchctl.py mac-clear --yes                     # 清空(危险)
```

端口 4 → 掩码 8。一个端口最多绑定 5 条 MAC,绑定后该口关闭学习。

## 场景 6:端口限速与风暴抑制

```bash
python switchctl.py limit-get
# 给端口 3 设上下行 1000kbps(数组按端口索引;其余端口 0 表示不限速)
python switchctl.py limit-set --up "[0,0,1000]" --down "[0,0,1000]"

python switchctl.py storm-set --on     # 开启风暴抑制(广播/组播/单播限 4Mbps)
python switchctl.py storm-set          # 关闭
```

## 场景 7:网络配置

```bash
python switchctl.py netcfg-get
python switchctl.py netcfg-set --dhcp                       # 启用 DHCP
python switchctl.py netcfg-set --ip 192.168.1.20 --gw 192.168.1.1 \
    --mask 255.255.255.0 --dns 223.5.5.5                    # 静态 IP
```

## 场景 8:端口镜像与流量统计

```bash
# 端口 1 捕获端口 2,3,4 的流量
python switchctl.py raw PortMirror '{"Catch_port":1,"Catched_port":14}'
# 关闭镜像
python switchctl.py raw PortMirror '{"Catch_port":0,"Catched_port":0}'

# 端口流量包统计(V3.2)
python switchctl.py raw port_mibCnt '{"port":4}'
python switchctl.py raw port_mibCnt
```

## 场景 9:LLDP 邻居发现

```bash
python switchctl.py lldp-set --on
python switchctl.py lldp-get       # V3.0 返回 lldp_info,含邻居端口/系统名/管理地址
```

## 场景 10:环网 / 端口优先级(V3.2)

```bash
python switchctl.py raw LoopNet '{"LoopNet":1,"mode":1}'   # 开启环网,成环自恢复
python switchctl.py raw port_pri '{"PortPri":[0,1,5,2]}'   # 端口优先级 0-6
```

## 场景 11:恢复出厂 / 重启(危险)

```bash
python switchctl.py reboot --yes     # 软重启
python switchctl.py reset --yes      # 恢复出厂(清空所有配置!)
```

## 场景 12:Python 批量操作

给 1~8 号端口统一开启 POE:

```python
import sys
sys.path.insert(0, "scripts")
from ssc_web import SSCWebClient
from ssc_protocol import build_config_opcode

cli = SSCWebClient("192.168.1.10")
for port in range(1, 9):
    opcode = build_config_opcode(func=2, port_index=port - 1, value=1)  # POE 开
    err, data = cli.call("config", {"opcode": opcode})
    print(f"端口{port}: errcode={err} {data}")
```

导出所有接口数据留档:

```python
import json
err, data = cli.call("cmd_all", None)
open("device_dump.json", "w", encoding="utf-8").write(
    json.dumps(data, indent=2, ensure_ascii=False))
```

## 排错速查

| 现象 | 排查 |
|------|------|
| 连接被拒绝 | IP/端口不对,或设备 WEB 服务未开 |
| 响应不是合法 JSON | `--path` 路径不对,或该路径返回了 HTML 页面 |
| errcode 非 0 | 参数越界(如 vlanid<2)、端口不存在、该机型不支持 |
| UDP search 无返回 | 见场景 0 的排查顺序:网段 / UDP 10086 入站 / 端口被占用 / 设备应用层挂死 |
| 配置成功但无效果 | 部分机型/版本不支持该功能;或需先 `vlan`/`detail` 读当前值再改 |
| 端口号对不上 | 注意索引规则与机型首端口定义(见 protocol.md 第 4 节) |
