# 管理端 1.5.13、网页 1.1.0 与固件 1.5.11

GitHub Pages 现已直接支持图片日历、左右取景、共用离线轮播设置、设备图库配置/原图恢复、实际 RAM 像素读回及应用 OTA。修复旧网页拒绝新 ELUI 能力位、固件版本表缺失和未查询像素的问题。Windows 与网页共享图库操作布局；快速连续选择图片按点击顺序处理。

旧固件维持四张上限。1.5.11 使用 ELA1 v3，最多七张，每张 8000 字节，占一个 8192 字节槽；以小时至七天的间隔顺序循环。每天换一张可形成七天一轮；它不是按星期几绑定图片的课程表。图片与图片日历共用选图、顺序、取景及间隔。重新通电从首张开始，整图换图不依赖校时，日历日期仍需要校时。

读取状态会返回数量、当前索引、间隔、模式、启停、CRC32、取景和原图。已知图片复用本地记录；新固件通过只读 BD05 取回未知图片，每张校验 CRC32，最后再次核对配置序号。界面恢复播放列表，可移除一张后选入新图，其余图片和取景保留。点击应用才写入新的完整事务。旧固件没有原图读取命令；本地缺失原图时提示升级，不伪造可编辑图库。

## 空间及兼容

所有区间左闭右开，未改变低 256KiB、启动、射频、BLE、面板、波形、OTA 双槽、OTP/MAC、校准及堆栈边界。

| Flash 区间 | 大小 | 用途 |
|---|---:|---|
| 0x40000–0x42000 | 8KiB | 交替配置页，与旧版相同 |
| 0x42000–0x4A000 | 32KiB | 图像区 0，第 1–4 张，地址不变 |
| 0x4A000–0x52000 | 32KiB | 图像区 1，第 1–4 张，地址不变 |
| 0x52000–0x58000 | 24KiB | 新增图像区 0，第 5–7 张 |
| 0x58000–0x5E000 | 24KiB | 新增图像区 1，第 5–7 张 |
| 0x5E000–0x80000 | 136KiB | 本版不写入 |

图库合计 120KiB，比四张版增加 48KiB。旧配置先在 RAM 中校验转换，原图地址不动；首次接纳旧配置还要确认新增 48KiB 全部为 FF，发现未知数据即拒绝。已有 512KiB 备份中该范围为 FF，但固件仍会现场检查，不能用历史备份代替设备检查。

新配置 ELG2 为 52 字节：前 16 字节为 magic、sequence、CRC32、minutes、count、flags；flags 的 bit0/1/2 分别为日历模式、图像区、启用。后面依次是七个 CRC32、七个取景字节、ready。CRC 覆盖 0–7 及 12–50，ready 最后写入。ELA1 v3 共 64 字节，前 12 字节沿用状态含义。ELUI 第 6 字节 bit4 表示七张和原图读取。BD05 slot offsetLE16 仅读当前有效图像区，返回最多 128 字节，严格限制 slot/count 和 0–7999 偏移；不暴露任意地址读取。

升级会保留旧四张图库；旧固件不能读取 ELG2。写入新图库后若要回退旧固件，应先保留原图和管理数据备份，不能假定旧版还能识别七张播放列表。

RAM 状态 124/128 字节，沿用 0x07FD2140 位置。应用层去掉未被现有页面调用的 18px 字形，保留字形的像素和度量逐字节相同；字体尾部形成 512 字节应用辅助段。未扩大任何底层内存边界。准确代码余量见同版本 space-report.json。

仍采用非活动图像区和交替元数据页，保存中断不启用半套新图库。替换一张时目前仍提交完整新事务，保证旧图库可恢复；不是原地覆盖正在播放的那张。

## 传输与升级

网页先用严格无存储写入的长状态请求检查连接容量；支持后用 128 字节像素载荷、63 包，旧连接保留 17 字节、471 包。屏幕清屏和三色刷新耗时仍在。网页 OTA 检查专用升级包、应用大小、SHA256、启动向量、固件 ID 和版本标记；在擦写前检查 136 字节写入，逐字节读回整个非活动镜像后仅提交一次，重连核对新 ID。两端将应用上限限制为 65472 字节，给 64 字节头和页对齐留足单槽空间。

本地原有导入图片的英文标签通过显式备份命令统一为中文，不修改像素、ID、任务、取景或播放顺序。命令 source/tools/normalize_image_titles.py 默认只预览，--apply 才修改已知旧标签。

## 验证状态

编译后 Thumb 模拟验证七张循环、旧配置迁移、断电首张恢复、原图读回、边界拒绝和保护区；浏览器验证 1280/390 宽度、共用轮播、读回设置、单张替换、置顶进度及重载保留数据。网页协议测试还覆盖长包回退、全量 OTA 读回、错误版本和提交中断。

交付为候选测试版本。模拟及像素读回不等于物理屏幕光学、续航、射频或真实掉电验证。本次没有对实体屏执行升级、擦写或恢复出厂。

## Launcher revision 2

Start.cmd is ASCII only, without BOM. Startup failures keep the window open until a key is pressed and write the full error to %LOCALAPPDATA%/ElinkManager/logs/startup.log. Missing files report that the complete ZIP must be extracted. If an older manager owns port 18765, close its console first; closing only the browser tab does not stop that process. No process is killed automatically.

This revision changes only the launcher, packaging checks and related documentation. Manager executable/resources and firmware1.5.11 are byte-for-byte unchanged; no additional screen update is required for this launcher fix.
