# 云网管交换机协议说明

本文件描述云网管交换机私有协议的分层结构、报文格式与加密封帧方式,  
来源:《云网管系列接口说明(250806)》《Cloud_Series_API》《交换机接口文档(IPCC)》  
《交换机产测接口》《设备升级流程说明》。

## 1. 统一报文结构

**请求**

```json
{ "cmd": "主题名", "syn": "8位同步码", "data": { ... } }
```

**响应**

```json
{ "errcode": 0, "ack": "主题名", "syn": "8位同步码", "data": { ... } }
```

- `syn`:同步码(8 位),请求与响应必须一致。
- `errcode`:0 表示成功,其余为错误码。
- `ack`:响应主题名,与请求 `cmd` 对应。

## 2. 两条通道

### 2.1 WEB 到设备(推荐,已实测确认)

- 传输:HTTP **POST**,数据**不加密**,会话靠 **Cookie** 维持,支持多设备并发。
- **URL 路径 = 命令号**:`POST http://<ip>/<callcmd>`,如 `/100`、`/109`、`/123`。  
  未注册的命令号,设备(lwIP HTTP 服务)会**直接断开连接**(空回复)。
- 请求体(无参数时不带 `calldata` 键):


  ```json
  {"data": {"callcmd": 109, "calldata": { ... }}}
  ```
- 响应体:
  ```json
  {"data": {"callcmd": 109, "calldata": { ... }}, "errcode": 0}
  ```
  失败:`{"data":{"callcmd":123,"calldata":{"login":"fail"}},"errmsg":"parameter error","errcode":1001}`
- **会话靠 Cookie 维持(已实测,关键)**:
  - 先调 `Security_verification/123` 带 `{"password":"..."}` 登录,成功时  
    **响应头返回 `Set-Cookie: <裸 token>`**(非标准 `name=value` 形式,例如  
    `Set-Cookie: HaJ2HTgcNuLhu5OVWTqwLgA=`)。
  - **只要设备端存在活动会话,后续每个请求都必须带 `Cookie: <token>`**;不带则  
    设备**直接断开连接**(空回复)。该闸门**也管登录 `/123` 本身**:已有会话时,  
    不带 cookie 的登录请求同样被拒(实测:需等会话空闲超时后才可重新登录)。  
    这是 `/101`、`/200` 等"登录后仍失败"的真正原因。
  - 该 cookie 非标准,`requests` 的 cookie jar 会当非法值丢弃,故客户端  
    **手动**收发 `Cookie` 头(见 `ssc_web.py`),并把 token 持久化到  
    `~/.ssc_switch_sessions/<host>.cookie` 以便跨命令/跨进程复用。
  - **设备只允许一个会话**:若别处(如浏览器 WEB 界面)已登录并占用会话,  
    脚本必须等其空闲超时、或先调 `logout/126` 清除会话,才能重新登录。
  - 本通道专有命令:`123`(登录)、`120`(改密钥)、`126`(登出)、  
    `200`(cmd_all 取全部接口数据)。
- **登出 `/126`(已真机验证生效)**:`POST /126`,body `{"data":{"callcmd":126}}`,  
  **立即清空设备端会话**,旧 cookie 随即失效,重登会换发新 cookie。
  - **正常返回 `errcode 1003`**——登出**专用成功码,不是错误**(设备前端亦以 1003  
    判定登出完成);`0` 同样视为成功。代码中 `ssc_web.LOGOUT_OK_CODES = {0, 1003}`。
  - 验证方法要点:判定"会话是否被清"必须用**需登录**的接口(如 `/200`);  
    `/100` 免登录,清不清会话它都返回 0,不能作判据。
- **会话空闲超时 ≈ 2 分钟(固件实测)**:  
  固件每秒对 `cookie_info.idleTime` 累加,**仅当收到带正确 cookie 的请求时才清零**;  
  累计约 20000 次(≈2 分钟)后执行 `memset(&cookie_info,0,...)` 清空会话。  
  推论:①每个请求都带 cookie → 会话长存;②不带 cookie 的请求会持续被拒,  
  直到 ~2 分钟超时后会话自动失效,请求才恢复。**这不是"设备被打饱和"**——  
  实测带有效 cookie 连发 12 次(间隔 0.3s)全部成功,频率不是瓶颈。  
  ③`/126` 登出可**立即**解除会话,无需等这 2 分钟。
