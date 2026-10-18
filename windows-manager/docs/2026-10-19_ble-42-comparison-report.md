# 4.2 寸通信路径对照与 2.13 服务发现故障

2026-10-19。目标是核对连接生命周期及实际错误恢复，修复 Windows 管理端过早判断接口缺失和手动任务过久重试的问题。只修改管理端应用，不修改任何屏幕的启动、射频、Flash 驱动、显示波形、MAC 或分区。

## 范围与证据

案例目录为 `backup/2026-10-19/ble-discovery-1.5.12`，其中 `scope.md` 和 `timeline.md` 保存本轮范围及检查顺序。4.2 样本只读，未安装 APK、未修改授权、未连接或刷写 4.2 实机。

| Evidence | 来源与复跑方式 | 哈希或结果 |
|---|---|---|
| E-01 | 生产数据库 `mode=ro` 读取，目标设备三次 probe 均在服务发现阶段失败；之后用户报告恢复 | 尚未发送状态命令就终止；不能据此诊断屏幕固件损坏 |
| E-02 | 案例 `physical-gatt-cached-comparison.json`；空闲时运行 `runtime/venv/Scripts/python.exe backup/2026-10-19/ble-discovery-1.5.12/inspect_gatt.py --cached` | 同一完整 MAC 的筛选及全量服务发现均含 FF00、FF01；FF01 handle 15，read/write，读到 11B。此脚本不发送控制命令 |
| E-03 | 用户指定 `F:/AI/4.2-Elink/APK/final.apk`，APK 版本 1.6.5，包名 `com.gclab.epdcontrol` | SHA256 `a651bfb07f5980d5e5cbaba9445237cf2d7bf6b4419a3127493e8d0928a6cf84` |
| E-04 | 从该 APK 原样提取 DEX，用 Android SDK 35.0.0 的 `dexdump -d` 反汇编；案例 `apk/` 中保存原 DEX、指令及 `x0.f` 回调片段 | `onConnectionStateChange`、`onServicesDiscovered`、`onMtuChanged`、`onCharacteristicWrite` 的真实方法调用；不是只搜索界面文案 |
| E-05 | 原版 `OM6626Full-261008.bin`，案例 `verify_reference_transport.py` 对照原 BIN 并执行局部 Thumb 指令 | SHA256 `6fcedbb08bc39361a29b15e3ad22cbdd9d5907ed7f54b15d9405c5a2f81bd7ca`；98 行指令字节一致，四组 MTU、连接重置及断开清理断言通过 |
| E-06 | 案例 `regression-before.txt` / `regression-after.txt`，`runtime/venv/Scripts/python.exe -m unittest discover -s source/tests -p test_ble_connection.py -v` | 旧管理端在首次缺项恢复及手动重试上失败，新管理端通过；1.5.2 使用原始二进制 `3bbf1f31`，未改版本号冒充旧实现 |

复跑原固件实验：

```powershell
runtime/venv/Scripts/python.exe backup/2026-10-19/ble-discovery-1.5.12/verify_reference_transport.py
```

DEX 指令输出含 Android modified UTF-8 字符串，导出局部片段时将不合法 UTF-8 字节显示为转义；原 DEX 未改动。Dart 业务库的完整 AOT 调用图仍未恢复，不能据这些 Android 回调推定业务层重连次数、退避时长、PRN 用途或无响应写入窗口。

## 已确认的对照

