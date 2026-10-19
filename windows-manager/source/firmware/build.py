"""Reproducible, hash-pinned patch of the physically booted HMCLOCK baseline.

Requires the development lockfile. Does not connect to or flash any hardware.
"""
from pathlib import Path
import hashlib,json,struct,re,zlib,argparse,sys,io
from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from module_build import load_modules,expand_assembly,module_functions,section_limits

ROOT=Path(__file__).resolve().parents[2]
BASE=0x07fc0000
APP_HASH='4f8178cfb73fe16209121070a499471f136d2c1e1f1636a3c59adbd3583cfb5f'
SPI_HASH='aa3d5913551d29e23e1b7cca23dd767dcbd214d78f4a26c2b4fc952e89bd0b64'
RUNTIME=BASE+0x11480
CODE=RUNTIME+48
STATE=BASE+0x11980
ASSET=STATE+32
LOAD_OFFSET=0xddd4
STATE_OFFSET=LOAD_OFFSET+STATE-RUNTIME
sha=lambda b:hashlib.sha256(b).hexdigest()
ks=Ks(KS_ARCH_ARM,KS_MODE_THUMB)
def asm(s,addr):
    b,_=ks.asm(s,addr=addr)
    if b is None: raise RuntimeError('Assembly failed: '+s)
    return bytes(b)

def assemble_external(s,addr):
    # Keystone numeric BL after .ltorg has a pool-size relocation bias.
    external=[]
    def call(m):
        name=f'external_call_{len(external)}'
        external.append((name,int(m[1],16)))
        return f'{name}:\n    bl {name}'
    s=re.sub(r'^\s*bl\s+(0x[0-9a-fA-F]+)\s*$',call,s,flags=re.M)
    if not external:return asm(s,addr)
    raw=asm(s+'\n'+''.join(f'    .word {name}\n' for name,_ in external),addr)
    positions=struct.unpack_from('<'+'I'*len(external),raw,len(raw)-4*len(external))
    code=bytearray(raw[:-4*len(external)])
    for pos,(_,target) in zip(positions,external):
        off=pos-addr
        assert 0<=off<len(code)-3
        code[off:off+4]=asm(f'bl {target}',pos)
    return bytes(code)

def boot_asset(version):
    from PIL import Image,ImageDraw
    sys.path.insert(0,str(ROOT/'source/backend'))
    from render import quantize
    from bitmap_fonts import paint,text_mask
    im=Image.new('RGB',(250,122),'white');d=ImageDraw.Draw(im)
    d.rectangle((8,15,11,107),fill=(190,0,0))
    paint(im,'ELINK',(21,20),40)
    d.line((21,83,239,83),fill='black',width=1)
    # Spec line and red version are drawn at boot by product_boot_battery from the font tables.
    if 148+text_mask('V'+version.split('-')[0],12).width>244:raise ValueError('标题行仅容纳 Vx.x.x；更长版本需重新排版')
    rendered=quantize(im);frame=rendered['frame'];im=Image.open(io.BytesIO(rendered['png']));out=bytearray()
    for p in [frame[:4000],frame[4000:]]:
        i=0
        while i<len(p):
            j=i+1
            while j<len(p) and p[j]==p[i] and j-i<128:j+=1
            if j-i>=3:out.extend((0x80|(j-i-1),p[i]));i=j
            else:
                start=i;i=j
                while i<len(p) and i-start<128:
                    j=i+1
                    while j<len(p) and p[j]==p[i] and j-i<128:j+=1
                    if j-i>=3:break
                    i=min(j,start+128)
                out.append(i-start-1);out.extend(p[start:i])
    return im,frame,bytes(out)

