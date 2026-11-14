# 原生点阵预览核对：250×122 / 固件1.5.15

用户实拍中的断笔问题仍未解决。本次修正预览来源和展示方式，没有刷写设备，也没有改变固件、驱动、波形或字库。不使用 Computer Use。

## 找到的确定差异

1. 旧演示入口 `source/opendesign/mockups/elink-screen-design/index.html` 仍引用 `v1.5.2/*.png`。其 `proof.json` 标明使用 **Noto Sans SC Black**，而当前1.5.15使用 **Fusion Pixel / Unifont**，不是同一版本或同一字形。
2. 旧入口默认选择 `real` 和 `paper`：按96 DPI估算时，将250×122内容显示为约183.50×89.61 CSS像素，开启高质量平滑缩放并替换三种颜色。它无法用于逐点核对。
3. 旧导出脚本默认选择 `build/firmware-1.5.2`，并生成每屏500×244的总览及4倍放大图。交付前一次确实显式指定了1.5.15构建，但默认值和旧查看入口仍可能误导后续核对。

旧入口及原始源码已归档到 `backup/2026-11-14/native-pixel-preview/`。现入口只引用 `native-1.5.15/`，不调色、不绘字、不平滑、不推算物理尺寸；每张PNG的固有尺寸、HTML宽高都为250×122。

## 新预览的数据链

指定已交付 OTA JSON → 校验其应用与受测BIN逐字节相同 → 执行应用内的原生绘图/接收代码 → 读取两个4000字节模拟RAM平面 → 按控制器原生位序解码为PNG。

应用 SHA256：`e85dc4045bb5dac341f5295b073fdeb9bfa709d424c54df5277883035745ee2b`，固件ID：`18982457`。与当前1.5.15升级包一致，不能自动回退到旧构建。

控制器平面存储为128×250个比特，长度4000字节；其中每行只有122个源比特可见，另外6个是填充。无插值地裁去填充并旋转后，得到250×122，即30500个可见点。PNG仅含黑/白/红，不含灰阶或抗锯齿。每一张同时保留原始8000字节点阵和SHA256。

默认页、时钟、月历、提醒汇总及图片日历来自编译应用执行后的RAM；公告先用当前点阵渲染器产生固定输入，再通过编译应用的上传接收路径后读取RAM。SPI/GPIO/BUSY等仍是模拟边界，不是实体控制器读回。

## 核对方法

5项针对性测试覆盖全部30500点的位序、四角和字节边界、6个填充比特不影响可见区域、错误固件/标识拒绝、缺少显式来源时拒绝、PNG导出期间禁止调用缩放/绘字/字体API。另逐点核对9张完整原生图，共274500个像素，及PNG头中的实际250×122尺寸。

月历样例与用户实拍同为 **2026-11-14，星期六，第46周，100%电量，农历十月初六，小雪8天后**。提醒汇总保留2026-10-06测试输入，另保留六行月份、闰月和荷兰时间边界。

```powershell
$env:ELINK_TEST_FIRMWARE_DIR = "$PWD/build/firmware-1.5.15-release"
$env:ELINK_PREVIEW_UPDATE_PACKAGE = "$PWD/releases/firmware-1.5.15-test/elink-bwr-1.5.15.elink-update.json"
$env:ELINK_PREVIEW_OUT = "$PWD/build/native-preview-check"
runtime/venv/Scripts/python.exe -B source/tools/preview_screen_design.py
$env:PYTHONPATH = "$PWD/source/tests;$PWD/source/backend"
runtime/venv/Scripts/python.exe -B -m unittest -v test_native_preview
```

输出目录必须为空，避免混入旧图。当前预览见 `source/opendesign/mockups/elink-screen-design/index.html`，可分发包见 `releases/elink-native-preview-1.5.15.zip`。证据目录中的 `legacy-viewer-evidence.json`、`unit-tests.txt`、`output-verification.json` 和 `verified-pages/proof.json` 分别记录旧入口、测试、像素穷举及来源。

## 实拍暴露出的另一项限制

1.5.15增高数字，但12px中文示例“待、提、醒、今、日、天、后”与1.5.14的位图完全相同；18px中文多数横竖笔段仍只有一个点宽。以“小”为例，34个水平连续笔段均为单点宽。`thin-stroke-evidence.json` 记录了测量，不能再用数字高度达标代替整页可读性验收。

实拍可见细笔画断裂、粗笔画较完整，与单点细笔画问题相符；尚不能仅凭照片证明唯一显影原因。新PNG准确表达这些固件像素，但不模拟墨水屏的反射对比度、残影和单点显影，不能作为断笔已修复的证明。
