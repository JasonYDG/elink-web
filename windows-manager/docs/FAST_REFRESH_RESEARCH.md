# 三色时钟快刷研究

2026-10-05，比较现有固件的真实二进制、上游源代码及公开驱动。采用同板原生波形，未移植其他芯片固件。

## 查明的区别

HMCLOCK 的 user_peripheral.c 每分钟选择 UPDATE_FLY；更大变化选择 UPDATE_FAST / UPDATE_FULL。epd.c 中 FAST 和 FLY 是两张不同的 70 字节 LUT。先前 ELINK 整页模式传 1，实际落在 FAST；原时钟分钟的 FLY 是另一分支，基线表位于 0x07fcdc68。

V1.2.0 整页分钟路径选择 FLY（传值 2），保留 BW 组合的原生脉冲与其余时序/驱动寄存器。红层 R=1 的两行组合保持零驱动，保护时钟页红线。周期全刷、小时/日期或外围/红层变动回全刷；任何失败不提交快刷参考。全部原生 LUT 字节及 C7/F7 指令选择由实际 Thumb 执行测试检查。

[HMCLOCK 时钟选择](https://github.com/tpunix/HMCLOCK/blob/master/src/user_peripheral.c) · [HMCLOCK 显示驱动](https://github.com/tpunix/HMCLOCK/blob/master/src/epd/epd.c)

## 其他公开方案

ATC_TLSR_Paper 的 2.13 BWR 驱动也有自定义 BW 快刷脉冲，但使用 TLSR 平台与 159 字节 LUT，其红色路径标有 TODO。不能把其 LUT 或二进制直接写入本板 DA14585 的 70 字节 IL3897 驱动；可参考“BW 快刷 + 定期全刷”的选择，而不能据此承诺三色光学结果。

[ATC 2.13 BWR 驱动](https://github.com/atc1441/ATC_TLSR_Paper/blob/main/Firmware/src/epd_bwr_213.c) · [GxEPD2 三色驱动参考](https://github.com/ZinggJM/GxEPD2/blob/master/src/epd3c/GxEPD2_213c.cpp)

## 实际边界

底部细字同时加粗并修复完整农历字形。真实 BUSY 结束和完整 RAM 读回能确认设备执行及数据完整，不能证明残影/颜色。没有测温、电流或长期数据，不提高驱动电压，不承诺快刷跨温度范围和电池寿命。默认全刷仍可一键选回；建议从每 10 次全刷开始，按照片残影调整此参数。
