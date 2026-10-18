"""Execute the compiled UI, native fonts/pixel renderer and native display dispatcher."""
import struct,unittest,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from datetime import datetime
from test_firmware import Machine,BASE,STATE,END,FIRMWARE_DIR
from unicorn.arm_const import *
from unicorn import UC_HOOK_CODE

class ProductMachine(Machine):
    def __init__(self):
        self.draws=[];self.stream=[];super().__init__()
        functions=json.loads((FIRMWARE_DIR/'product-functions.json').read_text('utf-8'))
        self.compressed_glyph_address=functions.get('compressed_ink',{}).get('address',0)
        # Actual five-pad panel probe reports a 70-byte LUT; the probe needs SPI hardware.
        self.uc.mem_write(BASE+0x104dc+0x58,struct.pack('<I',70))
        # Legacy waveform cases exercise every minute; real cold default is checked separately.
        self.uc.mem_write(STATE+24,b'\x01')
    def hook(self,uc,a,size,_):
        if a==getattr(self,'compressed_glyph_address',0):
            p=uc.reg_read(UC_ARM_REG_R3);raw=bytes(uc.mem_read(p,100)).split(b'\0',1)[0]
            self.draws.append((uc.reg_read(UC_ARM_REG_R1),uc.reg_read(UC_ARM_REG_R2),raw))
        if a==BASE+0x2cc4:return # Execute, do not stub the function under test.
        if a==BASE+0x3cf4 and getattr(self,'execute_sender',False):return
        if a==BASE+0x4140 and getattr(self,'execute_sender',False):
            self.data_pins.append((self.pin_values.get(0x11),self.pin_values.get(7)))
        if a==BASE+0x3b4c:
            p=uc.reg_read(UC_ARM_REG_R2);raw=bytes(uc.mem_read(p,100)).split(b'\0',1)[0]
            self.draws.append((uc.reg_read(UC_ARM_REG_R0),uc.reg_read(UC_ARM_REG_R1),raw))
        if a==0x07f1dfb8:
            uc.reg_write(UC_ARM_REG_R0,uc.reg_read(UC_ARM_REG_R0)//uc.reg_read(UC_ARM_REG_R1))
            uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR));return
        if a==0x07f1e134: # ROM __aeabi_llsl; native formatter's 64-bit division stays real.
            value=uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R1)<<32)
            shift=uc.reg_read(UC_ARM_REG_R2);value=(value<<shift)&((1<<64)-1) if shift<64 else 0
            uc.reg_write(UC_ARM_REG_R0,value&0xffffffff);uc.reg_write(UC_ARM_REG_R1,value>>32)
            uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR));return
        if a==BASE+0x3cf4:
            # SPI hardware boundary; native array sender handles CS/DC, unlike raw SPI byte.
            self.stream.extend(uc.mem_read(uc.reg_read(UC_ARM_REG_R0),uc.reg_read(UC_ARM_REG_R1)))
        if a in (BASE+0x3c48,BASE+0x3c84):
            self.commands.append((a,uc.reg_read(UC_ARM_REG_R0),uc.reg_read(UC_ARM_REG_R1),uc.reg_read(UC_ARM_REG_R2),uc.reg_read(UC_ARM_REG_R3)))
            uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR));return
        return super().hook(uc,a,size,_)
    def draw(self,h=9,minute=58,year=2026,month=10,day=5,weekday=1,force=0):
        self.uc.mem_write(STATE+27,bytes([self.uc.mem_read(STATE+27,1)[0]|1]))
        for off,value in ((8,year),(12,weekday),(16,year-2020),(20,7),(24,24)):
            self.uc.mem_write(BASE+0xdd98+off,struct.pack('<I',value))
        for off,value in ((28,month-1),(32,day-1),(36,h),(40,minute)):
            self.uc.mem_write(BASE+0x104dc+off,struct.pack('<I',value))
        self.uc.reg_write(UC_ARM_REG_R0,force);self.uc.reg_write(UC_ARM_REG_LR,END|1)
        self.uc.emu_start(BASE+0x2cc5,END,count=2500000)
        assert self.uc.reg_read(UC_ARM_REG_PC)==END, hex(self.uc.reg_read(UC_ARM_REG_PC))
        assert self.uc.reg_read(UC_ARM_REG_SP)==BASE+0x1d000
        return bytes(self.uc.mem_read(BASE+0xdedc,4000))+bytes(self.uc.mem_read(BASE+0xf15c,4000))
    def finish(self):
        self.busy=0
        for _ in range(2):
            self.run(BASE+0x4208)
            if not self.status()['busy']:return
        raise AssertionError('Display did not finish within erase + target phases')
    def update_sequence(self):return [c[2] for c in self.commands if c[0]==BASE+0x3c10 and c[1]==0x22][-1]

