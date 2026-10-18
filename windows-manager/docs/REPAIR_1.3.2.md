# ELINK BWR V1.3.2 · 鸿蒙粗体

适用 DA14585 五测试点、IL3897、2.13 寸三色 250×122。默认、时钟、月历和公告统一采用 HarmonyOS Sans Bold，保留上一版字号与布局。中文/正文为 SC Bold；12px 紧凑英文为同家族 Condensed Bold。原厂清晰的66px时钟数字保持。

使用字体本身的粗体笔画，去掉额外偏移描粗；不放大字号补偿细字。生成1bpp无灰阶文字像素，预览、公告发送和设备内置页面共用该结果。默认页版本保持红色大写V，紧接“-”和完整设备MAC；宽MAC与蓝牙图标之间检查留白。

原始TTF来自华为官方字体包，按完整原文件附带，不修改轮廓、不改名、不子集化；许可证在 fonts/HarmonyOS/LICENSE.txt，软件页尾明确字体使用说明。设备绘图数据为原字体渲染的文字图像，许可来源与文件哈希见PROVENANCE.md。

保持5分钟按05/10/15等对齐更新，可选15分钟、整点或每分钟；荷兰时区及夏令时不变。广播1022.5ms、三色清屏/LUT、LED、BUSY恢复和OTA保护不变。只先升级…91:A7，实际清晰度确认后再升级其他四台。

OTA选择 firmware/elink-bwr-1.3.2.elink-update.json；有线选择 firmware/elink-bwr-1.3.2-spi.bin，偏移0，Verify。完整SPI不可作OTA，禁止操作OTP。固件ID以manifest.json为准。

设置保存在管理端和设备保留RAM，完全断电后需重新应用。软件像素和BUSY读回不能证明光学效果、残影和续航；仍待实物确认。
