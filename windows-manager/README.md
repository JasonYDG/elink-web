# ELINK Windows Manager 1.5.11

Windows 本地蓝牙服务端，配套 2.13 寸 DA14585 黑白红固件 1.5.10（`fde89808`）。

[下载 Windows 服务端与配套固件](https://github.com/JasonYDG/elink-web/releases/tag/manager-v1.5.11)。解压 `elink-manager-1.5.11-windows.zip`，退出旧程序，运行 `Start.cmd`，浏览器访问 `http://127.0.0.1:18765/`。无需安装 Python。数据仍保存在 `%LOCALAPPDATA%/ElinkManager/data`，升级时保留该目录。

此目录保存 Windows 版的后台、管理页面、固件扩展源码和字体许可。仓库根目录是独立 Web Bluetooth 网页，两者分别运行；GitHub Pages 只托管静态网页版。

本版包含：16 张内置图；最多四张图片的设备离线轮播；图片日历与整图共用选图、顺序、取景和轮播间隔；图片日历为 174 列图片、76 列日期，无分割线；年月、节气倒计时及开机 MAC 小字加粗；置顶操作弹窗；状态与设备像素读回；Windows OTA 提交断连后的版本核对。轮播可设 1 小时至 7 天，电脑关闭后由屏幕执行。

管理端按设备能力开放功能。1.5.2 可继续使用原有状态和控制；离线图库、图片日历等新功能需要相应固件。此次上传不改动蓝牙协议，也没有修复尚未确定原因的偶发发现问题。

## 源码运行

在本目录用 Windows Python 3.12 创建隔离环境：

```powershell
py -3.12 -m venv runtime/venv
runtime/venv/Scripts/python.exe -m pip install -r source/backend/requirements.txt
runtime/venv/Scripts/python.exe source/backend/server.py --open
```

后端依赖 Bleak 3.0.2、Pillow 12.2.0。打包依赖版本见 `source/tools/development-lock.txt`；安装 PyInstaller 6.22.3 后运行 `runtime/venv/Scripts/python.exe source/tools/build_desktop.py`，输出在 `build/desktop/ElinkManager`。

`source/firmware` 为现有固件扩展源码。固件重建还需要来源说明中的哈希锁定 HMCLOCK 基线与 Zig 0.13.0；本公共源码目录不附设备 Flash 备份或完整 SDK，不能仅凭此目录重建原生基线。可直接使用 Release 中已校验的应用升级包。

## 固件与验证

Release 同时提供原样的 `elink-bwr-1.5.10-test.zip`，固件 ID 为 `fde89808`。仅使用包内 `.elink-update.json` 经现有 OTA 通道升级；不要整片擦除或覆盖启动、射频、MAC、校准、面板波形及未知区域。服务端下载包不包含原厂全片备份、有线烧录 helper 或本机数据。

此前本版本已通过 106 项 Python 回归、6 组 JavaScript 检查和最终 ZIP 全新解压启动检查；发布时另行核对文件哈希、资源依赖及公开包启动。保护区域对照有 57156 字节保持相同。上述软件验证不能代替实物字体、续航、长期连接和掉电恢复验收。偶发旧屏连接等待的原因尚未确定，不能把本次恢复视为已修复。

详见 [本版说明](docs/MANAGER_1.5.11.md)、[上版图库与回执说明](docs/MANAGER_1.5.10.md)、[模块说明](docs/FIRMWARE_MODULES.md)。新固件先在一台已备份的测试屏验收。

字体、Python 依赖与 Renesas 原生代码适用各自许可，保留 `source/fonts`、下载包 `legal` 中的原文；不宣称整个固件为 MIT。`SOURCE_MANIFEST.json` 列出本次公开源码的文件哈希。
