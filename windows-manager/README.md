# ELINK Windows Manager 1.5.13

[下载完整 Windows 程序与固件](https://github.com/JasonYDG/elink-web/releases/tag/manager-v1.5.13-r2) · [网页1.1.0](https://jasonydg.github.io/elink-web/)

配套固件1.5.11 / ff001ff1。解压 elink-manager-1.5.13-r2-windows.zip，退出旧程序后运行 Start.cmd，无需安装Python。原数据继续保存在 %LOCALAPPDATA%/ElinkManager/data。

包含完整服务端：扫描/登记、单台/批量控制、状态与像素读回、时钟/时区/刷新策略、月历/图片日历、16张内置图、上传裁切、共用离线图库、原图与配置恢复、离线重复提醒/今日汇总、置顶任务弹窗、队列/历史/备份，以及完整应用OTA读回和重启核对。

旧1.5.2保留原有读取/控制。7张与未知原图恢复需1.5.11；旧版四张图库可保留升级。图片与图片日历共用顺序、取景和间隔，修改一张可保留其余设置。每天一张可七天一轮。代码使用受限应用区域，低层驱动、启动、OTP/MAC及堆栈边界保持。详见[本版说明](docs/MANAGER_1.5.13.md)及[完整空间表](docs/DEVICE_MEMORY_MAP.md)。旧固件不识别新图库配置，回退前保留照片与管理数据备份。

源码在source/，资源、字体、时区、图库、构建工具和测试均包含。运行Windows服务端：

```powershell
py -3.12 -m venv runtime/venv
runtime/venv/Scripts/python.exe -m pip install -r source/backend/requirements.txt
runtime/venv/Scripts/python.exe source/backend/server.py --open
```

PyInstaller打包入口 source/tools/build_desktop.py；开发依赖锁见 source/tools/development-lock.txt。固件重建及完整模拟还需哈希固定的原始HMCLOCK夹具、Zig0.13.0及模拟工具，详见docs/PROVENANCE.md；这些原始二进制不作为服务端运行依赖。历史烧录/本机交付工具有各自外部前提。

已验证候选包全新解压、清洁PATH启动、字体与时区、16图、原生读回图片、OTA包解析、SQLite备份及单实例。源码相关HTTP/连接/图库等20项Python、6组JS、网页38项协议/数据测试，以及编译后七图/兼容/边界/保护区验证通过。浏览器在1280与390宽度检查通过，日期字形与主机逐像素匹配。

这是候选测试发布，本轮没有擦写实体屏；真实蓝牙、光学、掉电时序、续航与长稳仍待验收。公开包不含本机数据库、全片备份、有线helper、原始固件夹具或私钥。保留source/fonts与legal中的第三方许可，不宣称整个固件为MIT。

## Launcher revision 2

Start.cmd contains ASCII only, without BOM. It keeps errors visible and writes startup.log under %LOCALAPPDATA%/ElinkManager/logs. Close the old manager before starting this package; closing a browser tab is insufficient. If the old console is hidden, find the old ElinkManager.exe in Task Manager / Details. The executable, resources and firmware are unchanged. The small launcher ZIP can also be extracted over an existing1.5.13 package.
