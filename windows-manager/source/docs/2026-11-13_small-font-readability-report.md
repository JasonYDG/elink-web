# 250×122 小字适配：固件 1.5.15 / Web 1.1.14

适用于 DA14585 五触点黑白红屏。新版仍待实屏光学验收；本次没有连接或写入设备。已保存的提醒画面、汇总标题属于像素数据，升级后需通过新版网页重新保存并下发。

## 更新方式

打开 <https://jasonydg.github.io/elink-web/?v=1.1.14>，加载在线固件 1.5.15，核对所选屏幕后按现有 OTA 流程安装。固件 ID 为 `18982457`。本地包是 `releases/elink-bwr-1.5.15-test.zip`，只包含可校验的应用升级 JSON 和验证资料，不包含整片 SPI 写入镜像。

## 原因与改动

上一版把原生 12px/16px 点阵居中放入较大的字格，但未充分利用字格高度。部分标为 14、15px 的数字，实际笔画仍只有 8px。此前像素一致性检查证明了预览与发送相同，却没有证明实际笔画尺寸合适，这是漏检。

| 字格高度 | 旧数字实际高度 | 新数字实际高度 | 字库占用 / 原槽位上限 |
|---|---|---|---|
| 12px | 8px | 11px | 1490 / 1612 字节 |
| 14px | 8px | 13px | 583 / 604 字节 |
| 15px | 8px | 14px | 232 / 292 字节 |
| 18px | 10px | 17px | 4168 / 4340 字节 |

共享绘图源码调整 12–20px 小字：按实际笔画高度放大 Fusion Pixel ASCII 点阵；18px 中文将16行原始点阵放大为17行。全部使用最近邻，不缩小、不抗锯齿，不引入浏览器字体。16px 提醒标题保留字宽，使四个汉字及省略号仍能放入72列。

比较过额外加粗。双向加粗产生细碎空洞，横向叠画会改变部分字腔；这两个方案已舍弃。交付版通过放大改善小字，保留点阵来源和内部空隙。12px 中文继续使用原生12行点阵。44px 图片日历日期、66px 原生时钟和启动插画字节不变。

改动覆盖默认页版本/MAC/规格/电量、时钟日期与农历节气、月历日期与侧栏、图片日历小字、提醒汇总以及新生成的到点提醒、公告/会议/日程/时钟模板。导入照片和旧提醒中已有的文字不会自动重绘。

## 验证依据

证据 → 发现 → 修改路径：

- `font-geometry-final.json` 对照编译字库与共享绘图：数字实际高度不足 → `source/backend/bitmap_fonts.py` 统一处理小字高度与字宽。
- `native-18982457/proof.json`：真实 Thumb 字库解码后的250×122双平面与 PNG 一致 → 校对默认页、时钟、月历、六行月历、闰月、提醒和公告。
- `test_font_readability.py`：199个原生小字字形的字腔数量不变，无新增单像素封闭字腔，原始墨迹不减少，槽位不超限；日期栏、最宽MAC、100%电量、提醒省略号均在实际列宽内。
- `protected-region-check.json`：差异仅落在四个已有小字槽位、版本和ID → 55个应用函数的地址、大小与机器码逐字节相同；启动、驱动、波形、蓝牙、Flash、OTA及内存边界保持基线。
- 两次独立输出目录构建：应用、SPI对照产物、OTA JSON与函数表一致。应用60028字节，装载区3240字节。
- `native-python-tests.txt`、`boot-geometry-recheck.txt`、`web-tests.txt` 与交付包 `VALIDATION.json`：原生执行、页面边界、图片日历、提醒、启动及95项网页回归。启动页空白行断言随实际字高调整，并增加完整规格/MAC逐像素断言。
- `browser-check.json` / `browser-live.json`：Edge 在1280、390、360宽度下禁止浏览器文字绘制，逐像素核对7种模板、6种提醒元数据和6个图片日历日期，无横向溢出。

上述证据位于 `backup/2026-11-13/small-font-readability/`。最终包全新解压后核对文件清单、版本及SHA256；网站上线后另核对全部静态资源和公开下载包。

## 复现

在项目根目录使用现有隔离环境：

```powershell
runtime/venv/Scripts/python.exe -B source/firmware/build.py --version 1.5.15 --output build/firmware-1.5.15-check
$env:ELINK_TEST_FIRMWARE_DIR = "$PWD/build/firmware-1.5.15-check"
$env:PYTHONPATH = "$PWD/source/tests;$PWD/source/backend"
runtime/venv/Scripts/python.exe -B -m unittest -v test_font_readability test_pixel_fonts
node --test source/web/tests/*.test.js
```

`test_font_readability` 的基线位于 `build/firmware-1.5.14-repro`，需保留作只读对照。网页内附的源码字体与项目源码一致，可在 `source/web` 内运行 `python tools/build-text-fonts.py` 重建。

软件像素、墨迹数量和放大图不能证明实体屏对比度。本次未做实体红色显影、残影、续航、真手机蓝牙或整套长期存储回归；未改动的机器码保持字节一致，不能代替这些实机验收。
