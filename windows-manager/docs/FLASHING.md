> 1.5.10字体升级请使用 `firmware/elink-bwr-1.5.10.elink-update.json` 应用OTA包，配套管理端1.5.11，先在测试屏验收。下面是1.2.1历史有线恢复资料，其中旧文件名不适用于本次升级；不要整片擦除或覆盖底层配置。当前说明见 [FIRMWARE_1.5.10_TEST.md](FIRMWARE_1.5.10_TEST.md)。

# 有线安装和回退

此步骤会改写 Flash，须先留存设备读回备份。当前交付没有自动打开串口或自动烧录程序；避免向其他 USB 设备写入。

## 文件

- 完整 SPI 镜像：`firmware/elink-bwr-1.2.1-spi.bin`，241664 bytes / 0x3B000，写入偏移 **0**。双应用区、启动内容和本次五测试点屏幕配置已保留。
- `firmware/*-app.bin` 为应用镜像，用于分析；不要在 SPI 偏移 0 直接写此文件。
- `firmware/*.elink-update.json` 仅给管理端蓝牙 OTA。
- `rollback/hmclock-bwr-baseline-spi.bin` 为已经物理启动成功的 HMCLOCK 回退镜像。
- `tools/wired-helper/flash_programmer.bin` 是本机 5.0.10 已验证的 Flash 烧录助手，SHA256 为 `1c982e96de4eea64289c54f76b8da0c5cea7bfc23eae544543a04b9d32213333`。仅与 SmartSnippets Toolbox 5.0.10 对应支持包配套，修改安装目录前另存原文件。

## 接线及步骤

1. 电池取下。GND→GND；VBA→稳定 3.3V；标签 RX→串口 TX、标签 TX→串口 RX。确认信号亦是 3.3V；RST 平时悬空。线短、焊点牢固。
2. 设备管理器核对 CH340 实际 COM 口，不沿用之前 COM8，也不要把其他 USB 串行设备当作标签刷机线。
3. 使用之前已经成功的 SmartSnippets Toolbox SPI Flash 菜单和 UART 设置。SPI 配置：CLK=P0_0、CS=P0_3、MISO=P0_5、MOSI=P0_6。此前用户工具使用 P0_4/P0_5 57600 UART，须保留已实测可下载的组合。
4. Connect 等待复位提示后，RST 短暂接 VBA/3.3V 再松开；**此板复位为高电平，不接负极**。
5. 先读回目标擦除范围并导出新备份。当前文件需要覆盖低 0x3B000 字节；若工具只支持整片擦除，须先确认容量和完整备份。旧工具 `40000` 表示 256KiB 的操作范围，不能据此认定 Flash 总容量。
6. 选择完整 SPI 文件，偏移 0。沿用之前已验证的 Erase → Verify → Burn → Verify 方法。擦除读回应为 FF；烧录后须以文件逐字节比较或工具 Verify 通过为准。
7. 烧录验证完成后退出助手，断开全部供电再上电。新版本显示ELINK及本机完整MAC开机页；四块广播名为`ELINK-BWR-6B91A7`、`ELINK-BWR-6B8EBF`、`ELINK-BWR-6B8683`、`ELINK-BWR-6B8666`。打开1.2.1管理端读取ELK1状态，核对ID为90559ec8。关闭手机/旧网页的连接。若图片/LED/连接验收不通过，先保存日志，再用回退镜像同法刷回。

不要通过 OTP 菜单擦写、改变蓝牙地址或启动标志。没有确认实际 COM 口和复位窗口前，管理端不会替代这些检查直接写串口。
