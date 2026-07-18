


In [85]:

In [85]: !adb logcat -c && adb logcat -v threadtime | findstr /i "python"
07-18 05:42:27.719  3568  3587 I python  : [Connecting] Connecting to midea via BLE GATT...
07-18 05:42:28.830  3568  3587 I python  : [GATT] Connected to midea, discovering services...
07-18 05:42:29.616  3568  3587 I python  : [GATT] Services discovered successfully
07-18 05:42:29.619  3568  3587 I python  : [GATT] Found AC core service: FFA0
07-18 05:42:29.623  3568  3587 I python  : [GATT] BLE channel established! Panel unlocked.
07-18 05:42:38.447  3568  3587 I python  : [Command] Sending: Power:False, Temp:25, Mode:Cool, Fan:Auto
07-18 05:42:43.839  3568  3587 I python  : [GATT] Disconnected from midea
07-18 05:42:52.620  3568  3587 I python  : [Connecting] Connecting to midea via BLE GATT...
07-18 05:42:53.879  3568  3587 I python  : [GATT] Disconnected from midea
07-18 05:42:59.868  3568  3587 I python  : [INFO   ] [Clipboard   ] Provider: android
07-18 05:43:40.258  3568  3587 I python  : [Connecting] Connecting to midea via BLE GATT...
07-18 05:43:43.792  3568  3587 I python  : [GATT] Connected to midea, discovering services...
07-18 05:43:44.437  3568  3587 I python  : [GATT] Services discovered successfully
07-18 05:43:44.445  3568  3587 I python  : [GATT] Found AC core service: FFA0
07-18 05:43:44.452  3568  3587 I python  : [GATT] BLE channel established! Panel unlocked.
07-18 05:43:49.331  3568  3587 I python  : [Command] Sending: Power:True, Temp:25, Mode:Cool, Fan:Auto
07-18 05:43:51.921  3568  3587 I python  : [Command] Sending: Power:False, Temp:25, Mode:Cool, Fan:Auto
07-18 05:43:52.905  3568  3587 I python  : [Command] Sending: Power:False, Temp:26, Mode:Cool, Fan:Auto
07-18 05:43:53.740  3568  3587 I python  : [Command] Sending: Power:False, Temp:27, Mode:Cool, Fan:Auto
07-18 05:43:55.503  3568  3587 I python  : [Command] Sending: Power:False, Temp:27, Mode:Cool, Fan:Low
07-18 05:43:56.461  3568  3587 I python  : [Command] Sending: Power:False, Temp:27, Mode:Cool, Fan:Medium
07-18 05:43:57.370  3568  3587 I python  : [Command] Sending: Power:False, Temp:27, Mode:Cool, Fan:High
07-18 05:43:58.813  3568  3587 I python  : [GATT] Disconnected from midea



结论： 当你在 UI 上疯狂点击时，App 只是在本地改变了变量并打印了文本，根本没有通过 writeCharacteristic 把指令推送到蓝牙通道里。空调没有收到任何字节，自然不会有反应。

核心推理 2：为什么连接后 10~15 秒会自动断线？
日志显示了极其规律的时间差：

连接成功：05:42:29 -> 断开：05:42:43 (存活 14 秒)

连接成功：05:43:44 -> 断开：05:43:58 (存活 14 秒)

这是美的/华凌 BLE 固件的“鉴权超时机制（Security Timeout）”。

防黑客机制： 现在的智能家电绝不是你连上蓝牙就能随便控制的。空调的固件中有一个计时器。当手机建立 GATT 连接并发现服务后（05:42:29），计时器开始倒数。

强制踢下线： 固件要求手机必须在 10~15 秒内，向特定特征值（FFA1）发送正确的加密握手包（Session Token / 密钥协商）。

日志暴露的事实： 在这 14 秒内，你只点了温度和风量，并没有点击 "Handshake (Security)" 按钮，或者即使点了，发送的也是代码里写死的假数据 [0x5A, 0x0A, 0x03, 0x11, ... 0xFF]。

结论： 空调等了你 14 秒，发现你既不亮明身份，也不发合法的加密秘钥，于是出于安全策略，主动掐断了蓝牙连接（Disconnected from midea）。

核心推理 3：为什么第二次连接立刻就被拒绝？
日志：

05:42:52 ... Connecting...

05:42:53 ... Disconnected... (仅 1 秒)

因为空调刚刚因为“鉴权失败”把你踢下线，它的蓝牙协议栈通常会有几秒钟的“冷却锁定时间”或清理资源的延迟。如果在它释放底层资源前立刻强连，会被直接 Reject。

下一步必须攻克的难点：美的 Msmart 协议
你现在的代码处于“物理线已经接好，但双方语言不通”的阶段。要让空调听话且不断线，必须解决真实的协议问题：

真实的加密握手：
美的系空调走的是 Msmart V3 / V4 协议。通过 BLE 连接后，必须抓取真实美居 App 的数据包，分析它是如何做 AES 协商的。代码里的 mock_c1_packet 是过不了空调的安全校验的。

指令帧的封包与加密：
空调听不懂字符串 "Power:False, Temp:25"。一条完整的美的控制指令通常是以 0x5A 开头的几十个字节的十六进制数组。

它包含了：包头 5A + 长度 + 消息类型（控制包通常是 0x02 或 0x03）+ 具体的位操作（温度占某一个 Byte 的某几位，风速占另一位）+ CRC8 校验 + 最终整体的 AES 加密。

修正建议：
如果你想让界面按钮起作用，你必须重写 send_current_ac_frame 和 send_security_handshake。你需要一个针对 Midea BLE 协议的 Python 编码解码库（类似 GitHub 上开源的 msmart 库的 BLE 变种），把温度 26 度翻译成类似 [0x5A, 0x28, 0x01, ..., 0x1A, 0xXX] 这样的二进制串，然后通过 self.active_gatt.writeCharacteristic(self.active_write_char) 发出去。