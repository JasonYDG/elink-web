// Reuse the former QR drawing body; the native boot tail remains untouched.
// OTP MAC is already cached by native startup, little endian, before DB init.
boot_identity:
    push {r3,r4,r5,r6,r7,lr}
    sub sp,#24
    ldr r4, =0x07fd0520
    movs r5,#5
    mov r6,sp
mac_byte:
    ldrb r7,[r4,r5]
    lsrs r0,r7,#4
    bl hex_digit
    movs r0,#15
    ands r0,r7
    bl hex_digit
    cmp r5,#0
    beq mac_end
    movs r0,#58
    strb r0,[r6]
    adds r6,#1
    subs r5,#1
    b mac_byte
mac_end:
    movs r0,#0
    strb r0,[r6]
    // Select the small ASCII font even when re-entered from clock/calendar.
    bl PRODUCT_BOOT_BATTERY
    // Native 12px bitmap font; per-device MAC (version sits beside the title).
    movs r0,#MAC_X
    movs r1,#87
    mov r2,sp
    bl 0x07fc3b4c
    add sp,#24
    pop {r3,r4,r5,r6,r7,pc}
hex_digit:
    cmp r0,#10
    blo numeric
    adds r0,#7
numeric:
    adds r0,#48
    strb r0,[r6]
    adds r6,#1
    bx lr
.ltorg
