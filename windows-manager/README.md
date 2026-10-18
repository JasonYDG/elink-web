# ELINK Windows Manager 1.5.12

完整 Windows 蓝牙服务端、配套管理网页及源码。适用 2.13 寸 DA14585 BWR 250×122 标签，配套固件 **1.5.10 / fde89808**。

[下载完整 Windows 服务端](https://github.com/JasonYDG/elink-web/releases/tag/manager-v1.5.12)。解压 `elink-manager-1.5.12-windows.zip`，退出旧程序，运行 `Start.cmd`。打开 `http://127.0.0.1:18765/`；无需安装 Python。Windows 包包含程序、全部运行资源及配套应用 OTA 包，原数据继续保存在 `%LOCALAPPDATA%/ElinkManager/data`。

## 功能

| 功能 | 已包含的行为 |
|---|---|
| 设备管理 | 扫描、完整 MAC 登记、单台/批量操作、设备状态、电压估算、实际像素读回 |
| 时钟 | 新版时钟、12/24 小时、刷新间隔与完整刷新策略、本地/荷兰时区、校时 |
| 日历 | 设备月历、左图右日期主题、农历、节气/倒计时、图片左右取景 |
| 图片 | 上传、裁切/移动/缩放/旋转、三色预览、电脑保存、16 张原生内置图直接应用 |
| 离线图库 | 最多四张存入屏幕，1 小时至 7 天轮播；整图与图片日历共用顺序、取景和间隔 |
| 提醒 | 离线日程、每日/星期重复、持续时间、今日汇总、修改/完成/删除及安装读回 |
| 任务控制 | 串行队列、置顶操作弹窗、完成回执、等待取消、批量结果、历史记录 |
| 定时与数据 | 电脑端图片计划、SQLite 持久记录、备份；电脑计划需要后台运行，屏幕离线图库和已写入提醒独立执行 |
| Windows OTA | 包/型号/哈希校验、非活动区上传、全量读回、提交后重启版本核对 |

功能按固件能力开放。1.5.2 保留已有状态/控制兼容，新图库和图片日历需要对应固件。1.5.12 只更新服务端：FF01 缺项时最多三次释放/重发现；无广播时核对 Windows 已连接对象的完整 MAC；手动连接失败三次后停止。固件保持 1.5.10，此项修复无需重刷。

此目录及下载包是 Windows 服务端。GitHub Pages 从 `gh-pages` 发布根目录的独立 Web Bluetooth 网页；GitHub 不代替本机蓝牙适配器或运行这个 Python 服务。根目录静态版的功能与数据存储有自己的范围说明。

## 源码运行与打包

在本目录创建 Windows Python 3.12 环境：

```powershell
py -3.12 -m venv runtime/venv
runtime/venv/Scripts/python.exe -m pip install -r source/backend/requirements.txt
runtime/venv/Scripts/python.exe source/backend/server.py --open
```

后台、管理网页、字体、时区与内置图库均在 `source/`；没有省略服务端 API 或替换成模拟蓝牙。`source/tools/development-lock.txt` 固定原构建环境依赖。安装 PyInstaller 6.22.3 后执行：

```powershell
runtime/venv/Scripts/python.exe source/tools/build_desktop.py
```

输出为 `build/desktop/ElinkManager`。上述运行和桌面打包不需要设备 Flash 备份。

基础后台与界面检查：

```powershell
runtime/venv/Scripts/python.exe -m unittest discover -s source/tests -p test_http.py -v
runtime/venv/Scripts/python.exe -m unittest discover -s source/tests -p test_operation_lock.py -v
Get-ChildItem source/tests/test_ui_*.js | ForEach-Object { node $_.FullName }
```

完整固件/集成测试还需 Unicorn、Keystone、Capstone 及其原始二进制夹具；`source/firmware` 重建还需哈希锁定的 HMCLOCK 基线与 Zig 0.13.0，详见 [来源](docs/PROVENANCE.md)。这些外部原件不作为服务端启动依赖。历史烧录/本机打包工具也会引用本地备份、SDK 或工具安装路径，应先阅读其前提。

## 配套固件与验证

Windows 包 `firmware/elink-bwr-1.5.10.elink-update.json` 与独立固件 ZIP 内容一致。仅通过适配的应用 OTA 通道使用；保留启动、射频、面板、MAC、校准和未知区域。公开包不含本机数据库、设备全片备份、有线编程 helper 或私钥。

本地 1.5.12 已通过 34 项相关 Python、6 组 JS、最终包清洁 PATH 启动；实际冻结程序在 1.5.2 旧屏读取状态和完整 8000B 画面。公开包另行全新解压检查，原生图库/字体/OTA 资源按清单核对。一次读回不能证明长期稳定；Windows/适配器为何偶发返回不完整服务仍未确定。

[1.5.12 连接说明](docs/MANAGER_1.5.12.md) · [图库与回执](docs/MANAGER_1.5.10.md) · [模块说明](docs/FIRMWARE_MODULES.md) · [4.2 寸代码对照](docs/2026-10-19_ble-42-comparison-report.md)

`SOURCE_MANIFEST.json` 记录源码哈希，Release 的 `SHA256SUMS.txt` 记录 ZIP 哈希。字体和第三方组件遵循 `source/fonts`、`legal` 下各自许可证，不宣称整个固件为 MIT。
