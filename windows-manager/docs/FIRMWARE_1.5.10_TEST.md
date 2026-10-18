# 2.13原生小字加粗1.5.10测试固件

DA14585五测试点、BWR 250×122，固件ID `fde89808`，应用60028B，SHA256 `af8942121ecb2b84e2973ae6402c23a2b46c5193cb1af9364a00cd071e826058`。

配套管理端1.5.11，使用elink-bwr-1.5.10.elink-update.json执行应用OTA，先升级一块测试屏。此包不包含用于偏移0覆盖的整片SPI镜像，不要整片擦除。

12px年月、倒计时及开机MAC改用Noto Sans SC Black；“今日天后”一并加粗，斜杠保留完整笔画。字号、174/76布局、图库分区和协议保持。MAC读取、设备身份、启动/蓝牙/面板/Flash原生驱动及堆栈边界不修改；应用差异保护见protected-region-check.json。

回退文件为rollback/elink-bwr-1.5.9.elink-update.json。旧图库格式兼容，换字体无需重新写图。当前为供用户实机验收的测试固件，原像素与模拟验证不能代替实物观感。详情见MANAGER_1.5.11.md。
