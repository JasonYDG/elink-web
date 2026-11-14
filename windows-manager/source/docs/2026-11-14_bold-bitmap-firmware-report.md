# 全界面粗点阵：固件1.5.16 / Web1.1.15

仅适用于DA14585五触点250×122黑白红屏。固件ID `32ed5996`。本版针对用户实拍中的断笔提高字形粗度；尚未进行新版本实屏显影验收，没有使用Computer Use或连接/刷写设备。

## 更新与使用

打开 <https://jasonydg.github.io/elink-web/?v=1.1.15>，加载在线固件1.5.16，核对所选屏幕后走现有OTA流程。离线升级包为 `releases/elink-bwr-1.5.16-test.zip`，包含应用OTA JSON、原始点阵预览和校验资料，不包含整片SPI写入镜像。

旧提醒画面和汇总标题属于已保存像素，需要在新版网页重新保存并下发。旧模板再次编辑保存后更新字体。已有图库、原图和日程不被升级主动清空。

## 实拍对应的改动

1.5.15主要增高数字，仍保留大量单像素细笔画；12px中文甚至保持旧位图。实拍显示细笔画断裂而粗笔画较完整。这是选择提高笔画粗度的依据，不能单凭照片认定驱动或波形是唯一原因。

本版字表称为 **ELINK Screen Bold**：

- 数字和英文使用 [Terminus官方粗体BDF](https://terminus-font.sourceforge.net/) 的8×14位图来源，按字格高度作最近邻适配。竖向笔画原生为双点宽，不再放大细体ASCII；仍保留12/14/15/18px字格中11/13/14/17px的数字实际高度。
- 常用汉字以Fusion Pixel12px网格为来源。18px字号采用16×17点阵加水平1点增重，16px提醒标题采用14×15点阵增重；12/14px汉字也增加横向笔画宽度。采用完整相邻位图并集，不采用此前会产生碎孔的逐点拓扑加粗。
- Unifont保留其他Unicode字符覆盖。半角假名和双宽符号保留自身字格，不被强行塞入方块汉字宽度。
- 数字和原生常用汉字逐行检查，主要竖向笔画至少2点宽；0、8、B、日、月等内部间隙另有检查。并非每一段笔画都变成2点高，M/W/%等符号仍可能含单点细节。
- 24px及以上模板大字、44px图片日期、66px原生时钟已具备较粗整数倍点阵，保持原始字节。不存在浏览器字体、矢量轮廓或抗锯齿文字。

| 原生字表 | 墨迹像素：1.5.15 → 1.5.16 | 增加 | 占用 / 原槽位 |
|---|---|---|---|
| 12px | 1932 → 2891 | 49.6% | 1491 / 1612字节 |
| 14px | 875 → 1197 | 36.8% | 583 / 604字节 |
| 15px | 378 → 476 | 25.9% | 232 / 292字节 |
| 18px | 7037 → 11335 | 61.1% | 4085 / 4340字节 |

这组数值衡量位图粗度，不代表实屏对比度提高相同比例。

## 验证链

- `red-green-weight.json`：旧版单点笔画在新回归中失败，新字表通过双点宽要求。
- `font-weight-metrics.json` 与 `test_font_readability.py`：199个原生小字与编译字表逐字节一致，四个槽位不超限，日期/MAC/100%电量/72列提醒省略号完整；检查数字和汉字的粗度及关键字腔。
- `native-previews/proof.json`：执行实际交付应用的绘图与接收代码，读取8000字节模拟帧缓冲，直接导出9张250×122三色PNG；不绘字、不平滑、不调色、不生成放大总览。逐点校对274500个可见像素。
- `native-test-result.json`：覆盖实际Thumb字体解码、所有原生页面、四行提醒、图片日历、启动及保护字节；半角字形另做单项复查。完整检查结果以包内 `VALIDATION.json` 为准。
- `web-tests.txt` 和全新解压后的Node回归：95项网页检查，包括模板完整帧、提醒元数据、图片日历日期、缺字/损坏字库拒绝、OTA校验及提交边界。不做浏览器/电脑UI操作。
- `protected-region-check.json`：相对1.5.15只更改四个小字槽位、版本字符串和ID，55个应用函数的地址/大小/机器码相同，44/66px大数字与启动背景相同。驱动、波形、蓝牙、Flash/OTA逻辑、身份/校准数据、堆栈/装载边界不动。
- 最终源码在独立目录重建，应用、SPI对照产物、OTA JSON及函数表相同。应用60028字节、装载3240字节。SPI仅作只读差分，不在升级包中交付。

证据位于 `backup/2026-11-14/bold-bitmap-firmware/`。Terminus原始归档SHA256为 `d961c1b781627bf417f9b340693d64fc219e0113ad3a3af1a3424c7aa373ef79`，与官方发布页一致；未修改原始BDF，压缩文件及OFL许可证随源码提供。Fusion/Unifont原始字体和许可保持不变。

## 复现

在项目根目录使用现有隔离环境：

```powershell
runtime/venv/Scripts/python.exe -B source/firmware/build.py --version 1.5.16 --output build/firmware-1.5.16-check
$env:ELINK_TEST_FIRMWARE_DIR = "$PWD/build/firmware-1.5.16-check"
$env:PYTHONPATH = "$PWD/source/tests;$PWD/source/backend;$PWD/source/firmware"
runtime/venv/Scripts/python.exe -B -m unittest -v test_font_readability test_native_preview test_pixel_fonts
$env:ELINK_PREVIEW_UPDATE_PACKAGE = "$PWD/build/firmware-1.5.16-check/elink-bwr-1.5.16.elink-update.json"
$env:ELINK_PREVIEW_OUT = "$PWD/build/firmware-1.5.16-native-check"
runtime/venv/Scripts/python.exe -B source/tools/preview_screen_design.py
node --test source/web/tests/*.test.js
```

测试的只读基线位于 `build/firmware-1.5.15-release` 和 `build/firmware-1.5.14-repro`。PNG表达固件像素，不模拟实体墨水颗粒、反射对比度或残影；软件通过不能证明真机断笔已经消除。本次没有重跑全部长期存储/轮播边界，也没有实际蓝牙或续航验收。
