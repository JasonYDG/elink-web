// HMCLOCK exact-baseline extension, Cortex-M0 Thumb-1 plus BL.
// Builder relocates this code into the bounded, retained RAM gap above native heap.
dispatch:
    push {r0,r1,r2,r3,r5,r6,r7,lr}
    ldr r5, =0x07fc04e0
    ldrh r6, [r4,#4]
    cmp r6,#1
    blo handled
    ldrb r0,[r4,#6]
    cmp r0,#0x9e
    beq sync_validate
    cmp r0,#0x91
    bne commands
sync_validate:
    cmp r6,#12
    bne bad
    mov r0,r4
    adds r0,#6
    bl PRODUCT_SYNC_VALID
    cmp r0,#0
    beq bad
    ldrb r2,[r4,#6]
    cmp r2,#0x9e
    beq quiet_sync
    movs r1,#0
    ldrb r2,[r5,#7]
    cmp r2,#3
    bne clock_sync
    movs r1,#3
    b clock_sync
quiet_sync:
    ldrb r1,[r5,#8]
    cmp r1,#0
    bne busy
    movs r1,#2
    movs r2,#0x91
    strb r2,[r4,#6]
clock_sync:
    strb r1,[r5,#7]
    ldrb r1,[r5,#27]
    movs r3,#1
    orrs r1,r3
    strb r1,[r5,#27]
    // Validation returned 1; the original tail reloads the actual 91 opcode.
commands:
    cmp r0,#0xa0
    beq ota_guard
    cmp r0,#0xa2
    blo native_command
    cmp r0,#0xa3
    bhi native_command
    cmp r6,#136
    bne bad
    b original
ota_guard:
    cmp r6,#4
    blo bad
    ldrb r1,[r5,#8]
    cmp r1,#0
    bne busy
    ldrh r1,[r4,#8]
    ldr r2, =0xe2f4
    cmp r1,r2
    blo bad
    b original
native_command:
    cmp r0,#0xb0
    bhs timezone
    cmp r0,#0x9f
    beq timezone
    cmp r0,#0x9c
    beq calendar_view
    cmp r0,#0x9d
    beq capabilities
    cmp r0,#0xa5
    beq ota_abort
    cmp r0,#0xa1
    beq ota_read
    cmp r0,#0x9a
    beq frame_read
    cmp r0,#0x9b
    beq panel_info
    cmp r0,#0x93
    beq status
    cmp r0,#0x94
    beq policy
    cmp r0,#0x95
    beq begin
    cmp r0,#0x96
    beq data
    cmp r0,#0x97
    beq commit
    cmp r0,#0x98
    beq resume
    cmp r0,#0x99
    beq timing
original:
    pop {r0,r1,r2,r3,r5,r6,r7}
    pop {r0}
    mov lr,r0
    ldrb r0,[r4,#6]
    cmp r0,#0x90
    bx lr
calendar_view:
    cmp r6,#2
    bne bad
    ldrb r0,[r4,#7]
    cmp r0,#2
    bne timed_view
    ldrb r0,[r5,#8]
    cmp r0,#0
    bne busy
    ldrb r0,[r5,#7]
    cmp r0,#1
    beq busy
    movs r0,#4
    strb r0,[r5,#7]
    bl boot_first
    b accepted
timed_view:
    bl PRODUCT_VIEW
    b reject
capabilities:
    cmp r6,#1
    bne bad
    ldr r5, =PRODUCT_CAPS
    movs r6,#8
    b allocate
timezone:
    mov r0,r4
    mov r1,r6
    bl PRODUCT_CONTROL
    b reject
policy:
    cmp r6,#3
    bne bad
    ldrb r1,[r4,#7]
    cmp r1,#2
    bhi bad
    ldrb r2,[r4,#8]
    cmp r2,#1
    blo bad
    cmp r2,#60
    bhi bad
    strb r1,[r5,#5]
    strb r2,[r5,#6]
    movs r1,#0
    strb r1,[r5,#20]
    b accepted
timing:
    cmp r6,#4
    bne bad
    ldrb r1,[r4,#7]
    cmp r1,#1
    blo bad
    cmp r1,#60
    bhi bad
    ldrb r2,[r4,#8]
    cmp r2,#1
    blo bad
    cmp r2,#240
    bhi bad
    ldrb r3,[r4,#9]
    cmp r3,#0
    beq save_timing
    cmp r3,#10
    blo bad
    cmp r3,#120
    bhi bad
save_timing:
    strb r1,[r5,#24]
    strb r2,[r5,#22]
    strb r3,[r5,#21]
    movs r1,#0
    strb r1,[r5,#23]
    strb r1,[r5,#25]
    b accepted
.include "modules/image/commands.s"
resume:
    cmp r6,#1
    bne late_bad
    ldrb r0,[r5,#8]
    cmp r0,#0
    bne late_busy
    movs r0,#0
    strb r0,[r5,#7]
    movs r0,#0x80
    bl 0x07fc2cc4
accepted:
    movs r0,#0
    strb r0,[r5,#9]
    b handled
busy:
late_busy:
    movs r0,#2
    b reject
bad:
late_bad:
    movs r0,#1
reject:
    strb r0,[r5,#9]
handled:
    pop {r0,r1,r2,r3,r5,r6,r7}
    pop {r0}
    ldr r0, =0x07fc6c95
    bx r0
frame_read:
    ldr r0, =FRAME_READ
    bx r0
panel_info:
    cmp r6,#1
    bne bad
    ldr r5, =0x07fd04dc
    movs r6,#128
    b allocate
status:
    cmp r6,#1
    bne bad
    movs r6,#32
allocate:
    movs r0,#0xfd
    bl 0x07f0283e
    mov r1,r0
    ldr r0, =0xfd03
    movs r2,#4
    mov r3,r6
    adds r3,#6
    bl 0x07f1bbb0
    ldr r1, =0x07fd24cc
    adds r1,#0x5c
    ldrb r1,[r1]
    strb r1,[r0]
    movs r1,#6
    strh r1,[r0,#2]
    mov r1,r6
    strh r1,[r0,#4]
    movs r2,#0
    adds r0,#6
publish:
    ldrb r1,[r5,r2]
    strb r1,[r0,r2]
    adds r2,#1
    cmp r2,r6
    bne publish
    subs r0,#6
    bl 0x07f1bbe2
    b handled
.ltorg

refresh:
    push {r0,r2,r3,lr}
    ldr r5, =0x07fd04dc
    bl PRODUCT_REFRESH
    mov r1,r0
refresh_exit:
    pop {r0,r2,r3,pc}

finish_busy:
    push {r1,r2,r3,lr}
    bl 0x07fc3bdc
    bl BUSY_TIMEOUT
    bl PRODUCT_FINISH
    cmp r0,#0
    bne finish_exit
    ldr r1, =0x07fc04e0
    ldrb r2,[r1,#8]
    cmp r2,#0
    beq finish_exit
    movs r2,#0
    strb r2,[r1,#8]
    ldrh r2,[r1,#18]
    adds r2,#1
    strh r2,[r1,#18]
finish_exit:
    pop {r1,r2,r3,pc}

led_open:
    push {r0,r1,r2,lr}
    bl LEDS_OFF
    bl 0x07fc3f04
    pop {r0,r1,r2,pc}
.ltorg
adv_tick:
    push {r0,r1,r2,lr}
    bl PRODUCT_MINUTE_TICK
    ldr r0, =0x07fd24cc
    ldr r0,[r0,#0x48]
    adds r0,#1
    bne adv_exit
    ldr r0, =0x07fd04dc
    ldr r0,[r0,#0x2c]
    cmp r0,#0
    bne adv_exit
    ldr r1, =0x07fc04e0
    ldrb r2,[r1,#7]
    cmp r2,#1
    bne adv_count
    ldrb r2,[r1,#26]
    adds r2,#1
    strb r2,[r1,#26]
    cmp r2,#3
    blo adv_count
    movs r2,#0
    strb r2,[r1,#7]
    movs r2,#3
    strb r2,[r1,#9]
adv_count:
    ldrb r2,[r1,#23]
    adds r2,#1
    ldrb r0,[r1,#22]
    cmp r2,r0
    blo save_adv_count
    movs r2,#0
    strb r2,[r1,#23]
    bl 0x07fc6af0
    b adv_exit
save_adv_count:
    strb r2,[r1,#23]
adv_exit:
    pop {r0,r1,r2,pc}
.ltorg
ota_abort:
    pop {r0,r1,r2,r3,r5,r6,r7}
    pop {r0}
    ldr r0, =0x07fd0558
    movs r1,#0
    ldr r2, =0x07fc6e5d
    bx r2
.ltorg
ota_read:
    cmp r6,#3
    bne bad
    ldr r0, =0x07fd0558
    ldr r0,[r0,#0x18]
    ldrb r1,[r4,#7]
    ldrb r2,[r4,#8]
    lsls r2,r2,#8
    orrs r1,r2
    adds r0,r0,r1
    movs r1,#128
    ldr r5, =0x07fd03dc
    mov r2,r5
    bl 0x07fc6828
    movs r6,#128
    b allocate
.ltorg
ota_finalize:
    push {r4,lr}
    ldr r4, =0x07fd0558
    ldr r0,[r4,#0x14]
    lsls r0,r0,#24
    ldr r1, =0x00aa5170
    orrs r0,r1
    ldr r1, =0x07fd03dc
    str r0,[r1]
    ldr r0,[r4,#0x18]
    movs r2,#4
    bl 0x07fc67c4
    bl 0x07fc6990
    mov r0,r4
    movs r1,#0
    pop {r4,pc}
.ltorg
boot_screen:
    ldr r0, =0x07fc04e0
    ldrb r1,[r0,#27]
    cmp r1,#0
    bne boot_done
    ldrh r1,[r0,#18]
    cmp r1,#0
    bne boot_done
    ldrb r1,[r0,#8]
    cmp r1,#0
    beq boot_first
boot_done:
guard:
    bx lr
boot_first:
    push {r1,r2,r3,r4,r5,r6,r7,lr}
    bl led_open
    ldr r6, =BOOT_ASSET
    ldr r4, =0x07fcdedc
    ldr r7, =4000
    movs r5,#0
boot_run:
    ldrb r0,[r6]
    adds r6,#1
    movs r2,#0x80
    tst r0,r2
    bne boot_repeat
    adds r0,#1
boot_literal:
    ldrb r1,[r6]
    adds r6,#1
    strb r1,[r4]
    adds r4,#1
    subs r7,#1
    subs r0,#1
    bne boot_literal
    b boot_next
boot_repeat:
    subs r0,#127
    ldrb r1,[r6]
    adds r6,#1
boot_fill:
    strb r1,[r4]
    adds r4,#1
    subs r7,#1
    subs r0,#1
    bne boot_fill
boot_next:
    cmp r7,#0
    bne boot_run
    cmp r5,#0
    bne boot_display
    movs r5,#1
    ldr r4, =0x07fcf15c
    ldr r7, =4000
    b boot_run
boot_display:
    bl 0x07fc2248
    bl 0x07fc3f68
    bl 0x07fc40e8
    bl 0x07fc4174
    // Reuse the exact native startup refresh/sleep tail and its matching stack.
    ldr r0, =0x07fc22d7
    bx r0
.ltorg
labels:
    .word dispatch+1,refresh+1,guard+1,finish_busy+1,led_open+1,adv_tick+1,ADV_WINDOW,ota_finalize+1,boot_screen+1
    .word allocate+1,handled+1,bad+1
    .word begin+1,data+1,commit+1,resume+1
