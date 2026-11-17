ENTRY(product_clock)
SECTIONS {
    .clock 0x07fc2cc4 : { *(.clock.entry) *(.clock.extra) *(.clock.rodata) }
    ASSERT(SIZEOF(.clock) <= 0x504, "Clock body overlaps native tick function")
    .alert_small 0x07fc8488 : { *(.alert.small) }
    ASSERT(SIZEOF(.alert_small) <= 0x78, "LED state overlaps reminder RAM")
    .reminder_extra 0x07fc8600 : { *(.reminder.extra) }
    ASSERT(SIZEOF(.reminder_extra) <= 0xaa4, "Reminder helpers overlap header font")
    .product 0x07fc9300 : {
        *(.text.__aeabi_unwind_cpp_pr0 .text.__aeabi_memclr .text.memset)
        *(.text.product_ink .text.next_code .text.pixel .text.product_battery .text.product_sync_valid .text.product_timezone)
        . = 0x07fc96cc; *(.product.boot)
        *(.text*)
        *(.rodata.product* .rodata.month* .rodata.calendar* .rodata.lunar* .rodata.clock_face* .rodata.cst* .rodata..L*)
        KEEP(*(.product.version))
        *(.rodata*)
    }
    ASSERT(product_boot_battery == 0x07fc96cd, "Preserve the native boot hook target")
    ASSERT(SIZEOF(.product) <= 0x116c, "Product code overlaps retained UI state")
    .alert_photo 0x07fcb968 : { *(.alert.photo) }
    ASSERT(SIZEOF(.alert_photo) <= 0x98, "Alert helper overlaps reminder code")
    .reminder 0x07fcba00 : { *(.reminder.main) }
    ASSERT(SIZEOF(.reminder) <= 0x8a0, "Reminder code overlaps calendar digits")
    .album_extra 0x07fcb580 : { *(.album.extra) }
    ASSERT(SIZEOF(.album_extra) <= 0x200, "Album helpers overlap photo digit glyphs")
    .alert 0x07fcc848 : { *(.alert*) }
    ASSERT(SIZEOF(.alert) <= 0x5c, "Alert helper overlaps album code")
    .album 0x07fcc8a4 : { *(.album*) }
    ASSERT(SIZEOF(.album) <= 0xa0c, "Album code overlaps native CRC32 table")
    .large_date 0x07fd1ae0 : { *(.large_date) }
    ASSERT(SIZEOF(.large_date) <= 0x564, "Calendar renderer overlaps retained helpers")
    /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.eh_frame*) }
    ASSERT(SIZEOF(.data) == 0 && SIZEOF(.bss) == 0, "No implicit C runtime initialization")
}
