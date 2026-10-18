# 构建与来源

- HMCLOCK 项目：https://github.com/tpunix/HMCLOCK ，源码快照 `bc9c1ea04c8ec5ffc6c73cf4e1aaf382817ebdc3`；社区基线 https://github.com/afo183/HMCLOCK/releases/tag/firmware 。上游介绍的2.13黑白红为 HINK-E0213A67 / 250×122。
- 原始应用 SHA256 `4f8178cfb73fe16209121070a499471f136d2c1e1f1636a3c59adbd3583cfb5f`；完整 SPI 基线 `aa3d5913551d29e23e1b7cca23dd767dcbd214d78f4a26c2b4fc952e89bd0b64`。构建器拒绝不同基线、代码区越界或错误向量/散装加载表。
- 新固件是 Cortex-M0 Thumb 扩展及少量原生函数钩子。1.0.0 对 A0..510 区域的可用性判断错误，已撤回。原生 scatter 表会清零110..510，随后供 TRNG 使用；C0..110 是补丁表。1.0.1在启动前复制扩展到07FD1480起的保留RAM空隙，避开07FD0C18起的2048+12字节原生堆，以及07FD21C0起的保留数据。原生初始化、堆配置、栈和面板缓冲地址均保持；临时复制入口在 TRNG 初始化前执行，此后被正常清零。应用扩展为60068字节，仍满足原生16位OTA长度。完整 C 重编译需要上游 Renesas SDK 6.0.22.1401 与 Keil；本机未安装该完整SDK/Keil工具链，1.1.0的有限C模块使用下述Zig。
- 测试执行实际构建指令并模拟 ROM消息、SPIFlash、BUSY 与BLE传输边界。OTA 页流、校验读回、有效标记提交和旧区保护有实际二进制执行测试；未模拟射频、模拟供电或墨水粒子驱动。
- 1.0.2 延续 1.0.1 布局，应用为 60084 字节。按 SDK `arch_sleep.c` 与原生二维码刷新尾部修正 BLE 事件中 `sleep_pend` 为 0x80；开机页入口增加 BUSY/代次检查，避免重复绘制。两个测试在旧代码上复现失败，修复后通过。1.0.1 已取得真实广播、FF00 状态与传图回执，但用户报告模板花屏；1.0.2 经真实OTA后同一模板仍花屏，不能作为光学修复成功的证据。
- 开发环境隔离 `runtime/venv`，Python3.12.7，Keystone0.9.2，Capstone5.0.7，Unicorn2.1.4；管理端 Bleak3.0.2 / Pillow12.2.0 / PyWinRT3.2.1，PyInstaller6.22.3。完整实际依赖清单在 `source/tools/development-lock.txt`。
- Bleak Windows后端采用WinRT，参见 https://bleak.readthedocs.io/en/latest/backends/windows.html 。不依赖浏览器WebBluetooth或远程CDN。便携版含Python DLL；微软雅黑字体从系统读取，是明确系统依赖。
- 设计沿用用户 E-paper 的 meeting-room-operations 系统；日历/任务/持久化方案参考用户 E-Ink 项目，没有更改那些项目的源代码或服务。
- 上游 SDK 包含 Renesas/Dialog 版权和使用范围说明，不能宣称全部固件为MIT。交付保留 SDK_NOTICE 和随依赖安装的第三方许可；当前交付供本次自有Renesas标签本地使用，未发布公共仓库。

- 1.0.3 从实际标签核对原生122×250、stride16、RST P1_0、BUSY P1_1、DC P0_7；8000字节RAM读回逐字节匹配模板。共用初始化补入上电后的RST低脉冲与稳定等待，复位单独测试版a7c35efb得到用户文字清晰确认。最终组合标识de05d8d1已实际OTA、读回并完成模板BUSY；持续模式完成20次重新扫描/连接/读状态/断开。Windows释放GATT后实际断链有延迟，6秒严格测试曾超时，30秒容限内实际重发现0.531–12.468秒。原始记录保留，24小时和电流等仍待验收。

- 1.0.4 的本机完整MAC已在第一块实际OTA及8000字节开机RAM读回中确认。但LED极性错误：低电平导致常亮；其关灯结论撤回。Claude Code的1.0.5（24f56403）改为三路输出高电平，并在原生periph_init的0x6276、PAD锁存前增加每次唤醒钩子。原始1.0.5构建留存，28项测试通过。
- 1.0.6（e7d6ebb6）仅在1.0.5基础上将MAC移到ELINK右侧同一行并删除MAC标签。LED、唤醒和主运行代码逐字节一致；最宽AA地址含加粗占用至x247，250像素内完整显示。28项测试通过；实际OTA、像素读回和LED观察另行记录，尚未测量电流。

