# 维护固件的四个静态模块

最新源码已进入1.5.4功能测试阶段，新增单张图片日历、大包接收及只读Flash诊断，见 [测试说明](FIRMWARE_1.5.4_TEST.md)。下文“逐字节相同”特指已归档的1.5.2纯拆分里程碑；新增功能不再与旧应用逐字节相同，但原生底层代码保持不变。

时钟、日历、提醒和图片现在按模块维护，使用构建端的 `elink-static-modules-1` 清单登记源文件、入口和代码归属。它们仍编译成一个完整固件；本轮不增加设备端插件表、动态加载器或新的蓝牙命令。

本轮只验证模块拆分的成本，不接入相册、不重新分配 Flash，也不改变未校时行为。构建后的应用和 SPI 镜像与原 1.5.2 逐字节相同。空间结论与验证证据见 [本次报告](2026-10-18_firmware-modules-report.md)。

## 找到需要修改的功能

| 模块 | 源码 | 入口 | 运行条件 |
|---|---|---|---|
| 时钟 | `firmware/modules/clock/render.inc`、`schedule.inc` | `clock_face`、`product_clock`、`product_view` | 当前分钟入口要求已校时 |
| 日历 | `firmware/modules/calendar/render.inc`、`photo.inc` | `calendar`、`photo_calendar` | 共用分钟入口，跨日刷新；单图主题先完整上传图片 |
| 提醒 | `firmware/modules/reminder/reminders.c` | `product_reminder_cmd`、`product_reminder_tick`、`product_reminder_finish` | 后台检查保留；真实提醒要求已校时及偏移有效 |
| 图片 | `firmware/modules/image/commands.s` | `begin`、`data`、`commit` | 无需校时；继续接收 8000B 固定像素帧 |

公共核心在 `product_ui.c`、`product_runtime.h`、`extension.s` 和 `helpers.s`：字体和绘制原语、日期计算、时区、屏幕刷新/BUSY、清屏与目标两阶段、蓝牙分发、回包、广播、OTA 和原生入口补丁。日期/农历/节气计算同时服务时钟和日历，不复制进两个模块。

`.inc` 是有意采用的 C 编译片段。它们按原有顺序组合进一个编译单元，保留跨函数内联和机器码布局；提醒继续单独编译。图片汇编片段先在构建端展开，再统一解析标签、分支和常量池。不要把这些片段当作可以独立链接的动态插件。

## 按统一清单登记模块

清单入口：[modules.json](../firmware/modules.json)。构建器实际读取此文件，选择独立 C 源文件、核对 C/汇编片段的组合位置、核对最终已编译入口，并生成模块代码统计。

| 字段 | 含义 |
|---|---|
| `id` | 固定英文模块名，不等于设备显示模式数值 |
| `sources` | `c_fragment` 在 `product_ui.c` 中组合；`c_source` 单独编译；`asm_fragment` 在 `extension.s` 中展开 |
| `hooks` | 逻辑入口名到现有 C 函数或汇编标签的绑定；未使用的入口省略 |
| `owned_functions` | 用于预算的 C 函数归属；编译器内联后的函数可能没有独立符号 |
| `legacy_routes` | 现有协议路由说明，供维护者查阅，不生成或修改分发代码 |
| `requires_time` | 功能依赖说明，不自动改变现有调度条件 |

接口版本为 1，采用现有入口签名：C 绘制入口 `void(void)`；现有分钟入口 `void(unsigned flags)`；页面选择入口 `int(unsigned view)`；提醒命令入口 `int(const u8 *message, unsigned n)`，message 含原6B消息头；提醒 tick 返回是否占用本轮调度；提醒 finish 无参数。图片入口使用现有汇编寄存器/栈约定。统一的是构建登记和职责契约，本轮保留这些已验证的不同调用约定。

不在模块中自行改写 OTA 区、产品/面板配置、未分配 RAM 或屏幕忙状态。原协议保持：校时 `91/9E`，恢复时钟 `98`，页面选择 `9C 00/01`，图片 `95/96/97`，提醒 `B0..BB`；`9C 02` 默认页和其余能力/状态/策略接口也原样保留。

