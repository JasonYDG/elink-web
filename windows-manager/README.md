# ELINK Windows Manager 1.5.14

[下载完整 Windows 程序与固件](https://github.com/JasonYDG/elink-web/releases/tag/manager-v1.5.14-r2) · [网页1.1.1](https://jasonydg.github.io/elink-web/)

配套固件1.5.12 / 50d9e83d。解压 elink-manager-1.5.14-r2-windows.zip，先运行 Stop.cmd，再运行 Start.cmd，无需安装Python。原数据继续保存在 %LOCALAPPDATA%/ElinkManager/data。

包含完整服务端：扫描/登记、单台/批量控制、状态与像素读回、时钟/时区/刷新策略、月历/图片日历、16张内置图、上传裁切、共用离线图库、原图与配置恢复、离线重复提醒/今日汇总、置顶任务弹窗、队列/历史/备份，以及完整应用OTA读回和重启核对。

旧1.5.2保留原有读取/控制。7张与未知原图恢复需1.5.11；旧版四张图库可保留升级。图片与图片日历共用顺序、取景和间隔，修改一张可保留其余设置。每天一张可七天一轮。代码使用受限应用区域，低层驱动、启动、OTP/MAC及堆栈边界保持。详见[本版说明](docs/MANAGER_1.5.14.md)及[完整空间表](docs/DEVICE_MEMORY_MAP.md)。旧固件不识别新图库配置，回退前保留照片与管理数据备份。

源码在source/，资源、字体、时区、图库、构建工具和测试均包含。运行Windows服务端：

```powershell
py -3.12 -m venv runtime/venv
runtime/venv/Scripts/python.exe -m pip install -r source/backend/requirements.txt
runtime/venv/Scripts/python.exe source/backend/server.py --open
```

PyInstaller打包入口 source/tools/build_desktop.py；开发依赖锁见 source/tools/development-lock.txt。固件重建及完整模拟还需哈希固定的原始HMCLOCK夹具、Zig0.13.0及模拟工具，详见docs/PROVENANCE.md；这些原始二进制不作为服务端运行依赖。历史烧录/本机交付工具有各自外部前提。

本版修复开机默认页被识别为时钟、读图失败显示示意图，以及读图时自动换页造成的状态不一致。读取中断有限重试，弹窗只保留操作标题和当前步骤。设备保留旧图库并自动恢复轮播；读取不会清除或停用图库。

只读实机核对1.5.11成功，实际画面像素与湖畔鸟居一致；新固件1.5.12尚未写入实体屏幕，光学、掉电和长期稳定性待测试。公开包不含数据库、全片备份、有线helper、原始固件夹具或私钥，第三方许可保留在source/fonts与legal。

UI revision 2：操作弹窗保留设备地址、当前步骤、百分比和进度条。当前操作结束后刷新；固件仍为1.5.12，无需为此升级屏幕。
