ENTRY(product_clock)
SECTIONS {
    .clock 0x07fc2cc4 : { *(.clock.entry) *(.clock.extra) *(.clock.rodata) }
    ASSERT(SIZEOF(.clock) <= 0x504, "Clock body overlaps native tick function")
    .reminder_extra 0x07fc8600 : { *(.reminder.extra) }
    ASSERT(SIZEOF(.reminder_extra) <= 0xaa4, "Reminder helpers overlap header font")
    .product 0x07fc9300 : { *(.text*) *(.rodata*) }
    ASSERT(SIZEOF(.product) <= 0x116c, "Product code overlaps retained UI state")
    .reminder 0x07fcba00 : { *(.reminder.main) }
    ASSERT(SIZEOF(.reminder) <= 0x8a0, "Reminder code overlaps calendar digits")
    .album 0x07fcc8a4 : { *(.album*) }
    ASSERT(SIZEOF(.album) <= 0xa0c, "Album code overlaps native CRC32 table")
    /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.eh_frame*) }
    ASSERT(SIZEOF(.data) == 0 && SIZEOF(.bss) == 0, "No implicit C runtime initialization")
}
