# 墨水屏高地址Flash使用核对

2026-10-18。问题是“其他方案是否使用512KiB的全部容量”。这里区分使用高于0x40000的地址、规划整个存储器、以及把全部字节用满；三者不能混称。网上证据不能替代本机型号、供电及擦写验证，本轮没有运行外部刷机代码。

## 查到的直接证据

| 项目 | 源码或维护者文档证据 | 对本机的意义与限制 |
|---|---|---|
| ATC_TLSR_Paper | [作者引脚说明](https://github.com/atc1441/ATC_TLSR_Paper/blob/main/Hanshow_Stellar_MN%40_E31H_Pinout.txt)列TLSR8359、512KB Flash；[固定提交flash.c](https://github.com/atc1441/ATC_TLSR_Paper/blob/3778d296f418c30b05310d86dafa4e3404071cb4/Firmware/src/flash.c)提供0x78100配置读取、扇区擦除及写入代码 | 代码确实出现高半区操作，但本次未在设备运行，也未确认此配置模块在所有构建中被调用；不能说已证明全部512KiB都用满。它不是DA14585，不能移植启动/射频/引脚配置 |
| OpenEPaperLink TLSR分支 | [固定提交board.h](https://github.com/OpenEPaperLink/OpenEPaperLink/blob/53aa3d83fd554ba8ea732170badb527bbd151bfd/ARM_Tag_FW/OpenEPaperLink_TLSR/src/board.h)把配置定义在0x40000、长度0x3000，图片起点0x43000、范围长度0x20000；[eeprom.c](https://github.com/OpenEPaperLink/OpenEPaperLink/blob/53aa3d83fd554ba8ea732170badb527bbd151bfd/ARM_Tag_FW/OpenEPaperLink_TLSR/src/eeprom.c)接到Flash实际读写API | 这是高地址用于图片/配置的源码先例。更新区和图片区定义重叠，不能把该文件当成本机可直接套用的可靠分区表；没有证明所有物理字节被使用 |
| OpenEPaperLink Chroma74 | [项目维护者Wiki](https://github.com/OpenEPaperLink/OpenEPaperLink/wiki/Chroma-74)列1MiB SPI Flash及10个图片槽，同时保留厂家NVRAM、配置、OTA和尾部空闲区 | 说明小RAM主控可以分区读取外部图片；该机是TI CC1110，容量1MiB，非本机512KiB案例。Wiki表格个别后部行起止地址有重叠/倒置，不能据此生成写入布局 |
| HMCLOCK，当前基线的来源 | [维护者说明](https://github.com/tpunix/HMCLOCK)列DA14585、OTA及0x39000/0x3A000面板配置；[固定提交spi_flash.c](https://github.com/tpunix/HMCLOCK/blob/bc9c1ea04c8ec5ffc6c73cf4e1aaf382817ebdc3/src/epd/spi_flash.c)的读写函数发送三字节地址 | 驱动接口本身不是16位地址，并非天然只能读低256KiB；未找到其同款设备把高256KiB完整作为图库使用的可复核实机证据 |

## 与当前空间问题的关系

存在墨水屏方案规划和访问512KiB高地址的代码先例，所以Toolbox默认0x40000不是通用硬件上限。但本轮没有找到同款DA14585屏将全部512KiB用满且保留本项目底层和双区回退的可靠实证。

[Renesas DA14585数据手册](https://www.renesas.com/en/document/dst/da14585-datasheet)说明，96KiB系统RAM同时承载启动时从外部Flash镜像的程序以及蓝牙数据、全局变量和栈。因此把外部Flash的高半区用于照片，并不会自动增加可执行程序的RAM空间；这是依据官方内存结构及本项目编译布局得出的结论。

本机512KiB文件与完整读取日志已经归档，高256KiB这次全FF。若进一步核实物理容量、原生地址用途和擦除边界，按双4KiB元数据页、一个8KiB更新备用槽预算，理论可容纳30张8KiB照片；不是“512KiB全用于图片”，也不是已验收的设备容量。当前1.5.4只做高地址读取诊断，没有开放高半区写入。

GitHub源码树、固定提交源文件在 `backup/2026-10-18/album-test-version/research`。TLSR提交分别为 `3778d296f418c30b05310d86dafa4e3404071cb4` 与 `53aa3d83fd554ba8ea732170badb527bbd151bfd`；没有导入它们的启动或驱动实现。