| 层次 | 4.2 原实现的代码证据 | 2.13 管理端的处理 |
|---|---|---|
| 连接与服务分开 | `x0.f.onServicesDiscovered` 的 DEX 偏移 `0x0FBF04` 枚举 `getServices()`，向上层发送 `OnDiscoveredServices`、成功位、错误码及文字；连接回调另发 `OnConnectionStateChanged` | 原代码连接后只查一次 FF01，缺项直接失败。本版在发命令前最多三次释放并重新发现 |
| 连接状态清理 | `x0.f.onConnectionStateChange` 的 `0x0FB6B0–0x0FB6F0` 删除连接相关映射，非 auto-connect 分支执行 `gatt.close()`；连接成功时 MTU 映射从 23 开始 | 保留每次操作的独立状态与 uncached GATT，不复用失败服务表；最终清理不覆盖主错误 |
| 已连接对象可继续发现 | 用户确认无其他客户端，但 Windows 返回已连接，同一完整 MAC 没有在本次扫描出现，见 E-02 的缓存身份诊断 | 扫描未发现时，仅对系统确认为已连接且 MAC 完全匹配的对象继续发现服务；不把系统连接状态当作业务就绪 |
| MTU 来自协商结果 | APK 的 `onMtuChanged` 保存 MTU 并上报错误状态；原固件 `0x004208C4–0x004208DC` 保存 ATT MTU 减 3 | 继续按设备能力与真实连接 MTU 限制像素包，旧版回退 17B。不会照搬 App 文案中的 244 |
| 新连接重置会话 | 原固件 `0x0042088C–0x004208A4` 将值长度恢复到 20，并清除该连接的命令长度/状态标志 | 业务开始前重新读状态和能力。没有改动 2.13 的原生蓝牙初始化 |
| 写入回调与业务完成 | `x0.f.onCharacteristicWrite` 在 `0x0FB360` 起构造 `OnCharacteristicWritten`，带 success 和错误信息 | 保留带响应 GATT 写、接收位置、校验和、BUSY/代次及实际读回；GATT 确认仍不等于实物刷新完成 |
| 断开后释放传输对象 | 原固件 `0x004216BC–0x004216EE` 调用对象清理回调，清空 `0x20005020+0x18` 指针，再执行后续清理路径 | 本版只改善主机侧连接准备。图库和 OTA 提交后只重连核对，不重复提交 |
| 设备命令门禁 | 原固件有 OTA active 与 EPD busy 分支，拒绝冲突命令 | 原有串行队列与设备 busy 检查保留；手动连接失败最多三次停止，避免 24 小时任务锁 |

局部固件执行仅替换硬件/日志回调，不改所执行指令。MTU 23/131/247/517 分别得到 20/128/244/514；连接事件清理断言和断开对象指针清零断言通过。这验证代码路径，未测量 4.2 实机无线吞吐或供电表现。

## Findings 与调用路径

- **F-01**：`validated`，`n/a_re`，证据 E-01/E-02/E-06，置信度高；位置 `source/backend/gateway.py` 初始连接。首次服务发现缺项不足以支持“设备没有 FF01”的确定诊断。修复为发命令前有界恢复，失败保留实际 UUID。Windows 底层为何偶发缺项仍是待确认项。
- **F-02**：`validated`，`n/a_re`，证据 E-06，置信度高；位置同文件 `worker`。手动未连接任务原先最多重试 24 小时，且统一操作锁持续占用。修复为三次停止；后台接收窗口策略保留。
- **F-03**：`validated`，`n/a_re`，证据 E-03/E-04/E-05，置信度高；位置为上表 DEX/Thumb 地址。值得移植的是会话状态边界与完成条件，不能从芯片不同的实现复制驱动、句柄或固定包长。

**P-01 / callflow**：选定完整 MAC → 连接会话 → 发现 FF01（缺项则释放后重试，最多三次）→ 读取状态/能力/MTU → 执行既有协议 → 核对设备结果 → 释放会话。若请求已提交后断开，进入只读核对或未知结果，不从链首重放操作。

## 边界

此前报告主要是功能与字符串线索，没有完成 Flutter Dart 业务层的完整重连分析；本轮补充了实际 Android 回调和原固件局部执行，仍不宣称完整恢复该 APK。没有证据保证两种芯片获得相同速度。新管理端须继续做现场重复读取、跨屏切换、长时间连接、图库保存及 OTA 验收；软件测试与显存读回不能证明光学效果或续航。