- **必须绕过系统代理**:环境里若设了 `http_proxy`,内网设备会连不上。  
  `ssc_web.py` 已内置 `session.trust_env = False`。
- 用 `scripts/ssc_web.py` 或 `switchctl.py` 直接调用。

### 2.2 客户端到设备(UDP 组播)

- 组播地址 `239.0.0.100`,端口 `10086`。
- 请求体:
  ```json
  {"cmd":"calludp","syn":"xxxxxxxx","data":{"callcmd":119,"sn":"..","calldata":{...}}}
  ```
  `calldata` 为空时**应省略该字段**——固件自身的 `getDEV()`
  (`iot_local.c:171`)就是这样发的。
- 响应体 `ack` 为 `calludp`。
- 用途:`search`(发现)、`Security verification`(激活/登录)、`modify_key`(改密钥)。
  注意安全验证的命令名是 **`Security verification`**(完整写法),
  低层 bug 写法 `Security ver` 不会被匹配。
- 这些是本地管理命令,管理前需先通过安全验证。

**接收响应必须满足两个条件**(否则永远收不到):

1. **请求必须加密**。设备侧在 `iot_local.c:305` 对收到的报文
   **无条件**先做 `base64 解码 + TEA 解密` 再交给 JSON 解析,
   明文请求会被静默丢弃。此前"search 免加密"的说法是错的。
2. **套接字必须 `bind` 到发送端口 10086 并 `IP_ADD_MEMBERSHIP` 加入组播组**。
   设备在 `net/ssc_net.c:202` 把响应发往 **组播 `239.0.0.100:<请求源端口>`**,
   不是单播回给请求方——只发不绑收不到。

实测正常设备 **0.1 秒内**应答;若某台设备 ping 通却对 UDP 和 HTTP 都无反应,
是其应用层已挂死,需断电重启,与本通道实现无关。

## 3. 加密封帧

WEB 通道:**不加密**。

UDP / 云端通道:请求数据先 **TEA 加密**,再 **base64 编码**,最后以 `\r\n` 结尾。  
设备响应用相同方式加密。

- 密钥:
  - `activate` 由云分配 `did`;
  - `connect` 由云分配 `key`(16 位可见字符),作为后续加密密钥;
  - 本地管理则由 `Security verification` / `modify_key` 设置的管理密钥。

## 4. 端口编号与掩码

不同版本端口编号规则不同:

- V2.0:对应端口号配置
- V2.1-V2.2:默认远离级联口为起始端口,按索引
- V3.0:无固定级联口,机器正放最左为第一个端口(或左上),按索引

协议内部统一用**索引**(端口号 - 1)。`vlanport`/`bitmap`/`porttype`/`Catched_port`  
等是**按位表示的十进制掩码**:

| 端口 | 位    | 掩码贡献 | 组合示例           |
| -- | ---- | ---- | -------------- |
| 1  | bit0 | 1    | 端口1,2 → 3      |
| 2  | bit1 | 2    | 端口3,4 → 12     |
| 3  | bit2 | 4    | 端口1,2,3,4 → 15 |
| 4  | bit3 | 8    | 端口2,3,4 → 14   |

工具函数:`port_mask(1,2) -> 3`,`mask_ports(12) -> [3,4]`。

## 5. 状态字段字典

- `link` / `phyc`:0-未连接 1-半双工10M 2-全双工10M 3-半双工100M 4-全双工100M 5-全双工1000M
- `snr`:0-优 1-良 2-差
- `stpPort_State`:0-Disable 1-Discarding 2-Learning 3-Forward
- `AdminState`:0-phydown 1-phyup 2-环网阻塞
- `fwd`(MAC):0-系统默认 1-LAN+CPU 2-LAN 3-仅CPU 4-丢弃
- `cloud_status`:0-未在线 1-在线
- `Active_state`:`active` 已激活 / `not_active` 未激活

## 6. 版本差异速查

| 功能                                             | 起始版本 |
| ---------------------------------------------- | ---- |
| limit/storm/netcfg                             | V2.1 |
| dev_add/ResKey/本地管理                            | V2.2 |
| mac_table/PortMirror/dhcp_snop/LoopDetect      | V3.0 |
| lldp                                           | V2.3 |
| AI_AnAuto/AI_Wdog                              | V2.4 |
| LoopNet(环网)/event/port_mibCnt/get_dev/port_pri | V3.2 |
| LBZ/pwWarCfg                                   | V3.1 |