## 1.1.0 自主页面与分钟窗口

新增 freestanding Cortex-M0 product_ui.c：独立时钟/月历、12小时制、AM/PM、加粗小字、原生ADC电量估算；MAC移到启动页底栏。仅复用清晰的大数字字库。分钟局刷以保护掩码、中性LUT2/3及gate扫描范围实现；使用基线原生SPI数组发送函数保证CS/DC时序。模板与小时/日期/其他像素变化全刷。布局为ELINK自行排版。官方 Zig 0.13.0 ZIP 校验 SHA256 d859994725ef9402381e557c60bb57497215682e355204d754ee3df75ee3c158；未全局安装。IL3897依据厂家原文 https://cursedhardware.github.io/epd-driver-ic/IL3897.pdf 。历史失败和实机未验收项继续保留在验证报告。

节气倒计时复用基线0x7FC7D6C的24项秒数及0x7FC7DCC的名称表，零基公历日计算保持上游规则，包括跨年到下一次小寒。完整基线SHA256锁定这些地址。新增缺少的“今”字，页面字形集合在构建阶段检查。

## 1.1.1

按用户实机反馈恢复原生整页快速波形，分钟局刷保留为实验。启动底栏大写V，横线上下各5像素空白；月历左日期网格、今日红底白字、右年份与节气。农历两个字用16像素粗体及更完整的纯色阈值，底栏上移，完整字形有原生绘图执行对照。

新增9E静默校时复用原生RTC更新，公告发送不先绘制时钟；状态及能力查询遇到周期11字节旧值时重新发送查询，最多3次，最终异常仍报错。软件OTA兼容测试使用交付的真实1.0.5应用作为旧区，位于source/reference/bootstrap-1.0.5，不把新源码换版本号冒充旧实现。

1.1.0分钟局刷取得BUSY完成及RAM读回，但用户认为观感怪异；此项未通过光学验收。1.1.1实机和最终包的测试结果见VALIDATION_REPORT。

## V1.2.0

整页轻快刷选择上游分钟 UPDATE_FLY，替代上一版 UPDATE_FAST；保护原生 R=1 组合并保留周期完整刷新。日历顶部状态、共用蓝牙标识、默认页9C2和页面能力位5由有限C模块/Thumb扩展实现。应用60040字节；固件ID38d70f9e。原生ADC电量估算和广播名尾部编号仍沿用基线，显示MAC从各设备自己的OTP读取。

管理端复用已有SQLite/串行BLE工作队列，新增多设备选择、统一四种页面与逐台回执；没有新增云服务。旧固件不返回ELUI时重新查询并验证真实ELK1，保留OTA通道，不给其开启新版页面。原生11字节时钟回复不会被当作32字节成功状态。

本机交付保留实际四设备升级、完整像素RAM和明确标注的UI测试证据；此前失败日志未删除。最终光学、LED、电流和24小时结果仍待验收。

## V1.2.1

有限C模块在共用更新路径加入异步清屏、目标重刷及完成回执保护；蓝牙符号和月历使用现有像素/字形渲染。原生地址格式化处0x57a8由eors改为mov，名称取真实MAC后六位大写。原生GAPM共享间隔0x27f0从1100改为3200槽，保留睡眠与频道。应用60024字节，固件ID90559ec8；未替换上游SDK或扩大BLE保留区域。

## 2026-10-06 页面设计稿字体

仅用于 `opendesign/mockups/elink-screen-design` 的屏幕设计稿；尚未替换生产渲染器、编译进固件或升级标签。字形直接读取上游点阵，12／16 像素原生大小或整数倍最近邻放大。PNG 与导出的 8000 字节帧逐像素一致。

