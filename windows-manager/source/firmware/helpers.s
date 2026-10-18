// Appended after the boot asset, inside the same bounded retained RAM overlay.
frame_read:
    cmp r6,#3
    bne frame_bad
    ldrb r1,[r4,#7]
    ldrb r2,[r4,#8]
    lsls r2,r2,#8
    orrs r1,r2
    ldr r0, =8000
    cmp r1,r0
    bhs frame_bad
    ldr r0, =4000
    ldr r5, =0x07fcdedc
    cmp r1,r0
    blo frame_allocate
    ldr r5, =0x07fcf15c-4000
frame_allocate:
    adds r5,r5,r1
    movs r6,#128
    ldr r0, =ALLOCATE
    bx r0
frame_bad:
    ldr r0, =BAD_PACKET
    bx r0
.ltorg
busy_timeout:
    push {r1,r2,lr}
    cmp r0,#0
    beq timeout_exit
    ldr r1, =STATE_ADDRESS
    ldrb r2,[r1,#26]
    adds r2,#1
    strb r2,[r1,#26]
    cmp r2,#225
    blo timeout_exit
    movs r0,#0
    strb r0,[r1,#8]
    movs r2,#4
    strb r2,[r1,#9]
timeout_exit:
    pop {r1,r2,pc}
.ltorg
panel_reset:
    push {r4,lr}
    ldr r4, =0x07fd0550
    ldr r0,[r4]
    movs r1,#0
    bl 0x07fc505c
    // Bounded Cortex-M0 loops: at <=32 MHz, low >=5 ms, settle >=22 ms.
    // No dependency on how long the caller spent drawing the frame.
    ldr r0, =40000
reset_low:
    subs r0,#1
    bne reset_low
    ldr r0,[r4]
    movs r1,#1
    bl 0x07fc505c
    ldr r0, =180000
reset_settle:
    subs r0,#1
    bne reset_settle
    pop {r4,pc}
.ltorg
adv_window:
    ldr r0, =STATE_ADDRESS
    ldrb r0,[r0,#21]
    cmp r0,#0
    beq continuous
    movs r1,#100
    muls r0,r1,r0
    ldr r1, =0x07fc277d
    bx lr
continuous:
    // Continue the native start function after its optional stop timer.
    // A zero-delay app_easy_timer is invalid; it must never be called here.
    strb r0,[r5,#15]
    ldr r0, =0x07fc6b49
    bx r0
.ltorg
leds_off:
    // LED cathodes sit on these pins (active low): output high keeps them dark.
    push {lr}
    movs r0,#2
    bl led_high
    movs r0,#0x25
    bl led_high
    movs r0,#0x29
    bl led_high
    pop {pc}
led_high:
    push {lr}
    movs r1,#3
    lsls r1,r1,#8
    movs r2,#1
    bl 0x07fc4ff4
    pop {pc}
wake_pins:
    // Replaces native periph_init's PAD_LATCH_EN read-modify; caller still stores r0.
    // Unconfigured pads revert to pull-down after every wake, which lights the LED.
    push {lr}
    bl leds_off
    ldrh r0,[r4,#0xe]
    orrs r0,r7
    pop {pc}
    .word busy_timeout+1,panel_reset+1,adv_window+1,leds_off+1,wake_pins+1