## 构建并查看空间

以下 PowerShell 命令从 `F:/AI/2.13-Elink` 工作区根目录执行，使用已有隔离环境，不连接设备：

```powershell
runtime/venv/Scripts/python.exe source/firmware/build.py --version 1.5.7 --output build/firmware-1.5.7
$env:ELINK_TEST_FIRMWARE_DIR=(Resolve-Path 'build/firmware-1.5.7').Path
runtime/venv/Scripts/python.exe -m unittest discover -s source/tests -v
# 当前相册新增区段，比较见随构建提供的 comparison.json；旧的同布局比较工具会拒绝不同区段集合。
```

最后一条的 `--require-identical` 用于本轮纯拆分验收；以后实现新行为时去掉它，检查真实字节和空间变化。若区段起点发生变化，比较工具会要求先明确核对布局，不把地址迁移当作普通大小变化。

| 构建输出 | 用途 |
|---|---|
| `space-report.json` | 各模块入口、源文件哈希、函数大小、各执行区段上限/占用/余量 |
| `product-functions.json` | 最终 ELF 中实际保留的 C 函数地址与大小 |
| `comparison.json` | 两个构建的镜像是否相同、区段和应用大小差值 |
| `manifest.json` | 固件版本、ID、镜像哈希、模块清单版本与模块 ID |

模块函数大小不是“关闭此模块能节省的空间”：共享辅助函数、字符串、对齐、调用端内联和调度分支会影响结果。图片统计的是 begin 到 resume 前的216B命令处理范围，不包含公共分发、回包或刷屏。实际是否装得下，以链接区段边界和完整构建增量为准，不能直接相加不同区域的余量。

## 接入后续功能

1. 在 `firmware/modules/<id>/` 放置实现，在 `modules.json` 登记源文件、必要入口、函数归属与依赖。修改已有功能时沿用原入口，避免新增重复分发层。
2. C 片段在 `product_ui.c` 中显式组合，汇编片段在 `extension.s` 中显式组合；独立 C 源文件由清单加入编译。新入口还需显式接入公共调度/协议，登记清单本身不会让设备自动调用它。
3. 实现前预算代码、常量、保留 RAM 和持久化区间；先证明它们与既有代码、字库、堆、状态、日程、OTA 和面板配置不重叠，再增加链接断言。
4. 构建、比较新旧输出，并运行涉及的实际 Thumb 路径和现有协议回归。超出任何固定区域时构建应失败，不能只看应用文件总大小。

1.5.7已完成相册接入：`image` 模块新增 `modules/image/album.c` 独立编译源，沿用原4模块登记。无损压缩66px字库腾出 `.album` 段；高区72KiB使用双配置页与双图像区，原生ID和空区门槛均在固件检查。`product_minute_tick` 在未校时时也提供相对计数，先调用原生分钟函数。新入口、BD协议、完整区段预算和验收边界见 [OFFLINE_ALBUM_1.5.7.md](OFFLINE_ALBUM_1.5.7.md)。


## 1.5.7实际模块函数统计

| 模块 | 最终C函数字节 | 说明 |
|---|---:|---|
| 时钟 | 1140 | 绘制、分钟入口和页面选择 |
| 日历 | 1404 | 月历与照片日期栏 |
| 提醒 | 4468 | 含图库复用的CRC、分页写入和回包函数 |
| 图片 | 2426 | 离线图库私有辅助函数也归入此项；另有既有216B图片命令汇编范围 |
| 共享应用逻辑 | 2714 | 字体解码、电池、刷新等公共代码 |

这是函数符号归属统计，不含全部常量、对齐和原生驱动，不能作为关闭模块可回收量相加。最终五个C区使用13050B/13248B，剩198B；完整分段、函数和源码哈希以1.5.7的space-report.json为准。四模块维持静态编译，未引入占RAM的动态插件描述表。