- Fusion Pixel 12px Mono zh_Hans，版本 2026.09.25，来源 https://github.com/TakWolf/fusion-pixel-font/releases/tag/2026.09.25 。上游 BDF ZIP SHA256 `d75f5262f108757edb0f47ee8e3d2dfdfbecfd94558faf5ffb0c06dc5866fb3b`；选取的原始 BDF SHA256 `bb2cdfa029674d83ad9fc6b01bba11752f61779cae1219a722c7ccee96b2d0ae`。本地无损 gzip 的 SHA256 `1cc43ef154f2b223d085889d0d2f6ace35b56e11488db7897768d06de6f10ae4`。OFL-1.1 原文及上游所附来源许可证保留在 `fonts/FusionPixel/`。
- GNU Unifont 17.0.04，原生 16px HEX 点阵，来源 https://unifoundry.com/pub/unifont/unifont-17.0.04/font-builds/unifont-17.0.04.hex.gz 。本地原文件 SHA256 `e808096f98ff04294f0d49452cad51964e2930b7be046ac8e1efadc46b2bab0f`。上游提供 OFL-1.1 / GPL 字体例外双授权，本设计采用 OFL 条款；原始说明 https://unifoundry.com/LICENSE.txt 保存为 `fonts/Unifont-LICENSE.txt`。
- 大时钟数字沿用上述哈希锁定的 HMCLOCK 社区基线 66px 点阵。没有使用微软雅黑字形作为随包资源；网页周边文字仍使用本机系统字体。

## V1.3.0 字体与时区

以上点阵源现已用于后台渲染和 V1.3.0 的设备字库子集。完整字形表只保留页面所需字符，设备使用原厂字形格式与绘图函数。12px 字库止于0x9500之前，有限C模块从0x9500开始、止于状态0xA46C之前；16px字库止于原生66px大数字0xC3C4之前。构建有独立边界断言。完整上游字体、许可证及本地哈希随源码和管理端分发；固件小包附字体许可证。预览由编译二进制实际执行得到，模拟的SPI/GPIO不证明光学效果。

荷兰时区使用 tzdata 2026.5 的 Europe/Amsterdam TZif，通过标准库 ZoneInfo.from_file 读取，未新增运行时依赖。PyPI上游wheel SHA256为 `b683bd1b6659ddcd810ff02ad09ba821d4bf1065072805063eb35c49617905ac`；TZif SHA256为 `b10f9542a8509f0a63ebca78e3d80432dd86b8ea296400280febd9cfa76e8288`。来源、完整URL和双层许可证记录在timezones/provenance.json。管理端处理IANA时区，设备保存当前夏令时位并按荷兰现行规则离线转时；日期规则依据荷兰政府 https://www.government.nl/faq/european-union/why-do-the-clocks-change-twice-a-year 。未来法规变化需要更新固件。

## V1.3.1 可读性

继续使用上述同版本同哈希的字体子集。BWR ASCII行加一像素水平笔画，中文不作错位假粗体；时钟底栏、月历星期/侧栏、公告底栏使用原生16px字形。密集日期与MAC用12px，四页共用同一字号层级。屏幕分辨率、LUT、广播间隔及保留RAM边界不变。

## V1.3.2 · 用户指定鸿蒙粗体

采用华为官方包 https://developer.huawei.com/images/download/next/HarmonyOS-Sans.zip ，官方资源页 https://developer.huawei.com/consumer/cn/design/resource/ 。原始文件完整保存：HarmonyOS_SansSC_Bold.ttf，SHA256 `c215d8ab1cb6709fec2e063f8213e9af86d7587d345b56325e36b67d6b947d98`；HarmonyOS_Sans_Condensed_Bold.ttf，SHA256 `fa964ca60754b42dae91beaf27909578053cfa31901690e05d93615e3aeb0bfb`。包哈希和原路径记录在fonts/preview-fonts.json。

Copyright 2021 Huawei Device Co., Ltd.，使用HarmonyOS Sans Fonts License Agreement，原文 https://raw.githubusercontent.com/openharmony/global_system_resources/master/LICENSE_Fonts ，本地fonts/HarmonyOS/LICENSE.txt。协议允许随软件使用/嵌入未修改的字体，并要求使用说明、保留许可证及禁止字体文件修改。本版保存原TTF，不改字体轮廓、不子集化；设备页面资源为原字体经Pillow单色绘制得到的文字像素，并非重新设计的字形。管理端及预览页明确说明字体使用。按协议中使用字体创作作品的条款处理生成画面，未把这些像素作为独立字体产品分发。

用户指定鸿蒙粗体优先于此前WORKITEMS_FONT.md的小字号点阵建议。尺寸仍12/16px，24/36等大字使用整数倍；原厂66px时钟数字不变。生成资源仍使用原生五字节头、字节对齐行格式，完全保留硬件绘图路径。无抗锯齿、无额外错位描粗。缺失汉字才显式记录并回退到此前OFL点阵；固件所需全部字符使用鸿蒙字形。
