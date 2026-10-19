# ELINK Web 1.1.1

[打开网页](https://jasonydg.github.io/elink-web/) · [Windows 管理端 1.5.14 与固件 1.5.12](https://github.com/JasonYDG/elink-web/releases/tag/manager-v1.5.14-r2) · [完整服务端源码](windows-manager/README.md)

2.13 寸 DA14585 红白黑墨水屏，250 × 122 原生像素。网页使用访问者本机 Web Bluetooth，数据保存在当前浏览器 IndexedDB；GitHub 不运行家庭后台或提供蓝牙适配器。

本版修复开机默认页误报时钟和读图时换页造成的画面不一致，读图失败不显示替代示意图；操作进度弹窗已精简。

## 功能

- 最新固件及显示能力识别，电压、当前页面、图库配置、8000 字节 RAM 像素读回；读回不是光学拍照。
- 新版时钟、刷新策略、时区、设备月历、左图右日期的图片日历、农历、当天节气或下一节气倒计时。
- 16 张中文命名的原生三色图，上传、裁切、旋转、缩放；图片日历可左右取景。
- 图片与图片日历共用离线轮播的选图、顺序、位置、间隔。1.5.11 最多 7 张，每天一张可七天一轮；旧固件仍按 4 张上限。关闭网页后设备继续换图。
- 读取设备时恢复播放列表。新固件可只读取回未知原图，逐张校验 CRC32；修改其中一张，其余设置保留，点击应用才保存。旧固件没有原图接口时会提示升级。
- 离线提醒、星期重复、持续时间、今日任务汇总、安装读回、完成与取消。
- 串行任务、置顶进度、等待取消、历史与未知结果保护；提交中断不自动重复提交。
- 网页 OTA：专用应用包校验、非活动区上传、逐字节读回、单次提交及重启版本核对。

安卓使用 Chrome；Windows 使用支持 Web Bluetooth 的 Chrome/Edge，通过 HTTPS 打开本页。选择 ELINK 开头的屏幕，并关闭其他连接端。浏览器不会提供真实硬件 MAC，web-... 是本站设备标识，可通过设备名称及手动 MAC 核对。1.5.2 的原有读取/控制保留，新增功能按能力开放。

支持长写入的连接使用 128 字节像素载荷（63 包），容量不足或旧固件回退 17 字节（471 包）。屏幕清屏和三色刷新仍需等待。OTA 先用无存储写入的请求检查 136 字节连接容量，未通过则在擦写前拒绝；只能选择 .elink-update.json，不能使用全片 SPI 镜像。

## 数据

现有数据库名、schema、记录 ID 和历史保留，无需清空网站数据。清除数据前导出 JSON；导入前自动备份原工作区，并停止旧队列和电脑更新计划。授权不跨域，迁移后核对设备名称重新关联。电脑计划依赖页面运行，已保存的离线图库和提醒由设备执行。

旧 Windows SQLite 备份可在电脑只读转换后导入：

```powershell
python tools/convert-backup.py old-backup.sqlite3 elink-backup.json
```

## 源码、许可与检查

main 保存网页及 windows-manager/ 源码；gh-pages 只发布静态运行资源，支持 /elink-web/ 子路径。Windows 程序入口与数据路径见服务端说明。不发布本机数据库、设备 Flash 备份、凭据或私钥。

```powershell
node --test tests/*.test.js
```

图像原生帧及哈希保持不变，来源见 ARTWORK.json。通用模板使用 Noto Sans SC Black，许可见 fonts/LICENSE.txt。图片日历使用与固件同源的原生尺寸 Noto Black/Medium 和 Fusion Pixel 字形表，见 fonts/calendar-glyphs.json、fonts/FusionPixel-OFL.txt；未复制 4.2 寸固件的专有字体。

通用 Canvas 模板可能有系统栅格化差异，预制图库和日历字形不依赖系统字体。协议模拟、浏览器界面及编译检查不能代替真实手机蓝牙、实体显示、续航和掉电验收；本次为候选测试发布。
