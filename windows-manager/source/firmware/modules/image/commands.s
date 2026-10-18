// Compile-time image module; shared dispatch, reply and refresh labels stay in core.
begin:
    cmp r6,#5
    bne bad
    ldrb r0,[r5,#8]
    cmp r0,#0
    bne busy
    movs r0,#1
    strb r0,[r5,#7]
    ldrb r0,[r4,#7]
    ldrb r1,[r4,#8]
    lsls r1,r1,#8
    orrs r0,r1
    strh r0,[r5,#12]
    ldrb r0,[r4,#9]
    ldrb r1,[r4,#10]
    lsls r1,r1,#8
    orrs r0,r1
    strh r0,[r5,#16]
    movs r0,#0
    strh r0,[r5,#10]
    strh r0,[r5,#14]
    strb r0,[r5,#26]
    b accepted
data:
    cmp r6,#4
    blo bad
    cmp r6,#131
    bhi bad
    ldrb r0,[r5,#7]
    cmp r0,#1
    bne bad
    ldrb r0,[r5,#8]
    cmp r0,#0
    bne busy
    ldrb r0,[r4,#7]
    ldrb r1,[r4,#8]
    lsls r1,r1,#8
    orrs r0,r1
    ldrh r2,[r5,#10]
    cmp r0,r2
    bne bad
    subs r6,#3
    adds r1,r2,r6
    ldr r0, =8000
    cmp r1,r0
    bhi bad
    mov r7,r4
    adds r7,#9
copy:
    ldr r0, =4000
    ldr r1, =0x07fcdedc
    cmp r2,r0
    blo first
    ldr r1, =0x07fcf15c-4000
first:
    ldrb r3,[r7]
    strb r3,[r1,r2]
    ldrh r0,[r5,#14]
    adds r0,r0,r3
    strh r0,[r5,#14]
    adds r7,#1
    adds r2,#1
    subs r6,#1
    bne copy
    strh r2,[r5,#10]
    b accepted
commit:
    cmp r6,#3
    bne late_bad
    ldrb r0,[r5,#7]
    cmp r0,#1
    bne late_bad
    ldrb r0,[r5,#8]
    cmp r0,#0
    bne late_busy
    ldrb r0,[r4,#7]
    ldrb r1,[r4,#8]
    lsls r1,r1,#8
    orrs r0,r1
    ldrh r1,[r5,#12]
    cmp r0,r1
    bne late_bad
    ldrh r0,[r5,#10]
    ldr r1, =8000
    cmp r0,r1
    bne late_bad
    ldrh r0,[r5,#14]
    ldrh r1,[r5,#16]
    cmp r0,r1
    bne late_bad
    movs r0,#2
    strb r0,[r5,#7]
    bl led_open
    bl 0x07fc3f68
    bl 0x07fc40e8
    bl 0x07fc4174
    // Exact native clock tail disables sleep during refresh and starts BUSY polling.
    bl 0x07fc00a0
    b accepted