def identity_preview(im,app,address,version):
    # Decode the pinned native ASCII font for an example, not a shared runtime MAC.
    from PIL import ImageDraw
    from bitmap_fonts import text_mask
    im=im.copy();draw=ImageDraw.Draw(im)
    def put(font,x,y,value,fill):
        count=struct.unpack_from('<H',app,font)[0]
        for ch in value:
            entry=next(font+offset for code,offset in (struct.unpack_from('<HH',app,font+2+i*4) for i in range(count)) if code==ord(ch))
            advance,w,h,bx,by=struct.unpack_from('<BBBbb',app,entry)
            stride=(w+7)//8
            for row in range(h):
                for col in range(w):
                    if app[entry+5+row*stride+col//8] & (128>>(col%8)):
                        draw.point((x+bx+col,y+by+row),fill=fill)
            x+=advance
    put(0xa48c,19,61,'BWR 2.13 / 250x122','black')
    put(0x7eb4,148,39,'V'+version.split('-')[0],(190,0,0))
    put(0x7eb4,20,87,address,'black')
    from bitmap_fonts import status_icon
    status_icon(im,194,89)
    return im

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--version',default='1.5.4');parser.add_argument('--output',type=Path,default=ROOT/'build/firmware');args=parser.parse_args()
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9]+)?',args.version):raise ValueError('ASCII semantic version required')
    app0=(ROOT/'source/reference/hmclock-bwr-baseline-app.bin').read_bytes()
    spi0=(ROOT/'source/reference/hmclock-bwr-baseline-spi.bin').read_bytes()
    assert sha(app0)==APP_HASH and sha(spi0)==SPI_HASH
    assert app0[0xa0:0x510]==b'\xff'*1136
    assert struct.unpack_from('<I',app0,4)[0]==BASE+0x525
    assert struct.unpack_from('<4I',app0,0xdbf4)==(BASE+0xddd4,BASE+0xddd8,0x2e40,BASE+0x7088)
    assert struct.unpack_from('<4I',app0,0xdbe4)==(BASE+0x110,BASE+0x110,0x400,BASE+0x7088)
    assert struct.unpack_from('<II',app0,0x7700)==(BASE+0x10c18,2048)
    # SDK RWIP_CALC_HEAP_LEN includes 12 bytes of allocator overhead.
    assert BASE+0x10c18+2048+12<=RUNTIME<ASSET<BASE+0x121c0
    preview,frame,asset=boot_asset(args.version)
    helper_address=(ASSET+len(asset)+3)&~3
    helper_source=(ROOT/'source/firmware/helpers.s').read_text()
    helpers_probe=assemble_external(helper_source.replace('ALLOCATE',hex(CODE|1)).replace('BAD_PACKET',hex(CODE|1)).replace('STATE_ADDRESS',hex(STATE)),helper_address)
    helper_exports=struct.unpack_from('<5I',helpers_probe,len(helpers_probe)-20)
    timeout_address,reset_address,window_address,leds_off_address,wake_pins_address=helper_exports
    helper_size=len(helpers_probe)-20
    blob_size=helper_address-RUNTIME+helper_size
    assert RUNTIME+blob_size<=BASE+0x121c0, 'Overlay overlaps retained BLE data'
    app_size=LOAD_OFFSET+blob_size
    assert app_size<=65535 and app_size+64<=0x12000
    app=bytearray(app0)
    from product_build import bold_font,small_font,clock_digits,compile_product
    regions,product,elf_hash=compile_product(ROOT,args.output,leds_off_address,args.version.split('-')[0])
    font_data=bold_font(app0)
    small_data=small_font()
    app[0x7eb4:0x9300]=small_data+bytes(0x9300-0x7eb4-len(small_data))
    # No remaining low-resolution clock caller: this product is 250x122 only.
    struct.pack_into('<I',app,0x7ea0,BASE+0xc3c4)
    app[0xa46c:0xa48c]=bytes(32)
    app[0xa48c:0xc3c4]=font_data+bytes(0xc3c4-0xa48c-len(font_data))
    app[0xc3c4:0xd2b0]=clock_digits(app0)+bytes(0xd2b0-0xc8a4)
    # Reminder code uses the padding freed by the same-size glyph subset.
    for address,raw in regions.values():app[address-BASE:address-BASE+len(raw)]=raw
    # Pin native FAST/FLY BW rows; product_refresh neutralizes red combinations for the chosen mode.
    assert app0[0xdc18:0xdc26]==bytes.fromhex('80 60 40 00 00 00 00 10 60 20 00 00 00 00')
    assert app0[0xdc26:0xdc34]==app0[0xdc18:0xdc26]
    assert app0[0xdc68:0xdc76]==bytes.fromhex('40 00 00 00 00 00 00 80 00 00 00 00 00 00')
    assert app0[0xdc76:0xdc84]==app0[0xdc68:0xdc76]
    modules=load_modules(ROOT/'source/firmware')
    source=expand_assembly(ROOT/'source/firmware',(ROOT/'source/firmware/extension.s').read_text(),modules)
    source=source.replace('0x07fc04e0',hex(STATE)).replace('0x07fc00a0',hex(RUNTIME)).replace('BOOT_ASSET',hex(ASSET)).replace('FRAME_READ',hex(helper_address|1)).replace('BUSY_TIMEOUT',hex(timeout_address&~1)).replace('ADV_WINDOW',hex(window_address)).replace('LEDS_OFF',hex(leds_off_address&~1))
    for name,address in product.items():source=source.replace(name.upper(),hex(address&~1) if name!='product_caps' else hex(address))
    # Force conditional branches to Thumb-1 trampolines even for distant handlers.
    inverse={'eq':'ne','ne':'eq','lo':'hs','hs':'lo','hi':'ls','ls':'hi'}
    n=0
    def expand(m):
        nonlocal n
        if m[2] in {'commands','select_policy','refresh_exit','quick','finish_exit','adv_exit','adv_count','save_adv_count','guard_skip','guard_exit','ota_guard','native_command','late_bad','late_busy','timezone'}:
            return m[0]
        n+=1; skip=f'cond_skip_{n}'
        return f'    b{inverse[m[1]]} {skip}\n    b {m[2]}\n{skip}:'
    source=re.sub(r'^\s*b(eq|ne|lo|hs|hi|ls)\s+(\w+)\s*$',expand,source,flags=re.M)
    code=assemble_external(source,CODE)
    exported=struct.unpack_from('<16I',code,len(code)-64)
    labels=exported[:9]
    allocate,handled,bad=exported[9:12]
    image_labels=dict(zip(('begin','data','commit','resume'),exported[12:]))
    code=code[:-64] # Build-only label table is not executable firmware.
    assert CODE<=image_labels['begin']-1<image_labels['data']-1<image_labels['commit']-1<image_labels['resume']-1<=CODE+len(code)
    dispatch,refresh,guard,finish,led,adv,window,ota_finalize,boot_screen=labels
    assert all((x==window_address if i==6 else CODE<=x<STATE) and x&1 for i,x in enumerate(labels)), labels
    assert len(code)<=STATE-CODE, f'Runtime code overflow: {len(code)}'
    blob=bytearray(blob_size)
    blob[CODE-RUNTIME:CODE-RUNTIME+len(code)]=code
    # A dedicated native refresh tail with no dependency on the caller stack.
    tail=asm('''push {r0,r1,r2,lr}
        ldr r0, =0x07fd24cc
        ldrb r1,[r0,#3]
        cmp r1,#0
        beq no_sleep
        movs r1,#0x80
        strb r1,[r0,#4]
        b start_timer
    no_sleep:
        ldr r0, =0x07fd7758
        movs r1,#0
        strb r1,[r0,#3]
        adds r0,#0x5c
        strb r1,[r0]
    start_timer:
        movs r0,#40
        ldr r1, =0x07fc4209
        bl 0x07fc27f4
        pop {r0,r1,r2,pc}
        .ltorg''',RUNTIME)
    assert len(tail)<=CODE-RUNTIME
    blob[:len(tail)]=tail
    patches=[]
    def patch(off,size,s):
        b=asm(s,BASE+off); assert len(b)==size
        patches.append({'offset':hex(off),'before':app0[off:off+size].hex(),'after':b.hex()})
        app[off:off+size]=b
    patch(0x6c98,4,f'bl {dispatch&~1}')
    patch(0x4176,4,f'bl {refresh&~1}')
    patch(0x420a,4,f'bl {finish&~1}')
    assert app0[0x2646:0x264a]==asm(f'bl {BASE+0x31c8}',BASE+0x2646)
    patch(0x2646,4,f'bl {adv&~1}')
    patch(0x6b3e,4,f'bl {window&~1}')
    # Native code XORed the low MAC with its prefix. Use the actual low 24 bits.
    assert app0[0x57a8:0x57aa]==asm('eors r0,r1',BASE+0x57a8)
    patch(0x57a8,2,'mov r0,r1')
    # Native GAPM min/max use this shared literal in 0.625 ms slots.
    assert struct.unpack_from('<I',app0,0x27f0)[0]==1100
    struct.pack_into('<I',app,0x27f0,1636) # 1022.5 ms connectable advertising, sleep between events.
    assert app0[0x3f74:0x3f78]==asm(f'bl {BASE+0x40d4}',BASE+0x3f74)
    patch(0x3f74,4,f'bl {reset_address&~1}')
    # Remote disconnect must reopen advertising, without repainting a clock/QR.
    assert app0[0x4558:0x455a]==asm(f'bne {BASE+0x4572}',BASE+0x4558)
    patch(0x4558,2,f'b {BASE+0x4572}')
    # periph_init (cold start and every wake) latches pads at 0x627a; LEDs must be set first.
    assert app0[0x6276:0x627c]==asm('ldrh r0,[r4,#0xe]; orrs r0,r7; strh r0,[r4,#0xe]',BASE+0x6276)
    patch(0x6276,4,f'bl {wake_pins_address&~1}')
    # Native OTA page zero remains invalid until host readback verifies all bytes.
    assert app0[0x6e1c:0x6e20]==bytes.fromhex('0ecd2869')
    patch(0x6e1c,12,'movs r0,#255; strb r0,[r5,#2]; b '+hex(BASE+0x6e28)+'; nop; nop; nop')
    patch(0x6e58,4,f'bl {ota_finalize&~1}')
    # Own boot screen replaces QR_draw as a whole; clock keeps native sequencing.
    assert app0[0x2224:0x2226]==asm('push {r1,r2,r3,r4,r5,r6,r7,lr}',BASE+0x2224)
    patch(0x2224,4,f'ldr r3,[pc,#0]; bx r3')
    app[0x2228:0x222c]=struct.pack('<I',boot_screen)
    # QR_draw entry is replaced above; its old body has no remaining callers.
    from bitmap_fonts import text_mask
    mac_x=20
    identity=assemble_external((ROOT/'source/firmware/boot_identity.s').read_text().replace('PRODUCT_BOOT_BATTERY',hex(product['product_boot_battery']&~1)).replace('MAC_X',str(mac_x)),BASE+0x2248)
    assert len(identity)<=0x22d6-0x2248, 'Identity code overlaps native refresh tail'
    patches.append({'offset':'0x2248','before':app0[0x2248:0x2248+len(identity)].hex(),'after':identity.hex()})
    app[0x2248:0x2248+len(identity)]=identity
    # Broadcast timeout: existing function literal 0x1770 = 60s (community binary).
    # Window zero bypasses this stop timer; radio still sleeps between adverts.
    assert struct.unpack_from('<I',app0,0x6b74)[0]==6000
    state_off=STATE-RUNTIME
    blob[state_off:state_off+32]=bytes.fromhex('45 4c 4b 31 01 00 0a 04')+b'\0'*13+bytes([0,1,0,5])+b'\0'*7
    blob[ASSET-RUNTIME:ASSET-RUNTIME+len(asset)]=asset
    helpers=assemble_external(helper_source.replace('ALLOCATE',hex(allocate)).replace('BAD_PACKET',hex(bad)).replace('STATE_ADDRESS',hex(STATE)),helper_address)
    assert len(helpers)-20==helper_size
    assert struct.unpack_from('<5I',helpers,len(helpers)-20)==helper_exports
    blob[helper_address-RUNTIME:]=helpers[:-20]
    # Copy before native scatter initialization; temporary code is deliberately
    # inside TRNG only until it transfers control to the unmodified reset path.
    wrapper=asm(f'''ldr r0, ={BASE+LOAD_OFFSET}
        ldr r1, ={RUNTIME}
        ldr r2, ={blob_size}
    copy_runtime:
        ldm r0!, {{r3}}
        stm r1!, {{r3}}
        subs r2,#4
        bne copy_runtime
        ldr r0, ={BASE+0x525}
        bx r0
        .ltorg''',BASE+0x110)
    assert len(wrapper)<=0x400
    app[0x110:0x110+len(wrapper)]=wrapper
    struct.pack_into('<I',app,4,BASE+0x111)
    assert app0[0x5b28:0x5b32]==b'DLG-CLOCK-'
    app[0x5b28:0x5b32]=b'ELINK-BWR-'
    assert app0[0x5b32:0x5b3e]==b'%02x%02x%02x'
    app[0x5b32:0x5b3e]=b'%02X%02X%02X'
    firmware_id=sha(app+blob+args.version.encode('ascii'))[:8]
    blob[state_off+28:state_off+32]=bytes.fromhex(firmware_id)
    app.extend(blob)
    assert len(app)==app_size
    # Disallow Cortex-M3-only Thumb-2 instructions in extension (BL is ARMv6-M valid).
    for ins in Cs(CS_ARCH_ARM,CS_MODE_THUMB).disasm(code,CODE):
        if len(ins.bytes)==4 and ins.mnemonic!='bl':
            # Literal pools are data. Their location is inspected/tested separately.
            if ins.mnemonic.endswith('.w'): raise AssertionError(str(ins))
    assert spi0[0x26000:0x36000]==b'\xff'*0x10000, 'Pinned baseline schedule area must be unused'
    assert 0x14000+64+len(app)<=0x26000, 'OTA application bank overlaps schedule storage'
    spi=bytearray(spi0)
    crc=zlib.crc32(app)
    for bank in [0x2000,0x14000]:
        assert struct.unpack_from('<I',spi,bank+4)[0]==len(app0)
        spi[bank+64:bank+64+len(app)]=app
        struct.pack_into('<I',spi,bank+4,len(app))
        struct.pack_into('<I',spi,bank+8,crc)
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    (out/f'elink-bwr-{args.version}-app.bin').write_bytes(app)
    (out/f'elink-bwr-{args.version}-spi.bin').write_bytes(spi)
    identity_preview(preview,app,'18:BC:5A:6B:91:A7',args.version).save(out/'boot-preview.png')
    info={'version':args.version,'base_application_sha256':APP_HASH,'base_spi_sha256':SPI_HASH,
          'app_sha256':sha(app),'spi_sha256':sha(spi),'bytes':len(spi),'crc32':hex(crc),
          'state_address':hex(STATE),'state_file_offset':hex(STATE_OFFSET),'runtime_address':hex(RUNTIME),'runtime_bytes':blob_size,'runtime_load_offset':hex(LOAD_OFFSET),'app_bytes':len(app),'boot_asset_bytes':len(asset),'boot_frame_sha256':sha(frame),'code_bytes':len(code),'firmware_id':firmware_id,'labels':dict(zip(['dispatch','refresh','guard','finish','led','adv','window','ota_finalize','boot'],map(hex,labels))),
          'helper_address':hex(helper_address),'helper_bytes':helper_size,'busy_timeout_address':hex(timeout_address),'busy_timeout_seconds':90,
          'panel_reset_address':hex(reset_address),'panel_reset_low_iterations':40000,'panel_reset_settle_iterations':180000,
          'advertising_default':'continuous connectable, 1022.5 ms interval; native extended sleep between events',
          'advertising_interval_ms':1022.5,'advertising_name':'ELINK-BWR- plus actual uppercase MAC low 24 bits',
          'full_refresh_cleanup':'full white erase then full target, asynchronous BUSY phases; target RAM retained',
          'boot_identity_address':hex(BASE+0x2249),'boot_identity_bytes':len(identity),'boot_identity':'full per-device OTP MAC; not a fixed shared address',
          'boot_frame_identity_dynamic':True,'boot_frame_hash_scope':'constant background before dynamic MAC text',
          'boot_preview_mac':'18:BC:5A:6B:91:A7 (example only)',
          'led_policy':'P0_2/P2_5/P2_9 active-low; output high in display-open path and before every wake pad latch',
          'leds_off_address':hex(leds_off_address),'wake_pins_address':hex(wake_pins_address),
          'patches':patches,'hardware_tested':False,
          'offline_album':{'slots':7,'frame_bytes':8000,'flash_start':'0x40000','flash_end':'0x5e000','metadata_pages':['0x40000','0x41000'],'image_banks':['0x42000','0x4a000'],'extra_image_banks':['0x52000','0x58000'],'required_native_id':'a112','state_address':'0x07fd2140','state_bytes':124,'state_limit':128,'wire_version':3,'save_steps':32,'save_step_bytes':250,'minutes':[60,10080],'atomic_commit':'inactive image bank and alternating CRC metadata; ready byte last','cold_start':'resume first photo without clock calibration; calendar date waits for sync','cursor_persistence':'RAM only; rotation never programs flash'},'flash_offset':0,
          'product_symbols':{name:hex(address) for name,address in product.items()},'product_elf_sha256':elf_hash,
          'product_regions':{name:{'address':hex(address),'bytes':len(raw),'sha256':sha(raw)} for name,(address,raw) in regions.items()},
          'bold_font_bytes':len(font_data),'bold_font_sha256':sha(font_data),
          'small_font_bytes':len(small_data),'small_font_sha256':sha(small_data),'font_sources':'OFL Noto Sans SC: Black 12px ASCII/countdown and run-coded 44px photo digits, Medium 14/18px labels, Black 15/40px existing sizes; OFL Fusion Pixel remaining 12px Chinese; original 66px clock pixels losslessly run-coded',
          'clock_default_refresh_minutes':5,'clock_refresh_alignment':'local wall-clock minute modulo interval','clock_timezone':'local / Europe/Amsterdam with retained DST state',
          'minute_window':{'logical':[138,24,240,95],'native_gates':[9,111],'source_bytes':[3,11],'outside_mask':'R=1, LUT2/3 neutral'},
          'panel':'DA14585 five-pad BWR 250x122','default_refresh':'full',
          'policy_persistence':'retained RAM; full default after power cycle',
          'offline_reminders':{'slots':8,'slot_bytes':8192,'flash_start':'0x26000','flash_end':'0x36000','state_address':'0x07fc8500','state_bytes':256,'recurrence':'fixed-offset daily / weekdays mask','summary_mode':5,'large_text':True,'summary_title_pixels':18,'summary_task_pixels':16,'summary_visible_rows':4,'summary_title_width':72,'reminder_duration_minutes':'0 or 1..120','check_interval_minutes':[1,5,15,60],'time_granularity_seconds':60,'atomic_commit':'CRC32 and readback before READY state','persistence':'SPI Flash; full power loss requires clock resynchronization'},
          'display_status':'BUSY deasserted; optical result and current not measured'}
    functions=json.loads((out/'product-functions.json').read_text(encoding='utf-8'))
    limits=section_limits(ROOT/'source/firmware')
    assert set(limits)==set(regions), 'Module budget must cover every bounded C section'
    space={'format':'elink-module-space-1','module_api_version':modules['api_version'],
           'function_accounting':'C symbol sizes plus image assembly span; shared rodata and alignment are counted only in region totals',
           'modules':module_functions(ROOT/'source/firmware',modules,functions,image_labels),
           'regions':{n:{'address':hex(a),'used':len(b),'limit':limits[n],'free':limits[n]-len(b)} for n,(a,b) in regions.items()},
           'extension':{'used':len(code),'limit':STATE-CODE,'free':STATE-CODE-len(code)},
           'runtime':{'used':blob_size,'limit':BASE+0x121c0-RUNTIME,'free':BASE+0x121c0-RUNTIME-blob_size,
                      'free_scope':'Unloaded tail; includes the application-initialized album state below',
                      'tail_alignment_bytes':24,'album_state_bytes':124,'remaining_tail_bytes':4},
           'app_bytes':len(app),'spi_bytes':len(spi),'firmware_id':firmware_id,
           'app_sha256':sha(app),'spi_sha256':sha(spi),'hardware_tested':False}
    info['static_modules']={'api_version':modules['api_version'],'ids':[m['id'] for m in modules['modules']],
                            'space_report':'space-report.json','runtime_descriptor_bytes':0}
    info['test_features']={'image_payload_bytes':128,'legacy_image_payload_supported':True,
                           'photo_calendar':{'view_command':'9C 03','display_mode':6,'source':'complete checksum-verified upload or current uploaded frame','direct_commit':True,'left_width':174,'date_width':76,'divider':False,'date_updates':'daily after clock sync','solar_term':'term name plus today or days remaining'},
                           'flash_diagnostic':'BC; read-only 90h ID and two high-address samples',
                           'persistent_gallery':True,'offline_photo_rotation':True}
    (out/'space-report.json').write_text(json.dumps(space,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps(info,indent=2),encoding='utf-8')
    import base64
    update={'format':'elink-update-1','board':'da14585-5pad-bwr-250x122','version':args.version,'firmware_id':firmware_id,'sha256':sha(app),'application':base64.b64encode(app).decode()}
    (out/f'elink-bwr-{args.version}.elink-update.json').write_text(json.dumps(update),encoding='utf-8')
    print(json.dumps(info,indent=2))
if __name__=='__main__':main()