def frame_matches(frame,value,size,x,y,plane='black'):
    """Region (x,y)+cell must equal the exact-size host mask: nothing cropped, nothing extra."""
    from bitmap_fonts import text_mask
    mask=text_mask(value,size)
    for j in range(mask.height):
        for i in range(mask.width):
            pos=(249-x-i)*16+(y+j)//8;bit=128>>((y+j)%8)
            on=bool(frame[4000+pos]&bit) if plane=='red' else not frame[pos]&bit
            if on!=bool(mask.getpixel((i,j))):return False
    return True

class ProductUi(unittest.TestCase):
    def test_clock_header_fourteen_pixels_and_lower_black_rule(self):
        from bitmap_fonts import text_mask
        m=ProductMachine();m.cmd(b'\x94\x01\x0a')
        for weekday,day in enumerate('日一二三四五六'):
            for hour,period in ((9,'AM'),(15,'PM')):
                frame=m.draw(weekday=weekday,h=hour,force=128);m.finish()
                for value,x in (('2026/10/05',12),('星期',96),(day,124),(period,146)):
                    self.assertTrue(frame_matches(frame,value,14,x,4),value+' must use complete 14px glyphs')
                self.assertLessEqual(12+text_mask('2026/10/05',14).width,96)
                self.assertLessEqual(124+text_mask(day,14).width,146)
                self.assertLessEqual(146+text_mask(period,14).width,176)
                for x in range(12,250):
                    pos=(249-x)*16+22//8;bit=128>>(22%8)
                    self.assertFalse(frame[pos]&bit,'Black separator must reach x249 at y22')
                    self.assertFalse(frame[4000+pos]&bit,'Separator must not contain red pixels')
                self.assertFalse(any(frame[4000+(249-x)*16+20//8]&(128>>(20%8)) for x in range(250)), 'Old rule row must be clear')
        before=m.draw(h=9,minute=58,force=128);m.finish()
        after=m.draw(h=9,minute=59);m.finish()
        self.assertEqual(m.update_sequence(),0xc7)
        self.assertEqual(before[4000:],bytes(4000),'Clock page must contain no red pixels')
        self.assertEqual(before[4000:],after[4000:])
        for x in range(12,250):
            pos=(249-x)*16+22//8;bit=128>>(22%8)
            self.assertFalse(after[pos]&bit,'Quick refresh must keep the complete black rule')

    def test_readable_boot_specification_and_clock_footer_use_native_larger_sizes(self):
        m=ProductMachine();m.run(BASE+0x2224);m.finish()
        frame=bytes(m.uc.mem_read(BASE+0xdedc,4000))+bytes(m.uc.mem_read(BASE+0xf15c,4000))
        self.assertTrue(frame_matches(frame,'BWR 2.13 / 250x122',18,19,61),'Specification must use the 18px table')
        self.assertTrue(frame_matches(frame,'V'+m.meta['version'],12,148,39,'red'),'Version must be complete red 12px glyphs')
        m.draw(force=128);m.finish()
        frame=bytes(m.uc.mem_read(BASE+0xdedc,4000))
        self.assertTrue(frame_matches(frame,'农历',18,8,103),'Clock footer must use complete 18px glyphs')
        m.finish();m.uc.mem_write(STATE+7,b'\x03');m.uc.mem_write(BASE+0xdd98+20,struct.pack('<I',128|7))
        m.run(BASE+0x2cc4,128);m.finish();frame=bytes(m.uc.mem_read(BASE+0xdedc,4000))+bytes(m.uc.mem_read(BASE+0xf15c,4000))
        for value,size,x,y in (('闰八月廿五',12,171,68),('3天后',18,171,103)):
            self.assertTrue(frame_matches(frame,value,size,x,y),'Calendar leap month and final row must show every source pixel')
        self.assertTrue(frame_matches(frame,'2026',18,171,24,'red'),'Red year must be the native 18px glyphs, not scaled')

    def test_cold_default_is_five_minutes(self):
        self.assertEqual(Machine().status()['clock_refresh_minutes'],5)

    def test_refresh_is_aligned_to_wall_clock_not_elapsed_ticks(self):
        for interval, start, due in ((5,7,10),(15,7,15),(60,57,60),(1,7,8)):
            m=ProductMachine();m.cmd(bytes([0x99,interval,1,0]));m.draw(minute=start,force=128);m.finish()
            before=m.status()['display_generation']
            for minute in range(start+1,due):
                m.draw(minute=minute);self.assertEqual(m.status()['display_generation'],before)
            m.draw(h=10 if due==60 else 9,minute=due%60);m.finish()
            self.assertEqual(m.status()['display_generation'],before+1,f'{interval} min must align to the wall clock')

    def test_netherlands_label_and_dst_transitions_do_not_repeat(self):
        m=ProductMachine();m.cmd(b'\x9d');self.assertTrue(m.published[5]&64,'Timezone capability required')
        for packet, month, hour, result, summer in ((b'\x9f\x01\x00',3,2,3,True),(b'\x9f\x01\x01',10,3,2,False)):
            m.cmd(packet);m.draws.clear();m.draw(month=month,day=29 if month==3 else 25,weekday=0,h=hour,minute=0,force=128);m.finish()
            self.assertEqual(m.word(BASE+0x104dc+36),result)
            self.assertEqual(m.status()['clock_timezone'],'Europe/Amsterdam')
            self.assertEqual(m.status()['clock_summer_time'],summer)
            self.assertIn((100,103,'荷兰'.encode()),m.draws)
            m.draw(month=month,day=29 if month==3 else 25,weekday=0,h=result,minute=5,force=128);m.finish()
            self.assertEqual(m.word(BASE+0x104dc+36),result,'DST adjustment must happen once')
        m.cmd(b'\x9f\x00\x00');self.assertEqual(m.status()['clock_timezone'],'local')
        for packet in (b'\x9f',b'\x9f\x02\x00',b'\x9f\x00\x01'):
            m.cmd(packet);self.assertEqual(m.status()['error'],1)

    def test_quiet_sync_preserves_timezone_and_native_clock_fields(self):
        from protocol import sync_packet
        from datetime import timezone
        m=ProductMachine();m.cmd(b'\x9f\x01\x01')
        packet=sync_packet(datetime(2026,10,6,0,55,tzinfo=timezone.utc),'Europe/Amsterdam')
        m.cmd(b'\x9e'+packet[1:])
        # Execute the actual native clock_set stores, before unmodelled holiday/timer ROM.
        m.uc.emu_start(BASE+0x6ca7,BASE+0x6cdc,count=1000)
        self.assertEqual(m.word(BASE+0x104dc+28),9)
        self.assertEqual(m.word(BASE+0x104dc+32),5)
        self.assertEqual(m.word(BASE+0x104dc+36),2)
        self.assertEqual(m.word(BASE+0x104dc+40),55)
        self.assertEqual(m.word(BASE+0xdd98+24),25)
        self.assertEqual(m.status()['clock_timezone'],'Europe/Amsterdam')
        self.assertTrue(m.status()['clock_summer_time']);self.assertTrue(m.status()['time_initialized'])

    def test_static_pages_sixty_ticks_and_calendar_daily_refresh(self):
        from protocol import image_packets
        for mode in (2,3,4):
            m=ProductMachine();m.draw();m.finish()
            if mode==2:
                for p in image_packets(bytes([255])*4000+bytes(4000),77):m.cmd(p)
            else:m.cmd(b'\x9c'+bytes([1 if mode==3 else 2]))
            m.finish();before=len(m.commands);generation=m.status()['display_generation']
            for minute in range(60):m.draw(h=10,minute=minute)
            self.assertEqual(len(m.commands),before,'A static page must not refresh on minute ticks')
            m.draw(day=6,weekday=2)
            if mode==3:
                m.finish();self.assertEqual(m.status()['display_generation'],generation+1)
                self.assertEqual(sum(c[0]==BASE+0x3c10 and c[1]==0x22 for c in m.commands[before:]),1,'Calendar day change needs one full update, no extra erase')
            else:self.assertEqual(len(m.commands),before)

    def test_fast_clock_exit_erases_white_then_commits_target_once_and_recovers_timeout(self):
        from protocol import image_packets
        for target in ('default','calendar','notice'):
            m=ProductMachine();m.cmd(b'\x94\x01\x0a');m.draw();m.finish();m.draw(minute=59);m.finish()
            generation=m.status()['display_generation'];m.stream.clear()
            if target=='notice':
                frame=bytes([0x5a])*4000+bytes(4000)
                for p in image_packets(frame,123):m.cmd(p)
            else:m.cmd(b'\x9c'+bytes([2 if target=='default' else 1]))
            retained=bytes(m.uc.mem_read(BASE+0xdedc,4000))+bytes(m.uc.mem_read(BASE+0xf15c,4000))
            self.assertEqual(m.stream,[255]*4000+[0]*4000,'Clear both controller planes without discarding the target')
            self.assertEqual(m.update_sequence(),0xf7)
            m.busy=0;m.run(BASE+0x4208)
            self.assertTrue(m.status()['busy']);self.assertEqual(m.status()['display_generation'],generation)
            self.assertEqual(bytes(m.uc.mem_read(BASE+0xdedc,4000))+bytes(m.uc.mem_read(BASE+0xf15c,4000)),retained)
            self.assertEqual(m.update_sequence(),0xf7)
            m.run(BASE+0x4208);self.assertFalse(m.status()['busy']);self.assertEqual(m.status()['display_generation'],generation+1)
        # A stuck erase must never launch the target or report success.
        m=ProductMachine();m.cmd(b'\x94\x01\x0a');m.draw();m.finish();m.draw(minute=59);m.finish();m.cmd(b'\x9c\x02')
        generation=m.status()['display_generation'];before=m.calls.count(BASE+0x40e8);m.busy=1
        for _ in range(225):m.run(BASE+0x4208)
        self.assertEqual(m.status()['error'],4);self.assertEqual(m.status()['display_generation'],generation)
        self.assertEqual(m.calls.count(BASE+0x40e8),before,'Timeout must not reload target')
        self.assertFalse(m.status()['busy'])

    def test_timezone_setting_preserves_clock_exit_cleanup_history(self):
        m=ProductMachine();m.cmd(b'\x94\x01\x0a');m.draw();m.finish();m.draw(minute=59);m.finish()
        m.cmd(b'\x9f\x01\x01');m.stream.clear();m.cmd(b'\x9c\x01')
        self.assertEqual(m.stream,[255]*4000+[0]*4000,'Settings must retain the clock history required for white cleanup')
        m.finish();self.assertFalse(m.status()['busy'])

    def test_actual_mac_suffix_and_native_1022ms_advertising_parameters(self):
        for address in ('18BC5A6B91A7','18BC5A6B8EBF','18BC5A6B8683','18BC5A6B8666'):
            m=ProductMachine();m.uc.mem_write(BASE+0x10520,bytes.fromhex(address)[::-1])
            m.uc.reg_write(UC_ARM_REG_R6,BASE+0x104dc)
            m.uc.emu_start(BASE+0x5797,BASE+0x57c4,count=1000000)
            ptr=m.uc.reg_read(UC_ARM_REG_R7)
            self.assertEqual(bytes(m.uc.mem_read(ptr,17)),('ELINK-BWR-'+address[-6:]).encode()+b'\0')
        m=ProductMachine()
        def allocate(uc,a,size,_):
            if a==0x07f1bbb0 and uc.reg_read(UC_ARM_REG_R0)==0x0d0d:
                uc.reg_write(UC_ARM_REG_R0,BASE+0x1c000);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
        # Replace only the ROM allocator boundary; native interval setup is executed.
        m.uc.hook_add(UC_HOOK_CODE,allocate)
        m.run(BASE+0x27a0)
        command=bytes(m.uc.mem_read(BASE+0x1c000,82))
        self.assertEqual(struct.unpack_from('<HH',command,4),(1636,1636));self.assertEqual(command[8],7)
        self.assertEqual(m.meta['advertising_interval_ms'],1022.5)

    def test_clock_centered_complete_footer_year_and_next_term(self):
        from bitmap_fonts import text_mask
        m=ProductMachine()
        for year,month,day,wanted in ((2026,10,5,'寒露3天后'),(2026,10,8,'寒露今日'),(2026,12,31,'小寒5天后')):
            m.draws.clear();m.draw(year=year,month=month,day=day,force=128);m.finish()
            self.assertIn((244-text_mask(wanted,18).width,103,wanted.encode()),m.draws,'Term is right-aligned to the header rule')
            self.assertIn((8,103,'农历八月廿五'.encode()),m.draws)
            digits=[(x,y) for x,y,s in m.draws if x in (11,139)]
            self.assertEqual(digits,[(11,1),(139,1)])
        # Leap lunar month must still leave a gap before the longest term label.
        m.uc.mem_write(BASE+0xdd98+20,struct.pack('<I',128|7))
        for off in (0xdedc-8,0xdedc+4000,0xf15c-8,0xf15c+4000):m.uc.mem_write(BASE+off,b'guard123')
        m.uc.mem_write(BASE+0xdd98+16,struct.pack('<I',5))
        m.draws.clear();m.uc.mem_write(STATE+27,b'\x01');m.uc.reg_write(UC_ARM_REG_R0,128)
        m.run(BASE+0x2cc4,128);m.finish()
        self.assertIn((8,103,'农历闰八月廿五'.encode()),m.draws)
        term=[(x,s) for x,y,s in m.draws if y==103 and x>8][0]
        self.assertLess(8+text_mask('农历闰八月廿五',18).width+8,term[0],'Leap footer must leave a gap before the term')
        for off in (0xdedc-8,0xdedc+4000,0xf15c-8,0xf15c+4000):self.assertEqual(bytes(m.uc.mem_read(BASE+off,8)),b'guard123')
        actual=bytes(m.uc.mem_read(BASE+0xdedc,4000))
        self.assertTrue(frame_matches(actual,'农历闰八月廿五',18,8,103),'Footer glyph cropped or overwritten')
    def test_boot_alignment_and_widest_mac_fit_before_battery(self):
        import sys
        from test_firmware import ROOT
        sys.path.insert(0,str(ROOT/'source/firmware'))
        from bitmap_fonts import text_mask
        m=ProductMachine();m.uc.mem_write(BASE+0x10520,bytes([0xaa])*6)
        m.run(BASE+0x2224)
        frame=bytes(m.uc.mem_read(BASE+0xdedc,4000))
        black=lambda x,y:not frame[(249-x)*16+y//8]&(128>>(y%8))
        # Title, specification, rule and MAC share the left edge beside the red bar.
        # MAC_X=20 aligns the 14 hex glyphs with a 1px bearing; 'A' and '4' sit 1px further left.
        for low,high,edge in ((20,49,21),(62,78,21),(83,83,21),(89,98,20)):
            self.assertEqual(min(x for y in range(low,high+1) for x in range(12,176) if black(x,y)),edge)
        for y in list(range(50,62))+list(range(79,83))+list(range(84,89)):
            self.assertFalse(any(black(x,y) for x in range(12,176)),f'row {y} must stay blank')
        mac=[(x,y) for x,y,s in m.draws if s==b'AA:AA:AA:AA:AA:AA']
        self.assertEqual(mac,[(20,87)])
        mac_end=20+text_mask('AA:AA:AA:AA:AA:AA',12).width
        self.assertLess(mac_end,176,'Widest MAC must not overlap Bluetooth icon')
        for x in range(mac_end,176):
            for y in range(89,99):
                self.assertTrue(frame[(249-x)*16+y//8] & (128>>(y%8)))
    def test_boot_battery_unknown_curve_and_maximum_label_fit(self):
        m=ProductMachine()
        for adc,wanted in ((0,b'--%'),(1136,b'0%'),(1248,b'2%'),(1360,b'4%'),(1472,b'16%'),(1584,b'28%'),(1647,b'65%'),(1705,b'100%'),(1706,b'100%')):
            m.draws.clear();m.uc.mem_write(BASE+0x104dc+0x18,struct.pack('<H',adc))
            for off in (0xdedc-8,0xdedc+4000,0xf15c-8,0xf15c+4000):m.uc.mem_write(BASE+off,b'guard123')
            m.run(int(m.meta['product_symbols']['product_boot_battery'],16))
            self.assertEqual([s for x,y,s in m.draws],[b'BWR 2.13 / 250x122',wanted])
            for off in (0xdedc-8,0xdedc+4000,0xf15c-8,0xf15c+4000):self.assertEqual(bytes(m.uc.mem_read(BASE+off,8)),b'guard123')
    def test_mask_uses_real_native_array_sender_with_selected_cs_and_data_dc(self):
        m=ProductMachine();m.execute_sender=True;m.data_pins=[]
        m.uc.mem_write(BASE+0x10558,struct.pack('<I',0x11))
        m.uc.mem_write(BASE+0x10554,struct.pack('<I',7))
        data=BASE+0x18000;m.uc.mem_write(data,bytes(range(16)))
        m.uc.reg_write(UC_ARM_REG_R1,16);m.run(BASE+0x3cf4,data)
        self.assertEqual(m.data_pins,[(0,1)]*16)
        self.assertEqual(m.pin_values[0x11],1)
        self.assertEqual([x[1] for x in m.commands if x[0]==BASE+0x4140],list(range(16)))
    def test_clock_layout_and_minute_only_then_hour_full(self):
        m=ProductMachine();m.cmd(b'\x94\x02\x0a');a=m.draw();m.finish()
        self.assertEqual(m.update_sequence(),0xf7)
        b=m.draw(minute=59);m.finish();self.assertEqual(m.update_sequence(),0xc7)
        changes=[i for i in range(8000) if a[i]!=b[i]];self.assertTrue(changes)
        self.assertTrue(all(i<4000 and 9<=i//16<=111 and 3<=i%16<=11 for i in changes))
        self.assertEqual(m.stream[:4000],[0 if 9<=i//16<=111 and 3<=i%16<=11 else 255 for i in range(4000)])
        self.assertEqual(len(m.stream),4070) # Mask then native quick waveform upload.
        expected=list(m.b[0xdc18:0xdc18+70]);expected[14:28]=[0]*14
        self.assertEqual(m.stream[4000:],expected)
        self.assertEqual(m.stream[4014:4028],[0]*14,'Masked red combinations must be undriven')
        self.assertTrue(any(c[:4]==(BASE+0x3c48,0x0f,9,0) for c in m.commands))
        self.assertIn((BASE+0x3c84,0x01,102,0,0),m.commands)
        m.draw(h=10,minute=0);m.finish();self.assertEqual(m.update_sequence(),0xf7)
        texts=[x[2] for x in m.draws];self.assertIn(b'AM',texts);self.assertIn(b'09',texts);self.assertIn(b'10',texts)
    def test_whole_page_fast_restores_native_waveform_after_experimental_minute_mask(self):
        m=ProductMachine();m.cmd(b'\x94\x01\x03');m.draw(minute=55);m.finish()
        self.assertEqual(m.update_sequence(),0xf7)
        m.commands.clear();m.stream.clear();m.draw(minute=56);m.finish()
        self.assertEqual(m.update_sequence(),0xc7)
        fly=list(m.b[0xdc68:0xdc68+70]);fly[14:28]=[0]*14
        self.assertEqual(m.stream,fly,'Whole-page minute refresh uses native FLY, preserving red pixels')
        self.assertFalse(any(c[0]==BASE+0x3c48 and c[1]==0x0f for c in m.commands))
        self.assertFalse(any(c[:4]==(BASE+0x3c84,0x01,102,0) for c in m.commands))
        m.draw(minute=57);m.finish();self.assertEqual(m.update_sequence(),0xc7)
        m.draw(minute=58);m.finish();self.assertEqual(m.update_sequence(),0xf7,'Periodic BWR full refresh')
        m.cmd(b'\x94\x02\x0a');m.stream.clear();m.draw(minute=59);m.finish()
        self.assertEqual(len(m.stream),4070);self.assertEqual(m.stream[4014:4028],[0]*14)
        m.draw(h=10,minute=0);m.finish();self.assertEqual(m.update_sequence(),0xf7)
        m.cmd(b'\x94\x01\x0a');m.stream.clear();m.draw(h=10,minute=1);m.finish()
        self.assertEqual(m.stream,fly,'Changing back from minute-only must select native FLY')
        m.uc.mem_write(BASE+0x104dc+0x18,struct.pack('<H',1706));m.draw(h=10,minute=2);m.finish()
        self.assertEqual(m.update_sequence(),0xf7,'Header and battery changes require full refresh')
    def test_calendar_all_months_leap_years_bounds_and_daily_update(self):
        import calendar
        from bitmap_fonts import text_mask
        m=ProductMachine();m.uc.mem_write(STATE+7,b'\x03')
        for year,month in ((2021,1),(2022,1),(2024,2),(2025,2),(2026,2),(2026,8),(2026,10),(2027,1)):
            m.draws.clear();first,days=calendar.monthrange(year,month)
            # The 31-day month starting Saturday needs the sixth row.
            for off in (0xdedc-8,0xdedc+4000,0xf15c-8,0xf15c+4000):m.uc.mem_write(BASE+off,b'guard123')
            m.draw(year=year,month=month,day=1,weekday=(first+1)%7,force=128);m.finish()
            dense=(first+1)%7+days>35;pitch=13 if dense else 15
            # Day numbers are centred in their 22px cell using the drawn table's advances.
            inset=lambda v:(22-text_mask(v.decode(),12 if dense else 15).width)>>1
            cells=[(x-inset(v),y,int(v)) for x,y,v in m.draws if v.isdigit() and 44<=y<=110 and x<167 and (x-inset(v)-6)%22==0]
            self.assertEqual([v for x,y,v in cells],list(range(1,days+1)))
            self.assertEqual(cells[0][:2],(6+((first+1)%7)*22,44))
            self.assertLessEqual(max(y for x,y,v in cells)+pitch,122)
            bw=bytes(m.uc.mem_read(BASE+0xdedc,4000));red=bytes(m.uc.mem_read(BASE+0xf15c,4000))
            x,y=cells[0][:2];colors=set()
            for xx in range(x+1,x+21):
                for yy in range(y,y+pitch):
                    pos=(249-xx)*16+yy//8;mask=128>>(yy%8)
                    colors.add((bool(bw[pos]&mask),bool(red[pos]&mask)))
            self.assertEqual(colors,{(True,False),(False,True)},'Today must have white digits and red background only')
            self.assertIn((171,64,'八月廿五'.encode()),m.draws)
            self.assertIn((52,5,('第'+str(datetime(year,month,1).isocalendar().week)+'周').encode()),m.draws)
            for off in (0xdedc-8,0xdedc+4000,0xf15c-8,0xf15c+4000):self.assertEqual(bytes(m.uc.mem_read(BASE+off,8)),b'guard123')
            before=len(m.commands);m.draw(year=year,month=month,day=1,weekday=(first+1)%7,minute=59)
            self.assertEqual(len(m.commands),before,'Monthly calendar must not refresh every minute')
            m.draw(year=year,month=month,day=2,weekday=(first+2)%7);m.finish();self.assertEqual(m.update_sequence(),0xf7)
    def test_am_pm_interval_full_limit_battery_change_and_busy_failure(self):
        m=ProductMachine();m.cmd(b'\x94\x02\x03')
        m.draw(h=23,minute=56);m.finish()
        self.assertIn(b'11',[s for x,y,s in m.draws]);self.assertIn(b'PM',[s for x,y,s in m.draws])
        choices=[]
        for minute in (57,58,59):m.draw(h=23,minute=minute);choices.append(m.update_sequence());m.finish()
        self.assertEqual(choices,[0xc7,0xc7,0xf7])
        m.draw(h=0,minute=0,day=6,weekday=2);m.finish()
        self.assertIn(b'12',[s for x,y,s in m.draws]);self.assertEqual(m.update_sequence(),0xf7)
        m.uc.mem_write(BASE+0x104dc+0x18,struct.pack('<H',1706));m.draw(h=0,minute=1,day=6,weekday=2)
        self.assertEqual(m.update_sequence(),0xf7,'Battery/header changes must force full refresh')
        m.busy=1
        for _ in range(225):m.run(BASE+0x4208)
        self.assertEqual(m.status()['error'],4);self.assertFalse(m.status()['busy'])
        m.draw(h=0,minute=2,day=6,weekday=2);self.assertEqual(m.update_sequence(),0xf7);m.finish()
        m.cmd(b'\x99\x03\x01\x00');before=len(m.commands)
        m.draw(h=0,minute=3,day=6,weekday=2);self.assertGreater(len(m.commands),before);m.finish();before=len(m.commands)
        m.draw(h=0,minute=4,day=6,weekday=2);m.draw(h=0,minute=5,day=6,weekday=2);self.assertEqual(len(m.commands),before)
        m.draw(h=0,minute=6,day=6,weekday=2);self.assertGreater(len(m.commands),before)
    def test_calendar_capability_validation_and_legacy_sync_compatibility(self):
        from protocol import sync_packet
        m=ProductMachine();m.cmd(b'\x9d');self.assertEqual(m.published,b'ELUI\x01'+bytes([255 if m.meta.get('offline_reminders') else 127])+bytes([int(bool(m.meta.get('offline_reminders',{}).get('summary_mode')))+2*int(bool(m.meta.get('offline_reminders',{}).get('large_text')))+12*int(bool(m.meta.get('offline_album'))),0]))
    def test_quiet_publish_sync_does_not_render_clock_or_repaint_static_content(self):
        from protocol import sync_packet,image_packets
        m=ProductMachine();before=len(m.commands)
        m.cmd(b'\x9e'+sync_packet(datetime(2026,10,5,9,58))[1:])
        self.assertEqual(m.status()['display_mode'],2);self.assertTrue(m.status()['time_initialized'])
        m.draw(force=128);self.assertEqual(len(m.commands),before)
        frame=bytes([255])*4000+bytes(4000)
        for p in image_packets(frame,22):m.cmd(p)
        m.finish();before=len(m.commands)
        for minute in (59,0):self.assertEqual(m.draw(h=10,minute=minute),frame)
        self.assertEqual(len(m.commands),before)
        m.cmd(b'\x9e');self.assertEqual(m.status()['error'],1)
        m.uc.mem_write(STATE+8,b'\x01');m.cmd(b'\x9e'+sync_packet()[1:])
        self.assertEqual(m.status()['error'],2)
    def test_calendar_commands_reject_invalid_inputs_and_keep_mode_on_sync(self):
        from protocol import sync_packet
        m=ProductMachine()
        m.cmd(b'\x9c\x01');self.assertEqual(m.status()['error'],1)
        m.cmd(sync_packet(datetime(2026,10,5,9,58)));m.draw(force=128);m.finish()
        m.cmd(b'\x9c\x01');self.assertEqual(m.status()['display_mode'],3);m.finish()
        m.cmd(sync_packet(datetime(2026,10,5,10)));self.assertEqual(m.status()['display_mode'],3)
        for packet in (b'\x9c',b'\x9c\x03',b'\x9d\0',bytes([0x91])+bytes(11),sync_packet(datetime(2026,10,5,10))[:4]+b'\x20'+sync_packet(datetime(2026,10,5,10))[5:]):
            m.cmd(packet);self.assertEqual(m.status()['error'],1)
        m.uc.mem_write(STATE+8,b'\x01');m.cmd(b'\x9c\0');self.assertEqual(m.status()['error'],2)

    def test_default_page_reentry_keeps_own_identity_font_and_survives_minute(self):
        m=ProductMachine();m.uc.mem_write(BASE+0x10520,bytes([0xaa])*6)
        m.uc.mem_write(BASE+0x104dc+0x18,struct.pack('<H',1706))
        m.run(BASE+0x2224);m.finish()
        expected=bytes(m.uc.mem_read(BASE+0xdedc,4000))+bytes(m.uc.mem_read(BASE+0xf15c,4000))
        m.draw(force=128);m.finish();before=m.status()['display_generation']
        m.cmd(b'\x9c\x02');m.finish()
        self.assertEqual(m.status()['display_mode'],4);self.assertEqual(m.status()['error'],0)
        self.assertEqual(m.status()['display_generation'],before+1)
        self.assertEqual(m.draw(minute=59),expected,'Default page must not inherit the clock font or be overwritten')
        before=len(m.commands);m.draw(h=10,minute=0,force=128);self.assertEqual(len(m.commands),before)
        m.uc.mem_write(STATE+7,b'\x01');m.cmd(b'\x9c\x02');self.assertEqual(m.status()['error'],2)

    def test_bluetooth_mark_precedes_battery_and_calendar_status_is_in_header(self):
        m=ProductMachine();m.uc.mem_write(BASE+0x104dc+0x18,struct.pack('<H',1706))
        for mode,x,y,label in ((0,194,4,True),(3,194,4,True),(4,194,89,True)):
            m.uc.mem_write(STATE+7,bytes([mode]));m.draws.clear()
            if mode==4:m.cmd(b'\x9c\x02')
            else:m.draw(force=128)
            m.finish();frame=bytes(m.uc.mem_read(BASE+0xdedc,4000))
            for row,bits in enumerate((48,56,60,567,1843,1023,252,120,252,1023,1843,567,60,56,48)):
                for col in range(11):
                    if bits&(1024>>col):self.assertFalse(frame[(249-(x-18+col))*16+(y-2+row)//8]&(128>>((y-2+row)%8)))
            if label:self.assertIn((x+24,y-2,b'100%'),m.draws)

if __name__=='__main__':unittest.main()
