# 全界面像素字库固件 1.5.14

本次按用户确认，使用真正的 Fusion Pixel / Unifont 原始点阵字形，覆盖默认页、时钟、月历、图片日历、任务汇总及到点提醒。目标为 DA14585 五测试点、250×122 黑白红屏；只准备应用 OTA 包，没有刷写设备。

## 字库与覆盖范围

共享入口为 `source/backend/bitmap_fonts.py`。12px 字体来自 Fusion Pixel，16px 字体来自 Unifont；其余字号只对原点阵做整数倍最近邻放大，并在原有字格内居中，不栅格化 Noto 矢量字体。保留字格宽度后，原有星期、农历和节气的固定列距仍对齐。

| 页面或文字 | 字库路径 | 处理 |
|---|---|---|
| 默认页 ELINK、规格、版本、MAC、电量 | 默认页图像、MAIN、SMALL | 全部从原始点阵生成 |
| 时钟大数字和冒号 | DIGITS | Unifont 数字墨迹整数六倍放大，保留原时钟坐标体系，沿用五位无损游程解码 |
| 时钟日期、星期、AM/PM、农历和节气 | DATE、MAIN | 原点阵及字格留白 |
| 月历标题、星期、年月、农历、节气和日期 | MAIN、SMALL、DAYS | 五行/六行原布局保留 |
| 图片日历大日期与右侧全部文字 | PHOTO_DAYS、MAIN、SMALL | 大日期整数四倍放大，沿用四位无损游程编码 |
| 提醒标题、时间、状态、汇总任务及到点画面 | 设备 SMALL/MAIN 与配套网页像素 | 新建或重新下发时全部使用点阵 |

网页 1.1.13 的通用模板、提醒元数据和 `fonts/calendar-glyphs.json` 复用同一字库规则；原生页面缩略图直接来自编译固件执行。管理网页菜单按钮仍是系统字体。照片中已经存在的文字和旧提醒像素保持原数据，需要重发旧提醒后才使用新字形。

## 硬件保护和容量

先重建 1.5.13，应用 SHA256 与已交付版本完全相同：`b6347e11f4a6c305d5b6540e61e71b564bbff2d623d26677205064f6be443c75`。新版 1.5.14 的固件 ID 为 `89b6f6f2`，应用 SHA256 为 `2f00afd51934190c2c10063020a8fd62e8be7e4c7d688d27d9a2101ad74e2853`。

新版应用仍为 60,028 字节，运行时覆盖区仍为 3,240 字节。默认页压缩图像保持原 1,697 字节槽位，空余部分填零，避免移动既有启动复制长度和辅助函数地址。字库全部落在原字体槽位；没有扩充 RAM、移动堆栈、改存储分区或复用未知区域。

证据目录 `backup/2026-11-13/firmware-pixel-fonts/` 中的 `protected-region-check.json` 检查了所有差异偏移，限定为五处字库槽、默认页图像、版本字符串和四字节 ID。55 个应用函数的地址、长度及机器码全部相同；保护区没有任何额外差异，底层初始化、驱动、波形、OTA 与原始校准数据不变。

随网页提供的 Windows 源码此前尚缺少已交付 1.5.13 的图库分段预检改动，本次同步该既有基线，使公开源码能重现新固件；这不是相对实机基线新增的图库逻辑。当前 Windows 可执行交付包没有重建或切换。

## 验证证据

| 证据 | 结论 | 代码或产物 |
|---|---|---|
| `pixel-python-tests.txt`、`python-test-result.json` 及重查记录 | 实际 Thumb 字形、所有原生页、月历边界、图片日期、提醒汇总和保护范围 | `source/tests/test_pixel_fonts.py` 及现有页面回归 |
| `web-tests.txt` | 95 项网页检查，包含新 OTA 包的 SHA256、CRC32、目标确认和显示像素 | Web 1.1.13 |
| `browser-check.json` | 全新 ZIP 解压后的 Edge 1280/390/360px；禁用浏览器绘字后，模板、提醒和六组图片日期仍逐像素相同 | 配套 `elink-web-1.1.13.zip` |
| `previews/proof.json` | 默认、时钟、月历、荷兰时钟、六行月历、闰月与提醒的输出帧 | 编译固件执行及共享主机渲染 |
| `protected-region-check.json` | 除明确数据区外全部字节一致，55 个应用函数完全相同 | 1.5.13 与 1.5.14 应用 |

测试中修正了两处旧检查的状态假设：UI 专用模拟机必须明确切换到时钟，不能沿用真实冷启动默认页 4；能力位预期必须包含 1.5.13 已具有的七张图库标志。前者没有改动生产冷启动行为，后者已在 1.5.13 和 1.5.14 两个镜像上核对。

## 重现和交付

在工作区根目录执行：

```powershell
runtime/venv/Scripts/python.exe -B source/firmware/build.py --version 1.5.14 --output build/firmware-1.5.14-pixel
runtime/venv/Scripts/python.exe -B backup/2026-11-13/firmware-pixel-fonts/run_tests.py
node --test source/web/tests/*.test.js
runtime/venv/Scripts/python.exe -B source/web/tools/build-text-fonts.py
```

工具链沿用 Python 3.12.7、Pillow 12.2.0 和 Zig 0.13.0，没有新增依赖。最终应用升级包、预览、许可和文件清单位于 `releases/firmware-1.5.14-test/` 与 `releases/elink-bwr-1.5.14-test.zip`。当前测试固件由 `releases/CURRENT_FIRMWARE_TEST.json` 指向。

本次重点验证所有绘字入口和保护区。完整的长时图库/存储场景未全部重跑；已完成的分段预检与轮播检查另见中断的全量运行日志，相关生产函数机器码与 1.5.13 一致。真实手机蓝牙、实屏光学、观看距离、红色显影及续航未验收。
