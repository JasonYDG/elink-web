# Firmware 1.5.13 candidate

首次保存离线图库需配合 Web 1.1.4。尚未完成实物验收，不自动给设备升级。Windows Manager 1.5.14 的历史二进制没有新检查协议；首次保存请使用新版网页，已有图库不受此协议要求影响。

用户报告：Windows Edge / Web 1.1.3，设备此前从未保存图库，选 7 张用于图片日历，在分区检查约 30 秒后报 GATT 错误，随后出现开机默认画面。默认画面支持发生重启的判断；目前没有复位寄存器或串口证据，不能确定是看门狗、供电还是其他复位。

旧应用在一个 `BD 01` 回调内同步扫描完整 120 KiB，调用 1,920 次 64 字节原生 Flash 读取，之后才创建元数据。原生读取使用软件 SPI。新应用把检查拆为 `BD 06 part` 的 120 次只读请求，每次 1 KiB，逐次返回 `ELAP` 进度，让固件在请求之间回到蓝牙事件循环。全部确认空白后才允许 `BD 01`；未完成、乱序、未知数据、重启和元数据创建失败均拒绝再次初始化。不会清空未知分区来绕过检查。

保留 7 张、8000 字节原生帧、双图像区、交替 CRC 元数据和最后有效字节提交。已有图库跳过首次空白检查。新图每张仍分 32 次保存，核对设备进度后，最后一次提交播放列表；提交中断不自动重放。应用 60,028 字节，保留状态 124/128 字节，原有代码区域、堆、栈、驱动、波形、启动与 OTP/MAC 边界保持。

## 参考的卡槽管理方法

只读比较了用户的 4.2 寸项目：查询设备容量与槽位状态、只向允许的目标保存、分块传输、核对长度与 CRC 后标记可用、轮播设置再读回确认。这些方法用于本版检查和回执设计；没有复制 4.2 寸固件、字体或私有资源，也没有扩大 2.13 寸存储范围。

网页增加“上次读回的播放槽”，逐槽显示已保存状态、CRC32、当前槽位；未提交的新图库进度单独显示。这里的槽位是已提交列表中的逻辑播放位置，不代表可直接擦除的物理空槽。网页选图是草稿，点击应用才保存。2.13 寸继续保留整组交替提交，未新增独立删除或覆盖物理槽命令。

## 重建与验证

此目录为增量源码。以本仓库提交 `bbb6e9761770c2686e04dacae3b2445886fd6b73` 的 `windows-manager/` 为项目根，把 `overlay/` 下的文件按原路径覆盖到该根目录。未变更的源码、字体、许可证与测试都从该固定提交获取；`provenance.json` 列出覆盖文件及哈希。

使用原有 `source/tools/development-lock.txt` 环境和 Zig 0.13.0，后者位于 `runtime/tools/zig-windows-x86_64-0.13.0/`。还需自行提供 `provenance.json` 中哈希固定的两份原始 HMCLOCK 基线夹具，放到 `source/reference/`；它们不随公开包分发。源码覆盖不代表重建过 Windows 程序。

```powershell
runtime/venv/Scripts/python.exe source/firmware/build.py --version 1.5.13 --output build/firmware-1.5.13
$env:ELINK_TEST_FIRMWARE_DIR=(Resolve-Path build/firmware-1.5.13).Path
runtime/venv/Scripts/python.exe -m unittest discover -s source/tests -p test_album_preflight.py -v
runtime/venv/Scripts/python.exe -m unittest discover -s source/tests -p test_album_seven.py -v
```

验证执行实际编译 Thumb 应用，模拟 ROM、SPI、BUSY 和传输；新检查 4 项、七图保护 5 项、管理端实际协议链 1 项、模块/状态/OTA 11 项通过。网页 52 项 Node 测试通过。测试不证明实体屏幕的蓝牙时序、供电、光学显示、长期轮播或真实掉电恢复。

应用 ID `f1ef98a7`，SHA256 `b6347e11f4a6c305d5b6540e61e71b564bbff2d623d26677205064f6be443c75`。网页只接受专用 `.elink-update.json`；不分发全片 SPI 镜像作为升级包。

升级：在 Web 1.1.4 连接并读取单台屏幕，加载在线固件 1.5.13，核对目标和版本，输入 `UPDATE` 确认。等待 OTA 读回及重启版本核对后，再保存 7 张图片；保持供电、网页前台及连接。
